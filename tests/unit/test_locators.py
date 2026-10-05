#!/usr/bin/env python3
"""Unit tests for the (socket, session, window, pane) locator."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from termdebug.tmuxio import parse_target


def test_session_only():
    t = parse_target("s")
    assert (t.socket, t.session, t.window, t.pane) == (None, "s", None, None), t


def test_session_window():
    t = parse_target("s:1")
    assert (t.socket, t.session, t.window, t.pane) == (None, "s", "1", None), t


def test_session_window_pane():
    t = parse_target("s:1.0")
    assert (t.socket, t.session, t.window, t.pane) == (None, "s", "1", "0"), t


def test_socket_prefixed():
    t = parse_target("sock:s:1.0")
    assert (t.socket, t.session, t.window, t.pane) == ("sock", "s", "1", "0"), t


def test_roundtrip_to_arg():
    assert parse_target("s:1.0").to_arg() == "s:1.0"
    assert parse_target("s:1").to_arg() == "s:1"
    assert parse_target("s").to_arg() == "s"


def test_malformed_rejected():
    from termdebug.errors import TDError
    for bad in (":", ":1.0", "a:b:c:d:e"):
        try:
            parse_target(bad)
        except TDError:
            pass
        else:
            raise AssertionError(f"parse_target({bad!r}) should raise TDError")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
