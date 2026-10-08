# Minimal Linux passthrough (synthetic host x guest)

- game: _example (synthetic stand-in, no real games)
- status: working
- agents: OpenCode (muse-spark)
- versions: hot-wills-modkit 0.1.0, Python 3.12, Pillow 12, numpy 1.26, Ubuntu (headless, no display)
- route: passthrough (composited picture) because the goal was the kit's own pipeline proof

## What was built

`examples/linux-passthrough-minimal`: a fake host (orbiting `cam` + flat `ground`, renders sky + world-locked
pillar) and a fake guest (follows `cam`, renders checkerboard + cube + depth, fires one `explosion` event),
linked by `hw bridge` protocol v1 through the `hw bridge serve` broker, composited per frame with
`hw composite compose` over a HUD overlay. Run with `bash run_demo.sh`.

## How it was verified

- `hw bridge demo` (protocol loopback) and `hw composite demo` (occlusion/alignment/overlay asserts) green.
- `run_demo.sh` gates: contract check, host saw `['explosion']` (back-channel proof), 12/12 frames
  composited, `hw bridge check --log bridge.jsonl` (every message validates against protocol v1).
- Looked at `takes/out_006.png`: guest checkerboard + green cube over host sky, host red pillar occluding the
  guest cube behind it, white HUD bar on top.
- What was NOT verified: real game engines on either side (by design — the fakes are the CI gate; real-game
  slices follow skills/linux-passthrough step 6).

## Gotchas

1. Guest waits forever, script hangs → host `main()` was never called (missing `__main__` guard). Cause: the
   file defined `main()` with no call. Fix: add the guard; design checklists now include "every example script
   runs standalone".
2. `python3 -m hw` from the example dir says "No module named hw" → cwd is not the repo root. Cause: relative
   imports need the kit on `PYTHONPATH`. Fix: `run_demo.sh` exports `PYTHONPATH=$ROOT/../..`.
3. Broker "Address already in use" in tests → the demo grabbed a port and the broker bound it again. Cause:
   double-bind. Fix: broker binds once (port 0 = ephemeral) and the test reads back the bound port.
