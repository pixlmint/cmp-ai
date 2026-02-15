import os
import sys

# When run as `python scripts/generate`, Python adds scripts/generate/ to
# sys.path but doesn't set up package context, breaking relative imports.
# Fix by ensuring the parent directory (scripts/) is on sys.path so that
# `generate` is importable as a proper package.
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from generate._cli import main

main()
