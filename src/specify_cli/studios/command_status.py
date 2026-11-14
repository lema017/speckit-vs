"""CLI adapter for ``specify studio status``."""

from __future__ import annotations

import json

import typer
from rich.table import Table
from rich.text import Text

from .._console import console
from ..progress._engine import load_engine
from . import studio_app
from ._script import fail, load_script, project_root, terminal_text

_STATES = {"done": "done", "active": "in progress", "attention": "needs attention", "pending": "not started"}
_AREA_STATES = {"not-started": "not started", "in-design": "in design", "drawn": "drawn"}


def _line(*parts: object) -> None:
    """Print file-derived text literally: no markup, no control characters."""
    console.print(Text(terminal_text("".join(str(part) for part in parts))), soft_wrap=True)


@studio_app.command("status")
def studio_status(
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show how far the design is and which command comes next. Read-only."""
    root = project_root()
    script = load_script()
    try:
        status = script.status(script.Product(root))
    except script.StudioError as exc:
        fail(str(exc))
    if as_json:
        typer.echo(json.dumps(status, indent=2, ensure_ascii=False))
        return
    command = load_engine().command_text
    step = status["next"]
    if status["status"] == "none":
        _line("No design yet. It starts with ", command(root, step["command"]), ".")
        return
    _line("Design of ", status["product"])
    table = Table(show_edge=False, box=None, pad_edge=False)
    table.add_column("Step", no_wrap=True)
    table.add_column("State", no_wrap=True)
    table.add_column("", overflow="fold")
    for row in status["steps"]:
        table.add_row(row["name"].capitalize(), _STATES.get(row["state"], row["state"]), Text(terminal_text(row["fact"])))
    console.print(table)
    if status["areas"]:
        console.print()
        areas = Table(show_edge=False, box=None, pad_edge=False)
        areas.add_column("Area", overflow="fold")
        areas.add_column("State", no_wrap=True)
        areas.add_column("Screens", justify="right", no_wrap=True)
        areas.add_column("Drawn", justify="right", no_wrap=True)
        for area in status["areas"]:
            areas.add_row(Text(terminal_text(area["title"])), _AREA_STATES.get(area["state"], area["state"]), str(area["screens"]), str(area["pages"]))
        console.print(areas)
    console.print()
    _line("Next: ", command(root, step["command"], step["args"]), ". ", step["why"])
    if status["attention"]:
        console.print()
        _line("Needs your attention")
        for item in status["attention"]:
            _line("  ", item["text"])
