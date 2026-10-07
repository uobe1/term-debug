"""OSC 133 command-sequencing state machine (VSCode shell-integration scheme).

Sequences flowing through the pane's output stream:
  ESC]133;A (BEL|ESC\\)   prompt start
  ESC]133;B               command line start
  ESC]133;C               pre-execution / output start
  ESC]133;D;<code>        command done (a D is "done" only after a C;
                          otherwise the command was aborted)

The scanner tolerates chunk boundaries mid-sequence and skips over any other
escape sequences (CSI, other OSCs) so their payloads can never be mistaken
for markers. Works on the decoded text of raw.log o-events (ESC survives
UTF-8 decoding as \\x1b).
"""
from termuse.errors import TDError


class OSC133Scanner:
    def __init__(self):
        self.buf = ""
        self.saw_c = False
        self.events: list[dict] = []

    def feed(self, text: str) -> list[dict]:
        """Consume more stream text; return events completed by this chunk."""
        self.buf += text
        produced: list[dict] = []
        i = 0
        n = len(self.buf)
        while i < n:
            if self.buf[i] != "\x1b":
                i += 1
                continue
            end, event = self._match(self.buf, i)
            if end is None:  # incomplete sequence: wait for more bytes
                break
            if event is not None:
                produced.append(event)
            i = end
        self.buf = self.buf[i:]
        self.events.extend(produced)
        return produced

    # -- internals ----------------------------------------------------------

    def _match(self, s: str, i: int):
        """Parse one escape sequence at s[i] == ESC.

        Returns (end_index, event_or_None); end=None means incomplete.
        """
        if not s.startswith("\x1b]", i):
            return self._skip_csi_or_short(s, i), None
        j = i + 2
        # OSC payload until BEL or ESC \
        while j < len(s):
            if s[j] == "\x07":
                return j + 1, self._osc_event(s[i + 2:j])
            if s[j] == "\x1b" and s.startswith("\x1b\\", j):
                return j + 2, self._osc_event(s[i + 2:j])
            j += 1
        return None, None

    def _skip_csi_or_short(self, s: str, i: int) -> int:
        j = i + 1
        if j < len(s) and s[j] == "[":
            j += 1
            while j < len(s) and not ("@" <= s[j] <= "~"):
                j += 1
            return j + 1 if j < len(s) else len(s)  # past final byte
        return j + 1 if j < len(s) else len(s)      # 2-char escape

    def _osc_event(self, payload: str):
        if not payload.startswith("133;"):
            return None  # some other OSC (title, clipboard, ...)
        body = payload[4:]
        marker, _, param = body.partition(";")
        if marker == "A":
            self.saw_c = False
            return {"kind": "prompt"}
        if marker == "B":
            self.saw_c = False
            return {"kind": "cmdline"}
        if marker == "C":
            self.saw_c = True
            return {"kind": "preexec"}
        if marker == "D":
            code: int | None = None
            if param.strip().lstrip("-").isdigit():
                code = int(param)
            kind = "done" if self.saw_c else "aborted"
            self.saw_c = False
            return {"kind": kind, "code": code}
        return None


def scan_stream(text: str) -> list[dict]:
    sc = OSC133Scanner()
    sc.feed(text)
    return sc.events


def last_done(events: list[dict]) -> dict | None:
    done = [e for e in events if e["kind"] == "done"]
    return done[-1] if done else None


def mismatch_error(expect: int | None, actual: int | None, evidence: dict) -> TDError:
    return TDError(
        "expect-code-mismatch",
        f"command exited {actual}, expected {expect}",
        hint="inspect evidence.screen; the exit code comes from the shell's OSC 133 D marker (fact)",
        evidence=evidence,
    )
