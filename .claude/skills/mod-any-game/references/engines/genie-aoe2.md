# Genie / AoE2 playbook

- **Detect:** `*.dat` (Genie data), `resources/_common/slp` + `*.sld` sprites, `AI/` scripts, scenario `.aoe2scenario`.
- **Routes:** data edits via genieutils-py (units, civs, techs) → SLD/SLP sprite pipeline (`hw asset` for
  frames, engine-exact camera presets when rendering from 3D) → AI scripts (`.per`) → scenario triggers for
  scripted takes.
- **Read the truth:** the exe enforces UI tables the data doesn't (civ picker lists a hard-coded table —
  replace a slot, don't append); test every data edit in game.
- **Linux:** AoE2:DE runs under Proton; data/sprite/scenario mods are file drops (Proton-safe); the SLD writer
  and `hw asset` run natively on Linux.
- **Pitfalls:** sprite direction frames must match the engine's heading count exactly; dataset CRCs/desyncs in
  multiplayer — data mods are for single-player or matched lobbies.
