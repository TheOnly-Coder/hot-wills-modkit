# hot-wills-modkit

An agent-native game-modding toolkit, passthrough-first and Linux-first: Claude Code, Codex, Cursor, Gemini
CLI, GitHub Copilot, OpenCode and anything else that reads `AGENTS.md`. When someone opens an agent in this
repo, they almost always want to **mod a game** — any mod, with a focus on **passthrough mods** (two games at
once) that also run on **Linux without ReShade**.

## Start here
1. **Read `skills/mod-any-game/SKILL.md` and follow its loop:** intake → recon → route → lab (backups) →
   source of truth → vertical slice → assets → verify in the real game → publish.
2. **Passthrough idea?** Read `skills/passthrough-mods/SKILL.md` first, then `skills/linux-passthrough/SKILL.md`
   on Linux (no ReShade: `hw bridge` + `hw composite` instead of GPU hooks).
3. **Search the knowledge base first:** `bin/hw kb search "<game or engine>"` (`knowledge/INDEX.md`).
4. **At the end, share what you learned:** write a field note (`bin/hw kb new ...`) and, once your human
   agrees, open a PR (`bin/hw kb pr <note> --yes`). See `knowledge/README.md` and `CONTRIBUTING.md`.

## Tools
- **`bin/hw`** is the Python CLI (Pillow + numpy + PyYAML only; `uv` sets it up).
  - Put it on PATH: `export PATH="$PWD/bin:$PATH"`.
  - Every group has `--help`:
    - `scan`: installed games, engine, anti-cheat, routes (Linux/Windows/macOS)
    - `bridge`: passthrough protocol v1 — contract, relay broker, loopback demo
    - `composite`: ReShade-free depth-tested guest-over-host compositing (CPU, Linux OK)
    - `capture`: Linux-first screenshots, window list, recording
    - `asset`: offline art pipeline (cutout, fit, pixelate, palette, sheets)
    - `backup`: snapshot and restore saves
    - `publish`: pre-release lint
    - `kb`: the knowledge base
- **No MCP server, no API key.** Everything runs locally and offline; that is the point. (Agents that got
  assets from universal-modder's fal MCP can still use it there — this kit's pipeline is the offline half.)
- **Skills** (`skills/*/SKILL.md`, Agent Skills format) are copied where agents look for them in a clone:
  `.agents/skills` (Codex, Gemini CLI, Copilot, Cursor, OpenCode) and `.claude/skills` (Claude Code). Edit
  `skills/`, then copy it over; a test fails while the copies differ.
- **Adapters** (`adapters/`): copy-paste bridge clients (Python stdlib-only, Lua, C#) for host/guest mods.
- **Engine playbooks:** `skills/mod-any-game/references/engines/`.
- **Worked example:** `examples/linux-passthrough-minimal` (runs headless, no games needed).

## Rules (same spirit as the Hard rules in `skills/mod-any-game/SKILL.md`)
- **What you can mod:** any game the user owns: single-player, multiplayer, or servers the user hosts.
  - Never touch online clients protected by anti-cheat.
  - Never write cheats against other players (aimbots, ESP, speed hacks).
  - Never bypass anti-cheat, DRM or ownership checks.
- **Saves:** `hw backup` before modded launches.
- **What you ship:** never commit or publish game files, extracted assets or decompiled code. Keep
  decompiles outside the repo.
- **Processes:** kill by exact PID, never by name pattern.
- **Ask first** before:
  - driving the user's mouse and keyboard, and never focus a game with an online mode while they're typing;
  - installing loaders into game folders or changing the registry;
  - publishing anything, PRs included.
- **Keep a journal:** a `MODLOG.md` in the mod's working folder. It becomes your field note at the end.

## Working on the toolkit itself
- **Python:** 3.10+, deps Pillow, numpy, PyYAML (`uv` handles them via `bin/hw`). Code lives in `hw/`,
  one module per CLI group, each with `register(sub)` and a docstring that doubles as `--help`.
- **Tests:** `HW_NO_UV=1 python3 -m pytest -q tests` (or `uv run --with pytest pytest -q tests`).
  CI also runs `hw kb check --index`-equivalent and `hw publish check` on examples.
- **Wording:** keep skills and docs agent-neutral ("the agent", not a product name) except in sections
  about one specific agent.
