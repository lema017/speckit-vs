"""CLI adapter for ``specify progress open``."""

from __future__ import annotations

import webbrowser
from pathlib import Path

import typer

from .._console import console
from . import progress_app
from ._engine import fail, load_engine, named_feature, project_root


@progress_app.command("open")
def progress_open(
    feature: str | None = typer.Option(
        None,
        "--feature",
        help="Open this spec: its directory name, or a unique prefix such as 002.",
    ),
    no_browser: bool = typer.Option(False, "--no-browser", help="Draw the page and print its link, without opening it."),
) -> None:
    """Draw the progress page and open it in your browser.

    Opens the current spec, or the list of specs when none is current. Over SSH,
    in CI or without a display it only prints the link.
    """
    root = project_root()
    engine = load_engine()
    target = named_feature(engine, root, feature)
    if target is None:
        target = engine.current_feature_dir(root)
    try:
        result = engine.render_project(root, target)
    except (engine.ProgressError, OSError) as exc:
        fail(str(exc))
    page = result["pages"][0]["path"] if target is not None else result["index"]
    link = Path(page).resolve().as_uri()
    opened = False
    if not no_browser and engine.can_open_browser():
        try:
            opened = webbrowser.open(link)
        except webbrowser.Error:
            opened = False
    if not opened and not no_browser:
        console.print("Could not open a browser here. The page is at:", markup=False)
    console.print(link, markup=False, soft_wrap=True)
