"""Command group for ``specify studio``: the design of a product and its mockup.

The work happens in the script of the studio extension,
``extensions/studio/scripts/python/studio.py``, which projects get a copy of and agents run with
whatever Python they have. These commands are thin adapters over that script, for the person who
wants to see the mockup or the state of the design without asking an agent.
"""

import typer

studio_app = typer.Typer(
    name="studio",
    help="See the design of a product: open its mockup, check it, or read how far it is.",
    add_completion=False,
)


def register(app: typer.Typer) -> None:
    """Attach ``specify studio`` and its commands to the root CLI."""
    from . import (  # noqa: F401
        command_check,
        command_open,
        command_status,
    )

    app.add_typer(studio_app, name="studio")
