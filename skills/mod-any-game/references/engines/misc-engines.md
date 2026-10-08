# Misc engines playbook (GameMaker, RPG Maker, Ren'Py, Paradox, Doom, HTML5, Love2D, Java)

- **GameMaker** (`data.win`): UndertaleModTool — rooms/sprites/scripts as data edits; test in game (runner
  enforces layout the data doesn't show).
- **RPG Maker MV/MZ** (`www/js/rpg_core.js`): plain `.js` plugins in `www/js/plugins` + `plugins.js` entry —
  the easiest code mods in existence; NW.js devtools inspect live.
- **Ren'Py** (`renpy/`): `.rpy` mod files in `game/`, no compilation; `config.developer` + console for live checks.
- **Paradox** (CK/EU/Stellaris): text scripts in `common/` + `events/`; `error.log` is the oracle; checksum vs
  cosmetic-only mods for hosted multiplayer.
- **Doom** (GZDoom): ZScript/DECORATE + PK3s; `logfile` + `vid_fps`; stays cross-platform by construction.
- **HTML5/JS games:** override fused JS or patch `www/` assets; browser devtools first.
- **Love2D** (`.love`/fused lua): unzip/repack or `main.lua` overrides; `love` binary version matters.
- **Java games:** Mixin-style bytecode patches or plugin APIs; match the exact game + loader versions.
- **Linux note:** this whole family is natively cross-platform — prefer it for first Linux mods and for
  headless guest sims in passthrough builds.
