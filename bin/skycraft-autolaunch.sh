#!/usr/bin/env bash
# skycraft-autolaunch.sh — Steam Launch Options prefix for Skyrim SE + SkyCraft.
#
# Install (Steam > Skyrim Special Edition > Properties > Launch Options):
#   "/home/user/Downloads/AI game modding stuff/hot-wills-modkit/bin/skycraft-autolaunch.sh" %command%
#
# ALSO REQUIRED (one time): Steam > Skyrim SE > Properties > Compatibility >
# check "Force the use of a specific Steam Play compatibility tool" and pick
# Proton 9.0. SkyCraft's SKSE plugin fails its Load check under Proton
# Experimental and loads correctly under 9.0 (verified on 0.1.0 and 0.1.2).
#
# What it does (default SKSE mode): backs up saves, then runs Skyrim through
# SKSE under Proton 9.0 and waits on the game. Steam tracks this script while
# it waits, so %command% is superseded (it is NOT executed). The SKSE plugin
# then starts Minecraft by itself (see SkyCraft.ini sLauncher: the Modrinth
# profile under Wine by default, no Prism involved).
#
# This script is deliberately self-contained bash + proton: no uv, no python,
# no network in the hot path, so a broken toolchain can never block the game.
# Every step is appended to $LOG (tail it after any failed Play click).
#
# Env overrides: SKYCRAFT_USE_SKSE=0 (legacy mode: background Linux bridge
# services via hw, then exec Steam's %command% unchanged),
# SKYCRAFT_PROFILE ("Fabric 26.3"), SKYCRAFT_PORT (27431),
# SKYCRAFT_NO_MINECRAFT=1, SKYCRAFT_NO_OVERLAY=1, SKYCRAFT_DRY_RUN=1.
set -uo pipefail

KIT_ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Game dir: explicit override wins, else the usual Steam locations (Proton runs
# .exe files regardless of the Linux exec bit, so test -f, not -x).
GAME_DIR="${SKYCRAFT_GAME_DIR:-}"
if [ -z "$GAME_DIR" ]; then
  for d in "$HOME/.local/share/Steam/steamapps/common/Skyrim Special Edition" \
           "$HOME/.steam/steam/steamapps/common/Skyrim Special Edition"; do
    if [ -f "$d/SkyrimSE.exe" ]; then GAME_DIR="$d"; break; fi
  done
fi
[ -z "$GAME_DIR" ] && GAME_DIR="$HOME/.local/share/Steam/steamapps/common/Skyrim Special Edition"
PFX="${SKYCRAFT_PREFIX:-$HOME/.local/share/Steam/steamapps/compatdata/489830/pfx}"
STEAM_ROOT="${SKYCRAFT_STEAM:-$HOME/.local/share/Steam}"
LOG="${SKYCRAFT_LOG:-$HOME/.local/share/hot-wills-modkit/skycraft-autolaunch.log}"
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true

log() { echo "[$(date '+%F %T')] $*" >>"$LOG"; }
log "--- autolaunch invoked (args: $*)"

if [ "$#" -eq 0 ]; then
  echo "usage: skycraft-autolaunch.sh %command%  (as a Steam Launch Options prefix)" >&2
  echo "dry run:" >&2
  SKYCRAFT_DRY_RUN=1 exec "$0" true
fi

# -- graphics: low preset + borderless fullscreen (fast, idempotent) ---------
if [ -z "${SKYCRAFT_NO_GRAPHICS:-}" ]; then
  if [ -x "$KIT_ROOT/bin/skycraft-graphics.sh" ]; then
    "$KIT_ROOT/bin/skycraft-graphics.sh" 2>>"$LOG" || log "WARN: graphics script failed (continuing)"
  fi
else
  log "graphics step skipped (SKYCRAFT_NO_GRAPHICS=1)"
fi

# -- save backup (fast copy, never fatal) ------------------------------------
SAVES="$PFX/drive_c/users/steamuser/Documents/My Games/Skyrim Special Edition/Saves"
if [ -d "$SAVES" ]; then
  DEST="$HOME/.local/share/hot-wills-modkit/backups/skyrim-saves-autolaunch"
  if mkdir -p "$DEST" 2>/dev/null && cp -a "$SAVES/." "$DEST/" 2>>"$LOG"; then
    log "saves backed up ($SAVES -> $DEST)"
  else
    log "WARN: save backup failed (continuing anyway)"
  fi
fi

# -- pick Proton (Steam default first: Experimental also runs the Java side;
# 9.0 is the fallback — the plugin's Load flake is Proton-independent) --------
PROTON_SCRIPT="${SKYCRAFT_PROTON:-}"
if [ -z "$PROTON_SCRIPT" ]; then
for cand in "$STEAM_ROOT/steamapps/common/Proton - Experimental/proton" \
            "$STEAM_ROOT/steamapps/common/Proton 9.0 (Beta)/proton"; do
  if [ -x "$cand" ]; then PROTON_SCRIPT="$cand"; break; fi
done
fi
if [ -z "$PROTON_SCRIPT" ]; then
  # last resort: newest Proton dir with a proton script
  PROTON_SCRIPT="$(ls -d "$STEAM_ROOT"/steamapps/common/Proton*/proton 2>/dev/null | sort | tail -n 1)"
fi
log "proton script: ${PROTON_SCRIPT:-MISSING}"

# -- legacy bridge mode -------------------------------------------------------
if [ "${SKYCRAFT_USE_SKSE:-1}" = "0" ]; then
  log "legacy bridge mode"
  HW="$KIT_ROOT/bin/hw"
  PROFILE="${SKYCRAFT_PROFILE:-Fabric 26.3}"
  PORT="${SKYCRAFT_PORT:-27431}"
  ARGS=(skyrim launch --profile "$PROFILE" --port "$PORT")
  [ -n "${SKYCRAFT_NO_MINECRAFT:-}" ] && ARGS+=(--no-minecraft)
  [ -n "${SKYCRAFT_NO_OVERLAY:-}" ] && ARGS+=(--no-overlay)
  [ -n "${SKYCRAFT_DRY_RUN:-}" ] && ARGS+=(--dry-run)
  # shellcheck disable=SC2068
  if [ -n "${SKYCRAFT_DRY_RUN:-}" ]; then
    log "dry run: $HW ${ARGS[@]} --as-steam-wrapper -- $@"
    echo "dry run — see $LOG"; exit 0
  fi
  # shellcheck disable=SC2068
  HW_NO_UV=1 exec "$HW" ${ARGS[@]} --as-steam-wrapper -- $@
fi

# -- SKSE mode (default) ------------------------------------------------------
if [ ! -f "$GAME_DIR/skse64_loader.exe" ]; then
  log "ERROR: skse64_loader.exe missing in $GAME_DIR (install SKSE64); aborting to Steam command"
  echo "skycraft-autolaunch: SKSE missing, running Steam command instead (see $LOG)" >&2
  exec "$@"
fi
if [ -z "$PROTON_SCRIPT" ]; then
  log "ERROR: no Proton script found; aborting to Steam command"
  echo "skycraft-autolaunch: no Proton found, running Steam command instead (see $LOG)" >&2
  exec "$@"
fi
export STEAM_COMPAT_DATA_PATH="$STEAM_ROOT/steamapps/compatdata/489830"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="$STEAM_ROOT"
# Steam injects its overlay via LD_PRELOAD into every game process. Under Wine
# that perturbs the address space the SKSE plugin's init is sensitive to
# (flaky _Mtx_lock crash), and the overlay is unusable in this setup anyway.
# Strip it (and only it) before launching.
if [ -n "${LD_PRELOAD:-}" ]; then
  log "stripping LD_PRELOAD for the game ($LD_PRELOAD)"
  unset LD_PRELOAD
fi
log "SKSE mode: cd $GAME_DIR && proton-run skse64_loader.exe"
if [ -n "${SKYCRAFT_DRY_RUN:-}" ]; then
  echo "+ (cd $GAME_DIR) $PROTON_SCRIPT run $GAME_DIR/skse64_loader.exe"
  echo "(dry run — not launching; log $LOG)"; exit 0
fi
cd "$GAME_DIR" || { log "ERROR: cannot cd $GAME_DIR"; exit 1; }
log "game starting (waiting on it; quit the game to release Steam)"
# The plugin's Load check is flaky under Wine (a mutex-call crash inside its
# init, ~1 in 3-4 boots sail through; identical files/config). Detect the
# outcome from SKSE's own log and retry automatically: a failed boot shows the
# SKSE dialog, which we cannot click headless, so kill that attempt by exact
# PID and boot again. Success = "loaded correctly".
SKSE_LOG="$PFX/drive_c/users/steamuser/Documents/My Games/Skyrim Special Edition/SKSE/skse64.log"
MAX_TRIES="${SKYCRAFT_MAX_TRIES:-3}"
try=1
while [ "$try" -le "$MAX_TRIES" ]; do
  log "boot attempt $try/$MAX_TRIES"
  PRE_SZ="$(stat -c %s "$SKSE_LOG" 2>/dev/null || echo 0)"
  PRE_PIDS="$(pgrep -f "SkyrimSE\.exe" 2>/dev/null | sort | tr '\n' ' ')"
  "$PROTON_SCRIPT" run ./skse64_loader.exe >>"$LOG" 2>&1 &
  GAME_WRAPPER_PID=$!
  # wait up to 120s for SKSE's verdict on the plugin; only content written
  # by THIS attempt counts (the log persists across boots and may rotate)
  verdict=""
  for _ in $(seq 1 60); do
    sleep 2
    CUR_SZ="$(stat -c %s "$SKSE_LOG" 2>/dev/null || echo 0)"
    FROM="$PRE_SZ"
    [ "$CUR_SZ" -lt "$PRE_SZ" ] && FROM=0
    if tail -c "+$((FROM + 1))" "$SKSE_LOG" 2>/dev/null | grep -a -q "loaded correctly"; then verdict=ok; break; fi
    if tail -c "+$((FROM + 1))" "$SKSE_LOG" 2>/dev/null | grep -a -q "disabled, fatal\|address library needs to be updated"; then verdict=failed; break; fi
    kill -0 "$GAME_WRAPPER_PID" 2>/dev/null || { verdict=exited; break; }
  done
  log "verdict after attempt $try: ${verdict:-timeout}"
  if [ "$verdict" = "ok" ] || [ "$verdict" = "" ] || [ "$verdict" = "exited" ]; then
    log "plugin loaded (or game running past check) — waiting on game exit"
    wait "$GAME_WRAPPER_PID" 2>/dev/null
    log "game exited (code $?)"
    exit 0
  fi
  if [ "$verdict" = "failed" ]; then
    # kill only PIDs this attempt started (never the wrapper, never strangers)
    for gp in $(pgrep -f "SkyrimSE\.exe" 2>/dev/null | sort); do
      case " $PRE_PIDS " in
        *" $gp "*) ;;
        *) if [ "$gp" != "$$" ]; then kill "$gp" 2>/dev/null && log "killed failed attempt pid $gp"; fi ;;
      esac
    done
    kill "$GAME_WRAPPER_PID" 2>/dev/null
    sleep 5
  fi
  try=$((try + 1))
done
log "all $MAX_TRIES attempts failed to load the plugin; launching once more and leaving the dialog to you"
exec "$PROTON_SCRIPT" run ./skse64_loader.exe >>"$LOG" 2>&1
