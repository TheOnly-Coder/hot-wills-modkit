"""`hw scan`: find installed games and fingerprint an install (engine, runtime, anti-cheat, routes).

Read-only. Works on Linux, macOS and Windows; Steam/Proton paths are resolved per-OS.
Examples:
  hw scan --list
  hw scan "Stardew Valley"
  hw scan /path/to/game --json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
from pathlib import Path

MAX_FILES = 4000
MAX_BYTES_SNIFF = 1 << 20  # 1 MiB per file for version-string sniffing

# (key, engine label, playbook hint, route hint)
ROUTES = {
    "unity-mono": ("Unity (Mono/.NET)", "skills/mod-any-game/references/engines/unity.md",
                   "loader API (BepInEx) or Harmony patching"),
    "unity-il2cpp": ("Unity (IL2CPP, native)", "skills/mod-any-game/references/engines/unity.md",
                     "BepInEx IL2CPP build or asset/data modding"),
    "unreal": ("Unreal Engine", "skills/mod-any-game/references/engines/unreal.md",
               "UE4SS Lua or pak overrides"),
    "godot": ("Godot", "skills/mod-any-game/references/engines/godot.md",
              "GDScript mod loader (e.g. GodotModLoader) or PCK overrides"),
    "gamemaker": ("GameMaker", "skills/mod-any-game/references/engines/misc-engines.md",
                  "UndertaleModTool data modding"),
    "rpgmaker-mv": ("RPG Maker MV/MZ (HTML5/JS)", "skills/mod-any-game/references/engines/misc-engines.md",
                    "plugin .js files in www/js/plugins"),
    "renpy": ("Ren'Py (Python)", "skills/mod-any-game/references/engines/misc-engines.md",
              "rpy mod files, no compilation needed"),
    "dotnet": ("Managed .NET (XNA/MonoGame/FNA)", "skills/mod-any-game/references/engines/dotnet-xna.md",
               "Harmony patching or loader API (tModLoader/SMAPI style)"),
    "bethesda": ("Bethesda (Creation Engine)", "skills/mod-any-game/references/engines/bethesda.md",
                 "ESP/ESL plugins via xEdit, script extender, Data/ replacers"),
    "native": ("Native C/C++", "skills/mod-any-game/references/engines/native.md",
               "proxy DLL + signatures, or a loader (REFramework/UE4SS/SKSE family)"),
    "loved": ("Love2D (Lua)", "skills/mod-any-game/references/engines/misc-engines.md",
              "fused/unfused .lua overrides"),
}


class Index:
    """Bounded file listing of one install dir: {relpath posix -> size} plus root path."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.files: dict[str, int] = {}
        n = 0
        for dirpath, _dirs, filenames in os.walk(self.root):
            for fn in filenames:
                p = Path(dirpath) / fn
                try:
                    rel = p.relative_to(self.root).as_posix()
                except Exception:
                    continue
                try:
                    self.files[rel] = p.stat().st_size
                except OSError:
                    continue
                n += 1
                if n >= MAX_FILES:
                    return

    def has(self, *names: str) -> str | None:
        low = {k.lower(): k for k in self.files}
        for n in names:
            if n.lower() in low:
                return low[n.lower()]
        return None

    def glob(self, pattern: str):
        import fnmatch
        return [k for k in self.files if fnmatch.fnmatch(k.lower(), pattern.lower())]

    def read(self, rel: str, n: int = MAX_BYTES_SNIFF) -> bytes:
        try:
            with open(self.root / rel, "rb") as f:
                return f.read(n)
        except OSError:
            return b""


def pe_info(path: str | Path):
    """Minimal PE sniff: {'arch': x86|x64, 'managed': bool} or None if not a PE."""
    try:
        with open(path, "rb") as f:
            data = f.read(512)
    except OSError:
        return None
    if data[:2] != b"MZ":
        return None
    if len(data) < 0x84:
        return None
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if e_lfanew > len(data) - 6:
        # read further for real header
        try:
            with open(path, "rb") as f:
                f.seek(e_lfanew)
                data = f.read(512)
        except OSError:
            return None
        base = 0
    else:
        base = e_lfanew
    if data[base:base + 4] != b"PE\0\0":
        return None
    machine = struct.unpack_from("<H", data, base + 4)[0]
    arch = {0x14C: "x86", 0x8664: "x64", 0xAA64: "arm64"}.get(machine, f"machine:{machine:#x}")
    opt_off = base + 24
    magic = struct.unpack_from("<H", data, opt_off)[0]
    # data-directory index 14 = CLR header; offset differs PE32 (96) vs PE32+ (112)
    dd_off = opt_off + (96 if magic == 0x10B else 112) + 14 * 8
    managed = False
    if dd_off + 8 <= len(data):
        rva, size = struct.unpack_from("<II", data, dd_off)
        managed = bool(rva and size)
    return {"arch": arch, "managed": managed}


def _vdf(text: str):
    """Tiny VDF parser good enough for libraryfolders.vdf / appmanifest files."""
    toks = re.findall(r'"(?:[^"\\]|\\.)*"|\{|\}', text)
    stack: list[dict] = [{}]
    key: str | None = None
    i = 0
    for t in toks:
        if t == "{":
            d: dict = {}
            if key is not None and stack:
                stack[-1][key] = d
                key = None
            stack.append(d)
        elif t == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        else:
            s = t[1:-1]
            if key is None:
                key = s
            else:
                stack[-1][key] = s
                key = None
        i += 1
    return stack[0]


def _sniff_unity_version(idx: Index):
    for rel in idx.glob("*/globalgamemanagers") + idx.glob("globalgamemanagers"):
        blob = idx.read(rel, 200000)
        m = re.search(rb"\d{4}\.\d+\.[a-z0-9]+", blob)
        if m:
            return m.group(0).decode(errors="replace")
    return ""


def _sniff_unreal_version(idx: Index):
    for rel in idx.glob("*.exe")[:20]:
        blob = idx.read(rel)
        try:
            txt = blob.decode("utf-16-le", errors="ignore")
        except Exception:
            continue
        m = re.search(r"\+\+UE[45]\+Release-[\d.]+(?:-[\w]+)?", txt)
        if m:
            return m.group(0)
    return ""


def _sniff_godot_version(idx: Index):
    for rel in idx.files:
        if rel.lower().endswith(".pck") or rel.lower().endswith(".exe"):
            blob = idx.read(rel, 4096)
            if blob.startswith(b"GDPC"):
                try:
                    _pack_v, major, minor, patch = struct.unpack_from("<4I", blob, 4)
                    return f"{major}.{minor}.{patch}"
                except struct.error:
                    return "unknown (GDPC)"
    return ""


def _sniff_product(idx: Index):
    for rel in idx.glob("*/app.info") + idx.glob("app.info"):
        blob = idx.read(rel, 4096).decode(errors="replace")
        lines = [ln.strip() for ln in blob.splitlines() if ln.strip()]
        if len(lines) >= 2:
            return lines[1]
    return ""


ANTICHEAT_FILES = {
    "easyanticheat": "EasyAntiCheat",
    "beclient": "BattlEye",
    "vgk.sys": "Vanguard (kernel, lives outside game dir)",
    "ace-": "ACE",
    "eac_": "EasyAntiCheat",
}


def detect_anticheat(idx: Index) -> list[str]:
    found = []
    for rel in idx.files:
        base = rel.rsplit("/", 1)[-1].lower()
        for sig, label in ANTICHEAT_FILES.items():
            if base.startswith(sig) and label not in found:
                found.append(label)
    return found


def detect(idx: Index):
    """Return (hits, details). hits: list of (key, score, evidence, details-dict)."""
    hits: list[tuple] = []

    def add(key, score, evidence, details=None):
        hits.append((key, score, evidence, details or {}))

    unity_player = idx.has("UnityPlayer.dll", "UnityPlayer.so", "UnityPlayer.dylib")
    managed_dirs = idx.glob("*/Managed/Assembly-CSharp.dll") + idx.glob("Managed/Assembly-CSharp.dll")
    il2cpp_meta = idx.glob("*/il2cpp_data/Metadata/global-metadata.dat") + \
        idx.glob("il2cpp_data/Metadata/global-metadata.dat")
    game_assembly = idx.has("GameAssembly.dll", "GameAssembly.so")
    if unity_player and managed_dirs:
        ver = _sniff_unity_version(idx)
        add("unity-mono", 90, f"UnityPlayer + Assembly-CSharp ({ver or 'version unknown'})",
            {"version": ver, "product": _sniff_product(idx)})
    elif unity_player and (il2cpp_meta or game_assembly):
        ver = _sniff_unity_version(idx)
        add("unity-il2cpp", 90, f"UnityPlayer + IL2CPP metadata ({ver or 'version unknown'})",
            {"version": ver, "product": _sniff_product(idx)})
    elif unity_player:
        add("unity-mono", 55, "UnityPlayer present, runtime layout unclear", {})
    paks = idx.glob("*/Content/Paks/*.pak") + idx.glob("*.pak")
    shipping = [r for r in idx.glob("*.exe") if "shipping" in r.lower()]
    ue_ver = _sniff_unreal_version(idx) if (paks or shipping) else ""
    if paks and (shipping or ue_ver):
        utoc = bool(idx.glob("*/Content/Paks/*.utoc"))
        add("unreal", 88, f"Unreal paks ({ue_ver or 'version unknown'})",
            {"engine_version": ue_ver, "iostore": utoc})
    elif paks:
        add("unreal", 50, "Unreal-style .pak files", {})
    pck = [r for r in idx.files if r.lower().endswith(".pck")]
    if pck:
        add("godot", 85, f"Godot pack ({_sniff_godot_version(idx)})",
            {"version": _sniff_godot_version(idx)})
    if idx.has("data.win", "game.win", "game.unx"):
        add("gamemaker", 85, "GameMaker data.win", {})
    if idx.glob("www/js/rpg_core.js") or idx.glob("www/js/rmmz_core.js"):
        add("rpgmaker-mv", 85, "RPG Maker MV/MZ js core", {})
    if idx.glob("renpy/*.py") or idx.has("renpy.py"):
        add("renpy", 85, "Ren'Py runtime", {})
    love = [r for r in idx.files if r.lower().endswith(".love")]
    if love or idx.has("love.dll", "liblove.so"):
        add("loved", 70, "Love2D bundle", {})
    plugins = [r for r in idx.files if r.lower().endswith((".esm", ".esp", ".esl"))]
    archives = [r for r in idx.files if r.lower().endswith((".bsa", ".ba2"))]
    if plugins:
        add("bethesda", 85, f"Creation Engine plugins ({len(plugins)} .esm/.esp/.esl)",
            {"plugins": len(plugins), "archives": len(archives)})
    elif archives:
        add("bethesda", 55, "Creation Engine archives (.bsa/.ba2), no plugins seen", {})
    # managed vs native from exes
    exes = [r for r in idx.files if r.lower().endswith((".exe", ".dll", ".so"))][:30]
    managed_hits = 0
    for rel in exes:
        info = pe_info(idx.root / rel)
        if info and info.get("managed"):
            managed_hits += 1
    if managed_hits and not any(h[0].startswith("unity") for h in hits):
        ev = f"{managed_hits} managed PE module(s)"
        add("dotnet", 60, ev, {})
    if not hits and exes:
        add("native", 30, "native binaries, no engine fingerprint matched", {})
    hits.sort(key=lambda h: -h[1])
    ac = detect_anticheat(idx)
    return hits, {"anticheat": ac}


# ------------------------------------------------------------- steam discovery

def steam_roots() -> list[Path]:
    home = Path.home()
    cands = [
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
        home / ".steam",
        Path("/usr/share/steam"),
    ]
    if os.name == "nt":
        for drive in ("C:\\Program Files (x86)\\Steam", "C:\\Program Files\\Steam"):
            cands.append(Path(drive))
    return [c for c in cands if c.exists()]


def find_steam_libraries() -> list[Path]:
    libs: list[Path] = []
    for root in steam_roots():
        libs.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                data = _vdf(vdf.read_text(errors="replace"))
            except Exception:
                continue
            for _k, v in (data.get("libraryfolders") or {}).items():
                if isinstance(v, dict) and v.get("path"):
                    libs.append(Path(v["path"]))
                elif isinstance(v, str) and ("/" in v or "\\" in v or ":" in v):
                    libs.append(Path(v))
    # dedupe, keep existing
    seen, out = set(), []
    for l in libs:
        s = str(l)
        if s not in seen and l.exists():
            seen.add(s)
            out.append(l)
    return out


def list_installed() -> list[dict]:
    games = []
    for lib in find_steam_libraries():
        apps = lib / "steamapps"
        if not apps.exists():
            continue
        for mf in sorted(apps.glob("appmanifest_*.acf")):
            try:
                d = _vdf(mf.read_text(errors="replace")).get("AppState", {})
            except Exception:
                continue
            name, inst = d.get("name", "?"), d.get("installdir", "")
            if not inst:
                continue
            gdir = apps / "common" / inst
            if gdir.exists():
                games.append({"name": name, "appid": mf.stem.split("_")[-1],
                              "dir": str(gdir), "library": str(lib)})
    return games


def report(game: str, as_json: bool = False):
    games = list_installed()
    target = None
    gl = game.lower()
    for g in games:
        if gl == g["name"].lower() or gl == g["appid"] or gl in g["name"].lower():
            target = g
            break
    p = Path(game)
    if target is None and p.exists():
        target = {"name": p.name, "appid": "?", "dir": str(p), "library": "folder"}
    if target is None:
        return None
    idx = Index(target["dir"])
    hits, extra = detect(idx)
    out = {"game": target, "routes": [
        {"engine": ROUTES[h[0]][0] if h[0] in ROUTES else h[0], "score": h[1],
         "evidence": h[2], "details": h[3],
         "playbook": ROUTES[h[0]][1] if h[0] in ROUTES else "",
         "route": ROUTES[h[0]][2] if h[0] in ROUTES else "read skills/mod-any-game/SKILL.md"} for h in hits],
        "anticheat": extra["anticheat"]}
    return out


def register(sub):
    p = sub.add_parser("scan", help="find games; fingerprint engine, runtime, anti-cheat, routes")
    p.add_argument("game", nargs="?", help="game name/appid or folder path (omit with --list)")
    p.add_argument("--list", action="store_true", help="list installed Steam games")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=_run)


def _run(a: argparse.Namespace):
    if a.list or not a.game:
        games = list_installed()
        if a.json:
            print(json.dumps(games, indent=2))
        elif not games:
            print("no Steam libraries found. Pass a folder path directly: hw scan /path/to/game")
        else:
            for g in games:
                print(f"{g['appid']:>10}  {g['name']}  [{g['dir']}]")
        return
    rep = report(a.game, as_json=a.json)
    if rep is None:
        from hw.common import fail
        fail(f"game not found: {a.game!r}. Try `hw scan --list` or pass the install folder.")
    if a.json:
        print(json.dumps(rep, indent=2))
        return
    g = rep["game"]
    print(f"{g['name']}  (appid {g['appid']})\n  {g['dir']}")
    if not rep["routes"]:
        print("engine: unknown (no fingerprint matched) — see skills/game-recon/SKILL.md")
    for r in rep["routes"]:
        print(f"engine: {r['engine']}  (score {r['score']})\n  evidence: {r['evidence']}")
        if r["details"]:
            print("  details: " + ", ".join(f"{k}={v}" for k, v in r["details"].items() if v))
        print(f"  route: {r['route']}\n  playbook: {r['playbook']}")
    ac = rep["anticheat"]
    print("anti-cheat: " + (", ".join(ac) if ac else "none detected in folder (kernel/launcher-level protection lives elsewhere — search the web)"))
