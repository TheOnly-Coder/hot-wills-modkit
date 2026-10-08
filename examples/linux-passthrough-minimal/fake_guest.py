#!/usr/bin/env python3
"""Fake GUEST game for the minimal Linux passthrough example.

Follows the host's `cam`, renders colour+depth frames from it, and fires one
`explosion` event mid-run so the host can prove its back-channel. Run alongside
fake_host.py with a broker up:  hw bridge serve --port 27431 --log bridge.jsonl
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "examples" / "linux-passthrough-minimal"))
from bridge_client import Bridge  # noqa: E402
import render  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--port", type=int, default=27431)
    ap.add_argument("--outdir", default="frames")
    a = ap.parse_args()
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    render.save_png(out / "hud.png", render.hud_bar())

    b = Bridge(game="example-guest", role="guest", port=a.port)
    n = 0
    for msg in b.listen():
        if msg.get("t") != "cam":
            continue
        yaw = float(msg.get("yaw", 0.0))
        color, depth = render.guest_frame(yaw)
        render.save_png(out / f"guest_{n:03d}.png", color)
        render.save_depth(out / f"guest_{n:03d}.npy", depth)
        if n == a.frames // 2:
            b.send_event("explosion", at=[10.0, 64.0, -3.0], power=4.0)
        n += 1
        if n >= a.frames:
            break
    print(f"guest rendered {n} frames from host cams")


if __name__ == "__main__":
    main()
