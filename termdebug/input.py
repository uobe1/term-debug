"""Input injection: send text/keys as separate tmux send-keys calls.

Red line (design section 5): `-l` text and key names must never be mixed in
one send-keys invocation — mixing them silently drops keys.
"""
import re
import time

from termdebug import records, tmuxio
from termdebug.errors import TDError

# Key names accepted by send --key (tmux KEYC names). Raw bytes go through
# send --hex (send-keys -H) instead.
KNOWN_KEYS = frozenset({
    "Enter", "Space", "Tab", "Escape", "BSpace", "DC", "IC", "Home", "End",
    "Up", "Down", "Left", "Right", "PgUp", "PgDn", "F1", "F2", "F3", "F4",
    "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
    *(f"C-{c}" for c in "abcdefghijklmnopqrstuvwxyz"),
    *(f"M-{c}" for c in "abcdefghijklmnopqrstuvwxyz"),
})


def _run_or_die(target: tmuxio.Target, args: list[str], what: str) -> None:
    # tmux parses options strictly before positionals: -t must come first,
    # otherwise it lands in the pane as literal keys.
    res = tmuxio.tmux("send-keys", "-t", target.to_arg(), *args, socket=target.socket)
    if res.returncode != 0:
        raise TDError("session-missing", res.stderr.strip() or f"send-keys failed: {what}")


def mouse_encode(button: int, x: int, y: int, press: bool) -> str:
    """SGR mouse sequence; x/y are 0-based here, the wire format is 1-based.

    ESC [ < b ; x ; y M (press) / m (release).
    """
    return f"\x1b[<{button};{x + 1};{y + 1}{'M' if press else 'm'}"


def mouse_mode(raw_tail: str) -> dict:
    """Latest mouse tracking state from the pane's raw output stream.

    Scans for enable/disable pairs of the tracking modes; the most recent
    event of each wins (programs routinely toggle modes on enter/exit).
    """
    def latest(on_seq: str, off_seq: str) -> bool:
        on, off = raw_tail.rfind(on_seq), raw_tail.rfind(off_seq)
        return on >= 0 and on > off

    normal = latest("\x1b[?1000h", "\x1b[?1000l")
    motion = latest("\x1b[?1002h", "\x1b[?1002l")
    anym = latest("\x1b[?1003h", "\x1b[?1003l")
    sgr = latest("\x1b[?1006h", "\x1b[?1006l")
    return {"enabled": normal or motion or anym, "sgr": sgr,
            "normal": normal, "motion": motion, "any_motion": anym}


def click(target: tmuxio.Target, x: int, y: int) -> None:
    """Click at 1-based screen coordinates: inject press+release SGR pair."""
    seq = mouse_encode(0, x - 1, y - 1, True) + mouse_encode(0, x - 1, y - 1, False)
    _run_or_die(target, ["-l", seq], f"click {x},{y}")


def echo_broken(session: str, offset: int, text: str, window: float = 1.0) -> bool:
    """True if the typed text produced no echo bytes within the window.

    A heuristic warning only: programs may legitimately disable ECHO
    (password prompts, line editors), so this never escalates to an error.
    """
    probe = text[-8:]
    if not probe:
        return False
    deadline = time.monotonic() + window
    while time.monotonic() < deadline:
        if probe in records.stream_since(session, offset):
            return False
        time.sleep(0.05)
    return True


def send(target: tmuxio.Target, text: list[str], keys: list[str],
         hexes: list[str]) -> list[dict]:
    """Inject input as separate calls; returns the i-event records in order."""
    events: list[dict] = []
    for t in text:
        _run_or_die(target, ["-l", t], f"type {t!r}")
        events.append({"text": t})
    for k in keys:
        if k not in KNOWN_KEYS:
            raise TDError("session-missing", f"unknown key {k!r}",
                          hint=f"known keys: {', '.join(sorted(KNOWN_KEYS))}; "
                               f"raw bytes go through send --hex")
        _run_or_die(target, [k], f"key {k}")
        events.append({"key": k})
    for h in hexes:
        _run_or_die(target, ["-H", h], f"hex {h}")
        events.append({"hex": h})
    return events
