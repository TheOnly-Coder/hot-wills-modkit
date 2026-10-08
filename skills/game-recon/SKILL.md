---
name: game-recon
description: Figure out how a specific installed game can be modded, before writing any mod code. Covers where it's installed, engine and version, managed vs native code, anti-cheat, loaders present, save folders, and the community route. Use when the user asks "can I mod <game>?", "what engine is <game>", "how do people mod <game>", or at the start of any modding task. Produces MODDING_PLAN.md.
---

# Game recon

Goal: in about five minutes, know what you're dealing with and which route to take. Write it down so every
later step can rely on it.

## 0. Has another agent been here?
`hw kb search "<game>"` (and the engine name). A field note can hand you working versions, the route, and the
gotchas before you touch anything. See the **share-field-notes** skill.

## 1. Find it and fingerprint it
```bash
hw scan --list                 # Steam installs (Linux, Windows, macOS)
hw scan "<name or folder>"     # engine, version, .NET?, anti-cheat, routes
hw scan "<game>" --json        # the same, machine-readable
```
`hw` lives at `bin/hw` in this repo (plugins put it on PATH).

`hw scan` reads files only. It sniffs PE headers, Unity/Godot headers, Unreal version strings, and maps the
result to a route plus the playbook to read: `skills/mod-any-game/references/engines/<engine>.md`.

Check these by hand — the scan can't see them:
- **Game not in a Steam library** (GOG, itch, standalone folder): pass the folder path.
- **Anti-cheat installed elsewhere:** kernel drivers and launcher-level protection don't live in the game
  folder. Search "<game> anti-cheat".
- **Online-only or live-service games:** treat as protected even if nothing was detected.
- **Proton/Wine installs:** scan the `compatdata/<appid>` prefix too; note the Proton version.

## 2. Research the living community (always; versions move)
1. "<game> modding" / "<game> mod loader" / "<game> modding wiki".
2. Nexus Mods (dependencies of top mods reveal the framework), Thunderstore, mod.io, Steam Workshop.
3. GitHub: "<game> mod", "<game> modding api", "<game> linux modding".
4. Recent posts for new frameworks — the loader might be days old.

Capture: loader name, repo, **current version and install steps**, supported game versions, a hello-world
example mod, and where logs go. On Linux also capture: native build vs Proton, and whether the loader's
installer needs Windows (many do — plan a manual install).

## 3. Decide
- **Can it be modded safely?** Anti-cheat, online parts, EULA/mod policy, ownership checks. If not: say so,
  and offer what's possible (official tools, offline modes, a different game with the same idea).
- **Route:** loader API > data/asset mod > managed patching > passthrough/mashup > native hooks.
  On Linux, prefer routes that avoid DLL injection; native hooks are a last resort.
- **Passthrough?** If the idea is "game X inside game Y", stop here and read **passthrough-mods**.

## 4. Write MODDING_PLAN.md
```markdown
# <Game> modding plan
- Install: <path> (<store> <appid>), version <x>, OS <linux native | Proton X.Y | windows>
- Engine: <engine + version>, code: managed .NET / IL2CPP / native, 64-bit
- Anti-cheat / online: <none | what + verdict>
- Saves: <path>   Config: <path>   Logs: <path>
- Community route: <loader vX.Y (repo)>, install: <steps>, example mod: <link>
- Chosen route for "<idea>": <route> because <reason>
- Lab plan: backup <folders> (hw backup), lab profile <how>, windowed <how>
- Unknowns to resolve first: <list>
```
Then continue with the mod-any-game loop.
