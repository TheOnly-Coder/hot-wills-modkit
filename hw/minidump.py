"""`hw minidump`: read Windows minidumps (.dmp) on Linux.

Crash dumps from Wine/Proton games (e.g. Skyrim SKSE plugins that write their
own .dmp on crash) are parseable with stdlib struct: exception code/address,
faulting thread's stack, and module+offset resolution — no Windows debugger,
no symbols needed (offsets are enough to match against objdump disassembly).

Examples:
  hw minidump show "Documents/My Games/Skyrim Special Edition/SKSE/SkyCraft_crash.dmp"
  hw minidump show crash.dmp --json
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

STREAM_NAMES = {2: "ModuleList", 3: "ThreadList", 4: "ModuleList", 5: "MemoryList",
                6: "Exception", 7: "SystemInfo", 9: "MemoryList",
                15: "MiscInfo", 16: "Memory64List"}


def _getstr(d: bytes, rva: int) -> str:
    if rva + 4 > len(d):
        return "?"
    (ln,) = struct.unpack_from("<I", d, rva)
    if ln > 600 or rva + 4 + ln > len(d):
        return "?"
    return d[rva + 4:rva + 4 + ln].decode("utf-16le", "replace")


def parse(path: str | Path) -> dict:
    """Parse a minidump. Returns exception, fault thread, modules. Never throws
    on truncated files — inaccessible parts become '?'."""
    from hw.common import fail
    try:
        d = Path(path).read_bytes()
    except OSError as e:
        fail(f"cannot read {path}: {e}")
        raise AssertionError("unreachable")
    if d[:4] != b"MDMP":
        fail(f"not a minidump (bad magic): {path}")
        raise AssertionError("unreachable")
    _, _, nstreams, srv = struct.unpack_from("<IIII", d, 0)
    streams: dict[int, tuple[int, int]] = {}
    for i in range(nstreams):
        try:
            st, sz, rva = struct.unpack_from("<III", d, srv + i * 12)
        except struct.error:
            break
        streams.setdefault(st, (sz, rva))
    out: dict = {"path": str(path), "exception": None, "threads": 0,
                 "modules": [], "fault": None}
    if 4 in streams:
        _, mrva = streams[4]
        try:
            nmod = struct.unpack_from("<I", d, mrva)[0]
        except struct.error:
            nmod = 0
        off = mrva + 4
        # NOTE: the textbook MINIDUMP_MODULE is 92 bytes, but real dumps
        # (dbghelp under Wine included) land on 108 here — validated by
        # scanning strides for sane entries; nonzero base required anyway.
        for _ in range(min(nmod, 500)):
            try:
                base, size, _, _, md = struct.unpack_from("<QIIII", d, off)
            except struct.error:
                break
            if not base:
                break
            name = _getstr(d, md).split("\\")[-1] or "?"
            out["modules"].append({"base": base, "size": size, "name": name})
            off += 108
    if 6 in streams:
        _, erva = streams[6]
        try:
            # MINIDUMP_EXCEPTION: tid, align, code, flags, record, address, nparams
            tid = struct.unpack_from("<I", d, erva)[0]
            code, _, _, addr, nparams = struct.unpack_from("<IIQQI", d, erva + 8)[:5]
            info0 = struct.unpack_from("<Q", d, erva + 8 + 4 + 4 + 8 + 8 + 4 + 4)[0] \
                if nparams >= 1 else 0
            out["exception"] = {"tid": tid, "code": code, "address": addr,
                                "write": bool(info0)}
        except struct.error:
            pass
    if 3 in streams and out["exception"] is not None:
        _, trva = streams[3]
        try:
            nth = struct.unpack_from("<I", d, trva)[0]
        except struct.error:
            nth = 0
        out["threads"] = nth
        off = trva + 4
        want = out["exception"]["tid"]
        for _ in range(min(nth, 500)):
            try:
                tid = struct.unpack_from("<I", d, off)[0]
                # MINIDUMP_THREAD: tid,suspend,prioclass,prio,teb(8),
                # stack{start(8),size(4),rva(4)}, ctx{size(4),rva(4)}
                st_start, st_size, st_rva, _, ctx_rva = \
                    struct.unpack_from("<QIIII", d, off + 24)
            except struct.error:
                break
            if tid == want:
                frames = []
                try:
                    rip = struct.unpack_from("<Q", d, ctx_rva + 0xF8)[0]
                    out["fault"] = {"tid": tid, "rip": rip,
                                    "at": resolve(rip, out["modules"])}
                    for k in range(16):
                        v = struct.unpack_from("<Q", d, st_rva + k * 8)[0]
                        frames.append({"sp_off": k * 8, "value": v,
                                       "at": resolve(v, out["modules"])})
                except struct.error:
                    pass
                out["frames"] = frames
                break
            off += 48
    return out


def resolve(addr: int, modules: list[dict]) -> str:
    for m in modules:
        if m["base"] <= addr < m["base"] + m["size"]:
            return f"{m['name']}+{hex(addr - m['base'])}"
    return "???"


def format_text(rep: dict) -> str:
    lines = [f"minidump: {rep['path']}"]
    ex = rep.get("exception") or {}
    if ex:
        rw = ""
        lines.append(f"exception: {hex(ex.get('code', 0))} at {hex(ex.get('address', 0))} "
                     f"(thread {ex.get('tid')})")
    f = rep.get("fault") or {}
    if f:
        lines.append(f"fault: tid {f['tid']} rip {hex(f['rip'])} {f['at']}")
    for fr in rep.get("frames", [])[:12]:
        lines.append(f"  stack+{fr['sp_off']:#x}: {fr['value']:#x} {fr['at']}")
    if rep.get("modules") is not None:
        lines.append(f"modules: {len(rep['modules'])} "
                     f"({', '.join(m['name'] for m in rep['modules'][:8])}"
                     f"{', ...' if len(rep['modules']) > 8 else ''})")
    return "\n".join(lines)


def register(sub):
    p = sub.add_parser("minidump", help="read Windows crash dumps on Linux")
    sp = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = sp.add_parser("show", help="decode exception + fault stack")
    q.add_argument("dump", help="path to the .dmp file")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=_r_show)
    p.set_defaults(func=lambda a: p.print_help())


def _r_show(a: argparse.Namespace):
    import json
    rep = parse(a.dump)
    if a.json:
        print(json.dumps(rep, indent=2, default=hex))
    else:
        print(format_text(rep))
