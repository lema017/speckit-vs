"""CLI adapter for ``specify studio check``."""

from __future__ import annotations

import json

import typer
from rich.text import Text

from .._console import console
from . import studio_app
from ._script import load_product, load_script, project_root, terminal_text


def _line(text: object) -> None:
    """Print file-derived text literally: no markup, no control characters."""
    console.print(Text(terminal_text(text)), soft_wrap=True)


@studio_app.command("check")
def studio_check(
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Check that the design and the pages of the mockup agree. Read-only.

    Exits with 1 when something has to be fixed.
    """
    root = project_root()
    script = load_script()
    hard, notes, _ = script.problems(load_product(script, root))
    if as_json:
        typer.echo(json.dumps({"status": "invalid" if hard else "ok", "hard": hard, "notes": notes}, indent=2, ensure_ascii=False))
    else:
        if hard:
            _line("To fix (%d)" % len(hard))
            for problem in hard:
                _line("  " + problem)
        if notes:
            _line("Worth knowing (%d)" % len(notes))
            for note in notes:
                _line("  " + note)
        if not hard and not notes:
            _line("The design and the mockup agree.")
    if hard:
        raise typer.Exit(1)
