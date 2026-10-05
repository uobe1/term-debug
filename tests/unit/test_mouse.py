#!/usr/bin/env python3
"""Unit tests for mouse encoding and mode detection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from termdebug.input import mouse_encode, mouse_mode


def test_encode_press_release_one_based():
    assert mouse_encode(0, 9, 4, True) == "\x1b[<0;10;5M"
    assert mouse_encode(0, 9, 4, False) == "\x1b[<0;10;5m"


def test_encode_zero_origin_becomes_one():
    assert mouse_encode(0, 0, 0, True) == "\x1b[<0;1;1M"


def test_mode_enabled_sgr():
    tail = "noise\x1b[?1000h\x1b[?1006hmore"
    m = mouse_mode(tail)
    assert m["enabled"] is True and m["sgr"] is True and m["normal"] is True


def test_mode_disabled_after_exit():
    tail = "\x1b[?1000h\x1b[?1006h\x1b[?1000l\x1b[?1006l"
    m = mouse_mode(tail)
    assert m["enabled"] is False and m["sgr"] is False


def test_mode_reenable_wins():
    tail = "\x1b[?1000h\x1b[?1000l\x1b[?1000h"
    assert mouse_mode(tail)["enabled"] is True


def test_mode_absent():
    assert mouse_mode("nothing here")["enabled"] is False


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
