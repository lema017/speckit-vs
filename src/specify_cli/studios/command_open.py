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
) -> None:
    """Build the mockup of the product and open it in your browser.

    Over SSH, in CI or without a display it only prints the link.
    """
    root = project_root()
    script = load_script()
    product = load_product(script, root)
    try:
        link, opened = script.show(product, kit_path(), "directions" if directions else None, not no_browser)
    except (script.StudioError, OSError) as exc:
        fail(str(exc))
    if not opened and not no_browser:
        console.print("Could not open a browser here. The mockup is at:", markup=False)
    console.print(link, markup=False, soft_wrap=True)
