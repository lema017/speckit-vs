"""The progress view is mandatory: every integration, every script variant, every format."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from specify_cli import app
from specify_cli.events import progress_hook_defaults, resolve_and_run_event_command
from specify_cli.integrations import INTEGRATION_REGISTRY

REPO = Path(__file__).resolve().parents[3]
runner = CliRunner()

KEYS = sorted(INTEGRATION_REGISTRY)
WRAPPER_FILES = {
    "sh": ("bash", ("progress.sh", "run-step.sh")),
    "ps": ("powershell", ("progress.ps1", "run-step.ps1")),
    "py": ("python", ("progress.py", "run_step.py")),
}
PROGRESS_SCRIPT = {
    "sh": ".specify/scripts/bash/progress.sh --harness %s",
    "ps": ".specify/scripts/powershell/progress.ps1 --harness %s",
    "py": ".specify/scripts/python/progress.py --harness %s",
}
# The options that change how an integration writes its commands.
OPTIONS = {
    "generic": ["--integration-options=--commands-dir .myagent/commands"],
}
VARIANT_OPTIONS = [
    ("bob", "--legacy-commands"),
    ("copilot", "--commands"),
    ("generic", "--commands-dir .myagent/skills --skills"),
]


@pytest.fixture(autouse=True)
def _private_home(tmp_path, monkeypatch):
    """hermes writes to the home directory. It must never be the real one."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


def init(project: Path, key: str, script: str, options: list[str] | None = None):
    project.mkdir(exist_ok=True)
    previous = os.getcwd()
    os.chdir(project)
    try:
        result = runner.invoke(
            app,
            [
                "init", "--here", "--force", "--non-interactive", "--ignore-agent-tools",
                "--no-default-extensions", "--integration", key, "--script", script,
                *(OPTIONS.get(key, []) if options is None else options),
            ],
            catch_exceptions=False,
        )
    finally:
        os.chdir(previous)
    assert result.exit_code == 0, result.output
    return result


def installed_commands(project: Path, key: str) -> list[Path]:
    """Every file the integration wrote that holds a core command."""
    manifest = json.loads((project / ".specify" / "integrations" / ("%s.manifest.json" % key)).read_text(encoding="utf-8"))
    home = Path(os.environ["HOME"])
    found = []
    for name in manifest["files"]:
        path = Path(name)
        for base in (project, home):
            candidate = path if path.is_absolute() else base / path
            if candidate.is_file():
                found.append(candidate)
                break
    return [path for path in found if "speckit" in path.as_posix() and "speckit.manifest" not in path.name]


def command_files(project: Path, key: str) -> list[Path]:
    """Skip hook settings and the like: only files that are commands."""
    if key == "hermes":
        # Its skills live in the home directory, outside the project and its manifest.
        return sorted((Path(os.environ["HOME"]) / ".hermes" / "skills").glob("speckit-*/SKILL.md"))
    suffixes = {".md", ".mdc", ".toml", ".yaml", ".yml"}
    return [path for path in installed_commands(project, key) if path.suffix in suffixes]


def test_all_43_integrations_are_tested():
    assert len(KEYS) == 43


@pytest.mark.parametrize("script", sorted(WRAPPER_FILES))
@pytest.mark.parametrize("key", KEYS)
def test_every_integration_gets_the_engine_with_every_script_variant(tmp_path, key, script):
    project = tmp_path / "project"
    init(project, key, script)
    scripts = project / ".specify" / "scripts"
    for name in ("engine.py", "page.html", "index.html", "design.html"):
        assert (scripts / "progress" / name).is_file(), name
        assert (scripts / "progress" / name).read_bytes().replace(b"\r\n", b"\n") == (
            REPO / "scripts" / "progress" / name
        ).read_bytes().replace(b"\r\n", b"\n"), "%s must arrive unchanged" % name
    folder, names = WRAPPER_FILES[script]
    for name in names:
        assert (scripts / folder / name).is_file(), name
    manifest = json.loads((project / ".specify" / "integrations" / "speckit.manifest.json").read_text(encoding="utf-8"))
    assert ".specify/scripts/progress/engine.py" in manifest["files"]


@pytest.mark.parametrize("script", sorted(WRAPPER_FILES))
@pytest.mark.parametrize("key", [key for key in KEYS if key != "none"])
def test_every_command_of_every_integration_has_it_resolved(tmp_path, key, script):
    project = tmp_path / "project"
    init(project, key, script)
    files = command_files(project, key)
    assert files, "no command files found for %s" % key
    expected = PROGRESS_SCRIPT[script] % key
    wrapper_seen = 0
    report_seen = 0
    progress_command_seen = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "{PROGRESS}" not in text, path
        assert "__AGENT__" not in text, path
        assert "{SCRIPT}" not in text, path
        # Copilot's prompt files only point at its agent files.
        if expected in text:
            report_seen += 1
        if ("run-step" in text or "run_step" in text) and (" %s .specify/scripts/" % key) in text:
            wrapper_seen += 1
        if "progress" in path.name or "progress" in path.parent.name:
            progress_command_seen += 1
    assert wrapper_seen == 10, "%s: wrapper in %d commands" % (key, wrapper_seen)
    assert report_seen >= 11, "%s: progress command in %d commands" % (key, report_seen)
    assert progress_command_seen >= 1, "%s: /speckit.progress is missing" % key


@pytest.mark.parametrize(("key", "options"), VARIANT_OPTIONS)
@pytest.mark.parametrize("script", sorted(WRAPPER_FILES))
def test_the_other_formats_of_an_integration_have_it_resolved_too(tmp_path, key, options, script):
    project = tmp_path / "project"
    init(project, key, script, ["--integration-options=%s" % options])
    files = command_files(project, key)
    assert files
    expected = PROGRESS_SCRIPT[script] % key
    assert sum(1 for path in files if expected in path.read_text(encoding="utf-8")) >= 11
    for path in files:
        assert "{PROGRESS}" not in path.read_text(encoding="utf-8")


def test_the_integration_without_commands_still_gets_the_engine_and_can_draw(tmp_path, monkeypatch):
    project = tmp_path / "project"
    init(project, "none", "sh")
    assert (project / ".specify" / "scripts" / "progress" / "engine.py").is_file()
    monkeypatch.chdir(project)
    assert runner.invoke(app, ["progress", "render"]).exit_code == 0
    assert (project / ".specify" / "progress" / "index.html").is_file()


@pytest.mark.parametrize("key", [key for key in KEYS if INTEGRATION_REGISTRY[key].__class__.__mro__[1].__name__ == "TomlIntegration"])
def test_toml_commands_still_parse(tmp_path, key):
    project = tmp_path / "project"
    init(project, key, "sh")
    parsed = 0
    for path in command_files(project, key):
        if path.suffix == ".toml":
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            assert "{PROGRESS}" not in data["prompt"]
            parsed += 1
    assert parsed == 11


def test_yaml_commands_still_parse(tmp_path):
    project = tmp_path / "project"
    init(project, "goose", "sh")
    parsed = 0
    for path in command_files(project, "goose"):
        if path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            assert "progress.sh --harness goose" in data["prompt"]
            parsed += 1
    assert parsed == 11


@pytest.mark.parametrize(
    ("key", "relative"),
    [
        ("claude", ".claude/skills/speckit-progress/SKILL.md"),
        ("codex", ".agents/skills/speckit-progress/SKILL.md"),
        ("gemini", ".gemini/commands/speckit.progress.toml"),
        ("opencode", ".opencode/commands/speckit.progress.md"),
    ],
)
def test_the_progress_command_lands_where_each_format_keeps_commands(tmp_path, key, relative):
    project = tmp_path / "project"
    init(project, key, "sh")
    text = (project / relative).read_text(encoding="utf-8")
    assert ".specify/scripts/bash/progress.sh --harness %s show" % key in text


def test_removing_the_integration_leaves_the_engine_in_place(tmp_path, monkeypatch):
    project = tmp_path / "project"
    init(project, "claude", "sh")
    monkeypatch.chdir(project)
    assert runner.invoke(app, ["integration", "uninstall", "claude"]).exit_code == 0
    assert (project / ".specify" / "scripts" / "progress" / "engine.py").is_file()
    assert not (project / ".claude" / "skills" / "speckit-progress").exists()


def test_a_project_from_before_this_feature_gets_it_with_an_upgrade(tmp_path, monkeypatch):
    project = tmp_path / "project"
    init(project, "claude", "sh")
    scripts = project / ".specify" / "scripts"
    for path in (scripts / "bash" / "progress.sh", scripts / "bash" / "run-step.sh"):
        path.unlink()
    for path in (scripts / "progress").iterdir():
        path.unlink()
    (scripts / "progress").rmdir()
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["integration", "upgrade", "claude", "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert (scripts / "progress" / "engine.py").is_file()
    assert (scripts / "bash" / "run-step.sh").is_file()
    assert "run-step.sh analyze claude" in (project / ".claude" / "skills" / "speckit-analyze" / "SKILL.md").read_text(encoding="utf-8")


def test_a_customized_engine_is_preserved_on_upgrade(tmp_path, monkeypatch):
    project = tmp_path / "project"
    init(project, "claude", "sh")
    engine = project / ".specify" / "scripts" / "progress" / "engine.py"
    engine.write_text("# mine\n", encoding="utf-8")
    monkeypatch.chdir(project)
    assert runner.invoke(app, ["integration", "upgrade", "claude"], catch_exceptions=False).exit_code == 0
    assert engine.read_text(encoding="utf-8") == "# mine\n"


EVENT_VARIANTS = [
    variant
    for variant, available in (
        ("sh", os.name != "nt" or shutil.which("bash")),
        ("py", True),
        ("ps", shutil.which("pwsh") or shutil.which("powershell")),
    )
    if available
]


def ready_spec(project: Path) -> Path:
    feature = project / "specs" / "001-login"
    feature.mkdir(parents=True)
    (feature / "spec.md").write_text("# Feature Specification: Login\n", encoding="utf-8")
    (feature / "plan.md").write_text("# Implementation Plan: Login\n", encoding="utf-8")
    (feature / "tasks.md").write_text("# Tasks: Login\n\n- [ ] T001 Build\n", encoding="utf-8")
    (project / ".specify" / "feature.json").write_text(json.dumps({"feature_directory": "specs/001-login"}), encoding="utf-8")
    return feature


# The dispatcher passes the first path as Windows writes it, backslashes included, and anchors
# nothing after it. Only a run on Windows exercises the backslashes.
@pytest.mark.parametrize("script", EVENT_VARIANTS)
def test_a_core_command_still_works_as_an_event_handler(tmp_path, script, capsys):
    project = tmp_path / "project"
    init(project, "claude", script)
    feature = ready_spec(project)
    capsys.readouterr()
    code = resolve_and_run_event_command("speckit.analyze", "session_start", "{}", project)
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "FEATURE_DIR" in captured.out
    event = json.loads((feature / "progress.jsonl").read_text(encoding="utf-8"))
    assert (event["step"], event["status"]) == ("analyze", "in_progress")


@pytest.mark.parametrize("script", EVENT_VARIANTS)
def test_the_progress_command_works_as_an_event_handler(tmp_path, script, capsys):
    project = tmp_path / "project"
    init(project, "claude", script)
    ready_spec(project)
    capsys.readouterr()
    code = resolve_and_run_event_command("speckit.progress", "session_start", "{}", project)
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "Tasks: 0 of 1 done" in captured.out
    assert (project / ".specify" / "progress" / "001-login.html").is_file()


def test_nothing_is_drawn_or_recorded_by_installing(tmp_path):
    project = tmp_path / "project"
    init(project, "claude", "sh")
    assert not (project / ".specify" / "progress").exists()
    assert not list(project.rglob("progress.jsonl"))


PROTOCOL_TASKS = "# Tasks\n\n## Phase 1\n\n" + "".join("- [ ] T%03d Task %d\n" % (n, n) for n in range(1, 13))


@pytest.mark.skipif(os.name == "nt", reason="runs the POSIX line from the rendered command")
def test_the_lines_in_the_rendered_implement_command_really_run(tmp_path):
    """Word for word what the model reads, from an installed project."""
    project = tmp_path / "project"
    init(project, "claude", "sh")
    directory = project / "specs" / "001-login"
    directory.mkdir(parents=True)
    (directory / "tasks.md").write_text(PROTOCOL_TASKS, encoding="utf-8")
    (project / ".specify" / "feature.json").write_text(json.dumps({"feature_directory": "specs/001-login"}), encoding="utf-8")
    text = (project / ".claude" / "skills" / "speckit-implement" / "SKILL.md").read_text(encoding="utf-8")
    lines = re.findall(r"^\s*(\.specify/scripts/bash/progress\.sh --harness claude (?:start|done|block|fail|skip|note) .+)$", text, re.MULTILINE)
    assert len(lines) == 6
    env = dict(os.environ, SPECKIT_PROGRESS_NO_BROWSER="1")
    for line in lines:
        result = subprocess.run(["bash", "-c", line], cwd=project, env=env, capture_output=True, text=True, check=False, timeout=60)
        assert result.returncode == 0, (line, result.stderr)
    log = [json.loads(row) for row in (directory / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(e["task"], e["status"]) for e in log] == [
        ("T011", "in_progress"),
        ("T011", "done"),
        ("T012", "in_progress"),
        ("T012", "blocked"),
        ("T009", "failed"),
        ("T010", "skipped"),
        ("T011", "note"),
    ]
    assert all(e["actor"]["harness"] == "claude" for e in log)
    assert "- [X] T011" in (directory / "tasks.md").read_text(encoding="utf-8")


@pytest.mark.skipif(os.name == "nt", reason="execute bits are a POSIX concern")
def test_the_bash_wrappers_can_be_executed(tmp_path):
    project = tmp_path / "project"
    init(project, "claude", "sh")
    for name in ("progress.sh", "run-step.sh"):
        assert os.access(project / ".specify" / "scripts" / "bash" / name, os.X_OK), name


def test_init_mentions_the_progress_command(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    previous = os.getcwd()
    os.chdir(project)
    try:
        result = runner.invoke(
            app,
            ["init", "--here", "--force", "--non-interactive", "--ignore-agent-tools", "--no-default-extensions", "--integration", "claude", "--script", "sh"],
            catch_exceptions=False,
        )
    finally:
        os.chdir(previous)
    assert "speckit-progress" in result.output


# -- Native events: on by default where a harness has them ---------------------------------------

EVENT_KEYS = sorted(key for key, integration in INTEGRATION_REGISTRY.items() if integration.supports_events())
HOOK_FILES = {key: INTEGRATION_REGISTRY[key].events_config_file for key in EVENT_KEYS}
HOOK_FILES["opencode"] = ".opencode/plugin/speckit-events.ts"


def hook_text(project: Path, key: str) -> str:
    return (project / HOOK_FILES[key]).read_text(encoding="utf-8")


def test_the_ten_harnesses_with_events_are_all_here():
    assert EVENT_KEYS == ["claude", "codex", "copilot", "cursor-agent", "devin", "gemini", "opencode", "qwen", "tabnine", "vibe"]


@pytest.mark.parametrize("key", EVENT_KEYS)
def test_every_harness_with_events_gets_the_hook_on_each_event_it_has(tmp_path, key):
    project = tmp_path / "project"
    init(project, key, "sh")
    text = hook_text(project, key)
    natives = INTEGRATION_REGISTRY[key].CANONICAL_TO_NATIVE
    assert ("speckit.progress-hook." + key) in text
    for event in ("session_start", "post_tool_use", "stop"):
        if event in natives:
            assert natives[event] in text, event
    assert (project / ".specify" / "events.py").is_file()


@pytest.mark.parametrize(("key", "absent"), [("vibe", "session_start"), ("opencode", "stop")])
def test_an_event_a_harness_does_not_have_is_left_out_without_a_warning(tmp_path, key, absent):
    assert absent not in INTEGRATION_REGISTRY[key].CANONICAL_TO_NATIVE
    assert absent not in progress_hook_defaults(key)
    assert "does not support" not in init(tmp_path / "project", key, "sh").output


@pytest.mark.parametrize("key", [key for key in KEYS if key not in EVENT_KEYS and key != "none"])
def test_a_harness_without_events_gets_no_hook_and_no_dispatcher(tmp_path, key):
    project = tmp_path / "project"
    init(project, key, "sh")
    assert not (project / ".specify" / "events.py").exists()


@pytest.mark.parametrize("key", EVENT_KEYS)
def test_events_can_be_turned_off(tmp_path, key):
    project = tmp_path / "project"
    init(project, key, "sh", ["--integration-options=--events false"])
    path = project / HOOK_FILES[key]
    assert not path.exists() or "speckit.progress-hook" not in path.read_text(encoding="utf-8")
    assert not (project / ".specify" / "events.py").exists()


def test_a_file_of_your_own_replaces_them(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".specify").mkdir()
    (project / ".specify" / "integration-events.yml").write_text("integrations:\n  claude:\n    events: {}\n", encoding="utf-8")
    init(project, "claude", "sh")
    path = project / ".claude" / "settings.json"
    assert not path.exists() or "speckit.progress-hook" not in path.read_text(encoding="utf-8")


def test_settings_you_already_have_are_kept(tmp_path):
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}}), encoding="utf-8")
    init(project, "claude", "sh")
    settings = json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["permissions"] == {"allow": ["Bash(ls)"]}
    assert "PostToolUse" in settings["hooks"]


@pytest.mark.parametrize("key", EVENT_KEYS)
def test_removing_the_integration_removes_the_hook(tmp_path, monkeypatch, key):
    project = tmp_path / "project"
    init(project, key, "sh")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["integration", "uninstall", key, "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    path = project / HOOK_FILES[key]
    assert not path.exists() or "speckit.progress-hook" not in path.read_text(encoding="utf-8")
    assert not (project / ".specify" / "events.py").exists()


def test_a_project_from_before_this_feature_gets_the_hook_with_an_upgrade(tmp_path, monkeypatch):
    project = tmp_path / "project"
    init(project, "claude", "sh", ["--integration-options=--events false"])
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["integration", "upgrade", "claude", "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output


@pytest.mark.skipif(os.name == "nt", reason="runs the POSIX command from the config")
def test_the_command_in_the_config_really_draws_the_page(tmp_path):
    """The line Claude Code would run, with the shell expanding its variable."""
    project = tmp_path / "project"
    init(project, "claude", "sh")
    directory = project / "specs" / "001-login"
    directory.mkdir(parents=True)
    (directory / "tasks.md").write_text("## P\n\n- [ ] T001 One\n", encoding="utf-8")
    (project / ".specify" / "feature.json").write_text(json.dumps({"feature_directory": "specs/001-login"}), encoding="utf-8")
    settings = json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))
    command = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project), SPECKIT_PROGRESS_NO_BROWSER="1")
    result = subprocess.run(["bash", "-c", command], input="{}", cwd=project, env=env, capture_output=True, text=True, check=False, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("Spec Kit progress for 001-login: 0 of 1 tasks done.")
    assert (project / ".specify" / "progress" / "001-login.html").is_file()


def test_two_harnesses_share_the_dispatcher_until_the_last_one_leaves(tmp_path, monkeypatch):
    project = tmp_path / "project"
    init(project, "claude", "sh")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["integration", "install", "codex", "--script", "sh"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    dispatcher = project / ".specify" / "events.py"
    assert "speckit.progress-hook.codex" in (project / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "speckit.progress-hook.claude" in (project / ".claude" / "settings.json").read_text(encoding="utf-8")

    result = runner.invoke(app, ["integration", "uninstall", "claude"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert dispatcher.is_file()
    assert "speckit.progress-hook.codex" in (project / ".codex" / "config.toml").read_text(encoding="utf-8")

    result = runner.invoke(app, ["integration", "uninstall", "codex"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert not dispatcher.exists()


@pytest.mark.parametrize("key", EVENT_KEYS)
def test_removing_the_integration_leaves_no_empty_folder(tmp_path, monkeypatch, key):
    project = tmp_path / "project"
    init(project, key, "sh")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["integration", "uninstall", key, "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    outside = [path for path in project.iterdir() if path.name != ".specify"]
    assert [str(path.relative_to(project)) for path in outside] == []


def test_a_folder_that_holds_something_else_stays_when_the_hook_goes(tmp_path, monkeypatch):
    project = tmp_path / "project"
    init(project, "copilot", "sh")
    mine = project / ".github" / "hooks" / "mine.json"
    mine.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["integration", "uninstall", "copilot", "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert mine.is_file()
    assert not (project / ".github" / "hooks" / "speckit.json").exists()
