"""hot-wills-modkit: agent-native game modding, passthrough-first and Linux-first.

Tools any AI coding agent (Claude Code, Codex, Cursor, Gemini CLI, Copilot, OpenCode, ...)
uses to mod games. No API key, no Windows-only dependency, no ReShade required.

Subcommands (see `hw --help`):
  scan       find installed games and fingerprint one: engine, runtime, anti-cheat, routes
  bridge     the passthrough link: protocol v1 messages, contract, broker, loopback demo
  composite  ReShade-free compositing: depth-tested guest-over-host on the CPU (Linux OK)
  capture    Linux-first screenshots and recording (x11grab/PipeWire fallbacks), window list
  asset      local art pipeline: cutout, fit, pixelate, palette, sheets (no network, no key)
  backup     snapshot and restore save folders before you touch them
  publish    lint a mod folder before sharing: game files, decompiled code, secrets
  kb         the knowledge base: search prior field notes, write your own, check it, open a PR
"""

__version__ = "0.1.0"
PROTO_VERSION = 1
DEFAULT_TCP_PORT = 27431
DEFAULT_WS_PORT = 27432
