# Source 1/2 playbook

- **Detect:** `gameinfo.txt`/`gameinfo.gi`, VPKs, `bin/` server/client DLLs, `maps/*.bsp`.
- **Routes:** Source 1: MetaMod:Source + SourceMod plugins (check game support table), VPK overrides, Hammer
  maps; Source 2: addons in `game/<mod>/` (maps, materials, `vscripts` Lua), panorama UI overrides.
- **Read the truth:** `GCFScape`/`vpk` listing, `bspsrc` decompile (for learning layout — ship your own map),
  in-game `developer 1` + `con_log`.
- **Linux:** Source 1 dedicated servers and many clients are native; SourceMod builds are per-OS — match them.
- **Pitfalls:** signed VPKs / pure-server checks on some servers — stay on servers you host; Source 2 addon
  limits per game (check the workshop tools status for that title).
