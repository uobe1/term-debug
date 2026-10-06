#!/usr/bin/env bash
# Blind-test protocol for term-debug v2 (design section 8).
#
# Usage:
#   bash tests/blind/run_blind.sh          # print the protocol + prompt template
#   TERM_DEBUG_DISABLE_IMAGE=1 bash ...    # heuristics-only mode for testers
#
# The env switch TERM_DEBUG_DISABLE_IMAGE=1 makes `screenshot` return a
# structured pillow-missing-style error, so a subagent tester cannot use the
# image channel and must rely on the text channels (heuristic tier).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cat <<EOF
== term-debug v2 blind-test protocol ==

Tester profile:
  - A "volunteer user": knows the task, NOT the tool's internals.
  - Gets: the CLI (python3 -m termdebug, via src/) + skills/debugging-interactive-terminals/SKILL.md.
  - Runs with TERM_DEBUG_DISABLE_IMAGE=1 (heuristics-only) or without (full).
  - Right to complain: ends output with 'FEEDBACK: <one line about what
    confused / was missing / had to be guessed>'.

Scoring:
  - Task completion (0/1), path quality (waits used? blind sleeps? evidence
    attached?), complaints logged into the usability feedback list.

Prompt template (hand to the tester agent):

  You are testing a terminal-debugging CLI. Read the skill at
  ${ROOT}/skills/debugging-interactive-terminals/SKILL.md, then use the CLI
  it documents (PYTHONPATH=${ROOT}/src python3 -m termdebug ...) to complete this task:

  <TASK: e.g. reproduce and fix the two bugs in tests/fixtures/todo/todo.js,
  running it with bun — debug first, fix code second, prove both fixes.>

  Rules: drive the program only through the CLI; attach trace/screenshot
  evidence for every claim; end with FEEDBACK: <one line>.

EOF
