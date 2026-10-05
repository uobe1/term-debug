"""term-debug v2 CLI: evidence-driven driving/debugging of interactive terminals.

Client process is stateless and short-lived; tmux server is the service.
All failures surface as single-line JSON errors (termdebug.errors.TDError).
"""
import argparse
import sys

from termdebug.errors import TDError

SUBCOMMANDS = (
    "start", "stop", "send", "screen", "wait", "sessions",
    "trace", "fix-tty", "screenshot", "mouse-detect",
)


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
    for name in SUBCOMMANDS:
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
