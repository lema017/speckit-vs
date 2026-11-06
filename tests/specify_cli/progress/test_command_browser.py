"""Command tests for ``specify progress browser``."""

from __future__ import annotations

from typer.testing import CliRunner

from specify_cli import app
from tests.conftest import strip_ansi

from .conftest import symlink

runner = CliRunner()


def test_it_turns_the_automatic_opening_off_and_on(in_project, engine):
    result = runner.invoke(app, ["progress", "browser", "off"])
    assert result.exit_code == 0, result.output
    assert "stay closed" in strip_ansi(result.output)
    assert engine.browser_is_off(in_project.root, {}) is True
    result = runner.invoke(app, ["progress", "browser", "on"])
    assert result.exit_code == 0, result.output
    assert "open by themselves" in strip_ansi(result.output)
    assert engine.browser_is_off(in_project.root, {}) is False


def test_anything_else_is_refused(in_project, engine):
    result = runner.invoke(app, ["progress", "browser", "maybe"])
    assert result.exit_code == 1
    assert "Use on or off" in strip_ansi(result.output)
    assert not (in_project.root / ".specify" / "progress").exists()


def test_it_fails_outside_a_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["progress", "browser", "off"]).exit_code == 1
    assert list(tmp_path.iterdir()) == []


def test_a_write_problem_is_a_clean_error(in_project, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    symlink(in_project.root / ".specify" / "progress", outside)
    result = runner.invoke(app, ["progress", "browser", "off"])
    assert result.exit_code == 1
    assert "symbolic link" in strip_ansi(result.output)
    assert list(outside.iterdir()) == []


def test_a_project_elsewhere_can_be_targeted(project, engine, tmp_path, monkeypatch):
    launch = tmp_path / "elsewhere"
    launch.mkdir()
    monkeypatch.chdir(launch)
    monkeypatch.setenv("SPECIFY_INIT_DIR", str(project.root))
    assert runner.invoke(app, ["progress", "browser", "off"]).exit_code == 0
    assert engine.browser_is_off(project.root, {}) is True
    assert list(launch.iterdir()) == []
