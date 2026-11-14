"""Command tests for ``specify progress status``."""

from __future__ import annotations

import io
import json
import sys

import pytest
from typer.testing import CliRunner

from specify_cli import app
from specify_cli.progress._engine import terminal_text
from tests.conftest import strip_ansi

from .conftest import task_event

runner = CliRunner()


def status(*args):
    return runner.invoke(app, ["progress", "status", *args], env={"COLUMNS": "200"})


def test_it_shows_the_current_spec_in_detail(in_project):
    directory = in_project.feature("001-login", events=[task_event("T002", "in_progress", actor={"harness": "claude"}), task_event("T003", "blocked", note="No key")])
    in_project.feature("002-logout")
    in_project.set_current(directory)
    result = status()
    assert result.exit_code == 0, result.output
    output = strip_ansi(result.output)
    assert "Login" in output and "001-login, current" in output
    assert "1 of 4" in output and "25%" in output
    assert "T002 in progress, possibly abandoned (claude): Add the linter" in output
    assert "T003 blocked: Add the form" in output
    assert "T003 Blocked: No key" in output
    assert "claude: 0 done (on T002)" in output
    assert "Phase 1: Setup" in output
    assert "002-logout" not in output


def test_without_a_current_spec_it_lists_them_all(in_project):
    in_project.feature("001-login")
    in_project.feature("002-logout", tasks="- [x] T001 A\n")
    result = status()
    assert result.exit_code == 0, result.output
    output = strip_ansi(result.output)
    assert "001-login" in output and "1 of 4" in output and "3 pending" in output
    assert "002-logout" in output and "1 of 1" in output and "nothing left" in output


def test_all_lists_them_even_with_a_current_spec(in_project):
    in_project.set_current(in_project.feature("001-login"))
    in_project.feature("002-logout", tasks=None)
    output = strip_ansi(status("--all").output)
    assert "001-login (current)" in output
    assert "002-logout" in output and "no tasks yet" in output


def test_a_spec_can_be_picked_by_prefix(in_project):
    in_project.feature("001-login")
    in_project.feature("002-logout", spec="# Logout\n", tasks=None)
    output = strip_ansi(status("--feature", "002").output)
    assert "Logout" in output and "Tasks  none yet" in output


def test_it_prints_json_for_machines(in_project):
    in_project.feature("001-login")
    result = status("--json")
    assert result.exit_code == 0, result.output
    row = json.loads(result.stdout)[0]
    assert row["id"] == "001-login"
    assert row["totals"] == {"total": 4, "done": 1, "in_progress": 0, "blocked": 0, "failed": 0, "skipped": 0, "pending": 3}


def test_it_writes_nothing(in_project):
    in_project.feature("001-login", events=[task_event("T002", "in_progress")])
    before = in_project.written()
    for args in ([], ["--all"], ["--json"], ["--feature", "001"]):
        assert status(*args).exit_code == 0
    assert in_project.written() == before


def test_no_specs_is_not_an_error(in_project):
    result = status()
    assert result.exit_code == 0
    assert "No specs yet." in strip_ansi(result.output)
    assert json.loads(status("--json").stdout) == []


def test_an_unknown_spec_fails(in_project):
    in_project.feature("001-login")
    result = status("--feature", "zzz")
    assert result.exit_code == 1
    assert "No spec named" in strip_ansi(result.output)


def test_feature_and_all_cannot_be_combined(in_project):
    in_project.feature("001-login")
    result = status("--feature", "001", "--all")
    assert result.exit_code == 1
    assert "not both" in strip_ansi(result.output)


def test_it_fails_outside_a_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert status().exit_code == 1


def test_a_project_elsewhere_can_be_targeted(project, tmp_path, monkeypatch):
    project.feature("001-login")
    launch = tmp_path / "elsewhere"
    launch.mkdir()
    monkeypatch.chdir(launch)
    monkeypatch.setenv("SPECIFY_INIT_DIR", str(project.root))
    result = status("--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["id"] == "001-login"


@pytest.mark.parametrize("flags", [[], ["--all"]])
def test_text_from_a_file_cannot_control_the_terminal_or_be_read_as_markup(in_project, flags):
    evil = "evil \x1b[2J\x1b]0;owned\x07 [red]not red[/red] [/] \u202ereversed"
    tasks = "## %s\n- [ ] T001 %s\n- [ ] T002 %s\n" % (evil, evil, evil)
    directory = in_project.feature("001-login", spec="# %s\n" % evil, tasks=tasks, events=[task_event("T001", "in_progress", actor={"harness": evil}), task_event("T002", "blocked", note=evil)])
    if not flags:
        in_project.set_current(directory)
    result = status(*flags)
    assert result.exit_code == 0, result.output
    assert "\x1b[2J" not in result.output
    assert "\x1b]0" not in result.output
    assert "\x07" not in result.output
    assert "\u202e" not in result.output
    if not flags:
        assert "[red]not red[/red]" in result.output


def test_characters_the_output_cannot_encode_are_replaced_and_do_not_crash(monkeypatch):
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    try:
        assert terminal_text("caf\u00e9 \u2603") == "caf\u00e9 ?"
    finally:
        monkeypatch.undo()
        stream.detach()


def test_json_output_escapes_control_characters(in_project):
    in_project.feature("001-login", tasks="- [ ] T001 evil \x1b[2J\n", events=[task_event("T001", "in_progress")])
    result = status("--json")
    assert "\x1b" not in result.stdout
    assert json.loads(result.stdout)[0]["active"][0]["text"] == "evil \x1b[2J"


def test_an_unknown_spec_name_cannot_control_the_terminal(in_project):
    in_project.feature("001-login")
    result = status("--feature", "\x1b[2Jzzz[red]")
    assert result.exit_code == 1
    assert "\x1b[2J" not in result.output


# -- The design of the product -----------------------------------------------------------------

DESIGN = ["Design of Oficio", "Steps: Define: 2 decisions; Map: 2 of 2 areas; Mockup: 6 of 6 screens",
          "Next: /speckit.studio.mockup. Every area is drawn. Open the mockup and say what to change.", "Needs attention: 2, see the page"]


def test_the_design_is_shown_before_the_specs(in_project):
    in_project.design()
    in_project.feature("001-login")
    in_project.feature("002-logout")
    before = in_project.written()
    result = status()
    assert result.exit_code == 0, result.output
    lines = [" ".join(line.split()) for line in strip_ansi(result.output).splitlines() if line.strip()]
    assert lines[:4] == DESIGN and lines[4].startswith("Spec ") and any(line.startswith("001-login") for line in lines)
    assert in_project.written() == before, "reading the progress writes nothing"


def test_a_design_with_no_spec_yet_is_all_there_is_to_show(in_project):
    in_project.design()
    lines = [" ".join(line.split()) for line in strip_ansi(status().output).splitlines() if line.strip()]
    assert lines == DESIGN + ["No specs yet."]


def test_the_design_is_shown_with_the_current_spec_too(in_project):
    in_project.design()
    in_project.set_current(in_project.feature("001-login"))
    output = strip_ansi(status().output)
    assert "Design of Oficio" in output and "001-login, current" in output


def test_a_spec_that_was_asked_for_is_shown_alone(in_project):
    in_project.design()
    in_project.feature("001-login")
    assert "Design of Oficio" not in strip_ansi(status("--feature", "001").output)


def test_json_stays_the_list_of_specs(in_project):
    in_project.design()
    in_project.feature("001-login")
    rows = json.loads(status("--all", "--json").output)
    assert [row["id"] for row in rows] == ["001-login"]


def test_a_project_without_a_design_shows_none(in_project):
    in_project.feature("001-login")
    assert "Design" not in strip_ansi(status().output)
