"""`hw publish check`: lint a mod folder before sharing it.

Blocks the three classic mistakes:
  1. shipping game files / extracted assets (extension + size heuristics);
  2. shipping decompiled code dumps (long foreign blocks, known header markers);
  3. leaking secrets (API keys, tokens, private keys).

Heuristics, not proof: a clean check plus your own README review is the bar.
Exit code is nonzero on failure so agents can gate releases on it.

Examples:
  hw publish check ./my-mod --game ~/Games/SomeGame
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

GAME_EXTS = {".pak", ".utoc", ".ucas", ".bsa", ".ba2", ".esp", ".esm",
             ".wad", ".vpk", ".assets", ".ress", ".dat", ".sld", ".smx",
             ".rom", ".iso", ".nsp", ".xci", ".jar"}
GAME_NAMES = {"globalgamemanagers", "global-metadata.dat", "gameassembly.dll",
              "unityplayer.dll", "dinput8.dll", "scripthookv.dll"}
SECRET_RES = [
    (r"sk-[A-Za-z0-9]{20,}", "possible OpenAI-style key"),
    (r"ghp_[A-Za-z0-9]{20,}", "possible GitHub token"),
    (r"xox[bap]-", "possible Slack token"),
    (r"FAL_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{8,}", "possible fal key assignment"),
    (r"-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----", "private key material"),
    (r"AKIA[0-9A-Z]{16}", "possible AWS key id"),
]
DECOMP_MARKERS = ["// Decompiled with", "/* Decompiled with", "IL spy", "ILSpy",
                  "// Dumper-7", "Ghidra", "__int64 sub_"]


def check(moddir: str | Path, game_dir: str | Path | None = None) -> list[str]:
    errs: list[str] = []
    root = Path(moddir)
    if not root.exists():
        return [f"mod dir does not exist: {moddir}"]
    files = [p for p in root.rglob("*") if p.is_file() and ".git/" not in p.as_posix()]
    if not files:
        return ["mod dir is empty — nothing to publish"]
    for p in files:
        rel = p.as_posix()
        low = p.name.lower()
        if p.suffix.lower() in GAME_EXTS or low in GAME_NAMES:
            errs.append(f"game file must not ship: {rel}")
            continue
        if p.suffix.lower() in {".env"} or low == ".env":
            errs.append(f"dotenv must not ship: {rel}")
        try:
            if p.stat().st_size > 2_000_000:
                continue  # don't slurp giant binaries; extension check already ran
            text = p.read_text(errors="replace")
        except OSError:
            continue
        for rx, label in SECRET_RES:
            if re.search(rx, text):
                errs.append(f"{label} in {rel}")
        for m in DECOMP_MARKERS:
            if m in text:
                errs.append(f"looks like decompiled code ({m!r}) in {rel}")
                break
        long_blocks = [b for b in text.split("\n\n") if len(b.splitlines()) > 150]
        if long_blocks and p.suffix.lower() in {".cs", ".java", ".cpp", ".h"}:
            errs.append(f"{rel}: suspicious 150+ line block — keep pasted code short and yours")
    if game_dir:
        g = Path(game_dir)
        if g.exists():
            gnames = {p.name.lower() for p in g.rglob("*") if p.is_file()}
            for p in files:
                if p.name.lower() in gnames and p.suffix.lower() in GAME_EXTS:
                    if not any(p.name.lower() in e for e in errs):
                        errs.append(f"{p.as_posix()} matches a file inside the game install")
    if not (root / "README.md").exists() and not (root / "README").exists():
        errs.append("missing README.md (install steps, credits, AI-built honesty note)")
    return errs


def register(sub):
    p = sub.add_parser("publish", help="lint a mod folder before sharing")
    sp = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = sp.add_parser("check", help="lint a mod folder")
    q.add_argument("moddir")
    q.add_argument("--game", default=None, help="game install dir for overlap check")
    q.set_defaults(func=_run)
    p.set_defaults(func=lambda a: p.print_help())


def _run(a: argparse.Namespace):
    from hw.common import fail
    errs = check(a.moddir, a.game)
    if errs:
        fail("publish check FAILED:\n  - " + "\n  - ".join(errs))
    print("publish check OK")
