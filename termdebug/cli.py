"""term-debug v2 CLI: evidence-driven driving/debugging of interactive terminals.

Client process is stateless and short-lived; tmux server is the service.
All failures surface as single-line JSON errors (termdebug.errors.TDError).
"""
import argparse
import json
import re
import shlex
import sys
import time
from pathlib import Path

from termdebug import input as tdinput
from termdebug import rcfile, records, screen as tdscreen, tmuxio, waiting
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
    # Shell integration: bash sessions get an injected rcfile (OSC 133).
    cmd = args.cmd
    if cmd.split()[0].endswith("bash"):
        system_bashrc = "/data/data/com.termux/files/usr/etc/bash.bashrc"
        rc = writer.dir / "bashrc"
        rc.write_text(rcfile.bashrc_template(system_bashrc))
        cmd = f"bash --rcfile {shlex.quote(str(rc))} -i"
        writer.state["shell_integration"] = True
        writer.save_state()
    # remain-on-exit must be set *inside* the pane before exec: short-lived
    # commands would otherwise die (and take the session with them) before
    # the external set-option lands.
    inner = f"tmux set-option -w remain-on-exit on; exec {cmd}"
    res = tmuxio.tmux("new-session", "-d", "-s", args.name,
                      "-x", str(args.width), "-y", str(args.height),
                      inner, socket=args.socket)
    tmuxio.require(res, "socket-unreachable")
    pane_id = tmuxio.require(
        tmuxio.tmux("display-message", "-p", "-t", args.name, "-F", "#{pane_id}",
                    socket=args.socket)).strip()
    writer.state["pane_id"] = pane_id
    writer.save_state()
    # Recorder: pane output stream -> raw.log as v2 o-events.
    raw = shlex.quote(str(writer.dir / "raw.log"))
    tmuxio.tmux("pipe-pane", "-o", "-t", pane_id,
                f"{sys.executable} {PIPE_SCRIPT} {raw}", socket=args.socket)
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


def cmd_send(args) -> int:
    target = resolve_target(args.name)
    state = records.read_state(target.session)
    writer = records.V2Writer(target.session)
    offset = writer.size()  # where output caused by this send starts
    events = tdinput.send(target, args.type or [], args.key or [], args.hex or [])
    writer.append("i", events)
    state["last_send_offset"] = offset
    writer.state = state
    writer.save_state()
    result = {"ok": True, "sent": events, "offset": offset}
    sent_text = "".join(args.type or [])
    if sent_text and tdinput.echo_broken(target.session, offset, sent_text):
        result["warning"] = "tty-echo-broken"
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_fix_tty(args) -> int:
    target = resolve_target(args.name)
    state = records.read_state(target.session)
    writer = records.V2Writer(target.session)
    offset = writer.size()
    # C-u clears whatever half-typed line is sitting in the shell buffer,
    # so "stty sane" can never glue onto leftover input. Order matters:
    # clear first, then type the command, then Enter.
    events = tdinput.send(target, [], ["C-u"], [])
    events += tdinput.send(target, ["stty sane"], ["Enter"], [])
    writer.append("i", events)
    state["last_send_offset"] = offset
    writer.state = state
    writer.save_state()
    print(json.dumps({"ok": True, "fixed": "stty sane"}, ensure_ascii=False))
    return 0


def cmd_screen(args) -> int:
    target = resolve_target(args.name)
    if args.meta:
        state = records.read_state(target.session)
        m = tmuxio.meta(target)
        m.update(session=target.session, pane_id=state.get("pane_id"))
        print(json.dumps(m, ensure_ascii=False))
        return 0
    flags = []
    if args.keep_trailing:
        flags.append("-N")
    if args.join:
        flags.append("-J")
    if args.scrollback is not None:
        flags += ["-S", str(-args.scrollback)]
    if args.element_at is not None or args.grid or args.runs or args.grep:
        text = tmuxio.capture(target, tuple(flags + ["-e"]))
        grid = tdscreen.parse_grid(text)
        if args.element_at is not None:
            x, y = args.element_at
            print(json.dumps(tdscreen.cell_at(grid, x, y), ensure_ascii=False))
        elif args.grid:
            print(json.dumps(grid, ensure_ascii=False))
        elif args.runs:
            print(json.dumps(tdscreen.rows_to_runs(grid), ensure_ascii=False))
        elif args.grep:
            if args.fg is None and args.bg is None and not args.attr:
                raise TDError("session-missing", "--grep needs at least one of --fg/--bg/--attr")
            for row in grid:
                if tdscreen.row_matches(row, args.fg, args.bg, args.attr or ()):
                    print(tdscreen.grid_row_text(row))
        return 0
    print(tmuxio.capture(target, tuple(flags)), end="")
    return 0


def cmd_wait(args) -> int:
    # --until / --cmd-done here; --exit / --quiet-ms land in Tasks 6-7.
    target = resolve_target(args.name)
    state = records.read_state(target.session)

    def capture(scrollback: int) -> str:
        flags = ("-S", str(-scrollback)) if scrollback else ()
        return tmuxio.capture(target, flags)

    def pane_meta() -> dict:
        return tmuxio.meta(target)

    conditions: list = []
    if args.until is not None:
        conditions.append(waiting.UntilRegex(args.until, args.scrollback))
    if args.cmd_done:
        if not state.get("shell_integration"):
            raise TDError("no-shell-integration",
                          f"session {target.session!r} has no OSC 133 injection",
                          hint="start with --cmd bash to get shell integration")
        conditions.append(waiting.CmdDone(target.session, args.expect_code))
    if args.exit:
        conditions.append(waiting.ExitCondition(args.expect_code))
    if args.quiet_ms is not None:
        conditions.append(waiting.QuietCondition(target.session, args.quiet_ms))
    if not conditions:
        raise TDError("session-missing", "wait needs a condition",
                      hint="use --until, --cmd-done, --exit or --quiet-ms")
    cond = waiting.AllOf(conditions)
    ctx = waiting.WaitContext(capture, pane_meta)
    writer = records.V2Writer(target.session)

    deadline = time.monotonic() + args.timeout
    while True:
        if cond.evaluate(ctx):
            writer.append("m", {"event": "wait-met",
                                "confidence": cond.confidence})
            print(json.dumps({
                "verdict": "met",
                "confidence": cond.confidence,
                **cond.to_json(True),
                "evidence": {"screen": capture(0)},
            }, ensure_ascii=False))
            return 0
        # EOF early-termination: a dead pane can never satisfy --until or
        # --cmd-done, so fail immediately instead of burning the timeout.
        if not args.exit and not any(
                isinstance(c, waiting.ExitCondition) for c in cond.conditions):
            if pane_meta().get("pane_dead"):
                raise waiting.pane_dead_error(ctx)
        if time.monotonic() >= deadline:
            break
        time.sleep(args.interval)
    raise TDError("timeout",
                  f"conditions not met within {args.timeout}s",
                  evidence=waiting.timeout_evidence(ctx, cond))


def cmd_mouse_detect(args) -> int:
    target = resolve_target(args.name)
    tail = records.stream_since(target.session, 0)[-16384:]
    print(json.dumps(tdinput.mouse_mode(tail), ensure_ascii=False))
    return 0


def cmd_click(args) -> int:
    target = resolve_target(args.name)
    tail = records.stream_since(target.session, 0)[-16384:]
    mode = tdinput.mouse_mode(tail)
    if not mode["enabled"]:
        raise TDError("mouse-not-enabled",
                      "the program has not enabled mouse reporting",
                      hint="only programs that turned on \\e[?1000/1002/1003h accept clicks")
    tdinput.click(target, args.x, args.y)
    print(json.dumps({"ok": True, "clicked": [args.x, args.y],
                      "sgr": mode["sgr"]}, ensure_ascii=False))
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

    p = sub.add_parser("send", help="inject text/keys (always split into separate calls)")
    p.add_argument("-n", "--name", required=True, help="session name (or target)")
    p.add_argument("--type", action="append", metavar="TEXT",
                   help="literal text to type (repeatable, sent before keys)")
    p.add_argument("--key", action="append", metavar="KEY",
                   help="key name e.g. Enter Escape C-c (repeatable)")
    p.add_argument("--hex", action="append", metavar="HEX",
                   help="raw byte via send-keys -H e.g. 1c for C-\\ (repeatable)")
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("wait", help="poll the screen until a regex matches")
    p.add_argument("-n", "--name", required=True, help="session name (or target)")
    p.add_argument("--until", default=None, help="regex to wait for")
    p.add_argument("--cmd-done", action="store_true",
                   help="wait for the OSC 133 command-done marker (fact)")
    p.add_argument("--exit", action="store_true",
                   help="wait for the pane to exit (remain-on-exit, fact)")
    p.add_argument("--quiet-ms", type=int, default=None, metavar="N",
                   help="stable for N ms via double sampling (heuristic)")
    p.add_argument("--expect-code", type=int, default=None, metavar="N",
                   help="with --cmd-done/--exit: fail immediately unless exit code == N")
    p.add_argument("--scrollback", type=int, default=0, metavar="N",
                   help="search N lines of history too (default: visible screen)")
    p.add_argument("--timeout", type=float, default=10.0, help="max seconds (default 10)")
    p.add_argument("--interval", type=float, default=0.1, help="poll interval (default 0.1)")
    p.set_defaults(func=cmd_wait)

    p = sub.add_parser("screen", help="observe the pane: text, meta, SGR grid/runs")
    p.add_argument("-n", "--name", required=True, help="session name (or target)")
    p.add_argument("--meta", action="store_true", help="pane status JSON (cursor/modes/history)")
    p.add_argument("-N", "--keep-trailing", action="store_true", help="keep trailing spaces")
    p.add_argument("-J", "--join", action="store_true", help="join wrapped lines into logical lines")
    p.add_argument("--scrollback", type=int, metavar="N", help="include N lines of history")
    p.add_argument("--grid", action="store_true", help="SGR cell grid JSON")
    p.add_argument("--runs", action="store_true", help="attribute run view JSON")
    p.add_argument("--grep", action="store_true", help="print rows matching --fg/--bg/--attr")
    p.add_argument("--fg", default=None, metavar="COLOR")
    p.add_argument("--bg", default=None, metavar="COLOR")
    p.add_argument("--attr", action="append", metavar="A", help="e.g. bold, reverse (repeatable)")
    p.add_argument("--element-at", nargs=2, type=int, metavar=("X", "Y"), help="single cell JSON")
    p.set_defaults(func=cmd_screen)

    p = sub.add_parser("mouse-detect", help="report the pane's mouse tracking mode")
    p.add_argument("-n", "--name", required=True, help="session name (or target)")
    p.set_defaults(func=cmd_mouse_detect)

    p = sub.add_parser("click", help="inject an SGR mouse click (1-based coords)")
    p.add_argument("-n", "--name", required=True, help="session name (or target)")
    p.add_argument("x", type=int, help="column, 1-based")
    p.add_argument("y", type=int, help="row, 1-based")
    p.set_defaults(func=cmd_click)

    p = sub.add_parser("fix-tty", help="restore sane terminal settings (stty sane)")
    p.add_argument("-n", "--name", required=True, help="session name (or target)")
    p.set_defaults(func=cmd_fix_tty)

    for name in ("sessions", "trace", "screenshot"):
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
