# Minimal Linux passthrough (no ReShade, no real games)

Two fake games exchange camera/state over `hw bridge` while a broker logs everything; then every frame pair
is composited on the CPU with `hw composite`. It proves the whole loop — link, back-channel events, and
depth-tested compositing — on a headless Linux box.

## Run it

```bash
cd examples/linux-passthrough-minimal
bash run_demo.sh        # needs: python3, Pillow, numpy (the kit's only deps)
```

What it does:
1. `hw bridge new-contract` + `check` — scaffold and validate `docs/CONTRACT.md`.
2. `hw bridge serve` + `fake_host.py` + `fake_guest.py` — the host sends an orbiting `cam` and flat `ground`;
   the guest renders colour+depth from each cam and fires one `explosion` event mid-run.
3. Asserts the host saw the `explosion` (back-channel proof, `frames/host_seen_events.jsonl`).
4. `hw composite compose` per frame over `frames/hud.png` (overlay always wins, like a hand/HUD layer).
5. `hw bridge check --log bridge.jsonl` — every logged message validates against protocol v1.

## Look at

- `takes/out_006.png`: guest checkerboard + green cube over the host sky, host red pillar occluding the
  guest cube behind it, white HUD bar on top.
- `bridge.jsonl`: the exact message sequence your real mods must reproduce (`cam` per frame, `ground`,
  1 Hz `state`, one `event`).

## Steal this for a real mod

- `fake_host.py` → your host mod: keep the `send_cam`/`send_ground` call order, replace `render.host_frame`
  with the host's real camera API, replace the event recorder with code that acts events out in-game.
- `fake_guest.py` → your guest mod: keep the cam-following loop, replace `render.guest_frame` with the real
  colour+depth export, keep the stamped-frame discipline (poses carry pixels).
- `render.py` → delete (synthetic stand-in only). `run_demo.sh` steps 1/2/3/5 stay as your CI gate; step 4
  becomes the overlay window or `hw capture record` review.
- Copy the stdlib adapter, not the kit: `adapters/python/bridge_client.py` runs inside games with zero
  dependencies.

## Mapping used here (fake but explicit — yours goes in docs/CONTRACT.md)

Metres; yaw degrees orbiting 0→110; 2 px screen shift per degree; guest ground depth 60, cube 10, host
pillar 20, host sky 200. The compositor rule is guest-wins-iff-nearer (`guest_depth <= host_depth`).
