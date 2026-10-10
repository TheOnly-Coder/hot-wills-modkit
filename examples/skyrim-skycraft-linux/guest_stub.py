"""guest_stub: SkyCraft guest stand-in (stdlib only) for the headless prove-out.

Listens for `cam` on the hw bridge broker, stamps each pose, and mid-run
fires one `explosion` event — the back-channel proof the host daemon must see
in its inbox. Replace with the real guest (Modrinth Fabric 26.3 profile with
the SkyCraft Fabric jar) once its Linux bridge port exists; keep the
cam-per-frame + stamped-frame + single-event discipline.

    python3 guest_stub.py --port 27431 --seconds 20
"""
from __future__ import annotations

import argparse
import json
import socket
import time

PROTO = 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="SkyCraft guest stub (headless prove-out)")
    ap.add_argument("--port", type=int, default=27431)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--event-at", type=float, default=5.0,
                    help="seconds in at which to fire the explosion event")
    a = ap.parse_args(argv)

    s = None
    while s is None:
        try:
            s = socket.create_connection(("127.0.0.1", a.port), timeout=5)
        except OSError:
            time.sleep(0.5)
    s.settimeout(0.05)
    hello = {"v": PROTO, "stamp": int(time.time() * 1000),
             "t": "hello", "game": "skycraft-guest-stub", "role": "guest"}
    s.sendall((json.dumps(hello) + "\n").encode())

    buf = b""
    cams = 0
    fired = False
    states = 0
    t0 = time.time()
    while time.time() - t0 < a.seconds:
        try:
            chunk = s.recv(65536)
        except socket.timeout:
            chunk = b""
        except OSError:
            break
        if chunk:
            buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                msg = json.loads(line.decode())
            except ValueError:
                continue
            if msg.get("t") == "cam":
                cams += 1
            elif msg.get("t") == "state":
                states += 1
        if not fired and time.time() - t0 >= a.event_at:
            ev = {"v": PROTO, "stamp": int(time.time() * 1000), "t": "event",
                  "kind": "explosion", "at": [0.0, 65.0, 0.0], "power": 4.0,
                  "extra": "guest_stub tnt"}
            try:
                s.sendall((json.dumps(ev) + "\n").encode())
                fired = True
                print(f"guest stub: fired explosion event after {cams} cams")
            except OSError:
                break
        time.sleep(0.01)
    print(f"guest stub done: {cams} cams, {states} states seen, event fired={fired}")
    if cams == 0:
        raise SystemExit("guest stub saw no cam — is the host daemon running?")


if __name__ == "__main__":
    main()
