---
name: mod-any-game
description: Mod a PC game the user owns, taking an idea to working in the real game and recorded. Covers new items, weapons, enemies, units, mechanics, art, and cross-game passthrough mashups, on Windows and on Linux without ReShade. Use when the user wants to mod, extend, hack on, reverse engineer or mash up a game ("add a nuke to Terraria", "put Minecraft inside X", "can I mod this game on Linux?"). Covers recon, route choice, safe lab, vertical slice, local assets, in-game verification and field notes.
---

# Mod any game

You are the modder. The user names a game and an idea, and you take it all the way to working in the real
game. The toolkit is `hw` (this repo's `bin/hw`; plugins put it on PATH). No API key, no Windows-only tools,
no ReShade required — everything has a Linux path.

| Need | Command |
|---|---|
| What games are installed, what engine, anti-cheat, routes | `hw scan --list`, `hw scan "<game>"` |
| Passthrough link: contract, broker, loopback self-test | `hw bridge new-contract/check/serve/demo` |
| Composite a guest game over a host without ReShade | `hw composite demo`, `hw composite compose ...` |
| Screenshot / list windows / record on Linux | `hw capture shot/windows/record` |
| Cut out / fit / pixelate / pack sprites (offline) | `hw asset ...` |
| Snapshot saves before touching them; undo | `hw backup create/diff/restore` |
| Lint a mod before sharing | `hw publish check` |
| Search / write the shared knowledge base | `hw kb search/new/check` |

Companion skills: **game-recon**, **passthrough-mods**, **linux-passthrough**, **bridge-api**,
**game-automation**, **asset-pipeline**, **publish-mod**, **share-field-notes**.

## The loop

### 0. Intake (keep it short)
- Get the game, the OS and store, and the idea in one sentence. Agree what done means (usually: working in
  game, screenshot or clip as proof).
- Settle online vs offline up front. If the game is online/competitive with anti-cheat, don't mod the client
  (see Hard rules). Offer offline modes, private servers the user runs, or official tools.
- Start `MODLOG.md` in the working folder as the journal: paths, IDs, formats, class names, what failed and
  why, next step. Anything not in the journal is lost at the next context compaction.

### 1. Recon (the game-recon skill does this in depth)
- **Search the knowledge base first:** `hw kb search "<game>"` and `hw kb search "<engine>"`.
- Run `hw scan "<game>"`. It reports engine, managed vs native, anti-cheat found in-folder, and ranked
  routes. Read the playbook it points at: `skills/mod-any-game/references/engines/<engine>.md`.
- Research the living community: wiki modding page, Nexus / Thunderstore / mod.io / Workshop, GitHub, the
  loader's current release and install steps. Versions move — never install from memory.

### 2. Pick the cheapest route that reaches the idea

| Route | When | Examples |
|---|---|---|
| Data / assets only | the idea fits the game's data files | Bethesda ESP/ESL, Paradox scripts, JSON packs, pak overrides |
| Loader API | a loader exposes hooks for it | BepInEx, Fabric, UE4SS Lua, REFramework Lua, GDScript mod loader |
| Managed-code patching | .NET/Mono/IL2CPP/Java with no API for the idea | Harmony prefix/postfix, Mixin |
| Native hooks | C/C++ engine with no loader | proxy DLL + signatures (Windows-first; prefer other routes on Linux) |
| Passthrough / mashup | two games at once | the **passthrough-mods** skill (**linux-passthrough** on Linux) |
| Reimplement / decomp | total control, or retro consoles | decomps-as-libraries, headless guest sims |

Write the chosen route and the reason into MODLOG.md before building.

### 3. Lab setup (the safety net)
- Before the first modded launch: `hw backup create "<saves folder>" --name <game>-saves`.
- Use a separate lab profile/save when the loader allows it. Keep a pristine copy of test worlds.
- Use windowed mode at a known size so screenshots and click coordinates stay stable.
- Keep decompiles and extracted assets outside the repo. Never commit game files.

### 4. Read the source of truth
Read actual code and data instead of guessing: decompile (ILSpy/ilspycmd, Vineflower, Ghidra), dump data
(xEdit, FModel, UndertaleModTool), inspect live (UnityExplorer, UE4SS viewer, Cheat Engine). Record exact
names and IDs in MODLOG.md.

### 5. Vertical slice first
One item, unit or weapon all the way through with placeholder art. Prove it appears and works from the log
plus a screenshot you actually look at (`hw capture shot`, view it at reduced scale). Then widen. Commit each
working step in the mod's own git repo.

### 6. Assets (asset-pipeline skill, all local)
Study the game's own assets first: size, palette, outline, facing, frame layout. Then `hw asset cutout/fit`
into exactly what the engine loads. No network, no key — run it on the modding machine itself.

### 7. Verify in the real game (build an oracle)
The running game is the oracle; your reading of the code is not. Make the test repeatable: a mod-side chat
command, a scenario with triggers, or a test world. Drive it, screenshot it, read the logs.
**Circuit breaker:** the same failure 3 times → stop, write down what you know, change approach or ask.

### 8. Package and publish (the publish-mod skill)
`hw publish check <mod> --game "<install>"`. README with install steps, credits, honest AI-built note. Ship
no game files.

### 9. Leave a field note (the share-field-notes skill)
`hw kb new ...` from MODLOG.md, `hw kb check`, PR with your human's OK. Document dead ends too.

## Hard rules
- **Ownership.** Only mod games the user owns.
- **Online play.** Single-player/offline, or servers the user controls. Never touch online clients protected
  by anti-cheat; never write cheats for multiplayer; never bypass anti-cheat, DRM or ownership checks.
- **No redistribution.** No game files, extracted assets, ROMs, or decompiled dumps. Ship code, assets you
  made, or converters that run on the user's own install.
- **Back up first.** `hw backup` before changing saves, profiles or game folders.
- **Process hygiene.** Kill by exact PID, never by name pattern. Never block the game's main thread.
- **The user's machine.** Ask before driving input, installing loaders, changing settings, deleting anything,
  or publishing (PRs included).
