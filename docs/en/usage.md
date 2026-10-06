# Using term-debug

Complete guide for driving and debugging interactive terminal programs with
term-debug. Written for AI agents first — humans debugging a TUI will find it
works the same way.

## The three rules

1. **Wait for state, then act.** Never sleep, never guess a delay. After every
   action, `wait` for the condition you expect before the next one.
2. **Know what your evidence is worth.** `fact` (terminal protocol) beats
   `inference` (screen regex) beats `heuristic` (quiet sampling). Prefer fact;
   treat heuristic as "probably safe".
3. **Pick the right observation channel.** Attribute/semantic questions ("which
   item is selected", "what color is it") → `screen`. Spatial questions ("what
   does the frame look like", "where is the dialog drawn") → `screenshot`.
   Alternate freely.

## The basic workflow

```bash
TD="term-debug"   # or: PYTHONPATH=/path/to/repo/src python3 -m termdebug

$TD start -n demo --cmd bash --width 100 --height 30
$TD send  -n demo --type "make build" --key Enter
$TD wait  -n demo --cmd-done --expect-code 0 --timeout 120
# → {"verdict": "met", "confidence": "fact", "exit_code": 0, ...}
```

That is the whole loop: **start → send → wait for fact → act.**

- `--cmd-done` scans the pane's raw output stream for OSC 133 markers injected
  into bash; the exit code comes from the shell protocol → confidence `fact`.
- A wrong `--expect-code` fails **immediately** with `expect-code-mismatch` —
  no timeout burn.
- Pane death mid-wait fails immediately (`pane-dead` / `pane-dead-by-signal`
  with a respawn hint).
- Non-bash session → structured `no-shell-integration` error; fall back to
  `--until` anchored on the program's own output marker.

## Usage

### Choosing a wait condition

| Situation | Wait with |
|---|---|
| Did the shell command finish? what code? | `--cmd-done [--expect-code N]` — always prefer |
| Did the program exit or crash? | `--exit [--expect-code N]` (signal name in evidence) |
| A known output marker appears | `--until 'regex'` (`--scrollback N` extends history) |
| No marker exists (animated TUI) | `--quiet-ms 800`, at 2-3x the observed frame period |
| Several things must hold | pass multiple conditions in one `wait` (AND; verdict takes the weakest confidence) |

### Typing text, keys, raw bytes

```bash
$TD send -n demo --type "y" --key Enter          # text and keys are SEPARATE calls, always
$TD send -n demo --key C-o                        # control key (nano save)
$TD send -n demo --hex 1c                         # raw byte (C-\); no key name exists
$TD send -n demo --hex 1b5b31333b3275             # multi-byte: kitty Shift+Enter
```

Text and keys are issued as separate `send-keys` calls because tmux silently
drops keys when `-l` text and key names are mixed in one call — a documented
tmux failure mode this CLI refuses to let you trigger. `--hex` is split one
byte per `-H` (tmux 3.x drops multi-byte `-H`), so escape sequences arrive
contiguously within a single call.

TUI menus **debounce arrow keys**: `send --key Up --key Up` in one call moves
the selection **once**. Send each arrow as its own call, ~0.35 s apart.

If `send` warns `tty-echo-broken` (your text produced no echo bytes), the
program mangled the tty — run `fix-tty`.

### Mouse-driven TUIs

```bash
$TD mouse-detect -n demo          # report the pane's mouse tracking mode
$TD click -n demo 12 40           # SGR click, 1-based coords
```

`click` is 1-based while curses programs print 0-based coords — mind the
off-by-one.

### Observing: text vs image channel

```bash
$TD screen -n demo --meta                          # cursor, modes, history, alt-screen
$TD screen -n demo --runs                          # SGR attribute runs (token-cheap)
$TD screen -n demo --grep selected --fg red        # attribute search
$TD screen -n demo --element-at 40 12              # what is this cell?
$TD screenshot -n demo --format png -o pane.png    # spatial layout (needs Pillow)
$TD trace -n demo                                  # project raw.log: input/output/sync events
```

`screen --meta`'s `pane_current_path` is the real cwd; the prompt on screen may
abbreviate (`~/.../`) — that is the shell's PS1, not a display bug.

### Reading failures — timeouts are data

Every failure prints **single-line JSON on stderr** with a screen snapshot
attached:

```json
{"error":{"code":"wait-timeout","message":"...","evidence":{"screen":"...","cursor":{"x":1,"y":5},"raw_tail":"..."}}}
```

Never swallow it, never paraphrase it away. A timeout does **not** kill the
target — inspect the snapshot and retry with a better anchor.

## How it works

```
agent → term-debug CLI (stateless client) → tmux server → pane (target program)
                                               └→ pipe.py (recorder sink, one per pane)
```

The CLI is a short-lived, stateless client with zero resident memory; the tmux
server owns PTYs/sessions. All state lives on disk under
`$XDG_STATE_HOME/term-debug/<session>/`:

- **`raw.log`** — asciicast v2 evidence store (`o` pane output, `i` injections,
  `r` resize, `m` sync points). The ground truth for protocol-level bytes.
- **`state.json`** — locator + recorder state, written atomically (tmp + rename).
  `last_send_offset` is a **byte offset** into `raw.log`, so `--cmd-done` only
  accepts markers emitted after your last send — a typed echo can never fake
  completion.

Every mechanism claim in this guide is exercised by the E2E suite
(`tests/e2e/*.sh`), which drives real tmux and real programs through the CLI
only — nothing is mocked.

## Common mistakes

- **`--type "cmd" --enter`** — v2 has no `--enter`. Always
  `--type "cmd" --key Enter`.
- **Trailing spaces** — the terminal rstrips lines; `--until` self-heals, but
  never write regexes that *require* trailing spaces to survive.
- **Echo-anchored waits are untrustworthy** — you see your own typed text on
  screen. If the matched text is a substring of what you last sent, the verdict
  is flagged `echo_suspect: true` and confidence drops to `heuristic`. Never
  put the marker you wait for inside your sent text; split it at runtime
  (`print('OUT_' + '42')`). Leftover echoes from earlier experiments pollute
  later waits — use a fresh session for sensitive experiments.
- **Spinners defeat quiet** — `--quiet-ms` also gates on the raw stream's
  last-write time, but pick 2-3x the frame period and anchor with `--until`
  when possible. A program that *starts* spinning after your input can
  false-settle a large quiet value — wait for the stream to start first.
  **Menus are quiet-hostile**: inside modal pickers use `sleep 0.5-1` +
  `screen`, not `--quiet-ms`.
- **Long typed text wraps** — a ~90-char `--type` wraps on a 100-col pane; a
  `--until` pattern spanning that text must match the *wrapped* screen, or keep
  sent commands short and let the program print the marker.
- **Leaking sessions** — always `stop` when done (or `tmux kill-server` in test
  cleanup).

## Red lines (anti-cheating)

- **Never** bypass the CLI by editing files the program owns or by writing the
  expected output into place. The point is observing real behavior.
- **Never** claim a run happened without evidence: attach `trace` output or
  `raw.log` events, and for layout claims the `screenshot` path.
- Timeouts are data: report the `error` JSON, don't retry until it "passes".

## Worked example: nano edit + save

```bash
$TD start -n nano-demo --cmd bash --width 100 --height 30
$TD wait  -n nano-demo --cmd-done --timeout 10          # shell ready (fact)
$TD send  -n nano-demo --type "nano notes.txt" --key Enter
$TD wait  -n nano-demo --until 'GNU nano' --timeout 15  # TUI is up
$TD send  -n nano-demo --type "hello from an agent"
$TD send  -n nano-demo --key C-o                        # save
$TD wait  -n nano-demo --until 'File Name to Write' --timeout 10
$TD send  -n nano-demo --key Enter                       # confirm filename
$TD wait  -n nano-demo --cmd-done --expect-code 0 --timeout 15   # back at shell (fact)
$TD stop  -n nano-demo
```

## Getting help

- Issues: https://github.com/uobe1/term-debug/issues
- Install problems: [installation.md](installation.md)
- Full scenario library: [SKILL.md](../../skills/debugging-interactive-terminals/SKILL.md)
