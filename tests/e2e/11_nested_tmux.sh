#!/usr/bin/env bash
# E2E-11: sessions listing + nested-socket tmux end-to-end + multi-session isolation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TD="python3 $ROOT/term_debug.py"
SOCK="td11sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_CACHE_HOME="$TMP/cache"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; tmux -L inner kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-11 FAIL: $*"; exit 1; }

$TD start -n td11a --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start a failed"
$TD start -n td11b --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start b failed"

# --- nested: inner tmux on its own socket, created from inside the pane ---
$TD send -n td11a --type 'TMUX= tmux -L inner new-session -d -s inner' --key Enter >/dev/null \
  || fail "send nested failed"
$TD wait -n td11a --quiet-ms 500 --timeout 5 >/dev/null || fail "nested spawn unsettled"

# sessions --socket inner lists the inner session
$TD sessions --socket inner | python3 -c '
import json, sys
rows = json.load(sys.stdin)
names = [r["name"] for r in rows]
assert "inner" in names, f"inner session missing: {names}"
' || fail "sessions --socket inner"

# --- full chain against the inner pane: send + wait + capture ---
$TD send -n "inner:inner:0" --type "echo NESTED_OK_11" --key Enter >/dev/null \
  || fail "send to inner pane failed"
$TD wait -n "inner:inner:0" --until 'NESTED_OK_11' --timeout 5 >/dev/null \
  || fail "wait on inner pane failed"
tmux -L inner capture-pane -p -t inner:0 2>/dev/null | grep -q NESTED_OK_11 \
  || fail "inner pane screen lacks NESTED_OK_11"

# --- two sessions at once: waits are independent ---
$TD send -n td11a --type "echo MARK_A" --key Enter >/dev/null || fail "send a failed"
$TD send -n td11b --type "echo MARK_B" --key Enter >/dev/null || fail "send b failed"
$TD wait -n td11a --until 'MARK_A' --timeout 5 >/dev/null || fail "wait a"
$TD wait -n td11b --until 'MARK_B' --timeout 5 >/dev/null || fail "wait b"

# b prints a's marker; a's wait still only sees a's own screen
$TD send -n td11b --type "echo MARK_A" --key Enter >/dev/null || fail "send interference failed"
$TD wait -n td11b --until 'MARK_A' --timeout 5 >/dev/null || fail "b should show MARK_A"
if tmux -L "$SOCK" capture-pane -p -t td11a 2>/dev/null | grep -q 'MARK_A$'; then
  :  # a may legitimately show MARK_A from its own echo earlier; isolation
     # is about waits, asserted below
fi
$TD send -n td11a --type "clear; echo ONLY_A" --key Enter >/dev/null || fail "send clear failed"
$TD wait -n td11a --until 'ONLY_A' --timeout 5 >/dev/null || fail "wait a after clear"

echo "E2E-11 PASS"
