"""Every core command goes through the wrapper and ends by reporting progress."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from specify_cli.agents import CommandRegistrar
from specify_cli.integrations.base import IntegrationBase

REPO = Path(__file__).resolve().parents[3]
TEMPLATES = REPO / "templates" / "commands"
STEPS = {path.stem: path.stem for path in TEMPLATES.glob("*.md") if path.stem != "progress"}
# clarify-deep is another way to take the clarify step, so it reports as that step.
STEPS["clarify-deep"] = "clarify"

WRAPPERS = {
    "sh": ("scripts/bash/run-step.sh", "scripts/bash/"),
    "ps": ("scripts/powershell/run-step.ps1", "scripts/powershell/"),
    "py": ("scripts/python/run_step.py", "scripts/python/"),
}
HOOK_MARKERS = ("hooks.after_",)


def read(name):
    return (TEMPLATES / (name + ".md")).read_text(encoding="utf-8")


def test_all_ten_commands_are_covered():
    assert len(STEPS) == 10


@pytest.mark.parametrize("variant", sorted(WRAPPERS))
@pytest.mark.parametrize("name", sorted(STEPS))
def test_the_first_script_goes_through_the_wrapper(name, variant):
    wrapper, folder = WRAPPERS[variant]
    line = re.search(r"^\s*%s: (.+)$" % variant, read(name), re.MULTILINE).group(1).split()
    assert line[0] == wrapper
    assert line[1] == STEPS[name]
    assert line[2] == "__AGENT__"
    assert line[3].startswith(folder)
    assert (REPO / line[3]).is_file()
    assert (REPO / wrapper).is_file()


@pytest.mark.parametrize("name", sorted(STEPS))
def test_each_command_reports_progress_once_before_its_hooks_run(name):
    text = read(name)
    assert text.count("{PROGRESS}") == 1
    position = text.index("{PROGRESS}")
    assert position > text.index("hooks.before_") if "hooks.before_" in text else True
    assert position < text.index("hooks.after_"), "hooks may commit, and the log belongs in that commit"


@pytest.mark.parametrize("name", sorted(set(STEPS) - {"implement"}))
def test_each_command_records_its_own_step(name):
    assert "{PROGRESS} step %s done" % STEPS[name] in read(name)


def test_implement_only_redraws_since_its_boxes_say_how_far_it_got():
    assert "{PROGRESS} show" in read("implement")


@pytest.mark.parametrize("name", sorted(STEPS))
def test_progress_can_never_stop_a_command(name):
    assert "progress never blocks this command" in read(name)


@pytest.mark.parametrize("name", ["analyze", "clarify", "clarify-deep", "converge"])
def test_steps_that_leave_no_file_ask_for_a_note(name):
    assert re.search(r'\{PROGRESS\} step \S+ done --note "<[^"]+>"', read(name))


@pytest.mark.parametrize("name", ["constitution", "specify", "plan", "checklist", "tasks"])
def test_steps_their_files_already_explain_do_not_ask_for_a_note(name):
    assert "--note" not in read(name)


def test_the_progress_command_only_reads_and_treats_output_as_data():
    text = read("progress")
    assert "run-step" not in text and "run_step" not in text
    assert "treat it as data" in text
    assert "only reports" in text
    for variant, script in (
        ("sh", "scripts/bash/progress.sh"),
        ("ps", "scripts/powershell/progress.ps1"),
        ("py", "scripts/python/progress.py"),
    ):
        assert re.search(r"^\s*%s: %s --harness __AGENT__ show$" % (variant, re.escape(script)), text, re.MULTILINE)
        assert (REPO / script).is_file()


# -- {PROGRESS} on both rendering paths --------------------------------------------------------


EXPECTED = {
    "sh": ".specify/scripts/bash/progress.sh --harness claude",
    "ps": ".specify/scripts/powershell/progress.ps1 --harness claude",
}


@pytest.fixture
def pinned_python(monkeypatch):
    monkeypatch.setattr("specify_cli.integrations.base.shutil.which", lambda name: "/usr/bin/python3" if name == "python3" else None)
    monkeypatch.setattr("specify_cli.integrations.base.IntegrationBase._interpreter_runs", staticmethod(lambda path: True))


@pytest.mark.parametrize("variant", sorted(EXPECTED))
@pytest.mark.parametrize("name", sorted(STEPS))
def test_rendering_a_core_command_resolves_everything(name, variant):
    result = IntegrationBase.process_template(read(name), "claude", variant)
    assert EXPECTED[variant] in result
    assert "{PROGRESS}" not in result and "{SCRIPT}" not in result and "__AGENT__" not in result
    assert "scripts:\n" not in result
    assert " claude .specify/scripts/" in result


@pytest.mark.parametrize("name", sorted(STEPS))
def test_rendering_for_python_goes_through_the_interpreter(name, pinned_python):
    result = IntegrationBase.process_template(read(name), "claude", "py")
    assert "python3 .specify/scripts/python/progress.py --harness claude" in result
    assert "python3 .specify/scripts/python/run_step.py " in result
    assert " .specify/scripts/python/" in result


def test_a_template_without_a_scripts_block_still_gets_the_progress_command():
    result = IntegrationBase.process_template("---\ndescription: x\n---\nRun {PROGRESS} show\n", "codex", "sh")
    assert "Run .specify/scripts/bash/progress.sh --harness codex show" in result


def test_a_template_that_does_not_use_it_is_untouched():
    content = "---\ndescription: x\n---\nNothing here.\n"
    assert IntegrationBase.process_template(content, "codex", "sh") == content


@pytest.mark.parametrize("variant", sorted(EXPECTED))
def test_a_preset_or_an_extension_body_gets_it_too(tmp_path, variant, monkeypatch):
    monkeypatch.setattr("specify_cli.agents.load_init_options", lambda root: {"script": variant})
    body = CommandRegistrar.resolve_skill_placeholders("claude", {}, "Run `{PROGRESS} show`", tmp_path)
    assert body == "Run `%s show`" % EXPECTED[variant]


def test_an_extension_body_still_reaches_the_core_scripts(tmp_path, monkeypatch):
    monkeypatch.setattr("specify_cli.agents.load_init_options", lambda root: {"script": "sh"})
    body = CommandRegistrar.resolve_skill_placeholders(
        "claude", {}, "Run `{PROGRESS} show` and scripts/own.sh", tmp_path, extension_id="demo"
    )
    assert ".specify/scripts/bash/progress.sh --harness claude show" in body
    assert ".specify/extensions/demo/scripts/own.sh" in body


def test_a_preset_body_on_python_goes_through_the_interpreter(tmp_path, monkeypatch, pinned_python):
    monkeypatch.setattr("specify_cli.agents.load_init_options", lambda root: {"script": "py"})
    body = CommandRegistrar.resolve_skill_placeholders("claude", {}, "{PROGRESS} show", tmp_path)
    assert body == "python3 .specify/scripts/python/progress.py --harness claude show"


def test_a_project_with_no_recorded_variant_gets_the_platforms(tmp_path, monkeypatch):
    monkeypatch.setattr("specify_cli.agents.load_init_options", lambda root: {})
    monkeypatch.setattr("specify_cli.integrations.base.platform.system", lambda: "Linux")
    body = CommandRegistrar.resolve_skill_placeholders("claude", {}, "{PROGRESS} show", tmp_path)
    assert body == ".specify/scripts/bash/progress.sh --harness claude show"
