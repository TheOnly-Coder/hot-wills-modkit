# Choosing a passthrough route

- status: working
- agents: OpenCode (muse-spark)
- versions: hot-wills-modkit 0.1.0 (Linux, headless)
- route: technique (cross-game method selection)
- verified: applied to `examples/linux-passthrough-minimal` (route B slice oracles green, see field note)

"Passthrough" covers three different builds. Pick the lightest that delivers the idea.

| Route | What runs | Compositing | First slice + oracle |
|---|---|---|---|
| **A. State exchange only** | both games, no pixels cross | none (each game draws itself) | guest entity mirrors host position for 60 s (video, no swimming) |
| **B. Composited picture** | both games, guest colour+depth crosses | `hw composite` (Linux) or ReShade add-on (Windows) | guest checkerboard locked to host world while orbiting (screenshot pair) |
| **C. Host draws guest meshes** | guest exports meshes/atlas, host renders them | inside host pass (native plugin, host lighting) | one cube from guest at the right pose with host lighting (screenshot) |

A → B → C is the schedule: each route's slice is the next route's scaffolding. Most ideas ship on B.
Route C is a native-plugin milestone — scheduled after B works, never before.

Guests that are pure numbers (tower defense, cards, turn-based) skip all three: reimplement headless and
mirror entities (passthrough-mods Pattern 4). Guests you must never inject into (online-capable) are read
from files only.
