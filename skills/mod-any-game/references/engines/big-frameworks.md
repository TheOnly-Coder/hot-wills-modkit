# Big frameworks playbook (RE Engine, FromSoft, GTA, Cyberpunk, BG3)

- **Detect:** `re_chunk_*.pak` (RE Engine), `Geometry`/`Event` + `dinput8` modloader culture (FromSoft),
  `ScriptHookV`/`dinput8.dll` (GTA V), `red4ext`/`CET` (Cyberpunk), `bin/` script extender (BG3).
- **Routes:** the community framework per game (REFramework Lua, ModEngine2, ScriptHookV ASI, RED4ext/Cyber
  Engine Tweaks Lua, BG3 Script Extender) → file replacers → native hooks last.
- **Read the truth:** framework logs + in-game consoles; mod wikis document natives/hashes per game build.
- **Linux:** GTA V / Cyberpunk / FromSoft titles run under Proton; ASI loaders and script hooks are
  Windows-first — for passthrough ideas on Linux, prefer the no-hook path (**linux-passthrough**): send
  camera/state from a script mod, composite with `hw composite`. Don't fight Proton injection until the
  no-hook slice works.
- **Pitfalls:** story/offline mode only where anti-cheat guards online (GTA Online, EAC titles) — BattlEye/EAC
  off means offline; script-hook builds lag game updates by days (pin versions, re-fetch per update).
