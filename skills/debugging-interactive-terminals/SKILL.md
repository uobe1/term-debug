---
name: debugging-interactive-terminals
description: Use when debugging, driving, or reproducing issues in interactive terminal programs — tmux panes, full-screen TUIs (nano, vim, htop, less), interactive REPLs (bash, python, node), animated TUI apps (ink, bubbletea), nested tmux, interactive menus and wizards, or when you must confirm a command finished, get an exit code, select a menu item, or capture what an on-screen program really shows
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
| `send -n N --type "text" --key Enter [--repeat N --delay S]` | inject input; ONE CLI call may carry both — term-debug internally issues separate tmux send-keys calls (text and key names mixed in one tmux call silently drop keys); keys use tmux names (`Enter Escape C-c C-o`). `--repeat N` repeats the whole injection as N independent sends, `--delay S` between them (default 0.35) — debounced menus, double-key rhythms |
| `screen -n N [--meta] [-N] [-J] [--grid] [--runs] [--grep --attr A] [--find TEXT] [--element-at X Y]` | text channel: status, trailing spaces, join, SGR cell grid, runs, **attribute row filter** (`--grep` takes NO text pattern — rows matching `--fg`/`--bg`/`--attr`; pipe plain `screen` output to grep for text), **literal text finder** (`--find` → 1-based click-ready coords, feed into `click`), cell lookup |
| `wait -n N --cmd-done [--expect-code 0]` | **command finished + exit code (fact)** — a bare call right after `start` always times out (bash's first marker reads as aborted): probe with `--shell-ready` first, see the standard loop below |
| `wait -n N --shell-ready [--timeout S]` | CLI sends the `true` probe itself and waits for the shell's OSC 133 answer (fact); use right after `start` and after leaving a nested program; timeout → `shell-not-ready` error |
| `wait -n N --exit [--expect-code N]` | pane exit / death, signal name in evidence (fact) |
| `wait -n N --until 'regex' [--scrollback N]` | screen regex (inference; rstrip self-heal for trailing spaces) |
| `wait -n N --quiet-ms 800` | screen stable for N ms (heuristic; animation-immune) |
| `screenshot -n N --format png -o p.png` | image channel via Pillow |
| `mouse-detect -n N` / `click -n N X Y` | mouse mode (SGR) / click at 1-based coords |
| `fix-tty -n N` | restore sane terminal (stty sane) after ECHO damage |
| `trace -n N [--format json]` | project raw.log: input/output/sync events |
| `sessions [--socket NAME]` / `stop -n N` | list sessions / kill session |

Targets are `(socket, session, window, pane)` four-tuples: `-n "sess"`, `"sess:win"`,
`"sock:sess:win.pane"`. Nested tmux panes are directly addressable via their socket name
(see Nested tmux below). `wait` defaults: `--timeout 10` (seconds), `--interval 0.1`.
`--until` patterns are Python `re` with DOTALL|MULTILINE — alternation (`a|b`) works.
`--grep` attr names: bold, dim, italic, underline, blink, reverse, strikethrough; fg/bg take
color names (black..white, bright-*) or 256-palette indexes or `#rrggbb`.
Single-letter program commands (pager `q`, top's `P`) are TEXT — `send --type q`; `--key`
accepts tmux key names only and errors with a table of them if you try a letter.

## Confirming a command finished (the standard loop)

```bash
TD="term-debug"   # or: PYTHONPATH=$REPO/src python3 -m termdebug
$TD start -n demo --cmd bash --width 100 --height 30
$TD wait  -n demo --shell-ready --timeout 10    # probe: shell is ready (fact)
$TD send  -n demo --type "make build" --key Enter
$TD wait  -n demo --cmd-done --expect-code 0 --timeout 120   # fact: exit code 0
```

- **Why the probe** (`--shell-ready` sends `true` + Enter itself, waits for the shell's
  OSC 133 answer): bash's first startup emits a `D` marker with no preceding `C`, which
  the scanner classifies as aborted — a bare `--cmd-done` right after `start` always
  times out. The probe's answer is the first real `done` and proves the shell is reading
  input. It doubles as the "is the shell back?" check after leaving a nested program: a
  live REPL swallows it → `shell-not-ready` (evidence.screen shows the probe sitting on
  the program's prompt line — send the program's quit key, then re-probe).
- `--cmd-done` reads OSC 133 markers injected into bash (exit code from shell protocol → `fact`).
- Wrong `--expect-code` fails **immediately** with `expect-code-mismatch` (no timeout burn);
  pane death mid-wait fails immediately with `pane-dead` / `pane-dead-by-signal` + respawn hint.
- No shell integration (`start --cmd sh` and other non-bash; `--shell-ready` refuses the
  same way) → immediate structured `no-shell-integration` error. `--exit` still works
  there (pane death is tmux-level, fact); for in-shell completion fall back to `--until`
  on the program's own output marker.

## Common Mistakes

- **`--type "cmd" --enter`**: v2 has no `--enter`. Always `--type "cmd" --key Enter` — text
  and keys are separate calls, and Enter is a key.
- **"Never sleep" means "never sleep instead of waiting"**: sleep is banned as a
  completion oracle, but allowed as the pace of a polling loop — `sleep 0.5-1` + `screen`
  when nothing is waitable (timer-driven screens, menus, unmanaged panes). Pick the
  shortest pause that outlasts one observed repaint period.
- **Trailing spaces**: the terminal rstrips lines, so `'your name: '` won't match raw text.
  `--until` self-heals (matches rstripped text + a sentinel space) — trust it, and never
  invent regexes that require trailing spaces to survive.
- **Echo-anchored waits are untrustworthy**: you see your own typed text on screen.
  `wait --until` detects this — if the matched text is a substring of what you last sent,
  the verdict is flagged `echo_suspect: true` and confidence drops to `heuristic`.
  **Never put the marker you wait for inside your sent text**; split it at runtime
  (`print('OUT_' + '42')`) or anchor on *program output* / `--cmd-done` (fact). When the
  word is unavoidably both input and output (pager search terms, commands echoing
  filenames), don't wait on it — act, then **verify by reading the screen**
  (`screen | grep`).
  Leftover echoes from earlier experiments can also pollute later waits — and note
  `--until` matches the CURRENT screen, not "newly appeared" text: a stale anchor still
  on screen (an old `^>>>` prompt, earlier output) makes the new wait return met
  instantly. Beware also: YOUR shell expands `$((...))`/`$VAR` in double quotes before
  the text is injected, silently merging input and marker.
- **Never send a confirm key on a fixed sleep**: before EVERY TUI confirmation key
  (Enter on a save prompt or menu choice), wait for the prompt text itself (`--until`,
  or quiet + screen check) — a key sent before the prompt appears lands in the edit
  buffer and corrupts state (measured: nano `C-o` → immediate Enter forced an extra
  round-trip).
- **Spinners defeat quiet**: an animated line changes every 150 ms but a slow device can
  sample identical frames ~600 ms apart (frame-cycle resonance). `--quiet-ms` also gates
  on the raw stream's last-write time (25% margin), so it won't settle while a spinner
  runs — pick 2-3x the observed frame period, anchor with `--until` when a "done" marker
  exists, and don't trust a large quiet value across a phase where the program may only
  *start* thinking after your input (wait for the stream to start first). **Menu screens
  are quiet-hostile too** (modal pickers repaint on a timer): use `sleep 0.5-1` + `screen`
  inside menus. Menu arrows also debounce: `send --key Up --key Up` in one call moves the
  selection **once** — one arrow per call, ~0.35s apart.
- **Selecting item N in a menu** (recipe): read the highlight with `screen --grep --attr
  reverse` (prints the highlighted row; most curses apps draw it reversed) → send the
  arrows in one call, `send --key Down --repeat 3` (N independent sends, 0.35s apart by
  default) → **re-run the grep to verify the highlight landed where you intended** before
  Enter. Attribute channels don't cover every program: less's search highlight does not
  present as `reverse` — for pager-style highlights verify by plain text match instead.
- **Live-monitor TUIs (top/htop-style) repaint on a timer**: one captured frame can be
  mid-repaint or stale, and short-lived processes vanish between refreshes — read two
  frames ~2s apart and answer only if they agree. Answer from the program's own sorted
  rows, not aggregate header lines, which can be wrong on exotic platforms (measured on
  Android: `800%cpu 800%idle` while per-process rows were still usable).
- **REPL block input**: ANY colon-opening statement enters the continuation prompt
  (`...`) — even a physically single-line `def f(): return 1`, and the block needs ONE
  extra empty Enter to close; otherwise your next line is swallowed into the block
  (measured: needed `C-c` rescue). Prefer colon-free one-liners (lambda, `;`-joined);
  for real blocks send each line separately and anchor on the block's *result*, not
  the prompts.
- **Non-writable /tmp on sandboxed platforms** (measured on Termux/Android): scripts and
  fixtures aimed at `/tmp` die with Permission denied — use `$TMPDIR` (or the session's
  working directory) for throwaway files.
- **C-\\**: no key name exists; send raw bytes: `send --hex 1c`. Same for any byte without
  a tmux key name. Multi-byte sequences work too (`--hex 1b5b31333b3275` = kitty
  Shift+Enter) — tmux's `-H` takes one byte per argument, so the CLI splits the string
  for you within a single send-keys call (escape sequences arrive contiguously).
- **Stuck/echo-less screen**: a program may have mangled the tty (`stty -echo`). `send`
  warns `tty-echo-broken` when your text produces no echo bytes; run `fix-tty`.
- **Mouse apps**: `mouse-detect` first; `click X Y` is 1-based while curses programs print
  0-based coords.
- **Long typed text wraps**: a ~90-char `--type` wraps on a 100-col pane (the on-screen
  echo breaks mid-word); a `--until` pattern spanning that text must match the *wrapped*
  screen — or keep sent commands short and let the program print the marker. Note
  `evidence.screen` shows the prompt verbatim: `~/.../` is the shell's PS1, not term-debug;
  use `screen --meta`'s `pane_current_path` for the real cwd.
- **Leaking sessions**: always `stop` (or `tmux kill-server` in test cleanup). Stopping the
  last session kills the whole tmux server, taking nested sessions with it.

## Nested tmux

A tmux client running *inside* a term-debug pane is directly drivable — with three
measured gotchas:

1. **`$TMUX` blocks the nested client** — tmux refuses to start ("sessions should be nested
   with care, unset $TMUX to force"). Run `unset TMUX; tmux new-session -s inner ...`.
2. **Address inner panes by socket name**: the default socket's name is literally
   `default` — `screen -n default:inner:0.0` works; a bare `-n inner` does NOT (it looks
   for a term-debug-managed session and fails with `session-missing`).
3. **wait on unmanaged panes** (term-debug didn't start them): `--until`/`--quiet-ms`
   work with degraded confidence — capped at `heuristic`, condition JSON carries
   `"degraded": "unmanaged"`, and raw-stream echo detection is off (anchor on output
   that isn't a substring of your input). `--cmd-done`/`--shell-ready` refuse with
   structured `unmanaged-pane` (shell-protocol facts need a managed session). `--exit`
   works even when the pane's death takes its session with it (no remain-on-exit): the
   verdict is still met/fact but carries `"degraded": "status-unavailable"` and
   `exit_code: null` — don't pass `--expect-code` on unmanaged panes (a vanished pane
   can't prove its exit code → `expect-code-mismatch`). `send` and `screen` work
   unchanged.

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
     with `wait --exit` (fact; works for non-bash too).
   - *Program inside bash* (`send <prog> --key Enter` in a bash pane): the pane always
     belongs to bash → `--exit` never fires; "did it exit?" is confirmed with
     `wait --shell-ready` (a live interactive program swallows the probe instead of
     letting bash execute it, so it fails with `shell-not-ready` until the program
     quits). **Do NOT probe with `pgrep`** — term-debug's own recorder is a python3
     process, so a process count is never 0 (measured: 4 in a bare session).
   - *REPL* (prompt + eval): the prompt is the anchor; results are verified by reading
     `screen -J | grep`, never by waiting on a substring of what you sent.
   - *Full-screen TUI* (alt-screen, repaints): prompt-less; anchors come from observation
     (step 2). After it exits, the alt-screen restores and stale frames can fake-settle
     short quiets and re-match old `--until` anchors — re-verify the screen after any
     program swap; anchor the new program's first paint, don't trust a quiet interval.

**2. Observe, then derive the anchor.** Launch, then catch the first paint before you have
   any anchor: `wait --quiet-ms 700` (non-animated programs settle fast) or `sleep 1` +
   `screen` for timer-driven ones — read what the program ACTUALLY paints, then wait on
   it. Good anchors, in rough strength order: dialog text the program itself prints,
   status-line vocabulary shown only in a specific phase, prompt shapes (`^>>>`, `^>$`).
   Bad anchors: substrings of your own input (echo_suspect), text you know from a
   *different* program's manual — every anchor string belongs to the program it was
   measured on (measured drift: nano 9.2's save prompt is `Write to File:`, older nano
   said `File Name to Write`). Derive yours from your program's screen; when an anchor
   times out, read `evidence.screen` and re-anchor. Set `--timeout` from a first measured
   run (×3-5 headroom; raise it for slow cold starts, e.g. a Node CLI measured ~20s to
   first paint on Android).

**3. Find the exit path before you need it.** Check `--help`/man for the quit key; common
   conventions: `q` (pagers), `C-d` (REPLs / EOF), `C-c` (interrupt), `Escape` ×N (menus) —
   but verify on screen instead of assuming. After the quit keystroke, confirm the shell
   took input back with `wait --shell-ready`, not by trusting the screen. Double-tap
   rhythms are program-specific and fragile: `--repeat 2 --delay 0.3` sends the pair as
   two independent calls in one CLI invocation — measure which rhythm works before
   relying on it, and err on the short side with delays (each CLI invocation's startup
   inflates the gap).

**4. Drive in a wait-loop.** One action → wait for its observed effect → next action.
   When nothing new is waitable (input produces no fresh output, answers finish before
   the streaming phase is catchable), stop burning waits and poll `screen` for evidence
   (~1s per poll round at 0.5s sleep + CLI overhead) instead. On unmanaged panes
   `--exit` still reports the death, just without an exit code (see Nested tmux).

## Worked micro-example

Strings below belong to THAT program (codebuddy CLI, an ink TUI), not to the rules:
`unset` of inherited agent env was needed before the TUI would mount (tell: zero bytes
after the command echo); it must NOT be `exec`'d (replacing bash kills the OSC 133
reporter, so `--cmd-done` can never fire); first launch paints a trust dialog (anchor =
the dialog's own text); exit is a double C-c (`--repeat 2 --delay 0.3`), confirmed by
`--cmd-done --expect-code 0`. Your program's anchors will differ — find them in step 2.

## Tester Feedback Protocol

If you were handed this skill as a blind tester: you have the right to complain — after any
task, append a line `FEEDBACK: <what confused you / what was missing / what you had to guess>`
to your output. Complaints feed directly into this skill's next revision.
