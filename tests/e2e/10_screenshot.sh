#!/usr/bin/env bash
# E2E-10: screenshot channel — png/jpg via Pillow, pillow-missing isolation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
TD="python3 -m termdebug"
SOCK="td10sock_$$_$RANDOM"
TMP="$(mktemp -d)"
export XDG_STATE_HOME="$TMP/state"

cleanup() { tmux -L "$SOCK" kill-server >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
fail() { echo "E2E-10 FAIL: $*"; exit 1; }

$TD start -n td10 --cmd bash --socket "$SOCK" --width 100 --height 30 >/dev/null \
  || fail "start failed"
printf 'hello screenshot\nline two\n' > "$TMP/hello.txt"
$TD send -n td10 --type "nano $TMP/hello.txt" --key Enter >/dev/null || fail "send nano failed"
$TD wait -n td10 --until 'GNU nano' --timeout 10 >/dev/null || fail "nano never opened"

# --- png + jpg renders ---
$TD screenshot -n td10 --format png -o "$TMP/s.png" >"$TMP/png.json" || fail "png render failed"
$TD screenshot -n td10 --format jpg -o "$TMP/s.jpg" >"$TMP/jpg.json" || fail "jpg render failed"
python3 - "$TMP/png.json" "$TMP/jpg.json" <<'PY' || fail "file assertions (see above)"
import json, sys
from PIL import Image
for jf, kind in ((sys.argv[1], "PNG"), (sys.argv[2], "JPEG")):
    r = json.load(open(jf))
    import os
    sz = os.path.getsize(r["path"])
    assert sz > 5120, f"{kind}: {sz} bytes (want >5KB)"
    im = Image.open(r["path"])
    assert im.format == kind, f"{kind}: got {im.format}"
    assert list(im.size) == r["size"], f"{kind}: file {im.size} vs claimed {r['size']}"
    W, H = r["grid"]
    assert r["size"][0] == W * r["charw"] and r["size"][1] == H * r["lineh"], r
PY

# --- pillow-missing: -S skips site-packages, so PIL is importable nowhere ---
if python3 -S -m termdebug screenshot -n td10 --format png -o "$TMP/s2.png" \
    >/dev/null 2>"$TMP/np.json"; then
  fail "screenshot without Pillow must fail"
fi
python3 -c "
import json,sys
e=json.load(open('$TMP/np.json'))['error']
assert e['code']=='pillow-missing', e
assert e['hint'], 'install hint missing'
" || fail "expected pillow-missing error"

echo "E2E-10 PASS"
