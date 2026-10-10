# Retro decomp playbook

- **Detect:** N64/PSX-era binaries, community decomp repos (`*_decomp`), `*.z64`/ROM-adjacent tooling, recomp
  projects (N64Recomp, XenonRecomp).
- **Routes:** decomp-as-library (libsm64-style: feed collision+input, take state+mesh — the cleanest mashup
  primitive) → recomp static ports (ship engine, user supplies ROM/assets) → full rewrites that read the
  user's files (IW4L-style, with an evidence journal per milestone).
- **Read the truth:** the decomp itself + its matching-ROM hash checks; IDA/Ghidra only where no decomp exists.
- **Linux:** ideal — decomps/recomps are native C/C++ with CMake builds; CI-friendly oracles.
- **Pitfalls:** assets stay user-supplied (never commit ROM content); matching hash required for asset
  extraction; publish checks must grep for retail offsets — `hw publish check` plus a project-specific pattern.
