#!/usr/bin/env python3
"""Unit tests for the wait engine — conditions, AND composition, verdict JSON."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from termdebug.errors import TDError
from termdebug.waiting import (AllOf, QuietCondition, UntilRegex, WaitContext,
                               timeout_evidence, timeout_hint)


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


def test_until_unmanaged_capped_and_marked():
    # Nested tmux (no state.json): echo-suspect detection cannot run, so the
    # claim is capped at heuristic and the verdict says why — degrade, not refuse.
    ur = UntilRegex("hello", session="inner", managed=False)
    assert ur.confidence == "heuristic"
    assert ur.degraded == "unmanaged"
    assert ur.evaluate(ctx_with("say hello\n$ "))
    j = ur.to_json(True)
    assert j["confidence"] == "heuristic" and j["degraded"] == "unmanaged"


def test_allof_capped_by_unmanaged_member():
    class FakeFact:
        label, confidence = "fake-fact", "fact"
        def evaluate(self, ctx):
            return True
        def to_json(self, met):
            return {"type": self.label, "confidence": self.confidence, "met": met}

    combo = AllOf([FakeFact(), UntilRegex("x", managed=False)])
    assert combo.confidence == "heuristic", "weakest member wins even when degraded"


def test_quiet_unmanaged_screen_only_no_side_effects():
    from termdebug import records
    session = "td-unit-unmanaged-quiet"
    q = QuietCondition(session, 400, managed=False)
    assert q.confidence == "heuristic" and q.degraded == "unmanaged"
    assert not records.session_dir(session).exists(), \
        "unmanaged quiet must not create a state dir"
    ctx = WaitContext(capture=lambda sb: "stable",
                      meta=lambda: {"cursor_x": 1, "cursor_y": 1,
                                    "alternate_on": False, "history_size": 0})
    assert not q.evaluate(ctx), "first sample only primes"
    assert q.evaluate(ctx), "identical sample settles (gate 2 only)"


def test_quiet_unmanaged_timeout_hint_names_the_limit():
    q = QuietCondition("td-unit-unmanaged-quiet2", 400, managed=False)
    hint = timeout_hint(AllOf([q]))
    assert "unmanaged" in hint and "raw.log" not in hint.replace("no raw.log", ""), hint
    # a STANDALONE quiet condition gets the same hint (no AllOf wrapper)
    q2 = QuietCondition("td-unit-unmanaged-quiet3", 400, managed=False)
    assert "unmanaged" in timeout_hint(q2), timeout_hint(q2)
    # managed quiet keeps the raw.log hint; isolated XDG_STATE_HOME so the
    # V2Writer side effect never touches the real state dir
    import os, shutil, tempfile
    old_home = os.environ.get("XDG_STATE_HOME")
    os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
    try:
        managed_hint = timeout_hint(QuietCondition("td-unit-quiet-managed", 400))
        assert "raw.log" in managed_hint, "managed quiet keeps the raw.log hint"
    finally:
        shutil.rmtree(os.environ["XDG_STATE_HOME"], ignore_errors=True)
        if old_home is None:
            del os.environ["XDG_STATE_HOME"]
        else:
            os.environ["XDG_STATE_HOME"] = old_home


def _exit_ctx(meta):
    return WaitContext(capture=lambda sb: "", meta=meta)


def _missing_session():
    raise TDError("session-missing", "can't find session: dying")


def test_exit_unmanaged_collapse_is_fact_met():
    # Unmanaged pane, no remain-on-exit: the session collapses with the pane.
    # Pane death is still a tmux protocol fact — meet, status unreadable.
    from termdebug.waiting import ExitCondition
    ex = ExitCondition(managed=False)
    assert ex.evaluate(_exit_ctx(_missing_session)) is True
    assert ex.confidence == "fact" and ex.degraded == "status-unavailable"
    j = ex.to_json(True)
    assert j["exit_code"] is None and j["degraded"] == "status-unavailable"


def test_exit_managed_meta_failure_still_raises():
    from termdebug.waiting import ExitCondition
    ex = ExitCondition(managed=True)
    try:
        ex.evaluate(_exit_ctx(_missing_session))
    except TDError as e:
        assert e.code == "session-missing"
        return
    raise AssertionError("managed meta failure must propagate")


def test_exit_unmanaged_collapse_with_expect_code_fails():
    from termdebug.waiting import ExitCondition
    ex = ExitCondition(expect_code=0, managed=False)
    try:
        ex.evaluate(_exit_ctx(_missing_session))
    except TDError as e:
        assert e.code == "expect-code-mismatch"
        return
    raise AssertionError("unverifiable expect-code must fail, not silently pass")


def test_exit_unmanaged_vanish_empty_meta_is_met():
    # tmux answers a vanished pane target with rc=0 and EMPTY format fields
    # (no error): pane_dead=None, pane_width=None. That is the collapse.
    from termdebug.waiting import ExitCondition
    ex = ExitCondition(managed=False)
    empty = lambda: {"pane_dead": None, "pane_width": None, "cursor_x": None,
                     "pane_dead_status": None}
    assert ex.evaluate(_exit_ctx(empty)) is True
    assert ex.degraded == "status-unavailable" and ex.exit_code is None


def test_exit_unmanaged_alive_pane_keeps_waiting():
    from termdebug.waiting import ExitCondition
    ex = ExitCondition(managed=False)
    assert not ex.evaluate(
        _exit_ctx(lambda: {"pane_dead": False, "pane_width": 80,
                           "cursor_x": 0, "cursor_y": 0}))


def test_exit_unmanaged_dead_pane_still_reports_status():
    # Session survived (multi-window or remain-on-exit): full status available.
    from termdebug.waiting import ExitCondition
    ex = ExitCondition(expect_code=3, managed=False)
    meta = lambda: {"pane_dead": True, "pane_dead_signal": None,
                    "pane_dead_status": 3}
    assert ex.evaluate(_exit_ctx(meta)) is True
    assert ex.degraded is None and ex.exit_code == 3


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
