"""CLI adapter for ``specify progress doctor``."""

from __future__ import annotations

import typer

from .._console import console
from . import progress_app
from ._doctor import FAIL, OK, WARN, run_checks
from ._engine import fail, load_engine, project_root, terminal_text

MARKS = {OK: "ok  ", WARN: "warn", FAIL: "FAIL"}


@progress_app.command("doctor")
def progress_doctor() -> None:
    """Check that the progress view works here: files, Python, the log, each harness.

    Exits with 1 when something keeps the page from being drawn.
    """
    root = project_root()
    engine = load_engine()
    try:
        checks = run_checks(root)
    except (engine.ProgressError, OSError) as exc:
        fail(str(exc))
    for check in checks:
        console.print(
            "%s  %s: %s" % (MARKS[check.level], terminal_text(check.subject), terminal_text(check.detail)),
            markup=False,
            highlight=False,
            soft_wrap=True,
        )
    if any(check.level == FAIL for check in checks):
        raise typer.Exit(1)
