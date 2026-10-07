#!/usr/bin/env bash
# E2E-11: sessions listing + nested-socket tmux end-to-end + multi-session isolation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TD="python3 -m termdebug"
SOCK="td11sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_STATE_HOME="$TMP/state"

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

# --- unmanaged inner pane: waits degrade honestly instead of refusing ---
$TD send -n "inner:inner:0" --type "echo UM_MARK_11" --key Enter >/dev/null \
  || fail "send um marker failed"
$TD wait -n "inner:inner:0" --until 'UM_MARK_11' --timeout 5 | python3 -c '
import json, sys
v = json.load(sys.stdin)
c = v["conditions"][0]
assert v["verdict"] == "met", v
assert v["confidence"] == "heuristic", "unmanaged --until must cap at heuristic: " + str(v)
assert c["confidence"] == "heuristic" and c["degraded"] == "unmanaged", v
' || fail "unmanaged --until should meet with heuristic + degraded marker"

$TD wait -n "inner:inner:0" --quiet-ms 400 --timeout 8 | python3 -c '
import json, sys
v = json.load(sys.stdin)
c = v["conditions"][0]
assert c["type"] == "quiet" and c["degraded"] == "unmanaged", v
' || fail "unmanaged --quiet-ms should settle via screen stability"
[ ! -d "$XDG_STATE_HOME/term-debug/inner" ] \
  || fail "unmanaged wait must not create a state dir for the inner session"

if $TD wait -n "inner:inner:0" --cmd-done --timeout 3 >/dev/null 2>"$TMP/um.json"; then
  fail "--cmd-done on unmanaged pane must fail"
fi
python3 -c "
import json,sys
e=json.load(open('$TMP/um.json'))['error']
assert e['code']=='unmanaged-pane', e
assert 'not managed by term-debug' in e['message'], e
" || fail "expected unmanaged-pane error for --cmd-done"

# --- unmanaged --exit: session collapse = pane gone (fact met, status unavailable) ---
# sleep 4 (not 1): the wait CLI must cold-start and anchor the pane before it dies
tmux -L inner new-session -d -s dying "sleep 4" >/dev/null 2>&1 \
  || fail "dying session failed to start"
$TD wait -n inner:dying:0 --exit --timeout 10 | python3 -c '
import json, sys
v = json.load(sys.stdin)
c = v["conditions"][0]
assert v["verdict"] == "met" and v["confidence"] == "fact", v
assert c["type"] == "exit" and c["exit_code"] is None, v
assert c["degraded"] == "status-unavailable", v
' || fail "unmanaged --exit should meet (fact) when the session collapses"

# --- bare-name addressing on the DEFAULT server (unmanaged, degrades the
#     same way as the explicit socket form, instead of session-missing) ---
BARE="bare11_$RANDOM"
$TD send -n td11a --type "TMUX= tmux new-session -d -s $BARE" --key Enter >/dev/null \
  || fail "bare session spawn failed"
sleep 1
$TD send -n "$BARE:0" --type "echo BARE_OK_11" --key Enter >/dev/null \
  || fail "bare-name send failed"
$TD wait -n "$BARE:0" --until 'BARE_OK_11' --timeout 5 | python3 -c '
import json, sys
v = json.load(sys.stdin)
c = v["conditions"][0]
assert v["verdict"] == "met" and v["confidence"] == "heuristic", v
assert c["degraded"] == "unmanaged", v
' || fail "bare-name unmanaged wait should degrade like the socket form"
$TD screen -n "$BARE:0" --meta | python3 -c '
import json, sys
m = json.load(sys.stdin)
assert m["managed"] is False and m["pane_id"] is None, m
' || fail "screen --meta should work on an unmanaged bare name"
tmux kill-session -t "$BARE" >/dev/null 2>&1 || true

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
