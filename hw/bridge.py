"""`hw bridge`: the passthrough link between two running games (protocol v1).

Own API, zero-dependency default: newline-delimited JSON over TCP on 127.0.0.1
(port 27431). The same messages also go over WebSocket (port 27432) when the
`websockets` package is installed, and via a file-drop directory for engines
where sockets are blocked. No ReShade, no DLL injection, no Windows required:
each game's mod only needs its normal scripting API (Fabric, BepInEx, UE4SS,
GDScript, Lua ...) to send camera/state and receive events.

Message types (`t` field, every message carries `v: 1` and `stamp` ms):
  hello   {game, role: host|guest, proto: 1}          handshake
  cam     {pos: [x,y,z], yaw, pitch, fov}             host -> guest, every frame
  ground  {cols: [[x,z,y]...], span}                  host -> guest collision columns
  input   {keys: [...], mouse: [dx,dy], buttons: [...]} focus owner -> other side
  event   {kind, at: [x,y,z], power, extra}           guest -> host (explosion, ...)
  cmd     {op, args}                                  director -> either side
  state   {players: [...], entities: n}               either side, 1 Hz heartbeat
  bye     {}                                          clean disconnect

Coordinates: metres; yaw degrees (0 = +Z, clockwise seen from above);
pitch degrees (+ = up). Map per-game axes in docs/CONTRACT.md, never in code.

Examples:
  hw bridge new-contract --host "My Host" --guest "My Guest" --out docs/CONTRACT.md
  hw bridge check docs/CONTRACT.md
  hw bridge serve --port 27431          # log + relay messages between two sides
  hw bridge send --port 27431 '{"t":"cam","pos":[1,2,3],"yaw":90.0,"pitch":0.0}'
  hw bridge demo                       # loopback self-test, no games needed
"""
from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from pathlib import Path

from hw import DEFAULT_TCP_PORT, PROTO_VERSION

REQUIRED = {
    "hello": ["game", "role"],
    "cam": ["pos", "yaw", "pitch"],
    "ground": ["cols"],
    "input": [],
    "event": ["kind"],
    "cmd": ["op"],
    "state": [],
    "bye": [],
}
ROLES = {"host", "guest", "director", "observer"}
EVENT_KINDS = {"explosion", "projectile", "damage", "pickup", "teleport", "custom"}


def now_ms() -> int:
    return int(time.time() * 1000)


def make(t: str, stamp: int | None = None, **fields) -> dict:
    msg = {"v": PROTO_VERSION, "t": t, "stamp": now_ms() if stamp is None else stamp}
    msg.update(fields)
    return msg


def validate(msg: dict) -> list[str]:
    """Return a list of problems (empty = valid). Never raises on dict input."""
    errs = []
    if not isinstance(msg, dict):
        return ["message must be a JSON object"]
    if msg.get("v") != PROTO_VERSION:
        errs.append(f"v must be {PROTO_VERSION}, got {msg.get('v')!r}")
    t = msg.get("t")
    if t not in REQUIRED:
        errs.append(f"unknown t={t!r}; want one of {sorted(REQUIRED)}")
        return errs
    for f in REQUIRED[t]:
        if f not in msg:
            errs.append(f"{t}: missing field {f!r}")
    if t == "hello" and msg.get("role") not in ROLES:
        errs.append(f"hello: role must be one of {sorted(ROLES)}")
    if t == "cam":
        pos = msg.get("pos")
        if not (isinstance(pos, list) and len(pos) == 3 and all(isinstance(x, (int, float)) for x in pos)):
            errs.append("cam: pos must be [x, y, z] numbers")
        for k in ("yaw", "pitch"):
            if k in msg and not isinstance(msg[k], (int, float)):
                errs.append(f"cam: {k} must be a number")
    if t == "event" and msg.get("kind") not in EVENT_KINDS:
        errs.append(f"event: kind must be one of {sorted(EVENT_KINDS)}")
    if t == "ground" and not isinstance(msg.get("cols"), list):
        errs.append("ground: cols must be a list of [x, z, y] columns")
    return errs


def encode(msg: dict) -> bytes:
    return (json.dumps(msg, separators=(",", ":")) + "\n").encode()


def decode_line(line: bytes) -> tuple[dict | None, list[str]]:
    try:
        msg = json.loads(line.decode())
    except Exception as e:
        return None, [f"bad JSON: {e}"]
    return msg, validate(msg)


# ------------------------------------------------------------- contract

CONTRACT_TEMPLATE = """# Passthrough contract: {host} x {guest}
<!-- checked by `hw bridge check`. Keep this file where both mod repos can read it. -->

- proto: 1
- transport: tcp 127.0.0.1:{port}  (fallback: file-drop dir `{dropdir}`)
- host: {host}        (owns: player, camera, input focus)
- guest: {guest}      (owns: guest simulation near the player)
- units: 1 metre = 1 guest unit. Host (x, y, z) -> guest (x, z + YOFF, -y).
- rates: cam every host frame; ground <= 200 columns/frame; state 1 Hz.
- ownership: host owns the player and takes it back on guest death/exit (`event kind=teleport`).
- lifecycle: either side may start first; both reconnect forever; `bye` on clean exit.
- watchdog: no `cam` for 2000 ms -> guest pauses entities; no `state` for 5000 ms -> host hides guest layer.
- mapping:
  - yaw = 180 - heading; pitch = -pitch (fill in per game after measuring!)
  - YOFF chosen so host feet land on a whole guest block (re-level key rebroadcasts).
- poses carry pixels: every composited frame is stamped with the cam stamp it rendered from.
- what happens when late/full: drop frames, never queue more than 3; events are retried 3x.
"""

CONTRACT_REQUIRED_HEADINGS = ["proto:", "transport:", "host:", "guest:", "units:",
                              "rates:", "ownership:", "lifecycle:", "watchdog:", "mapping:"]


def check_contract(text: str) -> list[str]:
    errs = []
    low = text.lower()
    for h in CONTRACT_REQUIRED_HEADINGS:
        if h not in low:
            errs.append(f"contract missing line starting with {h!r}")
    if "proto: 1" not in low and "proto:1" not in low.replace(" ", ""):
        errs.append("contract must pin `proto: 1`")
    return errs


# ------------------------------------------------------------- broker

class Broker:
    """Minimal relay: every line received on TCP is validated, logged, and
    broadcast to the other connected sides. Directors can watch with --echo."""

    def __init__(self, port: int = DEFAULT_TCP_PORT, log_path: str | Path | None = None,
                 echo: bool = False):
        self.port = port
        self.bound_port: int | None = None
        self.log_path = Path(log_path) if log_path else None
        self.echo = echo
        self.peers: set[socket.socket] = set()
        self.received: list[dict] = []
        self.errors: list[str] = []
        self._stop = threading.Event()

    def _log(self, msg: dict):
        self.received.append(msg)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a") as f:
                f.write(json.dumps(msg) + "\n")
        if self.echo:
            print(json.dumps(msg), flush=True)

    def _handle(self, conn: socket.socket):
        buf = b""
        try:
            while not self._stop.is_set():
                data = conn.recv(65536)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    msg, errs = decode_line(line)
                    if errs:
                        self.errors.extend(errs)
                        continue
                    assert msg is not None
                    self._log(msg)
                    dead = []
                    for p in self.peers:
                        if p is not conn:
                            try:
                                p.sendall(encode(msg))
                            except OSError:
                                dead.append(p)
                    for d in dead:
                        self.peers.discard(d)
        except OSError:
            pass
        finally:
            self.peers.discard(conn)
            try:
                conn.close()
            except OSError:
                pass

    def serve_forever(self, timeout: float | None = None):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", self.port))
        self.bound_port = srv.getsockname()[1]
        srv.listen(8)
        srv.settimeout(0.2)
        t0 = time.time()
        try:
            while not self._stop.is_set():
                if timeout is not None and time.time() - t0 > timeout:
                    break
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                self.peers.add(conn)
                threading.Thread(target=self._handle, args=(conn,), daemon=True).start()
        finally:
            srv.close()

    def stop(self):
        self._stop.set()


def send_one(port: int, msg: dict, host: str = "127.0.0.1", timeout: float = 5.0) -> None:
    errs = validate(msg)
    if errs:
        from hw.common import fail
        fail("refusing to send invalid message:\n  - " + "\n  - ".join(errs))
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(encode(msg))


def _recv_until(sock: socket.socket, want: str, timeout: float = 5.0) -> dict:
    """Read newline-delimited messages until one with t == want arrives."""
    sock.settimeout(timeout)
    buf = b""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            continue
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            msg, errs = decode_line(line)
            assert not errs, errs
            assert msg is not None
            if msg.get("t") == want:
                return msg
    raise TimeoutError(f"never received t={want!r}")


def loopback_demo(port: int = 0) -> dict:
    """Host->guest->host round trip against an in-process broker. No games needed."""
    broker = Broker(port=port or 0)
    th = threading.Thread(target=broker.serve_forever, kwargs={"timeout": 15}, daemon=True)
    th.start()
    t0 = time.time()
    while broker.bound_port is None and time.time() - t0 < 5:
        time.sleep(0.05)
    assert broker.bound_port is not None, "broker did not bind"
    real_port = broker.bound_port
    # guest side: connect and listen; host side: send cam, expect guest event back
    guest = socket.create_connection(("127.0.0.1", real_port), timeout=5)
    host = socket.create_connection(("127.0.0.1", real_port), timeout=5)
    try:
        host.sendall(encode(make("hello", game="demo-host", role="host")))
        host.sendall(encode(make("cam", pos=[10.0, 64.0, -3.0], yaw=180.0, pitch=-10.0, fov=70)))
        # broker broadcasts to the *other* peer, so the guest sees the cam
        got = _recv_until(guest, "cam")
        assert got["pos"] == [10.0, 64.0, -3.0], f"cam did not round-trip: {got}"
        guest.sendall(encode(make("event", kind="explosion", at=[10.0, 64.0, -3.0], power=4.0)))
        back = _recv_until(host, "event")
        assert back["kind"] == "explosion", f"event did not round-trip: {back}"
    finally:
        guest.close()
        host.close()
        broker.stop()
        th.join(timeout=2)
    return {"port": real_port, "cam_ok": True, "event_ok": True}


def register(sub):
    p = sub.add_parser("bridge", help="passthrough link: protocol, contract, broker, loopback demo")
    sp = p.add_subparsers(dest="cmd", metavar="<cmd>")

    q = sp.add_parser("new-contract", help="scaffold docs/CONTRACT.md for a host x guest pair")
    q.add_argument("--host", required=True)
    q.add_argument("--guest", required=True)
    q.add_argument("--port", type=int, default=DEFAULT_TCP_PORT)
    q.add_argument("--dropdir", default="bridge-drop")
    q.add_argument("--out", default="docs/CONTRACT.md")
    q.set_defaults(func=_run_new)

    q = sp.add_parser("check", help="validate a CONTRACT.md (and optionally a .jsonl log)")
    q.add_argument("contract", help="path to CONTRACT.md")
    q.add_argument("--log", default=None, help="bridge .jsonl log to validate message-by-message")
    q.set_defaults(func=_run_check)

    q = sp.add_parser("serve", help="run the relay broker (logs every message)")
    q.add_argument("--port", type=int, default=DEFAULT_TCP_PORT)
    q.add_argument("--log", default="bridge.jsonl")
    q.add_argument("--echo", action="store_true")
    q.add_argument("--seconds", type=float, default=0, help="stop after N seconds (0 = forever)")
    q.set_defaults(func=_run_serve)

    q = sp.add_parser("send", help="send one JSON message to a broker")
    q.add_argument("--port", type=int, default=DEFAULT_TCP_PORT)
    q.add_argument("message", help="JSON object, e.g. '{\"t\":\"cam\",...}'")
    q.set_defaults(func=_run_send)

    q = sp.add_parser("demo", help="loopback self-test: cam + event round trip, no games needed")
    q.add_argument("--port", type=int, default=0)
    q.set_defaults(func=_run_demo)
    p.set_defaults(func=lambda a: p.print_help())


def _run_new(a: argparse.Namespace):
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(CONTRACT_TEMPLATE.format(host=a.host, guest=a.guest, port=a.port, dropdir=a.dropdir))
    print(f"wrote {out} — fill in the mapping section after measuring, then `hw bridge check {out}`")


def _run_check(a: argparse.Namespace):
    from hw.common import fail
    text = Path(a.contract).read_text()
    errs = check_contract(text)
    if a.log:
        from hw.common import load_jsonl
        for i, m in enumerate(load_jsonl(a.log)):
            for e in validate(m):
                errs.append(f"log line {i + 1}: {e}")
    if errs:
        fail("contract/log problems:\n  - " + "\n  - ".join(errs))
    print("contract OK" + (f" + log OK ({a.log})" if a.log else ""))


def _run_serve(a: argparse.Namespace):
    print(f"broker on 127.0.0.1:{a.port} (log {a.log}) — Ctrl-C to stop")
    Broker(port=a.port, log_path=a.log, echo=a.echo).serve_forever(
        timeout=a.seconds or None)


def _run_send(a: argparse.Namespace):
    try:
        msg = json.loads(a.message)
    except json.JSONDecodeError as e:
        from hw.common import fail
        fail(f"not JSON: {e}")
    send_one(a.port, msg)
    print("sent")


def _run_demo(a: argparse.Namespace):
    res = loopback_demo(port=a.port)
    print(f"loopback OK on 127.0.0.1:{res['port']} (cam round-trip + event round-trip)")
