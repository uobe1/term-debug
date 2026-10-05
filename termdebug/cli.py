"""term-debug v2 CLI: evidence-driven driving/debugging of interactive terminals.

Client process is stateless and short-lived; tmux server is the service.
All failures surface as single-line JSON errors (termdebug.errors.TDError).
"""
import argparse
import json
import shlex
import sys
from pathlib import Path

from termdebug import records, tmuxio
from termdebug.errors import TDError

PIPE_SCRIPT = Path(__file__).resolve().parent / "pipe.py"


def resolve_target(name: str) -> tmuxio.Target:
    """Resolve a CLI -n argument to a full target; socket falls back to state.json."""
    t = tmuxio.parse_target(name)
    if t.socket is None:
        t = tmuxio.Target(records.read_state(t.session).get("socket"),
                          t.session, t.window, t.pane)
    return t


def cmd_start(args) -> int:
    if tmuxio.tmux("has-session", "-t", args.name, socket=args.socket).returncode == 0:
        raise TDError("session-missing",
                      f"session {args.name!r} already exists",
                      hint="pick another -n name or stop the existing session")
    writer = records.V2Writer.fresh(args.name, args.width, args.height,
                                    args.cmd, args.socket)
    res = tmuxio.tmux("new-session", "-d", "-s", args.name,
                      "-x", str(args.width), "-y", str(args.height),
                      args.cmd, socket=args.socket)
    tmuxio.require(res, "socket-unreachable")
    tmuxio.tmux("set-window-option", "-g", "-t", args.name,
                "remain-on-exit", "on", socket=args.socket)
    pane_id = tmuxio.require(
        tmuxio.tmux("display-message", "-p", "-t", args.name, "-F", "#{pane_id}",
                    socket=args.socket)).strip()
    writer.state["pane_id"] = pane_id
    writer.save_state()
    # Recorder: pane output stream -> raw.log as v2 o-events.
    raw = shlex.quote(str(writer.dir / "raw.log"))
    tmuxio.tmux("pipe-pane", "-o", "-t", pane_id,
                "-F", f"{sys.executable} {PIPE_SCRIPT} {raw}", socket=args.socket)
    print(json.dumps({"ok": True, "session": args.name, "socket": args.socket,
                      "pane_id": pane_id, "width": args.width,
                      "height": args.height}, ensure_ascii=False))
    return 0


def cmd_stop(args) -> int:
    state = records.read_state(args.name)
    writer = records.V2Writer(state["session"])
    res = tmuxio.tmux("kill-session", "-t", state["session"], socket=state.get("socket"))
    if res.returncode != 0:
        raise TDError("session-missing",
                      res.stderr.strip() or f"session {state['session']!r} already gone")
    writer.append("m", {"event": "stop"})
    state["stopped"] = True
    writer.state = state
    writer.save_state()
    print(json.dumps({"ok": True, "session": state["session"]}, ensure_ascii=False))
    return 0


def _not_implemented(args) -> int:
    raise TDError(
        "not-implemented",
        f"subcommand '{args.command}' is not implemented yet",
        hint="this is the v2 skeleton; implement per docs/plans/2026-10-05-term-debug-v2-implementation.md",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="term_debug.py",
        description="Drive and debug interactive terminal programs via tmux (v2).",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("start", help="create a detached tmux session with v2 recording")
    p.add_argument("-n", "--name", required=True, help="session name")
    p.add_argument("--cmd", default="bash", help="command to run (default: bash)")
    p.add_argument("--width", type=int, default=120)
    p.add_argument("--height", type=int, default=40)
    p.add_argument("--socket", default=None, help="tmux socket name (-L)")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("stop", help="kill the session and finalize raw.log")
    p.add_argument("-n", "--name", required=True, help="session name (or target)")
    p.set_defaults(func=cmd_stop)

    for name in ("send", "screen", "wait", "sessions", "trace",
                 "fix-tty", "screenshot", "mouse-detect"):
        # Real options are added as each subcommand gets implemented.
        p = sub.add_parser(name, help=name)
        p.add_argument("args", nargs="*", help=argparse.SUPPRESS)
        p.set_defaults(func=_not_implemented)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except TDError as e:
        print(e.to_json(), file=sys.stderr)
        return e.exit_code
