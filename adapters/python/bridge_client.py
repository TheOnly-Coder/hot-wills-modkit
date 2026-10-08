"""hw bridge client: stdlib-only TCP JSON-lines link (protocol v1).

Copy this file into your mod — no `hw` install needed inside the game.
Works anywhere Python runs: Godot Python, Blender, headless sims, test fakes.

    from bridge_client import Bridge
    b = Bridge(game="my-host", role="host")   # connects, retries forever
    b.send_cam(pos=[x, y, z], yaw=yaw, pitch=pitch, fov=70)
    b.send_ground(cols=[[x, z, y], ...])
    for msg in b.listen():                     # generator, reconnects
        if msg["t"] == "event":
            on_guest_event(msg)
"""
from __future__ import annotations

import json
import socket
import time

PROTO = 1
HOST, PORT = "127.0.0.1", 27431


def _ms() -> int:
    return int(time.time() * 1000)


class Bridge:
    def __init__(self, game: str, role: str, host: str = HOST, port: int = PORT,
                 retry_every: float = 1.0):
        self.game, self.role = game, role
        self.host, self.port = host, port
        self.retry_every = retry_every
        self.sock: socket.socket | None = None
        self._buf = b""

    # -- connection ------------------------------------------------------
    def _connect(self) -> socket.socket:
        while True:
            try:
                s = socket.create_connection((self.host, self.port), timeout=5)
                s.settimeout(0.05)
                return s
            except OSError:
                time.sleep(self.retry_every)

    def _ensure(self) -> socket.socket:
        if self.sock is None:
            self.sock = self._connect()
            self._send({"t": "hello", "game": self.game, "role": self.role})
        return self.sock

    # -- sending ----------------------------------------------------------
    def _send(self, body: dict) -> None:
        msg = {"v": PROTO, "stamp": _ms()}
        msg.update(body)
        data = (json.dumps(msg) + "\n").encode()
        s = self._ensure()
        try:
            s.sendall(data)
        except OSError:
            self._drop()
            self._ensure().sendall(data)

    def send_cam(self, pos, yaw: float, pitch: float, fov: float = 70.0) -> None:
        self._send({"t": "cam", "pos": list(pos), "yaw": yaw, "pitch": pitch, "fov": fov})

    def send_ground(self, cols, span: float = 40.0) -> None:
        self._send({"t": "ground", "cols": [list(c) for c in cols], "span": span})

    def send_input(self, keys=(), mouse=(0, 0), buttons=()) -> None:
        self._send({"t": "input", "keys": list(keys), "mouse": list(mouse),
                    "buttons": list(buttons)})

    def send_event(self, kind: str, at=None, power: float = 0.0, **extra) -> None:
        body = {"t": "event", "kind": kind, "power": power}
        if at is not None:
            body["at"] = list(at)
        body.update(extra)
        self._send(body)

    def send_cmd(self, op: str, args=None) -> None:
        self._send({"t": "cmd", "op": op, "args": args or {}})

    def send_state(self, players=(), entities: int = 0) -> None:
        self._send({"t": "state", "players": list(players), "entities": entities})

    # -- receiving ----------------------------------------------------------
    def _drop(self) -> None:
        try:
            if self.sock is not None:
                self.sock.close()
        except OSError:
            pass
        self.sock, self._buf = None, b""

    def listen(self):
        """Yield validated messages forever, reconnecting as needed."""
        while True:
            s = self._ensure()
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                self._drop()
                continue
            if not chunk:
                self._drop()
                continue
            self._buf += chunk
            while b"\n" in self._buf:
                line, self._buf = self._buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line.decode())
                except ValueError:
                    continue
                if isinstance(msg, dict) and msg.get("v") == PROTO:
                    yield msg
