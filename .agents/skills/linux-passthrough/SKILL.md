---
name: linux-passthrough
description: Build a two-games-at-once passthrough mod on Linux with no ReShade, no DLL injection and no Windows. Covers the bridge link, guest rendering, CPU depth compositing with hw composite, overlay display, mapping measurement, and latency budgets. Use when the mod must run on Linux, when ReShade/ScriptHook-style injection is unavailable, or as the first slice before any GPU-hook work.
---

# Passthrough on Linux (no ReShade)

The Windows recipe hooks the host's GPU pass (ReShade add-on + injected plugin). On Linux that stack is
fragile under Proton and absent for native games — so don't hook anything. Run both games unmodified apart
from small mods written against their **normal scripting APIs**, and composite outside both processes:

```
host game (+ tiny mod: sends cam/ground, acts out events) --\
                                                             hw bridge (127.0.0.1:27431, JSON lines)
guest game (+ tiny mod: follows cam, sends colour+depth) ---/--> hw composite --> overlay window / video
```

## 1. Prove the pipeline with no games (10 minutes)
```bash
hw bridge demo                                  # cam + event round trip
hw composite demo --out takes/demo              # occlusion + alignment + overlay proof
```
Look at `takes/demo/out.png`. If this fails, the toolchain is broken — fix it before touching any game.
Copy `examples/linux-passthrough-minimal` as your starting point; it extends this demo with a scripted
host camera and a director op.

## 2. Write the contract
```bash
hw bridge new-contract --host "<host>" --guest "<guest>" --out docs/CONTRACT.md
```
Fill in the mapping section **after measuring** (step 4). `hw bridge check docs/CONTRACT.md` gates every
milestone. Units: metres; yaw 0 = +Z clockwise from above, pitch + = up. Contract rules that save projects:
drop frames (never queue more than 3), retry events 3x, both sides reconnect forever, watchdog pauses the
guest layer when the other side goes quiet.

## 3. Minimal mods on both sides (copy from adapters/)
- Host mod: every frame send `cam {pos, yaw, pitch, fov}`; send `ground {cols}` for columns near the player
  (<= 200/frame); listen for `event` and act it out (explosion, projectile, damage). Needs only the host's
  scripting API — see `adapters/` for Python/Lua/C# starting points.
- Guest mod: receive `cam`, move its camera/entity to match; export colour+depth per frame (offscreen target
  when the engine allows it, else its own window captured with `hw capture shot`); send `event`s.
- Transport default: TCP JSON lines via the stdlib adapter (`adapters/python/bridge_client.py` — no `hw`
  install needed inside the game). File-drop dir when sockets are blocked. WebSocket only if both sides
  already speak it.

## 4. Measure the mapping (don't guess it)
Drive the host to 3+ known poses, record what the guest must render, fit: axis flips, yaw/pitch signs and
offsets, and the vertical offset that lands host feet on whole guest blocks. Put the numbers in the contract.
Re-measure after every engine or loader update. The classic failure is a sign error that looks "almost right".

## 5. Composite and display
```bash
hw composite compose --host host.png --host-depth host.npy --guest guest.png \\
    --guest-depth guest.npy --shift 6,-3 --overlay hud.png --out out.png
```
- Host depth: best from the host mod (raycast grid exported as `.npy`); fallback `--host-far` constant
  (guest always visible — fine for sky/arenas, wrong for interiors).
- `--shift dx,dy` hides one frame of latency for small rotations. Measure pose lag with a scene where one
  side draws something the other doesn't (gold wall vs skyline); if lag > 2 frames, fix the link, don't warp.
- Display: borderless always-on-top overlay window (SDL/pygame when available), or record with
  `hw capture record` and review. Keep the guest window unminimized — background windows render slowly.
- Latency budget: cam send (<2 ms localhost) + guest render (the big one) + export + composite (~5–15 ms at
  720p numpy) + display (1 vsync). If guest render dominates, drop guest resolution before optimizing code.

## 6. Slice order (each gated by its oracle)
1. Cube from A positioned in B (screenshot proves it).
2. Poses every frame while the host camera orbits (video: guest sticks to the world, no swimming).
3. Collision back-channel (guest entities rest on host ground).
4. Real content + events both ways (explosion in guest = explosion in host, on video).
5. Director ops (`cmd`) for repeatable takes, then showcase recording.

## Limits of the no-hook path (say these out loud)
- No per-pixel host depth unless the host mod exports it → interiors need the raycast-grid export.
- 2.5D shift, not full 6-DoF warp → keep end-to-end latency under ~100 ms.
- No host lighting on guest pixels (optional `--match-exposure` approximates the grade).
- If a game later needs scene-integrated lighting/shadows, that is a native-plugin milestone — scheduled
  after the no-hook slice works, never before.
