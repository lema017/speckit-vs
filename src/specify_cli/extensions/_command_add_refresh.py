"""The refresh phase of ``specify extension add``.

``specify upgrade`` updates an extension that ships with specify by adding it
again. That replaces the files of the extension. It does not touch what the
extension once wrote into the project: the block for agents that
``capabilities`` keeps in the agent file stayed as the older version wrote it,
until a review sealed a spec.

This phase asks the extension to bring that up to date. The extension decides
whether there is anything to do: ``capabilities`` writes nothing into a
project that never had its block. ``specify init`` is the other caller: it sets
a new project up with ``setup_new_project``, which writes the block where
there was none, so the agent follows the fork from its first command.

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


# Extension id -> the arguments that set up a new project, run by ``specify init``.
# Unlike a refresh, a setup writes into a project that never had the extension's block.
_SETUP: dict[str, tuple[str, ...]] = {
    "capabilities": ("setup",),
}


def run_shipped_script(project_root: Path, extension_id: str, shipped: Path, *, first: bool = False) -> list[str] | None:
    """Run the shipped script of *extension_id* and return its ``setup`` list.

    With *first*, it sets up a new project; otherwise it refreshes one. ``None``
    when the extension keeps nothing in a project or its script is not there.
    Raises ``RuntimeError`` with the reason when the script fails.
    """
    entry = _REFRESH.get(extension_id)
    if entry is None:
        return None
    script = shipped / entry[0]
    if not script.is_file():
        return None
    arguments = _SETUP.get(extension_id) if first else entry[1]
    if arguments is None:
        return None

    # -I: only the script and the standard library are loaded, whatever the
    # project or the environment hold. -B: no bytecode is written.
    argv = [sys.executable, "-I", "-B", str(script), *arguments, "--root", str(project_root)]
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
        raise RuntimeError(f"it did not answer in {_TIMEOUT_SECONDS:g} seconds") from None
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc
    if done.returncode != 0:
        last = (done.stderr or "").strip().splitlines()[-1:]
        raise RuntimeError(f"it ended with code {done.returncode}" + (f": {last[0]}" if last else ""))
    try:
        setup = json.loads(done.stdout)["setup"]
    except (ValueError, KeyError, TypeError):
        setup = None
    if not isinstance(setup, list) or not all(isinstance(item, str) for item in setup):
        raise RuntimeError("its answer could not be read")
    return setup


def refresh_lines(project_root: Path, extension_id: str, shipped: Path) -> list[str]:
    """Refresh what *extension_id* keeps in the project, and return what to print about it.

    *shipped* is the directory of the extension as it ships with specify. The
    result is empty when the extension keeps nothing, when its script is not
    there, or when nothing changed.
    """
    try:
        setup = run_shipped_script(project_root, extension_id, shipped)
    except RuntimeError as exc:
        return [_problem(extension_id, str(exc))]
    if setup is None:
        return []

    lines = []
    updated = [item for item in setup if not item.startswith(_SKIPPED)]
    if updated:
        lines.append("Brought up to date: " + escape(", ".join(updated)))
    for item in setup:
        if item.startswith(_SKIPPED):
            lines.append("[yellow]⚠[/yellow]  Not brought up to date: " + escape(item[len(_SKIPPED):]))
    return lines


def setup_new_project(project_root: Path, extension_id: str, shipped: Path) -> tuple[str, str]:
    """Set up what *extension_id* keeps in a new project, for ``specify init``.

    Returns ``("complete" | "skip" | "error", detail)``, in the words of the
    step tracker. Never raises: the project is usable without it, and a review
    sets it up later.
    """
    try:
        setup = run_shipped_script(project_root, extension_id, shipped, first=True)
    except RuntimeError as exc:
        return "error", f"not written: {exc}"
    if setup is None:
        return "skip", "nothing to write"
    written = [item for item in setup if not item.startswith(_SKIPPED)]
    skipped = [item[len(_SKIPPED):] for item in setup if item.startswith(_SKIPPED)]
    detail = ", ".join(written) if written else "already up to date"
    if skipped:
        return "error", detail + "; not written: " + "; ".join(skipped)
    return "complete", detail


def _problem(extension_id: str, why: str) -> str:
    return (
        f"[yellow]⚠[/yellow]  Could not bring up to date what {escape(extension_id)} keeps in this project: "
        f"{escape(why)}. Its own commands do it the next time a spec is reviewed or folded."
    )
