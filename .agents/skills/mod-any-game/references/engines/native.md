# Native C/C++ playbook

- **Detect:** PE/ELF with no managed/Unity/Unreal fingerprints; PDB-adjacent strings, RTTI, `lua*`/`duktape`
  symbols hint at embedded scripting worth using instead of hooks.
- **Routes:** existing loader first (REFramework, UE4SS, SKSE/xSE, ASI loaders — check per game) → proxy DLL
  (`version`/`winmm`/`dinput8` + MinHook/SafetyHook, signature scans pinned per game build) → last resort only.
- **Read the truth:** Ghidra/IDA (IDA over MCP when available), Cheat Engine for live structures, RenderDoc for
  the render pass (find view-projection matrices for passthrough compositing).
- **Linux:** prefer LD_PRELOAD shims and mod-loader plugins over injection; Proton prefixes need the proxy DLL
  in the right folder *and* the right DLL-override mode. Native hooks are the last resort on Linux — re-read
  the route table and pick passthrough/data-mods first.
- **Pitfalls:** every game update breaks signatures (pin + re-scan); anti-cheat + hooks = instant refusal (see
  Hard rules); never block the render thread.
