"""Private helpers shared by the ``specify progress`` commands."""

from __future__ import annotations

import importlib.util
import re
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import NoReturn

import typer
from rich.markup import escape

from .._assets import _locate_core_pack, _repo_root
from .._console import err_console

# Terminal control characters and the Unicode marks that reorder text. A task's text comes from a
# file a model wrote, and must not be able to move the cursor or disguise what it says.
_UNSAFE_FOR_TERMINAL = re.compile(r"[\x00-\x1f\x7f-\x9f\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def engine_path() -> Path:
    """Return where the engine lives: the wheel's core pack, or the source checkout."""
    core = _locate_core_pack()
    base = core if core is not None else _repo_root()
    return base / "scripts" / "progress" / "engine.py"


@lru_cache(maxsize=1)
def load_engine() -> ModuleType:
    """Load the engine by path, the same file a project runs on its own."""
    path = engine_path()
    spec = importlib.util.spec_from_file_location("specify_cli_progress_engine", path)
    if spec is None or spec.loader is None or not path.is_file():
        fail("The progress engine is missing from this installation: %s" % path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # Keep __pycache__ out of the folder that gets packaged.
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def fail(message: str) -> NoReturn:
    """Report an expected failure on stderr and exit with 1."""
    err_console.print("[red]Error:[/red] %s" % escape(terminal_text(message)), soft_wrap=True)
    raise typer.Exit(1)


def terminal_text(value: object) -> str:
    """Make text from a project file safe to print, whatever the output can encode."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    clean = _UNSAFE_FOR_TERMINAL.sub(" ", str(value))
    return clean.encode(encoding, "replace").decode(encoding)


def project_root() -> Path:
    """Return the project these commands act on, honoring ``SPECIFY_INIT_DIR``."""
    from .. import _require_specify_project  # lazy: avoids a circular import

    return _require_specify_project()


def named_feature(engine: ModuleType, root: Path, reference: str | None) -> Path | None:
    """Resolve ``--feature``. Without one, return None."""
    if reference is None:
        return None
    try:
        return engine.find_feature(root, reference)
    except engine.ProgressError as exc:
        fail(str(exc))
