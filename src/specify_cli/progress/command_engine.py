"""CLI adapter for ``specify progress engine``: the engine's own command line, for the wrappers.

A project's ``progress`` wrappers run the engine with a system Python. Where there is none, they
fall back to this command, which runs the same engine with the Python ``specify`` came with.
"""

from __future__ import annotations

import typer

from . import progress_app
from ._engine import load_engine


@progress_app.command(
    "engine",
    hidden=True,
    add_help_option=False,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def progress_engine(ctx: typer.Context) -> None:
    """Run the progress engine with the given arguments."""
    try:
        code = load_engine().main(list(ctx.args))
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    raise typer.Exit(code or 0)
