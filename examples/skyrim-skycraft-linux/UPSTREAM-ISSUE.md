# Upstream issue draft: SkyCraft SKSE plugin fails Load under Wine/Proton
<!-- For chasmlol/SkyCraft issues. Post as-is (fill in the two blanks). -->

Title: `SKSE plugin fails to load under Wine/Proton (Load-time crash in MSVCP140, flaky)`

## What happens

On Linux (Steam + Proton, game 1.7.104.0, SKSE 2.3.1, Address Library with
versionlib-1-7-104-0.bin), `SkyCraft.dll` 0.1.2 (and 0.1.0, same signature)
usually fails SKSE's load with the generic dialog:

> `SkyCraft.dll: disabled, fatal error occurred while loading plugin`

`skse64.log` ends right after `loading plugin "SkyCraft"` and `SkyCraft.log`
is created but stays 0 bytes. Roughly 1 in 3–4 boots sails through instead
(`loaded correctly`, all hooks install, shared memory created, Prism starts).

## What I ruled out (with evidence)

- Imports/DLLs: all present (`objdump`: D3DCOMPILER_47, MSVCP140,
  VCRUNTIME140(_1), api-ms-win-crt-*, all in prefix system32).
- Game/SKSE/Address Library versions: loader log confirms 1.7.104.0, SKSE
  2.3.1, correct bins; SKSE's own gate passes.
- Config: fails identically with the release ini, an empty-stub ini, and
  `bStartWithSkyrim = 0` (so it is NOT the launcher thread/COM/tar call).
- It's not the version database: SKSE opens
  `Data/SKSE/Plugins/versionlib-1-7-104-0.bin` itself during its gate
  (Wine `+file` trace), and removing the bin changes the message to
  `address library needs to be updated` instead.
- Not Proton-version-specific: identical failure under Proton 9.0 and
  Experimental (separate Wine seh traces, same crash).

## The crash (the part you can act on)

`WINEDEBUG=seh` captures an access violation during plugin init, same address
every time:

```
EXCEPTION_ACCESS_VIOLATION, read of 0x0
fault: MSVCP140.dll+0x18C34  (import: _Mtx_lock)
called from SkyCraft.dll+0x252783 ... C++ EH unwinding ...
... SkyCraft.dll+0x21B24C ... skse64_1_7_104.dll (SKSE calling in)
```

So: a `std::mutex`-family lock on a bad mutex very early in init (before any
log line is written and before SkyCraft.ini is read), caught by SKSE. Given
the flakiness across identical boots, prime suspects from the outside are an
uninitialized/static-init-order mutex (or the spdlog sink mutex, since the
first log write never lands) — worth an LLVM/MSan or `/RTC` pass over the
`SKSEPluginLoad` path, especially anything static that touches
`std::mutex`/`std::locale`/`std::filesystem` before `SetupLog()`.

Two environment notes that helped isolate it:

- The prefix originally shipped a 2016-era `msvcp140.dll`; updating to a
  current VC++ redist changed the failure rate but did not eliminate it, so
  don't chase the CRT too far — the null read reproduces with a 2025 CRT.
- Unrelated but found on the way: you may want `.log = false` handling or a
  null-guard review wherever `logger::` is first touched, since a dead logger
  is currently the only symptom (`SkyCraft.log` created, 0 bytes).

## Repro (no Windows box needed on your side)

Steam Deck / any Linux + Steam + Skyrim SE 1.7.104 + SKSE + Address Library +
this mod under Proton: launch via `skse64_loader.exe` 5–6 times, count dialogs
vs `loaded correctly` in `skse64.log`. `WINEDEBUG=seh` shows the AV above.

Update 2026-10-09: re-downloaded the 0.1.2 release zip fresh (md5-verified,
DLL hash-identical to the installed copy) and reinstalled DLL+ini clean —
still fails the same way, and reverting all local settings tweaks changes
nothing. Not file corruption, not config.

## Environment of this report

- Skyrim SE 1.7.104.0 (Steam build 24914197), SKSE64 2.3.1
  (`skse64_1_7_104.dll`), Address Library All-in-One (incl. 1-7-104-0, v5 format)
- Proton 9.0 and Experimental (both fail; successes observed under both too)
- Intel HD 630, Ubuntu 24.04, kernel 6.17
- `__YOUR_SKSE_LOG_SNIPPET__`, `__YOUR_HW_SPECS__`
