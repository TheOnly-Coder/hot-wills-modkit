# Godot playbook

- **Detect:** `.pck` pack (`GDPC` magic), `project.godot` remnants, `libgodot`/`Godot` binary strings.
- **Routes:** GDScript mod loader (e.g. GodotModLoader / ModLoader — check what's current for the game's Godot
  version) → PCK overrides (unpack/repack with `godotpcktool`, keep UID/paths) → GDExtension native only when
  scripting can't reach the idea.
- **Read the truth:** unpack the PCK, read the `.gd`/`.tscn`/`.tres` sources directly — Godot ships readable
  scripts unless encrypted (then check the key situation; never bypass DRM, use official mod support instead).
- **Linux:** first-class — Godot games ship native Linux builds; mod loaders are usually drop-in folders.
- **Pitfalls:** PCK encryption keys differ per game build; script load order matters (mod loader autoloads);
  3.x vs 4.x GDScript syntax differs — match the game's version.
