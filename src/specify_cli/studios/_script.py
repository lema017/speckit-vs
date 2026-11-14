"""Private helpers shared by the ``specify studio`` commands."""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from .._assets import _locate_bundled_extension
from ..progress._engine import fail, project_root, terminal_text

__all__ = ["fail", "kit_path", "load_product", "load_script", "project_root", "script_path", "terminal_text"]


def script_path() -> Path:
    """Return where the studio script lives: the wheel's core pack, or the source checkout."""
    extension = _locate_bundled_extension("studio")
    if extension is None:
        fail("The studio extension is missing from this installation.")
    return extension / "scripts" / "python" / "studio.py"


def kit_path() -> Path:
    """Return the folder of the kit the mockup is built with."""
    return script_path().parents[2] / "mockup" / "_studio"


@lru_cache(maxsize=1)
def load_script() -> ModuleType:
    """Load the studio script by path, the same file a project runs on its own."""
    path = script_path()
    spec = importlib.util.spec_from_file_location("specify_cli_studio_script", path)
    if spec is None or spec.loader is None or not path.is_file():
        fail("The studio script is missing from this installation: %s" % path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # Keep __pycache__ out of the folder that gets packaged.
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def load_product(script: ModuleType, root: Path):
    """Read the design of the project. A project without one, or with one that cannot be read, stops here."""
    try:
        product = script.Product(root)
    except script.StudioError as exc:
        fail(str(exc))
    if not product.exists:
        fail("This project has no design yet. It starts with the speckit.studio.define command of your agent.")
    return product
