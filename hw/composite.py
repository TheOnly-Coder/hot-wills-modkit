"""`hw composite`: ReShade-free passthrough compositing on the CPU.

The Windows passthrough recipe composites the guest inside the host's GPU pass
with a ReShade add-on. This module is the Linux answer: no injector, no ReShade,
no GPU hook. The host mod sends camera/state over `hw bridge`, the guest renders
in its own window (or headless), and this compositor depth-tests the guest's
colour+depth against the host's colour+depth with numpy+Pillow, then shows or
saves the result.

Depth convention: metres, LARGER = farther, inf/NaN = sky. Guest wins a pixel
iff guest_alpha > 0 and guest_depth <= host_depth. The hand/HUD overlay layer
always wins (drawn last, like the worked Windows example).

Re-projection is a 2.5D shift (dx, dy pixels from the pose delta), which hides
one frame of link latency for small rotations. It is NOT a full 6-DoF warp:
large translations need the real host camera pose per frame, i.e. keep latency
low instead of warping hard. See knowledge/techniques/linux-compositing-without-reshade.md.

Examples:
  hw composite demo --out takes/demo              # synthetic proof, no games needed
  hw composite compose --host host.png --host-far 50 --guest guest.png \\
      --guest-depth guest.npy --shift 6,-3 --overlay hud.png --out out.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

SKY = float("inf")


def load_color(path: str | Path) -> np.ndarray:
    img = Image.open(path)
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    a = np.asarray(img)
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    return a


def load_depth(path: str | Path | None, shape, far: float = SKY) -> np.ndarray:
    if path is None:
        return np.full(shape[:2], far, dtype=np.float64)
    p = Path(path)
    if p.suffix.lower() == ".npy":
        d = np.load(p).astype(np.float64)
    else:
        d = np.asarray(Image.open(p).convert("F"), dtype=np.float64)
    if d.shape[:2] != shape[:2]:
        d = np.asarray(Image.fromarray(d.astype(np.float32)).resize(
            (shape[1], shape[0]), Image.BILINEAR), dtype=np.float64)
    d[np.isnan(d)] = SKY
    return d


def shift_layer(color: np.ndarray, depth: np.ndarray, dx: int, dy: int):
    """Integer 2.5D re-projection shift. Empty regions become transparent / sky."""
    h, w = depth.shape[:2]
    sc = np.zeros_like(color)
    sd = np.full((h, w), SKY)
    xs, ys = max(0, -dx), max(0, -dy)
    xd, yd = max(0, dx), max(0, dy)
    sh, sw = h - abs(dy), w - abs(dx)
    if sh <= 0 or sw <= 0:
        return sc, sd
    sc[yd:yd + sh, xd:xd + sw] = color[ys:ys + sh, xs:xs + sw]
    sd[yd:yd + sh, xd:xd + sw] = depth[ys:ys + sh, xs:xs + sw]
    return sc, sd


def soften_alpha(alpha: np.ndarray) -> np.ndarray:
    """1 px box blur on the mask to avoid hardaliased edges."""
    a = alpha.astype(np.float64) / 255.0
    pad = np.pad(a, 1, mode="edge")
    blur = (pad[:-2, :-2] + pad[:-2, 1:-1] + pad[:-2, 2:] +
            pad[1:-1, :-2] + pad[1:-1, 1:-1] + pad[1:-1, 2:] +
            pad[2:, :-2] + pad[2:, 1:-1] + pad[2:, 2:]) / 9.0
    return (blur * 255.0).astype(np.uint8)


def composite(host_color: np.ndarray, host_depth: np.ndarray,
              guest_color: np.ndarray, guest_depth: np.ndarray,
              shift: tuple[int, int] = (0, 0),
              overlay: np.ndarray | None = None,
              soften: bool = True,
              match_exposure: bool = False) -> np.ndarray:
    """Depth-tested guest-over-host. All arrays HxW(xC). Returns HxWx3 uint8."""
    h, w = host_color.shape[:2]
    if guest_color.shape[:2] != (h, w):
        g = Image.fromarray(guest_color)
        guest_color = np.asarray(g.resize((w, h), Image.BILINEAR))
        guest_depth = np.asarray(Image.fromarray(
            guest_depth.astype(np.float32)).resize((w, h), Image.BILINEAR),
            dtype=np.float64)
    if guest_color.shape[2] == 3:
        alpha = np.full((h, w), 255, np.uint8)
        rgb = guest_color
    else:
        rgb = guest_color[:, :, :3]
        alpha = guest_color[:, :, 3]
        if soften:
            alpha = soften_alpha(alpha)
    rgb_s, gd_s = shift_layer(rgb, guest_depth, *shift)
    a_s = shift_layer(alpha[:, :, None], guest_depth, *shift)[0][:, :, 0] \
        if shift != (0, 0) else alpha
    a = (a_s.astype(np.float64) / 255.0)[..., None]
    if match_exposure:
        hm = host_color.astype(np.float64).mean() + 1e-6
        gm = rgb_s.astype(np.float64).mean() + 1e-6
        rgb_s = np.clip(rgb_s.astype(np.float64) * (hm / gm), 0, 255)
    host_d = host_depth.astype(np.float64)
    host_d[np.isnan(host_d)] = SKY
    gd = gd_s.astype(np.float64)
    nearer = (a[..., 0] > 0.003) & (gd <= host_d)
    out = host_color.astype(np.float64)
    n3 = nearer[..., None]
    out = np.where(n3, rgb_s.astype(np.float64) * a + out * (1 - a), out)
    if overlay is not None:
        if overlay.shape[:2] != (h, w):
            overlay = np.asarray(Image.fromarray(overlay).resize((w, h), Image.BILINEAR))
        if overlay.shape[2] == 4:
            oa = (overlay[:, :, 3:4].astype(np.float64) / 255.0)
            out = overlay[:, :, :3].astype(np.float64) * oa + out * (1 - oa)
        else:
            mask = overlay.sum(axis=2, keepdims=True) > 0
            out = np.where(mask, overlay[:, :, :3].astype(np.float64), out)
    return np.clip(out, 0, 255).astype(np.uint8)


# ------------------------------------------------------------- synthetic demo

def demo_scene(w: int = 320, h: int = 180):
    """Fake host (sky gradient + red pillar only the host has) and fake guest
    (checkerboard ground + green cube). Returns dict of arrays + depths."""
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:h, 0:w]
    host = np.zeros((h, w, 3), np.uint8)
    host[..., 0] = 40
    host[..., 1] = 90 + (yy * 80 // h).astype(np.uint8)
    host[..., 2] = 160
    host_d = np.full((h, w), 200.0)
    # red pillar, host-only, at x 200..240, depth 20
    host[40:150, 200:240] = (200, 30, 30)
    host_d[40:150, 200:240] = 20.0
    # distant hill band, depth 120
    host[120:150, 0:120] = (60, 140, 70)
    host_d[120:150, 0:120] = 120.0
    guest = np.zeros((h, w, 4), np.uint8)
    chk = ((xx // 16 + yy // 16) % 2).astype(np.uint8) * 255
    guest[..., 0] = chk
    guest[..., 1] = chk
    guest[..., 2] = chk
    guest[..., 3] = 255
    guest_d = np.full((h, w), 60.0)
    # green cube nearer than pillar region overlap? place left, depth 10
    guest[60:130, 60:130, :3] = (30, 200, 60)
    guest_d[60:130, 60:130] = 10.0
    # hole: guest transparent where pillar is, so occlusion is testable both ways
    guest[40:150, 200:240, 3] = 0
    # small guest cube BEHIND the pillar (depth 40 > 20) overlapping pillar x-range
    guest[70:110, 205:235, :3] = (30, 200, 60)
    guest[70:110, 205:235, 3] = 255
    guest_d[70:110, 205:235] = 40.0
    # overlay: white HUD bar on top rows
    overlay = np.zeros((h, w, 4), np.uint8)
    overlay[4:14, 4:120, :3] = 255
    overlay[4:14, 4:120, 3] = 255
    _ = rng  # deterministic anyway
    return {"host": host, "host_d": host_d, "guest": guest, "guest_d": guest_d,
            "overlay": overlay}


def demo_checks(out: np.ndarray, s: dict) -> list[str]:
    errs = []
    # 1. green cube region shows guest green (nearer than host sky 200)
    cube = out[80:110, 80:110]
    if not (cube[..., 1].mean() > 120 and cube[..., 0].mean() < 100):
        errs.append("guest-near cube did not win over host sky")
    # 2. pillar region: host red wins over guest-behind cube (20 < 40)
    pil = out[80:100, 210:230]
    if not (pil[..., 0].mean() > 120 and pil[..., 1].mean() < 100):
        errs.append("host-near pillar did not occlude guest-behind cube")
    # 3. overlay HUD bar is white on top
    hud = out[6:12, 10:100]
    if not (hud.mean() > 200):
        errs.append("overlay HUD bar not on top")
    # 4. checkerboard visible where guest is nearer than host far field
    chk = out[150:170, 150:190].astype(int)
    if chk.std() < 10:
        errs.append("guest checkerboard ground not visible")
    _ = s
    return errs


def register(sub):
    p = sub.add_parser("composite", help="depth-tested guest-over-host compositing (no ReShade)")
    sp = p.add_subparsers(dest="cmd", metavar="<cmd>")

    q = sp.add_parser("demo", help="synthetic occlusion/alignment proof, no games needed")
    q.add_argument("--out", default="takes/demo")
    q.add_argument("--width", type=int, default=320)
    q.add_argument("--height", type=int, default=180)
    q.set_defaults(func=_run_demo)

    q = sp.add_parser("compose", help="composite real frames to a PNG")
    q.add_argument("--host", required=True, help="host colour PNG")
    q.add_argument("--host-depth", default=None, help="host depth .npy (float, metres)")
    q.add_argument("--host-far", type=float, default=float("inf"),
                   help="host depth when --host-depth omitted (default: sky)")
    q.add_argument("--guest", required=True, help="guest colour PNG (RGB or RGBA)")
    q.add_argument("--guest-depth", required=True, help="guest depth .npy (float, metres)")
    q.add_argument("--overlay", default=None, help="hand/HUD overlay PNG (drawn last, always on top)")
    q.add_argument("--shift", default="0,0", help="re-projection shift dx,dy in pixels")
    q.add_argument("--no-soften", action="store_true")
    q.add_argument("--match-exposure", action="store_true")
    q.add_argument("--out", required=True)
    q.set_defaults(func=_run_compose)
    p.set_defaults(func=lambda a: p.print_help())


def _run_demo(a: argparse.Namespace):
    from hw.common import fail
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    s = demo_scene(a.width, a.height)
    res = composite(s["host"], s["host_d"], s["guest"], s["guest_d"],
                    overlay=s["overlay"])
    Image.fromarray(s["host"]).save(out / "host.png")
    Image.fromarray(s["guest"]).save(out / "guest.png")
    Image.fromarray(res).save(out / "out.png")
    errs = demo_checks(res, s)
    if errs:
        fail("demo FAILED:\n  - " + "\n  - ".join(errs) + f"\nframes kept in {out}/")
    print(f"demo OK: occlusion + alignment + overlay all correct. frames in {out}/")


def _run_compose(a: argparse.Namespace):
    host = load_color(a.host)
    host_d = load_depth(a.host_depth, host.shape, far=a.host_far)
    guest = load_color(a.guest)
    guest_d = load_depth(a.guest_depth, guest.shape, far=SKY)
    overlay = load_color(a.overlay) if a.overlay else None
    dx, dy = (int(v) for v in a.shift.split(","))
    out = composite(host, host_d, guest, guest_d, shift=(dx, dy),
                    overlay=overlay, soften=not a.no_soften,
                    match_exposure=a.match_exposure)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out).save(a.out)
    print(f"wrote {a.out}")
