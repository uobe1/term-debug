---
name: debugging-interactive-terminals
description: Use when debugging, driving, or reproducing issues in interactive terminal tools such as tmux panes, full-screen TUIs (nano, vim, htop, less), or interactive REPLs (bash, python, node), where output is a screen rather than plain stdout and timing/state matter
---

# Debugging Interactive Terminals

## Overview

Interactive tools (tmux, nano, vim, htop, bash REPL, python REPL) do **not** behave like
piped commands: they own a screen, keep internal state, and react to individual keystrokes.
You cannot just capture stdout — you must drive them like a human at a keyboard.

**Core principle:** The unit of observation is the *screen* (`capture-pane`), the unit of action
is a *keystroke* (`send-keys`), and you must **synchronize on screen state, never on a blind
`sleep`**. Wait for the prompt/pattern you expect, then act.

CLI: `term-debug` (Python + tmux). Reference it by absolute path
`/data/data/com.termux/files/home/agent-i/term_debug.py`, or symlink it onto PATH:
`ln -s /data/data/com.termux/files/home/agent-i/term_debug.py ~/.local/bin/term-debug`.

## When to Use

- Driving/debugging a **tmux** pane or a tmux-in-tmux scenario.
- Operating a **full-screen TUI**: nano, vim, htop, less, top, mutt.
- Scripting an **interactive REPL**: bash, python, node, sqlite3.
- Reproducing a stateful interaction bug and recording it as evidence (the `trace`).

**Don't use** for ordinary non-interactive commands — just use the Bash tool directly.

## Workflow

```
spawn  →  capture state  →  send input  →  wait for expected state  →  verify  →  loop  →  cleanup
```

1. `start` a detached tmux session running the target.
2. `screen` to read current state; `wait --until <regex>` to block until ready.
3. `send --type "text"` for literal input, `--key C-o` for control keys, `--enter` for Enter.
4. `wait --until <pattern>` after every action that changes state (never guess a delay).
5. Repeat until you've reproduced / root-caused the issue.
6. `stop` to kill the session (always — leftover sessions leak).

**REQUIRED BACKGROUND:** `superpowers:systematic-debugging` (find root cause before fixing).
The `wait` loop *is* the condition-based-waiting pattern from `superpowers:condition-based-waiting`.

## Quick Reference

| Command | Purpose |
|---------|---------|
| `term-debug start -n N [--cmd bash] [--width W --height H]` | create detached session |
| `term-debug send -n N --type "text" [--key Enter\|C-o\|C-x\|Escape] [--enter]` | send input |
| `term-debug screen -n N [--numbered]` | capture visible screen (the state) |
| `term-debug wait -n N --until 'regex' [--timeout 10 --interval 0.2]` | block until pattern; exit 0=match, 1=timeout |
| `term-debug trace -n N [--format text\|json]` | replay the recorded interaction |
| `term-debug stop -n N` | kill session + finalize trace |

Trace is recorded automatically to `~/.cache/term-debug/<name>/trace.jsonl`.

## Common Mistakes

- **Literal vs control keys:** use `--type` for text, `--key` for special keys. Mixing them in
  one string breaks TUI input.
- **Racing the prompt:** sending `nano ...` before bash is ready fails silently. Always `wait`
  for the prompt (`'\$ '`) first.
- **Blind `sleep`:** don't. Use `wait --until`. Sleeps flake under load.
- **Wrong screen size:** TUIs wrap/redraw by pane size; set `--width/--height` explicitly.
- **Leaking sessions:** forgetting `stop` leaves orphan tmux sessions.

## Worked Example — the proof (tmux + interactive bash + nano edits a file)

```bash
TD=/data/data/com.termux/files/home/agent-i/term_debug.py
$TD start -n demo --cmd bash
$TD wait  -n demo --until '\$ '                       # bash prompt ready
$TD send  -n demo --type "nano /tmp/term-debug-proof.txt" --enter
$TD wait  -n demo --until 'GNU nano'                   # editor opened
$TD send  -n demo --type "Hello from term-debug via tmux + interactive bash"
$TD send  -n demo --key C-o                            # save
$TD wait  -n demo --until 'File Name to Write'
$TD send  -n demo --key Enter
$TD wait  -n demo --until 'Wrote .* lines'
$TD send  -n demo --key C-x                            # exit
$TD wait  -n demo --until '\$ '
$TD stop  -n demo
cat /tmp/term-debug-proof.txt                          # => contains the typed line
$TD trace -n demo                                      # evidence of the whole run
```

This demonstrates full control of a stateful full-screen TUI (nano) inside an interactive bash
inside tmux — the canonical hard case for agent-driven terminal debugging.
