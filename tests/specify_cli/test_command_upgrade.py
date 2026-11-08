"""``specify upgrade``: the latest release of specify, then the project it runs in.

Every step is its own ``specify`` process, so these tests record the commands it
would run instead of running them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from specify_cli import app
from specify_cli import command_upgrade

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _text(result) -> str:
    return " ".join(_ANSI.sub("", result.output).split())


def make_project(root: Path, integrations=("claude",), default="claude", extensions=("capabilities",)) -> Path:
    """A project folder. ``extensions`` names them, or maps each name to its registry fields."""
    specify = root / ".specify"
    specify.mkdir(parents=True)
    if integrations is not None:
        (specify / "integration.json").write_text(
            json.dumps({
                "version": "1.5.3",
                "integration_state_schema": 1,
                "installed_integrations": list(integrations),
                "integration": default,
                "default_integration": default,
            }),
            encoding="utf-8",
        )
    if extensions:
        registry = specify / "extensions" / ".registry"
        registry.parent.mkdir(parents=True)
        registry.write_text(
            json.dumps({
                "schema_version": "1.0",
                "extensions": {
                    name: {"version": "0.1.0", "enabled": True, "priority": 10,
                           **(extensions[name] if isinstance(extensions, dict) else {})}
                    for name in extensions
                },
            }),
            encoding="utf-8",
        )
    return root


class _Calls(list):
    """The commands specify upgrade ran."""

    failing: dict


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = make_project(tmp_path / "proj")
    monkeypatch.chdir(root)
    return root


def run(*args):
    return CliRunner().invoke(app, ["upgrade", *args])


def commands(calls):
    return [" ".join(argv[1:]) for argv in calls]


@pytest.fixture
def calls_list(monkeypatch):
    """Record each step instead of running it. ``failing`` maps a command to its exit code."""
    recorded = _Calls()
    recorded.failing = {}

    def run_step(argv):
        recorded.append(list(argv))
        return recorded.failing.get(" ".join(argv[1:]), 0)

    monkeypatch.setattr(command_upgrade, "_run_step", run_step)
    monkeypatch.setattr(command_upgrade, "_specify_executable", lambda: "specify")
    return recorded


def test_it_updates_specify_then_each_integration_then_adds_the_bundled_extensions_again(
    tmp_path, monkeypatch, calls_list
):
    root = make_project(tmp_path / "proj", integrations=("copilot", "claude"), default="claude",
                        extensions=("capabilities", "acme"))
    monkeypatch.chdir(root)
    result = run()
    assert result.exit_code == 0, result.output
    assert commands(calls_list) == [
        "self upgrade",
        "integration upgrade claude",
        "integration upgrade copilot",
        # Adding it again installs the copy this specify ships, and keeps its configuration.
        # `extension update` would compare with the catalog on main and could skip it.
        "extension add capabilities --force --priority 10",
    ]
    text = _text(result)
    assert "Not updated: acme does not ship with specify. To update it: specify extension update acme" in text


def test_a_pinned_release_reaches_the_self_upgrade(project, calls_list):
    result = run("--tag", "v1.5.3")
    assert result.exit_code == 0, result.output
    assert commands(calls_list)[0] == "self upgrade --tag v1.5.3"


def test_a_failed_self_upgrade_leaves_the_project_alone(project, calls_list):
    calls_list.failing["self upgrade"] = 3
    result = run()
    assert result.exit_code == 3
    assert commands(calls_list) == ["self upgrade"]
    assert "Stopped: specify self upgrade did not finish. The project was not changed." in _text(result)


def test_a_step_that_fails_stops_the_ones_after_it(tmp_path, monkeypatch, calls_list):
    root = make_project(tmp_path / "proj", integrations=("claude", "copilot"))
    monkeypatch.chdir(root)
    calls_list.failing["integration upgrade claude"] = 1
    result = run()
    assert result.exit_code == 1
    assert commands(calls_list) == ["self upgrade", "integration upgrade claude"]
    assert "Stopped: specify integration upgrade claude did not finish. Nothing after it ran." in _text(result)


def test_force_only_reaches_the_integration_upgrades(tmp_path, monkeypatch, calls_list):
    root = make_project(tmp_path / "proj", integrations=("claude", "copilot"))
    monkeypatch.chdir(root)
    result = run("--force")
    assert result.exit_code == 0, result.output
    assert commands(calls_list) == [
        "self upgrade",
        "integration upgrade claude --force",
        "integration upgrade copilot --force",
        "extension add capabilities --force --priority 10",
    ]


def test_without_force_integration_files_someone_edited_are_not_overwritten(project, calls_list):
    run()
    assert [argv for argv in calls_list if argv[1] == "integration"] == [
        ["specify", "integration", "upgrade", "claude"]
    ]


def test_a_bundled_extension_keeps_its_priority_and_stays_off_when_it_was_off(tmp_path, monkeypatch, calls_list):
    root = make_project(tmp_path / "proj", extensions={
        "capabilities": {"priority": 5, "enabled": False},
        "git": {"priority": 3},
    })
    monkeypatch.chdir(root)
    result = run()
    assert result.exit_code == 0, result.output
    assert commands(calls_list)[2:] == [
        "extension add capabilities --force --priority 5",
        # Adding it again turns it on, so it is turned off again.
        "extension disable capabilities",
        "extension add git --force --priority 3",
    ]


@pytest.mark.parametrize("priority", [0, -1, "5", None, True])
def test_a_priority_the_registry_cannot_use_becomes_the_default(tmp_path, monkeypatch, calls_list, priority):
    root = make_project(tmp_path / "proj", extensions={"capabilities": {"priority": priority}})
    monkeypatch.chdir(root)
    run()
    assert commands(calls_list)[-1] == "extension add capabilities --force --priority 10"


def test_a_dry_run_only_previews(project, calls_list):
    result = run("--dry-run")
    assert result.exit_code == 0, result.output
    assert commands(calls_list) == ["self upgrade --dry-run"]
    text = _text(result)
    assert "Then, with the specify that is installed, it would run: " in text
    assert "specify integration upgrade claude" in text
    assert "specify extension add capabilities --force --priority 10" in text


def test_outside_a_project_it_changes_nothing(tmp_path, monkeypatch, calls_list):
    monkeypatch.chdir(tmp_path)
    result = run()
    assert result.exit_code == 1
    assert calls_list == []
    assert "No Spec Kit project here" in _text(result)


def test_a_project_with_no_integration_record_upgrades_its_current_one(tmp_path, monkeypatch, calls_list):
    root = make_project(tmp_path / "proj", integrations=None, extensions=())
    monkeypatch.chdir(root)
    result = run()
    assert result.exit_code == 0, result.output
    assert commands(calls_list) == ["self upgrade", "integration upgrade"]


def test_the_steps_run_the_specify_that_is_installed_not_this_process(project, calls_list):
    run()
    assert {argv[0] for argv in calls_list} == {"specify"}


def test_help_says_what_it_does():
    result = CliRunner().invoke(app, ["upgrade", "--help"])
    assert result.exit_code == 0
    text = _text(result)
    assert "then update this project" in text
    assert "adds again each extension that ships with specify" in text
    assert "extension update" not in text
