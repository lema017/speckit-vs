"""Command tests for ``specify studio check``."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from specify_cli import app
from tests.conftest import strip_ansi

runner = CliRunner()
PENDING = "specs/_product/mockup/inicio.html: 6 links lead to something that is not designed yet: #proponer, #taller, #talleres"


def plain(result):
    return strip_ansi(result.output)


def test_a_design_that_agrees_passes_and_says_what_is_worth_knowing(designed):
    before = designed.written()
    result = runner.invoke(app, ["studio", "check"])
    assert result.exit_code == 0, result.output
    assert "Worth knowing (1)" in plain(result) and "To fix" not in plain(result)
    assert "6 links lead to something that is not designed yet" in plain(result).replace("\n", "")
    assert designed.written() == before, "the check writes nothing"


def test_a_design_with_nothing_to_say_says_so(designed):
    (designed.product / "mockup" / "inicio.html").unlink()
    result = runner.invoke(app, ["studio", "check"])
    assert result.exit_code == 0 and plain(result).strip() == "The design and the mockup agree."


def test_something_to_fix_exits_with_one(designed):
    designed.edit("mockup/entrar.html", 'data-screen="SCR-login"', 'data-screen="SCR-otra"')
    result = runner.invoke(app, ["studio", "check"])
    assert result.exit_code == 1
    assert "To fix (1)" in plain(result) and "<body data-screen> says SCR-otra" in plain(result).replace("\n", "")


def test_the_slices_of_an_area_are_checked_too(designed, monkeypatch):
    from specify_cli.studios import _script as script_module

    script = script_module.load_script()
    monkeypatch.setattr(script, "slice_problems", lambda product: (["specs/_slices/acceso.md: D-acceso-clave names ST-9, which is not in story-map.md"],
                                                                   ["specs/_slices/acceso.md: ST-4 of the area acceso is in no slice"]))
    result = runner.invoke(app, ["studio", "check", "--json"])
    answer = json.loads(result.output)
    assert result.exit_code == 1 and answer["status"] == "invalid"
    assert answer["hard"] == ["specs/_slices/acceso.md: D-acceso-clave names ST-9, which is not in story-map.md"]
    assert answer["notes"] == [PENDING, "specs/_slices/acceso.md: ST-4 of the area acceso is in no slice"]


def test_a_map_nothing_here_can_read_is_worth_knowing(designed):
    folder = designed.root / "specs" / "_slices"
    folder.mkdir(parents=True)
    (folder / "acceso.md").write_text("# Slices: Acceso\n\n<!-- slice-map:v1 -->\n", encoding="utf-8")
    result = runner.invoke(app, ["studio", "check", "--json"])
    assert result.exit_code == 0 and json.loads(result.output)["notes"][1].startswith("specs/_slices: nothing read the slice maps")


def test_json_carries_both_lists(designed):
    result = runner.invoke(app, ["studio", "check", "--json"])
    assert result.exit_code == 0 and json.loads(result.output) == {"status": "ok", "hard": [], "notes": [PENDING]}
    designed.edit("mockup/entrar.html", 'data-screen="SCR-login"', 'data-screen="SCR-otra"')
    result = runner.invoke(app, ["studio", "check", "--json"])
    assert result.exit_code == 1 and json.loads(result.output)["status"] == "invalid" and len(json.loads(result.output)["hard"]) == 1


def test_text_of_the_design_reaches_the_terminal_as_text(designed):
    designed.edit("mockup/entrar.html", 'data-screen="SCR-login"', 'data-screen="[red]x[/red]\x1b[31m"')
    result = runner.invoke(app, ["studio", "check"])
    assert result.exit_code == 1 and "[red]x[/red]" in plain(result).replace("\n", "") and "\x1b[31m" not in result.output


def test_a_project_without_a_design_is_told_where_to_start(project):
    result = runner.invoke(app, ["studio", "check"])
    assert result.exit_code == 1 and "This project has no design yet" in plain(result)
