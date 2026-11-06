#!/usr/bin/env python3
"""Run the progress engine with this Python. The engine is one file, the same on every platform.

Usage: progress.py [--harness NAME] COMMAND [OPTIONS]

Commands: show, step NAME STATUS, render, status, browser on|off.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MINIMUM_PYTHON = (3, 9)


def main(argv: list[str]) -> int:
    here = Path(__file__).resolve().parent
    engine = here.parent / "progress" / "engine.py"
    if not engine.is_file():
        print(f"progress: the page was not updated: {engine} is missing. Run: specify integration upgrade", file=sys.stderr)
        return 0
    if sys.version_info < MINIMUM_PYTHON:
        print("progress: the page was not updated: it needs Python 3.9 or newer.", file=sys.stderr)
        return 0
    return subprocess.call([sys.executable, "-I", str(engine), "--root", str(here.parents[2]), *argv])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
