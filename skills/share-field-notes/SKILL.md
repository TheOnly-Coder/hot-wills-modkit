---
name: share-field-notes
description: Record what a modding session learned as a knowledge-base field note so the next agent starts ahead: exact versions, route and why, engine behaviour, verification, gotchas. Use at the end of every modding session, finished or not, and before starting when prior art might exist.
---

# Share field notes

The knowledge base (`knowledge/`) is notes by agents, for agents. A documented dead end saves the next agent
hours — write the note even when the mod failed.

## During the session
- Search first: `hw kb search "<game>"`, `hw kb search "<engine>"`. Start from exact versions, routes and
  gotchas; don't repeat dead ends.
- Keep `MODLOG.md` as the journal — it becomes the note at the end.

## Writing the note
```bash
hw kb new --game "<game>" --title "<what you built>" --agent "<agent (model)>"
# techniques (routes, compositing, contracts): --kind technique
```
Fill it in from MODLOG.md, for an agent that has never seen this game:
- exact versions (game build, loader, OS/Proton, `hw` version);
- the route, and why it beat the alternatives;
- what the engine really does (names, IDs, file formats, enforcement the data doesn't show);
- build steps someone can replay;
- **how you verified it, and what you didn't** (oracle per claim: screenshot, video, log, loopback test);
- numbered gotchas: symptom → cause → fix;
- `status:` honestly (`idea`, `in-progress`, `working`, `released`, `abandoned`).

```bash
hw kb check knowledge/games/<game>/<note>.md   # must pass (no dumps, no secrets, honest status)
hw kb index                                    # rebuild the index
```

## Opening the PR (human says OK first)
```bash
hw kb pr knowledge/games/<game>/<note>.md        # dry run: shows the commands
hw kb pr knowledge/games/<game>/<note>.md --yes  # branch, push, open with gh
```
Rules (PRs breaking these are closed): no game content or links to pirated copies; no decompiled dumps
(describe logic, name symbols, keep your own snippets short); no secrets; no cheats/bypasses/online-client
injection; honest status and verification; credit people and projects.
