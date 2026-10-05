#!/usr/bin/env python3
"""Raw-terminal fixture: enables 1000h+1006h mouse reporting; a click
prints CLICKED:x,y with 0-based coordinates (like curses programs do).

Hand-rolled instead of curses: the SGR (1006) response must come from the
program itself, and Termux's curses terminfo only negotiates X10.
"""
import os
import re
import sys
import termios
import tty

PRESS = re.compile(r"\x1b\[<0;(\d+);(\d+)M")
RELEASE = re.compile(r"\x1b\[<0;(\d+);(\d+)m")


def main() -> None:
    old = termios.tcgetattr(0)
    out = sys.stdout
    out.write("\x1b[?1000h\x1b[?1006h")
    out.write("MOUSE_READY q=quit\n")
    out.flush()
    tty.setcbreak(0)
    buf = ""
    try:
        while True:
            chunk = os.read(0, 1024).decode("utf-8", "replace")
            if not chunk:
                break
            buf += chunk
            if "q" in chunk:
                break
            rel = RELEASE.search(buf)
            if rel:
                x, y = int(rel.group(1)) - 1, int(rel.group(2)) - 1
                out.write(f"\x1b[{y + 1};1HCLICKED:{x},{y}\x1b[K")
                out.flush()
                buf = ""
                continue
            if PRESS.search(buf):
                buf = ""  # press consumed; wait for release
    finally:
        out.write("\x1b[?1006l\x1b[?1000l")
        out.flush()
        termios.tcsetattr(0, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
