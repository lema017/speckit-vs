"""Command group for ``specify progress``: the visual progress of each spec.

The work happens in ``scripts/progress/engine.py``, which projects also get a copy of and run
with whatever Python they have. These commands are thin adapters over that engine.
"""

import typer

progress_app = typer.Typer(
    name="progress",
    help="Show how far each spec has come: a page per spec, or a summary in the terminal.",
    add_completion=False,
)


def register(app: typer.Typer) -> None:
    """Attach ``specify progress`` and its commands to the root CLI."""
    from . import (  # noqa: F401
        command_browser,
        command_engine,
        command_open,
        command_render,
        command_status,
    )

    app.add_typer(progress_app, name="progress")
