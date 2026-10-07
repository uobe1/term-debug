#!/usr/bin/env python3
"""Raw-terminal menu fixture that DEBOUNCES arrow keys, like frame-driven
TUI pickers and menu widgets do: after an arrow is applied, further arrows
arriving within DEBOUNCE seconds are dropped. Deterministic — the window is
anchored at each application, not at wall-clock ticks.

Output:
  MENU_READY        first paint
  SELECTED:<n>      selection index (0-based), repainted on every change
  QUIT              on 'q' (clean exit)

Start: SELECTED:0. Up increases, Down decreases (floor 0).
"""
import os
import select
import sys
import termios
import time
import tty

DEBOUNCE = 0.45


def main() -> None:
    old = termios.tcgetattr(0)
    out = sys.stdout
    tty.setcbreak(0)
    sel = 0
    last_applied = 0.0

    def paint() -> None:
        out.write(f"\x1b[2J\x1b[HMENU_READY\nSELECTED:{sel}\n")
        out.flush()

    paint()
    try:
        buf = ""
        while True:
            r, _, _ = select.select([0], [], [], 0.1)
            if r:
                chunk = os.read(0, 1024).decode("utf-8", "replace")
                buf += chunk
            if "q" in buf:
                out.write("QUIT\n")
                out.flush()
                return
            # process arrows in arrival order against the cooldown window
            while True:
                up = buf.find("\x1b[A")
                down = buf.find("\x1b[B")
                if up == -1 and down == -1:
                    buf = ""
                    break
                if up != -1 and (down == -1 or up < down):
                    kind, pos = "up", up
                else:
                    kind, pos = "down", down
                buf = buf[pos + 3:]
                now = time.monotonic()
                if now - last_applied >= DEBOUNCE:
                    sel = sel + 1 if kind == "up" else max(0, sel - 1)
                    last_applied = now
                    paint()
    finally:
        termios.tcsetattr(0, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
