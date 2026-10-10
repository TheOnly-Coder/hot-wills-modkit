"""skycraft_host_daemon: Skyrim-side bridge publisher (stdlib only).

Copy this file anywhere — it needs no `hw` install. It tails Skyrim's
Papyrus.0.log for `SkyCraftBridge cam ...` lines (written by
adapters/papyrus/SkyCraftBridge.psc), converts Skyrim units to the bridge
contract (metres, yaw 0 = +Z clockwise from above, pitch + = up), and
publishes `cam` every frame + `ground` columns + 1 Hz `state` to the hw bridge
broker. Guest `event`s from the broker are appended to the inbox file the
Papyrus side polls, and explosions/damage are also printed for `hw capture`.

No game = still useful: --synthetic orbits a fake camera so the whole
pipeline (bridge -> composite -> shade) proves out headless, exactly like
examples/linux-passthrough-minimal.

    python3 skycraft_host_daemon.py --log Papyrus.0.log --port 27431
    python3 skycraft_host_daemon.py --synthetic --seconds 20
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import socket
import sys
import time

PROTO = 1
UNITS_PER_BLOCK = 70.0  # 1 Minecraft block == 70 Skyrim units (SkyCraft DESIGN.md)

CAM_RE = re.compile(
    r"SkyCraftBridge\s+cam\s+x=(?P<x>-?[\d.]+)\s+y=(?P<y>-?[\d.]+)\s+z=(?P<z>-?[\d.]+)"
    r"\s+yaw=(?P<yaw>-?[\d.]+)\s+pitch=(?P<pitch>-?[\d.]+)")


def skyrim_to_bridge(x: float, y: float, z: float, yaw_z: float, pitch_x: float):
    """Skyrim (X east, Y north, Z up, units) -> bridge (metres, yaw 0=+Z cw, pitch +=up).

    Mirrors SkyCraft docs/DESIGN.md: mc.x = sky.x/70, mc.y = sky.z/70,
    mc.z = -sky.y/70. Yaw: Skyrim GetAngleZ is degrees about +Z; bridge yaw is
    0=+Z clockwise from above, so yaw_bridge = 180 - yaw_sky measured on the
    real game (CONTRACT.md pins the fitted offset; this is the starting fit).
    """
    mx, my, mz = x / UNITS_PER_BLOCK, z / UNITS_PER_BLOCK, -y / UNITS_PER_BLOCK
    yaw = (180.0 - yaw_z) % 360.0
    pitch = -pitch_x
    return [mx, my, mz], yaw, pitch


class Bridge:
    def __init__(self, port: int, game="skyrim-se", role="host"):
        self.port = port
        self.game = game
        self.role = role
        self.sock: socket.socket | None = None
        self._buf = b""

    def _connect(self):
        while True:
            try:
                s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
                s.settimeout(0.05)
                return s
            except OSError:
                time.sleep(1.0)

    def _ensure(self):
        if self.sock is None:
            self.sock = self._connect()
            self._send({"t": "hello", "game": self.game, "role": self.role})
        return self.sock

    def _send(self, body: dict):
        msg = {"v": PROTO, "stamp": int(time.time() * 1000)}
        msg.update(body)
        data = (json.dumps(msg) + "\n").encode()
        try:
            self._ensure().sendall(data)
        except OSError:
            self.sock = None
            self._ensure().sendall(data)

    def send_cam(self, pos, yaw, pitch, fov=75.0):
        self._send({"t": "cam", "pos": list(pos), "yaw": yaw,
                    "pitch": pitch, "fov": fov})

    def send_ground(self, cols, span=40.0):
        self._send({"t": "ground", "cols": [list(c) for c in cols], "span": span})

    def send_state(self, players=1, entities=0):
        self._send({"t": "state", "players": players, "entities": entities})

    def poll(self) -> list[dict]:
        """Non-blocking drain of broker-broadcast messages (guest events)."""
        out = []
        s = self._ensure()
        try:
            chunk = s.recv(65536)
        except (socket.timeout, OSError):
            return out
        if not chunk:
            self.sock = None
            return out
        self._buf += chunk
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                out.append(json.loads(line.decode()))
            except ValueError:
                pass
        return out


def ground_columns(pos, radius=3, step=1.0):
    """Flat stub columns under the player (metres). The real exporter raycasts
    Skyrim Havok; this stub keeps collision honest on flat ground and the
    contract gates the upgrade (slice 3 in linux-passthrough)."""
    cols = []
    for ix in range(-radius, radius + 1):
        for iz in range(-radius, radius + 1):
            cols.append([pos[0] + ix * step, pos[2] + iz * step, pos[1] - 1.0])
            if len(cols) >= 200:
                return cols
    return cols


def tail_log(path: str):
    with open(path, "r", errors="replace") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if line:
                yield line
            else:
                time.sleep(0.1)


def run_live(log_path: str, port: int, inbox: str, fov=75.0):
    b = Bridge(port)
    last_state = 0.0
    print(f"host daemon: tailing {log_path} -> bridge 127.0.0.1:{port}")
    for line in tail_log(log_path):
        m = CAM_RE.search(line)
        if m:
            pos, yaw, pitch = skyrim_to_bridge(float(m["x"]), float(m["y"]),
                                               float(m["z"]), float(m["yaw"]),
                                               float(m["pitch"]))
            b.send_cam(pos, yaw, pitch, fov)
            b.send_ground(ground_columns(pos))
        now = time.time()
        if now - last_state > 1.0:
            b.send_state()
            last_state = now
        for msg in b.poll():
            if msg.get("t") == "event":
                with open(inbox, "a") as f:
                    f.write(json.dumps(msg) + "\n")
                print(f"guest event -> inbox: {msg.get('kind')} {msg.get('at')}")


def run_synthetic(port: int, seconds: float, inbox: str):
    b = Bridge(port)
    t0 = time.time()
    i = 0
    seen_events = 0
    print(f"host daemon: synthetic orbit -> bridge 127.0.0.1:{port} ({seconds}s)")
    while time.time() - t0 < seconds:
        yaw = (i * 5) % 360
        pos = [10.0 * math.cos(math.radians(yaw)), 65.0, 10.0 * math.sin(math.radians(yaw))]
        b.send_cam(pos, float(yaw), 0.0)
        b.send_ground(ground_columns(pos))
        if i % 20 == 0:
            b.send_state()
        for msg in b.poll():
            if msg.get("t") == "event":
                seen_events += 1
                with open(inbox, "a") as f:
                    f.write(json.dumps(msg) + "\n")
        i += 1
        time.sleep(0.05)
    print(f"synthetic done: {i} cams sent, {seen_events} guest events seen")


def default_papyrus_log():
    return os.path.expanduser(
        "~/.local/share/Steam/steamapps/compatdata/489830/pfx/drive_c/users/"
        "steamuser/Documents/My Games/Skyrim Special Edition/Logs/Papyrus.0.log")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default=default_papyrus_log(),
                    help="Papyrus.0.log to tail (live mode)")
    ap.add_argument("--port", type=int, default=27431)
    ap.add_argument("--inbox", default="takes/skycraft-inbox.jsonl")
    ap.add_argument("--fov", type=float, default=75.0)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--seconds", type=float, default=20.0)
    a = ap.parse_args(argv)
    if a.synthetic:
        run_synthetic(a.port, a.seconds, a.inbox)
    else:
        if not os.path.exists(a.log):
            print(f"no log at {a.log} — try --synthetic for a headless prove-out",
                  file=sys.stderr)
            raise SystemExit(1)
        run_live(a.log, a.port, a.inbox, a.fov)


if __name__ == "__main__":
    main()
