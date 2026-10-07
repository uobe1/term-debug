#!/usr/bin/env bash
# E2E-01: start/stop + v2 recorder basics.
# Drives only the CLI; asserts on tmux state and the on-disk evidence store.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TD="python3 -m termuse"
NAME="td01_$$_$RANDOM"
SOCK="td01sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_STATE_HOME="$TMP/state"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-01 FAIL: $*"; exit 1; }

# --- start ---
$TD start -n "$NAME" --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start exited non-zero"

tmux -L "$SOCK" has-session -t "$NAME" 2>/dev/null \
  || fail "tmux has-session: session $NAME not found on socket $SOCK"

DIR="$XDG_STATE_HOME/term-use/$NAME"
[ -f "$DIR/raw.log" ] || fail "raw.log missing at $DIR"

# raw.log first line: asciicast v2 header with matching width/height
head -n 1 "$DIR/raw.log" | python3 -c '
import json, sys
h = json.loads(sys.stdin.read())
assert h.get("version") == 2, f"version != 2: {h}"
assert h.get("width") == 100, f"width != 100: {h}"
assert h.get("height") == 30, f"height != 30: {h}"
' || fail "raw.log header invalid (see assertion above)"

# state.json: pane_id (%N), shell_integration field, socket/size recorded
python3 - "$DIR/state.json" "$SOCK" <<'PY' || fail "state.json invalid (see assertion above)"
import json, sys
s = json.load(open(sys.argv[1]))
sock = sys.argv[2]
assert s["pane_id"].startswith("%"), f"pane_id not %N: {s['pane_id']!r}"
assert "shell_integration" in s, f"no shell_integration field: {sorted(s)}"
assert s["shell_integration"] is True, f"bash sessions get OSC 133 injection: {s}"
assert s["socket"] == sock, f"socket mismatch: {s['socket']!r} != {sock!r}"
assert s["width"] == 100 and s["height"] == 30, f"size mismatch: {s}"
PY

# --- stop ---
$TD stop -n "$NAME" >/dev/null || fail "stop exited non-zero"
if tmux -L "$SOCK" has-session -t "$NAME" 2>/dev/null; then
  fail "session $NAME still alive after stop"
fi

echo "E2E-01 PASS"
