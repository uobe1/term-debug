#!/usr/bin/env bash
# E2E-15: screen --find — locate text, click it (1-based click-ready coords).
# The mouse fixture paints "MOUSE_READY q=quit" on visual row 2 and reports
# clicks with 0-based coords (like curses programs do).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TD="python3 -m termdebug"
NAME="td15_$$_$RANDOM"
SOCK="td15sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_STATE_HOME="$TMP/state"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-15 FAIL: $*"; exit 1; }

$TD start -n "$NAME" --cmd bash --socket "$SOCK" --width 120 --height 30 >/dev/null \
  || fail "start failed"
$TD send -n "$NAME" --type "python3 $ROOT/tests/fixtures/curses_mouse.py" --key Enter >/dev/null \
  || fail "send fixture failed"
$TD wait -n "$NAME" --until 'MOUSE_READY' --timeout 10 >/dev/null || fail "fixture never started"

# --- find reports 1-based click-ready coordinates ---
$TD screen -n "$NAME" --find quit | python3 -c '
import json, sys
m = json.load(sys.stdin)
assert m == [{"text": "quit", "x": 15, "y": 2}], m
' || fail "--find quit should report x=15 y=2"

# --- the coordinates feed straight into click ---
$TD click -n "$NAME" 15 2 >/dev/null || fail "click failed"
$TD wait -n "$NAME" --until 'CLICKED:14,1' --timeout 5 >/dev/null \
  || fail "click at find-coords should report 0-based CLICKED:14,1"

# --- no match: empty list, not an error ---
$TD screen -n "$NAME" --find ABSENT | python3 -c '
import json, sys
assert json.load(sys.stdin) == []
' || fail "--find ABSENT should return []"

echo "E2E-15 PASS"
