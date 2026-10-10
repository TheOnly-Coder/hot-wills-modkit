# MODLOG — Skyrim SE x Fabric 26.3 (SkyCraft) on Linux

Agent journal. Becomes the field note at the end
(`knowledge/games/skyrim-se/skycraft-linux-passthrough.md`).

## 2026-10-09 — auto-launch + toolkit improvements (OpenCode/muse-spark)

- Recon: Steam appid 489830, SKSE 1.7.104 loader+dll, Address Library
  versionlib-1-7-104-0.bin x14, Proton 11.0-100 prefix, Modrinth "Fabric 26.3"
  (fabric-api 0.161.0+26.3 enabled, Java 25.0.2), no SkyCraft files yet.
- Key finding: SkyCraft `SkyLink.java` speaks Win32 `OpenFileMappingW` via FFM
  and the SKSE half needs an MSVC build — no shared-memory sync on Linux.
  Decision: Linux transport is `hw bridge` TCP v1; deep Havok/actor/GPU sync
  is Phase 2 (documented, never claimed).
- Added `hw proton` (prefix/run/doctor), `hw skyrim`
  (status/doctor/install-skycraft/build-fabric/launch), `hw shade` (CPU
  ReShade replacement: postFX chain + guest-to-host grade).
- Added `bin/skycraft-autolaunch.sh` (Steam Launch Options prefix, execs
  `%command%`) + `bin/skycraft-modrinth.sh`.
- Added `adapters/papyrus/SkyCraftBridge.psc` (Trace cam to Papyrus.0.log) +
  `adapters/python/skycraft_host_daemon.py` (stdlib-only tail -> bridge).
- Added `examples/skyrim-skycraft-linux` (CONTRACT, guest_stub, run_demo.sh).
- Added `skills/skyrim-linux/SKILL.md` (synced to .agents + .claude).
- Installed into Steam: Data/SKSE/Plugins/SkyCraft.ini + Data/Scripts psc
  (saves backed up as skyrim-skse-before-skycraft).
- Verified: 38/38 pytest, bridge/composite/shade demos, run_demo.sh ALL GREEN
  (252 broker msgs, explosion back-channel in inbox, log re-validates).
- Gradle build of skycraft-fabric jar kicked off in background
  (/tmp/opencode/skycraft-build.log); install with
  `hw skyrim build-fabric --source ~/Downloads/SkyCraft-0.1.2 --install`.
- Pre-existing drift fixed: skills/publish-mod/SKILL.md badge URL synced to copies.
- NOT verified: real two-game run (needs human Play click + screenshots),
  .psc Creation Kit compile, SKSE load in prefix.

## 2026-10-09 night — real DLL flow working (OpenCode/muse-spark)

- User reported vanilla Skyrim (no Steve) + SKSE Load dialog for SkyCraft.dll.
- Downloaded the 0.1.2 RELEASE mod zip (prebuilt DLL 4MB + Prism bundle 24MB),
  installed to Data/ (release ini kept; Linux ini saved as .linux-bridge-backup).
- Root-caused the Load dialog: Proton Experimental breaks it (identical on
  0.1.0 and 0.1.2; imports/d3dcompiler/msvcrt/versionlib all present, game
  1.7.104.0 confirmed). Under Proton 9.0: `loaded correctly`, branch-pool
  alloc ok, all hooks (camera/hit/combat/input/overlay/blocks/shadows/paths/
  NPC collision), 191MB shm created, Prism `--launch SkyCraft` started.
- Fixed bundle unpack (Wine has no tar.exe): Linux-pre-unpacked to prefix
  LOCALAPPDATA/SkyCraft + forged bundle.stamp (MSVC file_time math) — accepted.
- Fixed world shader E5032: native d3dcompiler_47 (winetricks cache) into
  system32+syswow64 + native,builtin override → `world renderer ready`.
- Fixed the user's MC crash (Bad layout path GetLastError): SkyLink lazy
  Win32 init + detached standby; rebuilt jar, installed to Modrinth profile,
  verified via loom runClient (`running detached`, reaches resource loading).
- Wrapper is now SKSE-first (Proton 9.0 pinned); `hw proton` gained compat
  mapping lookup + build picker; doctor demands Proton 9.0 for Skyrim.
- 41/41 pytest. Test instances killed by exact PID; machine left clean.
- STILL NEEDS THE HUMAN: (1) Steam compat → Proton 9.0, (2) paste Launch
  Options wrapper, (3) Play → Prism Microsoft sign-in once → MC/Java download,
  (4) load post-Helgen save → Steve + hotbar + blocks.

## 2026-10-09 evening — it lives, now perf (OpenCode/muse-spark)

- User in-game as Steve. perf: lines show 7-9 fps (115-151 ms/frame) with
  Skyrim's own parts ~6 ms total → ~140 ms/frame is Minecraft frame-fence wait
  on Intel HD 630 (two games, one iGPU) + RAM pressure (4-6 GB free for
  MC Xmx4G + Skyrim; Firefox ~2 GB is the hog — user's to close).
- Tuned Prism instance options (renderDistance 8→6 lower-only, sim 8→4,
  vsync off, maxFps 60, mipmap 1, entityDistance 0.5, particles minimal,
  fullscreen) + re-applied Skyrim Low + borderless 1080p (bisect had restored
  originals). skycraft-graphics.sh handles CRLF/LF, idempotent, tested.
- Stuck WASD: releases lost across frame hitches; O (MC menu) sends
  ReleaseAll which unsticks. Input path audited (Skyrim push → ring →
  InputBridge KEYS[] + keyPress 1/0/-1); exact drop point still open —
  expect it to fade as fps recovers; diagnose further only if it persists.

## 2026-10-09 night II — sound, auto-launch, Load-flake honesty (OpenCode/muse-spark)

- Audio: system PipeWire/Pulse healthy, MC OpenAL on PulseAudio Output ok,
  volumes sane (MC music 0 by design). Sink-inputs observed live during a boot
  (game + MC streams present). No mute/misroute found; sound report still open.
- Wrapper is now pure bash (no uv/python in the hot path), SKSE-first with
  per-boot save backup, persistent log, Proton default-first, and a retry loop:
  polls skse64.log for loaded/disabled (byte-offset aware, PID-scoped kills),
  SKYCRAFT_MAX_TRIES=3, then leaves the last dialog to the human.
- Load dialog root-caused as far as possible without MSVC: AV in
  MSVCP140!_Mtx_lock called from plugin init (objdump import resolution +
  Wine seh unwind), fixed-once by current VC++ runtime, still flaky across
  identical boots (~1/3). Proton 9.0-vs-Experimental turned out to be a
  red herring for Load (both load post-CRT-fix); Experimental is still
  REQUIRED because Java NetworkInterface fatally crashes under Wine 9.0
  (10-line repro, fails 9.0 / passes Experimental).
- New kit tool: `hw minidump show` (stdlib minidump decoder: exception +
  fault-thread stack + module resolution; stride/layout notes from a real
  Wine-written dump). 48/48 pytest.
- Honest status for the human: pressing Play usually needs the retry loop
  (dialog may flash 0-2 times, wrapper restarts itself); click No only if it
  gives up after 3 tries and send the SkyCraft.log + skse64.log lines.

## 2026-10-09 night III — "fix the mod": DLL deep-dive (OpenCode/muse-spark)

- User rightly demanded the mod itself be fixed, not the launch. Result: root
  cause narrowed to an AV in MSVCP140!_Mtx_lock called from plugin init
  (objdump import-thunk resolution + Wine seh unwind, same address every
  time), before any log write or ini read, caught by SKSE → dialog. Empty
  SkyCraft.log + untouched ini + no exception in traces all fit.
- Ruled out: imports, versions, config content (incl. bStartWithSkyrim=0),
  versiondb (SKSE's own gate, separate message), Proton version (both fail),
  ASLR, wineserver staleness, concurrent instances (verified clean singles).
- Rebuild paths all dead-ends here: MSVC-only CommonLib (Clang+MinGW ABI
  mismatch on SKSE's C++ interfaces), binary patch too risky to ship.
- Delivered instead: wrapper retry loop (tested fail-fail-load with fakes),
  `hw minidump show` decoder, UPSTREAM-ISSUE.md with full evidence for the
  author (only they can fix in minutes). Kit tests 48/48.
