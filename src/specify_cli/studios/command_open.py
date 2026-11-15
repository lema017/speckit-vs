"""CLI adapter for ``specify studio open``."""

from __future__ import annotations

import typer

from .._console import console
from . import studio_app
from ._script import fail, kit_path, load_product, load_script, project_root


@studio_app.command("open")
def studio_open(
    directions: bool = typer.Option(False, "--directions", help="Open the looks to choose from instead of the mockup."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Build the mockup and print its link, without opening it."),
    stop: bool = typer.Option(False, "--stop", help="Stop the server of the mockup instead of opening it."),
) -> None:
    """Build the mockup of the product and open it in your browser.

    The mockup is served from this computer, so a comment made in it is kept in the
    project. Over SSH, in CI or without a display it only prints the link of the file.
    """
    root = project_root()
    script = load_script()
    if stop:
        try:
            stopped = script.stop_server(root)
        except OSError as exc:
            fail(str(exc))
        console.print("The server of the mockup stopped." if stopped else "No server of the mockup was running.", markup=False)
        return
    product = load_product(script, root)
    try:
        link, opened, served = script.show(product, kit_path(), "directions" if directions else None, not no_browser)
    except (script.StudioError, OSError) as exc:
        fail(str(exc))
    if not opened and not no_browser:
        console.print("Could not open a browser here. The mockup is at:", markup=False)
    console.print(link, markup=False, soft_wrap=True)
    if served:
        console.print("A comment made in the mockup is kept in the project. `specify studio open --stop` stops its server.", markup=False)
