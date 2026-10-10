# Skyrim SE x Minecraft Fabric 26.3 (SkyCraft) on Linux — no ReShade, no Windows

One Steam click starts everything: Skyrim SE (Proton + SKSE) as the **host**,
the Modrinth **"Fabric 26.3"** profile as the **guest**, an `hw bridge` broker
between them, and an `hw composite` + `hw shade` overlay compositor on top.
This is the kit's Linux passthrough loop applied to SkyCraft
(`skills/linux-passthrough/SKILL.md`, contract in `docs/CONTRACT.md`).

## What runs where

```
Skyrim SE (+ SkyCraftBridge.psc shim: sends cam/ground, polls inbox) --\
                                                                        hw bridge (127.0.0.1:27431, JSON lines)
Modrinth "Fabric 26.3" (+ skycraft fabric jar when built) -------------/--> hw composite + hw shade --> overlay / video
```

- Host shim: `adapters/papyrus/SkyCraftBridge.psc` Trace()s
  `SkyCraftBridge cam ...` to `Papyrus.0.log`; `adapters/python/skycraft_host_daemon.py`
  tails it and publishes `cam`/`ground`/`state`.
- Guest: the real Modrinth profile when a human plays; `guest_stub.py` (one
  `explosion` event mid-run) when proving the loop headless.
- Compositing: `hw composite` depth-tests guest colour+depth vs host
  colour+depth on the CPU; `hw shade` grades the guest to the host's light
  (the ReShade replacement — no injector, no GPU hook).
- Launch: `bin/skycraft-autolaunch.sh` as the Steam Launch Options prefix, or
  `hw skyrim launch` standalone. Start with `--dry-run`.

## Run the headless prove-out (no games needed, < 60 s)

```bash
cd examples/skyrim-skycraft-linux
bash run_demo.sh
```

It gates the same five steps every real session must pass:

1. `hw bridge check docs/CONTRACT.md` — the mapping contract validates.
2. `hw bridge demo` — cam + event loopback round-trip.
3. `hw composite demo` — occlusion + alignment + overlay proof.
4. `hw shade demo` — grade proof (guest relit to host).
5. Live broker + synthetic host daemon + guest stub — the host inbox must
   contain the stub's `explosion` (back-channel proof), and the bridge log
   must validate message-by-message.

## Play it for real

```bash
hw skyrim status                        # one screen: game, skse, profile, proton
hw skyrim doctor                        # missing pieces + exact fixes
hw skyrim install-skycraft --source ~/Downloads/SkyCraft-0.1.2
hw skyrim build-fabric --source ~/Downloads/SkyCraft-0.1.2 --install
hw skyrim launch --dry-run              # read the plan
hw skyrim launch                        # bridge + Modrinth note + overlay + Steam
```

Steam auto-launch (every Play click): put this in Skyrim's Launch Options:

```
"/home/user/Downloads/AI game modding stuff/hot-wills-modkit/bin/skycraft-autolaunch.sh" %command%
```

## Mapping (measured-starting-fit, re-measure per engine update)

Metres on the bridge; `mc.x = sky.x/70, mc.y = sky.z/70, mc.z = -sky.y/70`;
`yaw = (180 - yaw_sky) mod 360`, `pitch = -pitch_sky`. Skyrim FOV ~75.
See `docs/CONTRACT.md`. The classic failure is a yaw sign error that looks
"almost right" — orbit the camera (synthetic daemon does this) and watch the
guest stick to the world before blaming latency.

## Honest limits (say these out loud)

- The primary flow is the real SKSE DLL under Proton 9.0 (verified: loads,
  hooks, Prism auto-start, world renderer). The hw-bridge fallback below is
  for DLL-less setups only — with the DLL working, skip it.
- Prism needs one interactive Microsoft sign-in + MC/Java download on first
  boot (Alt-Tab when it appears). After that it's automatic.
- The native-Linux Modrinth path runs the patched jar detached (no shm across
  the Proton boundary) — pixels-over-Skyrim there is Phase 2.
- No per-pixel host depth unless the host mod exports it → interiors need the
  raycast-grid export (`ground` columns are the v1 stand-in).
- Overlay is 2.5D, not scene-integrated lighting/shadows — `hw shade grade`
  approximates the grade per frame.
