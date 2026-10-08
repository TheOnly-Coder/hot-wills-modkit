@AGENTS.md

## Claude Code specifics
- Installed as a plugin, the skills are namespaced (`/hot-wills-modkit:mod-any-game`), and a SessionStart
  hook puts `hw` on PATH.
- In a clone, `.claude/settings.json` adds the same PATH hook, and `.claude/skills` is a copy of `skills/`.
- No MCP server is needed: everything runs through the `hw` CLI.
