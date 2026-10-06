#!/usr/bin/env bash
# E2E-06: --exit condition, signal death with respawn hint, EOF early-termination.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TD="python3 -m termdebug"
SOCK="td06sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_STATE_HOME="$TMP/state"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-06 FAIL: $*"; exit 1; }

# --- 1: pane command exits 7 -> --exit --expect-code 7 (fact) ---
$TD start -n td06a --cmd "sh -c 'exit 7'" --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start failed"
$TD wait -n td06a --exit --expect-code 7 --timeout 10 | python3 -c '
import json, sys
v = json.load(sys.stdin)
assert v["verdict"] == "met" and v["confidence"] == "fact", v
assert v["conditions"][0]["type"] == "exit", v
' || fail "--exit expect 7"

# --- 2: SIGKILL -> structured pane-dead-by-signal + respawn hint ---
$TD start -n td06b --cmd bash --socket "$SOCK" >/dev/null || fail "start b failed"
$TD send -n td06b --type "kill -9 \$\$" --key Enter >/dev/null || fail "send failed"
if $TD wait -n td06b --exit --timeout 10 2>"$TMP/sig.json"; then
  fail "signal death must not be a 'met' verdict"
fi
python3 -c "
import json,sys
e=json.load(open('$TMP/sig.json'))['error']
assert e['code']=='pane-dead-by-signal', e
assert 'KILL' in json.dumps(e['evidence']), e
assert e['hint'], 'respawn hint missing'
" || fail "signal-death JSON invalid"

# --- 3: EOF early-termination during --cmd-done (no 30s hang) ---
$TD start -n td06c --cmd bash --socket "$SOCK" >/dev/null || fail "start c failed"
$TD send -n td06c --type "exit" --key Enter >/dev/null || fail "send exit failed"
T0="$(date +%s%N)"
if $TD wait -n td06c --cmd-done --timeout 30 2>"$TMP/dead.json"; then
  fail "pane death during cmd-done must fail"
fi
T1="$(date +%s%N)"
[ $(( (T1 - T0) / 1000000 )) -lt 5000 ] || fail "pane-dead took >5s (EOF early-termination missing)"
python3 -c "
import json,sys
e=json.load(open('$TMP/dead.json'))['error']
assert e['code']=='pane-dead', e
" || fail "pane-dead JSON invalid"

echo "E2E-06 PASS"
