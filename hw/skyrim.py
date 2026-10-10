"""`hw skyrim`: Skyrim Special Edition on Linux — status, SkyCraft install, auto-launch.

Skyrim SE (appid 489830) runs under Proton; SKSE64 runs inside that prefix.
SkyCraft itself is a Windows SKSE plugin + a Minecraft Fabric mod that talk
over Windows shared memory — which does not cross the Proton boundary. So on
Linux this group does the honest thing:

- `status`/`doctor`: one screen for install, SKSE, Address Library, SkyCraft
  files, the Modrinth "Fabric 26.3" profile (fabric-api, skycraft jar, Java),
  Proton prefix, and whether the Steam auto-launch wrapper is installed.
- `install-skycraft`: copies the Linux-safe half of SkyCraft (SkyCraft.ini
  pointed at the Modrinth launcher, Papyrus host shim, docs) into the real
  Steam install. Backs up first. It never pretends the Windows .dll works
  here — see `doctor` for the Phase-2 native-build note.
- `launch`: the auto-launch. Backs up saves, starts the `hw bridge` broker,
  starts Modrinth's Fabric 26.3 profile, starts the overlay compositor, then
  starts Skyrim (via Steam, or via SKSE-in-Proton). As a Steam Launch Options
  prefix it backgrounds the services and `exec`s Steam's own command, so
  every normal Play click brings the passthrough up with it.

The Minecraft side is the user's Modrinth "Fabric 26.3" profile (MC 26.3,
Fabric Loader >= 0.19.5, Fabric API, Java 25). SkyCraft's Fabric jar, once
built from the user's SkyCraft source, lives in that profile's `mods/`.

Examples:
  hw skyrim status
  hw skyrim doctor
  hw skyrim install-skycraft --source ~/Downloads/SkyCraft-0.1.2
  hw skyrim build-fabric --source ~/Downloads/SkyCraft-0.1.2 [--install]
  hw skyrim launch --dry-run
  hw skyrim launch --no-minecraft --dry-run
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

APPID = "489830"
MC_PROFILE_DEFAULT = "Fabric 26.3"
BRIDGE_PORT_DEFAULT = 27431

# Which Proton runs SKSE. Empty = Steam default (Experimental): the DLL loads
# there once the prefix has a current VC++ runtime, AND Minecraft's Java
# needs Experimental's Wine (its NetworkInterface enumeration fatally crashes
# under Proton 9.0 — verified with a 10-line repro). The plugin's own Load
# check is flaky under Wine (~1 in 3-4 boots sail through; the wrapper retries
# automatically), independent of Proton version.
SKSE_PROTON_PREFER = ""

SKYCRAFT_INI_TEMPLATE = """; SkyCraft on Linux (written by `hw skyrim install-skycraft`).
; The Windows SKSE plugin reads this when present; the Linux auto-launch
; uses the same values so both halves agree.
; See docs/CONTRACT.md in examples/skyrim-skycraft-linux for the mapping.

[Minecraft]
; 1 = the auto-launch starts Minecraft with Skyrim (Modrinth profile below).
bStartWithSkyrim = 1

; Full path of the Linux launcher script (starts the Modrinth profile).
; Empty means: start it yourself (`hw skyrim launch` already did).
sLauncher = {launcher}

; Arguments passed to sLauncher.
sArguments = --profile "{profile}" --bridge 127.0.0.1:{port}

[Bridge]
; Linux transport: hw bridge protocol v1 over TCP (no Windows shared memory).
sHost = 127.0.0.1
nPort = {port}
sProfile = {profile}

[Debug]
bDiagnostics = {diagnostics}
"""


def skyrim_dir() -> Path | None:
    from hw import scan
    for g in scan.list_installed():
        if g["appid"] == APPID:
            return Path(g["dir"])
    for cand in (Path.home() / ".local" / "share" / "Steam" / "steamapps" / "common" / "Skyrim Special Edition",
                 Path.home() / ".steam" / "steam" / "steamapps" / "common" / "Skyrim Special Edition"):
        if (cand / "SkyrimSE.exe").exists():
            return cand
    return None


def modrinth_profiles_root() -> Path | None:
    cands = [
        Path.home() / ".var" / "app" / "com.modrinth.ModrinthApp" / "data" / "ModrinthApp" / "profiles",
        Path.home() / ".local" / "share" / "ModrinthApp" / "profiles",
        Path.home() / ".config" / "ModrinthApp" / "profiles",
    ]
    for c in cands:
        if c.exists():
            return c
    return None


def mc_profile_dir(profile: str = MC_PROFILE_DEFAULT) -> Path | None:
    root = modrinth_profiles_root()
    if root and (root / profile).exists():
        return root / profile
    return None


def java25() -> str:
    cands = [Path("/usr/lib/jvm/jdk-25.0.2-oracle-x64/bin/java"),
             Path("/usr/lib/jvm/jdk-25-oracle-x64/bin/java"),
             Path("/usr/lib/jvm/java-25-openjdk-amd64/bin/java")]
    for c in cands:
        if c.exists():
            return str(c)
    found = shutil.which("java")
    return found or ""


def skse_state(game: Path | None) -> dict:
    out = {"loader": False, "dll": False, "version": ""}
    if not game:
        return out
    out["loader"] = (game / "skse64_loader.exe").exists()
    out["dll"] = (game / "skse64_1_7_104.dll").exists() or \
        bool(list(game.glob("skse64_*.dll")))
    return out


def addresslib_state(game: Path | None) -> dict:
    out = {"bins": 0, "has_1179": False, "has_17104": False}
    if not game:
        return out
    plug = game / "Data" / "SKSE" / "Plugins"
    if plug.exists():
        bins = list(plug.glob("versionlib-*.bin"))
        out["bins"] = len(bins)
        out["has_1179"] = (plug / "versionlib-1-6-1179-0.bin").exists()
        out["has_17104"] = (plug / "versionlib-1-7-104-0.bin").exists()
    return out


def skycraft_state(game: Path | None) -> dict:
    out = {"ini": False, "dll": False, "linux_ini": False}
    if not game:
        return out
    ini = game / "Data" / "SKSE" / "Plugins" / "SkyCraft.ini"
    out["ini"] = ini.exists()
    out["dll"] = (game / "Data" / "SKSE" / "Plugins" / "SkyCraft.dll").exists()
    if ini.exists():
        try:
            out["linux_ini"] = "hw skyrim install-skycraft" in ini.read_text(errors="replace")
        except OSError:
            pass
    return out


def modrinth_db_profile(profile: str = MC_PROFILE_DEFAULT) -> dict:
    """Read game/loader versions from the Modrinth App's own database.

    Stdlib sqlite3 only; returns {} when the app/db is absent (read-only).
    """
    out: dict = {}
    db_path = (Path.home() / ".var" / "app" / "com.modrinth.ModrinthApp"
               / "data" / "ModrinthApp" / "app.db")
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


def fabric_profile_state(profile: str = MC_PROFILE_DEFAULT) -> dict:
    out = {"dir": "", "fabric_api": False, "skycraft_jar": "",
           "saves": [], "mods_disabled": 0,
           "game_version": "", "loader": "", "loader_version": ""}
    out.update({k: v for k, v in modrinth_db_profile(profile).items() if v})
    d = mc_profile_dir(profile)
    if not d:
        return out
    out["dir"] = str(d)
    mods = d / "mods"
    if mods.exists():
        jars = list(mods.glob("*.jar"))
        out["fabric_api"] = any("fabric-api" in j.name for j in jars)
        for j in jars:
            if j.name.startswith("skycraft-") and j.suffix == ".jar":
                out["skycraft_jar"] = j.name
        out["mods_disabled"] = len(list(mods.glob("*.jar.disabled")))
    saves = d / "saves"
    if saves.exists():
        out["saves"] = [p.name for p in sorted(saves.iterdir()) if p.is_dir()][:10]
    return out


def status(profile: str = MC_PROFILE_DEFAULT) -> dict:
    from hw import proton
    game = skyrim_dir()
    prefix = proton.prefix_dir(APPID)
    return {
        "game_dir": str(game) if game else "",
        "game_exe": bool(game and (game / "SkyrimSE.exe").exists()),
        "skse": skse_state(game),
        "addresslib": addresslib_state(game),
        "skycraft": skycraft_state(game),
        "proton_prefix": str(prefix) if prefix else "",
        "proton_version": proton.prefix_version(APPID),
        "proton_builds": [b["name"] for b in proton.proton_builds()],
        "compat_tool": proton.compat_tool(APPID),
        "skse_proton": SKSE_PROTON_PREFER,
        "java": java25(),
        "modrinth_root": str(modrinth_profiles_root() or ""),
        "fabric_profile": fabric_profile_state(profile),
        "wrapper": wrapper_state(),
    }


def wrapper_state() -> dict:
    root = _kit_root()
    script = root / "bin" / "skycraft-autolaunch.sh"
    return {"script": str(script), "exists": script.exists(),
            "executable": bool(script.exists() and os.access(script, os.X_OK))}


def _kit_root() -> Path:
    here = Path(__file__).resolve().parent
    for cand in (here.parent, Path.cwd(), *Path.cwd().parents):
        if (cand / "knowledge" / "INDEX.md").exists() or (cand / "skills" / "mod-any-game").exists():
            return cand
    return here.parent


def doctor_fixes(st: dict) -> list[str]:
    fixes = []
    if not st["game_dir"]:
        fixes.append("Skyrim SE not found via Steam — install it (appid 489830) first.")
    if st["game_dir"] and not st["skse"]["loader"]:
        fixes.append("SKSE64 missing: install skse64_loader.exe + .dll for your game "
                     "version next to SkyrimSE.exe (https://skse.silverlock.org/).")
    if st["game_dir"] and st["addresslib"]["bins"] == 0:
        fixes.append("Address Library missing: install the All-in-one file into "
                     "Data/SKSE/Plugins/ (lets SKSE plugins survive game updates).")
    if st["game_dir"] and st["skycraft"]["dll"]:
        fixes.append("SkyCraft.dll present: it needs a current VC++ runtime in the "
                     "prefix or its Load crashes in MSVCP140!_Mtx_lock (SKSE dialog). "
                     "Fix once: install vc_redist.x64 (vcrun2022) into the prefix. "
                     "Note the Load stays flaky under Wine (~1 in 3-4) — the wrapper "
                     "retries failed boots automatically (SKYCRAFT_MAX_TRIES).")
    if not st["proton_prefix"]:
        fixes.append("No Proton prefix for 489830 — launch Skyrim once from Steam first.")
    else:
        compat = (st.get("compat_tool") or "").lower()
        if "9" in compat and "experimental" not in compat:
            fixes.append("Proton is pinned to 9.0 for Skyrim, but Minecraft's Java "
                         "fatally crashes there (NetworkInterface enumeration under "
                         "Wine 9.0 — verified with a minimal repro). Use Steam's default "
                         "(Experimental): Steam > Skyrim SE > Properties > Compatibility > "
                         "UNCHECK the override (or pick Proton Experimental explicitly).")
    if not st["java"]:
        fixes.append("No Java found — install Java 25 (Minecraft 26.x needs it).")
    if not st["modrinth_root"]:
        fixes.append("Modrinth App profiles not found — install Modrinth App and log in.")
    elif not st["fabric_profile"]["dir"]:
        fixes.append(f"Modrinth profile {MC_PROFILE_DEFAULT!r} not found — create it "
                     "(MC 26.3, Fabric Loader >= 0.19.5, Fabric API).")
    elif not st["fabric_profile"]["fabric_api"]:
        fixes.append("Fabric API jar missing in the profile's mods/ — install "
                     "fabric-api 0.161.0+26.3 from Modrinth.")
    if st["fabric_profile"]["dir"] and not st["fabric_profile"]["skycraft_jar"]:
        fixes.append("SkyCraft Fabric jar not in the Modrinth profile's mods/ yet — run "
                     "`hw skyrim build-fabric --source <skycraft> --install`. "
                     "(Only needed for the native-Linux Minecraft path; the Proton path "
                     "uses the jar inside the SkyCraft-Minecraft bundle and manages it itself.)")
    if st["skycraft"]["dll"]:
        pass  # Windows build present (works under Proton); nothing to say
    elif st["game_dir"] and not st["skycraft"]["ini"]:
        fixes.append("SkyCraft.ini not installed — run `hw skyrim install-skycraft`.")
    if not st["wrapper"]["exists"]:
        fixes.append("Steam wrapper missing from the kit checkout (bin/skycraft-autolaunch.sh).")
    return fixes


def install_skycraft(source: str, profile: str = MC_PROFILE_DEFAULT,
                     port: int = BRIDGE_PORT_DEFAULT, diagnostics: int = 0) -> dict:
    """Copy the Linux-safe half of SkyCraft into the Steam install."""
    from hw.common import fail
    from hw import backup
    game = skyrim_dir()
    if not game:
        fail("Skyrim SE install not found (Steam appid 489830).")
    assert game is not None
    src = Path(source).expanduser()
    if not src.exists():
        fail(f"SkyCraft source not found: {src}")
    plug = game / "Data" / "SKSE" / "Plugins"
    plug.mkdir(parents=True, exist_ok=True)
    backup.create(str(game / "Data" / "SKSE"), "skyrim-skse-before-skycraft")
    root = _kit_root()
    notes = []
    if (plug / "SkyCraft.dll").exists():
        # Real Windows flow active (DLL loads under Proton 9.0): keep the release
        # SkyCraft.ini — the plugin reads Windows paths from it. The Linux bridge
        # ini would break its launcher lookup.
        notes.append("kept release SkyCraft.ini (SkyCraft.dll present)")
    else:
        launcher = root / "bin" / "skycraft-modrinth.sh"
        ini = SKYCRAFT_INI_TEMPLATE.format(launcher=str(launcher), profile=profile,
                                           port=port, diagnostics=diagnostics)
        (plug / "SkyCraft.ini").write_text(ini)
        notes.append("wrote Linux-bridge SkyCraft.ini (no SkyCraft.dll present)")
    # Papyrus host shim (file-drop cam export, no SKSE C++ needed on Linux).
    # Source goes to Data/Scripts/Source/ (compile once in the Creation Kit,
    # which writes the .pex next to it in Data/Scripts/).
    shim_src = root / "adapters" / "papyrus" / "SkyCraftBridge.psc"
    scripts = game / "Data" / "Scripts" / "Source"
    note = ""
    if shim_src.exists():
        scripts.mkdir(parents=True, exist_ok=True)
        shutil.copy(shim_src, scripts / "SkyCraftBridge.psc")
        note = " + SkyCraftBridge.psc"
    # contract for the mapping numbers
    launcher = root / "bin" / "skycraft-modrinth.sh"
    return {"ini": str(plug / "SkyCraft.ini"), "launcher": str(launcher),
            "note": "; ".join(notes) + f"{note}; saves backed up as "
                    f"skyrim-skse-before-skycraft"}


def build_fabric(source: str, install: bool = False,
                 profile: str = MC_PROFILE_DEFAULT, timeout: float = 1500.0) -> dict:
    """Build skycraft-fabric-<ver>.jar from the SkyCraft source with Gradle."""
    from hw.common import fail
    src = Path(source).expanduser()
    proj = src if (src / "build.gradle").exists() else src / "fabric"
    gradlew = proj / "gradlew"
    if not gradlew.exists():
        fail(f"no gradlew under {proj} (want the SkyCraft fabric/ project dir)")
    j25 = java25()
    env = dict(os.environ)
    if j25:
        env["JAVA_HOME"] = str(Path(j25).parent.parent)
        env["PATH"] = f"{Path(j25).parent}:{env.get('PATH', '')}"
    try:
        os.chmod(gradlew, 0o755)
    except OSError:
        pass
    cmd = [str(gradlew), "-p", str(proj), "build", "-x", "test"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        tail = ((r.stdout or "") + (r.stderr or ""))[-3000:]
        fail(f"gradle build failed (exit {r.returncode}):\n{tail}")
    libs = [j for j in (proj / "build" / "libs").glob("skycraft-*.jar")
            if "sources" not in j.name]
    if not libs:
        fail("build succeeded but no build/libs/skycraft-*.jar found")
    jar = sorted(libs, key=lambda p: p.stat().st_mtime)[-1]
    out: dict = {"jar": str(jar)}
    if install:
        d = mc_profile_dir(profile)
        if not d:
            fail(f"Modrinth profile {profile!r} not found — cannot install")
        assert d is not None
        dest = d / "mods" / jar.name
        shutil.copy(jar, dest)
        out["installed"] = str(dest)
    return out


def launch_plan(profile: str = MC_PROFILE_DEFAULT, port: int = BRIDGE_PORT_DEFAULT,
                with_minecraft: bool = True, with_overlay: bool = True,
                extra_game_args: str = "") -> list[str]:
    game = skyrim_dir()
    lines = [
        f"game: {game or '(NOT FOUND — install Skyrim SE, appid 489830)'}",
        f"bridge: hw bridge serve --port {port} --log takes/skycraft-bridge.jsonl (background)",
    ]
    if with_minecraft:
        d = mc_profile_dir(profile)
        lines.append(f"minecraft: Modrinth profile {profile!r} -> "
                     f"{d or '(NOT FOUND)'} (headless-ish, skycraft world)")
    else:
        lines.append("minecraft: skipped (--no-minecraft)")
    if with_overlay:
        lines.append("overlay: compositor (hw composite + hw shade grade) -> borderless window")
    else:
        lines.append("overlay: skipped (--no-overlay)")
    skse = skyrim_dir() and ((skyrim_dir() or Path()) / "skse64_loader.exe").exists()
    lines.append(f"skyrim: {'SKSE loader (skse64_loader.exe in Proton)' if skse else 'Steam default (no SKSE found)'}"
                 + (f" {extra_game_args}" if extra_game_args else ""))
    return lines


def launch(profile: str = MC_PROFILE_DEFAULT, port: int = BRIDGE_PORT_DEFAULT,
           with_minecraft: bool = True, with_overlay: bool = True,
           dry_run: bool = False, as_steam_wrapper: bool = False,
           steam_args: list[str] | None = None, use_skse: bool = True) -> int:
    """Full auto-launch.

    SKSE mode (default when skse64_loader.exe exists): back up saves, then run
    Skyrim through SKSE under the SkyCraft-compatible Proton (9.0 — the plugin
    fails its Load check under Experimental). The SKSE plugin starts its own
    Minecraft (Prism in the prefix) by itself; no bridge/overlay services are
    needed. With as_steam_wrapper=True this REPLACES Steam's %command% (Steam
    tracks the wrapper while it waits on the game).
    Legacy bridge mode (--no-skse): background hw bridge + Modrinth note +
    overlay probe, then exec Steam's command (or open the Steam URL).
    """
    from hw import backup
    game = skyrim_dir()
    if not dry_run and not game:
        from hw.common import fail
        fail("Skyrim SE install not found (Steam appid 489830).")
    skse_mode = bool(use_skse and skse_loader())
    if skse_mode:
        return _launch_skse(dry_run, as_steam_wrapper, steam_args or [])
    if not dry_run:
        try:
            saves = Path.home() / ".local" / "share" / "Steam" / "steamapps" / \
                "compatdata" / APPID / "pfx" / "drive_c" / "users" / \
                "steamuser" / "Documents" / "My Games" / "Skyrim Special Edition" / "Saves"
            if saves.exists():
                backup.create(str(saves), "skyrim-saves-before-skycraft-launch")
                print(f"saves backed up from {saves}")
        except Exception as e:
            print(f"note: save backup skipped ({e})")
    plan = launch_plan(profile, port, with_minecraft, with_overlay)
    if dry_run and not as_steam_wrapper:
        print("auto-launch plan (dry run — nothing started):")
        for ln in plan:
            print("  " + ln)
        return 0
    root = _kit_root()
    procs: list[subprocess.Popen] = []
    # 1. bridge broker
    broker_log = Path.cwd() / "takes" / "skycraft-bridge.jsonl"
    broker_log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "hw", "bridge", "serve", "--port", str(port),
           "--log", str(broker_log)]
    print("+ " + " ".join(cmd) + " &")
    if not dry_run:
        procs.append(subprocess.Popen(cmd, cwd=str(root)))
        time.sleep(0.5)
    # 2. minecraft (Modrinth profile, detached)
    if with_minecraft and not dry_run:
        mc_cmd = modrinth_launch_cmd(profile)
        if mc_cmd:
            print("+ " + " ".join(mc_cmd) + " &")
            try:
                procs.append(subprocess.Popen(mc_cmd))
            except OSError as e:
                print(f"note: minecraft start failed ({e}); continue without it")
        else:
            print("note: no Modrinth launcher found; start the "
                  f"{profile!r} profile by hand")
    # 3. overlay compositor daemon
    if with_overlay and not dry_run:
        ov = [sys.executable, "-m", "hw", "composite", "demo", "--out",
              str(Path.cwd() / "takes" / "skycraft-overlay-probe")]
        print("+ overlay probe: " + " ".join(ov))
        subprocess.run(ov, capture_output=True, timeout=120)
    if as_steam_wrapper:
        assert steam_args is not None
        print("+ exec steam command: " + " ".join(steam_args))
        if dry_run:
            print("(dry run — not exec'ing)")
            return 0
        os.execvp(steam_args[0], steam_args)
        return 0  # unreachable
    # standalone: start Skyrim via Steam URL (non-blocking), services stay up
    if not dry_run:
        url = f"steam://rungameid/{APPID}"
        print(f"+ launching Skyrim via Steam ({url}); services stay up. "
              f"Ctrl-C stops the wrapper (game keeps running).")
        try:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError:
            print("note: xdg-open missing — start Skyrim from Steam by hand")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("stopping background services...")
            for pr in procs:
                try:
                    pr.terminate()
                except OSError:
                    pass
    return 0


def skse_loader() -> Path | None:
    """skse64_loader.exe in the Steam install, if SKSE is installed."""
    game = skyrim_dir()
    if game and (game / "skse64_loader.exe").exists():
        return game / "skse64_loader.exe"
    return None


def skse_proton_cmd() -> list[str]:
    """`proton run skse64_loader.exe` under the SkyCraft-compatible Proton."""
    from hw import proton
    from hw.common import fail
    loader = skse_loader()
    if not loader:
        fail("no skse64_loader.exe next to SkyrimSE.exe (install SKSE64 first)")
    game = skyrim_dir()
    assert game is not None
    cmd = proton.proton_run_cmd(APPID, [str(loader)], prefer=SKSE_PROTON_PREFER)
    return cmd


def _launch_skse(dry_run: bool, as_steam_wrapper: bool,
                 steam_args: list[str]) -> int:
    """Run Skyrim through SKSE under Proton 9.0 (foreground, waits on the game)."""
    from hw import backup, proton
    from hw.common import fail
    game = skyrim_dir()
    assert game is not None
    if not dry_run:
        try:
            saves = Path.home() / ".local" / "share" / "Steam" / "steamapps" / \
                "compatdata" / APPID / "pfx" / "drive_c" / "users" / \
                "steamuser" / "Documents" / "My Games" / "Skyrim Special Edition" / "Saves"
            if saves.exists():
                backup.create(str(saves), "skyrim-saves-before-skycraft-launch")
                print(f"saves backed up from {saves}")
        except Exception as e:
            print(f"note: save backup skipped ({e})")
    cmd = skse_proton_cmd()
    env = proton.run_env(APPID)
    print("SKSE mode: the SkyCraft plugin starts its own Minecraft; "
          "no bridge/overlay services needed.")
    print("+ (cwd {}) {}".format(game, " ".join(cmd)))
    if as_steam_wrapper and steam_args:
        print("(Steam's %command% is superseded by the SKSE launch above; "
              "Steam tracks this wrapper while it waits.)")
    if dry_run:
        print("(dry run — not launching)")
        return 0
    r = subprocess.run(cmd, cwd=str(game), env=env)
    return r.returncode


def pe_file_version(path: str | Path) -> tuple[int, ...]:
    """(major, minor, build, rev) from a PE's FileVersion string, or () if unreadable."""
    import re
    try:
        d = Path(path).read_bytes()
    except OSError:
        return ()
    i = d.find("FileVersion".encode("utf-16le"))
    if i < 0:
        return ()
    m = re.search(rb"((?:\d+\.)+\d+)", d[i:i + 200].decode("utf-16le", "replace").encode())
    if not m:
        return ()
    try:
        return tuple(int(x) for x in m.group(1).decode().split("."))
    except ValueError:
        return ()


def _wine_binary() -> Path | None:
    from hw import proton
    home = proton.steam_home()
    if not home:
        return None
    for name in ("Proton - Experimental", "Proton 9.0 (Beta)"):
        cand = home / "steamapps" / "common" / name / "files" / "bin" / "wine"
        if cand.exists():
            return cand
    return None


def _wine_env(prefix: Path) -> dict:
    from hw import proton
    env = dict(os.environ)
    env["WINEPREFIX"] = str(prefix)
    home = proton.steam_home()
    if home:
        env["STEAM_COMPAT_DATA_PATH"] = str(
            home / "steamapps" / "compatdata" / APPID)
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = str(home)
    return env


def prefix_state(prefix: Path | None = None) -> dict:
    """Check the three manual prefix fixes. Pure reads (safe anytime)."""
    from hw import proton
    pfx = prefix or proton.prefix_dir(APPID)
    out: dict = {"prefix": str(pfx) if pfx else "", "msvcp": (),
                 "d3dcompiler_ok": False, "override_ok": False}
    if not pfx:
        return out
    out["msvcp"] = pe_file_version(pfx / "drive_c" / "windows" / "system32" / "msvcp140.dll")
    import hashlib
    cache = Path.home() / ".cache" / "winetricks" / "d3dcompiler_47"
    ok = True
    for sysdir, cached in (("system32", cache / "d3dcompiler_47.dll"),
                           ("syswow64", cache / "d3dcompiler_47_32.dll")):
        target = pfx / "drive_c" / "windows" / sysdir / "d3dcompiler_47.dll"
        try:
            if not cached.exists() or not target.exists():
                ok = False
                break
            if hashlib.md5(target.read_bytes()).hexdigest() != \
                    hashlib.md5(cached.read_bytes()).hexdigest():
                ok = False
                break
        except OSError:
            ok = False
            break
    out["d3dcompiler_ok"] = ok
    try:
        text = (pfx / "user.reg").read_text(errors="replace")
        out["override_ok"] = '"d3dcompiler_47"="native,builtin"' in text
    except OSError:
        pass
    return out


def fix_prefix(dry_run: bool = False) -> dict:
    """Re-apply prefix fixes Steam/Proton repairs wipe: current VC++ runtime,
    native d3dcompiler_47 + override. Idempotent. Refuses while the game runs."""
    from hw import proton
    from hw.common import fail
    import hashlib
    import shutil as _shutil
    pfx = proton.prefix_dir(APPID)
    if not pfx:
        fail("no Proton prefix for 489830 (launch Skyrim once from Steam first)")
    assert pfx is not None
    rep: dict = {"fixed": [], "ok": [], "prefix": str(pfx)}
    if list(pfx.parent.glob("*/pfx")):
        pass
    procs = subprocess.run(["pgrep", "-f", "SkyrimSE\\.exe"],
                           capture_output=True, text=True)
    if procs.stdout.strip():
        fail("quit Skyrim first (prefix surgery while the game runs risks corruption)")
    st = prefix_state(pfx)
    # 1. VC++ runtime: need 14.40+ (VS2026-built DLL dies on the 2016 14.0 CRT)
    if len(st["msvcp"]) >= 2 and st["msvcp"][:2] >= (14, 40):
        rep["ok"].append(f"msvcp140 {'.'.join(map(str, st['msvcp']))}")
    else:
        redist = None
        for cand in (Path.home() / ".cache" / "winetricks" / "vcrun2022" / "vc_redist.x64.exe",
                     Path("/tmp/opencode/vc_redist-latest-x64.exe")):
            if cand.exists():
                redist = cand
                break
        if not redist:
            fail("no vc_redist.x64.exe cached (expected in ~/.cache/winetricks/vcrun2022/)")
        assert redist is not None
        if dry_run:
            rep["fixed"].append(f"would install {redist.name} (msvcp now {st['msvcp'] or 'missing'})")
        else:
            wine = _wine_binary()
            if not wine:
                fail("no Proton wine binary found to run the installer")
            print(f"installing {redist.name} into the prefix (2-3 min, one time)...")
            r = subprocess.run([str(wine), str(redist), "/install", "/quiet", "/norestart"],
                               capture_output=True, text=True, timeout=600,
                               env=_wine_env(pfx))
            if r.returncode != 0:
                fail(f"redist installer exited {r.returncode}: {(r.stderr or '')[-500:]}")
            rep["fixed"].append(f"vc_redist installed (msvcp was {st['msvcp'] or 'missing'})")
    # 2. d3dcompiler_47 files
    cache = Path.home() / ".cache" / "winetricks" / "d3dcompiler_47"
    if st["d3dcompiler_ok"]:
        rep["ok"].append("d3dcompiler_47 files match cache")
    elif dry_run:
        rep["fixed"].append("would copy d3dcompiler_47 system32+syswow64")
    else:
        for sysdir, cached in (("system32", cache / "d3dcompiler_47.dll"),
                               ("syswow64", cache / "d3dcompiler_47_32.dll")):
            _shutil.copy(cached, pfx / "drive_c" / "windows" / sysdir / "d3dcompiler_47.dll")
        rep["fixed"].append("d3dcompiler_47 system32+syswow64 restored")
    # 3. override via wine reg (transactional, safe)
    if st["override_ok"]:
        rep["ok"].append("d3dcompiler_47 override present")
    elif dry_run:
        rep["fixed"].append("would set d3dcompiler_47=native,builtin override")
    else:
        wine = _wine_binary()
        if not wine:
            fail("no Proton wine binary found for reg edit")
        r = subprocess.run(
            [str(wine), "reg", "add", r"HKCU\Software\Wine\DllOverrides",
             "/v", "d3dcompiler_47", "/t", "REG_SZ", "/d", "native,builtin", "/f"],
            capture_output=True, text=True, timeout=120, env=_wine_env(pfx))
        if r.returncode != 0:
            fail(f"reg add failed: {(r.stderr or '')[-500:]}")
        rep["fixed"].append("d3dcompiler_47 override set")
    return rep


def modrinth_launch_cmd(profile: str = MC_PROFILE_DEFAULT) -> list[str] | None:
    """Best-effort Modrinth App launch for a profile (flatpak CLI when present)."""
    if shutil.which("flatpak"):
        # Modrinth App exposes no stable CLI deep-link; open the app so the
        # user one-clicks Play on the profile (documented in the skill).
        return ["flatpak", "run", "com.modrinth.ModrinthApp"]
    if shutil.which("modrinth-app"):
        return ["modrinth-app"]
    return None


def register(sub):
    p = sub.add_parser("skyrim", help="Skyrim SE on Linux: status, install, auto-launch")
    sp = p.add_subparsers(dest="cmd", metavar="<cmd>")
    from hw.mcwine import register_into as _mcwine_into
    _mcwine_into(sp)

    q = sp.add_parser("status", help="one screen: game, skse, skycraft, profile, proton")
    q.add_argument("--profile", default=MC_PROFILE_DEFAULT)
    q.set_defaults(func=lambda a: _r_status(a))

    q = sp.add_parser("doctor", help="what is missing + exact fixes")
    q.add_argument("--profile", default=MC_PROFILE_DEFAULT)
    q.set_defaults(func=lambda a: _r_doctor(a))

    q = sp.add_parser("install-skycraft", help="install the Linux-safe SkyCraft half")
    q.add_argument("--source", required=True, help="SkyCraft source dir (has fabric/, skse/)")
    q.add_argument("--profile", default=MC_PROFILE_DEFAULT)
    q.add_argument("--port", type=int, default=BRIDGE_PORT_DEFAULT)
    q.add_argument("--diagnostics", type=int, default=0)
    q.set_defaults(func=_r_install)

    q = sp.add_parser("build-fabric", help="Gradle-build the SkyCraft Fabric jar")
    q.add_argument("--source", required=True)
    q.add_argument("--profile", default=MC_PROFILE_DEFAULT)
    q.add_argument("--install", action="store_true")
    q.set_defaults(func=_r_build)

    q = sp.add_parser("fix-prefix", help="re-apply prefix fixes Steam repairs wipe (VC++/d3dcompiler)")
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(func=_r_fixprefix)

    q = sp.add_parser("launch", help="auto-launch: SKSE (+ its Minecraft) or legacy bridge mode")
    q.add_argument("--profile", default=MC_PROFILE_DEFAULT)
    q.add_argument("--port", type=int, default=BRIDGE_PORT_DEFAULT)
    q.add_argument("--no-minecraft", action="store_true")
    q.add_argument("--no-overlay", action="store_true")
    q.add_argument("--dry-run", action="store_true")
    q.add_argument("--as-steam-wrapper", action="store_true",
                   help="SKSE mode: run the game here (Steam tracks the wrapper); "
                        "legacy mode: background services, then exec remaining args (Steam %%command%%)")
    q.add_argument("--use-skse", dest="use_skse", action="store_true", default=True,
                   help="run through SKSE under Proton 9.0 (default when skse64_loader.exe exists)")
    q.add_argument("--no-skse", dest="use_skse", action="store_false",
                   help="legacy bridge mode even when SKSE exists")
    q.add_argument("steam_args", nargs=argparse.REMAINDER)
    q.set_defaults(func=_r_launch)
    p.set_defaults(func=lambda a: p.print_help())


def _r_status(a: argparse.Namespace):
    import json
    st = status(a.profile)
    g = st["game_dir"] or "(not found)"
    print(f"game:    {g}")
    print(f"  exe={'yes' if st['game_exe'] else 'no'} "
          f"skse_loader={'yes' if st['skse']['loader'] else 'no'} "
          f"skse_dll={'yes' if st['skse']['dll'] else 'no'} "
          f"addrbins={st['addresslib']['bins']} "
          f"skycraft_ini={'yes' if st['skycraft']['ini'] else 'no'}"
          + (" (linux)" if st['skycraft']['linux_ini'] else ""))
    print(f"proton:  prefix={st['proton_prefix'] or '(none — launch once from Steam)'} "
          f"ver={st['proton_version'] or '?'} "
          f"compat={st.get('compat_tool') or 'Steam default (Experimental — correct)'}")
    print(f"java:    {st['java'] or '(not found — need Java 25)'}")
    fp = st["fabric_profile"]
    print(f"profile: {a.profile!r} -> {fp['dir'] or '(NOT FOUND)'}")
    if fp["dir"]:
        print(f"  fabric_api={'yes' if fp['fabric_api'] else 'no'} "
              f"skycraft_jar={fp['skycraft_jar'] or '(none)'} "
              f"disabled_mods={fp['mods_disabled']} saves={fp['saves'] or []}")
        if fp.get("game_version") or fp.get("loader_version"):
            print(f"  mc={fp.get('game_version') or '?'} "
                  f"loader={fp.get('loader') or '?'} {fp.get('loader_version') or ''}".rstrip())
    print(f"wrapper: {st['wrapper']['script']} "
          f"({'ready' if st['wrapper']['executable'] else 'missing'})")
    _ = json


def _r_doctor(a: argparse.Namespace):
    st = status(a.profile)
    fixes = doctor_fixes(st)
    if not fixes:
        print("doctor: everything needed is present. Launch with "
              "`hw skyrim launch --dry-run` first, then for real.")
        return
    print("doctor: missing / to fix:")
    for f in fixes:
        print("  - " + f)


def _r_install(a: argparse.Namespace):
    import json
    print(json.dumps(install_skycraft(a.source, a.profile, a.port, a.diagnostics), indent=2))


def _r_build(a: argparse.Namespace):
    import json
    print(json.dumps(build_fabric(a.source, a.install, a.profile), indent=2))


def _r_launch(a: argparse.Namespace):
    rest = [x for x in (a.steam_args or []) if x != "--"]
    raise SystemExit(launch(a.profile, a.port, not a.no_minecraft,
                            not a.no_overlay, a.dry_run, a.as_steam_wrapper, rest,
                            a.use_skse))
