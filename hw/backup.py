"""`hw backup`: snapshot and restore save/config folders before modded launches.

Every modding loop starts here: one command before the first launch, restore path
written into MODLOG.md.

Examples:
  hw backup create ~/.config/MyGame --name mygame-saves
  hw backup diff ~/.config/MyGame --name mygame-saves
  hw backup restore ~/.config/MyGame --name mygame-saves
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

STORE = Path.home() / ".local" / "share" / "hot-wills-modkit" / "backups"


def _store(name: str) -> Path:
    p = STORE / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hash_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(folder: str | Path):
    """{relpath -> sha256} for all files under folder."""
    folder = Path(folder).expanduser()
    out = {}
    if not folder.exists():
        return out
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            try:
                out[str(p.relative_to(folder))] = _hash_file(p)
            except OSError:
                out[str(p.relative_to(folder))] = "<unreadable>"
    return out


def create(folder: str, name: str) -> Path:
    from hw.common import save_json
    folder_p = Path(folder).expanduser()
    dest = _store(name) / "files"
    if dest.exists():
        shutil.rmtree(dest)
    if folder_p.exists():
        shutil.copytree(folder_p, dest, symlinks=True)
    snap = snapshot(folder_p)
    save_json(_store(name) / "manifest.json", {"folder": str(folder_p), "files": snap})
    return _store(name)


def diff(folder: str, name: str) -> dict:
    from hw.common import load_json
    old = load_json(_store(name) / "manifest.json")["files"]
    new = snapshot(Path(folder).expanduser())
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "changed": sorted(k for k in set(old) & set(new) if old[k] != new[k]),
    }


def restore(folder: str, name: str) -> None:
    folder_p = Path(folder).expanduser()
    src = _store(name) / "files"
    from hw.common import fail
    if not src.exists():
        fail(f"no snapshot named {name!r} (see {STORE})")
    if folder_p.exists():
        shutil.rmtree(folder_p)
    shutil.copytree(src, folder_p, symlinks=True)


def register(sub):
    p = sub.add_parser("backup", help="snapshot, diff and restore save folders")
    sp = p.add_subparsers(dest="cmd", metavar="<cmd>")
    for cmd in ("create", "diff", "restore"):
        q = sp.add_parser(cmd, help=f"{cmd} a snapshot")
        q.add_argument("folder")
        q.add_argument("--name", required=True)
        q.set_defaults(func={"create": _r_create, "diff": _r_diff,
                             "restore": _r_restore}[cmd])
    p.set_defaults(func=lambda a: p.print_help())


def _r_create(a: argparse.Namespace):
    dest = create(a.folder, a.name)
    n = len(snapshot(a.folder))
    print(f"snapshot {a.name}: {n} files -> {dest}")


def _r_diff(a: argparse.Namespace):
    import json
    d = diff(a.folder, a.name)
    total = sum(len(v) for v in d.values())
    print(json.dumps(d, indent=2) if total else "(no changes since snapshot)")


def _r_restore(a: argparse.Namespace):
    restore(a.folder, a.name)
    print(f"restored {a.name} -> {a.folder}")
