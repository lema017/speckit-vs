"""The bundled extension: manifest, packaging, template composition and a real install."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from specify_cli import _locate_bundled_extension
from specify_cli.extensions import ExtensionManifest
from tests.conftest import requires_bash

from .conftest import EXT_DIR, MARK, ROOT, SCRIPT, modified, spec_text

COMMANDS = {"context", "review", "fold", "check"}
OLD_SENTENCE = "If a `before_specify` hook ran successfully in the Pre-Execution Checks above, it will have created/switched to a git branch"
NEW_SENTENCE = "If a `before_specify` hook's output contains `BRANCH_NAME` and `FEATURE_NUM`, that hook created or switched to a git branch."
NO_INVENT = "A hook that does not output them created no branch: do not infer or invent these values."


def manifest_data():
    return yaml.safe_load((EXT_DIR / "extension.yml").read_text(encoding="utf-8"))


def test_manifest_is_valid_and_lists_every_command():
    manifest = ExtensionManifest(EXT_DIR / "extension.yml")
    assert manifest.id == "capabilities"
    provided = {command["name"] for command in manifest_data()["provides"]["commands"]}
    assert provided == {"speckit.capabilities.%s" % name for name in COMMANDS}
    for command in manifest_data()["provides"]["commands"]:
        assert (EXT_DIR / command["file"]).is_file()


def test_hooks_are_mandatory_and_unconditional():
    hooks = manifest_data()["hooks"]
    assert hooks["before_specify"]["command"] == "speckit.capabilities.context"
    assert hooks["after_specify"]["command"] == "speckit.capabilities.review"
    assert hooks["before_plan"]["command"] == "speckit.capabilities.review"
    assert hooks["after_implement"]["command"] == "speckit.capabilities.fold"
    assert hooks["after_converge"]["command"] == "speckit.capabilities.fold"
    for hook in hooks.values():
        assert hook["optional"] is False
        assert "condition" not in hook, "prompts skip hooks that have a condition"


def test_catalog_and_packaging_agree_with_the_manifest():
    catalog = json.loads((ROOT / "extensions" / "catalog.json").read_text(encoding="utf-8"))
    entry = catalog["extensions"]["capabilities"]
    assert entry["bundled"] is True
    assert entry["version"] == manifest_data()["extension"]["version"]
    assert '"extensions/capabilities" = "specify_cli/core_pack/extensions/capabilities"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert _locate_bundled_extension("capabilities") == EXT_DIR


def test_extension_template_is_the_core_template_plus_the_addendum():
    core = (ROOT / "templates" / "spec-template.md").read_text(encoding="utf-8")
    own = (EXT_DIR / "templates" / "spec-template.md").read_text(encoding="utf-8")
    head, _, addendum = own.partition("## Capability Delta")
    assert head.rstrip("\n") == core.rstrip("\n"), "the copy drifted from templates/spec-template.md"
    assert addendum.startswith(" *(mandatory)*")
    assert MARK in addendum


def test_template_examples_do_not_count_as_a_delta():
    template = (EXT_DIR / "templates" / "spec-template.md").read_text(encoding="utf-8")
    assert not re.search(r"^### (ADDED|MODIFIED|REMOVED) ", template, re.M)
    assert not re.search(r"^Capabilities: none", template, re.M)


def test_specify_prompt_no_longer_ties_every_hook_to_a_branch():
    text = (ROOT / "templates" / "commands" / "specify.md").read_text(encoding="utf-8")
    assert OLD_SENTENCE not in text
    assert NEW_SENTENCE in text
    assert NO_INVENT in text


def test_context_command_is_read_only_and_invents_no_branch():
    text = (EXT_DIR / "commands" / "speckit.capabilities.context.md").read_text(encoding="utf-8")
    assert "No branch was created. This output contains no BRANCH_NAME and no FEATURE_NUM." in text
    assert "Do not run `check-prerequisites`" in text
    assert "Do not write any file" in text


def test_review_command_never_decides_a_change_of_meaning_alone():
    text = (EXT_DIR / "commands" / "speckit.capabilities.review.md").read_text(encoding="utf-8")
    assert "Name the changed items and the `rules`" in text
    assert "If you cannot see the previous text, treat it as a change of meaning" in text
    assert "do not fix anything on your own" in text
    assert "stop on any change of meaning" in text


def test_fold_command_keeps_requirement_and_observation_apart():
    text = (EXT_DIR / "commands" / "speckit.capabilities.fold.md").read_text(encoding="utf-8")
    assert "Write what it does, not what the spec asks" in text
    assert "Never soften it and never change the rule text" in text
    assert "Never edit the catalog or delete the journal by hand" in text
    assert "code manda" not in text and "code wins" not in text


def test_every_command_runs_the_script_through_the_python_variant():
    for name in COMMANDS:
        text = (EXT_DIR / "commands" / ("speckit.capabilities.%s.md" % name)).read_text(encoding="utf-8")
        front = yaml.safe_load(text.split("---")[1])
        assert list(front["scripts"]) == ["py"]
        assert front["scripts"]["py"].startswith("scripts/python/capabilities.py")
        assert "{SCRIPT}" in text


def test_ci_example_uses_the_combined_check_and_says_what_it_does_not_do():
    text = (EXT_DIR / "ci" / "capabilities-check.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    triggers = workflow.get("on") or workflow.get(True)
    assert set(triggers) == {"pull_request", "merge_group"}
    steps = workflow["jobs"]["capabilities-check"]["steps"]
    assert steps[0]["with"]["fetch-depth"] == 0
    queue = [step for step in steps if "merge_group" in str(step.get("if"))]
    assert len(queue) == 1
    assert "--combined" in queue[0]["run"]
    assert "--no-freshness" not in text
    assert "required status check" in text
    assert "Require branches to be up to date" in text
    assert not (ROOT / ".github" / "workflows" / "capabilities-check.yml").exists()


def test_script_uses_only_the_standard_library_and_parses_as_python_3_9():
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source, feature_version=(3, 9))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names <= set(sys.stdlib_module_names)
    assert "yaml" not in names


def test_readme_exit_codes_match_the_script():
    readme = (EXT_DIR / "README.md").read_text(encoding="utf-8")
    for code in range(6):
        assert re.search(r"^\| %d \| " % code, readme, re.M)
    source = SCRIPT.read_text(encoding="utf-8")
    assert "OK, HARD, INVALID, DECISION, RECOVER, BUSY = 0, 1, 2, 3, 4, 5" in source


def test_runs_on_the_oldest_supported_python_when_it_is_available():
    python39 = Path("/usr/bin/python3")
    if not python39.exists():
        pytest.skip("no system python3")
    done = subprocess.run([str(python39), "-I", "-S", "-c", "import sys; print(sys.version_info[:2] >= (3, 9))"], capture_output=True, encoding="utf-8")
    if done.stdout.strip() != "True":
        pytest.skip("system python3 is older than 3.9")
    done = subprocess.run([str(python39), "-I", "-S", str(SCRIPT), "status", "--root", str(ROOT)], capture_output=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr


# ---------------------------------------------------------------- a real project


def specify(project: Path, *args):
    code = "import sys; from specify_cli import main; sys.argv = ['specify'] + sys.argv[1:]; main()"
    env = dict(os.environ)
    env["HOME"] = str(project.parent)
    env.pop("SPECIFY_FEATURE_DIRECTORY", None)
    done = subprocess.run([sys.executable, "-c", code, *args], cwd=project, capture_output=True, encoding="utf-8", errors="replace", env=env)
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]
    return done


def script_run(project: Path, *args, env=None):
    full_env = dict(os.environ)
    full_env.update(env or {})
    done = subprocess.run(
        [sys.executable, "-I", "-S", str(project / ".specify/extensions/capabilities/scripts/python/capabilities.py"), *args],
        cwd=project, capture_output=True, encoding="utf-8", errors="replace", env=full_env,
    )
    return done.returncode, json.loads(done.stdout) if done.stdout.strip() else {}


def resolved_template(project: Path) -> str:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    done = subprocess.run(
        ["bash", ".specify/scripts/bash/resolve-template.sh", "spec-template", "--json"],
        cwd=project, capture_output=True, encoding="utf-8", errors="replace", env=env,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture(scope="module")
def installed_project(tmp_path_factory) -> Path:
    project = tmp_path_factory.mktemp("installed") / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=project, check=True)
    specify(project, "init", "--here", "--force", "--non-interactive", "--integration", "claude", "--script", "sh")
    specify(project, "extension", "add", "capabilities")
    return project


@requires_bash
def test_install_registers_hooks_commands_and_config(installed_project: Path):
    hooks = yaml.safe_load((installed_project / ".specify" / "extensions.yml").read_text(encoding="utf-8"))["hooks"]
    for event, command in (("before_specify", "context"), ("after_specify", "review"), ("before_plan", "review"), ("after_implement", "fold"), ("after_converge", "fold")):
        registered = [hook for hook in hooks[event] if hook["extension"] == "capabilities"]
        assert len(registered) == 1
        assert registered[0]["command"] == "speckit.capabilities.%s" % command
        assert registered[0]["optional"] is False
    assert (installed_project / ".specify/extensions/capabilities/capabilities-config.yml").is_file()
    skill = installed_project / ".claude/skills/speckit-capabilities-review/SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "{SCRIPT}" not in text
    assert ".specify/extensions/capabilities/scripts/python/capabilities.py ensure" in text
    assert ".specify/extensions/capabilities/scripts/python/capabilities.py review --accept" in text


@requires_bash
def test_script_finds_the_feature_through_spec_kit_when_installed(installed_project: Path):
    change = "modules/auth/flows/login"
    (installed_project / change).mkdir(parents=True)
    (installed_project / change / "spec.md").write_text(spec_text("Capabilities: none — nada\n"), encoding="utf-8")
    env = {"SPECIFY_FEATURE_DIRECTORY": change}
    rc, out = script_run(installed_project, "review", env=env)
    assert (rc, out["status"]) == (0, "stamped")
    assert (installed_project / change / "capability-delta.lock.json").is_file()

    rc, out = script_run(installed_project, "review", env={"SPECIFY_FEATURE_DIRECTORY": "/tmp/somewhere/outside"})
    assert rc == 2 and "outside the repository" in str(out)


@requires_bash
def test_installed_copy_finds_its_own_templates(installed_project: Path):
    change = "specs/050-no-section"
    (installed_project / change).mkdir(parents=True)
    (installed_project / change / "spec.md").write_text("# Feature\n", encoding="utf-8")
    rc, out = script_run(installed_project, "ensure", "--change", change)
    assert (rc, out["status"]) == (0, "inserted")
    assert MARK in (installed_project / change / "spec.md").read_text(encoding="utf-8")


@requires_bash
def test_script_reports_an_unresolved_feature(installed_project: Path):
    env = {k: v for k, v in os.environ.items() if k != "SPECIFY_FEATURE_DIRECTORY"}
    feature_json = installed_project / ".specify" / "feature.json"
    if feature_json.exists():
        feature_json.unlink()
    done = subprocess.run(
        [sys.executable, "-I", "-S", str(installed_project / ".specify/extensions/capabilities/scripts/python/capabilities.py"), "review"],
        cwd=installed_project, capture_output=True, encoding="utf-8", errors="replace", env=env,
    )
    assert done.returncode == 2
    assert "cannot resolve the feature directory" in done.stdout


@requires_bash
def test_template_composes_without_pyyaml_and_disable_or_remove_restore_the_core(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=project, check=True)
    specify(project, "init", "--here", "--force", "--non-interactive", "--integration", "claude", "--script", "sh")
    core = resolved_template(project)
    assert MARK not in core

    specify(project, "extension", "add", "capabilities")
    assert MARK in resolved_template(project)

    specify(project, "extension", "disable", "capabilities")
    assert resolved_template(project) == core

    specify(project, "extension", "enable", "capabilities")
    assert MARK in resolved_template(project)

    specify(project, "extension", "remove", "capabilities", "--force")
    assert resolved_template(project) == core
    assert not (project / ".specify/extensions/capabilities").exists()


def test_helper_spec_text_is_a_valid_delta_document():
    assert MARK in spec_text(modified())
