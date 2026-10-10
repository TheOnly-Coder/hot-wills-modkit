---
name: skyrim-linux
description: Mod Skyrim Special Edition on Linux (Steam + Proton + SKSE) and run the SkyCraft passthrough with the Modrinth Fabric 26.3 profile. Covers install recon, SKSE/Address Library version matching, the Papyrus host shim, hw bridge link, CPU composite + shade overlay instead of ReShade, and the one-click Steam auto-launch. Use when the user plays Skyrim SE on Linux, wants SkyCraft auto-launch, or needs any Skyrim-SE-on-Proton mod verified in the running game.
---

# Skyrim SE on Linux (Steam + Proton + SKSE + SkyCraft)

Skyrim SE is appid **489830**, a Windows game running under Proton. The kit
treats it like any Bethesda game (`skills/mod-any-game/references/engines/bethesda.md`)
plus three Linux facts: the prefix owns the Windows filesystem view, SKSE must
match the game build exactly, and there is **no ReShade/GPU-hook path** — the
guest is composited outside both processes.

## 1. Recon first (2 minutes, read-only)

```bash
hw scan --list                                  # confirm Skyrim SE appid 489830
hw skyrim status                                # game, skse, skycraft, profile, proton, wrapper
hw skyrim doctor                                # missing pieces + exact fixes
hw kb search "skyrim"                           # prior field notes before you guess
```

What `status` tells you: `Data/SKSE/Plugins/versionlib-*.bin` (Address Library
coverage — want `1-7-104` for the current AE build), `skse64_loader.exe` next
to `SkyrimSE.exe`, `Data/SKSE/Plugins/SkyCraft.ini` (ours says
`hw skyrim install-skycraft` inside), the Modrinth profile dir
(`~/.var/app/com.modrinth.ModrinthApp/data/ModrinthApp/profiles/Fabric 26.3`:
`fabric-api` jar enabled, `skycraft-*.jar` when built, Java 25), and the
Proton prefix (`steamapps/compatdata/489830/pfx`).

## 2. Safety before launches

```bash
hw backup create "<prefix>/drive_c/users/steamuser/Documents/My Games/Skyrim Special Edition/Saves" \
  --name skyrim-saves-$(date +%Y%m%d)
```

`hw skyrim launch` does this automatically too. Never skip it: script-heavy
mods bloat saves, and passthrough testing teleports the player.

## 3. SkyCraft install order (each step gates the next)

1. **SKSE64** matching the game build (SKSE site) next to `SkyrimSE.exe`.
   Mismatch = silent no-load; `doctor` flags a missing loader.
2. **Address Library** All-in-one into `Data/SKSE/Plugins/`.
3. **Proton: use Steam's default (Experimental).** History of a wrong turn, kept
   so you don't repeat it: the DLL Load dialog appeared under Experimental, and
   three boots under 9.0 succeeded — looking like a Proton rule. It wasn't.
   The actual Load blocker was the prefix's 2016-era MSVCP140 (VS2026-built
   DLL calls `_Mtx_lock` on new-layout mutexes → null-deref → SKSE catches →
   dialog; verified by disassembly + Wine seh trace + fixing it with
   vc_redist.x64). And 9.0 has its own fatal flaw: Java's
   `NetworkInterface.getNetworkInterfaces()` hard-crashes the JVM there
   (reproduced with a 10-line test; works under Experimental). So: default
   Proton everywhere, current VC++ runtime in the prefix, and treat the Load
   dialog as flaky-under-Wine rather than version-mismatch (the wrapper
   retries failed boots automatically, up to `SKYCRAFT_MAX_TRIES`).
   Diagnosing a Load dialog: empty `SkyCraft.log` + `skse64.log` ending at the
   disabled line means Load died in init before any log write — decode it with
   `hw minidump show` on any `.dmp` next to the logs, or a `WINEDEBUG=seh`
   boot (an access violation inside MSVCP140 called from the plugin =
   CRT/Wine mismatch, not your files).
4. **The SkyCraft release mod** (`SkyCraft-<ver>.zip` from GitHub releases, the
   packaged mod — not the source zip): `SKSE/Plugins/SkyCraft.dll`,
   `SkyCraft.ini`, and the `SkyCraft/SkyCraft-Minecraft.zip` bundle go into
   `Data/`. `hw skyrim install-skycraft` keeps the release ini when the DLL is
   present (the plugin reads Windows paths; the Linux-bridge ini is only for
   the DLL-less fallback).
5. **First-boot fixes** (done once per prefix, then automatic):
   - Proton/Wine ships no `tar.exe`, so the plugin's bundle unpack fails
     (`unpacking failed (tar exit code 1)` in SkyCraft.log). Pre-unpack with
     Linux `unzip` into the prefix's `.../AppData/Local/SkyCraft`, copy
     `defaults/prismlauncher.cfg` to `Prism/prismlauncher.cfg` if missing, and
     write `bundle.stamp` as `{size} {mtime-100ns-ticks-since-1601}` of the
     Data bundle zip — the plugin then accepts it and starts Prism.
   - Wine's built-in d3dcompiler fails SkyCraft's world shader (`E5032 unable
     to unroll loop` → blocks never draw). Install native `d3dcompiler_47`
     (winetricks cache works) into prefix `system32`+`syswow64` with a
     `native,builtin` override → `world renderer ready`.
6. **Minecraft guest**: the plugin manages its own portable Prism in the prefix
   (first boot: sign into the Microsoft account in its window, Alt-Tab back;
   Prism downloads MC/Java once). The native-Linux path (Modrinth profile
   `Fabric 26.3` + `hw skyrim build-fabric --install`) is the fallback: note
   the stock Fabric jar crashes on Linux at startup (`SkyLink` resolves the
   Win32 `GetLastError` layout at class init) — the patched source defers all
   Win32 lookups and idles detached; rebuild + reinstall after patching.
7. **Contract**: `examples/skyrim-skycraft-linux/docs/CONTRACT.md` holds the
   mapping (`mc.x = sky.x/70`, yaw/pitch fit). Re-measure after every game,
   SKSE, or loader update — sign errors look "almost right".

## 4. Prove the loop headless before touching the games

```bash
cd examples/skyrim-skycraft-linux && bash run_demo.sh
```

Five gates: contract check, `hw bridge demo` loopback, `hw composite demo`
occlusion, `hw shade demo` grade, live broker with the synthetic host daemon
+ guest stub (the host inbox must contain the stub's `explosion`). If any gate
fails, fix the toolchain — not the games.

## 5. Launch (dry run first, always)

```bash
hw skyrim launch --dry-run     # SKSE mode: proton-9.0 skse64_loader.exe
hw skyrim launch               # for real: backup, SKSE, plugin starts Prism itself
```

Steam auto-launch (every Play click): Skyrim Properties > Launch Options:

```
"<kit>/bin/skycraft-autolaunch.sh" %command%
```

The wrapper runs the game through SKSE itself in SKSE mode (Steam tracks the
wrapper while it waits, `%command%` is superseded) and falls back to
backgrounding the Linux bridge services + exec in legacy mode
(`SKYCRAFT_USE_SKSE=0`). Env overrides: `SKYCRAFT_USE_SKSE`,
`SKYCRAFT_PROFILE`, `SKYCRAFT_PORT`, `SKYCRAFT_NO_MINECRAFT=1`,
`SKYCRAFT_NO_OVERLAY=1`.

First launch: Prism asks for the Microsoft sign-in once (Alt-Tab to it),
downloads Minecraft/Java, then runs hidden. SkyCraft.log
(`Documents/My Games/Skyrim Special Edition/SKSE/`) narrates every stage:
`loading`, `unpacking`, `started prismlauncher.exe`, `shared memory ... created`,
hooks, `world renderer ready`. If the SKSE dialog names SkyCraft.dll at
startup, the Proton is wrong (see step 3) — click Yes, fix, relaunch.

## 6. How the pieces fit (so you debug the right layer)

- **Primary flow (real DLL under Steam's default Proton)**: SKSE plugin creates the shared
  mapping, exports collision/actors, puppets the player, composites blocks +
  overlay itself, and auto-starts the bundled Prism (Windows Java in-prefix, so
  the stock Fabric jar's Win32 shared-memory code works unmodified).
- **Fallback flow (no DLL / native Linux)**: `SkyCraftBridge.psc` Trace()s
  `SkyCraftBridge cam ...` to `Papyrus.0.log`;
  `adapters/python/skycraft_host_daemon.py` tails it and publishes
  `cam`/`ground`/`state` (stdlib only — copy it anywhere). Only needed when
  the DLL path is unavailable; with the DLL working, skip it.
- **Guest**: the Modrinth profile follows `cam`; its colour+depth export is
  the Phase-2 Fabric bridge port (SkyCraft's `SkyLink` speaks Win32
  `OpenFileMappingW` today — no kernel32 on Linux, so v1 runs the profile +
  overlay and stubs the pixels; never claim shared-memory sync works here).
- **Composite**: `hw composite` depth-tests guest over host on the CPU;
  `hw shade` grades the guest to the host's light (the ReShade replacement).
- **Verify in the running game**: `hw capture shot` / `record`, window list
  to confirm both processes, bridge log (`takes/skycraft-bridge.jsonl`)
  validated with `hw bridge check CONTRACT --log`.

## 7. Limits to say out loud

- v1 = auto-launch + bridge + overlay. Havok collision export, actor proxies,
  and GPU interop are a native-plugin milestone after this loop works.
- Skyrim's Helgen opening is heavily scripted — test from a post-Helgen save
  (or Alternate Start), same as upstream SkyCraft advises.
- End every session with a field note (`hw kb new --game "Skyrim Special Edition" ...`).
