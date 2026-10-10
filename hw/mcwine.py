"""`hw skyrim setup-modrinth-wine`: run the user's Modrinth profile under Wine.

The SkyCraft SKSE plugin starts Minecraft through a Windows launcher path
(ShellExecute/CreateProcess in the prefix), so the native-Linux Modrinth App
can never be its `sLauncher` — and the user has no Prism. This command builds
the third option: the profile's *content* (jars, mods, worlds, auth identity)
launched as a Windows process in the game's own Proton prefix:

- classpath + natives + args are derived from the Modrinth fused version json
  (`meta/versions/<mc>-<loader>/<mc>-<loader>.json`), reusing Theseus's own
  cached jars/assets via Z: paths (only Windows natives + logging config are
  downloaded when missing);
- Windows Java 25 comes from Adoptium (downloaded once into the prefix);
- the launch is a CRLF .bat the plugin ShellExecutes (`sLauncher`), with the
  player's real username+uuid so local saves keep their playerdata
  (accessToken 0: singleplayer needs no session — Realms/servers stay out);
- the game dir IS the Modrinth profile, so worlds/mods/configs are shared
  (profile saves are backed up first).

Inside the prefix everything is Win32 again, so the stock SkyCraft Fabric jar
links over the plugin's shared memory with zero patching.

Examples:
  hw skyrim setup-modrinth-wine --dry-run
  hw skyrim setup-modrinth-wine
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

APPID = "489830"
ADOPTIUM_JAVA_URL = ("https://api.adoptium.net/v3/binary/latest/25/ga/windows"
                     "/x64/jdk/hotspot/normal/eclipse")
EPOCH_1601_TO_1970_100NS = 116444736000000000


# ------------------------------------------------------------- pure helpers

def dashless_uuid(u: str) -> str:
    return u.replace("-", "").lower()


def maven_path(name: str) -> str | None:
    """'group:artifact:version[:classifier]' -> 'group/path/artifact/version/file.jar'."""
    parts = name.split(":")
    if len(parts) < 3:
        return None
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    base = f"{artifact}-{version}" + (f"-{classifier}" if classifier else "") + ".jar"
    return f"{group.replace('.', '/')}/{artifact}/{version}/{base}"


def rules_allow(rules: list | None, os_name: str = "windows", arch: str = "x64") -> bool:
    """Mojang rules: no rules -> allow; first matching rule decides; none match -> deny."""
    if not rules:
        return True
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        features = rule.get("features")
        if features:
            continue  # demo/quickplay-only entries: skip in this flow
        oso = rule.get("os") or {}
        name_ok = ("name" not in oso) or (oso["name"] == os_name)
        arch_ok = ("arch" not in oso) or (oso["arch"] == arch)
        if name_ok and arch_ok:
            return rule.get("action") == "allow"
    return False


def zpath(linux_path: str | Path) -> str:
    """Linux path -> Wine Z: path with backslashes."""
    p = str(linux_path)
    if len(p) > 1 and p[1] == ":":
        return p.replace("/", "\\")
    return ("Z:" + p).replace("/", "\\")


def msvc_ticks(st_mtime_ns: int) -> int:
    """MSVC file_time count (100ns ticks since 1601) for a Unix mtime."""
    return st_mtime_ns // 100 + EPOCH_1601_TO_1970_100NS


def substitute(arg: str, mapping: dict) -> str:
    for k, v in mapping.items():
        arg = arg.replace("${" + k + "}", v)
    return arg


def select_entries(libraries: list) -> tuple[list[dict], list[dict]]:
    """Split fused-json libraries into (classpath jars, windows-natives jars).

    Each item: {name, path, url, sha1, size}. Natives are the
    :natives-windows classifier variants; osx/linux/macOS entries are dropped.
    """
    cp, natives = [], []
    for lib in libraries:
        name = lib.get("name", "")
        if not rules_allow(lib.get("rules")):
            continue
        if lib.get("include_in_classpath") is False:
            continue
        low = name.lower()
        # Arch is encoded in the classifier (windows-arm64 etc.), not the rules.
        if "arm64" in low or "aarch64" in low:
            continue  # this flow targets x64
        if "natives-macos" in low or "natives-linux" in low or "natives-osx" in low:
            continue
        art = (lib.get("downloads") or {}).get("artifact") or {}
        if not art.get("path"):
            continue
        item = {"name": name, "path": art["path"], "url": art.get("url", ""),
                "sha1": art.get("sha1", ""), "size": art.get("size", 0)}
        if low.endswith(":natives-windows"):
            natives.append(item)
        else:
            cp.append(item)
    return cp, natives


def render_bat(java_exe: str, jvm_args: list[str], cp: str, main_class: str,
               game_args: list[str]) -> str:
    """CRLF .bat launching the game. ONE command line: batch executes
    line-by-line, so multi-line args would run as separate (broken) commands."""
    cmd = " ".join([f'start "" /min "{java_exe}"'] + jvm_args
                   + [f'-cp "{cp}"', main_class] + game_args)
    lines = ["@echo off",
             "rem Generated by `hw skyrim setup-modrinth-wine` — do not hand-edit.",
             "rem Starts the Modrinth profile's Minecraft as a Windows process so the",
             "rem SkyCraft SKSE plugin can link it over shared memory. Hidden window.",
             "cd /d %~dp0",
             cmd]
    return "\r\n".join(lines) + "\r\n"


# ------------------------------------------------------------- paths

def prefix_drive_c() -> Path:
    return (Path.home() / ".local" / "share" / "Steam" / "steamapps"
            / "compatdata" / APPID / "pfx" / "drive_c")


def modrinth_base() -> Path | None:
    for cand in (Path.home() / ".var" / "app" / "com.modrinth.ModrinthApp"
                 / "data" / "ModrinthApp",
                 Path.home() / ".local" / "share" / "ModrinthApp",
                 Path.home() / ".config" / "ModrinthApp"):
        if (cand / "profiles").exists():
            return cand
    return None


def modrinth_db_profile(profile: str) -> dict:
    out: dict = {}
    base = modrinth_base()
    if not base:
        return out
    db_path = base / "app.db"
    if not db_path.exists():
        return out
    try:
        import sqlite3
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = db.execute(
                "SELECT id FROM instances WHERE name = ? OR path = ?",
                (profile, profile)).fetchone()
            if not row:
                return out
            ver = db.execute(
                "SELECT game_version, loader, loader_version "
                "FROM instance_content_sets WHERE instance_id = ? LIMIT 1",
                (row[0],)).fetchone()
            if ver:
                out = {"game_version": ver[0] or "", "loader": ver[1] or "",
                       "loader_version": ver[2] or ""}
        finally:
            db.close()
    except Exception:
        return {}
    return out


def profile_identity(profile_dir: Path) -> tuple[str, str]:
    """(username, dashless-uuid) from the profile's usercache.json."""
    try:
        entries = json.loads((profile_dir / "usercache.json").read_text())
        if entries:
            return entries[0].get("name", "Steve"), \
                dashless_uuid(entries[0].get("uuid", ""))
    except Exception:
        pass
    return "Steve", "0" * 32


def fused_json(meta: Path, mc: str, loader: str) -> tuple[Path, dict]:
    p = meta / "versions" / f"{mc}-{loader}" / f"{mc}-{loader}.json"
    if not p.exists():
        from hw.common import fail
        fail(f"fused version json missing: {p} (is the profile fully downloaded?)")
    assert isinstance(p, Path)
    return p, json.loads(p.read_text())


# ------------------------------------------------------------- downloads

def download(url: str, dest: Path, size: int = 0, sha1: str = "") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and size and dest.stat().st_size == size:
        return dest
    if sha1 and dest.exists():
        h = hashlib.sha1()
        with open(dest, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() == sha1:
            return dest
    req = urllib.request.Request(url, headers={"User-Agent": "hot-wills-modkit"})
    last = [0.0]
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            now = time.time()
            if now - last[0] > 5:
                last[0] = now
                print(f"  ... {dest.name}: {f.tell() // 1024 // 1024} MiB")
    print(f"  got {dest.name} ({dest.stat().st_size // 1024} KiB)")
    return dest


def ensure_windows_jre(java_dir: Path, force: bool = False) -> Path:
    """Windows Java 25 (Adoptium) in the prefix. Returns javaw.exe (C: path as given)."""
    hit = list(java_dir.rglob("javaw.exe"))
    if hit and not force:
        return hit[0]
    if java_dir.exists() and force:
        shutil.rmtree(java_dir)
    java_dir.mkdir(parents=True, exist_ok=True)
    zf = java_dir / "openjdk25-win.zip"
    print(f"downloading Windows Java 25 (~200 MB) ...")
    download(ADOPTIUM_JAVA_URL, zf)
    print("extracting ...")
    with zipfile.ZipFile(zf) as z:
        z.extractall(java_dir)
    zf.unlink(missing_ok=True)
    hit = list(java_dir.rglob("javaw.exe"))
    if not hit:
        from hw.common import fail
        fail(f"javaw.exe not found after extracting {zf}")
    return hit[0]


def ensure_windows_natives(natives: list[dict], dl_dir: Path, out_dir: Path,
                            force: bool = False) -> int:
    """Download :natives-windows jars, extract their .dlls. Returns dll count."""
    dl_dir.mkdir(parents=True, exist_ok=True)
    if force and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    have = list(out_dir.glob("*.dll"))
    if have and not force:
        return len(have)
    count = 0
    for item in natives:
        dest = dl_dir / Path(item["path"]).name
        download(item["url"], dest, item.get("size", 0), item.get("sha1", ""))
        with zipfile.ZipFile(dest) as z:
            for member in z.namelist():
                if member.lower().endswith(".dll"):
                    data = z.read(member)
                    (out_dir / Path(member).name).write_bytes(data)
                    count += 1
    return count


# ------------------------------------------------------------- setup

def setup(profile: str = "Fabric 26.3", dry_run: bool = False,
          force: bool = False) -> dict:
    from hw import backup
    from hw.common import fail
    base = modrinth_base()
    if not base:
        fail("Modrinth App data not found (profiles/ missing).")
    assert base is not None
    prof = base / "profiles" / profile
    if not prof.exists():
        fail(f"Modrinth profile {profile!r} not found under {base / 'profiles'}")
    meta = base / "meta"
    ver = modrinth_db_profile(profile)
    mc = ver.get("game_version") or "26.3"
    loader = ver.get("loader_version") or "0.19.5"
    username, uuid = profile_identity(prof)
    fused_path, fused = fused_json(meta, mc, loader)
    cp_items, nat_items = select_entries(fused.get("libraries", []))

    drive_c = prefix_drive_c()
    mc_dir = drive_c / "skycraft-mc"
    java_dir = drive_c / "skycraft-java"
    natives_dir = mc_dir / "natives"
    dl_natives = mc_dir / "downloads" / "natives"
    bat = drive_c / "skycraft-modrinth.bat"

    # resolve every cp jar to a Theseus-cached file (download if absent)
    resolved: list[str] = []
    missing: list[dict] = []
    for item in cp_items:
        local = meta / "libraries" / item["path"]
        if local.exists():
            resolved.append(str(local))
        else:
            missing.append(item)
    resolved.append(str(fused_path.parent / f"{mc}-{loader}.jar"))
    log_cfg = ((fused.get("logging") or {}).get("client") or {}).get("file") or {}
    log_cfg_local = meta / "log_configs" / Path(log_cfg.get("url", "")).name \
        if log_cfg.get("url") else None

    plan = {
        "profile": str(prof),
        "mc": mc, "loader": loader, "username": username, "uuid": uuid,
        "classpath_jars": len(resolved), "missing_jars": len(missing),
        "natives": len(nat_items),
        "java_dir": str(java_dir), "natives_dir": str(natives_dir),
        "bat": str(bat),
    }
    if dry_run:
        plan["missing_urls"] = [m["url"] for m in missing[:10]]
        return plan

    backup.create(str(prof / "saves"), "modrinth-saves-before-wine")
    # downloads: missing cp jars + logging config
    for item in missing:
        download(item["url"], meta / "libraries" / item["path"],
                 item.get("size", 0), item.get("sha1", ""))
        resolved.append(str(meta / "libraries" / item["path"]))
    if log_cfg.get("url") and log_cfg_local and not log_cfg_local.exists():
        download(log_cfg["url"], log_cfg_local,
                 log_cfg.get("size", 0), log_cfg.get("sha1", ""))
    javaw = ensure_windows_jre(java_dir, force=force)
    ensure_windows_natives(nat_items, dl_natives, natives_dir, force=force)

    mapping = {
        "natives_directory": zpath(natives_dir),
        "launcher_name": "skycraft-modrinth",
        "launcher_version": "0.1.0",
        "classpath": ";".join([zpath(p) for p in resolved]),
        "classpath_separator": ";",
        "library_directory": zpath(meta / "libraries"),
        "version_name": mc,
    }
    jvm_args = []
    for entry in (fused.get("arguments") or {}).get("jvm", []):
        if isinstance(entry, str):
            if entry == "-cp" or entry == "${classpath}":
                continue
            jvm_args.append(substitute(entry, mapping))
        elif isinstance(entry, dict):
            if rules_allow(entry.get("rules")):
                v = entry.get("value")
                for s in (v if isinstance(v, list) else [v]):
                    if isinstance(s, str) and s not in ("-cp", "${classpath}"):
                        jvm_args.append(substitute(s, mapping))
    jvm_args = [a for a in jvm_args if "${" not in a]
    jvm_args.append(f"-Dlog4j.configurationFile={zpath(log_cfg_local)}"
                    if log_cfg_local and log_cfg_local.exists() else "")
    jvm_args = [a for a in jvm_args if a]

    asset_index = (fused.get("assetIndex") or {}).get("id", mc)
    game_args: list[str] = []
    for entry in (fused.get("arguments") or {}).get("game", []):
        if isinstance(entry, str):
            game_args.append(entry)
        elif isinstance(entry, dict) and rules_allow(entry.get("rules")):
            v = entry.get("value")
            game_args += [s for s in (v if isinstance(v, list) else [v])
                          if isinstance(s, str)]
    subs = {"auth_player_name": username, "version_name": mc,
            "game_directory": zpath(prof),
            "assets_root": zpath(meta / "assets"),
            "assets_index_name": str(asset_index),
            "auth_uuid": uuid, "auth_access_token": "0",
            "clientid": "0", "auth_xuid": "0",
            "user_type": "msa", "version_type": "release"}
    game_args = [substitute(a, subs) for a in game_args]
    game_args = [a for a in game_args if "${" not in a]

    cp = ";".join(zpath(p) for p in resolved)
    bat.write_text(render_bat(zpath(javaw), jvm_args, cp,
                              fused.get("mainClass", ""), game_args),
                   encoding="utf-8", newline="")

    # point the SKSE plugin at the bat (Windows path), keep a backup
    game = Path.home() / ".local" / "share" / "Steam" / "steamapps" / "common" \
        / "Skyrim Special Edition"
    ini = game / "Data" / "SKSE" / "Plugins" / "SkyCraft.ini"
    if ini.exists():
        backup.create(str(ini.parent), "skse-plugins-before-modrinth-bat")
    ini.write_text("; SkyCraft: modrinth profile under Wine (written by "
                   "`hw skyrim setup-modrinth-wine`).\n; No Prism involved.\n"
                   "\n[Minecraft]\n"
                   "bStartWithSkyrim = 1\n\n"
                   "; The .bat boots the Modrinth profile as a Windows process.\n"
                   "sLauncher = C:\\skycraft-modrinth.bat\n\n"
                   "sArguments = \n\n"
                   "[Debug]\nbDiagnostics = 0\n",
                   encoding="utf-8")
    return {**plan, "javaw": zpath(javaw), "ini": str(ini)}


def register_into(sp) -> None:
    q = sp.add_parser("setup-modrinth-wine",
                      help="boot the Modrinth profile as a Windows process (no Prism)")
    q.add_argument("--profile", default="Fabric 26.3")
    q.add_argument("--dry-run", action="store_true")
    q.add_argument("--force", action="store_true",
                   help="re-download Java + natives even if present")
    q.set_defaults(func=lambda a: print(json.dumps(
        setup(a.profile, a.dry_run, a.force), indent=2)))
