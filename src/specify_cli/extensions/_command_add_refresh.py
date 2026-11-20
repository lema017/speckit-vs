"""The refresh phase of ``specify extension add``.

``specify upgrade`` updates an extension that ships with specify by adding it
again. That replaces the files of the extension. It does not touch what the
extension once wrote into the project: the block for agents that
``capabilities`` keeps in the agent file stayed as the older version wrote it,
until a review sealed a spec.

This phase asks the extension to bring that up to date. The extension decides
whether there is anything to do: ``capabilities`` writes nothing into a
project that never had its block.

It runs the script that ships with specify, never a file of the project, and
only for an extension added from that shipped copy: one added from a
directory, a URL or a catalog is someone else's code. It never fails the add:
the extension is installed either way, and its own commands refresh the same
things later.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from rich.markup import escape

# Extension id -> its script, relative to the extension, and the arguments
# that make it refresh what it keeps in a project.
_REFRESH: dict[str, tuple[str, tuple[str, ...]]] = {
    "capabilities": ("scripts/python/capabilities.py", ("refresh",)),
}

_TIMEOUT_SECONDS: float = 60

_SKIPPED = "skipped "


def refresh_lines(project_root: Path, extension_id: str, shipped: Path) -> list[str]:
    """Refresh what *extension_id* keeps in the project, and return what to print about it.

    *shipped* is the directory of the extension as it ships with specify. The
    result is empty when the extension keeps nothing, when its script is not
    there, or when nothing changed.
    """
    entry = _REFRESH.get(extension_id)
    if entry is None:
        return []
    script = shipped / entry[0]
    if not script.is_file():
        return []

    # -I: only the script and the standard library are loaded, whatever the
    # project or the environment hold. -B: no bytecode is written.
    argv = [sys.executable, "-I", "-B", str(script), *entry[1], "--root", str(project_root)]
    try:
        done = subprocess.run(
            argv,
            cwd=project_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [_problem(extension_id, f"it did not answer in {_TIMEOUT_SECONDS:g} seconds")]
    except OSError as exc:
        return [_problem(extension_id, str(exc))]

    if done.returncode != 0:
        last = (done.stderr or "").strip().splitlines()[-1:]
        why = f"it ended with code {done.returncode}" + (f": {last[0]}" if last else "")
        return [_problem(extension_id, why)]

    try:
        setup = json.loads(done.stdout)["setup"]
    except (ValueError, KeyError, TypeError):
        setup = None
    if not isinstance(setup, list) or not all(isinstance(item, str) for item in setup):
        return [_problem(extension_id, "its answer could not be read")]

    lines = []
    updated = [item for item in setup if not item.startswith(_SKIPPED)]
    if updated:
        lines.append("Brought up to date: " + escape(", ".join(updated)))
    for item in setup:
        if item.startswith(_SKIPPED):
            lines.append("[yellow]⚠[/yellow]  Not brought up to date: " + escape(item[len(_SKIPPED):]))
    return lines


def _problem(extension_id: str, why: str) -> str:
    return (
        f"[yellow]⚠[/yellow]  Could not bring up to date what {escape(extension_id)} keeps in this project: "
        f"{escape(why)}. Its own commands do it the next time a spec is reviewed or folded."
    )
