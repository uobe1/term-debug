#!/usr/bin/env python3
"""Unit tests for the ShellReady condition (wait --shell-ready)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from termdebug import waiting
from termdebug.errors import TDError
from termdebug.waiting import ShellReady, UntilRegex, WaitContext


def ctx_with(screen: str) -> WaitContext:
    return WaitContext(capture=lambda sb: screen,
                       meta=lambda: {"cursor_x": 0, "cursor_y": 0})


def test_label_confidence_and_json_shape():
    sr = ShellReady("td-unit-any")
    assert sr.label == "shell-ready"
    assert sr.confidence == "fact"
    j = sr.to_json(False)
    assert j["type"] == "shell-ready" and j["met"] is False
    assert j["expect_code"] == 0, "the probe always expects exit 0"


def test_evaluate_delegates_to_cmd_done():
    sr = ShellReady("td-unit-any")

    class FakeDone:
        exit_code = 0

        def evaluate(self, ctx):
            return True

        def to_json(self, met):
            return {"type": "cmd-done", "confidence": "fact", "met": met,
                    "expect_code": 0, "exit_code": 0}

    sr._done = FakeDone()
    assert sr.evaluate(ctx_with("$ "))
    j = sr.to_json(True)
    assert j["type"] == "shell-ready" and j["exit_code"] == 0


def test_evaluate_without_state_raises_structured():
    sr = ShellReady("td-unit-definitely-missing-state")
    try:
        sr.evaluate(ctx_with("$ "))
    except TDError as e:
        assert e.code == "session-missing"
        return
    raise AssertionError("expected TDError for missing state.json")


def test_allof_takes_weakest_with_until():
    sr = ShellReady("td-unit-any")
    combo = waiting.AllOf([sr, UntilRegex("$ ")])
    assert combo.confidence == "inference", "weakest member wins"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
