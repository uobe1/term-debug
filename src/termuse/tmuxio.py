"""tmux primitives: target parsing, command assembly, capture and pane metadata.

The locator is a (socket, session, window, pane) four-tuple. Accepts the
following CLI spellings (socket omitted -> default tmux server):

  s              -> (None, s, None, None)
  s:1            -> (None, s, "1", None)
  s:1.0          -> (None, s, "1", "0")
  sock:s         -> (sock, s, None, None)
  sock:s:1.0     -> (sock, s, "1", "0")
"""
import subprocess
from dataclasses import dataclass

from termuse.errors import TDError


@dataclass(frozen=True)
class Target:
    socket: str | None
    session: str
    window: str | None
    pane: str | None

    def to_arg(self) -> str:
        t = self.session
        if self.window is not None:
            t += f":{self.window}"
            if self.pane is not None:
                t += f".{self.pane}"
        return t


def parse_target(spec: str) -> Target:
    parts = spec.split(":")
    if len(parts) == 1:
        socket, sess, win = None, parts[0], None
    elif len(parts) == 2:
        socket, sess, win = None, parts[0], parts[1]
    elif len(parts) == 3:
        socket, sess, win = parts[0], parts[1], parts[2]
    else:
        raise TDError("session-missing", f"malformed target {spec!r}", hint="use [socket:]session[:window[.pane]]")
    if not sess:
        raise TDError("session-missing", f"target {spec!r} names no session")
    if win and "." in win:
        win, pane = win.split(".", 1)
    else:
        pane = ""
    return Target(socket or None, sess, win or None, pane or None)


def tmux(*args: str, socket: str | None = None) -> subprocess.CompletedProcess:
    """Run a tmux command; never raises, callers inspect the result."""
    cmd = ["tmux", *(["-L", socket] if socket else []), *args]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise TDError("socket-unreachable", "tmux binary not found on PATH")


def require(res: subprocess.CompletedProcess, err_code: str = "session-missing") -> str:
    """Return stdout of a tmux call or raise a structured error."""
    if res.returncode != 0:
        raise TDError(err_code, res.stderr.strip() or "tmux command failed")
    return res.stdout


def capture(target: Target, flags: tuple[str, ...] = ()) -> str:
    """Visible screen text (plus history with flags like ("-S", "-50)")."""
    res = tmux("capture-pane", *flags, "-p", "-t", target.to_arg(), socket=target.socket)
    return require(res)


def meta(target: Target) -> dict:
    """One-call pane status: cursor, modes, history, death, size, cwd."""
    keys = ("cursor_x", "cursor_y", "alternate_on", "pane_in_mode",
            "history_size", "pane_dead", "pane_dead_status", "pane_dead_signal",
            "pane_width", "pane_height", "pane_current_path")
    fmt = "|".join("#{" + k + "}" for k in keys)
    res = tmux("display-message", "-p", "-F", fmt, "-t", target.to_arg(), socket=target.socket)
    out = require(res).rstrip("\n").split("|")
    d: dict = {}
    bool_keys = {"alternate_on", "pane_in_mode", "pane_dead"}
    int_keys = {"cursor_x", "cursor_y", "history_size", "pane_dead_status",
                "pane_width", "pane_height"}
    for i, k in enumerate(keys):
        # pane_current_path is last and may itself contain "|": rejoin tail.
        if k == "pane_current_path" and len(out) > len(keys) - 1:
            v = "|".join(out[len(keys) - 1:])
        else:
            v = out[i] if i < len(out) else ""
        if v == "":
            d[k] = None
        elif k in bool_keys:
            d[k] = v == "1"
        elif k in int_keys:
            d[k] = int(v)
        else:  # e.g. pane_dead_signal is a name like "KILL"
            d[k] = v
    return d
