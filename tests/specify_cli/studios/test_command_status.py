"""Command tests for ``specify studio status``."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from specify_cli import app
from tests.conftest import strip_ansi

runner = CliRunner()


def lines(result):
    return [" ".join(line.split()) for line in strip_ansi(result.output).splitlines() if line.strip()]


def test_it_says_how_far_the_design_is_and_what_comes_next(designed):
    before = designed.written()
    result = runner.invoke(app, ["studio", "status"])
    assert result.exit_code == 0, result.output
    shown = lines(result)
    assert shown[0] == "Design of Oficio"
    assert shown[2:8] == ["Define done 2 decisions", "Map done 2 of 2 areas", "Mockup done 6 of 6 screens", "Iterate not started No comments yet",
                          "Approve in progress 1 of 2 areas", "Slice not started 0 of 2 areas"]
    assert shown[8] == "Area State Screens Drawn Rules approved Slices delivered"
    assert shown[9:11] == ["Acceso drawn 5 5 0 of 6 -", "Inicio approved 1 1 - -"], "an area with no rule has nothing to approve, and none is cut yet"
    assert shown[11] == "Next: /speckit.studio.approve acceso. Acceso is drawn. Approve its rules when the mockup is right, or say what to change first."
    assert shown[12:] == ["Needs your attention", "Open, Ana Pérez decides: ¿Hay cupo por taller?", "6 links in Inicio lead to something that is not designed yet."]
    assert designed.written() == before, "reading the design writes nothing"


def test_the_next_command_is_written_the_way_the_agent_takes_it(designed):
    (designed.root / ".specify" / "init-options.json").write_text(json.dumps({"ai_skills": True}), encoding="utf-8")
    designed.edit("navigation.md", "## Flows", "### talleres Talleres\n- Covers: Ver los talleres y apuntarse\n\n## Flows")
    shown = lines(runner.invoke(app, ["studio", "status"]))
    assert "Talleres not started 0 0 - -" in shown
    assert "Next: /speckit-studio-approve acceso. Acceso is drawn. Approve its rules when the mockup is right, or say what to change first." in shown
    assert "Map in progress 2 of 3 areas" in shown


def test_an_area_says_how_many_of_its_slices_are_delivered(designed, monkeypatch):
    from specify_cli.studios import _script as script_module

    script = script_module.load_script()
    read = script.status

    def cut(product):
        status = read(product)
        status["areas"][0]["slices"] = {"total": 4, "delivered": 1, "underway": 1, "next": None, "loose": []}
        del status["areas"][1]["slices"]  # What a studio script from before an area was cut answers.
        return status

    monkeypatch.setattr(script, "status", cut)
    result = runner.invoke(app, ["studio", "status"])
    assert result.exit_code == 0, result.output
    shown = lines(result)
    assert "Acceso drawn 5 5 0 of 6 1 of 4" in shown and "Inicio approved 1 1 - -" in shown


def test_a_project_without_a_design_is_told_where_to_start(project):
    result = runner.invoke(app, ["studio", "status"])
    assert result.exit_code == 0 and lines(result) == ["No design yet. It starts with /speckit.studio.define."]


def test_json_is_what_the_script_answers(designed):
    result = runner.invoke(app, ["studio", "status", "--json"])
    status = json.loads(result.output)
    assert result.exit_code == 0 and status["product"] == "Oficio" and [step["name"] for step in status["steps"]] == ["define", "map", "mockup", "iterate", "approve", "slice"]
    assert status["summary"]["people"][1]["name"] == "Tomás", "names keep their letters"


def test_a_design_that_cannot_be_read_stops_with_its_reason(designed):
    designed.edit("product.md", "studio-product:v1", "studio-product:v9")
    result = runner.invoke(app, ["studio", "status"])
    assert result.exit_code == 1 and "is in a newer format than this script reads" in strip_ansi(result.output).replace("\n", "")


def test_text_of_the_design_reaches_the_terminal_as_text(designed):
    designed.edit("product.md", "# Product: Oficio", "# Product: [bold]Oficio[/bold]\x1b[31m")
    result = runner.invoke(app, ["studio", "status"])
    assert result.exit_code == 0 and "Design of [bold]Oficio[/bold]" in strip_ansi(result.output) and "\x1b[31m" not in result.output
