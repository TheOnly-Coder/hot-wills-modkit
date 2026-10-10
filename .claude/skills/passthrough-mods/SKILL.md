---
name: passthrough-mods
description: Build cross-game mashups and total conversions — "Minecraft inside game X", "skateboarding in a shooter". Covers passthrough mods (two games running at once, exchanging state/rendering/collision), content ports, decomp-as-library, and headless guest sims. Picks the lightest pattern for the idea, on Windows or on Linux without ReShade. Use when the user wants to combine two games, bring content or mechanics from one game into another, or rebuild a guest runtime.
---

# Mashups: putting one game inside another

Most mashup attempts fail by drifting, not by lacking code. Work this page top to bottom before writing any
mashup code, and plan the oracles first.

## 0. What does the user want from the guest game?
Its real behaviour (physics, inventory, combat), or only its look / one mechanic? Ask if unclear. The answer
decides whether the guest has to run at all — and which pattern below is the lightest that delivers it.

## 1. Name the pattern, find the nearest prior project
- `hw kb search "<host> <guest>"` plus both engine names. Another agent's note on either game applies here.
- `knowledge/techniques/choosing-a-passthrough-route.md` sorts builds into routes with first-slice oracles.
- Write the chosen route and why into MODLOG.md, and tell the user what every player must own and install
  (which OS, which store) before building.

## Pattern 1: port the content (lightest)
Bring an enemy, weapon or block type into the host as **new host content** imitating the guest. No IPC, no
second game running. Works with any host that has a loader.
- Read the guest's behaviour from its source of truth (decompile or wiki's exact numbers), reimplement in the
  host's mod API.
- **Assets:** never copy guest files into the mod. Convert from the user's install at install time, or
  recreate lookalikes with `hw asset`.

## Pattern 2: passthrough (two games at once)
Host and guest run simultaneously and exchange state every frame; the guest's picture lands in the host's
frame and host collision/events flow back. This kit's home turf.
1. **Guest process** runs the sim and publishes state each tick (entities near the player, or a rendered
   colour+depth layer).
2. **Transport** is `hw bridge` protocol v1 on 127.0.0.1 (see the **bridge-api** skill): `cam`/`ground`/
   `input` host→guest, `event` guest→host, `cmd` for the director, `state` heartbeat. Start both sides with
   `hw bridge new-contract` and keep it in `docs/CONTRACT.md`.
3. **Host side** is a normal mod in the host's own API (Fabric/BepInEx/UE4SS/GDScript): it sends the camera
   and nearby ground, and acts out guest events (explosions, projectiles, damage). No memory patching needed
   for the first slice.
4. **Compositing:**
   - Windows with GPU-headroom games: a ReShade add-on or host-native objects (host lighting applies).
   - **Linux / anywhere without ReShade: `hw composite`** — CPU depth-test of guest colour+depth against
     host colour+depth, overlay drawn last. See the **linux-passthrough** skill. Honest trade: one frame of
     latency and no per-pixel host depth unless the host mod exports it; keep latency low instead of warping
     hard.
5. **Back-channel:** host collision near the player (raycasts or exported mesh) becomes guest colliders.
   Input routes to one process at a time.
6. **Sync:** timestamps on every message, tolerance for two frame rates, watchdog when one side dies (spec it
   in the contract: no `cam` for 2 s → guest pauses; no `state` for 5 s → host hides the guest layer).
7. **Start small:** a cube from process A positioned in B. Then poses every frame, then collision, then real
   content. Prove each with `hw bridge demo`-style loopback tests before involving the real games
   (`examples/linux-passthrough-minimal` is the template).

## Pattern 3: embed a decomp as a library
Wrap a decomp/recomp (libsm64-style) as a library: feed it collision + input, take back state + mesh. The user
supplies their own ROM/assets. Best when the guest is retro and the host wants its *behaviour*, not its
window.

## Pattern 4: reimplement the guest's rules headless, keep the host as the view
Rewrite the guest's *rules* as a pure sim (no host imports) at the guest's own step rate and units; mirror
only what the player touches as host entities; batch projectiles/particles/effects per tick; every UI button
is a command. Best for guests whose gameplay is numbers (tower defense, cards, turn-based) and for
online-capable guests you must never inject into. Oracles: headless engine bench first (seconds, no host),
then host-side benches.

## Guardrails
- Offline, single-player, or servers the user runs. Never network into official online services.
- Guest-side content comes from the user's own install. Publish code and converters, not assets
  (`hw publish check --game`).
- Online-capable guests (accounts, co-op, leaderboards) are read from files offline only: never launched,
  patched or hooked.
- Be honest about what was verified: a README, a design doc or a green loopback test is not a real two-game
  run. Say which oracle each claim rests on.
- Be honest that it was built with AI; credit the loaders and projects you built on.
