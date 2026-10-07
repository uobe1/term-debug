#!/usr/bin/env bash
# E2E-12: trace as a v2 projection of raw.log (json NDJSON + human summary).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TD="python3 -m termuse"
SOCK="td12sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_STATE_HOME="$TMP/state"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-12 FAIL: $*"; exit 1; }

$TD start -n td12 --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start failed"
$TD send -n td12 --type "echo T12" --key Enter >/dev/null || fail "send failed"
$TD wait -n td12 --until 'T12' --timeout 5 >/dev/null || fail "wait failed"

# --- json projection: raw NDJSON, events present, timestamps monotonic ---
$TD trace -n td12 --format json > "$TMP/nd.json" || fail "trace json failed"
python3 - "$TMP/nd.json" <<'PY' || fail "trace json assertions (see above)"
import json, sys
lines = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
assert isinstance(lines[0], dict) and lines[0].get("version") == 2, lines[0]
events = [l for l in lines if isinstance(l, list)]
codes = {e[1] for e in events}
assert {"o", "i", "m"} <= codes, f"missing event kinds: {codes}"
ts = [e[0] for e in events]
# i-events (client) and o-events (pipe wrapper) are concurrent writers:
# near-simultaneous lines may swap, allow a small negative tolerance.
assert all(b >= a - 0.1 for a, b in zip(ts, ts[1:])), f"timestamps wild: {ts}"
m_events = [e for e in events if e[1] == "m"]
assert any(e[2].get("event") == "wait-met" for e in m_events), m_events
PY

# --- human projection: summary lines ---
$TD trace -n td12 > "$TMP/human.txt" || fail "trace human failed"
grep -q "i .*type='echo T12'" "$TMP/human.txt" || fail "human trace lacks i summary"
grep -q "o " "$TMP/human.txt" || fail "human trace lacks o summary"
grep -q "m wait-met" "$TMP/human.txt" || fail "human trace lacks m summary"

echo "E2E-12 PASS"
