"""Command tests for ``specify progress engine``, the wrappers' way in when there is no Python."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from specify_cli import app
from tests.conftest import strip_ansi

runner = CliRunner()


def test_it_runs_the_engine_with_the_arguments_a_wrapper_passes(project):
    directory = project.feature()
    project.set_current(directory)
    result = runner.invoke(
        app,
        ["progress", "engine", "--root", str(project.root), "--harness", "claude", "step", "plan", "done", "--note", "All good"],
    )
    assert result.exit_code == 0, result.output
    assert "Tasks: 1 of 4 done" in strip_ansi(result.output)
    event = json.loads((directory / "progress.jsonl").read_text(encoding="utf-8"))
    assert event["note"] == "All good"
    assert event["actor"]["harness"] == "claude"


def test_a_wrong_command_keeps_the_engines_exit_code(project):
    result = runner.invoke(app, ["progress", "engine", "--root", str(project.root), "nonsense"])
    assert result.exit_code == 2


def test_a_failing_command_keeps_the_engines_exit_code(tmp_path):
    result = runner.invoke(app, ["progress", "engine", "--root", str(tmp_path), "render"])
    assert result.exit_code == 1


def test_it_stays_out_of_the_help(project):
    result = runner.invoke(app, ["progress", "--help"])
    assert result.exit_code == 0
    text = strip_ansi(result.output)
    assert "engine" not in text
    assert "browser" in text and "render" in text
