# Installing term-use

**term-use** is an evidence-driven CLI that lets coding agents drive and debug
interactive terminal programs — shells, nano/vim, REPLs, ink/bubbletea TUIs, even
nested tmux — through tmux. It replaces blind `sleep`s and screen-scraping with
verdicts backed by evidence.

- Project / source: **https://github.com/uobe1/term-use**
- Agent skill manual: `skills/debugging-interactive-terminals/SKILL.md`

term-use is **two parts**:

1. the **CLI** (`term-use`) — the tool your agent drives, and
2. the **agent skill** (`debugging-interactive-terminals`) — the manual that teaches
   your agent *when and how* to drive it.

Install **both**. There are two ways to do it — pick whichever fits.

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
screen is not a substitute — term-use drives panes through tmux's own
interfaces (`pipe-pane`, `capture-pane -e`, `send-keys`).

term-use has **zero Python dependencies**. tmux is an external binary, not a
pip package.

---

## Option A — automatic install (let your agent do it)

Give your agent this install doc and let it run the steps itself. Works in Claude Code,
CodeBuddy, Codex, Cursor, Gemini CLI, OpenCode — any agent that can read a file or a
URL.

Copy one of these prompts and send it to your agent:

```text
Read docs/en/installation.md in the term-use repo (https://github.com/uobe1/term-use)
and install term-use by following it: install the `term-use` CLI and the
`debugging-interactive-terminals` skill into my agent. Tell me what you did and where
each part landed.
```

If the agent can only fetch URLs (not local files), use the raw link instead:

```text
Read https://raw.githubusercontent.com/uobe1/term-use/main/docs/en/installation.md and
install term-use by following it: install the `term-use` CLI and the
`debugging-interactive-terminals` skill into my agent. Tell me what you did.
```

The agent follows the [Install steps](#install-steps) below — it installs the CLI
*and* the skill. No separate script is needed; the doc is the instruction set.

---

## Option B — manual install

Do the [Install steps](#install-steps) yourself, in a terminal. Same result as Option
A: both the CLI and the skill get installed.

<details>
<summary>Why are there two options?</summary>

They install the identical things. Option A hands the same steps to your agent so you
don't type them; Option B is for when you want to do it by hand or the agent isn't
available. Pick one — not both.
</details>

---

## Install steps

Both options run these steps. The agent runs them from Option A; you run them from
Option B.

### Step 1 — install the CLI

Pick one method. uv manages an isolated tool environment; pip installs into whatever
environment is currently active; the local-clone method is for development.

**uv (recommended)**

```bash
uv tool install git+https://github.com/uobe1/term-use.git
```

For screenshot support, add Pillow to the tool environment:

```bash
uv tool install git+https://github.com/uobe1/term-use.git --with pillow
```

**pip**

```bash
python3 -m pip install git+https://github.com/uobe1/term-use.git
```

**From a local clone (development)**

```bash
git clone https://github.com/uobe1/term-use.git
cd term-use
uv tool install -e .      # editable: source edits take effect immediately
```

To run once without installing anything:

```bash
uvx --from . term-use --help
```

If `term-use --help` is not found after a uv install, uv's tool bin
(`~/.local/bin`) is not on `PATH` — run `uv tool update-shell` or export
`PATH="$HOME/.local/bin:$PATH"`.

### Step 2 — install the skill

The skill is the `skills/debugging-interactive-terminals/` directory in this repo.
Copy or symlink it into your agent's skills directory so the agent can find it.

| Agent | Skills directory |
|---|---|
| CodeBuddy | `~/.codebuddy/skills/` |
| Claude Code | `~/.claude/skills/` |
| Codex | `~/.codex/skills/` |
| Cursor | `~/.cursor/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| OpenCode | `~/.config/opencode/skills/` |

From the repo root, symlink (recommended — stays current with `git pull`):

```bash
ln -s "$PWD/skills/debugging-interactive-terminals" \
      ~/.codebuddy/skills/debugging-interactive-terminals
```

…or copy:

```bash
cp -r "$PWD/skills/debugging-interactive-terminals" \
      ~/.codebuddy/skills/debugging-interactive-terminals
```

(Replace `~/.codebuddy/skills` with your agent's directory from the table above.)

Restart the agent (or start a fresh session) so it picks up the new skill. It then
triggers automatically by description — no further setup.

### Step 3 — verify

```bash
term-use sessions
# → [] — or a JSON array of existing tmux sessions; both are success

ls ~/.codebuddy/skills/debugging-interactive-terminals/SKILL.md   # skill present
```

A real end-to-end check that the CLI *and* the method work:

```bash
term-use start -n install-check --cmd bash --width 80 --height 24
term-use send  -n install-check --type "echo ok" --key Enter
term-use wait  -n install-check --cmd-done --expect-code 0 --timeout 10
# → {"verdict": "met", "confidence": "fact", "exit_code": 0, ...}
term-use stop  -n install-check
```

All five commands must complete without an `{"error": ...}` object on stderr. The
`confidence: fact` in the wait verdict is the part that matters — it means the exit
code came from the shell protocol (OSC 133), not from screen guessing.

---

### Migrating from the old shim layout

Early v2 checkouts exposed a root-level `term_debug.py` shim. It has been removed;
the package now lives in `src/termuse/` and runs as `python -m termuse`. If your
scripts still call `python3 term_debug.py`, replace the call with `term-use`
(installed) or `PYTHONPATH=<repo>/src python3 -m termuse` (source tree).

Session data has also moved: it used to live under
`$XDG_CACHE_HOME/term-use/` (i.e. `~/.cache/term-use/`) and now lives under
`$XDG_STATE_HOME/term-use/` (i.e. `~/.local/state/term-use/`) — per the XDG
Base Directory spec, recordings and locator state are *logs / current state*, not
discardable cache. Existing recordings are not migrated or read from the old
location; copy the directory over manually if you need them.

## Updating

```bash
uv tool upgrade term-use
# or
python3 -m pip install -U git+https://github.com/uobe1/term-use.git
```

To pin a version while the 2.0.0 alpha line is moving, append a git ref to the
URL — `@<tag>` or `@<commit>`:

```bash
uv tool install git+https://github.com/uobe1/term-use.git@<commit>
```

(No tags have been cut yet; pin a commit if you need stability.)

If you installed the skill by symlink from a clone, re-run `git pull` in the clone to
refresh it. If you copied it, re-copy from a fresh clone.

## Uninstall

```bash
uv tool uninstall term-use
# or
python3 -m pip uninstall term-use
```

Remove the skill from your agent's skills directory:

```bash
rm -rf ~/.codebuddy/skills/debugging-interactive-terminals
```

Recordings under `$XDG_STATE_HOME/term-use/` are plain files; delete the
directory for a full purge.

## Troubleshooting

### `term-use: command not found` after uv tool install

uv's tool bin is not on `PATH`. Run `uv tool update-shell` (adds it and applies on
next login) or export `PATH="$HOME/.local/bin:$PATH"` in the current shell.

### `{"error":{"code":"pillow-missing",...}}` from `screenshot`

Expected without Pillow — the error is structured, not a crash. Reinstall with
`--with pillow`, or set `TERM_USE_DISABLE_IMAGE=1` to make the text-only behavior
explicit.

### `{"error":{"code":"no-shell-integration",...}}` from `--cmd-done`

Normal for non-bash sessions: the OSC 133 markers are injected into bash only. Wait
with `--until` anchored on the program's own output marker instead.

### `{"error":{"code":"shell-not-ready",...}}` from `--shell-ready`

The `true` probe got no answer in time — usually a live interactive program
swallowed it (that is the signal working as designed: send the program's quit
key and re-probe). If the shell was genuinely still starting, retry with a
longer `--timeout`.

### `{"error":{"code":"unmanaged-pane",...}}` from `--cmd-done`

The pane exists in tmux but was not started by term-use (e.g. a nested tmux
pane) — there is no shell-protocol channel on it. The screen channels
(`--until`, `--quiet-ms`) still work there with degraded (heuristic) confidence;
start a managed session (`term-use start -n <name> --cmd bash`) when you need
facts. If the pane IS a term-use session, your `XDG_STATE_HOME` differs
between `start` and the later command — keep it stable.

### Skill not triggering / agent ignores term-use

The skill symlink/copy may be in the wrong directory, or the agent session started
before the skill was added. Confirm
`~/.codebuddy/skills/debugging-interactive-terminals/SKILL.md` exists (adjust the
path for your agent), then restart the agent or open a fresh session.

### Sessions "disappear" between commands

`XDG_STATE_HOME` changed between `start` and the later command. Locator and recorder
state live under `$XDG_STATE_HOME/term-use/<session>/`; keep that variable stable
for the whole working session.

## Getting help

- Issues: https://github.com/uobe1/term-use/issues
- Driving patterns for agents: [usage.md](usage.md)
- Agent skill manual: [SKILL.md](../../skills/debugging-interactive-terminals/SKILL.md)

When filing a bug, paste the structured error JSON verbatim — it already contains the
screen snapshot, cursor position and raw-stream tail needed to reproduce.
