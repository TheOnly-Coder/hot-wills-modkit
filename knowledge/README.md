# Knowledge base: field notes by agents, for agents

Every note is a real session: exact versions, the route and why, what the engine really does, how it was
verified, and numbered gotchas (symptom → cause → fix). Search before you mod (`hw kb search`), write after
you mod (`hw kb new`), even when it failed.

- `games/` — one folder per game, one note per build.
- `techniques/` — cross-game methods (routes, contracts, compositing).
- `TEMPLATE.md` — what a note must contain. `hw kb check` enforces it.
- `INDEX.md` — regenerated with `hw kb index` (CI checks it is fresh).

Contribution rules for humans and AIs: `CONTRIBUTING.md` at the repo root. The short version: no game files,
no decompiled dumps, no secrets, no cheats/bypasses, honest status and verification.
