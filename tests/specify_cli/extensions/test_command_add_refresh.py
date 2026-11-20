"""The refresh phase of ``specify extension add``: what it runs, and what it says when that fails."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from specify_cli.extensions import _command_add_refresh as refresh

SCRIPT = Path("scripts") / "python" / "capabilities.py"
RECORDS = "import json, pathlib, sys\npathlib.Path(__file__).with_name('ran.json').write_text(json.dumps(sys.argv[1:]))\n"


class Case:
    """A project, and the extension as it ships with specify. Its script writes its arguments next to itself."""

    def __init__(self, tmp_path: Path, body: str):
        self.project = tmp_path / "project"
        self.project.mkdir()
        self.shipped = tmp_path / "shipped" / "capabilities"
        self.script = self.shipped / SCRIPT
        self.script.parent.mkdir(parents=True)
        self.script.write_text(RECORDS + body, encoding="utf-8")

    def lines(self, extension: str = "capabilities") -> list[str]:
        return refresh.refresh_lines(self.project, extension, self.shipped)

    def ran(self) -> list[str] | None:
        record = self.script.with_name("ran.json")
        return json.loads(record.read_text(encoding="utf-8")) if record.exists() else None


def answer(setup: list[str], status: str = "ok") -> str:
    return "print(%r)\n" % json.dumps({"setup": setup, "status": status})


def test_it_asks_the_shipped_script_to_refresh_this_project(tmp_path):
    case = Case(tmp_path, answer(["CLAUDE.md", ".gitattributes"]))
    assert case.lines() == ["Brought up to date: CLAUDE.md, .gitattributes"]
    assert case.ran() == ["refresh", "--root", str(case.project)]


def test_a_script_of_the_project_is_never_run(tmp_path):
    """The project gets a copy of the script. What runs is the one inside specify."""
    case = Case(tmp_path, answer([]))
    installed = case.project / ".specify" / "extensions" / "capabilities" / SCRIPT
    installed.parent.mkdir(parents=True)
    installed.write_text(RECORDS + answer(["CLAUDE.md"]), encoding="utf-8")
    assert case.lines() == []
    assert case.ran() is not None and not installed.with_name("ran.json").exists()


@pytest.mark.parametrize("setup, status", [([], "ok"), ([], "none")])
def test_it_says_nothing_when_nothing_changed(tmp_path, setup, status):
    case = Case(tmp_path, answer(setup, status))
    assert case.lines() == []
    assert case.ran() is not None


def test_it_says_what_the_extension_could_not_refresh(tmp_path):
    case = Case(tmp_path, answer([".gitignore", "skipped CLAUDE.md: unbalanced markers"]))
    assert case.lines() == [
        "Brought up to date: .gitignore",
        "[yellow]⚠[/yellow]  Not brought up to date: CLAUDE.md: unbalanced markers",
    ]


def test_a_name_with_brackets_is_not_read_as_markup(tmp_path):
    case = Case(tmp_path, answer(["docs/[red]AI.md"]))
    assert case.lines() == ["Brought up to date: docs/\\[red]AI.md"]


@pytest.mark.parametrize("extension", ["studio", "git", "made-up", "../capabilities"])
def test_an_extension_with_nothing_to_refresh_runs_nothing(tmp_path, extension):
    case = Case(tmp_path, answer(["CLAUDE.md"]))
    assert case.lines(extension) == []
    assert case.ran() is None


def test_a_shipped_extension_without_the_script_runs_nothing(tmp_path):
    case = Case(tmp_path, answer(["CLAUDE.md"]))
    case.script.unlink()
    assert case.lines() == []


def problem(lines: list[str]) -> str:
    assert len(lines) == 1, lines
    assert lines[0].startswith("[yellow]⚠[/yellow]  Could not bring up to date what capabilities keeps in this project: ")
    assert lines[0].endswith(" Its own commands do it the next time a spec is reviewed or folded.")
    return lines[0]


def test_a_script_that_fails_is_said_and_does_not_raise(tmp_path):
    case = Case(tmp_path, "sys.stderr.write('boom [x]\\n')\nsys.exit(4)\n")
    said = problem(case.lines())
    assert "it ended with code 4" in said and "boom \\[x]" in said


@pytest.mark.parametrize("body", [
    "print('not json')\n",
    "print('[]')\n",
    "print('{}')\n",
    "print('{\"setup\": \"CLAUDE.md\"}')\n",
    "print('{\"setup\": [1]}')\n",
    "",
])
def test_an_answer_that_cannot_be_read_is_said(tmp_path, body):
    case = Case(tmp_path, body)
    assert "its answer could not be read" in problem(case.lines())


def test_a_script_that_does_not_answer_in_time_is_said(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, "_TIMEOUT_SECONDS", 0.5)
    case = Case(tmp_path, "import time\ntime.sleep(30)\n")
    assert "it did not answer in 0.5 seconds" in problem(case.lines())


def test_a_python_that_cannot_be_started_is_said(tmp_path, monkeypatch):
    case = Case(tmp_path, answer(["CLAUDE.md"]))

    def no_python(*args, **kwargs):
        raise OSError("no such interpreter")

    monkeypatch.setattr(refresh.subprocess, "run", no_python)
    assert "no such interpreter" in problem(case.lines())


def test_it_runs_the_script_alone_and_writes_no_bytecode(tmp_path, monkeypatch):
    """Isolated: a PYTHONPATH that leads to a file named like a module of the standard library loads nothing."""
    case = Case(tmp_path, answer([]))
    (case.project / "json.py").write_text("raise SystemExit('the project was loaded')\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(case.project))
    seen = {}
    real = subprocess.run

    def spy(argv, **kwargs):
        seen["argv"], seen["kwargs"] = argv, kwargs
        return real(argv, **kwargs)

    monkeypatch.setattr(refresh.subprocess, "run", spy)
    assert case.lines() == []
    assert seen["argv"] == [sys.executable, "-I", "-B", str(case.script), "refresh", "--root", str(case.project)]
    assert seen["kwargs"]["cwd"] == case.project and seen["kwargs"]["timeout"] == refresh._TIMEOUT_SECONDS
    assert not list(tmp_path.rglob("__pycache__"))
