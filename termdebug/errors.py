"""Structured error taxonomy: every failure surfaces as JSON {code,message,hint,evidence}."""
import json

# Design doc section 6 — the canonical code table.
ERROR_CODES = (
    "session-missing",
    "socket-unreachable",
    "pane-dead",
    "pane-dead-by-signal",
    "no-shell-integration",
    "expect-code-mismatch",
    "timeout",
    "mouse-not-enabled",
    "tty-echo-broken",
    # Skeleton-phase placeholder; removed once all subcommands are implemented.
    "not-implemented",
)


class TDError(Exception):
    """A term-debug failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str, hint: str | None = None,
                 evidence: dict | None = None):
        super().__init__(message)
        assert code in ERROR_CODES, f"unknown error code: {code}"
        self.code = code
        self.message = message
        self.hint = hint
        self.evidence = evidence

    def to_json(self) -> str:
        return json.dumps(
            {"error": {
                "code": self.code,
                "message": self.message,
                "hint": self.hint,
                "evidence": self.evidence,
            }},
            ensure_ascii=False,
        )

    @property
    def exit_code(self) -> int:
        return 1
