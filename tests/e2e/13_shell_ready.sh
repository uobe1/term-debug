#!/usr/bin/env bash
# E2E-13: wait --shell-ready — internalized `true` probe (fact).
# Covers: bare --cmd-done after start times out (the quirk), shell-ready
# meets after start, times out inside a live REPL (shell-not-ready),
# re-probe succeeds after leaving the program, no-shell-integration.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TD="python3 -m termuse"
NAME="td13_$$_$RANDOM"
SOCK="td13sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_STATE_HOME="$TMP/state"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-13 FAIL: $*"; exit 1; }

$TD start -n "$NAME" --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start failed"

# --- the quirk shell-ready internalizes: bare --cmd-done right after
#     start times out (bash's first D has no preceding C -> aborted) ---
if $TD wait -n "$NAME" --cmd-done --timeout 2 >/dev/null 2>"$TMP/bare.json"; then
  fail "bare --cmd-done right after start unexpectedly met"
fi
python3 -c "
import json,sys
e=json.load(open('$TMP/bare.json'))['error']
assert e['code']=='timeout', e
" || fail "bare --cmd-done should fail with timeout"

# --- shell-ready right after start: probe answered (fact) ---
$TD wait -n "$NAME" --shell-ready --timeout 10 | python3 -c '
import json, sys
v = json.load(sys.stdin)
assert v["verdict"] == "met" and v["confidence"] == "fact", v
assert v["conditions"][0]["type"] == "shell-ready", v
assert v["conditions"][0]["exit_code"] == 0, v
' || fail "shell-ready after start should meet with exit 0"

# --- inside a live python REPL the probe is swallowed -> shell-not-ready ---
$TD send -n "$NAME" --type python3 --key Enter >/dev/null || fail "send python3 failed"
$TD wait -n "$NAME" --until '>>>' --timeout 10 >/dev/null || fail "REPL never came up"
if $TD wait -n "$NAME" --shell-ready --timeout 3 >/dev/null 2>"$TMP/repl.json"; then
  fail "shell-ready inside a live REPL must not meet"
fi
python3 -c "
import json,sys
e=json.load(open('$TMP/repl.json'))['error']
assert e['code']=='shell-not-ready', e
assert e['evidence'] and '>>>' in e['evidence']['screen'], e
" || fail "expected shell-not-ready with screen evidence"

# --- after leaving the program the same probe confirms the shell is back ---
$TD send -n "$NAME" --key C-d >/dev/null || fail "send C-d failed"
$TD wait -n "$NAME" --shell-ready --timeout 10 >/dev/null \
  || fail "shell-ready after quitting the REPL should meet"

# --- non-bash session: structured no-shell-integration, no probe sent ---
$TD start -n td13sh --cmd sh --socket "$SOCK" >/dev/null || fail "sh start failed"
if $TD wait -n td13sh --shell-ready --timeout 5 >/dev/null 2>"$TMP/noint.json"; then
  fail "shell-ready without shell integration must fail"
fi
python3 -c "
import json,sys
e=json.load(open('$TMP/noint.json'))['error']
assert e['code']=='no-shell-integration', e
" || fail "expected no-shell-integration"

echo "E2E-13 PASS"
