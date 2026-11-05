"""Graphify as a part of specify: finding it, and the first graph of a project."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from specify_cli import _graphify
from specify_cli._graphify import GATE, build_first_graph, graphify_path, graphify_version


def test_it_is_found_beside_this_python_with_an_empty_path(monkeypatch):
    monkeypatch.setenv("PATH", "")
    path = graphify_path()
    assert path is not None
    assert Path(path).parent == Path(_graphify._environment_bin())


def test_the_version_is_the_one_that_runs():
    assert graphify_version() == "0.9.102"


def test_it_is_missing_when_it_is_nowhere(monkeypatch):
    monkeypatch.setattr(_graphify.shutil, "which", lambda *_args, **_kwargs: None)
    assert graphify_path() is None
    assert graphify_version() is None


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.CompletedProcess([], 1, stdout="graphify 0.9.102"),
        subprocess.CompletedProcess([], 0, stdout="no version here"),
        OSError("cannot run"),
        subprocess.TimeoutExpired("graphify", 60),
    ],
)
def test_a_tool_that_cannot_say_its_version_counts_as_missing(monkeypatch, outcome):
    monkeypatch.setattr(_graphify.shutil, "which", lambda *_args, **_kwargs: "graphify")
    with patch.object(_graphify.subprocess, "run", side_effect=[outcome]):
        assert graphify_version() is None


def _project_with_gate(tmp_path: Path) -> Path:
    gate = tmp_path / GATE
    gate.parent.mkdir(parents=True)
    gate.write_text("", encoding="utf-8")
    return tmp_path


def test_without_the_gate_nothing_runs(tmp_path: Path):
    with patch.object(_graphify.subprocess, "run") as run:
        assert build_first_graph(tmp_path) == ("skip", "not used in this project")
    run.assert_not_called()


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        ({"status": "ok"}, ("complete", "graph built")),
        ({"status": "degraded", "reason": "no-code"}, ("skip", "no code yet")),
        ({"status": "degraded", "reason": "update-failed"}, ("error", "not built: update-failed")),
        ({"status": "degraded", "reason": "not-installed"}, ("error", "not built: not-installed")),
    ],
)
def test_the_report_of_the_gate_becomes_a_step(tmp_path: Path, report, expected):
    done = subprocess.CompletedProcess([], 0, stdout=json.dumps(report))
    with patch.object(_graphify.subprocess, "run", return_value=done):
        assert build_first_graph(_project_with_gate(tmp_path)) == expected


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.CompletedProcess([], 1, stdout="not json"),
        OSError("cannot run"),
        subprocess.TimeoutExpired("gate", 660),
    ],
)
def test_a_gate_that_fails_never_raises(tmp_path: Path, outcome):
    with patch.object(_graphify.subprocess, "run", side_effect=[outcome]):
        state, detail = build_first_graph(_project_with_gate(tmp_path))
    assert state == "error" and detail.startswith("not built:")


def test_the_gate_finds_this_environment_however_specify_was_started(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PATH", "/elsewhere")
    done = subprocess.CompletedProcess([], 0, stdout='{"status": "ok"}')
    with patch.object(_graphify.subprocess, "run", return_value=done) as run:
        build_first_graph(_project_with_gate(tmp_path))
    assert run.call_args.kwargs["env"]["PATH"].split(_graphify.os.pathsep)[0] == _graphify._environment_bin()
