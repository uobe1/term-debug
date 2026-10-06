#!/usr/bin/env python3
"""Unit tests for the wait engine — conditions, AND composition, verdict JSON."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from termdebug.waiting import AllOf, UntilRegex, WaitContext, timeout_evidence


def ctx_with(screen: str, meta=None) -> WaitContext:
    return WaitContext(capture=lambda sb: screen, meta=meta or (lambda: {"cursor_x": 3, "cursor_y": 1}))


def test_until_plain_match():
    assert UntilRegex("hello").evaluate(ctx_with("say hello\n$ "))


def test_until_trailing_space_self_heal():
    # 'TD4: ' printed then rstripped by the terminal: raw screen lacks the space.
    assert UntilRegex("TD4: ").evaluate(ctx_with("echo TD4:\n$ "))
    assert not UntilRegex("TD4: x").evaluate(ctx_with("echo TD4:\n$ "))


def test_until_multiline_and_line_anchor():
    assert UntilRegex("^300$").evaluate(ctx_with("299\n300\n$ "))
    assert not UntilRegex("^30$").evaluate(ctx_with("299\n300\n$ "))


def test_until_scrollback_window():
    # History only reachable when the capture includes it.
    ctx = WaitContext(capture=lambda sb: ("1\n2\n7\n$ " if sb else "$ "),
                      meta=lambda: {"cursor_x": 0, "cursor_y": 0})
    assert UntilRegex("^7$", scrollback=500).evaluate(ctx)
    assert not UntilRegex("^7$").evaluate(ctx)


def test_allof_and_composition():
    ctx = ctx_with("ready\n7\n$ ")
    both = AllOf([UntilRegex("ready"), UntilRegex("^7$")])
    assert both.evaluate(ctx)
    assert both.confidence == "inference"
    one_fails = AllOf([UntilRegex("ready"), UntilRegex("NEVER")])
    assert not one_fails.evaluate(ctx)


def test_allof_confidence_takes_weakest():
    class FakeFact:
        label, confidence = "fake-fact", "fact"
        def evaluate(self, ctx):
            return True
        def to_json(self, met):
            return {"type": self.label, "confidence": self.confidence, "met": met}

    combo = AllOf([FakeFact(), UntilRegex("x")])
    assert combo.confidence == "inference", "weakest wins"


def test_allof_json_shape():
    j = AllOf([UntilRegex("a")]).to_json(True)
    assert j["type"] == "all-of" and j["met"] is True
    assert j["conditions"][0]["pattern"] == "a"


def test_timeout_evidence_shape():
    ev = timeout_evidence(ctx_with("last screen\n$ "), UntilRegex("NEVER"))
    assert ev["screen"].strip()
    assert ev["cursor"] == {"x": 3, "y": 1}
    assert ev["conditions"][0]["met"] is False


def test_empty_allof_rejected():
    try:
        AllOf([])
    except ValueError:
        return
    raise AssertionError("AllOf([]) should raise")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
