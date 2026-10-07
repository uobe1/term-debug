"""Input injection: send text/keys as separate tmux send-keys calls.

Red line (design section 5): `-l` text and key names must never be mixed in
one send-keys invocation — mixing them silently drops keys.
"""
import re
import time

from termuse import records, tmuxio
from termuse.errors import TDError

# DECSET/DECRST: ESC [ ? <mode>[;<mode>...] h (set) / l (reset).
_DECSET = re.compile("\x1b\\[\\?(\\d+(?:;\\d+)*)([hl])")

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

    Parses every DECSET/DECRST sequence (ESC [ ? <modes> h/l); later events
    overwrite earlier ones (programs routinely toggle modes on enter/exit).
    Modes may be combined in one sequence (`\\e[?1000;1006h`) — tmux accepts
    that form and real TUIs emit it, so splitting on ';' is required.
    """
    states: dict[str, bool] = {}
    for m in _DECSET.finditer(raw_tail):
        on = m.group(2) == "h"
        for mode in m.group(1).split(";"):
            states[mode] = on
    normal = states.get("1000", False)
    motion = states.get("1002", False)
    anym = states.get("1003", False)
    sgr = states.get("1006", False)
    return {"enabled": normal or motion or anym, "sgr": sgr,
            "normal": normal, "motion": motion, "any_motion": anym}


def click(target: tmuxio.Target, x: int, y: int) -> None:
    """Click at 1-based screen coordinates: inject press+release SGR pair."""
    seq = mouse_encode(0, x - 1, y - 1, True) + mouse_encode(0, x - 1, y - 1, False)
    _run_or_die(target, ["-l", seq], f"click {x},{y}")


def echo_broken(session: str, offset: int, text: str, window: float = 1.0) -> bool:
    """True if typing produced no reaction within the window.

    A heuristic warning only: programs may legitimately disable ECHO
    (password prompts, line editors), so this never escalates to an error.
    Any output activity counts as a reaction — full-screen TUIs redraw
    instead of echoing, so "no echo but the program responded" is healthy.
    """
    probe = text[-8:]
    if not probe:
        return False
    deadline = time.monotonic() + window
    while time.monotonic() < deadline:
        new = records.stream_since(session, offset)
        if probe in new or new.strip():
            return False
        time.sleep(0.05)
    return True


def hex_to_args(h: str) -> list[str]:
    """Expand a hex string into send-keys -H args (tmux 3.x: one byte per -H).

    `--hex 1b5b3133` must become `-H 1b -H 5b -H 31 -H 33` — passing the whole
    string as a single -H argument is silently dropped by tmux 3.7c (rc=0,
    zero bytes delivered). Byte-splitting stays within one send-keys call, so
    escape sequences arrive contiguously.
    """
    h = h.strip().lower()
    if len(h) % 2 or not all(c in "0123456789abcdef" for c in h):
        raise TDError("session-missing", f"bad hex {h!r}",
                      hint="even-length hex string, e.g. 1c or 1b5b3133")
    args: list[str] = []
    for i in range(0, len(h), 2):
        args += ["-H", h[i:i + 2]]
    return args


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
        _run_or_die(target, hex_to_args(h), f"hex {h}")
        events.append({"hex": h})
    return events
