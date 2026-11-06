#!/usr/bin/env python3
"""Run the script a Spec Kit command starts with, then record the step and redraw the progress page.

A model parses that script's output, so it passes through untouched: same stdout, same stderr, same
exit code. This wrapper adds nothing of its own, and nothing it does can fail the command.

Usage: run_step.py STEP HARNESS SCRIPT [ARG ...]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def update_progress(step: str, harness: str) -> None:
    command = [sys.executable, "-I", str(Path(__file__).resolve().with_name("progress.py"))]
    command += ["--harness", harness, "step", step, "in_progress", "--quiet"]
    try:
        subprocess.call(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass


def locate(script: str) -> str:
    """Installed commands name the script from the project root. The event dispatcher anchors only
    the first path of a command's header, so there it still reads scripts/..., under .specify. A
    scripts/ folder the project has of its own must not win over it."""
    anchored = Path(__file__).resolve().parents[2] / script
    return str(anchored) if anchored.is_file() else script


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: run_step.py STEP HARNESS SCRIPT [ARG ...]", file=sys.stderr)
        return 2
    step, harness, script, *rest = argv
    status = subprocess.call([sys.executable, locate(script), *rest])
    if status == 0:
        update_progress(step, harness)
    return 128 - status if status < 0 else status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
