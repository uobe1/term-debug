#!/usr/bin/env python3
"""Unit tests for new CLI flags: send --repeat/--delay, wait --shell-ready."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from termuse.cli import build_parser
from termuse.errors import ERROR_CODES


def test_send_repeat_defaults():
    args = build_parser().parse_args(["send", "-n", "x", "--key", "Up"])
    assert args.repeat == 1
    assert args.delay == 0.35, "default gap clears real menu debouncing"


def test_send_repeat_parse():
    args = build_parser().parse_args(
        ["send", "-n", "x", "--key", "C-c", "--repeat", "2", "--delay", "0.3"])
    assert args.repeat == 2 and args.delay == 0.3


def test_wait_shell_ready_default_off():
    args = build_parser().parse_args(["wait", "-n", "x", "--cmd-done"])
    assert args.shell_ready is False


def test_wait_shell_ready_parse():
    args = build_parser().parse_args(
        ["wait", "-n", "x", "--shell-ready", "--timeout", "5"])
    assert args.shell_ready is True


def test_shell_not_ready_registered():
    assert "shell-not-ready" in ERROR_CODES


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
