# Contributing to term-debug

Thanks for your interest in contributing! Bug reports, documentation and code are all
welcome. The workflow is **issues + pull requests**: direct pushes to `main` are
blocked by a branch ruleset, so all changes — including small ones — arrive through PRs.

## Reporting bugs

Open a [GitHub issue](https://github.com/uobe1/term-debug/issues) and include:

1. **The structured error JSON** — term-debug prints every failure as single-line JSON
   with an evidence snapshot attached. Paste it verbatim; it is designed for this.
2. `tmux -V`, `python3 --version`, OS/terminal.
3. A minimal reproduction: the exact `start` / `send` / `wait` / `screen` commands.
4. If relevant, a `trace -n NAME` excerpt or the session's `raw.log` tail
   (**sanitize first** — recordings can contain anything your pane displayed).

Feature requests are also issues — please describe the scenario you are driving
(program, what you need to observe) rather than the API you imagine.

## Development workflow

0. **Local setup** — the source tree runs without any install step:
   ```bash
   PYTHONPATH=src python3 -m termdebug --help      # run from a source checkout
   uv tool install -e .                            # or get the `term-debug` command
   ```
   Unit tests and E2E scripts manage `sys.path` / `PYTHONPATH` themselves; E2E
   isolation (socket name, `XDG_STATE_HOME`) is automatic — never point them at
   your real `~/.local/state/term-debug/`.
1. Fork / create a feature branch from `main`.
2. Write the **failing E2E test first** (see discipline below).
3. Implement the minimal change until it goes green.
4. Run the full regression suite.
5. Open a pull request referencing the issue.

### e2e-first discipline

- E2E scripts drive **real tmux and real programs through the CLI only** — no mocks,
  no bypassing the CLI, no editing files the target program owns. Helper programs
  for scenarios that need a scripted target (e.g. a deterministic debouncing menu)
  live in `tests/fixtures/`.
- Follow the self-isolation pattern of `tests/e2e/*.sh`: unique tmux socket name per
  run, `XDG_STATE_HOME` pointed at a `mktemp -d` directory, `trap`-based cleanup,
  and always `stop` your sessions.
- Unit tests live in `tests/unit/test_*.py`, are pure asserts (pytest optional), and
  insert the repo root into `sys.path` themselves.

### Hard guarantees your change must preserve

- **Confidence taxonomy**: `fact` (OSC 133 / pane death) > `inference` (screen regex)
  > `heuristic` (quiet sampling). Composite wait verdicts take the weakest member's
  confidence. Never let a heuristic masquerade as fact.
- **Honest degradation**: unmanaged panes (nested tmux — no `state.json`/`raw.log`)
  get screen-only waits with confidence capped at `heuristic` and a `degraded`
  marker in the verdict; shell-protocol facts refuse with `unmanaged-pane`. Never
  silently overclaim evidence that cannot be gathered, and never create record
  state as a side effect of touching an unmanaged pane.
- **Injection red lines**: `-l` text and key names are never mixed in one `send-keys`
  call; `--hex` is split one byte per `-H`.
- **Structured errors**: every failure surfaces as a `TDError` with a code from the
  fixed table in `termdebug/errors.py`, as single-line JSON on stderr with exit code 1.
  Timeouts return an evidence snapshot and never kill the target.
- **Atomic state**: `state.json` is always written via tmp + rename;
  `last_send_offset` is a byte offset into `raw.log`, never a timestamp.
- **Stateless client**: no resident daemon, no in-memory state across invocations.

### Dependencies

Python 3.14 **stdlib only**; tmux is the only external hard dependency; Pillow stays
optional (screenshots only). Do not add hard dependencies without discussing it in an
issue first.

### Real-world pitfalls → update the skill

`skills/debugging-interactive-terminals/SKILL.md` ("Common Mistakes") encodes
hard-won behavioral findings (echo-anchored waits, spinner/quiet resonance, menu
arrow debounce, kitty key encodings, …). If you fix a real-world pitfall, update the
skill in the same PR so agents benefit immediately.

## Commit messages

Follow the existing style:

```
feat(v2): ...
fix(v2): ...
docs(v2): ...
```

One logical change per commit; the commit message should say *why*, the diff says *what*.

## Pull request checklist

- [ ] Linked issue (or short scenario description)
- [ ] E2E test added first and now green; full `tests/e2e/` regression passes
- [ ] Unit tests updated/added where pure logic changed
- [ ] No new hard dependencies; stdlib only
- [ ] New failure paths return structured `TDError` JSON, not exceptions/raw text
- [ ] `SKILL.md` updated if this fixes an agent-facing pitfall
- [ ] No secrets or personal data in code, logs, or recordings

## Licensing

term-debug is licensed under the **GNU General Public License v3.0 or later**
(`GPL-3.0-or-later`), see [LICENSE](LICENSE). By opening a PR you agree that your
contribution is licensed under the same license (GPL-3.0-or-later).
