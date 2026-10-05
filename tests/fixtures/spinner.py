#!/usr/bin/env python3
"""Animation simulator fixture: redraws one line every 150ms for ~3s.

Used by E2E-07 to prove --quiet-ms does not fire while an animation runs.
"""
import sys
import time

FRAMES = "|/-\\|/-\\|/-\\|/-\\"  # 20 frames x 150ms ~= 3s

for f in FRAMES:
    sys.stdout.write(f"\r{f} working\033[K")
    sys.stdout.flush()
    time.sleep(0.15)

sys.stdout.write("\rSPINNER_DONE\033[K\n")
