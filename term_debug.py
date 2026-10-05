#!/usr/bin/env python3
"""term-debug v2 entry shim; implementation lives in the termdebug package."""
import sys

from termdebug.cli import main

if __name__ == "__main__":
    sys.exit(main())
