"""The picture of the command lifecycle that every project gets in ``.specify/``.

``specify init`` and ``specify integration upgrade`` copy it like the other
shared files: byte for byte, tracked in ``speckit.manifest.json``, replaced by
a newer one while nobody has edited the copy, and kept when someone has.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from specify_cli import _install_shared_infra

REPO_ROOT = Path(__file__).parents[1]
SOURCE = REPO_ROOT / "templates" / "guide" / "lifecycle.png"
IMAGE = ".specify/lifecycle.png"


def _install(project: Path, **kwargs) -> None:
    (project / ".specify").mkdir(parents=True, exist_ok=True)
    _install_shared_infra(project, "sh", **kwargs)


def _manifest_path(project: Path) -> Path:
    return project / ".specify" / "integrations" / "speckit.manifest.json"


def _manifest(project: Path) -> dict:
    return json.loads(_manifest_path(project).read_text(encoding="utf-8"))


def _save_manifest(project: Path, manifest: dict) -> None:
    _manifest_path(project).write_text(json.dumps(manifest), encoding="utf-8")


def test_a_new_project_gets_the_image_byte_for_byte(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _install(project)

    image = project / IMAGE
    assert image.read_bytes() == SOURCE.read_bytes()
    assert _manifest(project)["files"][IMAGE] == hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def test_upgrading_a_project_that_predates_the_image_adds_it(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _install(project)
    (project / IMAGE).unlink()
    manifest = _manifest(project)
    del manifest["files"][IMAGE]
    _save_manifest(project, manifest)

    _install(project, refresh_managed=True)

    assert (project / IMAGE).read_bytes() == SOURCE.read_bytes()
    assert IMAGE in _manifest(project)["files"]


def test_an_untouched_older_image_is_replaced_on_upgrade(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _install(project)
    older = b"\x89PNG\r\n\x1a\nan older picture"
    (project / IMAGE).write_bytes(older)
    manifest = _manifest(project)
    manifest["files"][IMAGE] = hashlib.sha256(older).hexdigest()
    _save_manifest(project, manifest)

    _install(project, refresh_managed=True)

    assert (project / IMAGE).read_bytes() == SOURCE.read_bytes()


def test_an_edited_image_is_kept(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _install(project)
    mine = b"\x89PNG\r\n\x1a\nmy own picture"
    (project / IMAGE).write_bytes(mine)

    _install(project)
    assert (project / IMAGE).read_bytes() == mine

    _install(project, refresh_managed=True)
    assert (project / IMAGE).read_bytes() == mine


def test_force_restores_the_image(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    _install(project)
    (project / IMAGE).write_bytes(b"\x89PNG\r\n\x1a\nmy own picture")

    _install(project, force=True)

    assert (project / IMAGE).read_bytes() == SOURCE.read_bytes()


def test_the_wheel_ships_the_image() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)
    force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]

    assert force_include.get("templates/guide/lifecycle.png") == (
        "specify_cli/core_pack/templates/guide/lifecycle.png"
    )
