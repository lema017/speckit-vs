"""Command tests for ``specify progress watch``."""

from __future__ import annotations

import time

import pytest
from typer.testing import CliRunner

from specify_cli import app
from specify_cli.progress import command_watch
from tests.conftest import strip_ansi

runner = CliRunner()


def test_it_draws_once_and_then_only_when_something_changed(in_project, monkeypatch):
    directory = in_project.feature()
    in_project.set_current(directory)
    naps = []

    def nap(seconds):
        naps.append(seconds)
        if len(naps) == 2:
            (directory / "tasks.md").write_text("## P\n\n- [X] T001 Only\n", encoding="utf-8")

    monkeypatch.setattr(command_watch.time, "sleep", nap)
    result = runner.invoke(app, ["progress", "watch", "--rounds", "4", "--interval", "0.5"])
    assert result.exit_code == 0, result.output
    output = strip_ansi(result.output)
    assert "001-login: 1 of 4 tasks done" in output
    assert "001-login: 1 of 1 tasks done" in output
    assert output.count("tasks done") == 2
    assert naps == [0.5, 0.5, 0.5]


def test_it_writes_the_page(in_project):
    directory = in_project.feature()
    in_project.set_current(directory)
    assert runner.invoke(app, ["progress", "watch", "--rounds", "1"]).exit_code == 0
    assert (in_project.root / ".specify" / "progress" / "001-login.html").is_file()


def test_it_can_follow_a_spec_that_is_not_the_current_one(in_project):
    in_project.feature()
    in_project.set_current(in_project.feature(name="002-other"))
    result = runner.invoke(app, ["progress", "watch", "--rounds", "1", "--feature", "001"])
    assert result.exit_code == 0, result.output
    assert "001-login" in strip_ansi(result.output)


def test_a_spec_that_does_not_exist_is_refused(in_project):
    in_project.feature()
    result = runner.invoke(app, ["progress", "watch", "--rounds", "1", "--feature", "999"])
    assert result.exit_code == 1


def test_with_no_spec_it_waits_for_one(in_project):
    result = runner.invoke(app, ["progress", "watch", "--rounds", "1"])
    assert result.exit_code == 0, result.output
    assert "tasks done" not in strip_ansi(result.output)


def test_with_the_lock_taken_it_looks_again_next_time(in_project, engine):
    directory = in_project.feature()
    in_project.set_current(directory)
    with engine.spec_lock(in_project.root, directory):
        assert engine.watch_round(in_project.root, None, None) == (None, None)
    last, line = engine.watch_round(in_project.root, None, None)
    assert "001-login" in line
    assert engine.watch_round(in_project.root, None, last) == (last, None)


def test_a_write_problem_is_shown_and_it_keeps_watching(in_project, engine, monkeypatch):
    directory = in_project.feature()
    in_project.set_current(directory)

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(engine, "render_project", broken)
    monkeypatch.setattr(command_watch, "load_engine", lambda: engine)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    result = runner.invoke(app, ["progress", "watch", "--rounds", "2"])
    assert result.exit_code == 0, result.output
    assert strip_ansi(result.output).count("disk full") == 2


def test_control_c_ends_it_cleanly(in_project, monkeypatch):
    in_project.set_current(in_project.feature())

    def interrupted(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(command_watch.time, "sleep", interrupted)
    result = runner.invoke(app, ["progress", "watch"])
    assert result.exit_code == 0, result.output
    assert "Stopped." in strip_ansi(result.output)


@pytest.mark.parametrize("value", ["0", "-1", "0.01"])
def test_an_interval_too_short_is_refused(in_project, value):
    assert runner.invoke(app, ["progress", "watch", "--rounds", "1", "--interval", value]).exit_code == 2


def test_outside_a_project_it_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["progress", "watch", "--rounds", "1"]).exit_code != 0
