#!/usr/bin/env bash
# skycraft-graphics.sh — force low graphics + fullscreen for the Skyrim launch.
#
# Skyrim: applies the shipped Low.ini preset over the prefix SkyrimPrefs.ini
# (section-aware upsert, comments/order/line-endings preserved), then forces
# borderless fullscreen at desktop resolution. Minecraft (Modrinth profile
# options.txt): fullscreen on, minimal particles, halved entity distance.
# Idempotent: re-running changes nothing once applied. Backs up both files
# (timestamped) before the first change of a run.
#
# Env: SKYCRAFT_PREFS (SkyrimPrefs.ini), SKYCRAFT_LOWINI (Low.ini),
# SKYCRAFT_MC_OPTIONS (Modrinth profile options.txt), SKYCRAFT_RES (e.g.
# 1920x1080; autodetected via xrandr when unset), SKYCRAFT_LOG (appended).
# Exit 0 always (graphics must never block the game); failures are logged.
set -uo pipefail

PREFS="${SKYCRAFT_PREFS:-$HOME/.local/share/Steam/steamapps/compatdata/489830/pfx/drive_c/users/steamuser/Documents/My Games/Skyrim Special Edition/SkyrimPrefs.ini}"
LOWINI="${SKYCRAFT_LOWINI:-$HOME/.local/share/Steam/steamapps/common/Skyrim Special Edition/Low.ini}"
MCOPT="${SKYCRAFT_MC_OPTIONS:-$HOME/.var/app/com.modrinth.ModrinthApp/data/ModrinthApp/profiles/Fabric 26.3/options.txt}"
LOG="${SKYCRAFT_LOG:-$HOME/.local/share/hot-wills-modkit/skycraft-autolaunch.log}"
BACKUP_BASE="${SKYCRAFT_BACKUP_BASE:-$HOME/.local/share/hot-wills-modkit/backups}"

log() { echo "[$(date '+%F %T')] graphics: $*" >>"$LOG" 2>/dev/null || true; }

# section-aware upsert of key=value into an ini file (CRLF preserved).
ini_upsert() { # file section key value
  local file="$1" section="$2" key="$3" value="$4"
  [ -f "$file" ] || return 0
  local eol=""
  if head -c 4096 "$file" 2>/dev/null | grep -q $'\r'; then eol=$'\r'; fi
  local tmp
  tmp="$(mktemp)" || return 0
  awk -v section="$section" -v key="$key" -v value="$value" -v eol="$eol" '
    BEGIN { insec = 0; done = 0 }
    {
      line = $0
      sub(/\r$/, "", line)
      if (line ~ /^\[.*\]/) {
        if (insec && !done) { print key "=" value eol; done = 1 }
        insec = (line == section)
        print $0
        next
      }
      if (insec && !done && line ~ /^[^=]+=/) {
        k = line; sub(/=.*/, "", k)
        if (k == key) { print key "=" value eol; done = 1; next }
      }
      print $0
    }
    END {
      if (!done && insec) print key "=" value eol
      if (!done && !insec) { print ""; print section; print key "=" value eol }
    }' "$file" >"$tmp" 2>/dev/null && cat "$tmp" >"$file"
  rm -f "$tmp"
}

# flat key:value upsert for Minecraft options.txt (LF).
mc_upsert() { # file key value
  local file="$1" key="$2" value="$3"
  [ -f "$file" ] || return 0
  local tmp
  tmp="$(mktemp)" || return 0
  if grep -q "^${key}:" "$file" 2>/dev/null; then
    sed -E "s/^(${key}:)[^\r]*(\r?)$/\1${value}\2/" "$file" >"$tmp" && cat "$tmp" >"$file"
  else
    { cat "$file"; echo "${key}:${value}"; } >"$tmp" && cat "$tmp" >"$file"
  fi
  rm -f "$tmp"
}

STAMP="$(date +%Y%m%d-%H%M%S)"
[ -f "$PREFS" ] && mkdir -p "$BACKUP_BASE/skyrim-prefs-$STAMP" 2>/dev/null \
  && cp -a "$PREFS" "$BACKUP_BASE/skyrim-prefs-$STAMP/" 2>/dev/null \
  && log "SkyrimPrefs.ini backed up to $BACKUP_BASE/skyrim-prefs-$STAMP"
[ -f "$MCOPT" ] && mkdir -p "$BACKUP_BASE/mc-options-$STAMP" 2>/dev/null \
  && cp -a "$MCOPT" "$BACKUP_BASE/mc-options-$STAMP/" 2>/dev/null \
  && log "options.txt backed up to $BACKUP_BASE/mc-options-$STAMP"

# -- Skyrim: Low.ini preset -----------------------------------------------
if [ -f "$PREFS" ] && [ -f "$LOWINI" ]; then
  section=""
  # NOTE: Low.ini ships CRLF; strip CR while parsing.
  while IFS= read -r raw || [ -n "$raw" ]; do
    line="${raw%$'\r'}"
    case "$line" in
      \[*\]) section="$line" ;;
      *=*)
        key="${line%%=*}"; value="${line#*=}"
        # resolution/fullscreen are forced below, never from the preset
        case "$key" in
          "iSize H"|"iSize W"|"bFull Screen"|"bBorderless"|fGamma) continue ;;
        esac
        [ -n "$section" ] && ini_upsert "$PREFS" "$section" "$key" "$value"
        ;;
    esac
  done <"$LOWINI"
  log "Low.ini preset applied over SkyrimPrefs.ini"
else
  log "WARN: PREFS or LOWINI missing (prefs=$PREFS low=$LOWINI); preset skipped"
fi

# -- Skyrim: borderless fullscreen at desktop resolution --------------------
RES="${SKYCRAFT_RES:-}"
if [ -z "$RES" ]; then
  RES="$(xrandr 2>/dev/null | grep -E '\*' | head -n 1 | grep -oE '[0-9]+x[0-9]+' | head -n 1)"
fi
[ -z "$RES" ] && RES="1920x1080"
W="${RES%x*}"; H="${RES#*x}"
if [ -f "$PREFS" ]; then
  ini_upsert "$PREFS" "[Display]" "bFull Screen" "1"
  ini_upsert "$PREFS" "[Display]" "bBorderless" "1"
  ini_upsert "$PREFS" "[Display]" "iSize W" "$W"
  ini_upsert "$PREFS" "[Display]" "iSize H" "$H"
  log "fullscreen forced: borderless ${W}x${H}"
fi

# -- Minecraft profile: fullscreen + lean ------------------------------------
# Render distance is only ever lowered (never raised over the player's choice).
if [ -f "$MCOPT" ]; then
  mc_upsert "$MCOPT" "fullscreen" "true"
  mc_upsert "$MCOPT" "particles" "2"
  mc_upsert "$MCOPT" "entityDistanceScaling" "0.5"
  mc_upsert "$MCOPT" "simulationDistance" "4"
  mc_upsert "$MCOPT" "enableVsync" "false"
  mc_upsert "$MCOPT" "maxFps" "60"
  mc_upsert "$MCOPT" "mipmapLevels" "1"
  cur_rd="$(grep -E '^renderDistance:' "$MCOPT" 2>/dev/null | head -n 1 | cut -d: -f2 | tr -d '\r')"
  if [ -n "$cur_rd" ] && [ "$cur_rd" -gt 6 ] 2>/dev/null; then
    mc_upsert "$MCOPT" "renderDistance" "6"
  fi
  log "Modrinth options.txt: fullscreen + lean (renderDistance lowered only if > 6)"
else
  log "WARN: MC options.txt missing ($MCOPT); skipped"
fi

log "graphics done"
exit 0
