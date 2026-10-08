"""`hw capture`: Linux-first screenshots, window listing and recording.

No Windows-only recorder, no gfxcapture download. Tries, in order:
  screenshot: grim (Wayland) -> import/scrot/gnome-screenshot (X11) -> ffmpeg x11grab
  record:     ffmpeg x11grab + pulse audio
  windows:    swaymsg/hyprctl (Wayland) -> wmctrl/xdotool/xprop (X11)
If nothing is available it says exactly what to install, and the compositor
demo (`hw composite demo`) still works headless for pipeline testing.

Examples:
  hw capture shot --out takes/shot.png
  hw capture windows --list
  hw capture record --out takes/play.mkv --seconds 20 --audio game
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def shot(out: str, region: str | None = None) -> str:
    """Take a screenshot, return the path written. Raises SystemExit with install help."""
    from hw.common import fail
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    if _have("grim") and not region:
        rc, msg = _run(["grim", str(p)])
        if rc == 0 and p.exists():
            return str(p)
    if _have("import"):
        cmd = ["import", "-window", "root"]
        if region:
            cmd += ["-crop", region]
        cmd.append(str(p))
        rc, msg = _run(cmd)
        if rc == 0 and p.exists():
            return str(p)
    if _have("scrot") and not region:
        rc, msg = _run(["scrot", str(p)])
        if rc == 0 and p.exists():
            return str(p)
    if _have("gnome-screenshot") and not region:
        rc, msg = _run(["gnome-screenshot", "-f", str(p)])
        if rc == 0 and p.exists():
            return str(p)
    if _have("ffmpeg"):
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "x11grab", "-i", ":0.0",
               "-frames:v", "1", str(p)]
        rc, msg = _run(cmd)
        if rc == 0 and p.exists():
            return str(p)
    fail("no screenshot backend found. Install one of: grim (Wayland), "
         "ImageMagick (`import`), scrot, gnome-screenshot, or ffmpeg with x11grab. "
         "Headless pipeline tests still work: `hw composite demo`.")


def list_windows() -> list[dict]:
    wins: list[dict] = []
    if _have("swaymsg"):
        import json
        rc, msg = _run(["swaymsg", "-t", "get_tree"])
        if rc == 0:
            try:
                def walk(n):
                    if isinstance(n, dict):
                        if n.get("name") and n.get("pid"):
                            wins.append({"id": str(n.get("id")), "title": n["name"], "pid": n["pid"]})
                        for v in n.values():
                            walk(v)
                    elif isinstance(n, list):
                        for v in n:
                            walk(v)
                walk(json.loads(msg))
                return wins
            except Exception:
                pass
    if _have("wmctrl"):
        rc, msg = _run(["wmctrl", "-l", "-p"])
        if rc == 0:
            for line in msg.splitlines():
                parts = line.split(None, 3)
                if len(parts) == 4:
                    wins.append({"id": parts[0], "pid": parts[2], "title": parts[3]})
            return wins
    if _have("xdotool"):
        rc, msg = _run(["xdotool", "search", "--onlyvisible", "--name", ""])
        if rc == 0:
            for wid in msg.split():
                rc2, title = _run(["xdotool", "getwindowname", wid])
                wins.append({"id": wid, "title": title.strip(), "pid": "?"})
            return wins
    return wins


def backends() -> dict:
    return {
        "shot": [c for c in ("grim", "import", "scrot", "gnome-screenshot", "ffmpeg") if _have(c)],
        "record": ["ffmpeg"] if _have("ffmpeg") else [],
        "windows": [c for c in ("swaymsg", "wmctrl", "xdotool", "hyprctl") if _have(c)],
    }


def register(sub):
    p = sub.add_parser("capture", help="screenshots, window list, recording (Linux-first)")
    sp = p.add_subparsers(dest="cmd", metavar="<cmd>")

    q = sp.add_parser("shot", help="screenshot the desktop to a PNG")
    q.add_argument("--out", default="takes/shot.png")
    q.add_argument("--region", default=None, help="WxH+X+Y crop (X11 `import` only)")
    q.set_defaults(func=lambda a: print(shot(a.out, a.region)))

    q = sp.add_parser("windows", help="list visible windows")
    q.add_argument("--list", action="store_true")
    q.set_defaults(func=lambda a: _print_windows())

    q = sp.add_parser("backends", help="show which capture backends exist here")
    q.set_defaults(func=lambda a: print("\n".join(
        f"{k}: {', '.join(v) if v else '(none installed)'}" for k, v in backends().items())))

    q = sp.add_parser("record", help="record the desktop with ffmpeg (x11grab+pulse)")
    q.add_argument("--out", default="takes/play.mkv")
    q.add_argument("--seconds", type=float, default=20)
    q.add_argument("--size", default="1280x720")
    q.add_argument("--audio", default="game", choices=["game", "none"],
                   help="'game': monitor source (set per machine); 'none': silent")
    q.set_defaults(func=_run_record)
    p.set_defaults(func=lambda a: p.print_help())


def _print_windows():
    wins = list_windows()
    if not wins:
        print("(no window tool found: install swaymsg/wmctrl/xdotool — or pick the window by hand)")
        return
    for w in wins:
        print(f"{w['id']:>12}  pid={w['pid']!s:>8}  {w['title']}")


def _run_record(a: argparse.Namespace):
    from hw.common import fail
    if not _have("ffmpeg"):
        fail("ffmpeg not found (needed for recording). Install it from your distro, "
             "then re-run. Screenshots may still work: `hw capture backends`.")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "x11grab", "-video_size", a.size,
           "-i", ":0.0"]
    if a.audio == "game":
        cmd += ["-f", "pulse", "-i", "default"]
    cmd += ["-t", str(a.seconds), "-pix_fmt", "yuv420p", str(out)]
    print("+ " + " ".join(cmd))
    rc, msg = _run(cmd)
    if rc != 0 or not out.exists():
        fail(f"recording failed. ffmpeg said: {msg.strip()[-2000:]} "
             "(headless machine? use `hw composite demo` for pipeline tests)")
    print(f"wrote {out}")
