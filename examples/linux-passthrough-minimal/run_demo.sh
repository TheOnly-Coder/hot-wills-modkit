#!/usr/bin/env bash
# Minimal Linux passthrough end to end: contract -> broker -> two fake games ->
# composite -> checks. No real games, no display, no ReShade. Run from this dir.
set -euo pipefail
HW="${HW:-python3 -m hw}"
ROOT="$(cd -P "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT/../..:${PYTHONPATH:-}"
cd "$ROOT"
rm -rf frames takes docs bridge.jsonl
mkdir -p frames takes docs

echo "== 1. contract"
$HW bridge new-contract --host "example-host" --guest "example-guest" --out docs/CONTRACT.md
$HW bridge check docs/CONTRACT.md

echo "== 2. broker + two fake games"
$HW bridge serve --port 27431 --log bridge.jsonl --seconds 30 &
BROKER=$!
sleep 1
python3 fake_guest.py --frames 12 --outdir frames &
GUEST=$!
python3 fake_host.py --frames 12 --outdir frames
wait "$GUEST"
kill "$BROKER" 2>/dev/null || true

echo "== 3. back-channel proof (host saw the guest explosion)"
grep -q explosion frames/host_seen_events.jsonl \
  && echo "back-channel OK" \
  || { echo "FAIL: no explosion event in frames/host_seen_events.jsonl"; exit 1; }

echo "== 4. composite every frame (CPU, no ReShade)"
for i in $(seq 0 11); do
  f=$(printf "%03d" "$i")
  HW_NO_UV=1 $HW composite compose --host "frames/host_$f.png" --host-depth "frames/host_$f.npy" \
    --guest "frames/guest_$f.png" --guest-depth "frames/guest_$f.npy" \
    --overlay frames/hud.png --out "takes/out_$f.png"
done

echo "== 5. bridge log validates against protocol v1"
$HW bridge check docs/CONTRACT.md --log bridge.jsonl
echo "== 6. frames"
ls takes/ | head -20
echo "DEMO OK: open takes/out_006.png — guest checkerboard + cube over host sky, red pillar occluding."
