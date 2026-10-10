# Skyrim SE x Fabric 26.3 passthrough on Linux (SkyCraft auto-launch)

- game: Skyrim Special Edition (Steam appid 489830, Anniversary runtime)
- status: in-progress
- agents: OpenCode (muse-spark)
- versions: Skyrim SE Steam build 24914197 (game 1.7.104.0) + SKSE 2.3.1 loader/1_7_104 dll + Address Library incl. versionlib-1-7-104-0.bin, Steam default Proton (Experimental) + current VC++ runtime (vcrun2022) in the prefix, Modrinth App 0.21.6 profile "Fabric 26.3" (MC 26.3, fabric loader 0.19.5, Java 25), SkyCraft 0.1.2 release (prebuilt DLL + bundle), Ubuntu 24.04 + Intel HD 630, hw 0.1.0 + proton/skyrim/shade/minidump groups
- route: passthrough because two full games must run at once (MC physics/inventory inside Skyrim's world); primary flow is the real SKSE DLL + bundled Prism inside the default-Proton prefix (Windows shm works in-prefix), Linux bridge/composite/shade is the DLL-less fallback

## What was built

One Steam click starts the whole SkyCraft loop: `bin/skycraft-autolaunch.sh`
(Steam Launch Options prefix) backs up saves and runs Skyrim through SKSE
under Proton 9.0; the SKSE plugin starts its bundled Prism (Windows Java
in-prefix) by itself. `hw skyrim` owns status/doctor/install-skycraft/
build-fabric/launch (SKSE-first, legacy `--no-skse` bridge mode kept);
`hw proton` owns prefix/compat-mapping/run plumbing incl. per-game compat
lookup; `hw shade` is the CPU ReShade replacement. First-boot prefix fixes
are done: pre-unpacked Prism bundle + forged bundle.stamp (Wine ships no
tar.exe), native d3dcompiler_47 (Wine's compiler rejects the world shader
with E5032). The stock Fabric jar was also patched for native-Linux boot
(lazy Win32 in SkyLink) and verified loading detached. Host Papyrus shim +
stdlib daemon remain the DLL-less fallback.

## Build steps

1. Recon: `hw scan --list`, `hw skyrim status`, `hw skyrim doctor`.
2. Back up: `hw backup create .../Skyrim Special Edition/Saves --name ...`
   (launch does it again automatically).
3. Install the SkyCraft RELEASE mod zip (prebuilt DLL + bundle) into Data/
   (NOT the source zip). `hw skyrim install-skycraft` keeps the release ini
   when the DLL is present.
4. Force Proton 9.0 for Skyrim (Steam > Properties > Compatibility).
5. Pre-unpack the Prism bundle + write bundle.stamp (see skill step 5) OR let
   the first boot fail once, then do it — the log says exactly what failed.
6. Native d3dcompiler_47 into the prefix (system32+syswow64, native,builtin).
7. `hw skyrim build-fabric --source ~/Downloads/SkyCraft-0.1.2 --install`
   (native-Linux path only; needs the SkyLink Linux patch to boot).
8. Prove: `cd examples/skyrim-skycraft-linux && bash run_demo.sh`.
9. `hw skyrim launch --dry-run`, then Play. First boot: Prism wants the
   Microsoft sign-in once (Alt-Tab), downloads MC/Java, then hides.
10. Persist: Steam Launch Options = `"<kit>/bin/skycraft-autolaunch.sh" %command%`.

## How it was verified

- SKSE boot under Proton 9.0: `plugin SkyCraft.dll ... loaded correctly`,
  trampoline branch-pool alloc ok, hooks installed (camera/hit/combat/input/
  overlay/blocks/shadows/paths/NPC collision), `shared memory ... created`,
  `world renderer ready`, Prism process started with `--launch Skyrim... SkyCraft`.
- Same DLL under Experimental: identical modal Load failure on 0.1.0 and 0.1.2
  (objdump/imports/versionlib all check out — Proton-version issue, not files).
- Patched Fabric jar: loom runClient on Linux reaches resource loading with
  `no Win32 shared-memory link ... running detached` (stock jar crashes at
  SkyCraftClient:12 with GetLastError layout error — user's own crash log).
- `hw bridge demo` loopback, `hw composite demo` occlusion, `hw shade demo`
  grade, `run_demo.sh` ALL GREEN (explosion back-channel in inbox).
- 41/41 pytest incl. new proton-pick/compat, skyrim launch dry-runs, mapping math.
- NOT verified: Prism sign-in + MC download + in-game Steve view (needs the
  human: sign in once, load a post-Helgen save, screenshot). Papyrus .psc
  still uncompiled (not needed for the primary flow).

## Gotchas

1. `gradlew: Permission denied` → cause: zip loses exec bits → fix: `chmod +x fabric/gradlew`.
2. SKSE dialog naming SkyCraft.dll at startup → cause (verified): Proton
   Experimental breaks the plugin Load (identical on 0.1.0/0.1.2; imports,
   versionlib, turns all check out) → fix: force Proton 9.0 for the game.
3. `Minecraft: unpacking failed (tar exit code 1)` → cause: Wine ships no
   tar.exe → fix: Linux-unzip the bundle into prefix LOCALAPPDATA/SkyCraft +
   forge bundle.stamp `{size} {mtime-ns//100 + 116444736000000000}`.
4. `world shader PSMain failed: E5032` → cause: Wine d3dcompiler can't unroll
   the loop → fix: native d3dcompiler_47 in system32+syswow64, native,builtin.
   Result: `world renderer ready`.
5. MC crash `Bad layout path: cannot resolve 'GetLastError'` at
   SkyCraftClient:12 → cause: SkyLink resolves the Win32 capture layout in a
   field initializer → fix: lazy initWin32() + detached standby (verified:
   `running detached until Skyrim links up`, game reaches resource loading).
6. Modrinth App has no per-profile CLI → cause: flatpak app model → fix: launcher
   script opens the app + prints the one-click Play step; auto-launch never blocks on it.
7. `hw <new-group> --help` fails after adding a module → cause: forgot `hw/cli.py`
   GROUPS + `hw/__init__.py` doc → fix: register in both (test_cli_help_all_groups covers it).
8. Skill copies drift → cause: edited `skills/` but not `.agents/skills` +
   `.claude/skills` → fix: copy the new dir over; test_skill_copies_in_sync enforces it.
9. Argparse `default=func()` at import time → cause: name not yet defined →
   fix: compute defaults inside `main()` (hit in skycraft_host_daemon).
10. `install-skycraft` must not overwrite the release ini when SkyCraft.dll is
    present → fix: keep release ini (Windows paths), Linux ini only for the
    DLL-less fallback.
11. Never `pkill -f` game/wine processes (tool guard + blast radius) → fix:
    `pgrep` to identify, `kill <exact-PID>`; only your own test PIDs, never
    while the human plays.
