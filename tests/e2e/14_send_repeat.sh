#!/usr/bin/env bash
# E2E-14: send --repeat N --delay S — debounced menus / double-key rhythms.
# The menu_debounce fixture applies an arrow only if >= 0.45s elapsed since
# the last applied arrow and drops the rest (debounced menu widget behavior).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TD="python3 -m termuse"
NAME="td14_$$_$RANDOM"
SOCK="td14sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_STATE_HOME="$TMP/state"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-14 FAIL: $*"; exit 1; }

selected() { $TD screen -n "$NAME" | grep -o 'SELECTED:[0-9]*'; }

$TD start -n "$NAME" --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start failed"
$TD send -n "$NAME" --type "python3 $ROOT/tests/fixtures/menu_debounce.py" --key Enter >/dev/null \
  || fail "send fixture failed"
$TD wait -n "$NAME" --until 'SELECTED:0' --timeout 10 >/dev/null || fail "fixture never started"

# --- control: one call with two Ups is debounced to a single move ---
$TD send -n "$NAME" --key Up --key Up >/dev/null || fail "send failed"
sleep 1
[ "$(selected)" = "SELECTED:1" ] || fail "one-call two Ups should move once, got: $(selected)"

# --- --repeat 2 --delay 0.6: each repetition is a full independent send ---
BEFORE="$(grep -o '"key": "Up"' "$XDG_STATE_HOME/term-use/$NAME/raw.log" | wc -l)"
$TD send -n "$NAME" --key Up --repeat 2 --delay 0.6 >/dev/null || fail "send --repeat failed"
sleep 2
[ "$(selected)" = "SELECTED:3" ] || fail "--repeat 2 --delay 0.6 should move twice, got: $(selected)"
AFTER="$(grep -o '"key": "Up"' "$XDG_STATE_HOME/term-use/$NAME/raw.log" | wc -l)"
[ "$((AFTER - BEFORE))" -eq 2 ] || fail "expected 2 i-event Up records, got $((AFTER - BEFORE))"

# --- red line: each repetition must stay text/key separated (works at all) ---
$TD send -n "$NAME" --key Down --repeat 1 >/dev/null || fail "repeat 1 failed"
sleep 1
[ "$(selected)" = "SELECTED:2" ] || fail "repeat 1 Down should move once, got: $(selected)"

# --- validation: repeat < 1 is a structured error, nothing is sent ---
if $TD send -n "$NAME" --key Up --repeat 0 >/dev/null 2>"$TMP/bad.json"; then
  fail "--repeat 0 must fail"
fi
python3 -c "
import json,sys
e=json.load(open('$TMP/bad.json'))['error']
assert e['code']=='invalid-arguments', e
" || fail "expected invalid-arguments error for --repeat 0"

echo "E2E-14 PASS"
