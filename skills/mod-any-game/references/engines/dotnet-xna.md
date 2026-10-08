# .NET / XNA / MonoGame / FNA playbook (Terraria, Stardew, Celeste...)

- **Detect:** managed PE modules, `MonoGame`/`FNA`/`XNA` strings, content `*.xnb`.
- **Routes:** the game's loader is almost always the answer — tModLoader (Terraria), SMAPI (Stardew), Everest
  (Celeste), BepInEx (Unity-adjacent ones) → Harmony prefix/postfix/transpiler for what the API lacks → content
  packs (XNB) for data-only ideas.
- **Read the truth:** `ilspycmd` on the game's assemblies; loader wikis document the patch points; game logs
  (`client.log`, SMAPI console) are the oracle.
- **Linux:** tModLoader/SMAPI/Everest all run natively on Linux — this family is the friendliest Linux target.
  Keep saves in the lab profile (`-tmlsavedirectory` etc.).
- **Pitfalls:** loader version must match the game version (check both releases); transpilers break on game
  updates — prefer prefix/postfix; XNB content needs the matching importer version.
