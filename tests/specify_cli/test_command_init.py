"""Tests for the ``specify init`` command adapter.

`command_init.py` interpolated the project name, `--integration`/`--script`
values and paths straight into Rich markup f-strings. A name containing a
tag-shaped bracket run was therefore consumed as markup:

* ``specify init "proj [v2]"`` succeeded and created the directory, but the
  Next Steps panel printed ``cd proj`` -- a command that fails when pasted.
* ``specify init "app[/red]x"`` created the directory and then died with
  ``MarkupError``, so the user saw a traceback for a project that had in fact
  been scaffolded.

Every sibling CLI module (extensions, presets, workflows, integrations) already
escapes user-controlled display values; init.py was the outlier.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from specify_cli import app
from specify_cli.command_init import _installs_extension, _shell_quote_arg
from specify_cli.integrations import INTEGRATION_REGISTRY, get_integration
from tests.conftest import requires_bash

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def test_command_init_importable():
    mod = importlib.import_module("specify_cli.command_init")
    assert hasattr(mod, "register")
    assert callable(mod.register)


def test_transitional_commands_package_removed():
    import specify_cli

    package_root = Path(specify_cli.__file__).parent
    assert not (package_root / "commands" / "__init__.py").exists()
    assert not (package_root / "commands" / "init.py").exists()


def test_init_command_registered():
    callback_names = [
        cmd.callback.__name__ for cmd in app.registered_commands if cmd.callback
    ]
    assert callback_names == ["init", "check", "version", "upgrade", "mcp"]


def test_init_has_win32_guard():
    """init.py must assign _transient from platform check and pass it to Live."""
    import specify_cli

    init_src = Path(specify_cli.__file__).parent / "command_init.py"
    content = init_src.read_text(encoding="utf-8")
    guard = (
        r"_transient\s*=\s*sys\.platform\s*!=\s*['\"]win32['\"].*"
        r"Live\(.*transient\s*=\s*_transient"
    )
    assert re.search(guard, content, re.DOTALL)


def _strip(text: str) -> str:
    return _ANSI.sub("", text or "")


def _init(tmp_path: Path, name: str):
    """Run a fully offline, non-interactive `specify init <name>`."""
    previous = os.getcwd()
    os.chdir(tmp_path)
    try:
        return CliRunner().invoke(
            app,
            [
                "init",
                name,
                "--integration",
                "generic",
                "--integration-options",
                "--commands-dir .agent/commands",
                "--ignore-agent-tools",
                "--offline",
            ],
            catch_exceptions=True,
        )
    finally:
        os.chdir(previous)


@pytest.mark.parametrize("numbering", ["timestamp", "sequential", None])
def test_reinit_preserves_feature_numbering(tmp_path: Path, monkeypatch, numbering):
    result = _init(tmp_path, "proj")
    assert result.exit_code == 0, _strip(result.stdout)
    project = tmp_path / "proj"
    options_path = project / ".specify" / "init-options.json"
    options = json.loads(options_path.read_text(encoding="utf-8"))
    assert options["feature_numbering"] == "sequential"
    if numbering is None:
        options.pop("feature_numbering")
    else:
        options["feature_numbering"] = numbering
    options["custom_setting"] = "keep me"
    options_path.write_text(json.dumps(options), encoding="utf-8")

    monkeypatch.chdir(project)
    result = CliRunner().invoke(app, [
        "init", "--here", "--force", "--integration", "generic",
        "--integration-options", "--commands-dir .agent/commands",
        "--script", "sh", "--non-interactive", "--ignore-agent-tools", "--offline",
    ])
    assert result.exit_code == 0, _strip(result.stdout)
    updated = json.loads(options_path.read_text(encoding="utf-8"))
    assert updated["feature_numbering"] == (numbering or "sequential")
    assert updated["custom_setting"] == "keep me"
    assert updated["here"] is True


@pytest.mark.parametrize("name", ["proj [v2]", "my[bold]app"])
def test_next_steps_cd_shows_the_real_project_name(tmp_path: Path, name: str):
    """The `cd` line must name the directory that was actually created."""
    result = _init(tmp_path, name)
    assert result.exit_code == 0, _strip(result.stdout)
    assert (tmp_path / name).is_dir()

    out = _strip(result.stdout)
    cd_lines = [line for line in out.splitlines() if "cd " in line]
    assert cd_lines, out
    assert f"cd {_shell_quote_arg(name)}" in " ".join(cd_lines), cd_lines


def test_closing_tag_in_project_name_does_not_crash(tmp_path: Path):
    """A name forming a closing tag raised MarkupError *after* the project had
    been created, so init reported failure for work it had completed."""
    name = "app[/red]x"
    result = _init(tmp_path, name)

    assert result.exception is None or not isinstance(
        result.exception, Exception
    ) or "MarkupError" not in type(result.exception).__name__, (
        f"unexpected {type(result.exception).__name__}: {result.exception}"
    )
    assert result.exit_code == 0, _strip(result.stdout)
    assert (tmp_path / name).is_dir()
    assert f"cd {_shell_quote_arg(name)}" in _strip(result.stdout)


def test_invalid_integration_value_is_rendered_literally(tmp_path: Path):
    """An invalid `--integration` value is echoed back; it must not be parsed as
    markup (nor raise) when it contains a bracket run."""
    previous = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = CliRunner().invoke(
            app,
            ["init", "proj", "--integration", "nope[/red]", "--ignore-agent-tools"],
            catch_exceptions=True,
        )
    finally:
        os.chdir(previous)

    assert result.exit_code != 0
    assert "nope[/red]" in _strip(result.stdout)


def _cd_argument(stdout: str) -> str:
    """Return the argument of the printed `cd` command, verbatim.

    The line is rendered inside a Rich panel, so the trailing box-drawing
    border and its padding are stripped before the argument is compared.
    """
    marker = "Go to the project folder: cd "
    for line in _strip(stdout).splitlines():
        if marker in line:
            return line.split(marker, 1)[1].rstrip().rstrip("│").rstrip()
    raise AssertionError(f"no cd line in output:\n{stdout}")


@pytest.mark.parametrize("name", ["proj v2", "my project"])
def test_cd_line_quotes_a_name_containing_whitespace(tmp_path: Path, name: str):
    """Rich-escaping alone left `cd proj v2`, which every shell reads as two
    arguments, so the copy-pasted command did not enter the directory."""
    result = _init(tmp_path, name)
    assert result.exit_code == 0, _strip(result.stdout)
    assert (tmp_path / name).is_dir()

    printed = _cd_argument(result.stdout)
    assert printed != name, "a whitespace-bearing name must be quoted"
    assert name in printed, printed
    assert printed == _shell_quote_arg(name)


def test_ordinary_name_is_not_quoted(tmp_path: Path):
    """The common case must stay byte-identical: no gratuitous quoting."""
    result = _init(tmp_path, "my-project")
    assert result.exit_code == 0, _strip(result.stdout)
    assert _cd_argument(result.stdout) == "my-project"


@requires_bash
@pytest.mark.parametrize("name", ["proj v2", "proj [v2]", "my-project"])
def test_printed_cd_command_actually_changes_directory(tmp_path: Path, name: str):
    """Execute the printed command rather than only inspecting it.

    This is the assertion the string comparisons cannot make: the rendered
    `cd <arg>` is fed to a real shell and must land in the created directory.
    """
    result = _init(tmp_path, name)
    assert result.exit_code == 0, _strip(result.stdout)
    target = tmp_path / name
    assert target.is_dir()

    printed = _cd_argument(result.stdout)
    proc = subprocess.run(
        ["bash", "-c", f"cd {printed} && pwd"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"cd {printed!r} failed: {proc.stderr}"
    assert Path(proc.stdout.strip()).name == name, proc.stdout


def test_shell_quote_arg_is_host_appropriate():
    """The helper follows `_version._render_argv`: list2cmdline on Windows,
    shlex.quote elsewhere. Names needing no quoting round-trip unchanged."""
    assert _shell_quote_arg("my-project") == "my-project"
    quoted = _shell_quote_arg("my project")
    assert quoted != "my project"
    if os.name == "nt":
        assert quoted == '"my project"'
    else:
        assert quoted == "'my project'"


@pytest.mark.parametrize("here", [False, True])
def test_output_free_init_recommends_switching_integrations(tmp_path, monkeypatch, here):
    from specify_cli.integrations.generic import GenericIntegration

    monkeypatch.setattr(GenericIntegration, "list_command_templates", lambda self: [])
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "init", *(["--here"] if here else ["proj"]),
            "--integration", "generic",
            "--integration-options", "--commands-dir .agent/commands",
            "--ignore-agent-tools",
        ],
    )
    assert result.exit_code == 0, result.output
    output = _strip(result.output)
    assert "Next Steps" in output
    if here:
        assert "You're already in the project directory!" in output
    else:
        assert "cd proj" in output
    assert "specify integration switch <key>" in output
    assert "Switch this project to it:" in output
    assert "Add it to this project:" not in output
    assert "specify integration list" in output
    assert "Start using" not in output
    assert "speckit." not in output
    assert "Enhancement Commands" not in output
    assert "Enhancement Skills" not in output
    project = tmp_path if here else tmp_path / "proj"
    assert not (project / ".agent" / "commands").exists()


def test_rendering_init_preserves_command_guidance(tmp_path):
    result = _init(tmp_path, "proj")
    assert result.exit_code == 0, result.output
    output = _strip(result.output)
    assert "Start using slash commands" in output
    for command in ("constitution", "specify", "plan", "tasks", "implement", "converge",
                    "clarify", "clarify-deep", "progress", "analyze", "checklist"):
        assert f"/speckit.{command}" in output
        assert (tmp_path / "proj" / ".agent" / "commands" / f"speckit.{command}.md").is_file()
    assert "Enhancement Commands" in output
    assert "specify integration switch <key>" not in output


def test_init_points_to_the_lifecycle_image(tmp_path):
    result = _init(tmp_path, "proj")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "proj" / ".specify" / "lifecycle.png").is_file()
    output = " ".join(_strip(result.output).split())
    assert "Every command, in the order to run them: .specify/lifecycle.png" in output


def test_rendering_init_preserves_skill_guidance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app, ["init", "proj", "--integration", "copilot", "--ignore-agent-tools"],
    )
    assert result.exit_code == 0, result.output
    output = _strip(result.output)
    assert "Start using skills" in output
    assert "Enhancement Skills" in output
    assert "specify integration switch <key>" not in output
    for command in ("constitution", "specify", "plan", "tasks", "implement", "converge",
                    "clarify", "clarify-deep", "progress", "analyze", "checklist"):
        assert f"/speckit-{command}" in output
        assert (tmp_path / "proj" / ".github" / "skills" / f"speckit-{command}" / "SKILL.md").is_file()


def test_init_force_syncs_manifest_hash_for_preset_override(tmp_path, monkeypatch):
    """Re-init must record preset bytes and retain setup's other files (#5078)."""
    from specify_cli.integrations.manifest import IntegrationManifest

    monkeypatch.chdir(tmp_path)
    args = ["--integration", "codex", "--script", "sh", "--ignore-agent-tools", "--non-interactive"]
    result = CliRunner().invoke(app, ["init", "proj", *args])
    assert result.exit_code == 0, result.output
    project = tmp_path / "proj"
    preset = tmp_path / "tasks-preset"
    (preset / "commands").mkdir(parents=True)
    (preset / "commands/speckit.tasks.md").write_bytes(
        b"---\ndescription: Tasks override\n---\nPreset tasks body\n"
    )
    (preset / "preset.yml").write_bytes(b"""schema_version: '1.0'
preset: {id: tasks-preset, name: Tasks Preset, version: 1.0.0, description: x}
requires: {speckit_version: '>=0.1.0'}
provides:
  templates:
  - {type: command, name: speckit.tasks, file: commands/speckit.tasks.md}
""")
    monkeypatch.chdir(project)
    result = CliRunner().invoke(app, ["preset", "add", "--dev", str(preset)])
    assert result.exit_code == 0, result.output
    plan_rel = ".agents/skills/speckit-plan/SKILL.md"
    original_plan = (project / plan_rel).read_bytes()
    (project / plan_rel).write_bytes(b"User-edited skill\n")

    result = CliRunner().invoke(app, ["init", "--here", "--force", *args])
    assert result.exit_code == 0, result.output

    manifest = IntegrationManifest.load("codex", project)
    rel = ".agents/skills/speckit-tasks/SKILL.md"
    content = (project / rel).read_bytes()
    assert b"Preset tasks body" in content
    assert manifest.files[rel] == hashlib.sha256(content).hexdigest(), (
        "manifest hash must match the preset-overridden skill (#5078)"
    )
    assert (project / plan_rel).read_bytes() == original_plan, "force re-init still replaces user edits"
    assert manifest.files[plan_rel] == hashlib.sha256(original_plan).hexdigest()
    result = CliRunner().invoke(app, ["integration", "status", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["modified_managed_files"] == 0
    result = CliRunner().invoke(app, ["integration", "upgrade", "codex", "--script", "sh"])
    assert result.exit_code == 0, result.output


def test_init_force_keeps_recovered_markers(tmp_path, monkeypatch):
    """Re-init resync must not re-record files registration left unchanged (#5078)."""
    from specify_cli.integrations import get_integration
    from specify_cli.integrations.manifest import IntegrationManifest

    monkeypatch.chdir(tmp_path)
    args = ["--integration", "codex", "--script", "sh", "--ignore-agent-tools", "--non-interactive"]
    result = CliRunner().invoke(app, ["init", "proj", *args])
    assert result.exit_code == 0, result.output
    project = tmp_path / "proj"
    integration_class = type(get_integration("codex"))
    original_setup = integration_class.setup
    rel = ".agents/skills/speckit-plan/SKILL.md"

    def setup_with_recovered_file(self, project_root, manifest, *args, **kwargs):
        created = original_setup(self, project_root, manifest, *args, **kwargs)
        manifest.record_existing(rel, recovered=True)
        return created

    monkeypatch.setattr(integration_class, "setup", setup_with_recovered_file)
    monkeypatch.chdir(project)
    result = CliRunner().invoke(app, ["init", "--here", "--force", *args])

    assert result.exit_code == 0, result.output
    assert IntegrationManifest.load("codex", project).is_recovered(rel)


# ---------------------------------------------------------------- default extensions


def _default_ext_init(tmp_path: Path, *args: str, name: str = "demo", script: str = "sh"):
    """Run init in a directory, in the shape a user runs it. Returns the project and the output."""
    project = tmp_path / name
    project.mkdir(exist_ok=True)
    previous = os.getcwd()
    try:
        os.chdir(project)
        result = CliRunner().invoke(
            app,
            ["init", "--here", "--force", "--integration", "claude", "--script", script, "--ignore-agent-tools", *args],
            catch_exceptions=False,
        )
    finally:
        os.chdir(previous)
    assert result.exit_code == 0, result.output
    return project, _strip(result.output)


def _installed(project: Path) -> list[str]:
    registry = project / ".specify" / "extensions" / ".registry"
    if not registry.is_file():
        return []
    return list(json.loads(registry.read_text(encoding="utf-8")).get("extensions", {}))


def _hook_order(project: Path, event: str) -> list[str]:
    config = yaml.safe_load((project / ".specify" / "extensions.yml").read_text(encoding="utf-8"))
    return [hook["extension"] for hook in config["hooks"].get(event, [])]


def _init_for(project: Path, key: str, *args: str) -> dict[str, bytes]:
    project.mkdir()
    options = ["--integration-options", "--commands-dir .myagent/commands/"] if key == "generic" else []
    previous = os.getcwd()
    try:
        os.chdir(project)
        result = CliRunner().invoke(
            app,
            ["init", "--here", "--force", "--integration", key, "--script", "sh", "--ignore-agent-tools", *options, *args],
            catch_exceptions=False,
        )
    finally:
        os.chdir(previous)
    assert result.exit_code == 0, result.output
    return {path.relative_to(project).as_posix(): path.read_bytes() for path in project.rglob("*") if path.is_file()}


# The extension's files that do not carry its name, and the records init timestamps on every run.
_DEFAULT_ALSO_WRITES = {".specify/extensions.yml", ".specify/extensions/.registry", ".graphifyignore"}
_TIMESTAMPED = (".manifest.json", "workflow-registry.json")


@pytest.mark.parametrize("key", sorted(INTEGRATION_REGISTRY))
def test_on_every_integration_the_default_adds_only_its_own(tmp_path: Path, monkeypatch, key: str):
    """The tests of the core run without the default, so this is what covers the two together."""
    # hermes installs its skills in the home directory, the core ones too.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    core = _init_for(tmp_path / "core", key, "--no-default-extensions")
    with_default = _init_for(tmp_path / "default", key)
    changed = {path for path in core if core[path] != with_default.get(path) and not path.endswith(_TIMESTAMPED)}
    assert changed == set()
    added = set(with_default) - set(core)
    if not get_integration(key).list_command_templates():
        assert added == set()
        return
    assert {path for path in added if "capabilities" not in path and not path.startswith("graphify-out/")} == _DEFAULT_ALSO_WRITES
    in_project = [path for path in added if "capabilities" in path and not path.startswith(".specify/")]
    assert in_project or list((tmp_path / "home").rglob("*capabilities*")), "no command reached this integration"


def _files(*roots: Path) -> dict[str, bytes]:
    return {
        f"{root.name}/{path.relative_to(root).as_posix()}": path.read_bytes()
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("key", sorted(INTEGRATION_REGISTRY))
def test_on_every_integration_an_upgrade_rewrites_nothing_init_wrote(tmp_path: Path, monkeypatch, key: str):
    """init and integration upgrade both write the skills of the default: they must write the same bytes.

    init used to keep the skills the command registrar rendered, and upgrade replaced them with the
    ones the extension renders, so the first upgrade of a new project rewrote every capabilities skill.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    project = tmp_path / "proj"
    _init_for(project, key)
    after_init = _files(project, home)
    previous = os.getcwd()
    try:
        os.chdir(project)
        result = CliRunner().invoke(app, ["integration", "upgrade", key], catch_exceptions=False)
    finally:
        os.chdir(previous)
    assert result.exit_code == 0, result.output
    after_upgrade = _files(project, home)
    changed = sorted(
        path
        for path in after_init.keys() | after_upgrade.keys()
        if after_init.get(path) != after_upgrade.get(path) and not path.endswith(_TIMESTAMPED)
    )
    assert changed == []


def test_a_new_project_with_code_gets_its_first_graph(tmp_path: Path):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    project, output = _default_ext_init(tmp_path)
    assert "graph built" in output
    assert (project / "graphify-out/graph.json").is_file()
    assert (project / ".graphifyignore").is_file()


def test_a_new_project_without_code_has_no_graph_and_it_is_not_a_failure(tmp_path: Path):
    project, output = _default_ext_init(tmp_path)
    assert "no code yet" in output
    assert "not built" not in output
    assert not (project / "graphify-out/graph.json").exists()
    assert (project / ".graphifyignore").is_file()


def test_without_capabilities_nothing_is_written_for_the_graph(tmp_path: Path):
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    project, output = _default_ext_init(tmp_path, "--no-default-extensions")
    assert "not used in this project" in output
    assert not (project / ".graphifyignore").exists()
    assert not (project / "graphify-out").exists()


def test_a_graph_that_cannot_be_built_does_not_stop_init(tmp_path: Path, monkeypatch):
    import specify_cli.command_init as command_init

    monkeypatch.setattr(command_init, "build_first_graph", lambda _project: ("error", "not built: update-failed"))
    project, output = _default_ext_init(tmp_path)
    assert "not built: update-failed" in output
    assert _installed(project) == ["capabilities"]


def test_a_new_project_gets_the_default_extensions(tmp_path: Path):
    project, output = _default_ext_init(tmp_path)
    assert _installed(project) == ["capabilities"]
    assert "Install extension: capabilities" in output
    assert (project / ".claude/skills/speckit-capabilities-locate/SKILL.md").is_file()
    # Two hooks of its own before specify: the cut into slices, then the rules of the slice.
    assert _hook_order(project, "before_specify") == ["capabilities", "capabilities"]
    assert (project / ".claude/skills/speckit-capabilities-slice/SKILL.md").is_file()
    # The size of the spec is measured before its delta is sealed, and again once the tasks exist.
    assert _hook_order(project, "after_specify") == ["capabilities", "capabilities"]
    assert _hook_order(project, "after_tasks") == ["capabilities"]
    assert (project / ".claude/skills/speckit-capabilities-size/SKILL.md").is_file()
    template = (project / ".specify/extensions/capabilities/templates/spec-template.md").read_text(encoding="utf-8")
    assert "## Slice *(mandatory)*" in template and "## Capability Delta" in template


def test_the_default_runs_before_what_the_user_asks_for(tmp_path: Path):
    """Prompts run hooks in install order: fold has to run before the commit offer of git."""
    project, _ = _default_ext_init(tmp_path, "--extension", "git")
    assert _installed(project) == ["capabilities", "git"]
    assert _hook_order(project, "after_implement")[0] == "capabilities"


def test_asking_for_a_default_by_name_installs_it_once_where_it_was_asked(tmp_path: Path):
    project, output = _default_ext_init(tmp_path, "--extension", "git", "--extension", "capabilities")
    assert _installed(project) == ["git", "capabilities"]
    assert output.count("Install extension: capabilities") == 1


def test_asking_for_a_default_by_its_directory_replaces_it(tmp_path: Path):
    """The default would install first, and the copy that was asked for would fail as already installed."""
    source = Path(__file__).resolve().parents[2] / "extensions" / "capabilities"
    project, output = _default_ext_init(tmp_path, "--extension", str(source))
    assert _installed(project) == ["capabilities"]
    assert "already installed" not in output


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("capabilities", True),
        ("git", False),
        ("https://example.invalid/releases/capabilities-1.0.0.zip", True),
        ("https://example.invalid/capabilities", True),
        ("https://example.invalid/other-1.0.0.zip", False),
        ("./does-not-exist", False),
    ],
)
def test_what_counts_as_asking_for_an_extension(spec: str, expected: bool):
    assert _installs_extension(spec, "capabilities") is expected


def test_a_workflow_run_directory_does_not_make_a_project_existing(tmp_path: Path):
    """The engine creates ``.specify/workflows/runs/`` before its init step runs."""
    (tmp_path / "demo" / ".specify" / "workflows" / "runs").mkdir(parents=True)
    project, _ = _default_ext_init(tmp_path)
    assert _installed(project) == ["capabilities"]


def test_no_default_extensions_leaves_the_core_project(tmp_path: Path):
    project, output = _default_ext_init(tmp_path, "--no-default-extensions")
    assert _installed(project) == []
    assert "capabilities" not in output
    assert not (project / ".specify/extensions/capabilities").exists()
    assert not (project / ".claude/skills/speckit-capabilities-locate").exists()
    assert "Capability Delta" not in (project / ".specify/templates/spec-template.md").read_text(encoding="utf-8")


def test_an_explicit_extension_wins_over_no_default_extensions(tmp_path: Path):
    project, _ = _default_ext_init(tmp_path, "--no-default-extensions", "--extension", "capabilities")
    assert _installed(project) == ["capabilities"]


def test_removing_a_default_lasts_through_a_re_init(tmp_path: Path):
    project, _ = _default_ext_init(tmp_path)
    previous = os.getcwd()
    try:
        os.chdir(project)
        removed = CliRunner().invoke(app, ["extension", "remove", "capabilities", "--force"], catch_exceptions=False)
    finally:
        os.chdir(previous)
    assert removed.exit_code == 0, removed.output
    assert _installed(project) == []

    project, output = _default_ext_init(tmp_path)
    assert _installed(project) == []
    assert "Install extension: capabilities" not in output


def test_an_existing_project_is_not_given_a_default_it_never_had(tmp_path: Path):
    project, _ = _default_ext_init(tmp_path, "--no-default-extensions")
    project, _ = _default_ext_init(tmp_path)
    assert _installed(project) == []


def test_a_re_init_keeps_the_default_of_a_project_that_has_it(tmp_path: Path):
    project, _ = _default_ext_init(tmp_path)
    project, _ = _default_ext_init(tmp_path)
    assert _installed(project) == ["capabilities"]


def test_powershell_does_not_get_a_default_validated_only_with_python3(tmp_path: Path):
    """The prompts call ``python3``, which a Windows machine may not have. Nothing here ran on Windows."""
    project, output = _default_ext_init(tmp_path, script="ps")
    assert _installed(project) == []
    assert "--extension capabilities" in output.replace("\n", " ")

    project, _ = _default_ext_init(tmp_path, "--extension", "capabilities", name="asked", script="ps")
    assert _installed(project) == ["capabilities"]


@pytest.mark.parametrize("args", [(), ("--no-default-extensions",)])
def test_the_powershell_note_is_for_a_new_project_that_did_not_opt_out(tmp_path: Path, args: tuple[str, ...]):
    _, first = _default_ext_init(tmp_path, *args, script="ps")
    assert ("--extension capabilities" in first.replace("\n", " ")) == (not args)
    _, again = _default_ext_init(tmp_path, *args, script="ps")
    assert "--extension capabilities" not in again.replace("\n", " ")


def test_the_powershell_note_is_not_for_a_project_that_has_it(tmp_path: Path):
    source = Path(__file__).resolve().parents[2] / "extensions" / "capabilities"
    project, output = _default_ext_init(tmp_path, "--extension", str(source), script="ps")
    assert _installed(project) == ["capabilities"]
    assert "not installed with PowerShell" not in output.replace("\n", " ")
    _, again = _default_ext_init(tmp_path, script="ps")
    assert "not installed with PowerShell" not in again.replace("\n", " ")


def test_an_integration_with_no_commands_does_not_get_a_default(tmp_path: Path):
    """Nothing could invoke its commands, and trying would show a failure on a healthy init."""
    project = tmp_path / "none-project"
    project.mkdir()
    previous = os.getcwd()
    try:
        os.chdir(project)
        result = CliRunner().invoke(app, ["init", "--here", "--force", "--integration", "none", "--script", "sh", "--ignore-agent-tools"], catch_exceptions=False)
    finally:
        os.chdir(previous)
    assert result.exit_code == 0, result.output
    assert _installed(project) == []
    assert "capabilities" not in _strip(result.output)


def test_a_default_that_fails_to_install_does_not_stop_init(tmp_path: Path, monkeypatch):
    import specify_cli.command_init as command_init

    def fail(*_args, **_kwargs):
        raise ValueError("no bundle here")

    monkeypatch.setattr(command_init, "_install_extension_during_init", fail)
    project, output = _default_ext_init(tmp_path)
    assert _installed(project) == []
    assert "no bundle here" in output
    assert (project / ".specify/templates/spec-template.md").is_file()
