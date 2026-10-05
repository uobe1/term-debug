"""Shell integration injection: a bashrc that emits OSC 133 markers.

Layout (VSCode template adapted):
  PROMPT_COMMAND first entry reads $?  -> D;<code> then A (next prompt)
  PS0                                  -> C (pre-execution)
  PS1 wrapped in \\[ \\]                -> B (command line start)

The rcfile takes responsibility for the environment: source the Termux
system bashrc so an interactive bash with --rcfile stays recognizable.
"""


def bashrc_template(system_bashrc: str) -> str:
    lines = [
        "# --- term-debug v2 shell integration (OSC 133) ---",
        f'[ -r "{system_bashrc}" ] && . "{system_bashrc}"',
        "__td_ps() { printf '\\033]133;D;%s\\007\\033]133;A\\007' \"$1\"; }",
        'case ":$PROMPT_COMMAND:" in',
        '  *"__td_ps"*) ;;  # already integrated',
        '  "::") PROMPT_COMMAND="__td_ps \\$?" ;;',
        '  *) PROMPT_COMMAND="__td_ps \\$?;${PROMPT_COMMAND:+\\$PROMPT_COMMAND}" ;;',
        "esac",
        'PS0="${PS0}\\e]133;C\\a"',
        'PS1="\\[\\e]133;B\\a\\]$PS1"',
        "",
    ]
    return "\n".join(lines)
