#!/usr/bin/env bash
# E2E-05: OSC 133 shell integration — --cmd-done (fact confidence),
# exit codes, expect-code mismatch fails immediately.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TD="python3 -m termdebug"
NAME="td05_$$_$RANDOM"
SOCK="td05sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_STATE_HOME="$TMP/state"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-05 FAIL: $*"; exit 1; }

$TD start -n "$NAME" --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start failed"
DIR="$XDG_STATE_HOME/term-debug/$NAME"

# shell integration is injected for bash
python3 -c "
import json,sys
s=json.load(open('$DIR/state.json'))
assert s['shell_integration'] is True, s
" || fail "state.json should have shell_integration=true for bash"

# --- true -> 0 ---
$TD send -n "$NAME" --type "true" --key Enter >/dev/null || fail "send failed"
$TD wait -n "$NAME" --cmd-done --expect-code 0 --timeout 10 | python3 -c '
import json, sys
v = json.load(sys.stdin)
assert v["verdict"] == "met" and v["confidence"] == "fact", v
assert v["conditions"][0]["type"] == "cmd-done", v
' || fail "cmd-done true/0"

# --- false -> 1 ---
$TD send -n "$NAME" --type "false" --key Enter >/dev/null || fail "send failed"
$TD wait -n "$NAME" --cmd-done --expect-code 1 --timeout 10 >/dev/null \
  || fail "cmd-done false/1"

# --- sh -c 'exit 42' -> 42 ---
$TD send -n "$NAME" --type "sh -c 'exit 42'" --key Enter >/dev/null || fail "send failed"
$TD wait -n "$NAME" --cmd-done --expect-code 42 --timeout 10 >/dev/null \
  || fail "cmd-done exit 42"

# --- expect mismatch fails immediately (not after a timeout) ---
$TD send -n "$NAME" --type "sh -c 'exit 7'" --key Enter >/dev/null || fail "send failed"
T0="$(date +%s%N)"
if $TD wait -n "$NAME" --cmd-done --expect-code 5 --timeout 30 2>"$TMP/err.json"; then
  fail "expect-code 5 vs actual 7 must fail"
fi
T1="$(date +%s%N)"
ELAPSED_MS=$(( (T1 - T0) / 1000000 ))
[ "$ELAPSED_MS" -lt 2000 ] || fail "expect-code mismatch took ${ELAPSED_MS}ms (should fail immediately)"
python3 -c "
import json,sys
e=json.load(open('$TMP/err.json'))['error']
assert e['code']=='expect-code-mismatch', e
assert e['evidence']['exit_code']==7, e
" || fail "mismatch error JSON invalid"

echo "E2E-05 PASS"
