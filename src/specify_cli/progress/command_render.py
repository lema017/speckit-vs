"""CLI adapter for ``specify progress render``."""

from __future__ import annotations

import json

import typer

from .._console import console
from . import progress_app
from ._engine import fail, load_engine, named_feature, project_root


@progress_app.command("render")
def progress_render(
    feature: str | None = typer.Option(
        None,
        "--feature",
        help="Draw only this spec: its directory name, or a unique prefix such as 002.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print what was drawn as JSON."),
) -> None:
    """Draw the progress pages into .specify/progress/.

    Reads tasks.md, the spec's other files and its progress.jsonl, and changes
    nothing outside .specify/progress/. Without --feature it draws every spec.
    """
    root = project_root()
    engine = load_engine()
    target = named_feature(engine, root, feature)
    try:
        result = engine.render_project(root, target)
    except (engine.ProgressError, OSError) as exc:
        fail(str(exc))
    if as_json:
        typer.echo(json.dumps(result, indent=2))
        return
    count = len(result["pages"])
    console.print("Drew %d %s." % (count, "page" if count == 1 else "pages"), markup=False)
    console.print(result["index"], markup=False, soft_wrap=True)
