"""`hw proton`: Steam-on-Linux helpers for modding Proton games.

Read-only by default; `run` only launches what you name, never kills anything.
Resolves Steam libraries, Proton prefixes (compatdata), and the Proton build
Steam would use, so other groups (`skyrim`, `capture`) don't reimplement paths.

Examples:
  hw proton list                       # Steam games with appid + prefix state
  hw proton prefix --appid 489830      # print the Proton prefix dir
  hw proton run --appid 489830 -- notepad.exe
  hw proton doctor --appid 489830      # prefix, proton build, skse, dxvk state
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


SKYRIM_SE_APPID = "489830"


def steam_home() -> Path | None:
    for cand in (Path.home() / ".local" / "share" / "Steam",
                 Path.home() / ".steam" / "steam",
                 Path.home() / ".steam"):
        if (cand / "steamapps").exists():
            return cand
    return None


def compatdata_dir(appid: str | int) -> Path | None:
    home = steam_home()
    if not home:
        return None
    p = home / "steamapps" / "compatdata" / str(appid)
    return p if p.exists() else None


def prefix_dir(appid: str | int) -> Path | None:
    c = compatdata_dir(appid)
    if c and (c / "pfx").exists():
        return c / "pfx"
    return None


def drive_c(appid: str | int) -> Path | None:
    p = prefix_dir(appid)
    if p and (p / "drive_c").exists():
        return p / "drive_c"
    return None


def proton_builds() -> list[dict]:
    """Installed Proton builds under steamapps/common + compatdata versions."""
    home = steam_home()
    out: list[dict] = []
    if not home:
        return out
    common = home / "steamapps" / "common"
    if common.exists():
        for d in sorted(common.iterdir()):
            if d.is_dir() and d.name.lower().startswith("proton"):
                ver = ""
                vf = d / "version"
                if vf.exists():
                    try:
                        ver = vf.read_text(errors="replace").strip().splitlines()[0]
                    except OSError:
                        pass
                out.append({"name": d.name, "dir": str(d), "version": ver})
    return out


def prefix_version(appid: str | int) -> str:
    c = compatdata_dir(appid)
    if c and (c / "version").exists():
        try:
            return (c / "version").read_text(errors="replace").strip().splitlines()[0]
        except OSError:
            pass
    return ""


def compat_tool(appid: str | int) -> str:
    """Per-game Proton mapping name from Steam's localconfig.vdf (read-only).

    Returns "" when the game follows Steam's default. Names look like
    "proton_experimental", "proton_9", ... Absent/multiple users -> "".
    """
    import glob
    cands = sorted(glob.glob(str(Path.home() / ".local" / "share" / "Steam"
                                     / "userdata" / "*" / "config" / "localconfig.vdf")))
    if not cands:
        return ""
    try:
        from hw import scan
        for path in cands:
            try:
                text = Path(path).read_text(errors="replace")
            except OSError:
                continue
            try:
                data = scan._vdf(text)
            except Exception:
                continue
            # walk down to Software/Valve/Steam/CompatToolMapping/<appid>/name
            node: object = data
            for key in ("Software", "Valve", "Steam"):
                node = node.get(key, {}) if isinstance(node, dict) else {}
            mapping = node.get("CompatToolMapping", {}) if isinstance(node, dict) else {}
            entry = mapping.get(str(appid), {}) if isinstance(mapping, dict) else {}
            if isinstance(entry, dict) and entry.get("name"):
                return str(entry["name"])
    except Exception:
        pass
    return ""


def pick_build(prefer: str = "") -> dict | None:
    """Pick an installed Proton build: prefer-substring, else Experimental, else last."""
    builds = proton_builds()
    if not builds:
        return None
    if prefer:
        for b in builds:
            if prefer.lower() in b["name"].lower():
                return b
    for b in builds:
        if "experimental" in b["name"].lower():
            return b
    return sorted(builds, key=lambda b: b["name"])[-1]


def proton_run_cmd(appid: str | int, exe_args: list[str],
                   prefer: str = "") -> list[str]:
    """Build a `proton run` command for an exe inside (or outside) the prefix.

    Uses the newest installed Proton build's `proton` script with
    STEAM_COMPAT_DATA_PATH / STEAM_COMPAT_CLIENT_INSTALL_PATH set, which is
    exactly what Steam does. Returns the argv; the caller decides to run it.
    """
    from hw.common import fail
    home = steam_home()
    if not home:
        fail("no Steam install found (looked in ~/.local/share/Steam, ~/.steam)")
    pick = pick_build(prefer)
    if not pick:
        fail("no Proton builds installed (install one in Steam: Steam > Settings > Compatibility)")
    proton_script = Path(pick["dir"]) / "proton"
    if not proton_script.exists():
        fail(f"Proton script missing: {proton_script}")
    compat = compatdata_dir(appid)
    env_note = pick["name"]
    _ = env_note
    cmd = [str(proton_script), "run"] + list(exe_args)
    return cmd


def run_env(appid: str | int) -> dict:
    home = steam_home() or Path.home() / ".local" / "share" / "Steam"
    compat = compatdata_dir(appid) or (home / "steamapps" / "compatdata" / str(appid))
    env = dict(os.environ)
    env["STEAM_COMPAT_DATA_PATH"] = str(compat)
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = str(home)
    return env


def run_in_prefix(appid: str | int, exe_args: list[str], timeout: float = 120.0,
                  prefer_proton: str = "") -> tuple[int, str]:
    cmd = proton_run_cmd(appid, exe_args, prefer=prefer_proton)
    env = run_env(appid)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return 127, f"proton script not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def list_games() -> list[dict]:
    from hw import scan
    games = scan.list_installed()
    for g in games:
        c = compatdata_dir(g["appid"])
        g["prefix"] = str(c / "pfx") if c and (c / "pfx").exists() else ""
        g["proton"] = prefix_version(g["appid"])
    return games


def doctor(appid: str | int) -> dict:
    """Machine-readable health of one Proton game (used by `hw skyrim doctor`)."""
    from hw import scan
    home = steam_home()
    out: dict = {"appid": str(appid), "steam": str(home) if home else "",
                 "prefix": "", "proton": "", "builds": [b["name"] for b in proton_builds()],
                 "compat_tool": compat_tool(appid),
                 "protontricks": bool(shutil.which("protontricks")),
                 "wine": bool(shutil.which("wine"))}
    c = compatdata_dir(appid)
    if c:
        out["prefix"] = str(c / "pfx")
        out["proton"] = prefix_version(appid)
    # game dir via scan
    for g in scan.list_installed():
        if g["appid"] == str(appid):
            out["game"] = g["name"]
            out["dir"] = g["dir"]
            break
    return out


def register(sub):
    p = sub.add_parser("proton", help="Steam/Proton paths, prefix runs, doctor")
    sp = p.add_subparsers(dest="cmd", metavar="<cmd>")

    q = sp.add_parser("list", help="Steam games with prefix + proton state")
    q.set_defaults(func=lambda a: _r_list())

    q = sp.add_parser("prefix", help="print the Proton prefix dir for an appid")
    q.add_argument("--appid", default=SKYRIM_SE_APPID)
    q.set_defaults(func=lambda a: print(prefix_dir(a.appid) or compatdata_dir(a.appid) or ""))

    q = sp.add_parser("run", help="run an exe inside a game's Proton prefix")
    q.add_argument("--appid", default=SKYRIM_SE_APPID)
    q.add_argument("--proton", default="", help="substring to pick a Proton build")
    q.add_argument("--timeout", type=float, default=120.0)
    q.add_argument("exe", nargs=argparse.REMAINDER, help="exe + args (after --)")
    q.set_defaults(func=_r_run)

    q = sp.add_parser("doctor", help="prefix, proton build, tools for an appid")
    q.add_argument("--appid", default=SKYRIM_SE_APPID)
    q.set_defaults(func=_r_doctor)
    p.set_defaults(func=lambda a: p.print_help())


def _r_list():
    import json
    games = list_games()
    if not games:
        print("no Steam libraries found.")
        return
    for g in games:
        state = f"prefix={'yes' if g['prefix'] else 'no'}"
        if g.get("proton"):
            state += f" proton={g['proton']}"
        print(f"{g['appid']:>10}  {g['name']}  [{g['dir']}]  {state}")
    _ = json  # (kept import-light; --json lives on scan)


def _r_run(a: argparse.Namespace):
    from hw.common import fail
    exe = [x for x in (a.exe or []) if x != "--"]
    if not exe:
        fail("usage: hw proton run --appid 489830 -- notepad.exe [args...]")
    cmd = proton_run_cmd(a.appid, exe, prefer=a.proton)
    env = run_env(a.appid)
    print("+ " + " ".join(cmd))
    r = subprocess.run(cmd, env=env, timeout=a.timeout)
    raise SystemExit(r.returncode)


def _r_doctor(a: argparse.Namespace):
    import json
    print(json.dumps(doctor(a.appid), indent=2))
