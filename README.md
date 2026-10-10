<img width="1440" height="720" alt="Gemini_Generated_Image_2be1ya2be1ya2be1" src="https://github.com/user-attachments/assets/25f35ff2-efae-4b99-b8f8-1b7d016a4cd9" />
# hot-wills-modkit

**Mod any game with any AI coding agent — passthrough-first, Linux-first, no ReShade, no API key.**

Point your agent at a game you own and say what you want: a new weapon, a new civilization, or one game
*inside* another. The agent recons the install, picks the cheapest route, builds against the real code,
verifies in the running game, and writes down what it learned for the next agent.

Passthrough mods (two games running at once, exchanging state/rendering/collision) are the focus — and on
Linux they work **without the Windows shading/injector stack**: both games talk over the kit's own bridge
protocol, and the guest is composited over the host on the CPU.

## Install

| Agent | Install |
|---|---|
| **Claude Code** | `/plugin marketplace add TheOnly-Code/hot-wills-modkit`<br>`/plugin install hot-wills-modkit@hot-wills-modkit` |
| **Codex** | `codex plugin marketplace add TheOnly-Coder/hot-wills-modkit`<br>`codex plugin add hot-wills-modkit@hot-wills-modkit` |
| **Gemini CLI** | `gemini extensions install https://github.com/TheOnly-Coder/hot-wills-modkit` |
| **VS Code / Copilot** | Enable `chat.plugins.enabled`, run **Chat: Install Plugin From Source**, enter this repo's URL |
| **Cursor** | Cursor Marketplace, or clone (Cursor reads `AGENTS.md`) |
| **OpenCode** | Clone and run `opencode` inside it (`opencode.json` points at `skills/`) |
| **Skills only** (any agent) | `npx skills add https://github.com/<you>/hot-wills-modkit` |
| **Anything else** | `git clone https://github.com/TheOnly-Coder/hot-wills-modkit` and start your agent inside it |

Inside a clone, each agent finds the skills where it looks for them: `.agents/skills` (Codex, Gemini CLI,
Copilot, Cursor, OpenCode) and `.claude/skills` (Claude Code) are copies of `skills/`. Instructions are in
`AGENTS.md`, which `CLAUDE.md` and `GEMINI.md` point to. `opencode.json` points OpenCode at `skills/`.
There is deliberately **no MCP server and no API key**: the whole kit runs locally and offline.

**The `hw` CLI.** Plugin installs and clones put it on PATH (it lives at `bin/hw`). Anywhere else, check
out the repo and `export PATH="$PWD/bin:$PATH"`. Needs Python 3.10+, Pillow, numpy, PyYAML (`uv` sets all
of that up automatically; without `uv`: `pip install pillow numpy pyyaml`).

## Try it
> Mod Terraria: add a homing missile launcher. Prove it in game with a screenshot.

> Make a new unit for a game I own on Linux, sprites generated locally with no API key.

> Put game X inside game Y on Linux, no ReShade. Start with the loopback demo, then the minimal example.

> What engine is `/path/to/MyGame`, and has anyone modded it before?

The agent runs the same loop every time: search the knowledge base → recon → route → safe lab (backups) →
read the real code → one working slice → assets → verify in the real game → package → field note.

## How passthrough works here (Linux, no ReShade)

```
host game (+ tiny mod: sends cam/ground, acts out events) --\
                                                             hw bridge (127.0.0.1:27431, JSON lines)
guest game (+ tiny mod: follows cam, sends colour+depth) ---/--> hw composite --> overlay / video
```

- `hw bridge new-contract/check/serve/demo` — protocol v1, relay broker, loopback self-test.
- `hw composite demo/compose` — CPU depth-test of guest colour+depth vs host colour+depth; overlay last.
- `examples/linux-passthrough-minimal` — the whole loop against two fake games (runs headless).
- `adapters/` — stdlib-only bridge clients (Python, Lua, C#) to copy into real mods.

## What's inside

**Skills** (`skills/`, Agent Skills format): `mod-any-game` (the loop + 12 engine playbooks),
`game-recon`, `passthrough-mods` (all mashup patterns), `linux-passthrough` (the no-ReShade build order),
`bridge-api` (protocol v1 reference), `game-automation` (Linux capture/input), `asset-pipeline` (offline
art), `publish-mod`, `share-field-notes`.

**The `hw` CLI** (Python, three deps): `scan`, `bridge`, `composite`, `capture`, `asset`, `backup`,
`publish`, `kb`. Every command has `--help` with examples.

**Knowledge base** (`knowledge/`): field notes by agents, for agents — versions, routes, verification,
gotchas. Every finished session adds one.

## Rules it follows
- Any game you own: single-player, multiplayer, or servers you host. Refuses online anti-cheat clients,
  cheats against other players, and DRM/anti-cheat/ownership bypasses.
- Never ships game files or decompiled code. Backs up saves first. Kills processes by PID only. Asks before
  driving input, installing loaders, or publishing.

## Made a mod with it?
Put the badge on your mod's page:

```markdown
[![made with hot-wills-modkit](https://raw.githubusercontent.com/TheOnly-Coder/hot-wills-modkit/main/docs/media/made-with.svg)](https://github.com/TheOnly-Coder/hot-wills-modkit)
```

## Credits
- Inspired by [universal-modder](https://github.com/rehan-remade/universal-modder)'s agent-skills + field-notes
  model; the bridge/composite path here is an original Linux-first design (no ReShade, no injection).
- Standing on the shoulders of every mod loader and community listed in the engine playbooks.

MIT licensed.
