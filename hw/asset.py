"""`hw asset`: local art pipeline. No network, no API key, works offline on Linux.

Study the game's own assets first (size, palette, outline, facing), then:
  cutout    chroma/corner-key background removal -> RGBA
  fit       nearest-neighbour resize to exact frame WxH (pixel-art safe)
  pixelate  downscale-then-upscale posterize for pixel-art consistency
  palette   quantize to N colors or map onto a palette PNG
  sheet     pack frames into a spritesheet + JSON manifest (row-major)
  slice     split a sheet back into frames (given tile WxH)
  preview   contact sheet of frames for quick visual checks

Examples:
  hw asset cutout raw.png cut.png --key "#00ff00"
  hw asset fit cut.png 64x64 sprite.png
  hw asset sheet frames/ sheet.png --manifest sheet.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def _parse_color(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def cutout(src: str | Path, dst: str | Path, key: str | None = None, tol: int = 32) -> None:
    """Remove background: explicit hex key, else the median of the border pixels."""
    img = Image.open(src).convert("RGB")
    a = np.asarray(img).astype(int)
    if key:
        bg = np.array(_parse_color(key))
    else:
        border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
        bg = np.median(border, axis=0)
    dist = np.abs(a - bg).sum(axis=2)
    alpha = np.where(dist < tol * 3, 0, 255).astype(np.uint8)
    out = np.dstack([np.asarray(img), alpha])
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out).save(dst)


def fit(src: str | Path, dst: str | Path, size: str) -> None:
    w, h = (int(v) for v in size.lower().split("x"))
    img = Image.open(src)
    img = img.resize((w, h), Image.NEAREST)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    img.save(dst)


def pixelate(src: str | Path, dst: str | Path, px: int = 4) -> None:
    img = Image.open(src).convert("RGB")
    small = img.resize((max(1, img.width // px), max(1, img.height // px)), Image.BILINEAR)
    out = small.resize(img.size, Image.NEAREST)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    out.save(dst)


def palette(src: str | Path, dst: str | Path, colors: int = 16,
            palette_png: str | Path | None = None) -> None:
    img = Image.open(src).convert("RGB")
    if palette_png:
        pal = Image.open(palette_png).convert("RGB")
        pal = pal.resize((colors, 1), Image.NEAREST)
        pal_img = Image.new("P", (1, 1))
        pal_img.putpalette(list(np.asarray(pal).reshape(-1)) + [0] * (768 - colors * 3))
        out = img.quantize(colors=colors, palette=pal_img, dither=Image.NONE).convert("RGB")
    else:
        out = img.quantize(colors=colors, dither=Image.NONE).convert("RGB")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    out.save(dst)


def sheet(frames_dir: str | Path, dst: str | Path, manifest: str | Path | None = None,
          cols: int = 8, pad: int = 0) -> dict:
    files = sorted(Path(frames_dir).glob("*.png"))
    if not files:
        from hw.common import fail
        fail(f"no .png frames in {frames_dir}")
    frames = [Image.open(f).convert("RGBA") for f in files]
    tw, th = frames[0].size
    for f in frames:
        if f.size != (tw, th):
            from hw.common import fail
            fail(f"frame {f} has size {f.size}, want uniform {(tw, th)} — run `hw asset fit` first")
    rows = (len(frames) + cols - 1) // cols
    canvas = Image.new("RGBA", (cols * (tw + pad) - pad, rows * (th + pad) - pad), (0, 0, 0, 0))
    meta = {"tile": [tw, th], "cols": cols, "frames": []}
    for i, (f, img) in enumerate(zip(files, frames)):
        x, y = (i % cols) * (tw + pad), (i // cols) * (th + pad)
        canvas.paste(img, (x, y), img)
        meta["frames"].append({"file": f.name, "x": x, "y": y, "w": tw, "h": th})
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst)
    if manifest:
        Path(manifest).parent.mkdir(parents=True, exist_ok=True)
        with open(manifest, "w") as fh:
            json.dump(meta, fh, indent=2)
    return meta


def slice_sheet(src: str | Path, outdir: str | Path, tile: str) -> list[str]:
    tw, th = (int(v) for v in tile.lower().split("x"))
    img = Image.open(src).convert("RGBA")
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    i = 0
    for y in range(0, img.height, th):
        for x in range(0, img.width, tw):
            p = out / f"frame_{i:03d}.png"
            img.crop((x, y, x + tw, y + th)).save(p)
            paths.append(str(p))
            i += 1
    return paths


def preview(frames_dir: str | Path, dst: str | Path, cols: int = 8, scale: int = 2) -> None:
    meta = sheet(frames_dir, dst, cols=cols)
    img = Image.open(dst)
    img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    img.save(dst)
    _ = meta


def register(sub):
    p = sub.add_parser("asset", help="local art pipeline: cutout, fit, pixelate, palette, sheets")
    sp = p.add_subparsers(dest="cmd", metavar="<cmd>")

    def add(args, help, func):
        q = sp.add_parser(args, help=help)
        func(q)
        return q

    q = sp.add_parser("cutout", help="key out the background -> RGBA")
    q.add_argument("src"); q.add_argument("dst")
    q.add_argument("--key", default=None, help="hex colour, else border median")
    q.add_argument("--tol", type=int, default=32)
    q.set_defaults(func=lambda a: (cutout(a.src, a.dst, a.key, a.tol), print(f"wrote {a.dst}")))

    q = sp.add_parser("fit", help="nearest-neighbour resize to exact WxH")
    q.add_argument("src"); q.add_argument("size"); q.add_argument("dst")
    q.set_defaults(func=lambda a: (fit(a.src, a.dst, a.size), print(f"wrote {a.dst}")))

    q = sp.add_parser("pixelate", help="pixel-art posterize")
    q.add_argument("src"); q.add_argument("dst"); q.add_argument("--px", type=int, default=4)
    q.set_defaults(func=lambda a: (pixelate(a.src, a.dst, a.px), print(f"wrote {a.dst}")))

    q = sp.add_parser("palette", help="quantize to N colours or a palette PNG")
    q.add_argument("src"); q.add_argument("dst")
    q.add_argument("--colors", type=int, default=16)
    q.add_argument("--palette-png", default=None)
    q.set_defaults(func=lambda a: (palette(a.src, a.dst, a.colors, a.palette_png),
                                   print(f"wrote {a.dst}")))

    q = sp.add_parser("sheet", help="pack frames/ into a spritesheet + manifest")
    q.add_argument("frames_dir"); q.add_argument("dst")
    q.add_argument("--manifest", default=None); q.add_argument("--cols", type=int, default=8)
    q.set_defaults(func=lambda a: (sheet(a.frames_dir, a.dst, a.manifest, a.cols),
                                   print(f"wrote {a.dst}")))

    q = sp.add_parser("slice", help="split a sheet into frames/")
    q.add_argument("src"); q.add_argument("outdir"); q.add_argument("tile")
    q.set_defaults(func=lambda a: print("\n".join(slice_sheet(a.src, a.outdir, a.tile))))

    q = sp.add_parser("preview", help="contact sheet of frames/ for quick checks")
    q.add_argument("frames_dir"); q.add_argument("dst")
    q.set_defaults(func=lambda a: (preview(a.frames_dir, a.dst), print(f"wrote {a.dst}")))
    p.set_defaults(func=lambda a: p.print_help())
    _ = add
