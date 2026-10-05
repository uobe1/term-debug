"""Input injection: send text/keys as separate tmux send-keys calls.

Red line (design section 5): `-l` text and key names must never be mixed in
one send-keys invocation — mixing them silently drops keys.
"""
from termdebug import tmuxio
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
