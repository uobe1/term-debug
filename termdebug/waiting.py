"""Wait engine: pluggable conditions, AND composition, verdict JSON.

Every condition carries a confidence label (design section 3):
  fact       — ground truth from the terminal protocol (OSC 133, pane death)
  inference  — screen-text regex (echo can fake it)
  heuristic  — sampling-based stability (quiet detection)
The composite verdict takes the *weakest* confidence of its conditions.
Timeout never kills the target; it returns an evidence snapshot.
"""
import re
import time

from termdebug import osc133, records
from termdebug.errors import TDError

CONFIDENCE_ORDER = ("fact", "inference", "heuristic")  # strong -> weak


class Condition:
    label: str = "condition"
    confidence: str = "inference"

    def evaluate(self, ctx) -> bool:
        raise NotImplementedError

    def to_json(self, met: bool) -> dict:
        return {"type": self.label, "confidence": self.confidence, "met": met}


class WaitContext:
    """What conditions may observe: screen text (+history) and pane meta."""

    def __init__(self, capture, meta):
        self.capture = capture  # callable(scrollback: int) -> str
        self.meta = meta        # callable() -> dict


class UntilRegex(Condition):
    label = "until"
    confidence = "inference"

    def __init__(self, pattern: str, scrollback: int = 0):
        self.pattern = pattern
        self.scrollback = scrollback
        self.rx = re.compile(pattern, re.DOTALL | re.MULTILINE)

    def evaluate(self, ctx) -> bool:
        screen = ctx.capture(self.scrollback)
        if self.rx.search(screen):
            return True
        # Self-heal red line: the terminal strips trailing spaces ('name: '
        # prints as 'name:'), so retry against per-line-rstripped text, and
        # against rstripped text + a sentinel space (pattern requires one).
        stripped = "\n".join(line.rstrip() for line in screen.splitlines())
        if self.rx.search(stripped):
            return True
        sentinel = "\n".join(line.rstrip() + " " for line in screen.splitlines())
        return bool(self.rx.search(sentinel))

    def to_json(self, met: bool) -> dict:
        return {**super().to_json(met), "pattern": self.pattern,
                "scrollback": self.scrollback}


class AllOf(Condition):
    """AND composition; confidence degrades to the weakest member."""

    def __init__(self, conditions: list[Condition]):
        if not conditions:
            raise ValueError("AllOf needs at least one condition")
        self.conditions = conditions
        self.label = "all-of"
        weakest = max(CONFIDENCE_ORDER.index(c.confidence) for c in conditions)
        self.confidence = CONFIDENCE_ORDER[weakest]

    def evaluate(self, ctx) -> bool:
        return all(c.evaluate(ctx) for c in self.conditions)

    def to_json(self, met: bool) -> dict:
        return {**super().to_json(met),
                "conditions": [c.to_json(met) for c in self.conditions]}


class CmdDone(Condition):
    """OSC 133 D marker after a C, scanned from raw.log since the last send.

    fact confidence: the exit code comes from the shell protocol, not from
    screen text. Expect-code mismatch fails immediately (never waits out the
    timeout). Requires shell integration recorded in state.json.
    """
    label = "cmd-done"
    confidence = "fact"

    def __init__(self, session: str, expect_code: int | None = None):
        self.session = session
        self.expect_code = expect_code
        self.exit_code: int | None = None

    def _stream(self) -> str:
        state = records.read_state(self.session)
        return records.stream_since(self.session, state.get("last_send_offset", 0))

    def evaluate(self, ctx) -> bool:
        events = osc133.scan_stream(self._stream())
        done = osc133.last_done(events)
        if done is None:
            return False
        self.exit_code = done.get("code")
        if self.expect_code is not None and self.exit_code != self.expect_code:
            raise osc133.mismatch_error(
                self.expect_code, self.exit_code,
                {"exit_code": self.exit_code, "expected": self.expect_code,
                 "screen": ctx.capture(0)})
        return True

    def to_json(self, met: bool) -> dict:
        return {**super().to_json(met), "expect_code": self.expect_code,
                "exit_code": self.exit_code if met else None}


def timeout_evidence(ctx, condition: Condition) -> dict:
    """Evidence snapshot for an unmet wait: screen, cursor, condition state."""
    screen = ctx.capture(0)
    try:
        m = ctx.meta()
        cursor = {"x": m.get("cursor_x"), "y": m.get("cursor_y")}
    except Exception:
        cursor = None
    return {"screen": screen, "cursor": cursor,
            "conditions": [condition.to_json(False)]}
