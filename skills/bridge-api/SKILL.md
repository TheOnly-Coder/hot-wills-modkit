---
name: bridge-api
description: Reference for the hw bridge protocol v1 that links two running games in a passthrough mod: message types, fields, validation, transports (TCP, WebSocket, file-drop), adapter templates, and broker tooling. Use when writing or debugging host/guest mod code, or when validating a CONTRACT.md or bridge log.
---

# Bridge API (protocol v1)

Own API, ASCII-debuggable. Default transport: newline-delimited JSON over TCP, 127.0.0.1 port 27431
(`hw bridge serve`). Same messages over WebSocket on port 27432 when `websockets` is installed, or as
`*.json` files in a shared drop dir for engines where sockets are blocked. Every message: `v: 1`,
`t: <type>`, `stamp` in ms.

## Messages

| `t` | dir | fields | notes |
|---|---|---|---|
| `hello` | either → broker | `game`, `role: host\|guest\|director\|observer` | handshake; both sides reconnect forever |
| `cam` | host → guest | `pos: [x,y,z]`, `yaw`, `pitch`, `fov?` | every host frame; metres; yaw 0=+Z clockwise from above, pitch +=up |
| `ground` | host → guest | `cols: [[x,z,y]...]`, `span?` | ≤ 200 columns/frame near the player |
| `input` | focus owner → other | `keys`, `mouse: [dx,dy]?`, `buttons?` | exactly one process owns the mouse |
| `event` | guest → host | `kind: explosion\|projectile\|damage\|pickup\|teleport\|custom`, `at?`, `power?`, `extra?` | retried 3x; host acts it out |
| `cmd` | director → either | `op`, `args?` | scripted takes: teleport, spawn, time, weather... |
| `state` | either → either | `players?`, `entities?` | 1 Hz heartbeat; drives the watchdog |
| `bye` | either → broker | — | clean exit |

Poses carry pixels: stamp every exported frame with the `cam.stamp` it rendered from so the compositor can
match them (`hw composite --shift` then hides one frame of lag).

## Tooling

```bash
hw bridge new-contract --host H --guest G --out docs/CONTRACT.md
hw bridge check docs/CONTRACT.md [--log bridge.jsonl]   # validates contract + every logged message
hw bridge serve --port 27431 --log bridge.jsonl --echo   # relay + log (directors watch with --echo)
hw bridge send --port 27431 '{"t":"cmd","op":"teleport","v":1,"stamp":0}'
hw bridge demo                                          # loopback self-test, no games
```

`hw.bridge.validate(msg)` returns a list of problems (empty = valid) — import it in tests: `hw bridge check
--log` runs the same validator over a recorded session, which is how desyncs get diagnosed after the fact.

## Adapter templates (`adapters/`)

- `adapters/python/bridge_client.py` — stdlib-only TCP JSONL client (connect, send, listen loop with
  reconnect). No `hw` install needed inside the game: copy the file into the mod. Works anywhere Python runs
  (Godot Python, Blender, headless sims, test fakes).
- `adapters/lua/host_ue4ss.lua` — host-side sketch for UE4SS/REFramework-style Lua: per-frame `cam` send,
  `ground` probe, `event` dispatch.
- `adapters/csharp/BepInExHost.cs` — host-side sketch for BepInEx: MonoBehaviour sending `cam`, background
  listener applying `event`s on the main thread.
- Guest sides mirror the host: receive `cam`, move camera, export frames, send `event`s. Java/Fabric guests
  follow the same shape (a `HostLink` WebSocket/TCP client + a frame exporter); see the worked minimal
  example's guest for the call order.

## Rules
- Validate before send in tests (`validate()`), log everything in production (`serve --log`), check the log
  after every session (`check --log`).
- Never queue more than 3 frames; drop, don't buffer. Latency lies; timestamps don't.
- The link listens on localhost with no token: any local program can send commands. Close games and broker
  when done; say so in the mod README.
- Protocol changes bump `v` and the contract's `proto:` line together; `check` fails mismatches.
