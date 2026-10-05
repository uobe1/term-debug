---
name: debugging-interactive-terminals
description: Use when debugging, driving, or reproducing issues in interactive terminal programs — tmux panes, full-screen TUIs (nano, vim, htop, less), interactive REPLs (bash, python, node), animated TUI apps (ink, bubbletea), or when you must confirm a command finished, get an exit code, click a TUI element, or capture what an on-screen program really shows
---

# Debugging Interactive Terminals

## Overview

Interactive programs own a screen and react to keystrokes; stdout capture and blind `sleep`
both fail. term-debug v2 drives them through tmux and replaces guessing with **evidence**:
every wait returns a verdict with a confidence level, every failure returns structured JSON
with a screen snapshot attached.

**Core principles**

1. **Wait for state, then act.** Never sleep, never guess a delay. After every action, `wait`
   for the condition you expect before the next one.
2. **Know what your evidence is worth.** `fact` (shell protocol / pane death) beats
   `inference` (screen regex — echo can fake it) beats `heuristic` (sampling-based quiet
   detection). Prefer fact; treat heuristic as "probably safe".
3. **Pick the right observation channel.** Attribute/semantic questions ("which item is
   selected", "what color is it", "find the row with X") → `screen` text channels. Spatial
   layout questions ("what does the frame look like", "where is the dialog box drawn") →
   `screenshot`. You may alternate freely.

CLI: `python3 <repo>/term_debug.py ...` (only external dependency: tmux).

## Quick Reference

| Command | Purpose |
|---------|---------|
| `start -n N --cmd bash --width W --height H` | create session (+ v2 recording; bash gets OSC 133 integration) |
| `send -n N --type "text" --key Enter` | inject input; text and keys are **always separate** tmux calls |
| `screen -n N [--meta] [-N] [-J] [--grid] [--runs] [--grep --fg red] [--element-at X Y]` | text channel: status, trailing spaces, join, SGR cell grid, runs, attribute search, cell lookup |
| `wait -n N --cmd-done [--expect-code 0]` | **command finished + exit code (fact)** — use this to confirm completion |
| `wait -n N --exit [--expect-code N]` | pane exit / death, signal name in evidence (fact) |
| `wait -n N --until 'regex' [--scrollback N]` | screen regex (inference; rstrip self-heal for trailing spaces) |
| `wait -n N --quiet-ms 800` | screen stable for N ms (heuristic; animation-immune) |
| `screenshot -n N --format png -o p.png` | image channel via Pillow |
| `mouse-detect -n N` / `click -n N X Y` | mouse mode (SGR) / click at 1-based coords |
| `fix-tty -n N` | restore sane terminal (stty sane) after ECHO damage |
| `trace -n N [--format json]` | project raw.log: input/output/sync events |
| `sessions [--socket NAME]` / `stop -n N` | list sessions / kill session |

Targets are `(socket, session, window, pane)` four-tuples: `-n "sess"`, `"sess:win"`,
`"sock:sess:win.pane"`. Nested tmux panes are directly addressable via their socket name.

## Confirming a command finished (the standard loop)

```bash
TD="python3 $REPO/term_debug.py"
$TD start -n demo --cmd bash --width 100 --height 30
$TD send  -n demo --type "make build" --key Enter
$TD wait  -n demo --cmd-done --expect-code 0 --timeout 120   # fact: exit code 0
```

- `--cmd-done` scans the pane's raw output stream for OSC 133 markers injected into bash.
  The exit code comes from the shell protocol → confidence `fact`.
- Wrong `--expect-code` fails **immediately** with `expect-code-mismatch` (no timeout burn).
- `pane dies mid-wait` → fails immediately with `pane-dead` / `pane-dead-by-signal` + respawn hint.
- No shell integration (non-bash) → structured `no-shell-integration` error; fall back to
  `--until` on the program's own output marker.

## Common Mistakes

- **`--type "cmd" --enter`**: v2 has no `--enter`. Always `--type "cmd" --key Enter` — text
  and keys are separate calls, and Enter is a key.
- **Trailing spaces**: the terminal rstrips lines, so `'your name: '` won't match raw text.
  `--until` self-heals (matches rstripped text + a sentinel space) — trust it, and never
  invent regexes that require trailing spaces to survive.
- **Echo-anchored waits are untrustworthy**: you see your own typed text on screen.
  `wait --until` detects this automatically — if the matched text is a substring of what
  you last sent, the verdict is flagged `echo_suspect: true` and confidence drops to
  `heuristic`. **Never put the marker you wait for inside your sent text**; if the program
  would echo it identically, split the string at runtime (e.g. `print('OUT_' + '42')`).
  Anchoring on *program output* (not echoed text) or using `--cmd-done` (fact) is stronger.
  Leftover echoes from earlier experiments can also pollute later waits — use a fresh
  session for sensitive experiments.
- **Spinners defeat quiet**: an animated line changes every 150 ms but a slow device can
  sample identical frames ~600 ms apart (frame-cycle resonance). `--quiet-ms` gates on the
  raw output stream's last-write time too (with a 25% margin), so it won't settle while a
  spinner runs — but a spinner that paints exactly once per quiet-ms sits at the margin's
  edge: prefer `--quiet-ms` at least 2-3x the observed frame period, and anchor with
  `--until` when the program has a known "done" marker. A stream that starts *thinking*
  (spinner on) after you sent a message can also false-settle a large quiet value — wait
  for the stream to actually start (`--until` on the streaming indicator) before trusting
  quiet for its end.
- **C-\\**: no key name exists; send raw bytes: `send --hex 1c`. Same for any byte without
  a tmux key name.
- **Stuck/echo-less screen**: a program may have mangled the tty (`stty -echo`). `send`
  warns `tty-echo-broken` when your text produces no echo bytes; run `fix-tty`.
- **Mouse apps**: `mouse-detect` first; `click X Y` is 1-based while curses programs print
  0-based coords.
- **Long typed text wraps**: `send --type` of a ~90-char line wraps on a 100-col pane
  (the on-screen echo breaks mid-word). A `--until` pattern spanning that text must match
  the *wrapped* screen, not the logical line — or keep sent commands short and let the
  program print the marker. Also note `evidence.screen` shows the pane's prompt verbatim:
  abbreviations like `~/.../` come from the shell's PS1, not from term-debug; use
  `screen --meta`'s `pane_current_path` for the real cwd.
- **Leaking sessions**: always `stop` (or `tmux kill-server` in test cleanup).

## Anti-Cheating Red Lines

- **Never** bypass the CLI by editing files the program owns, or by `Write`-ing the expected
  output into place. The whole point is observing the program's real behavior.
- **Never** claim a run happened without evidence: attach `trace` output (or the session's
  `raw.log` events) and, for layout claims, the `screenshot` path.
- Timeouts are data: report the `error` JSON (screen snapshot inside), don't swallow it.

## Standard Scenarios

1. **nano edit + run** (full-screen TUI): start → wait prompt → send `nano file` + Enter →
   wait `GNU nano` → type text → `C-o` → wait the save prompt (**version-dependent:
   `File Name to Write` on older nano, `Write to File:` on nano 9+** — on timeout read
   evidence.screen and re-anchor) → Enter → wait `Wrote` → `C-x` → `--cmd-done` → verify
   the file via ordinary `cat` (outside the pane). Expect `tty-echo-broken` warnings to be
   absent here: TUIs respond with redraws, which the warning logic treats as healthy.
   Editor key behavior differs by program: `C-k`/`C-o`/`Down` are safe bets, but keys like
   `End`/`Home` may be unbound in some editors — verify on screen instead of assuming.
2. **REPL driving** (python/node): start REPL → wait its prompt via `--until` →
   `--type` expression + Enter → read response via `screen`/`--grep`; exit via
   `C-d` then `wait --exit --expect-code 0`.
3. **todo.js double-bug repro** (JS project): run the failing program in the pane, wait for
   the error via `--until`, capture `trace --format json` as the evidence bundle, fix code
   with normal tools, re-run the same chain to prove the fix.
4. **ink/bubbletea app (e.g. codebuddy CLI)**: launch inside the pane with
   `unset SERVER__PORT CODEBUDDY_SERVICE_PROXY_URL` first (inherited agent env makes the
   TUI silently never mount — zero bytes after the command echo). A fresh directory first
   shows a **trust dialog** ("Do you trust the files in this folder?") — Enter through it
   before expecting the real first screen. Then `--quiet-ms 800` for the first paint →
   `screen --runs`/`--element-at` to locate the input → `--type` message + Enter →
   after the answer starts streaming, wait for its end with `--quiet-ms 1500` (anchor
   `--until 'streaming'` first — that word is in codebuddy's status line while text
   streams, and distinguishes it from the `preparing`/`waiting for model` phases; the
   rewind menu's checkpoint rows contain `ago` if you need an anchor there) → `Escape`
   (`--key Escape`) interrupts
   (`└ Interrupted by user`); double-ESC opens the rewind/resume menu — **one
   `send --key Escape --key Escape` call (both keys in a single invocation, 0ms apart);
   if that doesn't trigger it, try two separate calls ~0.2s apart** (the app's debounce
   window is picky; its live "N s ago" timestamps repaint every second — wait with
   `--until` anchors, not quiet). **Exit** needs a double C-c, and here the rhythm is the
   opposite: a single call with two C-c's does NOT work — use two separate
   `send --key C-c` calls with a short sleep (0.3-0.5s; **err on the short side** — the
   app's double-tap window is <1s of *key-event* time, and each CLI invocation's startup
   inflates the gap, so sleep 1 misses it); confirm with `--cmd-done`. Note that
   restarting the app in the same pane leaves stale frames that fake-settle short quiets
   and re-match old `--until` anchors — **the reliable way to see the new first screen is
   anchoring the `>` input box** (`--until '^>$'`); a longer quiet (~2.5s) is only a
   no-anchor fallback and can still settle on stale frames when cold start exceeds it.

## Tester Feedback Protocol

If you were handed this skill as a blind tester: you have the right to complain — after any
task, append a line `FEEDBACK: <what confused you / what was missing / what you had to guess>`
to your output. Complaints feed directly into this skill's next revision.
