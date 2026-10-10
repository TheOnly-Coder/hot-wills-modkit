# Minecraft playbook (Java + Bedrock)

- **Detect:** `versions/*.jar`, `mods/` + `config/`, `logs/latest.log` (Java); `com.mojang` packs (Bedrock).
- **Routes:** Java: Fabric (Loader + API + Loom — pin all three to the MC version) or NeoForge/Forge → Mixin
  for what the API lacks → resource/data packs for assets-only ideas. Bedrock: behavior/resource packs.
- **Read the truth:** Mojang mappings (official) + Fabric intermediary; `logs/latest.log` +Mixin export; a dev
  client (`runClient`) with a throwaway game dir.
- **Linux:** first-class (native Java client, native servers); headless servers are the ideal **guest sim**
  host for passthrough builds (no window needed for logic tests).
- **Pitfalls:** every MC version needs its Loader/API/mappings triple — mismatch = crash at startup; rendering
  mixins (world colour/depth export for passthrough) must not block the render thread — copy to a staging
  buffer and hand off (see examples/linux-passthrough-minimal for the shape).
