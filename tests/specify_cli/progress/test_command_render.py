"""Command tests for ``specify progress render``."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from specify_cli import app
from tests.conftest import strip_ansi

from .conftest import symlink

runner = CliRunner()


def test_it_draws_every_spec(in_project):
    in_project.feature("001-login")
    in_project.feature("002-logout")
    result = runner.invoke(app, ["progress", "render"])
    assert result.exit_code == 0, result.output
    assert "Drew 2 pages." in strip_ansi(result.output)
    assert (in_project.root / ".specify" / "progress" / "index.html").is_file()
    assert (in_project.root / ".specify" / "progress" / "002-logout.html").is_file()


def test_it_can_draw_one_spec_by_prefix(in_project):
    in_project.feature("001-login")
    in_project.feature("002-logout")
    result = runner.invoke(app, ["progress", "render", "--feature", "002"])
    assert result.exit_code == 0, result.output
    assert "Drew 1 page." in strip_ansi(result.output)
    assert (in_project.root / ".specify" / "progress" / "002-logout.html").is_file()
    assert not (in_project.root / ".specify" / "progress" / "001-login.html").exists()


def test_it_prints_json_for_machines(in_project):
    in_project.feature("001-login")
    result = runner.invoke(app, ["progress", "render", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["pages"][0]["id"] == "001-login"
    assert payload["pages"][0]["totals"]["total"] == 4


def test_an_unknown_spec_fails_and_draws_nothing(in_project):
    in_project.feature("001-login")
    result = runner.invoke(app, ["progress", "render", "--feature", "zzz"])
    assert result.exit_code == 1
    assert "No spec named" in strip_ansi(result.output)
    assert not (in_project.root / ".specify" / "progress").exists()


def test_it_fails_outside_a_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["progress", "render"])
    assert result.exit_code == 1
    assert list(tmp_path.iterdir()) == []


def test_a_project_elsewhere_can_be_targeted(project, tmp_path, monkeypatch):
    project.feature("001-login")
    launch = tmp_path / "elsewhere"
    launch.mkdir()
    monkeypatch.chdir(launch)
    monkeypatch.setenv("SPECIFY_INIT_DIR", str(project.root))
    result = runner.invoke(app, ["progress", "render"])
    assert result.exit_code == 0, result.output
    assert (project.root / ".specify" / "progress" / "001-login.html").is_file()
    assert list(launch.iterdir()) == []


def test_a_write_problem_is_a_clean_error(in_project, tmp_path):
    in_project.feature("001-login")
    outside = tmp_path / "outside"
    outside.mkdir()
    symlink((in_project.root / ".specify" / "progress"), outside)
    result = runner.invoke(app, ["progress", "render"])
    assert result.exit_code == 1
    assert "symbolic link" in strip_ansi(result.output)
    assert result.exception is None or isinstance(result.exception, SystemExit)
