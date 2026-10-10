#!/usr/bin/env bash
# skycraft-modrinth.sh — start the Modrinth "Fabric 26.3" profile for SkyCraft.
# The Modrinth App (flatpak) has no stable per-profile CLI deep-link, so this
# opens the app and prints the one-click step; when a CLI exists it is used.
# All paths degrade gracefully on headless boxes (used by hw skyrim launch).
set -uo pipefail
PROFILE="${1:-Fabric 26.3}"
while [ "$#" -gt 0 ]; do
  case "$1" in --profile) PROFILE="${2:-$PROFILE}"; shift 2;; *) shift;; esac
done
echo "SkyCraft Minecraft: open Modrinth App and press Play on profile '$PROFILE'."
echo "(MC 26.3 + Fabric Loader >= 0.19.5 + Fabric API + skycraft fabric jar in mods/.)"
if command -v flatpak >/dev/null 2>&1; then
  exec flatpak run com.modrinth.ModrinthApp
elif command -v modrinth-app >/dev/null 2>&1; then
  exec modrinth-app
else
  echo "no Modrinth launcher found on PATH (flatpak run com.modrinth.ModrinthApp)." >&2
  exit 1
fi
