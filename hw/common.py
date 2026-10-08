"""Shared helpers for the `hw` CLI groups."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def eprint(*a):
    print(*a, file=sys.stderr)


def load_json(path: str | Path):
    with open(path) as f:
        return json.load(f)


def save_json(path: str | Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def load_jsonl(path: str | Path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def repo_root() -> Path:
    """Best-effort repo root: the hot-wills-modkit checkout containing knowledge/."""
    here = Path(__file__).resolve().parent
    for cand in [here.parent, Path.cwd(), *Path.cwd().parents]:
        if (cand / "knowledge" / "INDEX.md").exists() or (cand / "skills" / "mod-any-game").exists():
            return cand
    return Path.cwd()


def fail(msg: str, code: int = 1):
    eprint(f"hw: error: {msg}")
    raise SystemExit(code)


def getenv(name: str, default: str = "") -> str:
    return os.environ.get(name, default)
