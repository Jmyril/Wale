"""Test harness setup: make ``src/`` importable and run from the repo root.

The Markov core loads its corpus and base via paths relative to the working
directory, so the tests must execute from the project root.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
os.chdir(ROOT)
