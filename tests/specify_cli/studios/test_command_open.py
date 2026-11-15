"""Command tests for ``specify studio open``."""

from __future__ import annotations

from typer.testing import CliRunner

from specify_cli import app
from tests.conftest import strip_ansi

runner = CliRunner()


def plain(result):
    return strip_ansi(result.output).replace("\n", "")


def test_it_builds_the_mockup_and_opens_it(designed, opened):
    result = runner.invoke(app, ["studio", "open"])
    assert result.exit_code == 0, result.output
    index = designed.product / "mockup" / "index.html"
    assert index.is_file() and (designed.product / "mockup" / "_studio" / "runtime.js").is_file()
    assert opened == [index.resolve().as_uri()]
    assert index.resolve().as_uri() in plain(result) and "Could not open" not in plain(result)


def test_no_browser_only_prints_the_link(designed, opened):
    result = runner.invoke(app, ["studio", "open", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert opened == []
    assert (designed.product / "mockup" / "index.html").resolve().as_uri() in plain(result) and "Could not open" not in plain(result)


def test_where_nobody_would_see_a_browser_it_says_so_and_prints_the_link(designed, opened, monkeypatch):
    monkeypatch.setenv("CI", "true")
    result = runner.invoke(app, ["studio", "open"])
    assert result.exit_code == 0, result.output
    assert opened == []
    assert "Could not open a browser here. The mockup is at:" in plain(result)
    assert (designed.product / "mockup" / "index.html").resolve().as_uri() in plain(result)


def test_it_can_open_the_looks_to_choose_from(designed, opened):
    result = runner.invoke(app, ["studio", "open", "--directions"])
    assert result.exit_code == 0, result.output
    page = designed.product / "mockup" / "_studio" / "directions.html"
    assert opened == [page.resolve().as_uri()]
    assert not (designed.product / "mockup" / "index.html").exists(), "the mockup was not asked for"


def test_before_the_first_page_it_says_which_command_draws_them(designed, opened):
    for path in (designed.product / "mockup").glob("*.html"):
        path.unlink()
    result = runner.invoke(app, ["studio", "open"])
    assert result.exit_code == 1 and opened == []
    assert "no screen has a page yet: speckit.studio.mockup draws them" in plain(result)


def test_a_project_without_a_design_is_told_where_to_start(project, opened):
    result = runner.invoke(app, ["studio", "open"])
    assert result.exit_code == 1 and opened == []
    assert "This project has no design yet. It starts with the speckit.studio.define command" in plain(result)
    assert not (project.root / "specs").exists()


def test_a_design_that_cannot_be_read_stops_with_its_reason(designed, opened):
    designed.edit("product.md", "<!-- studio-product:v1 -->\n", "")
    result = runner.invoke(app, ["studio", "open"])
    assert result.exit_code == 1 and opened == []
    assert "has no <!-- studio-product:v1 --> line" in plain(result)


def test_outside_a_project_it_fails(tmp_path, monkeypatch, opened):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["studio", "open"])
    assert result.exit_code == 1 and opened == []


def test_where_a_server_can_run_it_opens_the_served_mockup_and_says_where_comments_go(designed, opened, monkeypatch):
    from specify_cli.studios._script import load_script

    script = load_script()
    started = []
    monkeypatch.delenv("SPECKIT_STUDIO_NO_SERVER")
    monkeypatch.setattr(script, "server_state", lambda root: None)
    monkeypatch.setattr(script, "start_server", lambda root: started.append(root) or {"port": 47123, "session": "s"})
    result = runner.invoke(app, ["studio", "open"])
    assert result.exit_code == 0, result.output
    assert opened == ["http://127.0.0.1:47123/index.html"] and started == [designed.root.resolve()]
    assert "http://127.0.0.1:47123/index.html" in plain(result)
    assert "A comment made in the mockup is kept in the project." in plain(result) and "specify studio open --stop" in plain(result)


def test_the_file_is_opened_when_no_server_is_asked_for(designed, opened):
    result = runner.invoke(app, ["studio", "open"])
    assert result.exit_code == 0 and opened == [(designed.product / "mockup" / "index.html").resolve().as_uri()]
    assert "is kept in the project" not in plain(result)


def test_stop_stops_the_server_of_the_project_and_opens_nothing(designed, opened, monkeypatch):
    from specify_cli.studios._script import load_script

    script = load_script()
    asked = []
    monkeypatch.setattr(script, "stop_server", lambda root: asked.append(root) or True)
    result = runner.invoke(app, ["studio", "open", "--stop"])
    assert result.exit_code == 0 and opened == [] and asked == [designed.root.resolve()]
    assert "The server of the mockup stopped." in plain(result)
    assert not (designed.product / "mockup" / "index.html").exists(), "stopping builds nothing"
    monkeypatch.setattr(script, "stop_server", lambda root: False)
    assert "No server of the mockup was running." in plain(runner.invoke(app, ["studio", "open", "--stop"]))


def test_stop_needs_no_design(project, opened):
    result = runner.invoke(app, ["studio", "open", "--stop"])
    assert result.exit_code == 0 and "No server of the mockup was running." in plain(result)
