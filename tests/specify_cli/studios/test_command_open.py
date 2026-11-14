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
