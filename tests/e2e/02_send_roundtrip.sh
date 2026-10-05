#!/usr/bin/env bash
# E2E-02: send roundtrip — text/key separation, i-events, send offset.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TD="python3 $ROOT/term_debug.py"
NAME="td02_$$_$RANDOM"
SOCK="td02sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_CACHE_HOME="$TMP/cache"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-02 FAIL: $*"; exit 1; }

$TD start -n "$NAME" --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start failed"
DIR="$XDG_CACHE_HOME/term-debug/$NAME"

get_offset() { python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['last_send_offset'])" "$DIR/state.json"; }

# --- send #1: literal text only ---
$TD send -n "$NAME" --type "echo TD2_OK" >/dev/null || fail "send --type failed"
OFF1="$(get_offset)"
[ -n "$OFF1" ] || fail "last_send_offset missing after send #1"

# --- send #2: Enter only, separate call (the split-send red line) ---
$TD send -n "$NAME" --key Enter >/dev/null || fail "send --key failed"
OFF2="$(get_offset)"
[ "$OFF2" -gt "$OFF1" ] || fail "last_send_offset did not increase: $OFF1 -> $OFF2"

# --- roundtrip: wait for output, assert screen shows it ---
$TD wait -n "$NAME" --until 'TD2_OK' --timeout 5 >/dev/null || fail "wait --until TD2_OK did not match"
SCREEN="$(tmux -L "$SOCK" capture-pane -p -t "$NAME" 2>/dev/null)"
echo "$SCREEN" | grep -q "TD2_OK" || fail "screen does not contain TD2_OK"
# option-order red line: send-keys must never leak "-t <name>" into the pane
if echo "$SCREEN" | grep -q -- "-t$NAME"; then
  fail "pane polluted by literal -t target (send-keys option order bug)"
fi

# --- evidence: i-events recorded, Enter logged ---
grep -qE '\["?i"?|"i"' "$DIR/raw.log" && grep -E '^\[.*"i".*"Enter"' "$DIR/raw.log" >/dev/null \
  || fail "raw.log lacks i-event recording Enter"

echo "E2E-02 PASS"
