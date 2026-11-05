"""`specify extension update` looks in the catalog of this fork, the one that lists what the fork ships."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from specify_cli import _locate_bundled_extension, app
from specify_cli.command_init import DEFAULT_EXTENSIONS
from specify_cli.extensions import ExtensionCatalog, ExtensionManager, ExtensionManifest

REPOSITORY = Path(__file__).resolve().parents[3]
PUBLISHED = "https://raw.githubusercontent.com/lema017/speckit-vs/main/extensions/catalog.json"
ORIGINAL = "https://raw.githubusercontent.com/github/spec-kit/main/extensions/catalog.json"


def this_catalog() -> dict:
    return json.loads((REPOSITORY / "extensions" / "catalog.json").read_text(encoding="utf-8"))


def answer_like_the_network(self, entry, force_refresh=False):
    """This repository's catalog at its URL, and a catalog without this fork's extensions anywhere else."""
    if entry.url == PUBLISHED:
        return this_catalog()
    return {"schema_version": "1.0", "extensions": {}}


def test_the_default_catalog_is_the_one_in_this_repository():
    assert ExtensionCatalog.DEFAULT_CATALOG_URL == PUBLISHED
    assert this_catalog()["catalog_url"] == PUBLISHED


@pytest.mark.parametrize("extension", DEFAULT_EXTENSIONS)
def test_the_default_catalog_lists_what_a_new_project_gets(extension):
    assert extension in this_catalog()["extensions"]


@pytest.fixture
def old_install(tmp_path):
    """A project with the extension this fork installs, at a version older than the one it ships."""
    project = tmp_path / "project"
    (project / ".specify").mkdir(parents=True)
    (project / ".claude" / "skills").mkdir(parents=True)
    manager = ExtensionManager(project)
    source = _locate_bundled_extension("capabilities")
    manager.install_from_directory(source, "1.0.0")
    manager.registry.update("capabilities", {"version": "0.0.1"})
    return project, ExtensionManifest(source / "extension.yml").version


def update(project):
    with patch.object(Path, "cwd", return_value=project), patch.object(ExtensionCatalog, "_fetch_single_catalog", answer_like_the_network):
        return CliRunner().invoke(app, ["extension", "update", "capabilities"], input="y\n")


def test_update_finds_and_applies_what_the_fork_ships(old_install):
    project, shipped = old_install
    result = update(project)
    flat = " ".join(result.output.split())
    assert result.exit_code == 0, result.output
    assert "Not found in catalog" not in flat
    assert "Updated to v%s" % shipped in flat
    assert ExtensionManager(project).registry.get("capabilities")["version"] == shipped


def test_a_catalog_without_the_extension_changes_nothing(old_install):
    project, _ = old_install
    with patch.object(ExtensionCatalog, "DEFAULT_CATALOG_URL", ORIGINAL):
        result = update(project)
    assert "Not found in catalog" in " ".join(result.output.split())
    assert ExtensionManager(project).registry.get("capabilities")["version"] == "0.0.1"
