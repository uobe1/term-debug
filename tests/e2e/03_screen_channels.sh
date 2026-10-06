#!/usr/bin/env bash
# E2E-03: screen text channels — meta / trailing-space / join / scrollback /
# SGR grid / runs / grep-by-attribute / element-at.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TD="python3 -m termdebug"
NAME="td03_$$_$RANDOM"
SOCK="td03sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_STATE_HOME="$TMP/state"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-03 FAIL: $*"; exit 1; }

$TD start -n "$NAME" --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start failed"

# Colored line with trailing spaces + a 200-char line. Both stay on screen.
$TD send -n "$NAME" --type "printf '\\033[31mRED_TEXT\\033[0m      \\n'" --key Enter >/dev/null \
  || fail "send printf failed"
$TD send -n "$NAME" --type "printf 'B%.0s' {1..200}" --key Enter >/dev/null \
  || fail "send long-line failed"
$TD wait -n "$NAME" --until 'B{100}' --timeout 5 >/dev/null || fail "B line never appeared"

# --- --meta: cursor + main screen ---
$TD screen -n "$NAME" --meta | python3 -c '
import json, sys
m = json.load(sys.stdin)
assert "cursor_x" in m and "cursor_y" in m, f"no cursor fields: {m}"
assert m["alternate_on"] is False, f"bash should be on main screen: {m}"
assert "history_size" in m, f"no history_size: {m}"
' || fail "--meta invalid (see assertion above)"

# --- -N keeps trailing spaces (self-heal red line: default strips them) ---
$TD screen -n "$NAME" -N | grep -qE 'RED_TEXT +$' \
  || fail "-N should keep trailing spaces after RED_TEXT"
if $TD screen -n "$NAME" | grep -qE 'RED_TEXT +$'; then
  fail "default screen should strip trailing spaces"
fi

# --- -J joins wrapped lines: 200-char line restored on width-100 pane ---
$TD screen -n "$NAME" -J | grep -qE 'B{200}' \
  || fail "-J should join the 200-char line into one logical line"
if $TD screen -n "$NAME" -J | grep -qE 'B{300}'; then
  fail "-J joined too much (B{300} found)"
fi
$TD screen -n "$NAME" | grep -qE '^B{100}$' \
  || fail "default capture should show the wrapped 100-char physical line"

# --- --grid: SGR cell grid with fg names ---
$TD screen -n "$NAME" --grid > "$TMP/grid.json" || fail "--grid exited non-zero"
python3 - "$TMP/grid.json" <<'PY' || fail "--grid invalid (see assertion above)"
import json, sys
grid = json.load(open(sys.argv[1]))
red = [c for row in grid for c in row
       if c and c.get("fg") == "red" and c.get("char") in set("RED_TEXT")]
assert len(red) >= 8, f"expected RED_TEXT cells with fg=red, got {len(red)}"
r0 = red[0]
assert all(k in r0 for k in ("x", "y", "bg", "attrs")), f"cell missing fields: {r0}"
PY

# --- --runs: attribute run view compresses the row ---
$TD screen -n "$NAME" --runs > "$TMP/runs.json" || fail "--runs exited non-zero"
python3 - "$TMP/runs.json" <<'PY' || fail "--runs invalid (see assertion above)"
import json, sys
rows = json.load(open(sys.argv[1]))
hit = [r for row in rows for r in row if r.get("fg") == "red" and r.get("text") == "RED_TEXT"]
assert hit, f'expected run {{"fg":"red","text":"RED_TEXT"}} in {rows[:5]}...'
PY

# --- --grep --fg red: attribute search hits the line ---
$TD screen -n "$NAME" --grep --fg red | grep -q "RED_TEXT" \
  || fail "--grep --fg red should hit the RED_TEXT line"

# --- --element-at: cell lookup matches grid ---
python3 - "$TMP/grid.json" "$NAME" "$TD" <<'PY' || fail "--element-at mismatch (see above)"
import json, subprocess, sys
grid = json.load(open(sys.argv[1]))
name, td = sys.argv[2], sys.argv[3]
target = next(c for row in grid for c in row if c and c.get("char") == "R" and c.get("fg") == "red")
out = subprocess.run([*td.split(), "screen", "-n", name,
                      "--element-at", str(target["x"]), str(target["y"])],
                     capture_output=True, text=True)
assert out.returncode == 0, out.stderr
cell = json.loads(out.stdout)
assert cell["char"] == "R" and cell["fg"] == "red", f"element-at returned {cell}"
assert (cell["x"], cell["y"]) == (target["x"], target["y"]), f"coords differ: {cell}"
PY

# --- --scrollback: reach lines that scrolled off (seq pushes content out) ---
$TD send -n "$NAME" --type "seq 1 200" --key Enter >/dev/null || fail "send seq failed"
$TD wait -n "$NAME" --until '^200$' --timeout 5 >/dev/null || fail "seq output never appeared"
$TD screen -n "$NAME" --scrollback 250 | grep -qx '1' \
  || fail "--scrollback should contain seq line '1' (scrolled off)"

echo "E2E-03 PASS"
