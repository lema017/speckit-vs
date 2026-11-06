"""Command tests for ``specify progress doctor``."""

from __future__ import annotations

import os

import pytest
from typer.testing import CliRunner

from specify_cli import app
from specify_cli.progress import _doctor
from tests.conftest import strip_ansi

from .conftest import symlink
from .test_install import init

runner = CliRunner()


@pytest.fixture(autouse=True)
def _private_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


@pytest.fixture
def installed(tmp_path, monkeypatch):
    def install(key="claude", script="sh", options=None):
        project = tmp_path / "project"
        init(project, key, script, options)
        monkeypatch.chdir(project)
        return project

    return install


def doctor():
    result = runner.invoke(app, ["progress", "doctor"])
    return result.exit_code, strip_ansi(result.output)


def add_spec(project, tasks="## P\n\n- [ ] T001 One\n"):
    directory = project / "specs" / "001-login"
    directory.mkdir(parents=True)
    (directory / "tasks.md").write_text(tasks, encoding="utf-8")
    (project / ".specify" / "feature.json").write_text('{"feature_directory": "specs/001-login"}', encoding="utf-8")
    return directory


def test_a_fresh_project_is_fine(installed):
    installed()
    code, output = doctor()
    assert code == 0, output
    assert "ok    Engine:" in output
    assert "ok    Wrappers: Installed for bash" in output
    assert "ok    Python:" in output
    assert "ok    Current spec: None yet" in output
    assert "ok    claude: Native events are installed" in output
    assert "ok    Browser:" in output
    assert "warn" not in output
    assert "speckit:" not in output


@pytest.mark.parametrize("name", ["engine.py", "hook.py", "page.html", "index.html"])
def test_a_missing_engine_file_fails(installed, name):
    project = installed()
    (project / ".specify" / "scripts" / "progress" / name).unlink()
    code, output = doctor()
    assert code == 1
    assert "FAIL  Engine: Missing %s" % name in output
    assert "specify integration upgrade" in output


@pytest.mark.parametrize(("script", "folder", "name"), [("sh", "bash", "progress.sh"), ("py", "python", "run_step.py"), ("ps", "powershell", "run-step.ps1")])
def test_a_missing_wrapper_fails(installed, script, folder, name):
    project = installed(script=script)
    (project / ".specify" / "scripts" / folder / name).unlink()
    code, output = doctor()
    assert code == 1
    assert "FAIL  Wrappers: Missing %s" % name in output


def test_no_python_at_all_fails(installed, monkeypatch):
    installed()
    monkeypatch.setattr(_doctor, "_python_works", lambda candidate: False)
    monkeypatch.setattr(_doctor.shutil, "which", lambda name: None)
    code, output = doctor()
    assert code == 1
    assert "FAIL  Python:" in output


def test_no_python_with_the_specify_command_is_a_warning(installed, monkeypatch):
    installed()
    monkeypatch.setattr(_doctor, "_python_works", lambda candidate: False)
    monkeypatch.setattr(_doctor.shutil, "which", lambda name: "/bin/specify" if name == "specify" else None)
    code, output = doctor()
    assert code == 0
    assert "warn  Python:" in output


def test_a_python_that_does_not_run_does_not_count(monkeypatch):
    monkeypatch.setattr(_doctor.shutil, "which", lambda name: "/bin/python3")

    def broken(*args, **kwargs):
        raise OSError("no")

    monkeypatch.setattr(_doctor.subprocess, "run", broken)
    assert _doctor._python_works(["python3"]) is False


def test_the_current_spec_is_named(installed):
    add_spec(installed())
    assert "ok    Current spec: 001-login" in doctor()[1]


def test_bad_lines_in_the_log_are_a_warning(installed):
    directory = add_spec(installed())
    (directory / "progress.jsonl").write_text("not json\n", encoding="utf-8")
    (directory / ".gitattributes").write_text("progress.jsonl merge=union\n", encoding="utf-8")
    code, output = doctor()
    assert code == 0
    assert "warn  Log: 1 lines could not be understood" in output


def test_a_log_with_no_merge_rule_is_a_warning(installed):
    directory = add_spec(installed())
    (directory / "progress.jsonl").write_text("", encoding="utf-8")
    assert "merge=union" in doctor()[1]


def test_a_log_too_large_is_a_warning(installed, monkeypatch):
    from specify_cli.progress._engine import load_engine

    directory = add_spec(installed())
    (directory / "progress.jsonl").write_text("x" * 100, encoding="utf-8")
    monkeypatch.setattr(load_engine(), "MAX_LOG_BYTES", 10)
    assert "over the size limit" in doctor()[1]


def test_a_linked_log_fails(installed, tmp_path):
    directory = add_spec(installed())
    outside = tmp_path / "outside"
    outside.write_text("", encoding="utf-8")
    symlink(directory / "progress.jsonl", outside)
    code, output = doctor()
    assert code == 1
    assert "FAIL  Log:" in output


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="needs file permissions")
def test_a_spec_folder_that_cannot_be_written_fails(installed):
    directory = add_spec(installed())
    directory.chmod(0o555)
    try:
        code, output = doctor()
    finally:
        directory.chmod(0o755)
    assert code == 1
    assert "FAIL  Spec folder:" in output


def test_a_preset_that_replaced_implement_is_a_warning(installed):
    project = installed()
    (project / ".claude" / "skills" / "speckit-implement" / "SKILL.md").write_text("# Mine\n", encoding="utf-8")
    code, output = doctor()
    assert code == 0
    assert "warn  claude: Its implement command has no progress calls" in output


def test_a_harness_with_no_events_says_what_to_do_instead(installed):
    installed("amp")
    code, output = doctor()
    assert code == 0
    assert "ok    amp: No native events" in output
    assert "specify progress watch" in output


def test_events_turned_off_are_a_warning(installed):
    installed("claude", options=["--integration-options=--events false"])
    code, output = doctor()
    assert code == 0
    assert "warn  claude: Native events are off" in output


def test_codex_needs_its_hooks_approved(installed):
    installed("codex")
    assert "warn  codex: Native events are installed. Codex runs them only after you approve them with /hooks." in doctor()[1]


@pytest.mark.parametrize("key", ["copilot", "cursor-agent", "devin", "gemini", "opencode", "qwen", "tabnine", "vibe"])
def test_events_are_found_wherever_each_harness_keeps_them(installed, key):
    installed(key)
    assert "ok    %s: Native events are installed" % key in doctor()[1]


def test_browser_off_is_reported(installed):
    installed()
    assert runner.invoke(app, ["progress", "browser", "off"]).exit_code == 0
    assert "Pages stay closed" in doctor()[1]


def test_a_browser_that_cannot_open_is_reported(installed, monkeypatch):
    installed()
    monkeypatch.delenv("SPECKIT_PROGRESS_NO_BROWSER", raising=False)
    monkeypatch.setenv("SSH_CONNECTION", "1.2.3.4 1 5.6.7.8 22")
    assert "No browser can open from here" in doctor()[1]


def test_a_browser_that_can_open_is_reported(installed, monkeypatch):
    from specify_cli.progress._engine import load_engine

    installed()
    monkeypatch.delenv("SPECKIT_PROGRESS_NO_BROWSER", raising=False)
    monkeypatch.setattr(load_engine(), "can_open_browser", lambda env=None: True)
    assert "opens by itself" in doctor()[1]


def test_it_writes_nothing(installed):
    project = installed()
    before = sorted(str(path) for path in project.rglob("*"))
    doctor()
    assert sorted(str(path) for path in project.rglob("*")) == before


def test_outside_a_project_it_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["progress", "doctor"]).exit_code != 0
