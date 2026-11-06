"""Command tests for ``specify progress open``."""

from __future__ import annotations

import webbrowser

import pytest
from typer.testing import CliRunner

from specify_cli import app
from tests.conftest import strip_ansi

runner = CliRunner()


@pytest.fixture
def opened(monkeypatch):
    """Record what would have opened. No test here may start a real browser."""
    calls = []

    def fake_open(url):
        calls.append(url)
        return True

    monkeypatch.setattr(webbrowser, "open", fake_open)
    monkeypatch.setattr("sys.platform", "darwin")
    return calls


def plain(result):
    return strip_ansi(result.output).replace("\n", "")


def test_it_draws_and_opens_the_current_spec(in_project, opened):
    in_project.set_current(in_project.feature("001-login"))
    in_project.feature("002-logout")
    result = runner.invoke(app, ["progress", "open"])
    assert result.exit_code == 0, result.output
    page = in_project.root / ".specify" / "progress" / "001-login.html"
    assert page.is_file()
    assert opened == [page.resolve().as_uri()]
    assert page.resolve().as_uri() in plain(result)


def test_without_a_current_spec_it_opens_the_list(in_project, opened):
    in_project.feature("001-login")
    result = runner.invoke(app, ["progress", "open"])
    assert result.exit_code == 0, result.output
    assert opened == [(in_project.root / ".specify" / "progress" / "index.html").resolve().as_uri()]


def test_a_spec_can_be_picked(in_project, opened):
    in_project.set_current(in_project.feature("001-login"))
    in_project.feature("002-logout")
    result = runner.invoke(app, ["progress", "open", "--feature", "002"])
    assert result.exit_code == 0, result.output
    assert opened[0].endswith("/002-logout.html")


def test_no_browser_only_prints_the_link(in_project, opened):
    in_project.feature("001-login")
    result = runner.invoke(app, ["progress", "open", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert opened == []
    assert "index.html" in plain(result)
    assert "Could not open" not in plain(result)


@pytest.mark.parametrize(("name", "value"), [("CI", "true"), ("SSH_CONNECTION", "a b c d"), ("SSH_TTY", "/dev/ttys001")])
def test_where_nobody_could_see_it_only_the_link_is_printed(in_project, opened, monkeypatch, name, value):
    in_project.feature("001-login")
    monkeypatch.setenv(name, value)
    result = runner.invoke(app, ["progress", "open"])
    assert result.exit_code == 0, result.output
    assert opened == []
    assert "index.html" in plain(result)
    assert "Could not open a browser" in plain(result)


def test_without_a_display_on_linux_only_the_link_is_printed(in_project, opened, monkeypatch):
    in_project.feature("001-login")
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    result = runner.invoke(app, ["progress", "open"])
    assert result.exit_code == 0, result.output
    assert opened == []


@pytest.mark.parametrize("failure", ["false", "error"])
def test_a_browser_that_will_not_open_still_leaves_the_link(in_project, monkeypatch, failure):
    in_project.feature("001-login")

    def fake_open(_url):
        if failure == "error":
            raise webbrowser.Error("none")
        return False

    monkeypatch.setattr(webbrowser, "open", fake_open)
    monkeypatch.setattr("sys.platform", "darwin")
    result = runner.invoke(app, ["progress", "open"])
    assert result.exit_code == 0, result.output
    assert "Could not open a browser" in plain(result)
    assert "index.html" in plain(result)


def test_an_unknown_spec_opens_nothing(in_project, opened):
    in_project.feature("001-login")
    result = runner.invoke(app, ["progress", "open", "--feature", "zzz"])
    assert result.exit_code == 1
    assert opened == []
    assert not (in_project.root / ".specify" / "progress").exists()


def test_it_fails_outside_a_project(tmp_path, monkeypatch, opened):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["progress", "open"])
    assert result.exit_code == 1
    assert opened == []
    assert list(tmp_path.iterdir()) == []


def test_a_project_elsewhere_can_be_targeted(project, tmp_path, monkeypatch, opened):
    project.feature("001-login")
    launch = tmp_path / "elsewhere"
    launch.mkdir()
    monkeypatch.chdir(launch)
    monkeypatch.setenv("SPECIFY_INIT_DIR", str(project.root))
    result = runner.invoke(app, ["progress", "open"])
    assert result.exit_code == 0, result.output
    assert opened == [(project.root / ".specify" / "progress" / "index.html").resolve().as_uri()]
    assert list(launch.iterdir()) == []
