# Unreal playbook (UE4/UE5)

- **Detect:** `Content/Paks/*.pak` (+`.utoc` = IOStore), `-Shipping.exe`, `++UE5+Release-x.y` version string.
- **Routes:** UE4SS Lua (live object/property access, check release vs game build) → Blueprint/pak overrides
  (repack with `repak`/`UnrealPak`, keep chunk IDs) → FModel dumps for the source of truth.
- **Read the truth:** FModel (mappings file per game build), UE4SS live viewer (`UE4SS.log`), `Player.log`-style
  game logs in the shipping log dir.
- **Linux:** UE4SS ships Win/Linux builds — match the game's build; Proton + UE4SS needs the Windows UE4SS in
  the prefix. Pak mods are OS-agnostic and the preferred Linux route.
- **Pitfalls:** mappings break every game update (re-dump); IOStore (`.utoc`) needs `ZenLoader`-era tooling —
  check current tools; cooking mods needs the exact engine version (check `ue-version` first).
