# Bridge contracts: ownership, units, lifecycle

- status: working
- agents: OpenCode (muse-spark)
- versions: hot-wills-modkit 0.1.0, bridge protocol v1 (Linux, headless)
- route: technique (contract template enforced by `hw bridge check`)
- verified: contract template + example contract pass `hw bridge check`, logged session validates via `--log`

Every passthrough mod keeps a `docs/CONTRACT.md` both repos can read (`hw bridge new-contract`, gated by
`hw bridge check`). The lines that prevent the classic failures:

- **Ownership:** who owns the player, and the exact event that hands control back (guest death/exit →
  `event kind=teleport`). Exactly one process owns the mouse at a time; name it.
- **Units:** metres in, metres out; write the axis map (`Host (x,y,z) -> guest (x, z+YOFF, -y)`) and the
  yaw/pitch signs *after measuring* (drive 3+ known poses, fit, write the numbers).
- **Rates:** `cam` every host frame; `ground` ≤ 200 columns/frame; `state` 1 Hz. Pose stamps ride with pixels.
- **Late/full:** drop frames (queue ≤ 3), retry events 3x. Latency lies; timestamps don't.
- **Lifecycle:** either side starts first; both reconnect forever; `bye` on clean exit. Watchdog: no `cam`
  for 2 s → guest pauses entities; no `state` for 5 s → host hides the guest layer.
- **Protocol pin:** contract `proto:` matches message `v:`; `hw bridge check --log` fails mismatches, which
  is how desyncs get diagnosed after the fact (log everything in production with `serve --log`).
