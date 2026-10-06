---
name: debugging-interactive-terminals
description: Use when debugging, driving, or reproducing issues in interactive terminal programs — tmux panes, full-screen TUIs (nano, vim, htop, less), interactive REPLs (bash, python, node), animated TUI apps (ink, bubbletea), or when you must confirm a command finished, get an exit code, click a TUI element, or capture what an on-screen program really shows
---

# Debugging Interactive Terminals

## Overview

Interactive programs own a screen and react to keystrokes; stdout capture and blind `sleep`
both fail. term-debug v2 drives them through tmux and replaces guessing with **evidence**:
every wait returns a verdict with a confidence level, every failure returns structured JSON
with a screen snapshot attached. The skill teaches a **method for unfamiliar programs** —
observe, derive anchors from what the program actually paints, confirm with probes — not a
table of pre-known screens.

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

CLI: `term-debug` (after install) or `PYTHONPATH=<repo>/src python3 -m termdebug` (only external dependency: tmux).

## Quick Reference

| Command | Purpose |
|---------|---------|
| `start -n N --cmd bash --width W --height H` | create session (+ v2 recording; bash gets OSC 133 integration) |
| `send -n N --type "text" --key Enter` | inject input; ONE CLI call may carry both — term-debug internally issues separate tmux send-keys calls (text and key names mixed in one tmux call silently drop keys); keys use tmux names (`Enter Escape C-c C-o`) |
| `screen -n N [--meta] [-N] [-J] [--grid] [--runs] [--grep --fg red] [--element-at X Y]` | text channel: status, trailing spaces, join, SGR cell grid, runs, **SGR attribute search** (`--grep` needs --fg/--bg/--attr — it is NOT a text grep; pipe plain `screen` output to grep for text), cell lookup |
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
`wait` defaults: `--timeout 10` (seconds), `--interval 0.1`. `--until` patterns are Python
`re` with DOTALL|MULTILINE — alternation (`a|b`) works. `--grep` attr names: bold, dim,
italic, underline, blink, reverse, strikethrough; fg/bg take color names (black..white,
bright-*) or 256-palette indexes or `#rrggbb`.

## Confirming a command finished (the standard loop)

```bash
TD="term-debug"   # or: PYTHONPATH=$REPO/src python3 -m termdebug
$TD start -n demo --cmd bash --width 100 --height 30
$TD send  -n demo --type true --key Enter
$TD wait  -n demo --cmd-done --expect-code 0 --timeout 10   # probe: shell is ready (fact)
$TD send  -n demo --type "make build" --key Enter
$TD wait  -n demo --cmd-done --expect-code 0 --timeout 120   # fact: exit code 0
```

- **Why the `true` probe**: bash's first startup emits a `D` marker with no preceding `C`,
  which the scanner classifies as aborted — a bare `--cmd-done` right after `start` always
  times out. The probe's `D` is the first real `done` and proves the shell is reading input.
  The same probe doubles as the "is the shell back?" check after leaving a nested program
  (a live REPL would swallow `true`, so `--cmd-done` keeps timing out).

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
  When the word you need is unavoidably both your input and program output (search terms in
  a pager, commands echoing filenames), don't wait on it at all — act, then **verify by
  reading the screen** (`screen | grep`) instead of waiting.
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
  quiet for its end. **Menu screens are quiet-hostile too**: modal pickers (model list,
  dialogs) repaint on a timer, so inside menus use `sleep 0.5-1` + `screen` instead of
  `--quiet-ms`. Menu arrow keys also debounce: `send --key Up --key Up` in one call moves
  the selection **once** — send each arrow as its own call with ~0.35s between calls.
- **C-\\**: no key name exists; send raw bytes: `send --hex 1c`. Same for any byte without
  a tmux key name. Multi-byte sequences work too (`--hex 1b5b31333b3275` = kitty
  Shift+Enter) — tmux's `-H` takes one byte per argument, so the CLI splits the string
  for you within a single send-keys call (escape sequences arrive contiguously).
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

## Driving an unfamiliar interactive program

Work in this order — observe before you anchor, anchor before you drive:

**1. Classify the program** — it decides how completion and exit are confirmed:
   - *Program IS the pane* (`start --cmd <prog>`): its death is observable → confirm exit
     with `wait --exit` (fact).
   - *Program inside bash* (`send <prog> --key Enter` in a bash pane): the pane always
     belongs to bash → `--exit` never fires; "did it exit?" is confirmed with the `true`
     probe + `--cmd-done --expect-code 0` (a live interactive program swallows `true`
     instead of letting bash execute it, so the wait keeps timing out). **Do NOT probe
     with `pgrep`** — term-debug's own recorder is a python3 process, so a process count
     is never 0 (measured: 4 in a bare session).
   - *REPL* (prompt + eval): the prompt is the anchor; results are verified by reading
     `screen -J | grep`, never by waiting on a substring of what you sent.
   - *Full-screen TUI* (alt-screen, repaints): prompt-less; anchors come from observation
     (step 2). After it exits, the alt-screen restores and stale frames can fake-settle
     short quiets and re-match old `--until` anchors — re-verify the screen after any
     program swap in the same pane; anchor the new program's first paint, don't trust a
     quiet interval.

**2. Observe, then derive the anchor.** Launch, then `screen` (and `trace` for byte-level
   evidence) to see what the program ACTUALLY paints before waiting on anything. Good
   anchors, in rough strength order: dialog text the program itself prints (e.g. a
   first-launch trust dialog's own wording), status-line vocabulary shown only in a
   specific phase (e.g. a word the status line displays while streaming, distinct from
   the thinking/preparing phases), prompt shapes (`^>>>`, `^>$`). Bad anchors: substrings
   of your own input (echo_suspect), text you know from a *different* program's manual —
   every anchor string belongs to the program it was measured on; derive yours from your
   program's screen. Program versions also change prompt wording: when an anchor times
   out, read `evidence.screen` and re-anchor — don't trust a remembered string across
   versions. Set `--timeout` from a first measured run (×3-5 headroom; the 10s default is
   fine for local programs — raise it for slow cold starts, e.g. a Node CLI measured ~20s
   to first paint on Android).

**3. Find the exit path before you need it.** Check `--help`/man for the quit key; common
   conventions: `q` (pagers), `C-d` (REPLs / EOF), `C-c` (interrupt), `Escape` ×N (menus).
   Key bindings differ per program — verify on screen instead of assuming. After the quit
   keystroke, confirm the shell took input back with the `true` probe, not by trusting
   the screen. Double-tap rhythms (two keys in ONE call vs two separate calls with a
   short gap) are program-specific and fragile: measure which works before relying on it,
   and err on the short side when sleeping between calls (each CLI invocation's startup
   inflates the gap).

**4. Drive in a wait-loop.** One action → wait for its observed effect → next action.
   When nothing new is waitable (input produces no fresh output, answers finish before
   the streaming phase is catchable), stop burning waits and poll `screen` for evidence
   (~1s per poll round at 0.5s sleep + CLI overhead) instead.

## Worked micro-example

The method applied once — strings below belong to THAT program (codebuddy CLI, an ink
TUI), not to the rules: `unset` of inherited agent env was needed before the TUI would
mount at all (the tell: zero bytes after the command echo); it must NOT be `exec`'d
(replacing bash kills the OSC 133 reporter, so `--cmd-done` can never fire); first launch
paints a trust dialog (anchor = the dialog's own text); answers stream (anchor =
status-line vocabulary); exit is a double C-c sent as two separate calls ~0.3s apart,
confirmed by `--cmd-done --expect-code 0` (clean exit 0, verified on 2.161.4). Your
program's anchors will differ — find them in step 2.

## Tester Feedback Protocol

If you were handed this skill as a blind tester: you have the right to complain — after any
task, append a line `FEEDBACK: <what confused you / what was missing / what you had to guess>`
to your output. Complaints feed directly into this skill's next revision.
