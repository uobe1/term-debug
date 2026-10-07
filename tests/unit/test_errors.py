#!/usr/bin/env python3
"""Unit tests for termuse.errors — pure asserts, no pytest."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from termuse.errors import TDError, ERROR_CODES


def test_to_json_shape():
    e = TDError("timeout", "wait timed out after 3s",
                hint="increase --timeout", evidence={"screen": "abc"})
    obj = json.loads(e.to_json())
    assert "error" in obj, f"missing top-level 'error': {obj}"
    err = obj["error"]
    assert err["code"] == "timeout"
    assert err["message"] == "wait timed out after 3s"
    assert err["hint"] == "increase --timeout"
    assert err["evidence"] == {"screen": "abc"}


def test_optional_fields_default_null():
    e = TDError("session-missing", "no such session")
    err = json.loads(e.to_json())["error"]
    assert err["hint"] is None
    assert err["evidence"] is None


def test_error_code_table():
    expected = {
        "session-missing", "invalid-arguments", "socket-unreachable",
        "pane-dead", "pane-dead-by-signal", "no-shell-integration",
        "shell-not-ready", "unmanaged-pane", "expect-code-mismatch",
        "timeout", "mouse-not-enabled", "tty-echo-broken",
    }
    missing = expected - set(ERROR_CODES)
    assert not missing, f"missing codes in ERROR_CODES: {missing}"


def test_exit_code_nonzero():
    assert TDError("timeout", "x").exit_code != 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
