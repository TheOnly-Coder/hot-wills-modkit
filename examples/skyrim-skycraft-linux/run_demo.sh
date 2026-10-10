#!/usr/bin/env bash
# Headless prove-out for Skyrim SE x Fabric 26.3 (no games, no GPU, no display).
# Gates: contract -> bridge loopback -> composite -> shade grade -> live broker
# with synthetic host daemon + guest stub back-channel proof.
set -euo pipefail
HERE="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT="$(cd -P "$HERE/../.." && pwd)"
export PATH="$KIT/bin:$PATH"
export HW_NO_UV=1
TAKES="$HERE/takes"
rm -rf "$TAKES" bridge.jsonl
mkdir -p "$TAKES"

echo "== [1/5] contract =="
hw bridge check "$HERE/docs/CONTRACT.md"

echo "== [2/5] bridge loopback =="
hw bridge demo

echo "== [3/5] composite =="
hw composite demo --out "$TAKES/composite"

echo "== [4/5] shade grade =="
hw shade demo --out "$TAKES/shade" --preset skyrim-day

echo "== [5/5] live broker: synthetic host + guest stub =="
PORT=27441
LOG="$HERE/bridge.jsonl"
INBOX="$TAKES/skycraft-inbox.jsonl"
rm -f "$LOG" "$INBOX"
hw bridge serve --port "$PORT" --log "$LOG" --seconds 16 &
BROKER=$!
sleep 1
python3 "$KIT/adapters/python/skycraft_host_daemon.py" --synthetic --seconds 12 \
  --port "$PORT" --inbox "$INBOX" &
HOSTP=$!
sleep 1
python3 "$HERE/guest_stub.py" --port "$PORT" --seconds 11 --event-at 4 &
GUESTP=$!
wait "$HOSTP" || true
wait "$GUESTP" || true
wait "$BROKER" || true

echo "== asserts =="
python3 - "$LOG" "$INBOX" <<'EOF'
import json, sys
log, inbox = sys.argv[1], sys.argv[2]
msgs = [json.loads(l) for l in open(log) if l.strip()]
ts = {m.get("t") for m in msgs}
assert "cam" in ts, "no cam in bridge log"
assert "event" in ts, "no event in bridge log"
evs = [m for m in msgs if m.get("t") == "event" and m.get("kind") == "explosion"]
assert evs, "guest explosion never reached the broker"
inbox_lines = [l for l in open(inbox) if l.strip()] if __import__("os").path.exists(inbox) else []
assert any("explosion" in l for l in inbox_lines), "host inbox missing the explosion (back-channel broken)"
print(f"prove-out OK: {len(msgs)} broker msgs ({len([m for m in msgs if m.get('t')=='cam'])} cam), "
      f"{len(evs)} explosion events, inbox has {len(inbox_lines)} lines")
EOF

echo "== bridge log validates =="
hw bridge check "$HERE/docs/CONTRACT.md" --log "$LOG"
echo "ALL GREEN: frames in $TAKES/{composite,shade}, log $LOG"
