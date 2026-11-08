"""CLI adapter for ``specify upgrade``, registered on the root application by ``register``.

It chains commands that already exist: ``specify self upgrade``, then, for the
project in the current folder, ``specify integration upgrade`` for each
integration and ``specify extension add --force`` for each extension that ships
with specify. Each step is its own ``specify`` process, because the project steps
must run the code the first step installed, and a running Python process cannot
load a newer copy of itself.

Extensions are added again rather than updated: ``specify extension update``
compares the installed version with the catalog on the repository's main branch,
so it skips an extension whose files or hooks changed under the same version, and
an extension the catalog has moved past this release. Adding it again installs
the copy the installed specify ships and keeps its configuration files.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import typer

from ._console import console


def _specify_executable() -> str:
    """The ``specify`` this process was started as, or the one on PATH."""
    from ._version import _looks_like_specify_entrypoint, _resolved_argv0_path

    argv0 = _resolved_argv0_path()
    if argv0.is_file() and os.access(argv0, os.X_OK) and _looks_like_specify_entrypoint(argv0):
        return str(argv0)
    return shutil.which("specify") or "specify"


def _run_step(argv: list[str]) -> int:
    """Run one step with the person's terminal, and return its exit code."""
    try:
        return subprocess.run(argv, check=False).returncode
    except OSError as exc:
        console.print(f"Could not run {argv[0]}: {exc}", markup=False, soft_wrap=True)
        return 127


def _integration_keys(project: Path) -> list[str]:
    """The project's integrations, its default one first. Empty when no record says which."""
    from .integration_state import (
        default_integration_key,
        installed_integration_keys,
        try_read_integration_json,
    )

    state, _ = try_read_integration_json(project)
    if state is None:
        return []
    keys = installed_integration_keys(state)
    default = default_integration_key(state)
    if default in keys:
        keys.remove(default)
        keys.insert(0, default)
    return keys


_DEFAULT_PRIORITY = 10


def _extensions(project: Path) -> tuple[list[tuple[str, int, bool]], list[str]]:
    """The project's extensions that ship with specify, each with its priority and
    whether it is on, and the names of the others."""
    from ._assets import _locate_bundled_extension
    from .extensions import ExtensionRegistry

    registry = ExtensionRegistry(project / ".specify" / "extensions")
    bundled, others = [], []
    for name in sorted(registry.keys()):
        if _locate_bundled_extension(name) is None:
            others.append(name)
            continue
        entry = registry.get(name)
        entry = entry if isinstance(entry, dict) else {}
        priority = entry.get("priority", _DEFAULT_PRIORITY)
        if isinstance(priority, bool) or not isinstance(priority, int) or priority < 1:
            priority = _DEFAULT_PRIORITY
        bundled.append((name, priority, entry.get("enabled", True) is not False))
    return bundled, others


def upgrade(
    tag: str | None = typer.Option(
        None,
        "--tag",
        help="Update to this release (vX.Y.Z) instead of the latest one.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what it would do, and change nothing.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite the integration files you edited with the new ones.",
    ),
) -> None:
    """Update specify to the latest release, then update this project to it.

    Run it from the project's folder. It runs `specify self upgrade`, then, with
    the specify that is installed, `specify integration upgrade` for each of the
    project's integrations, and adds again each extension that ships with
    specify, keeping its configuration, its priority and whether it is on. It
    stops at the first step that does not finish. Integration files you edited
    are kept, and the step that finds one stops and says which, unless you pass
    --force. Extensions from a catalog are left alone.
    """
    project = Path.cwd()
    if not (project / ".specify").is_dir():
        console.print(
            "No Spec Kit project here: there is no .specify folder. "
            "Run specify upgrade from the folder of a project that uses Spec Kit.",
            soft_wrap=True,
        )
        raise typer.Exit(1)

    specify = _specify_executable()
    keys = _integration_keys(project)
    bundled, others = _extensions(project)

    self_step = [specify, "self", "upgrade"]
    if tag is not None:
        self_step += ["--tag", tag]
    if keys:
        project_steps = [[specify, "integration", "upgrade", key] for key in keys]
    else:
        project_steps = [[specify, "integration", "upgrade"]]
    if force:
        project_steps = [step + ["--force"] for step in project_steps]
    extension_steps = []
    for name, priority, enabled in bundled:
        extension_steps.append([specify, "extension", "add", name, "--force", "--priority", str(priority)])
        if not enabled:
            # Adding an extension again turns it on.
            extension_steps.append([specify, "extension", "disable", name])

    if dry_run:
        code = _run_step(self_step + ["--dry-run"])
        if code != 0:
            raise typer.Exit(code)
        lines = ["  specify " + " ".join(step[1:]) for step in project_steps + extension_steps]
        console.print(
            "Then, with the specify that is installed, it would run:\n" + "\n".join(lines),
            markup=False,
            soft_wrap=True,
        )
        _mention_others(others)
        raise typer.Exit(0)

    code = _run_step(self_step)
    if code != 0:
        console.print(
            "Stopped: specify self upgrade did not finish. The project was not changed.",
            soft_wrap=True,
        )
        raise typer.Exit(code)

    for step in project_steps + extension_steps:
        code = _run_step(step)
        if code != 0:
            console.print(
                f"Stopped: specify {' '.join(step[1:])} did not finish. Nothing after it ran.",
                markup=False,
                soft_wrap=True,
            )
            raise typer.Exit(code)

    _mention_others(others)
    console.print("This project is up to date with the specify that is installed.", soft_wrap=True)


def _mention_others(others: list[str]) -> None:
    for name in others:
        console.print(
            f"Not updated: {name} does not ship with specify. To update it: specify extension update {name}",
            markup=False,
            soft_wrap=True,
        )


def register(app: typer.Typer) -> None:
    """Register ``specify upgrade`` on the root application."""
    app.command()(upgrade)
