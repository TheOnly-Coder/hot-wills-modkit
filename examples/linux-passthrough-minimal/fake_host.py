#!/usr/bin/env python3
"""Fake HOST game for the minimal Linux passthrough example.

Sends an orbiting `cam` + flat `ground` over hw bridge (stdlib adapter, no `hw`
needed), renders its own frames (sky + world-locked pillar), and records inbound
guest `event`s to prove the back-channel. Run alongside fake_guest.py with a
broker up:  hw bridge serve --port 27431 --log bridge.jsonl
"""
import argparse
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "examples" / "linux-passthrough-minimal"))
from bridge_client import Bridge  # noqa: E402
import render  # noqa: E402

POS = [10.0, 64.0, -3.0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--port", type=int, default=27431)
    ap.add_argument("--outdir", default="frames")
    a = ap.parse_args()
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)

    b = Bridge(game="example-host", role="host", port=a.port)
    seen_events = []
    stop = threading.Event()

    def watch():
        for msg in b.listen():
            if stop.is_set():
                break
            if msg.get("t") == "event":
                seen_events.append(msg)

    th = threading.Thread(target=watch, daemon=True)
    th.start()

    flat = [[x, z, 64.0] for x in range(-2, 3) for z in range(-2, 3)]
    for i in range(a.frames):
        yaw = i * 10.0
        b.send_cam(pos=POS, yaw=yaw, pitch=-5.0, fov=70)
        b.send_ground(cols=flat, span=5.0)
        if i % 4 == 0:
            b.send_state(players=["Steve"], entities=3)
        color, depth = render.host_frame(yaw)
        render.save_png(out / f"host_{i:03d}.png", color)
        render.save_depth(out / f"host_{i:03d}.npy", depth)
        time.sleep(0.05)

    time.sleep(1.0)  # let the guest's explosion event arrive
    stop.set()
    with open(out / "host_seen_events.jsonl", "w") as f:
        for e in seen_events:
            f.write(json.dumps(e) + "\n")
    kinds = [e.get("kind") for e in seen_events]
    print(f"host sent {a.frames} cams; back-channel events seen: {kinds or '(none)'}")
    if "explosion" not in kinds:
        print("WARNING: guest explosion event never arrived (run fake_guest.py at the same time)")


if __name__ == "__main__":
    main()
