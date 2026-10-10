# Bethesda playbook (Morrowind → Starfield)

- **Detect:** `.esm`/`.esp`/`.esl`, `Data/` folder, `Papyrus` scripts, `SKSE`/`F4SE`/`SFSE` loader DLLs.
- **Routes:** plugin files (ESP/ESL via xEdit — check record-level conflicts) → script extender (SKSE family,
  match game build exactly) → asset replacers in `Data/` (loose files override BSAs, load order matters).
- **Read the truth:** xEdit (records, conflicts, what the exe enforces vs what data allows), Papyrus logs in
  `Documents/My Games/<game>/`.
- **Linux:** modlists run under Proton (Mod Organizer 2 in the prefix); prefer manual/`loadorder.txt`-style
  installs you can script. SKSE build must match the game build — mismatch = silent no-load.
- **Pitfalls:** the exe enforces limits the data doesn't (civ-picker-style hard tables exist here too: test in
  game, not in xEdit); save bloat from script-heavy mods — back up saves first, always.
