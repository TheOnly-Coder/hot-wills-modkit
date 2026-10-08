---
name: publish-mod
description: Package and release a mod safely: lint with hw publish check, write the README with install steps and credits, version, and share without game files or secrets. Use when the mod works and the user wants to share it, or as a pre-release gate.
---

# Publish a mod

## 1. Lint (gates everything)
```bash
hw publish check ./my-mod --game "<install dir>"
```
It blocks: game files / extracted assets (extension + install-overlap heuristics), decompiled-code dumps,
secrets (keys, tokens, private keys, dotenv), and missing README.md. Heuristics, not proof — read the diff
yourself too. Fix failures; never `--force` around them (there is no flag, on purpose).

## 2. Package per platform
- Ship: your code, your assets (or the fitted sheets), converters that run on the user's own install, and
  `docs/CONTRACT.md` for passthrough mods (plus which OS/store each side needs).
- Never ship: game files, extracted assets, ROMs/ISOs, decompiled code, third-party SDKs (link + fetch
  script instead), `.env`, keys.
- Name the exact supported versions (game build, loader version, `hw` version). Pin downloads (loader DLLs,
  SDK headers) by version + hash; document load order and exact uninstall (which files to delete).

## 3. README (required — the check enforces it)
Install steps from zero, what every player must own and install (OS, store, loader), controls, how to
uninstall, credits (loaders, tools, asset sources), and an honest AI-built note: what was built with AI,
what was verified in the real game and what wasn't.

## 4. Release
Ask before publishing anything (posts and PRs included — a release carries the human's identity). Tag the
mod's own repo, attach the package, write the post from the README's first paragraph, and use the badge:

```markdown
[![made with hot-wills-modkit](docs/media/made-with.svg)](https://github.com/<you>/hot-wills-modkit)
```
Then write the field note (**share-field-notes**) — released or not, the note is the point.
