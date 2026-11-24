"""CLI adapter for ``specify progress slices``: every slice of every map, and how far each one is."""

from __future__ import annotations

import json

import typer
from rich.table import Table
from rich.text import Text

from .._console import console
from . import progress_app
from ._engine import fail, load_engine, project_root, terminal_text

_BAR_WIDTH = 24


def _line(*parts: object) -> None:
    """Print file-derived text literally: no markup, no control characters."""
    console.print(Text(terminal_text("".join(str(part) for part in parts))), soft_wrap=True)


def _print_map(engine, group: dict) -> None:
    done, total = group["delivered"], group["total"]
    filled = round(_BAR_WIDTH * done / total) if total else 0
    _line(group["name"], "  %d of %d slices delivered  [%s]" % (done, total, "#" * filled + "-" * (_BAR_WIDTH - filled)))
    if group["request"]:
        _line(group["request"])
    table = Table(show_edge=False, box=None, pad_edge=False)
    table.add_column("Slice", no_wrap=True)
    table.add_column("State", no_wrap=True)
    table.add_column("Spec", overflow="fold")
    table.add_column("Title", overflow="fold")
    for view in group["slices"]:
        state = "next" if view["id"] == group["next"] else engine.SLICE_STATE_WORDS[view["state"]]
        where = view["spec"] or ""
        if view["state"] == "pending":
            where = "waits for " + ", ".join(view["waiting_for"]) if view["waiting_for"] else "can start now"
        table.add_row(*(Text(terminal_text(value)) for value in (view["id"], state, where, view["title"])))
    console.print()
    console.print(table)
    console.print()
    tally = engine.slice_tally(group)
    _line(tally[:1].upper() + tally[1:] + "." if tally else "No slices.")
    if group["next"]:
        _line("Next: /speckit-specify ", group["next"])
    elif total and done == total:
        _line("Every slice is delivered.")
    else:
        _line("No slice can start now: each one without a spec waits for another.")


@progress_app.command("slices")
def progress_slices(
    map_name: str | None = typer.Option(None, "--map", help="Show this map only: its file name under specs/_slices/, without .md."),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """List every slice of the project's slice maps and how far each one is. Read-only.

    A slice is delivered, being built (its spec has tasks), has its spec written, or has no spec
    yet. The state is read from the specs each time, so slices added to a map show up at once.
    """
    root = project_root()
    engine = load_engine()
    try:
        groups = engine.project_slices(root)
    except (engine.ProgressError, OSError) as exc:
        fail(str(exc))
    if map_name is not None:
        groups = [group for group in groups if group["name"] == map_name]
        if not groups:
            fail("There is no slice map named %s under specs/_slices/." % map_name)
    if as_json:
        typer.echo(json.dumps(groups, indent=2))
        return
    if not groups:
        console.print(
            "No slice maps yet. /speckit-capabilities-slice or /speckit-studio-slice writes one under specs/_slices/.",
            markup=False,
        )
        return
    for index, group in enumerate(groups):
        if index:
            console.print()
        _print_map(engine, group)
