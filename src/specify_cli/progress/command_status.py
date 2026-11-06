"""CLI adapter for ``specify progress status``."""

from __future__ import annotations

import json

import typer
from rich.table import Table
from rich.text import Text

from .._console import console
from . import progress_app
from ._engine import fail, load_engine, named_feature, project_root, terminal_text

_BAR_WIDTH = 24


def _line(*parts: object) -> None:
    """Print file-derived text literally: no markup, no control characters."""
    console.print(Text(terminal_text("".join(str(part) for part in parts))), soft_wrap=True)


def _bar(done: int, total: int) -> str:
    filled = round(_BAR_WIDTH * done / total) if total else 0
    return "#" * filled + "-" * (_BAR_WIDTH - filled)


def _print_one(row: dict) -> None:
    totals = row["totals"]
    _line(row["title"], "  (", row["id"], ", current)" if row["current"] else ")")
    if totals["total"]:
        percent = round(100 * totals["done"] / totals["total"])
        _line("Tasks  %d of %d  [%s] %d%%" % (totals["done"], totals["total"], _bar(totals["done"], totals["total"]), percent))
        _line("       ", load_engine().breakdown(totals))
    else:
        _line("Tasks  none yet")
    _line("Steps  ", ", ".join("%s: %s" % (step["label"], step["fact"]) for step in row["steps"]))
    if row["phases"]:
        console.print()
        table = Table(show_edge=False, box=None, pad_edge=False)
        table.add_column("Phase", overflow="fold")
        table.add_column("Done", justify="right", no_wrap=True)
        for phase in row["phases"]:
            table.add_row(Text(terminal_text(phase["name"])), "%d of %d" % (phase["done"], phase["total"]))
        console.print(table)
    if row["active"]:
        console.print()
        _line("Working now")
        for task in row["active"]:
            who = " (%s)" % task["who"] if task["who"] else ""
            flag = ", possibly abandoned" if task["id"] in row["abandoned"] else ""
            _line("  ", task["id"], " ", task["status"].replace("_", " "), flag, who, ": ", task["text"])
    if row["agents"]:
        console.print()
        _line("Who did what")
        for agent in row["agents"]:
            active = " (on %s)" % ", ".join(agent["active"]) if agent["active"] else ""
            _line("  ", agent["label"], ": %d done" % agent["done"], active)
    if row["attention"]:
        console.print()
        _line("Needs your attention")
        for item in row["attention"]:
            _line("  ", item["task"] + " " if item["task"] else "", item["text"])


def _print_many(rows: list) -> None:
    table = Table(show_edge=False, box=None, pad_edge=False)
    table.add_column("Spec", overflow="fold")
    table.add_column("Done", justify="right", no_wrap=True)
    table.add_column("Progress", no_wrap=True)
    table.add_column("Left", overflow="fold")
    for row in rows:
        totals = row["totals"]
        name = row["id"] + (" (current)" if row["current"] else "")
        table.add_row(
            Text(terminal_text(name)),
            "%d of %d" % (totals["done"], totals["total"]),
            _bar(totals["done"], totals["total"]),
            Text(load_engine().breakdown(totals) if totals["total"] else "no tasks yet"),
        )
    console.print(table)


@progress_app.command("status")
def progress_status(
    feature: str | None = typer.Option(
        None,
        "--feature",
        help="Show this spec: its directory name, or a unique prefix such as 002.",
    ),
    all_specs: bool = typer.Option(False, "--all", help="Summarize every spec instead of the current one."),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Show how far a spec has come, in the terminal. Read-only.

    Without options it shows the current spec, or every spec when none is current.
    """
    if feature is not None and all_specs:
        fail("Use either --feature or --all, not both.")
    root = project_root()
    engine = load_engine()
    target = named_feature(engine, root, feature)
    if target is None and not all_specs:
        target = engine.current_feature_dir(root)
    try:
        rows = engine.status_data(root, target)
    except (engine.ProgressError, OSError) as exc:
        fail(str(exc))
    if as_json:
        typer.echo(json.dumps(rows, indent=2))
    elif not rows:
        console.print("No specs yet.", markup=False)
    elif target is not None:
        _print_one(rows[0])
    else:
        _print_many(rows)
