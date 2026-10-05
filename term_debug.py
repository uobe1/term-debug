#!/usr/bin/env python3
"""term-debug: drive and inspect interactive terminal tools via tmux.

Lets an agent spawn an interactive program (bash, python REPL, nano, vim, htop,
or even tmux itself) inside a tmux session, send keystrokes, capture the visible
screen, wait for a pattern to appear (condition-based waiting instead of blind
sleep), and replay a recorded trace of the whole interaction.

Only dependency beyond Python stdlib is the `tmux` binary.

Subcommands:
  start   create a detached tmux session running a command
  send    send literal text and/or special keys to the session
  screen  capture the current visible screen (the "state")
  wait    poll the screen until a regex matches (or timeout)
  trace   dump the recorded interaction timeline
  stop    kill the session and finalize the trace
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "term-debug"

# tmux key names accepted by `send --key`. Anything else is rejected.
KNOWN_KEYS = {
    "Enter", "Space", "Tab", "Escape", "BSpace", "DC", "IC", "Home", "End",
    "Up", "Down", "Left", "Right", "PgUp", "PgDn",
    "C-a", "C-b", "C-c", "C-d", "C-e", "C-f", "C-g", "C-h", "C-i", "C-j",
    "C-k", "C-l", "C-m", "C-n", "C-o", "C-p", "C-q", "C-r", "C-s", "C-t",
    "C-u", "C-v", "C-w", "C-x", "C-y", "C-z",
    "M-a", "M-b", "M-c", "M-d", "M-x",
}


def trace_path(name: str) -> Path:
    return CACHE_ROOT / name / "trace.jsonl"


def log_event(name: str, action: str, data) -> None:
    path = trace_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": time.time(), "action": action, "data": data}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["tmux", *args],
        capture_output=True,
        text=True,
        check=check,
    )


def session_exists(name: str) -> bool:
    res = tmux("has-session", "-t", name, check=False)
    return res.returncode == 0


def capture(name: str) -> str:
    res = tmux("capture-pane", "-p", "-t", name, check=False)
    return res.stdout or ""


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #
def cmd_start(args: argparse.Namespace) -> int:
    if session_exists(args.name):
        print(f"session '{args.name}' already exists", file=sys.stderr)
        return 1
    # Start a fresh trace for this session (don't append to a stale run).
    p = trace_path(args.name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.open("w").close()
    tmux("new-session", "-d", "-s", args.name,
         "-x", str(args.width), "-y", str(args.height), args.cmd)
    log_event(args.name, "start",
              {"cmd": args.cmd, "width": args.width, "height": args.height})
    print(f"started session '{args.name}' running: {args.cmd}")
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    if not session_exists(args.name):
        print(f"session '{args.name}' does not exist", file=sys.stderr)
        return 1
    for key in args.key or []:
        if key not in KNOWN_KEYS:
            print(f"unknown key '{key}' (known: {', '.join(sorted(KNOWN_KEYS))})",
                  file=sys.stderr)
            return 1
    sent = []
    if args.type:
        for text in args.type:
            tmux("send-keys", "-l", "-t", args.name, text)
            sent.append({"type": text})
    if args.key:
        tmux("send-keys", "-t", args.name, *args.key)
        sent.extend({"key": k} for k in args.key)
    if args.enter:
        tmux("send-keys", "-t", args.name, "Enter")
        sent.append({"key": "Enter"})
    log_event(args.name, "send", sent)
    return 0


def cmd_screen(args: argparse.Namespace) -> int:
    if not session_exists(args.name):
        print(f"session '{args.name}' does not exist", file=sys.stderr)
        return 1
    out = capture(args.name)
    if args.numbered:
        for i, line in enumerate(out.splitlines(), 1):
            print(f"{i:4d}|{line}")
    else:
        print(out, end="" if out.endswith("\n") else "\n")
    log_event(args.name, "screen", {"text": out})
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    if not session_exists(args.name):
        print(f"session '{args.name}' does not exist", file=sys.stderr)
        return 1
    pattern = re.compile(args.until)
    deadline = time.time() + args.timeout
    last = ""
    matched = False
    while time.time() < deadline:
        last = capture(args.name)
        if pattern.search(last):
            matched = True
            break
        time.sleep(args.interval)
    result = {
        "until": args.until,
        "matched": matched,
        "timeout": args.timeout,
    }
    if matched:
        m = pattern.search(last)
        result["match"] = m.group(0)
        line_no = None
        for i, line in enumerate(last.splitlines(), 1):
            if m.group(0) in line:
                line_no = i
                result["at_line"] = line_no
                result["at_text"] = line
                break
    log_event(args.name, "wait", result)
    if matched:
        print(f"matched '{args.until}' (in {args.timeout:.1f}s window)")
        return 0
    print(f"TIMEOUT waiting for '{args.until}' after {args.timeout}s", file=sys.stderr)
    print("--- last screen ---", file=sys.stderr)
    for i, line in enumerate(last.splitlines(), 1):
        print(f"{i:4d}|{line}", file=sys.stderr)
    return 1


def cmd_trace(args: argparse.Namespace) -> int:
    path = trace_path(args.name)
    if not path.exists():
        print(f"no trace for '{args.name}'", file=sys.stderr)
        return 1
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            entry = json.loads(line)
            if args.format == "json":
                print(json.dumps(entry, ensure_ascii=False))
                continue
            ts = time.strftime("%H:%M:%S", time.localtime(entry["ts"]))
            action = entry["action"]
            data = entry["data"]
            if action == "screen":
                print(f"[{ts}] screen ({len(data['text'].splitlines())} lines)")
            elif action == "send":
                parts = []
                for s in data:
                    parts.append(f"type={s['type']!r}" if "type" in s else f"key={s['key']}")
                print(f"[{ts}] send " + " ".join(parts))
            elif action == "wait":
                ok = "OK" if data["matched"] else "TIMEOUT"
                line = f"[{ts}] wait {ok} until={data['until']!r}"
                if data.get("matched"):
                    shown = data.get("at_text", data["match"])
                    if len(shown) > 60:
                        shown = shown[:57] + "..."
                    line += f" -> line {data.get('at_line')}: {shown!r}"
                print(line)
            else:
                print(f"[{ts}] {action} {data}")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    if session_exists(args.name):
        tmux("kill-session", "-t", args.name)
        print(f"killed session '{args.name}'")
    else:
        print(f"session '{args.name}' already gone", file=sys.stderr)
    log_event(args.name, "stop", {})
    return 0


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="term-debug",
        description="Drive and inspect interactive terminal tools via tmux.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("start", help="create a detached tmux session running a command")
    sp.add_argument("-n", "--name", required=True, help="session name")
    sp.add_argument("--cmd", default="bash", help="command to run (default: bash)")
    sp.add_argument("--width", type=int, default=120, help="pane width (default 120)")
    sp.add_argument("--height", type=int, default=40, help="pane height (default 40)")
    sp.set_defaults(func=cmd_start)

    sp = sub.add_parser("send", help="send literal text and/or special keys")
    sp.add_argument("-n", "--name", required=True, help="session name")
    sp.add_argument("--type", action="append", metavar="TEXT",
                    help="literal text to type (repeatable, order preserved)")
    sp.add_argument("--key", action="append", metavar="KEY",
                    help="special key e.g. Enter C-o C-x Escape (repeatable)")
    sp.add_argument("--enter", action="store_true", help="also press Enter at the end")
    sp.set_defaults(func=cmd_send)

    sp = sub.add_parser("screen", help="capture the current visible screen")
    sp.add_argument("-n", "--name", required=True, help="session name")
    sp.add_argument("--numbered", action="store_true", help="prefix line numbers")
    sp.add_argument("--raw", action="store_true", help="ignored (kept for compatibility)")
    sp.set_defaults(func=cmd_screen)

    sp = sub.add_parser("wait", help="poll screen until a regex matches")
    sp.add_argument("-n", "--name", required=True, help="session name")
    sp.add_argument("--until", required=True, help="regex to wait for")
    sp.add_argument("--timeout", type=float, default=10.0, help="max seconds (default 10)")
    sp.add_argument("--interval", type=float, default=0.2, help="poll interval (default 0.2)")
    sp.set_defaults(func=cmd_wait)

    sp = sub.add_parser("trace", help="dump the recorded interaction timeline")
    sp.add_argument("-n", "--name", required=True, help="session name")
    sp.add_argument("--format", choices=["text", "json"], default="text")
    sp.set_defaults(func=cmd_trace)

    sp = sub.add_parser("stop", help="kill the session and finalize the trace")
    sp.add_argument("-n", "--name", required=True, help="session name")
    sp.add_argument("--kill", action="store_true", help="ignored; stop always kills")
    sp.set_defaults(func=cmd_stop)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
