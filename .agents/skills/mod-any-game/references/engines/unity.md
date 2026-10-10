# Unity playbook (Mono + IL2CPP)

- **Detect:** `UnityPlayer` + `*_Data/Managed/Assembly-CSharp.dll` (Mono) or
  `GameAssembly` + `il2cpp_data/Metadata/global-metadata.dat` (IL2CPP). Version in `globalgamemanagers`.
- **Routes:** BepInEx (Mono: `BepInEx 5`, IL2CPP: `BepInEx 6` pre-release — check the current release, versions
  move) → Harmony patches; asset/data mods (`.assets` overrides, AssetBundles); UE-style pak thinking does not apply.
- **Read the truth:** `ilspycmd` on Managed DLLs; Cpp2IL + dummy DLLs for IL2CPP; UnityExplorer in-game inspector.
- **Linux:** Proton games take BepInEx via `WINEDLLOVERRIDES="winhttp.dll=n,b"` doorstop proxy; prefer native
  Linux builds when the game ships one. Doorstop config version must match the game build — mismatch = silent no-load.
- **Pitfalls:** Assembly-CSharp reloads don't exist — restart the game per iteration; IL2CPP method names need
  `Il2CppInspector`/`Cpp2IL` cross-reference, don't guess signatures; never block the main thread (no ffmpeg waits).
