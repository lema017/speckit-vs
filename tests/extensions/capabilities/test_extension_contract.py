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

COMMANDS = {"context", "review", "fold", "check", "bootstrap", "locate"}
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
    for code in range(7):
        assert re.search(r"^\| %d \| " % code, readme, re.M)
    source = SCRIPT.read_text(encoding="utf-8")
    assert "OK, HARD, INVALID, DECISION, RECOVER, BUSY = 0, 1, 2, 3, 4, 5" in source
    assert "OK, INVALID, UNAVAILABLE = 0, 2, 6" in SCRIPT.with_name("cap_graph.py").read_text(encoding="utf-8")


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
    specify(project, "init", "--here", "--force", "--non-interactive", "--integration", "claude", "--script", "sh", "--no-default-extensions")
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
    specify(project, "init", "--here", "--force", "--non-interactive", "--integration", "claude", "--script", "sh", "--no-default-extensions")
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


@requires_bash
def test_installed_project_gets_the_block_in_the_file_of_its_integration(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=project, check=True)
    specify(project, "init", "--here", "--force", "--non-interactive", "--integration", "claude", "--script", "sh", "--no-default-extensions")
    specify(project, "extension", "add", "capabilities")
    change = "specs/001-x"
    (project / change).mkdir(parents=True)
    (project / change / "spec.md").write_text(spec_text("Capabilities: none — nada\n"), encoding="utf-8")
    rc, out = script_run(project, "review", "--change", change)
    assert (rc, out["status"]) == (0, "stamped")
    assert "CLAUDE.md" in out["setup"]
    text = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "<!-- SPECKIT CAPABILITIES START -->" in text and "specs/_capabilities/index.md" in text

    rc, out = script_run(project, "scaffold", "--capability", "login", "--covers", "Inicio de sesión")
    assert (rc, out["status"]) == (0, "planned")
    rc, out = script_run(project, "locate")
    assert (rc, out["planned"]) == (0, {"login": "Inicio de sesión"})

    for name, rendered in (("locate", "capabilities.py locate"), ("bootstrap", "capabilities.py scaffold --capability")):
        skill = (project / (".claude/skills/speckit-capabilities-%s/SKILL.md" % name)).read_text(encoding="utf-8")
        assert "{SCRIPT}" not in skill
        assert rendered in skill


def test_bootstrap_prompt_waits_for_approval_and_never_decides_for_a_person():
    text = (EXT_DIR / "commands" / "speckit.capabilities.bootstrap.md").read_text(encoding="utf-8")
    assert "**Write nothing before the user approves the map.**" in text
    assert "A request to bootstrap is not approval of the map" in text
    assert "If you cannot ask the user, show the map and stop." in text
    assert text.index("**Stop and ask which capabilities") < text.index("scaffold --capability")
    assert "Never write `[inferred]` by hand." in text
    assert "Never `discrepant`" in text
    assert "Only for rules the user names." in text
    assert "--scaffold-only" in text and "--validate" in text
    assert text.count("--no-tasks") == 2
    assert "and do not commit" in text


def test_locate_prompt_is_read_only_and_says_where_the_answer_comes_from():
    text = (EXT_DIR / "commands" / "speckit.capabilities.locate.md").read_text(encoding="utf-8")
    assert "This command writes nothing, except the graph when Graphify is installed" in text
    assert "`resolves: false` means the catalog lags the code" in text
    assert "which part of the answer comes from the graph or the code and not from the catalog" in text
    assert "The question and the catalog may be in different languages." in text
    assert "`rg`" in text and "origin" in text


def test_locate_goes_to_the_catalog_then_the_graph_then_the_code_and_the_graph_never_decides():
    text = (EXT_DIR / "commands" / "speckit.capabilities.locate.md").read_text(encoding="utf-8")
    assert text.index("{SCRIPT} locate`") < text.index("{SCRIPT} graph status") < text.index("search the code with `rg`")
    assert "{SCRIPT} graph explain <anchor>" in text and "{SCRIPT} graph affected <anchor>" in text
    assert "{SCRIPT} graph query <technical English keywords>" in text
    assert "It does not work with Spanish or with a whole question." in text
    assert "confirm the callers in the code" in text
    assert "With exit code 6, `not-found` or `ambiguous`, go to the next step." in text
    assert "never what the requirement is" in text


def test_only_the_gate_touches_graphify():
    scripts = EXT_DIR / "scripts" / "python"
    assert sorted(path.name for path in scripts.iterdir() if path.suffix == ".py") == ["cap_graph.py", "capabilities.py"]
    main = (scripts / "capabilities.py").read_text(encoding="utf-8")
    assert '"graphify"' not in main and "GRAPHIFY_" not in main
    for name in COMMANDS:
        text = (EXT_DIR / "commands" / ("speckit.capabilities.%s.md" % name)).read_text(encoding="utf-8")
        assert "graphify update" not in text and "graphify query" not in text and "graphify explain" not in text


def test_bootstrap_takes_communities_as_hints_and_writes_nothing_for_them():
    text = (EXT_DIR / "commands" / "speckit.capabilities.bootstrap.md").read_text(encoding="utf-8")
    assert "use them as hints and never save them" in text
    assert "graph update" not in text


def test_the_installed_copy_reaches_the_gate(installed_project):
    done = subprocess.run(
        [sys.executable, "-I", "-S", str(installed_project / ".specify/extensions/capabilities/scripts/python/capabilities.py"), "graph", "status", "--root", str(installed_project)],
        capture_output=True, encoding="utf-8", env={"PATH": "/usr/bin:/bin"},
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["available"] is False


@pytest.mark.parametrize("name", ["fold", "bootstrap"])
def test_prompts_teach_the_reference_of_each_runner(name):
    text = (EXT_DIR / "commands" / ("speckit.capabilities.%s.md" % name)).read_text(encoding="utf-8")
    assert "JUnit `file::[Nested::]method`" in text and "Jest and Vitest `file::[describe::]title`" in text


def test_readme_names_only_the_runners_that_were_validated_and_their_traps():
    text = (EXT_DIR / "README.md").read_text(encoding="utf-8")
    for needle in ("Maven Surefire 3", "Gradle 8", "`jest-junit`", "Vitest", 'addFileAttribute: "true"', "`cleanTest test`", "judged by when the file was written"):
        assert needle in text


@pytest.mark.parametrize("name", ["fold", "bootstrap"])
def test_prompts_ask_for_a_test_that_pins_the_value(name):
    text = (EXT_DIR / "commands" / ("speckit.capabilities.%s.md" % name)).read_text(encoding="utf-8")
    assert "A test that reads the same constant as the code keeps passing with any value" in text
    assert "if the value in the rule changes" in text or "if the value in the rule changed" in text
    assert "unverified" in text


@pytest.mark.parametrize("name", ["review", "fold", "bootstrap"])
def test_prompts_that_can_write_the_block_report_when_it_was_skipped(name):
    text = (EXT_DIR / "commands" / ("speckit.capabilities.%s.md" % name)).read_text(encoding="utf-8")
    assert "Report any `setup` entry that starts with `skipped`" in text


def test_agent_rule_template_has_one_pair_of_markers_and_points_to_the_catalog():
    text = (EXT_DIR / "templates" / "capability-agent-rule.md").read_text(encoding="utf-8")
    assert text.startswith("<!-- SPECKIT CAPABILITIES START -->\n")
    assert text.endswith("<!-- SPECKIT CAPABILITIES END -->\n")
    assert text.count("SPECKIT CAPABILITIES START") == 1 and text.count("SPECKIT CAPABILITIES END") == 1
    assert "specs/_capabilities/index.md" in text
    assert "before changing existing behaviour" in text
    assert "do not rewrite the requirement to match the code" in text


def test_readme_states_the_limit_of_the_block_and_of_inferred_rules():
    text = (EXT_DIR / "README.md").read_text(encoding="utf-8")
    assert "this is an instruction an agent can ignore" in text
    assert "can reach `ready` as `unverified`" in text
    assert "A value changed without a delta when the mapped tests do not pin it." in text


def test_helper_spec_text_is_a_valid_delta_document():
    assert MARK in spec_text(modified())
