#!/usr/bin/env bash
# E2E-09: echo-broken detection (send warning) + fix-tty recovery.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TD="python3 $ROOT/term_debug.py"
SOCK="td09sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_CACHE_HOME="$TMP/cache"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-09 FAIL: $*"; exit 1; }

$TD start -n td09 --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start failed"

# break ECHO (this send itself echoes fine)
$TD send -n td09 --type "stty -echo" --key Enter >/dev/null || fail "send failed"
$TD wait -n td09 --quiet-ms 500 --timeout 5 >/dev/null || fail "prompt never settled"

# --- typing into an ECHO-less pane warns (not errors) ---
$TD send -n td09 --type "echo hi" >/dev/null 2>&1 >"$TMP/warn.json" \
  || fail "send must not fail on broken echo"
python3 -c "
import json,sys
r=json.load(open('$TMP/warn.json'))
assert r.get('warning')=='tty-echo-broken', r
assert r['ok'] is True, r
" || fail "expected tty-echo-broken warning"

# --- fix-tty restores echo ---
$TD fix-tty -n td09 >/dev/null || fail "fix-tty failed"
$TD send -n td09 --type "stty -a" --key Enter >/dev/null || fail "send stty -a failed"
$TD wait -n td09 --until 'icanon iexten echo' --timeout 5 >/dev/null \
  || fail "stty -a should show echo enabled after fix-tty"

# --- typing echoes again: no warning ---
$TD send -n td09 --type "echo RECOVERED_9" --key Enter >"$TMP/fixed.json" \
  || fail "send after fix failed"
python3 -c "
import json,sys
r=json.load(open('$TMP/fixed.json'))
assert 'warning' not in r or r.get('warning') is None, r
" || fail "warning should be gone after fix-tty"
$TD wait -n td09 --until 'RECOVERED_9' --timeout 5 >/dev/null || fail "roundtrip after fix"

echo "E2E-09 PASS"
