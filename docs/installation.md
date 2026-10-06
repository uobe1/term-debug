# Installing term-debug

Complete guide for installing the term-debug CLI.

## Requirements

| Component | Version | Why |
|---|---|---|
| Python | **3.14+** | the development and E2E baseline; `requires-python` in `pyproject.toml` enforces it |
| tmux | **3.x** | the service side. OSC 133 passthrough, SGR mouse and `remain-on-exit` behavior rely on 3.x |
| Pillow | any current release | optional. Only `screenshot` needs it; every other command is Pillow-free |

Check what you have:

```bash
python3 --version
tmux -V
```

No tmux? Install it with the system package manager first (`pkg install tmux` on
Termux, `apt install tmux` on Debian/Ubuntu, `brew install tmux` on macOS). GNU
screen is not a substitute — term-debug drives panes through tmux's own
interfaces (`pipe-pane`, `capture-pane -e`, `send-keys`).

term-debug has **zero Python dependencies**. tmux is an external binary, not a
pip package.

## Installation

**Note:** pick one method. uv manages an isolated tool environment; pip installs
into whatever environment is currently active.

### uv (recommended)

```bash
uv tool install git+https://github.com/uobe1/term-debug.git
```

This installs a `term-debug` command into uv's tool bin (usually `~/.local/bin`).
If `term-debug --help` is not found afterwards, add that directory to `PATH`.

For screenshot support, add Pillow to the tool environment:

```bash
uv tool install git+https://github.com/uobe1/term-debug.git --with pillow
```

### pip

```bash
python3 -m pip install git+https://github.com/uobe1/term-debug.git
```

### From a local clone (development)

```bash
git clone https://github.com/uobe1/term-debug.git
cd term-debug
uv tool install -e .      # editable: source edits take effect immediately
```

To run once without installing anything:

```bash
uvx --from . term-debug --help
```

### Verify installation

```bash
term-debug sessions
# → [] — or a JSON array of existing tmux sessions; both are success

term-debug start -n install-check --cmd bash --width 80 --height 24
term-debug send  -n install-check --type "echo ok" --key Enter
term-debug wait  -n install-check --cmd-done --expect-code 0 --timeout 10
# → {"verdict": "met", "confidence": "fact", "exit_code": 0, ...}
term-debug stop  -n install-check
```

All five commands must complete without an `{"error": ...}` object on stderr.
The `confidence: fact` in the wait verdict is the part that matters — it means
the exit code came from the shell protocol (OSC 133), not from screen guessing.

### Migrating from the old shim layout

Early v2 checkouts exposed a root-level `term_debug.py` shim. It has been
removed; the package now lives in `src/termdebug/` and runs as
`python -m termdebug`. If your scripts still call `python3 term_debug.py`,
replace the call with `term-debug` (installed) or
`PYTHONPATH=<repo>/src python3 -m termdebug` (source tree).

Session data has also moved: it used to live under
`$XDG_CACHE_HOME/term-debug/` (i.e. `~/.cache/term-debug/`) and now lives under
`$XDG_STATE_HOME/term-debug/` (i.e. `~/.local/state/term-debug/`) — per the XDG
Base Directory spec, recordings and locator state are *logs / current state*,
not discardable cache. Existing recordings are not migrated or read from the
old location; copy the directory over manually if you need them.

## Updating

```bash
uv tool upgrade term-debug
# or
python3 -m pip install -U git+https://github.com/uobe1/term-debug.git
```

To pin a version while the 2.0.0 alpha line is moving, append a git ref to the
URL — `@<tag>` or `@<commit>`:

```bash
uv tool install git+https://github.com/uobe1/term-debug.git@<commit>
```

(No tags have been cut yet; pin a commit if you need stability.)

## Uninstall

```bash
uv tool uninstall term-debug
# or
python3 -m pip uninstall term-debug
```

Recordings under `$XDG_STATE_HOME/term-debug/` are plain files; delete the
directory for a full purge.

## Troubleshooting

### `term-debug: command not found` after uv tool install

uv's tool bin is not on `PATH`. Run `uv tool update-shell` (adds it and applies
on next login) or export `PATH="$HOME/.local/bin:$PATH"` in the current shell.

### `{"error":{"code":"pillow-missing",...}}` from `screenshot`

Expected without Pillow — the error is structured, not a crash. Reinstall with
`--with pillow`, or set `TERM_DEBUG_DISABLE_IMAGE=1` to make the text-only
behavior explicit.

### `{"error":{"code":"no-shell-integration",...}}` from `--cmd-done`

Normal for non-bash sessions: the OSC 133 markers are injected into bash only.
Wait with `--until` anchored on the program's own output marker instead.

### Sessions "disappear" between commands

`XDG_STATE_HOME` changed between `start` and the later command. Locator and
recorder state live under `$XDG_STATE_HOME/term-debug/<session>/`; keep that
variable stable for the whole working session.

## Getting help

- Issues: https://github.com/uobe1/term-debug/issues
- Driving patterns for agents: [usage.md](usage.md)
- Agent skill manual: [SKILL.md](../skills/debugging-interactive-terminals/SKILL.md)

When filing a bug, paste the structured error JSON verbatim — it already
contains the screen snapshot, cursor position and raw-stream tail needed to
reproduce.
