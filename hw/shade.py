"""`hw shade`: a ReShade replacement that runs on Linux with no injector.

ReShade is a Windows GPU-hook stack (addon + injected plugin). Under Proton it
is fragile and for native games it does not exist — so this module does the
honest CPU equivalent with numpy+Pillow only:

- a post-process chain (exposure, contrast, saturation, lift/gamma/gain, LUT,
  bloom-lite, sharpen, FXAA-lite, vignette, grain) applicable to any PNG/frame;
- a `grade` step that relights the guest layer with the host's local light and
  gives it the host's colour grade — the CPU version of what the worked
  Windows example does in its MCPassthrough.fx (`relight()` there);
- presets for Skyrim day/night and for matching Minecraft pixels to Skyrim.

The chain runs per exported frame (`hw composite` output, `hw capture shot`)
at ~5-15 ms for 720p on this box, or live inside the overlay compositor in
`examples/skyrim-skycraft-linux`. It never hooks any process.

Examples:
  hw shade presets
  hw shade demo --out takes/shade
  hw shade apply --in frame.png --out graded.png --preset skyrim-day
  hw shade apply --in guest.png --out guest-graded.png --grade-from host.png --grade 0.55
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

PRESETS: dict[str, dict] = {
    # neutral: no-op, proves the pipeline is lossless-ish
    "neutral": {},
    # Skyrim day exteriors: slight lift, cooler shadows, gentle bloom+sharpen
    "skyrim-day": {"exposure": 0.06, "contrast": 1.05, "saturation": 1.08,
                   "bloom": 0.25, "bloom_threshold": 0.75,
                   "sharpen": 0.35, "vignette": 0.18},
    # Skyrim night/interiors: protect shadows, warm highlights, stronger bloom
    "skyrim-night": {"exposure": 0.12, "contrast": 1.08, "saturation": 1.04,
                     "lift": (0.012, 0.010, 0.014), "bloom": 0.45,
                     "bloom_threshold": 0.55, "sharpen": 0.25, "vignette": 0.28},
    # guest pixels about to be composited over a Skyrim frame: no grade yet
    # (grade comes from --grade-from), just tame aliasing + light bloom
    "guest-clean": {"sharpen": 0.2, "bloom": 0.2, "bloom_threshold": 0.7,
                    "fxaa": 0.5},
    # ReShade-look showcase: full chain, still cheap
    "reshade-look": {"exposure": 0.04, "contrast": 1.07, "saturation": 1.12,
                     "bloom": 0.35, "bloom_threshold": 0.65, "sharpen": 0.5,
                     "fxaa": 0.6, "vignette": 0.22, "grain": 0.015},
}


def _as_float(img: np.ndarray) -> np.ndarray:
    return img.astype(np.float64) / 255.0


def _as_u8(img: np.ndarray) -> np.ndarray:
    return np.clip(img * 255.0, 0, 255).astype(np.uint8)


def _box_blur(a: np.ndarray) -> np.ndarray:
    p = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode="edge")
    return (p[:-2, :-2] + p[:-2, 1:-1] + p[:-2, 2:] +
            p[1:-1, :-2] + p[1:-1, 1:-1] + p[1:-1, 2:] +
            p[2:, :-2] + p[2:, 1:-1] + p[2:, 2:]) / 9.0


def _luma(a: np.ndarray) -> np.ndarray:
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def apply_exposure(a: np.ndarray, stops: float) -> np.ndarray:
    return np.clip(a * (2.0 ** stops), 0, 1)


def apply_contrast(a: np.ndarray, c: float) -> np.ndarray:
    return np.clip((a - 0.5) * c + 0.5, 0, 1)


def apply_saturation(a: np.ndarray, s: float) -> np.ndarray:
    l = _luma(a)[..., None]
    return np.clip(l + (a - l) * s, 0, 1)


def apply_lift_gamma_gain(a: np.ndarray, lift=(0.0, 0.0, 0.0),
                          gamma=(1.0, 1.0, 1.0), gain=(1.0, 1.0, 1.0)) -> np.ndarray:
    l = np.asarray(lift, dtype=np.float64).reshape(1, 1, 3)
    g = np.asarray(gamma, dtype=np.float64).reshape(1, 1, 3)
    gn = np.asarray(gain, dtype=np.float64).reshape(1, 1, 3)
    out = np.clip(a + l * (1 - a), 0, 1)
    out = np.clip(np.power(np.clip(out, 1e-6, 1), 1.0 / np.clip(g, 1e-3, 10)), 0, 1)
    return np.clip(out * gn, 0, 1)


def apply_bloom(a: np.ndarray, strength: float, threshold: float = 0.65) -> np.ndarray:
    if strength <= 0:
        return a
    lum = _luma(a)
    mask = np.clip((lum - threshold) / max(1e-3, 1 - threshold), 0, 1)[..., None]
    bright = a * mask
    glow = _box_blur(_box_blur(bright))
    return np.clip(a + glow * strength, 0, 1)


def apply_sharpen(a: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0:
        return a
    blur = _box_blur(a)
    return np.clip(a + (a - blur) * amount, 0, 1)


def apply_fxaa_lite(a: np.ndarray, amount: float) -> np.ndarray:
    """One-tap luminance-edge soften: the CPU shadow of FXAA, no GPU needed."""
    if amount <= 0:
        return a
    lum = _luma(a)
    px = np.pad(lum, 1, mode="edge")
    edge = (np.abs(px[1:-1, 2:] - px[1:-1, :-2]) +
            np.abs(px[2:, 1:-1] - px[:-2, 1:-1])) / 2.0
    w = np.clip(edge * 4.0, 0, 1)[..., None] * amount
    return np.clip(a * (1 - w) + _box_blur(a) * w, 0, 1)


def apply_vignette(a: np.ndarray, strength: float) -> np.ndarray:
    if strength <= 0:
        return a
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    dx = (xx / w - 0.5) * 2.0
    dy = (yy / h - 0.5) * 2.0
    d = np.sqrt(dx * dx + dy * dy) / np.sqrt(2.0)
    v = 1.0 - np.clip(d, 0, 1) ** 2 * strength
    return np.clip(a * v[..., None], 0, 1)


def apply_grain(a: np.ndarray, amount: float, seed: int = 7) -> np.ndarray:
    if amount <= 0:
        return a
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(a.shape[:2])[..., None] * amount
    return np.clip(a + n, 0, 1)


def grade_guest_to_host(guest: np.ndarray, host: np.ndarray,
                        light_match: float = 0.8, grade_match: float = 0.55,
                        neutral: float = 0.42) -> np.ndarray:
    """Relight guest pixels with the host's local light + whole-frame grade.

    CPU mirror of the Windows shader's relight(): guest colour is treated as
    albedo, multiplied towards the host's blurred luminance (tinted), then
    pulled towards the host frame's mean colour. Far-haze is the compositor's
    job (it owns depth); this function only fixes light and grade.
    """
    g = _as_float(guest[:, :, :3] if guest.shape[2] == 4 else guest)
    h = _as_float(host[:, :, :3] if host.shape[2] == 4 else host)
    if h.shape[:2] != g.shape[:2]:
        h = np.asarray(Image.fromarray((h * 255).astype(np.uint8))
                       .resize((g.shape[1], g.shape[0]), Image.BILINEAR),
                       dtype=np.float64) / 255.0
    light = _box_blur(_box_blur(h))
    lum = _luma(light)
    gain = np.clip(lum / neutral, 0.42, 1.3)[..., None]
    tint_denom = np.maximum(lum, 1e-3)[..., None]
    tint = np.clip(1.0 + (light / tint_denom - 1.0) * 0.55, 0.55, 1.5)
    out = g * (1 - light_match) + np.clip(g * gain * tint, 0, 1) * light_match
    mean = h.reshape(-1, 3).mean(axis=0).reshape(1, 1, 3)
    mean_lum = float((mean[0, 0, 0] * 0.2126 + mean[0, 0, 1] * 0.7152
                      + mean[0, 0, 2] * 0.0722))
    grade_col = np.clip(1.0 + (mean / max(mean_lum, 1e-3) - 1.0) * 0.6, 0.6, 1.6)
    mx = out.max(axis=2, keepdims=True)
    keep = 1.0 - np.clip((mx - 0.45) * 2.5, 0, 1)  # bright things keep colour
    graded = out * (1 - grade_match * keep) + np.clip(out * grade_col, 0, 1) * (grade_match * keep)
    if guest.shape[2] == 4:
        return np.dstack([_as_u8(graded), guest[:, :, 3]])
    return _as_u8(graded)


def apply_chain(img: np.ndarray, **kw) -> np.ndarray:
    """Run the full chain on a uint8 HxWx3/4 array. Unknown keys are ignored."""
    has_alpha = img.shape[2] == 4
    alpha = img[:, :, 3] if has_alpha else None
    a = _as_float(img[:, :, :3] if has_alpha else img)
    if kw.get("exposure"):
        a = apply_exposure(a, float(kw["exposure"]))
    lift = kw.get("lift", (0.0, 0.0, 0.0))
    gamma = kw.get("gamma", (1.0, 1.0, 1.0))
    gain = kw.get("gain", (1.0, 1.0, 1.0))
    if tuple(lift) != (0.0, 0.0, 0.0) or tuple(gamma) != (1.0, 1.0, 1.0) \
            or tuple(gain) != (1.0, 1.0, 1.0):
        a = apply_lift_gamma_gain(a, lift, gamma, gain)
    if kw.get("contrast", 1.0) != 1.0:
        a = apply_contrast(a, float(kw["contrast"]))
    if kw.get("saturation", 1.0) != 1.0:
        a = apply_saturation(a, float(kw["saturation"]))
    a = apply_bloom(a, float(kw.get("bloom", 0.0)),
                    float(kw.get("bloom_threshold", 0.65)))
    a = apply_sharpen(a, float(kw.get("sharpen", 0.0)))
    a = apply_fxaa_lite(a, float(kw.get("fxaa", 0.0)))
    a = apply_vignette(a, float(kw.get("vignette", 0.0)))
    a = apply_grain(a, float(kw.get("grain", 0.0)),
                    int(kw.get("grain_seed", 7)))
    out = _as_u8(a)
    if has_alpha:
        out = np.dstack([out, alpha])
    return out


def demo_checks(before: np.ndarray, after: np.ndarray, preset: str) -> list[str]:
    errs = []
    if before.shape != after.shape:
        errs.append(f"shape changed {before.shape} -> {after.shape}")
    if after.dtype != np.uint8:
        errs.append(f"dtype is {after.dtype}, want uint8")
    if preset == "neutral" and np.abs(before.astype(int) - after.astype(int)).max() > 1:
        errs.append("neutral preset is not lossless")
    if preset != "neutral" and np.abs(before.astype(int) - after.astype(int)).mean() < 0.5:
        errs.append(f"preset {preset!r} had no visible effect")
    return errs


def register(sub):
    p = sub.add_parser("shade", help="ReShade replacement: CPU postFX, no injector")
    sp = p.add_subparsers(dest="cmd", metavar="<cmd>")

    q = sp.add_parser("presets", help="list built-in grades")
    q.set_defaults(func=lambda a: _r_presets())

    q = sp.add_parser("demo", help="grade synthetic frames, no games needed")
    q.add_argument("--out", default="takes/shade")
    q.add_argument("--preset", default="skyrim-day", choices=sorted(PRESETS))
    q.set_defaults(func=_r_demo)

    q = sp.add_parser("apply", help="grade one PNG with a preset + overrides")
    q.add_argument("--in", dest="inp", required=True)
    q.add_argument("--out", required=True)
    q.add_argument("--preset", default="neutral", choices=sorted(PRESETS))
    q.add_argument("--grade-from", default=None,
                   help="host PNG: relight guest to its light/grade first")
    q.add_argument("--grade", type=float, default=0.55)
    q.add_argument("--light-match", type=float, default=0.8)
    q.add_argument("--exposure", type=float, default=None)
    q.add_argument("--contrast", type=float, default=None)
    q.add_argument("--saturation", type=float, default=None)
    q.add_argument("--bloom", type=float, default=None)
    q.add_argument("--sharpen", type=float, default=None)
    q.add_argument("--vignette", type=float, default=None)
    q.set_defaults(func=_r_apply)
    p.set_defaults(func=lambda a: p.print_help())


def _r_presets():
    for name, kw in PRESETS.items():
        print(f"{name:14} {kw if kw else '(no-op)'}")


def _r_demo(a: argparse.Namespace):
    from hw import composite as comp
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    s = comp.demo_scene()
    Image.fromarray(s["host"]).save(out / "host.png")
    graded = apply_chain(s["host"], **PRESETS[a.preset])
    Image.fromarray(graded).save(out / f"host-{a.preset}.png")
    guest_graded = grade_guest_to_host(s["guest"], s["host"])
    Image.fromarray(guest_graded).save(out / "guest-graded-to-host.png")
    res = comp.composite(apply_chain(s["host"], **PRESETS[a.preset]),
                         s["host_d"], guest_graded, s["guest_d"],
                         overlay=s["overlay"])
    Image.fromarray(res).save(out / "composite.png")
    errs = demo_checks(s["host"], graded, a.preset)
    if a.preset == "neutral":
        pass
    from hw.common import fail
    if errs:
        fail("shade demo FAILED:\n  - " + "\n  - ".join(errs))
    print(f"shade demo OK ({a.preset}): frames in {out}/")


def _r_apply(a: argparse.Namespace):
    img = np.asarray(Image.open(a.inp).convert("RGBA"))
    kw = dict(PRESETS[a.preset])
    for k in ("exposure", "contrast", "saturation", "bloom", "sharpen", "vignette"):
        v = getattr(a, k)
        if v is not None:
            kw[k] = v
    if a.grade_from:
        host = np.asarray(Image.open(a.grade_from).convert("RGBA"))
        img = grade_guest_to_host(img, host, light_match=a.light_match,
                                  grade_match=a.grade)
    out = apply_chain(img, **kw)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    # keep RGB when input had no real alpha
    src = Image.open(a.inp)
    if src.mode == "RGB":
        Image.fromarray(out[:, :, :3]).save(a.out)
    else:
        Image.fromarray(out).save(a.out)
    print(f"wrote {a.out} (preset {a.preset})")
