# term-debug

term-debug is an evidence-driven CLI that gives your coding agents complete control
over **interactive terminal programs** — shells, nano/vim, REPLs, animated TUIs
(ink / bubbletea), even nested tmux — and replaces guessing with proof. Built
agent-first, in the spirit of open-source AI-skill projects like
[superpowers](https://github.com/obra/superpowers) and
[anthropics/skills](https://github.com/anthropics/skills): the docs are written *for
the agent*, the CLI is the tool interface, and every answer comes with evidence
attached.

![version](https://img.shields.io/badge/version-2.0.0a1-orange)
![python](https://img.shields.io/badge/python-3.14%2B-3776AB?logo=python&logoColor=white)
![requires](https://img.shields.io/badge/external%20dep-tmux%203.x-1BB91F)
![stars](https://img.shields.io/github/stars/uobe1/term-debug?style=social)
![issues](https://img.shields.io/github/issues/uobe1/term-debug)
![license](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)

## How it works

It starts the moment your agent needs to know something stdout can't tell it: *"did
the command finish?" "what was the exit code?" "which row is selected in that TUI?"*
Instead of blind `sleep`s and screen-scraping prayers, your agent drives the program
inside a real tmux pane and gets verdicts, not vibes:

- Every `wait` returns a verdict with a **confidence level** — `fact` (terminal
  protocol: OSC 133 shell integration, pane death) beats `inference` (screen regex,
  echo-aware) beats `heuristic` (animation-immune quiet sampling).
- Every failure returns **single-line structured JSON** with a screen snapshot
  attached. Timeouts never kill the target — they return evidence.
- A full **protocol-level recording** (`raw.log`, asciicast v2) of every session is
  kept on disk as ground truth: injections, output bytes, sync points.

Because skills trigger by description, your agent doesn't need special instructions —
it reads [the skill](skills/debugging-interactive-terminals/SKILL.md) and just works.

## Installation

**Note:** installation differs by setup. All methods need Python **3.14+** (stdlib
only) and **tmux 3.x** on `PATH`; Pillow is optional (screenshots only).

### Verify prerequisites

```bash
python3 --version   # 3.14+
tmux -V             # tmux 3.x
```

### uv (recommended)

```bash
uv tool install git+https://github.com/uobe1/term-debug.git
```

### pip

```bash
python3 -m pip install git+https://github.com/uobe1/term-debug.git
```

### Zero install (local clone)

```bash
git clone https://github.com/uobe1/term-debug.git
uvx --from ./term-debug term-debug --help    # run once without installing
# or install editable from the clone:
uv tool install ./term-debug -e
```

### Verify installation

```bash
term-debug sessions
# → [] or a JSON array of tmux sessions — both are success
```

**Detailed docs:** [docs/installation.md](docs/installation.md) — written to be
followed end-to-end by an AI agent.

## Use as an agent skill

The repo ships an agent-facing skill manual with usage patterns and hard-won
pitfalls. Tell your agent:

```
Fetch and follow instructions from
https://raw.githubusercontent.com/uobe1/term-debug/refs/heads/main/skills/debugging-interactive-terminals/SKILL.md
```

For Claude Code / CodeBuddy, install it as a skill by copying or linking
`skills/debugging-interactive-terminals/` into your skills directory.

## The basic workflow

```bash
term-debug start -n demo --cmd bash --width 100 --height 30
term-debug send  -n demo --type "make build" --key Enter
term-debug wait  -n demo --cmd-done --expect-code 0 --timeout 120
# → {"verdict": "met", "confidence": "fact", "exit_code": 0, ...}
```

That's the whole loop: *start → send → wait for fact → act*. The wait engine also
speaks regex (`--until`), quiet detection (`--quiet-ms`), pane death (`--exit`),
AND-composition, and SGR mouse (`click X Y`).

**Detailed docs:** [docs/usage.md](docs/usage.md) — the agent-facing usage guide:
mental model, decision tables, worked examples, common mistakes, red lines.

## Architecture

```
agent → term-debug CLI (stateless client) → tmux server → pane (target program)
                                              └→ pipe.py (recorder sink, one per pane)
```

Service/Client split: the CLI is a short-lived, stateless client with zero resident
memory; the tmux server is the service owning PTYs/sessions. All state lives on disk
under `$XDG_STATE_HOME/term-debug/<session>/` — `raw.log` (asciicast v2 evidence
store) and `state.json` (atomic locator/recorder state, with `last_send_offset` as a
**byte offset** into `raw.log`, so echo can never fake completion).

Key internal guarantees: text/keys never mixed in one `send-keys` call; `--hex`
split one byte per `-H`; OSC 133 A/B/C/D state machine tolerates chunk boundaries;
composite verdicts take the weakest member's confidence; every failure surfaces as a
fixed-code `TDError`, single-line JSON, exit code 1.

## Testing

```bash
# Unit tests — pure asserts, each file runs standalone
python3 tests/unit/test_errors.py
python3 -m pytest tests/unit/

# E2E — standalone bash scripts driving real tmux + real programs (no mocks)
bash tests/e2e/01_start_stop.sh
for t in tests/e2e/*.sh; do bash "$t" || break; done
```

## Contributing

Bug reports, docs and code are welcome — please use **issues + pull requests**
(direct pushes to `main` are blocked). See [CONTRIBUTING.md](CONTRIBUTING.md).

## Star history

[![Star History Chart](https://api.star-history.com/svg?repos=uobe1/term-debug&type=Date)](https://star-history.com/#uobe1/term-debug&Date)

## License

Copyright (C) 2026 Uobe

Released under the **GNU General Public License v3.0 or later** (SPDX identifier:
`GPL-3.0-or-later`). See [LICENSE](LICENSE). This program is distributed in the hope
that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty
of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

## Design docs

- [Architecture & design (Chinese)](docs/plans/2026-10-05-term-debug-v2-design.md)
- [Task-by-task implementation plan (Chinese)](docs/plans/2026-10-05-term-debug-v2-implementation.md)
- Agent-facing user manual: [skills/debugging-interactive-terminals/SKILL.md](skills/debugging-interactive-terminals/SKILL.md)
