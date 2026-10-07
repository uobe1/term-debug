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
    # Degradation marker: why this condition runs with reduced evidence
    # (e.g. "unmanaged" — no state.json/raw.log, so part of the machinery
    # cannot run). None on fully-equipped waits.
    degraded: str | None = None

    def evaluate(self, ctx) -> bool:
        raise NotImplementedError

    def to_json(self, met: bool) -> dict:
        j = {"type": self.label, "confidence": self.confidence, "met": met}
        if self.degraded:
            j["degraded"] = self.degraded
        return j


class WaitContext:
    """What conditions may observe: screen text (+history) and pane meta."""

    def __init__(self, capture, meta):
        self.capture = capture  # callable(scrollback: int) -> str
        self.meta = meta        # callable() -> dict


class UntilRegex(Condition):
    label = "until"
    confidence = "inference"

    def __init__(self, pattern: str, scrollback: int = 0, session: str | None = None,
                 managed: bool = True):
        self.pattern = pattern
        self.scrollback = scrollback
        self.session = session
        self.managed = managed
        self.echo_suspect = False
        self.rx = re.compile(pattern, re.DOTALL | re.MULTILINE)
        if not managed:
            # Unmanaged pane (nested tmux): no i-events exist, so echo-suspect
            # detection cannot run and our own echo can fake the match. Cap
            # the claim and say why (nested tmux is a supported scenario —
            # degrade, don't refuse).
            self.confidence = "heuristic"
            self.degraded = "unmanaged"

    def evaluate(self, ctx) -> bool:
        screen = ctx.capture(self.scrollback)
        if self.rx.search(screen) or self._match_stripped(screen):
            return self._check_echo(screen)
        return False

    def _match_stripped(self, screen: str) -> bool:
        # Self-heal red line: the terminal strips trailing spaces ('name: '
        # prints as 'name:'), so retry against per-line-rstripped text, and
        # against rstripped text + a sentinel space (pattern requires one).
        stripped = "\n".join(line.rstrip() for line in screen.splitlines())
        if self.rx.search(stripped):
            return True
        sentinel = "\n".join(line.rstrip() + " " for line in screen.splitlines())
        return bool(self.rx.search(sentinel))

    def _check_echo(self, screen: str) -> bool:
        """Echo red line: if the matched text is just what we last typed, the
        match is our own echo — downgrade confidence and flag it."""
        self.echo_suspect = False
        if self.session is None:
            return True
        m = self.rx.search(screen)
        if not m or not m.group(0):
            return True
        try:
            for _ts, code, data, _pos in records.events_since(self.session, 0):
                if code != "i" or not isinstance(data, list):
                    continue
                typed = "".join(e.get("text", "") for e in data
                                if isinstance(e, dict))
                if typed and m.group(0) in typed:
                    self.echo_suspect = True
                    self.confidence = "heuristic"
                    return True
        except (TDError, OSError):
            # Managed on paper, but records vanished: echo can't be checked.
            self.confidence = "heuristic"
            self.degraded = "records-unavailable"
        return True

    def to_json(self, met: bool) -> dict:
        return {**super().to_json(met), "pattern": self.pattern,
                "scrollback": self.scrollback,
                "echo_suspect": self.echo_suspect}


class AllOf(Condition):
    """AND composition; confidence degrades to the weakest member.

    Recomputed after every evaluate: a condition may downgrade itself at
    runtime (e.g. until matching our own echo)."""

    def __init__(self, conditions: list[Condition]):
        if not conditions:
            raise ValueError("AllOf needs at least one condition")
        self.conditions = conditions
        self.label = "all-of"
        self._recompute()

    def _recompute(self) -> None:
        weakest = max(CONFIDENCE_ORDER.index(c.confidence) for c in self.conditions)
        self.confidence = CONFIDENCE_ORDER[weakest]

    def evaluate(self, ctx) -> bool:
        result = all(c.evaluate(ctx) for c in self.conditions)
        self._recompute()
        return result

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
        """Replay the full o-stream through the state machine, then accept
        the newest done/aborted event only if it was emitted after the last
        send (byte position >= last_send_offset). Full replay keeps C-marker
        continuity: the C of a long-running command may sit far behind the
        scan start."""
        state = records.read_state(self.session)
        offset = state.get("last_send_offset", 0)
        sc = osc133.OSC133Scanner()
        last_terminal = None  # (kind, code, byte_pos)
        for _ts, code, data, pos in records.events_since(self.session, 0):
            if code != "o" or not isinstance(data, str):
                continue
            for ev in sc.feed(data):
                if ev["kind"] in ("done", "aborted"):
                    last_terminal = (ev["kind"], ev.get("code"), pos)
        if last_terminal is None or last_terminal[2] < offset:
            return False
        kind, code_, _ = last_terminal
        if kind == "aborted":
            return False  # marker without a fresh C: no command completed
        self.exit_code = code_
        if self.expect_code is not None and self.exit_code != self.expect_code:
            raise osc133.mismatch_error(
                self.expect_code, self.exit_code,
                {"exit_code": self.exit_code, "expected": self.expect_code,
                 "screen": ctx.capture(0)})
        return True

    def to_json(self, met: bool) -> dict:
        return {**super().to_json(met), "expect_code": self.expect_code,
                "exit_code": self.exit_code if met else None}


class ShellReady(Condition):
    """The shell answers a `true` probe (fact).

    Internalizes the skill's standard probe loop: the client sends `true`
    + Enter, then requires a cmd-done (exit 0) emitted after the probe.
    Works where a bare --cmd-done cannot:
      - right after `start` (bash's startup D has no preceding C and is
        classified aborted, so --cmd-done would always time out);
      - after leaving a nested program (a live REPL swallows the probe,
        so the wait keeps failing — the timeout IS the "still inside" signal,
        surfaced as the shell-not-ready error code).
    The probe itself is injected by the CLI (cmd_wait) so last_send_offset
    stays authoritative; this condition only does the fact check.
    """

    label = "shell-ready"
    confidence = "fact"

    def __init__(self, session: str):
        self.session = session
        self._done = CmdDone(session, 0)

    def evaluate(self, ctx) -> bool:
        return self._done.evaluate(ctx)

    def to_json(self, met: bool) -> dict:
        return {**self._done.to_json(met), "type": self.label}


class ExitCondition(Condition):
    """Pane death via remain-on-exit: pane_dead / status / signal. fact."""

    label = "exit"
    confidence = "fact"

    def __init__(self, expect_code: int | None = None, managed: bool = True):
        self.expect_code = expect_code
        self.managed = managed
        self.exit_code: int | None = None

    def _meet_collapsed(self) -> bool:
        # Unmanaged pane whose session collapsed with it (no remain-on-exit):
        # the pane is gone, which is itself a tmux protocol fact. cmd_wait
        # probed the pane before constructing this condition, so a vanished
        # pane mid-wait means it died — meet with fact confidence, status
        # unreadable.
        if self.expect_code is not None:
            raise TDError(
                "expect-code-mismatch",
                f"pane vanished without remain-on-exit; exit code "
                f"unavailable (expected {self.expect_code})",
                hint="drop --expect-code for unmanaged panes, or keep the "
                     "program in a managed session (term-debug start)")
        self.exit_code = None
        self.degraded = "status-unavailable"
        return True

    def evaluate(self, ctx) -> bool:
        try:
            m = ctx.meta()
        except TDError as e:
            if self.managed or e.code != "session-missing":
                raise
            return self._meet_collapsed()  # server gone: pane certainly gone
        if m.get("pane_dead"):
            signal = m.get("pane_dead_signal")
            if signal:
                raise TDError(
                    "pane-dead-by-signal",
                    f"pane killed by signal {signal}",
                    hint="respawn with: term-debug start -n <name> --cmd "
                         "<command> (then re-run your scenario)",
                    evidence={"signal": signal, "screen": ctx.capture(0)},
                )
            self.exit_code = m.get("pane_dead_status")
            if self.expect_code is not None \
                    and self.exit_code != self.expect_code:
                raise osc133.mismatch_error(
                    self.expect_code, self.exit_code,
                    {"exit_code": self.exit_code, "expected": self.expect_code,
                     "screen": ctx.capture(0)})
            return True
        if not self.managed and m.get("pane_width") is None \
                and m.get("pane_dead") is None:
            # tmux answers a vanished pane target with rc=0 and EMPTY format
            # fields (no error) — that is the session collapsing with the pane
            return self._meet_collapsed()
        return False

    def to_json(self, met: bool) -> dict:
        return {**super().to_json(met), "expect_code": self.expect_code,
                "exit_code": self.exit_code if met else None}


def pane_dead_error(ctx) -> TDError:
    """Unexpected pane death during a wait that wasn't --exit (EOF early-termination)."""
    m = ctx.meta()
    signal = m.get("pane_dead_signal")
    if signal:
        return TDError(
            "pane-dead-by-signal",
            f"pane killed by signal {signal} while waiting",
            hint="respawn with: term-debug start -n <name> --cmd <command>",
            evidence={"signal": signal, "screen": ctx.capture(0)},
        )
    return TDError(
        "pane-dead",
        f"pane exited (status {m.get('pane_dead_status')}) while waiting",
        hint="use --exit --expect-code N to wait for pane death on purpose",
        evidence={"exit_code": m.get("pane_dead_status"), "screen": ctx.capture(0)},
    )


class QuietCondition(Condition):
    """Animation-immune stability (heuristic).

    Two independent gates:
    1. Output activity: the raw o-stream's last event must be older than
       the quiet interval (immune to screen-content resonance, where a
       cyclic animation happens to repaint identical frames at sampling
       time).
    2. Screen stability: (screen, cursor_x/y, alternate_on, history_size)
       must be identical across two samples spaced >= interval apart.

    An unclosed CSI 2026 (begin synchronized update) forces instability.
    """
    label = "quiet"
    confidence = "heuristic"

    def __init__(self, session: str, ms: int, managed: bool = True):
        self.session = session
        self.managed = managed
        self.ms = ms
        self.interval = max(ms / 1000, 0.25)  # sampling floor: 250ms
        self._last = None
        self._open_2026 = 0
        self._last_o_ts = None  # elapsed of the newest o-event
        self._scan_offset = 0
        self._tail = ""
        if not managed:
            # Unmanaged pane: no raw.log, so gate 1 (stream last-write) cannot
            # run. Degrade to screen-stability sampling only — never touch
            # records (V2Writer would create a bogus state dir as a side
            # effect). Confidence stays heuristic either way.
            self.t0 = None
            self.degraded = "unmanaged"
            return
        w = records.V2Writer(session)
        self.t0 = w.t0
        self._consume_stream()

    def _consume_stream(self) -> None:
        path = records.session_dir(self.session) / "raw.log"
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return
        if size <= self._scan_offset:
            return
        text = ""
        for ts, code, data, _pos in records.events_since(self.session, self._scan_offset):
            if code == "o" and isinstance(data, str):
                self._last_o_ts = ts
                text += data
        self._scan_offset = size
        buf = self._tail + text
        for i in range(len(buf) - 7):
            if buf.startswith("\x1b[?2026h", i):
                self._open_2026 += 1
            elif buf.startswith("\x1b[?2026l", i):
                self._open_2026 = max(0, self._open_2026 - 1)
        self._tail = buf[-16:]

    def evaluate(self, ctx) -> bool:
        if self.managed:
            self._consume_stream()
        m = ctx.meta()
        sample = (ctx.capture(0), m.get("cursor_x"), m.get("cursor_y"),
                  m.get("alternate_on"), m.get("history_size"))
        if self._open_2026 > 0:
            self._last = sample  # never settle mid-synchronized-update
            return False
        # Gate 1 (managed only): real output activity — how long since the
        # pane emitted? 25% margin: a spinner whose frame period exactly
        # equals the quiet interval would otherwise settle at the instant
        # just before the next frame lands.
        if self.managed:
            if self._last_o_ts is None:
                return False
            idle = (time.time() - self.t0) - self._last_o_ts
            if idle < self.interval * 1.25:
                self._last = sample
                return False
        # Gate 2: screen snapshot stability across spaced samples.
        if self._last == sample:
            return True
        self._last = sample
        return False

    def to_json(self, met: bool) -> dict:
        return {**super().to_json(met), "ms": self.ms}


def timeout_evidence(ctx, condition: Condition) -> dict:
    """Evidence snapshot for an unmet wait: screen, cursor, raw tail, state."""
    try:
        screen = ctx.capture(0)
    except (TDError, OSError):
        screen = None  # pane/session vanished before the snapshot
    try:
        m = ctx.meta()
        cursor = {"x": m.get("cursor_x"), "y": m.get("cursor_y")}
    except Exception:
        cursor = None
    raw_tail = ""
    if condition.__class__.__name__ == "AllOf":
        session = next((getattr(c, "session", None) for c in condition.conditions
                        if getattr(c, "session", None)), None)
        if session:
            try:
                raw_tail = records.stream_since(session, 0)[-300:]
            except (TDError, OSError):
                pass
    return {"screen": screen, "cursor": cursor, "raw_tail": raw_tail,
            "conditions": [condition.to_json(False)]}


def timeout_hint(condition: Condition) -> str:
    """Actionable next step for an unmet wait."""
    if condition.__class__.__name__ == "AllOf":
        quiet = next((c for c in condition.conditions if c.label == "quiet"),
                     None)
    else:
        quiet = condition if condition.label == "quiet" else None
    if quiet is not None:
        if getattr(quiet, "degraded", None) == "unmanaged":
            return ("quiet ran on an unmanaged pane (no raw.log) with "
                    "screen-stability sampling only — an animation or "
                    "clock repaint never settles; use --until on a program "
                    "marker instead")
        return ("quiet never settled — check raw.log for periodic writes "
                "(keepalive bytes reset the silence timer); use --until on a "
                "program marker instead, or raise --timeout")
    return "inspect evidence.screen; try a looser --until pattern or a longer --timeout"
