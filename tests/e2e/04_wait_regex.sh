#!/usr/bin/env bash
# E2E-04: wait engine — verdict JSON + confidence, trailing-space self-heal,
# timeout evidence, --scrollback history matching.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TD="python3 -m termdebug"
NAME="td04_$$_$RANDOM"
SOCK="td04sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_STATE_HOME="$TMP/state"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-04 FAIL: $*"; exit 1; }

$TD start -n "$NAME" --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start failed"

# --- match with a trailing-space pattern (self-heal red line) ---
$TD send -n "$NAME" --type "echo 'TD4: '" --key Enter >/dev/null || fail "send failed"
OUT="$($TD wait -n "$NAME" --until 'TD4: ' --timeout 5)" || fail "wait 'TD4: ' (trailing space) did not match"
echo "$OUT" | python3 -c '
import json, sys
v = json.load(sys.stdin)
assert v["verdict"] == "met", f"verdict: {v}"
c = v["conditions"][0]
assert c["type"] == "until", f"conditions: {v}"
assert c["echo_suspect"] is True, f"echo downgrade should fire: {v}"
assert v["confidence"] == "heuristic", f"echo-suspect must degrade: {v}"
' || fail "verdict JSON invalid (see assertion above)"

# --- timeout returns structured evidence, non-zero exit ---
if $TD wait -n "$NAME" --until 'NEVER_XYZ' --timeout 1 2>"$TMP/err.json"; then
  fail "wait NEVER_XYZ should fail"
fi
python3 - "$TMP/err.json" <<'PY' || fail "timeout error JSON invalid (see assertion above)"
import json, sys
e = json.load(open(sys.argv[1]))["error"]
assert e["code"] == "timeout", e
ev = e["evidence"]
assert ev["screen"].strip(), "evidence.screen must be non-empty"
assert "x" in ev["cursor"] and "y" in ev["cursor"], f"evidence.cursor: {ev}"
PY

# --- --scrollback reaches lines that scrolled off ---
$TD send -n "$NAME" --type "seq 1 300" --key Enter >/dev/null || fail "send seq failed"
$TD wait -n "$NAME" --until '^300$' --timeout 5 >/dev/null || fail "seq never appeared"
$TD wait -n "$NAME" --until '^150$' --timeout 5 --scrollback 200 >/dev/null \
  || fail "--scrollback 200 should reach seq line 150 (scrolled off)"
if $TD wait -n "$NAME" --until '^150$' --timeout 2 >/dev/null 2>&1; then
  fail "without --scrollback, scrolled-off line must not match"
fi

echo "E2E-04 PASS"
