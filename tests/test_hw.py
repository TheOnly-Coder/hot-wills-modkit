"""Offline tests: no games, no GPU, no display, no network, no API key.

    HW_NO_UV=1 python3 -m pytest -q tests
"""
import ast
import filecmp
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from hw import asset, backup, bridge, capture, composite, kb, mcwine, minidump, proton, publish, scan, shade, skyrim  # noqa: E402


# ------------------------------------------------------------------ helpers

def make(root: Path, files: dict):
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode())


def png(path: Path, size=(64, 48), color=(10, 200, 30), alpha=False):
    img = Image.new("RGBA" if alpha else "RGB", size, color + ((255,) if alpha else ()))
    img.save(path)
    return path


# ---------------------------------------------------------------------- scan

def engine_of(tmp_path, files):
    make(tmp_path, files)
    hits, _ = scan.detect(scan.Index(tmp_path))
    assert hits, "no engine detected"
    return hits[0][0], hits[0][3]


def test_unity_mono_and_version(tmp_path):
    key, det = engine_of(tmp_path, {
        "UnityPlayer.dll": b"MZ", "Game_Data/Managed/Assembly-CSharp.dll": b"MZ",
        "Game_Data/globalgamemanagers": b"\0" * 20 + b"2022.3.21f1\0" + b"\0" * 100,
        "Game_Data/app.info": "Studio\nCoolGame",
    })
    assert key == "unity-mono"
    assert det["version"] == "2022.3.21f1" and det["product"] == "CoolGame"


def test_unity_il2cpp(tmp_path):
    key, _ = engine_of(tmp_path, {"UnityPlayer.dll": b"MZ", "GameAssembly.dll": b"MZ",
                                  "Game_Data/il2cpp_data/Metadata/global-metadata.dat": b"\xaf\x1b\xb1\xfa"})
    assert key == "unity-il2cpp"


def test_godot_pck(tmp_path):
    key, det = engine_of(tmp_path, {"game.exe": b"MZ", "game.pck": b"GDPC" + struct.pack("<4I", 2, 4, 2, 1)})
    assert key == "godot" and det["version"].startswith("4.2.1")


def test_bethesda_plugins(tmp_path):
    key, det = engine_of(tmp_path, {"SkyrimSE.exe": b"MZ", "Data/Skyrim.esm": b"TES4",
                                    "Data/Skyrim - Textures0.bsa": b"BSA"})
    assert key == "bethesda" and det["plugins"] == 1


def test_managed_pe(tmp_path):
    pe = bytearray(1024)
    pe[0:2] = b"MZ"
    struct.pack_into("<I", pe, 0x3C, 0x80)
    pe[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", pe, 0x84, 0x14C)
    opt = 0x80 + 24
    struct.pack_into("<H", pe, opt, 0x10B)
    struct.pack_into("<II", pe, opt + 96 + 14 * 8, 0x2000, 0x48)
    p = tmp_path / "Game.exe"
    p.write_bytes(bytes(pe))
    assert scan.pe_info(p) == {"arch": "x86", "managed": True}


def test_vdf():
    d = scan._vdf('"AppState" { "appid" "105600" "name" "Terraria" "installdir" "Terraria" }')
    assert d["AppState"]["installdir"] == "Terraria"


def test_report_on_folder(tmp_path):
    make(tmp_path, {"UnityPlayer.so": b"ELF", "G_Data/Managed/Assembly-CSharp.dll": b"x"})
    rep = scan.report(str(tmp_path))
    assert rep and rep["routes"]


# -------------------------------------------------------------------- bridge

def test_bridge_validate_ok():
    assert bridge.validate(bridge.make("cam", pos=[1, 2, 3], yaw=90.0, pitch=0.0)) == []
    assert bridge.validate(bridge.make("hello", game="g", role="host")) == []
    assert bridge.validate(bridge.make("event", kind="explosion", at=[0, 0, 0])) == []
    assert bridge.validate(bridge.make("bye")) == []


def test_bridge_validate_bad():
    assert bridge.validate({"t": "cam", "pos": [1, 2]})  # missing yaw/pitch, short pos
    assert bridge.validate({"t": "nope", "v": 1})
    assert bridge.validate(bridge.make("hello", game="g", role="admin"))
    assert bridge.validate(bridge.make("event", kind="nuke-the-moon"))
    assert bridge.validate("not a dict")


def test_bridge_encode_decode_roundtrip():
    msg = bridge.make("ground", cols=[[1, 2, 3.0]], stamp=123)
    back, errs = bridge.decode_line(bridge.encode(msg))
    assert not errs and back == msg


def test_bridge_decode_bad_json():
    msg, errs = bridge.decode_line(b"{oops")
    assert msg is None and errs


def test_bridge_contract():
    text = bridge.CONTRACT_TEMPLATE.format(host="H", guest="G", port=27431, dropdir="d")
    assert bridge.check_contract(text) == []
    assert bridge.check_contract("# empty")  # missing headings + proto pin


def test_bridge_loopback_demo():
    res = bridge.loopback_demo()
    assert res["cam_ok"] and res["event_ok"]


# ---------------------------------------------------------------- composite

def test_composite_demo_proof(tmp_path):
    s = composite.demo_scene()
    out = composite.composite(s["host"], s["host_d"], s["guest"], s["guest_d"],
                              overlay=s["overlay"])
    assert composite.demo_checks(out, s) == []
    Image.fromarray(out).save(tmp_path / "out.png")


def test_composite_near_wins_far_loses():
    host = np.full((8, 8, 3), 50, np.uint8)
    host_d = np.full((8, 8), 100.0)
    guest = np.zeros((8, 8, 4), np.uint8)
    guest[..., :3] = (0, 255, 0)
    guest[..., 3] = 255
    near = composite.composite(host, host_d, guest, np.full((8, 8), 10.0), soften=False)
    assert (near[..., 1].mean() > 200)  # guest nearer -> green wins
    far = composite.composite(host, host_d, guest, np.full((8, 8), 500.0), soften=False)
    assert (far[..., 1].mean() < 100)  # guest farther -> host wins


def test_composite_overlay_always_on_top():
    host = np.zeros((8, 8, 3), np.uint8)
    guest = np.zeros((8, 8, 4), np.uint8)  # fully transparent guest
    overlay = np.zeros((8, 8, 4), np.uint8)
    overlay[..., :3] = 255
    overlay[..., 3] = 255
    out = composite.composite(host, np.full((8, 8), 1.0), guest,
                              np.full((8, 8), 999.0), overlay=overlay)
    assert out.mean() > 200


def test_composite_shift_moves_guest():
    host = np.zeros((10, 20, 3), np.uint8)
    guest = np.zeros((10, 20, 4), np.uint8)
    guest[:, :4, :3] = 255
    guest[:, :4, 3] = 255
    out = composite.composite(host, np.full((10, 20), 100.0), guest,
                              np.full((10, 20), 1.0), shift=(6, 0), soften=False)
    assert out[:, 6:10].mean() > 200 and out[:, :4].mean() < 50


# --------------------------------------------------------------------- asset

def test_asset_cutout_fit_pixelate(tmp_path):
    src = png(tmp_path / "raw.png", color=(0, 255, 0))
    # green border median -> keyed out; draw a red square first
    img = Image.open(src)
    px = img.load()
    for x in range(20, 40):
        for y in range(10, 30):
            px[x, y] = (200, 30, 30)
    img.save(src)
    asset.cutout(src, tmp_path / "cut.png")
    cut = Image.open(tmp_path / "cut.png")
    assert cut.mode == "RGBA" and cut.getpixel((0, 0))[3] == 0 and cut.getpixel((25, 15))[3] == 255
    asset.fit(tmp_path / "cut.png", tmp_path / "s.png", "32x32")
    assert Image.open(tmp_path / "s.png").size == (32, 32)
    asset.pixelate(src, tmp_path / "px.png", px=4)
    assert Image.open(tmp_path / "px.png").size == (64, 48)


def test_asset_palette_sheet_slice(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    for i in range(3):
        png(frames / f"f{i}.png", size=(16, 16), color=(i * 40, 100, 200))
    asset.palette(frames / "f0.png", tmp_path / "pal.png", colors=4)
    assert Image.open(tmp_path / "pal.png").size == (16, 16)
    meta = asset.sheet(frames, tmp_path / "sheet.png", tmp_path / "sheet.json", cols=2)
    assert len(meta["frames"]) == 3 and (tmp_path / "sheet.json").exists()
    paths = asset.slice_sheet(tmp_path / "sheet.png", tmp_path / "back", "16x16")
    assert len(paths) == 4  # 2 cols x 2 rows


# -------------------------------------------------------------------- backup

def test_backup_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "STORE", tmp_path / "store")
    game = tmp_path / "saves"
    make(game, {"slot1.dat": "hello", "sub/slot2.dat": "world"})
    backup.create(game, "t")
    assert backup.diff(game, "t") == {"added": [], "removed": [], "changed": []}
    (game / "slot1.dat").write_text("changed")
    (game / "new.dat").write_text("new")
    d = backup.diff(game, "t")
    assert d["changed"] == ["slot1.dat"] and d["added"] == ["new.dat"]
    backup.restore(game, "t")
    assert (game / "slot1.dat").read_text() == "hello"
    assert not (game / "new.dat").exists()


# ------------------------------------------------------------------- publish

def test_publish_blocks_bad_mod(tmp_path):
    bad = tmp_path / "bad"
    make(bad, {"README.md": "hi", "data.pak": "x" * 10, "key.txt": "token sk-abcdefghij1234567890"})
    errs = publish.check(bad)
    assert any("game file" in e for e in errs) and any("key" in e.lower() or "secret" in e.lower()
                                                      or "possible" in e for e in errs)


def test_publish_passes_clean_mod(tmp_path):
    good = tmp_path / "good"
    make(good, {"README.md": "# install\nsteps", "mod.py": "print('hi')"})
    assert publish.check(good) == []
    make(good, {})  # empty extra write is fine
    assert publish.check(tmp_path / "missing")  # nonexistent dir fails


# ------------------------------------------------------------------------ kb

def test_kb_new_check_search(tmp_path, monkeypatch):
    monkeypatch.setattr(kb, "repo_root", lambda: tmp_path)
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "TEMPLATE.md").write_text((REPO / "knowledge" / "TEMPLATE.md").read_text())
    note = kb.new_note("Some Game", "A cool sword", "pytest")
    assert note.exists()
    assert kb.check_note(note) == []
    (tmp_path / "knowledge" / "INDEX.md").write_text("# idx")
    hits = kb.search("cool sword")
    assert hits and hits[0][0] == note


def test_kb_check_fails_bad_note(tmp_path):
    p = tmp_path / "n.md"
    p.write_text("# x\n\nnothing here\n")
    assert kb.check_note(p)


def test_kb_index(tmp_path, monkeypatch):
    monkeypatch.setattr(kb, "repo_root", lambda: tmp_path)
    (tmp_path / "knowledge" / "games" / "g").mkdir(parents=True)
    (tmp_path / "knowledge" / "games" / "g" / "n.md").write_text("# N\n")
    idx = kb.rebuild_index()
    assert "n.md" in idx.read_text()


# ------------------------------------------------------------------- capture

def test_capture_backends_shape():
    b = capture.backends()
    assert set(b) == {"shot", "record", "windows"} and all(isinstance(v, list) for v in b.values())


# ------------------------------------------------------------------- proton

def test_proton_paths_shape():
    assert proton.steam_home() is None or proton.steam_home().exists()
    assert isinstance(proton.proton_builds(), list)
    d = proton.doctor("489830")
    assert d["appid"] == "489830" and "builds" in d and "prefix" in d


def test_proton_run_cmd_picks_build():
    if not proton.steam_home() or not proton.proton_builds():
        pytest.skip("no Steam/Proton on this box")
    cmd = proton.proton_run_cmd("489830", ["notepad.exe"])
    assert cmd[0].endswith("proton") and cmd[1] == "run" and "notepad.exe" in cmd


def test_proton_pick_build_prefers_substring():
    if not proton.proton_builds():
        pytest.skip("no Proton builds on this box")
    b = proton.pick_build("definitely-not-a-proton")
    assert b is not None  # falls back to Experimental/last
    names = [x["name"] for x in proton.proton_builds()]
    for want in names:
        got = proton.pick_build(want[:8])
        assert got is not None


def test_proton_compat_tool_shape():
    assert isinstance(proton.compat_tool("489830"), str)


# ------------------------------------------------------------------- shade

def test_shade_presets_known():
    assert "skyrim-day" in shade.PRESETS and "neutral" in shade.PRESETS


def test_shade_neutral_lossless_and_day_visible():
    s = composite.demo_scene()
    assert shade.demo_checks(
        s["host"], shade.apply_chain(s["host"], **shade.PRESETS["neutral"]), "neutral") == []
    graded = shade.apply_chain(s["host"], **shade.PRESETS["skyrim-day"])
    assert shade.demo_checks(s["host"], graded, "skyrim-day") == []


def test_shade_grade_keeps_shape_and_alpha():
    s = composite.demo_scene()
    g = shade.grade_guest_to_host(s["guest"], s["host"])
    assert g.shape == s["guest"].shape and g.dtype == np.uint8


# ------------------------------------------------------------------- skyrim

def test_skyrim_mapping_math():
    sys.path.insert(0, str(REPO / "adapters" / "python"))
    import skycraft_host_daemon as daemon
    pos, yaw, pitch = daemon.skyrim_to_bridge(70.0, -140.0, 210.0, 30.0, -10.0)
    assert pos == [1.0, 3.0, 2.0]  # mc.x = x/70, mc.y = z/70, mc.z = -y/70
    assert yaw == 150.0 and pitch == 10.0


def test_skyrim_status_shape():
    st = skyrim.status()
    for k in ("game_dir", "skse", "addresslib", "skycraft", "proton_prefix",
              "java", "fabric_profile", "wrapper", "compat_tool", "skse_proton"):
        assert k in st


def test_skyrim_launch_dry_run():
    assert skyrim.launch(dry_run=True) == 0
    assert skyrim.launch(dry_run=True, as_steam_wrapper=True, steam_args=["true"]) == 0
    assert skyrim.launch(dry_run=True, use_skse=False) == 0


def test_skyrim_contract_checks():
    text = (REPO / "examples" / "skyrim-skycraft-linux" / "docs" / "CONTRACT.md").read_text()
    assert bridge.check_contract(text) == []


# ------------------------------------------------------------------ adapters

def test_python_adapter_stdlib_only():
    stdlib = {"json", "socket", "time", "__future__", "typing", "argparse",
              "math", "os", "re", "socket", "sys"}
    for rel in ("adapters/python/bridge_client.py",
                "adapters/python/skycraft_host_daemon.py",
                "examples/skyrim-skycraft-linux/guest_stub.py"):
        src = (REPO / rel).read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name.split(".")[0] in stdlib, f"{rel}: non-stdlib import: {a.name}"
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] in stdlib, f"{rel}: non-stdlib import"


# --------------------------------------------------------------------- clips

def test_cli_help_all_groups():
    for g in ["scan", "bridge", "composite", "capture", "asset", "backup", "publish", "kb",
              "proton", "skyrim", "shade", "minidump"]:
        r = subprocess.run([sys.executable, "-m", "hw", g, "--help"],
                           capture_output=True, cwd=REPO, timeout=60)
        assert r.returncode == 0, f"hw {g} --help failed"


# --------------------------------------------------------------------- sync

def _tree_files(root: Path):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def test_skill_copies_in_sync():
    src = _tree_files(REPO / "skills")
    assert src, "no skills found"
    for copy in (REPO / ".agents" / "skills", REPO / ".claude" / "skills"):
        dup = _tree_files(copy)
        assert set(dup) == set(src), f"{copy} file list differs from skills/"
        for rel, data in src.items():
            assert dup[rel] == data, f"{copy}/{rel} differs from skills/{rel}"
    # every SKILL.md has Agent Skills frontmatter
    for rel in src:
        if rel.endswith("SKILL.md"):
            text = src[rel].decode()
            assert text.startswith("---") and "name:" in text.split("---")[1] \
                and "description:" in text.split("---")[1], f"{rel} missing frontmatter"


def test_playbooks_referenced_exist():
    import re
    for skill_md in (REPO / "skills").rglob("SKILL.md"):
        text = skill_md.read_text()
        for m in re.findall(r"`(skills/[^`]+?)`", text):
            if "<" in m or ">" in m:
                continue  # placeholder, e.g. <engine>
            assert (REPO / m).exists(), f"{skill_md}: dangling reference {m}"
    for pb in ["unity.md", "unreal.md", "godot.md", "source.md", "native.md", "dotnet-xna.md",
               "bethesda.md", "big-frameworks.md", "misc-engines.md", "minecraft.md",
               "genie-aoe2.md", "retro-decomp.md"]:
        assert (REPO / "skills" / "mod-any-game" / "references" / "engines" / pb).exists()
    assert (REPO / "adapters" / "python" / "bridge_client.py").exists()
    assert (REPO / "examples" / "linux-passthrough-minimal" / "run_demo.sh").exists()
    assert (REPO / "examples" / "skyrim-skycraft-linux" / "run_demo.sh").exists()
    assert (REPO / "bin" / "skycraft-autolaunch.sh").exists()
    assert (REPO / "bin" / "skycraft-graphics.sh").exists()
    assert json.loads((REPO / "plugin.json").read_text())["name"] == "hot-wills-modkit"
    assert json.loads((REPO / "opencode.json").read_text())["skills"]["paths"] == ["skills"]


# ------------------------------------------------------------------- mcwine

def test_mcwine_rules():
    assert mcwine.rules_allow(None)
    assert mcwine.rules_allow([{"action": "allow"}])
    assert mcwine.rules_allow([{"action": "allow", "os": {"name": "windows"}}])
    assert not mcwine.rules_allow([{"action": "allow", "os": {"name": "osx"}}])
    assert not mcwine.rules_allow([{"action": "disallow", "os": {"name": "windows"}}])
    assert not mcwine.rules_allow([{"action": "allow", "features": {"is_demo_user": True}}])


def test_mcwine_select_entries():
    libs = [
        {"name": "a:b:1", "downloads": {"artifact": {"path": "a/b/1/b-1.jar"}}},
        {"name": "c:d:1:natives-windows",
         "downloads": {"artifact": {"path": "c/d/1/d-1-natives-windows.jar"}}},
        {"name": "e:f:1:natives-linux",
         "downloads": {"artifact": {"path": "e/f/1/e-1-natives-linux.jar"}}},
        {"name": "g:h:1:natives-windows-arm64",
         "downloads": {"artifact": {"path": "g/h/1/g-1.jar"}}},
        {"name": "i:j:1", "rules": [{"action": "allow", "os": {"name": "osx"}}],
         "downloads": {"artifact": {"path": "i/j/1/j-1.jar"}}},
    ]
    cp, nat = mcwine.select_entries(libs)
    assert [x["name"] for x in cp] == ["a:b:1"]
    assert [x["name"] for x in nat] == ["c:d:1:natives-windows"]


def test_mcwine_paths_and_bat():
    assert mcwine.dashless_uuid("DF9196FD-C378-4B88-9838-325703078FFE") == \
        "df9196fdc3784b889838325703078ffe"
    assert mcwine.maven_path("g:a:1") == "g/a/1/a-1.jar"
    assert mcwine.maven_path("g:a:1:natives-windows") == "g/a/1/a-1-natives-windows.jar"
    assert mcwine.zpath("/home/u/Fabric 26.3/x") == "Z:\\home\\u\\Fabric 26.3\\x"
    bat = mcwine.render_bat("C:\\j\\javaw.exe", ["-Xmx4G"], "C:\\a.jar;C:\\b.jar",
                            "KnotClient", ["--username", "X"])
    assert "\r\n" in bat and "javaw.exe" in bat and "KnotClient" in bat


def test_mcwine_fused_contract():
    # the real fused json must satisfy the assumptions setup() relies on
    meta = Path.home() / ".var" / "app" / "com.modrinth.ModrinthApp" / "data" / "ModrinthApp" / "meta"
    fused = meta / "versions" / "26.3-0.19.5" / "26.3-0.19.5.json"
    if not fused.exists():
        pytest.skip("no Modrinth meta on this box")
    j = json.loads(fused.read_text())
    assert j["mainClass"].endswith("KnotClient")
    cp, nat = mcwine.select_entries(j["libraries"])
    assert len(cp) > 40 and len(nat) >= 8
    assert all("arm64" not in x["name"] and "macos" not in x["name"].lower()
               for x in cp + nat)


# ------------------------------------------------------------------- graphics script

def test_graphics_script_idempotent(tmp_path):
    import shutil as _shutil
    src = Path("/home/user/.local/share/Steam/steamapps/compatdata/489830/pfx/drive_c/users"
               "/steamuser/Documents/My Games/Skyrim Special Edition/SkyrimPrefs.ini")
    if not src.exists():
        pytest.skip("no Skyrim prefix on this box")
    prefs = tmp_path / "SkyrimPrefs.ini"
    _shutil.copy(src, prefs)
    low = Path("/home/user/.local/share/Steam/steamapps/common/Skyrim Special Edition/Low.ini")
    env = dict(os.environ, SKYCRAFT_PREFS=str(prefs),
               SKYCRAFT_MC_OPTIONS=str(tmp_path / "no-such-options.txt"),
               SKYCRAFT_LOG=str(tmp_path / "run.log"),
               SKYCRAFT_BACKUP_BASE=str(tmp_path / "backups"),
               SKYCRAFT_RES="1920x1080", SKYCRAFT_LOWINI=str(low))
    script = REPO / "bin" / "skycraft-graphics.sh"
    r1 = subprocess.run(["bash", str(script)], capture_output=True, env=env, timeout=60)
    assert r1.returncode == 0
    before = prefs.read_bytes()
    assert b"bFull Screen=1" in before and b"iShadowMapResolution=1024" in before
    r2 = subprocess.run(["bash", str(script)], capture_output=True, env=env, timeout=60)
    assert r2.returncode == 0 and prefs.read_bytes() == before


# ------------------------------------------------------------------- minidump

def _synthetic_dump(path: Path):
    import struct as _st
    # minimal valid dump: header + dir + exception + 1 thread + 1 module
    modname = "test.dll".encode("utf-16le")
    mname_rva = 0x200
    modlist_rva = 0x100
    thlist_rva = 0x300
    exc_rva = 0x400
    ctx_rva = 0x500
    stack_rva = 0x600
    buf = bytearray(0x800)
    _st.pack_into("<IIII", buf, 0, 0x504D444D, 0xA793, 3, 0x20)
    _st.pack_into("<III", buf, 0x20, 4, 200, modlist_rva)
    _st.pack_into("<III", buf, 0x2C, 3, 200, thlist_rva)
    _st.pack_into("<III", buf, 0x38, 6, 200, exc_rva)
    _st.pack_into("<I", buf, modlist_rva, 1)
    _st.pack_into("<QIIII", buf, modlist_rva + 4, 0x180000000, 0x1000, 0, 0, mname_rva)
    _st.pack_into("<I", buf, mname_rva, len(modname))
    buf[mname_rva + 4:mname_rva + 4 + len(modname)] = modname
    _st.pack_into("<I", buf, thlist_rva, 1)
    _st.pack_into("<I", buf, thlist_rva + 4, 99)  # tid
    _st.pack_into("<QIIII", buf, thlist_rva + 4 + 24, 0x10000, 0x80, stack_rva, 0x4D0, ctx_rva)
    _st.pack_into("<I", buf, exc_rva, 99)
    _st.pack_into("<IIQQI", buf, exc_rva + 8, 0xC0000005, 0, 0, 0x180000100, 0)
    _st.pack_into("<Q", buf, ctx_rva + 0xF8, 0x180000100)
    _st.pack_into("<Q", buf, stack_rva, 0x180000200)
    path.write_bytes(bytes(buf))


def test_minidump_synthetic(tmp_path):
    p = tmp_path / "t.dmp"
    _synthetic_dump(p)
    rep = minidump.parse(p)
    assert rep["exception"]["code"] == 0xC0000005
    assert rep["fault"]["at"] == "test.dll+0x100"
    assert minidump.resolve(0x180000200, rep["modules"]) == "test.dll+0x200"
    assert minidump.resolve(0x1234, rep["modules"]) == "???"


def test_minidump_real_crash_shape():
    p = Path("/home/user/.local/share/Steam/steamapps/compatdata/489830/pfx/drive_c/users"
             "/steamuser/Documents/My Games/Skyrim Special Edition/SKSE/SkyCraft_crash.dmp")
    if not p.exists():
        pytest.skip("no real crash dump on this box")
    rep = minidump.parse(p)
    assert rep["exception"]["code"] == 0xC0000005 and len(rep["modules"]) > 10
