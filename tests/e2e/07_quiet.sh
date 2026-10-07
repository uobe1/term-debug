#!/usr/bin/env bash
# E2E-07: --quiet-ms animation-immune double sampling (heuristic confidence).
#  A: periodic output -> quiet fires only after the last tick
#  B: spinner redraws -> quiet fires only after the spinner stops
#  C: unclosed CSI 2026 (begin-sync) -> never settles
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TD="python3 -m termuse"
SOCK="td07sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_STATE_HOME="$TMP/state"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-07 FAIL: $*"; exit 1; }

start() { $TD start -n "$1" --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null || fail "start $1 failed"; }

# --- A: periodic ticks; quiet(1000) must fire after tick8 ---
start td07a
$TD send -n td07a --type 'for i in $(seq 8); do echo tick$i; sleep 0.3; done' --key Enter >/dev/null \
  || fail "send loop failed"
$TD wait -n td07a --quiet-ms 1000 --timeout 10 >/dev/null || fail "A: quiet never fired"
python3 - "$XDG_STATE_HOME/term-use/td07a/raw.log" <<'PY' || fail "A: ordering assertion (see above)"
import json, sys
tick8 = wait_m = None
for line in open(sys.argv[1]):
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if isinstance(ev, list) and ev[1] == "o" and "tick8" in ev[2]:
        tick8 = ev[0]
    if isinstance(ev, list) and ev[1] == "m" and ev[2].get("event") == "wait-met":
        wait_m = ev[0]
assert tick8 is not None and wait_m is not None, (tick8, wait_m)
assert wait_m - tick8 >= 0.9, f"quiet fired {wait_m - tick8:.2f}s after tick8 (want >=0.9)"
PY

# --- B: spinner; quiet(400) AND until(first frame) must fire after stop ---
# The AND-composition matters: on a slow device the interpreter start-up is
# itself a quiet window, so quiet alone would fire before the animation
# begins. until anchors "the program is running", quiet then checks stillness.
start td07b
$TD send -n td07b --type "python3 $ROOT/tests/fixtures/spinner.py" --key Enter >/dev/null \
  || fail "send spinner failed"
$TD wait -n td07b --until 'working|SPINNER_DONE' --quiet-ms 400 --timeout 8 >/dev/null \
  || fail "B: quiet never fired"
python3 - "$XDG_STATE_HOME/term-use/td07b/raw.log" <<'PY' || fail "B: ordering assertion (see above)"
import json, sys
text, spans, wait_m = "", [], None
for line in open(sys.argv[1]):
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if isinstance(ev, list) and ev[1] == "o" and isinstance(ev[2], str):
        spans.append((len(text), len(text) + len(ev[2]), ev[0]))
        text += ev[2]
    elif isinstance(ev, list) and ev[1] == "m" and ev[2].get("event") == "wait-met":
        wait_m = ev[0]
idx = text.find("SPINNER_DONE")
assert idx >= 0, "SPINNER_DONE never reached the raw stream"
done_ts = next(ts for a, b, ts in spans if a <= idx < b)
assert wait_m >= done_ts - 0.05, f"quiet fired {done_ts - wait_m:.2f}s BEFORE spinner stopped"
PY

# --- C: unclosed CSI 2026 -> must not settle (timeout) ---
start td07c
$TD send -n td07c --type "printf '\\033[?2026h'" --key Enter >/dev/null || fail "send 2026 failed"
if $TD wait -n td07c --quiet-ms 800 --timeout 2 >/dev/null 2>"$TMP/c.json"; then
  fail "C: quiet fired despite unclosed CSI 2026"
fi
python3 -c "
import json,sys
e=json.load(open('$TMP/c.json'))['error']
assert e['code']=='timeout', e
" || fail "C: expected timeout error"

echo "E2E-07 PASS"
