"""CLI adapter for ``specify progress watch``."""

from __future__ import annotations

import time
from datetime import datetime

import typer

from .._console import console
from . import progress_app
from ._engine import fail, load_engine, project_root, terminal_text


@progress_app.command("watch")
def progress_watch(
    feature: str | None = typer.Option(None, "--feature", help="Spec directory name, or a unique prefix of one. By default, the current spec."),
    interval: float = typer.Option(1.0, "--interval", min=0.1, help="Seconds between looks."),
    rounds: int | None = typer.Option(None, "--rounds", hidden=True, help="Stop after this many looks. For tests."),
) -> None:
    """Keep a spec's page current from another terminal, whatever the agent does.

    It redraws only when a file the page shows has changed. Stop it with Ctrl+C.
    """
    root = project_root()
    engine = load_engine()
    last = None
    done = 0
    console.print("Watching. Press Ctrl+C to stop.", markup=False)
    try:
        while rounds is None or done < rounds:
            try:
                last, line = engine.watch_round(root, feature, last)
            except OSError as exc:
                line = "Could not draw the page: %s" % exc
            except engine.ProgressError as exc:
                fail(str(exc))
            if line:
                console.print("%s  %s" % (datetime.now().strftime("%H:%M:%S"), terminal_text(line)), markup=False, highlight=False)
            done += 1
            if rounds is None or done < rounds:
                time.sleep(interval)
    except KeyboardInterrupt:
        console.print("Stopped.", markup=False)
