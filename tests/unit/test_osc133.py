#!/usr/bin/env python3
"""Unit tests for the OSC 133 state machine — real byte samples."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from termdebug.osc133 import OSC133Scanner


def kinds(events):
    return [(e["kind"], e.get("code")) for e in events]


def feed_all(s: str) -> list[dict]:
    sc = OSC133Scanner()
    return sc.feed(s)


def test_full_lifecycle_bel():
    s = ("\x1b]133;A\x07prompt \x1b]133;B\x07$ cmd\x1b]133;C\x07"
         "output...\x1b]133;D;0\x07")
    assert kinds(feed_all(s)) == [("prompt", None), ("cmdline", None),
                                  ("preexec", None), ("done", 0)]


def test_esc_st_terminator():
    s = "\x1b]133;C\x1b\\output\x1b]133;D;42\x1b\\"
    assert kinds(feed_all(s)) == [("preexec", None), ("done", 42)]


def test_various_exit_codes():
    for code in (0, 1, 42, 130):
        s = f"\x1b]133;C\x07\x1b]133;D;{code}\x07"
        assert kinds(feed_all(s)) == [("preexec", None), ("done", code)]


def test_skips_csi_2004_and_other_osc():
    s = ("\x1b[?2004h\x1b]0;window title\x07\x1b]133;C\x07"
         "out\x1b]133;D;7\x07\x1b[?2004l")
    assert kinds(feed_all(s)) == [("preexec", None), ("done", 7)]


def test_chunked_feed_keeps_partial():
    sc = OSC133Scanner()
    assert sc.feed("\x1b]13") == []
    sc.feed("3;C\x07output\x1b]133;D;0\x07rest")
    assert kinds(sc.events) == [("preexec", None), ("done", 0)]


def test_d_without_c_is_aborted():
    s = "\x1b]133;A\x07\x1b]133;B\x07\x1b]133;D;0\x07"
    assert kinds(feed_all(s)) == [("prompt", None), ("cmdline", None),
                                  ("aborted", 0)]


def test_c_resets_between_commands():
    s = ("\x1b]133;A\x07\x1b]133;B\x07\x1b]133;C\x07\x1b]133;D;1\x07"
         "next prompt\x1b]133;D;5\x07")  # second D has no fresh C
    evs = feed_all(s)
    assert kinds(evs) == [("prompt", None), ("cmdline", None),
                          ("preexec", None), ("done", 1), ("aborted", 5)]


def test_plain_text_ignored():
    assert feed_all("hello world 133;D;0 nothing \x07 to see") == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
