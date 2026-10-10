---
name: game-automation
description: Drive and observe games on Linux: screenshots, window listing, desktop recording, safe mouse/keyboard input, windowed-mode setup, crash-reporter cleanup. Use when launching a modded game, taking proof screenshots, recording takes, or scripting repeatable in-game tests.
---

# Game automation (Linux-first)

## Observe
```bash
hw capture backends        # what exists on this machine (grim/import/scrot/ffmpeg...)
hw capture shot --out takes/shot.png
hw capture windows --list  # swaymsg/wmctrl/xdotool backed
hw capture record --out takes/play.mkv --seconds 20 --size 1280x720 [--audio none]
```
- Read screenshots at reduced scale to save tokens; multiply coordinates back when clicking.
- Windowed mode at a known client size keeps screenshots and click coordinates stable (set it in the game's
  config/registry or launch flags before scripting).
- The game is the oracle: every claim needs a screenshot you actually looked at or a log line, never "it
  should work".

## Drive (safely)
- Prefer mod-side automation first: chat commands, timelines, scenario triggers (no focus stealing, no
  keystroke leaks). Only drive real input when the game has no scriptable path.
- Linux input tools: `xdotool` (X11: `search`, `windowactivate`, `mousemove`, `click`, `type`), `wtype`/
  `ydotool` (Wayland — needs the compositor's permission model). Check what the session runs before picking.
- Rules: ask before long automated sessions while the user is at the PC; never focus a game with an online
  mode while they're typing; kill by exact PID only; clear crash reporters (BugSplat etc.) by PID when the
  launcher refuses to relaunch.

## Repeatable takes
Script launch → menus → scene with a director (`cmd` ops over `hw bridge` where the game has a mod, shell
driving where it doesn't), record with `hw capture record` (game audio via the pulse monitor source, or
`--audio none` and add music later), keep takes with event logs. One working take beats ten flaky ones.

## Headless fallback
No display (CI, SSH)? The pipeline still tests: `hw bridge demo` (link), `hw composite demo` (compositing),
`examples/linux-passthrough-minimal` (whole loop against fakes). Gate merges on those; reserve real-game
takes for milestones.
