"""Shared synthetic renderer for the minimal Linux passthrough example.

Same world as `hw composite demo`, but parameterized by camera yaw so the host
and guest frames visibly move against each other: the host pillar is world-locked
(screen x shifts with yaw), the guest checkerboard is world-locked too. If the
mapping is right, the composited guest sticks to the host world (no swimming).
"""
from __future__ import annotations

import numpy as np
from PIL import Image

W, H = 320, 180
PX_PER_DEG = 2  # fake projection: 2 px per degree of yaw


def host_frame(yaw_deg: float):
    """Sky gradient + host-only red pillar (depth 20) + distant hill (depth 120)."""
    yy, _ = np.mgrid[0:H, 0:W]
    color = np.zeros((H, W, 3), np.uint8)
    color[..., 0] = 40
    color[..., 1] = 90 + (yy * 80 // H).astype(np.uint8)
    color[..., 2] = 160
    depth = np.full((H, W), 200.0)
    color[120:150, 0:120] = (60, 140, 70)
    depth[120:150, 0:120] = 120.0
    px = int(220 + yaw_deg * PX_PER_DEG) % W
    x0, x1 = max(0, px - 20), min(W, px + 20)
    color[40:150, x0:x1] = (200, 30, 30)
    depth[40:150, x0:x1] = 20.0
    return color, depth


def guest_frame(yaw_deg: float):
    """Checkerboard ground (depth 60) + near green cube (depth 10) + hole where the
    host pillar is, so occlusion is testable both ways."""
    xx, yy = np.meshgrid(np.arange(W), np.arange(H))
    ox = int(yaw_deg * PX_PER_DEG) % 32
    chk = (((xx + ox) // 16 + yy // 16) % 2).astype(np.uint8) * 255
    color = np.zeros((H, W, 4), np.uint8)
    color[..., 0] = chk
    color[..., 1] = chk
    color[..., 2] = chk
    color[..., 3] = 255
    depth = np.full((H, W), 60.0)
    gx = int(60 + yaw_deg * PX_PER_DEG) % (W - 70)
    color[60:130, gx:gx + 70, :3] = (30, 200, 60)
    depth[60:130, gx:gx + 70] = 10.0
    # hole where the host pillar is (guest transparent -> host shows through)
    px = int(220 + yaw_deg * PX_PER_DEG) % W
    x0, x1 = max(0, px - 20), min(W, px + 20)
    color[40:150, x0:x1, 3] = 0
    # small guest cube BEHIND the pillar (depth 40 > 20 -> host must win)
    color[70:110, x0:x1, :3] = (30, 200, 60)
    color[70:110, x0:x1, 3] = 255
    depth[70:110, x0:x1] = 40.0
    return color, depth


def hud_bar():
    overlay = np.zeros((H, W, 4), np.uint8)
    overlay[4:14, 4:120, :3] = 255
    overlay[4:14, 4:120, 3] = 255
    return overlay


def save_png(path, arr):
    Image.fromarray(arr).save(path)


def save_depth(path, arr):
    np.save(path, arr.astype(np.float32))
