---
name: asset-pipeline
description: Turn art into exactly what the engine loads, fully offline with hw asset: background cutout, nearest-neighbour fit to frame size, pixel-art posterize, palette quantization, spritesheets with manifests, and contact-sheet previews. Use when making sprites, tiles, HUD art, or guest/host placeholder art for a vertical slice.
---

# Asset pipeline (local, no key)

Study the game's own assets first: frame size, palette, outline thickness, camera angle, facing, frame
layout. Match those before generating anything — a correctly-sized placeholder beats a pretty wrong-sized
sprite.

```bash
hw asset cutout raw.png cut.png [--key "#00ff00"]   # border-median key by default
hw asset fit cut.png 64x64 sprite.png               # NEAREST: pixel-art safe
hw asset pixelate big.png px.png --px 4             # consistent pixel-art look
hw asset palette img.png out.png --colors 16 [--palette-png game-pal.png]
hw asset sheet frames/ sheet.png --manifest sheet.json [--cols 8]
hw asset slice sheet.png frames/ 64x64
hw asset preview frames/ contact.png                # look at it before wiring into the game
```

## Rules that prevent rework
- One nearest-neighbour fit to the final frame size, at the end. Never scale twice.
- Sheets need uniform tiles: `fit` every frame first (`sheet` refuses mixed sizes — that error is the
  pipeline telling you a frame is wrong).
- Team-colour / recolour masks: keep a separate mask sheet with the same manifest layout; recolour at build
  time, not by hand-editing frames.
- 3D → sprite (units, buildings): render all headings from the game's camera angle from one model so frames
  stay consistent; `fit` + `palette` onto the game's palette last.
- Guest/host placeholder art for passthrough slices: flat-shaded primitives beat detailed art — alignment and
  occlusion are what you're proving (`hw composite demo` aesthetic on purpose).
- Keep sources (large PNGs, blends) next to the mod; ship only the fitted sheets. `hw publish check` must pass
  on the shipped folder.
