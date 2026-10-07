#!/usr/bin/env python3
"""Unit tests for mouse encoding, mode detection, and hex splitting."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from termuse.input import hex_to_args, mouse_encode, mouse_mode


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


def test_mode_combined_decset_enable():
    # Real TUIs often enable several modes with ONE combined sequence.
    m = mouse_mode("noise\x1b[?1000;1006hmore")
    assert m["enabled"] is True and m["sgr"] is True and m["normal"] is True


def test_mode_combined_decset_disable():
    tail = "\x1b[?1000h\x1b[?1006h\x1b[?1000;1006l"
    m = mouse_mode(tail)
    assert m["enabled"] is False and m["sgr"] is False


def test_mode_combined_motion_without_normal():
    m = mouse_mode("\x1b[?1002;1006h")
    assert m["enabled"] is True and m["motion"] is True
    assert m["normal"] is False and m["sgr"] is True


def test_mode_reenable_wins():
    tail = "\x1b[?1000h\x1b[?1000l\x1b[?1000h"
    assert mouse_mode(tail)["enabled"] is True


def test_mode_absent():
    assert mouse_mode("nothing here")["enabled"] is False


def test_hex_single_byte():
    assert hex_to_args("1c") == ["-H", "1c"]


def test_hex_multibyte_splits_per_byte():
    # tmux 3.x -H takes ONE byte per argument; a single long -H arg is dropped.
    assert hex_to_args("1b5b31333b3275") == [
        "-H", "1b", "-H", "5b", "-H", "31", "-H", "33", "-H", "3b", "-H", "32", "-H", "75"]


def test_hex_rejects_odd_and_nonhex():
    from termuse.errors import TDError
    for bad in ("1", "xyz", "12g"):
        try:
            hex_to_args(bad)
        except TDError:
            continue
        raise AssertionError(f"hex_to_args({bad!r}) should raise")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
