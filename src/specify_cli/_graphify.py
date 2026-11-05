"""Graphify as a part of specify: where it is, which version, and the first graph of a project.

Graphify is a dependency of specify, so it is beside this Python and not on PATH. Reading a project's
graph stays behind the gate of the capabilities extension: the first graph is built through it too.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REINSTALL_COMMAND = "uv tool install specify-cli --force --from git+https://github.com/lema017/speckit-vs.git"
GATE = ".specify/extensions/capabilities/scripts/python/cap_graph.py"
VERSION_SECONDS = 60
# The gate gives up on the tool after 600 seconds and reports it, so this only guards against a hung gate.
BUILD_SECONDS = 660


def _environment_bin() -> str:
    return str(Path(sys.executable).parent)


def graphify_path() -> str | None:
    """Beside this Python first: it is the version this fork ships. Then PATH."""
    return shutil.which("graphify", path=_environment_bin()) or shutil.which("graphify")


def graphify_version() -> str | None:
    """The version of the tool that runs, or None if it is missing or cannot run."""
    path = graphify_path()
    if path is None:
        return None
    try:
        done = subprocess.run(
            [path, "--version"], capture_output=True, encoding="utf-8", errors="replace",
            timeout=VERSION_SECONDS, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"\d+\.\d+\.\d+", done.stdout or "") if done.returncode == 0 else None
    return match.group(0) if match else None


def build_first_graph(project_path: Path) -> tuple[str, str]:
    """Build the graph of a new project. Never raises: a project is usable without its first graph.

    Returns ``("complete" | "skip" | "error", detail)``, in the words of the step tracker.
    """
    gate = project_path / GATE
    if not gate.is_file():
        return "skip", "not used in this project"
    env = dict(os.environ)
    # So the gate finds this environment's specify and Graphify, however specify was started.
    env["PATH"] = _environment_bin() + os.pathsep + env.get("PATH", "")
    try:
        done = subprocess.run(
            [sys.executable, "-I", "-S", str(gate), "update", "--root", str(project_path)],
            capture_output=True, encoding="utf-8", errors="replace", env=env,
            timeout=BUILD_SECONDS, check=False,
        )
        report = json.loads(done.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return "error", f"not built: {error}"
    if report.get("status") == "ok":
        return "complete", "graph built"
    reason = report.get("reason", "unknown")
    if reason == "no-code":
        return "skip", "no code yet"
    return "error", f"not built: {reason}"
