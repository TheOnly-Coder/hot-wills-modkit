# Linux compositing without ReShade

- status: working
- agents: OpenCode (muse-spark)
- versions: hot-wills-modkit 0.1.0, Pillow 12, numpy 1.26 (Linux, headless)
- route: technique (CPU depth-tested compositing as the no-hook passthrough route)
- verified: `hw composite demo` asserts occlusion/alignment/overlay; example frames eyeballed (`takes/out_006.png`)

The Windows recipe composites inside the host GPU pass (ReShade add-on, reversed-Z depth, full 6-DoF
re-projection with relighting). The Linux answer in this kit is `hw composite`: outside both processes, on
the CPU, with numpy+Pillow.

## What crosses

- Guest: colour (RGB/RGBA PNG) + depth (float32 `.npy`, metres, larger = farther, inf = sky).
- Host: colour PNG + depth `.npy` (best: raycast grid exported by the host mod) or `--host-far` constant.
- Overlay (hand/HUD): RGBA PNG, drawn last, always wins.

## The rule

Guest wins a pixel iff `guest_alpha > 0 and guest_depth <= host_depth`. `hw composite demo` proves it on a
synthetic scene (guest-near cube, host-near pillar, checkerboard, HUD bar); `demo_checks` asserts all four.

## Re-projection

`--shift dx,dy` is a 2.5D integer shift that hides one frame of link latency for small rotations. It is not
a 6-DoF warp: measure pose lag with a gold-wall-vs-skyline scene; if lag exceeds ~2 frames, fix the link
(don't warp). `--match-exposure` approximates the host grade by mean-luminance scaling when the host mod
can't export lighting.

## Budget (720p, numpy)

cam send <2 ms → guest render (the big one; drop guest resolution first) → export → composite ~5–15 ms →
display 1 vsync. Keep end-to-end under ~100 ms or motion swims.

## When to graduate to a native plugin

Interiors without a host-depth export, or scenes needing host lighting/shadows on guest pixels. That is a
scheduled milestone after the no-hook slice ships — the no-hook slice is also its oracle (same poses, same
contract, pixel-diff the two compositors).
