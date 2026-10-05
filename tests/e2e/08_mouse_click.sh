#!/usr/bin/env bash
# E2E-08: mouse mode detection + SGR click injection.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TD="python3 $ROOT/term_debug.py"
SOCK="td08sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_CACHE_HOME="$TMP/cache"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-08 FAIL: $*"; exit 1; }

# --- mouse-aware curses program ---
$TD start -n td08 --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start failed"
$TD send -n td08 --type "python3 $ROOT/tests/fixtures/curses_mouse.py" --key Enter >/dev/null \
  || fail "send fixture failed"
$TD wait -n td08 --until 'MOUSE_READY' --timeout 10 >/dev/null || fail "fixture never started"

# --- detection: enabled + SGR encoding ---
$TD mouse-detect -n td08 | python3 -c '
import json, sys
m = json.load(sys.stdin)
assert m["enabled"] is True, m
assert m["sgr"] is True, m
' || fail "mouse-detect should report enabled+sgr"

# --- click at screen coords (1-based CLI) -> curses prints 0-based ---
$TD click -n td08 10 5 >/dev/null || fail "click failed"
$TD wait -n td08 --until 'CLICKED:9,4' --timeout 5 >/dev/null \
  || fail "expected CLICKED:9,4 (0-based conversion)"

# --- control: clicking inside a plain bash pane is a structured error ---
$TD start -n td08plain --cmd bash --socket "$SOCK" >/dev/null || fail "plain start failed"
if $TD click -n td08plain 3 3 >/dev/null 2>"$TMP/noerr.json"; then
  fail "click without mouse mode must fail"
fi
python3 -c "
import json,sys
e=json.load(open('$TMP/noerr.json'))['error']
assert e['code']=='mouse-not-enabled', e
" || fail "expected mouse-not-enabled error"

echo "E2E-08 PASS"
