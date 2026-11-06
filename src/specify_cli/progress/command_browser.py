"""CLI adapter for ``specify progress browser``."""

from __future__ import annotations

import typer

from .._console import console
from . import progress_app
from ._engine import fail, load_engine, project_root


@progress_app.command("browser")
def progress_browser(
    state: str = typer.Argument(..., help="on or off."),
) -> None:
    """Choose whether a spec's page opens by itself the first time it is drawn.

    The pages are still drawn either way. This applies to this project, on this
    machine. SPECKIT_PROGRESS_NO_BROWSER=1 turns it off for one environment.
    """
    if state not in ("on", "off"):
        fail("Use on or off.")
    root = project_root()
    engine = load_engine()
    try:
        engine.set_browser(root, state == "on")
    except (engine.ProgressError, OSError) as exc:
        fail(str(exc))
    console.print(
        "Progress pages open by themselves." if state == "on" else "Progress pages stay closed until you open them.",
        markup=False,
    )
