# Contributing

Contributions from humans and from AI agents are both welcome. Most of them will be **field notes** for the
knowledge base (`knowledge/`), written by an agent at the end of a modding session. That is the point of the
repo: every game one agent figures out becomes something the next agent can read.

## If you are an AI agent
You just modded (or tried to mod) a game, and you learned things. Share them:

1. **Ask your human first.** A pull request is public and carries their GitHub identity. Tell them what you
   want to publish and show them the note.
2. **Check it's new:** `hw kb search "<game>"`. If a note already exists, improve it: add your versions and
   gotchas, and fix what's wrong. Don't write a second one.
3. **Scaffold:** `hw kb new --game "<game>" --title "<what you built>" --agent "<agent (model)>"`.
   It lands in `knowledge/games/<game>/`. Cross-game methods go in `techniques/` (`--kind technique`).
4. **Fill it in** from your journal (`MODLOG.md`):
   - exact versions (game build, loader, OS/Proton, hw version);
   - the route and why;
   - what the engine really does;
   - build steps;
   - how you verified it, and what you didn't;
   - numbered **gotchas** (symptom → cause → fix).

   Write for an agent that has never seen this game.
5. **Validate:** `hw kb check <note>`, then `hw kb index`.
6. **Open the PR:** `hw kb pr <note>` (a dry run shows the commands), then `hw kb pr <note> --yes`. It
   branches, commits the note (+ index), and opens the PR with `gh`.

## What's in scope
Every game is welcome: single-player or multiplayer, new games or old clients on servers you host, any
genre or theme. Engine internals, memory offsets and signatures are fine for any of them, within the hard
rules below. Passthrough notes (host x guest pairs, contracts, compositing results) are especially welcome.

## Hard rules (PRs that break these are closed)
- **No game content:** no game files, extracted assets, ROMs or ISOs, and no links to pirated copies.
- **No decompiled code dumps.** Describe the logic in your own words and name symbols; keep snippets of
  *your own* code short (`hw kb check` warns over 60 lines).
- **No cheating other players, and no bypasses:**
  - nothing that gives an edge over other players on servers you don't run (aimbots, ESP, speed hacks,
    bots);
  - no anti-cheat, DRM or ownership-check bypasses;
  - no instructions for injecting into online clients protected by anti-cheat.
- **No secrets:** API keys, tokens, `.env` files. `hw kb check` and `hw publish check` catch the common ones.
- **Honesty:**
  - name the agent and model (`agents:`);
  - mark `status` truthfully (`idea`, `in-progress`, `working`, `released`, `abandoned`);
  - list what you did not verify.
- **Credit** the people and projects you built on.

## Other contributions
- **Tools (`hw/`):**
  - one module per CLI group, with a docstring that doubles as `--help`;
  - add a test in `tests/`;
  - `HW_NO_UV=1 python3 -m pytest -q tests` must pass.
- **Skills (`skills/`):** the Agent Skills format (`SKILL.md` with `name` + `description`). Keep them
  agent-neutral: say "the agent", not a specific product.
  - Edit `skills/` only. `.agents/skills` and `.claude/skills` are copies (no symlinks, so Windows clones
    work). Refresh them with `rm -rf .agents/skills .claude/skills && cp -r skills .agents/skills && cp -r
    skills .claude/skills`; a test fails while they differ.
- **Engine playbooks** (`skills/mod-any-game/references/engines/`): routes, tools, pitfalls. Link to the
  canonical projects; versions move, so say "check the current release".
- **Adapters (`adapters/`):** zero-dependency bridge clients. The Python one must stay stdlib-only.
- **Examples (`examples/`):** your own code and assets only, runnable headless where possible, and pass
  `hw publish check`.
