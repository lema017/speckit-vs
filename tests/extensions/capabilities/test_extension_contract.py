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

COMMANDS = {"slice", "context", "clarify-context", "review", "fold", "check", "bootstrap", "locate"}
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
    hooks = {event: entries if isinstance(entries, list) else [entries] for event, entries in manifest_data()["hooks"].items()}
    commands = {event: [hook["command"].replace("speckit.capabilities.", "") for hook in entries] for event, entries in hooks.items()}
    assert commands == {
        # The cut comes first: context then loads the rules of the one slice the run is aimed at.
        "before_specify": ["slice", "context"],
        "before_clarify": ["clarify-context"],
        "after_specify": ["review"],
        "before_plan": ["review"],
        "after_implement": ["fold"],
        "after_converge": ["fold"],
    }
    for entries in hooks.values():
        for hook in entries:
            assert hook["optional"] is False
            assert "condition" not in hook, "prompts skip hooks that have a condition"


def test_catalog_and_packaging_agree_with_the_manifest():
    catalog = json.loads((ROOT / "extensions" / "catalog.json").read_text(encoding="utf-8"))
    entry = catalog["extensions"]["capabilities"]
    assert entry["bundled"] is True
    assert entry["version"] == manifest_data()["extension"]["version"]
    assert '"extensions/capabilities" = "specify_cli/core_pack/extensions/capabilities"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert _locate_bundled_extension("capabilities") == EXT_DIR


def test_extension_template_is_the_core_template_for_one_slice_plus_the_addendum():
    """The copy differs from the core in two places only, so a change upstream anywhere else still shows here."""
    stories = "## User Scenarios & Testing *(mandatory)*\n"
    core = (ROOT / "templates" / "spec-template.md").read_text(encoding="utf-8")
    own = (EXT_DIR / "templates" / "spec-template.md").read_text(encoding="utf-8")
    head, _, addendum = own.partition("## Capability Delta")
    assert addendum.startswith(" *(mandatory)*")
    assert MARK in addendum

    core_top, core_rest = core.split(stories)
    own_top, own_rest = head.split(stories)
    # 1. The Slice section, between the header and the stories.
    assert own_top.startswith(core_top), "the header drifted from templates/spec-template.md"
    assert own_top[len(core_top):].startswith("## Slice *(mandatory)*\n")

    def story_one(text):
        start = text.index("### User Story 1")
        return text[start:text.index("\n---\n", start)]

    def from_edge_cases(text):
        return text[text.index("### Edge Cases"):].rstrip("\n")

    # 2. One story: the first block is the core's, and the second and third are gone.
    assert story_one(own_rest) == story_one(core_rest), "the first story drifted from templates/spec-template.md"
    assert "### User Story 2" in core and "### User Story 2" not in own and "### User Story 3" not in own
    assert "Add more user stories" not in own
    assert "This spec is ONE slice, so it holds ONE user story" in own_rest
    assert from_edge_cases(own_rest) == from_edge_cases(core_rest), "the copy drifted from templates/spec-template.md"


def test_template_slice_section_is_a_placeholder_until_the_spec_fills_it():
    template = (EXT_DIR / "templates" / "spec-template.md").read_text(encoding="utf-8")
    body = re.sub(r"<!--.*?-->", "", template, flags=re.S)
    assert re.findall(r"^- Slice: (.)", body, re.M) == ["["], "one Slice line outside comments, and it is the placeholder"
    assert "- Slice: standalone — <what a person can do and check when this spec is done>" in template
    assert template.index("## Slice *(mandatory)*") < template.index("## User Scenarios") < template.index("## Capability Delta")


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
    assert "Do not write any file yourself" in text
    assert "If `SLICE FOR THIS RUN` appears earlier in this run, printed by `speckit.capabilities.slice` or in the answer of `slices show`, the request is that slice" in text
    assert "add no other `designed` rule" in text


def test_slice_command_writes_only_an_approved_map_and_invents_no_branch():
    text = (EXT_DIR / "commands" / "speckit.capabilities.slice.md").read_text(encoding="utf-8")
    assert "No branch was created. This output contains no BRANCH_NAME and no FEATURE_NUM." in text
    assert "The only file you write is a slice map under `specs/_slices/`, and only after the user approves the cut." in text
    assert "A request is not approval of a cut" in text
    assert "If you cannot ask the user, show the proposal, say that nothing was saved and no spec was written, and stop." in text
    assert "Do not run `check-prerequisites`" in text
    assert "Never edit or remove a slice that has a spec, and never reuse an id" in text
    assert "**stop and ask**: approve the cut, change it, or build everything in one spec" in text


def test_slice_command_aims_the_run_with_what_the_script_answers():
    text = (EXT_DIR / "commands" / "speckit.capabilities.slice.md").read_text(encoding="utf-8")
    for call in ("slices status", "slices show <id>", "slices check", "status --capability <name>", "publish-design --change <record>"):
        assert "{SCRIPT} %s" % call in text
    assert text.count("SLICE FOR THIS RUN") == 2, "one block for a slice of a map, one for a request that is a slice on its own"
    assert "Print the `aim` of the answer of `slices show`, verbatim." in text, "the script writes the block of a slice of a map"
    assert "If no map has one, take the first slice whose state is `pending`" in text, "`next` when no slice is ready"
    assert "If no slice is `pending`, say that every slice has a spec, and stop." in text
    assert "For the rest of this run the feature description is this slice" in text
    assert "It builds no other `[designed]` rule" in text
    # The example in the command is a map the script accepts as it is written.
    example = text[text.index("   # Slices: login"):text.index("   - An id is")]
    assert "<!-- slice-map:v1 -->" in example and "### D-login-clave " in example and "## Later" in example


def test_fold_and_check_commands_report_the_slices():
    fold = (EXT_DIR / "commands" / "speckit.capabilities.fold.md").read_text(encoding="utf-8")
    assert "{SCRIPT} slices status" in fold and "which slice is delivered and which one comes next" in fold
    check = (EXT_DIR / "commands" / "speckit.capabilities.check.md").read_text(encoding="utf-8")
    assert "{SCRIPT} slices check" in check


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


@pytest.mark.parametrize("name", ["capabilities.py", "cap_slices.py"])
def test_script_uses_only_the_standard_library_and_parses_as_python_3_9(name):
    source = SCRIPT.with_name(name).read_text(encoding="utf-8")
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
    specify(project, "init", "--here", "--force", "--non-interactive", "--ignore-agent-tools", "--integration", "claude", "--script", "sh", "--no-default-extensions")
    specify(project, "extension", "add", "capabilities")
    return project


@requires_bash
def test_install_registers_hooks_commands_and_config(installed_project: Path):
    hooks = yaml.safe_load((installed_project / ".specify" / "extensions.yml").read_text(encoding="utf-8"))["hooks"]
    for event, commands in (("before_specify", ["slice", "context"]), ("before_clarify", ["clarify-context"]), ("after_specify", ["review"]), ("before_plan", ["review"]), ("after_implement", ["fold"]), ("after_converge", ["fold"])):
        registered = [hook for hook in hooks[event] if hook["extension"] == "capabilities"]
        assert [hook["command"] for hook in registered] == ["speckit.capabilities.%s" % command for command in commands]
        assert all(hook["optional"] is False for hook in registered)
    assert (installed_project / ".specify/extensions/capabilities/capabilities-config.yml").is_file()
    skill = installed_project / ".claude/skills/speckit-capabilities-review/SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "{SCRIPT}" not in text
    assert ".specify/extensions/capabilities/scripts/python/capabilities.py ensure" in text
    assert ".specify/extensions/capabilities/scripts/python/capabilities.py review --accept" in text
    context = (installed_project / ".claude/skills/speckit-capabilities-context/SKILL.md").read_text(encoding="utf-8")
    assert "{SCRIPT}" not in context
    assert ".specify/extensions/capabilities/scripts/python/capabilities.py status --capability" in context
    cut = (installed_project / ".claude/skills/speckit-capabilities-slice/SKILL.md").read_text(encoding="utf-8")
    assert "{SCRIPT}" not in cut
    assert ".specify/extensions/capabilities/scripts/python/capabilities.py slices show <id>" in cut


@requires_bash
def test_the_installed_copy_reads_the_slices(installed_project: Path):
    """cap_slices.py travels with the extension, and the installed script finds it beside itself."""
    rc, out = script_run(installed_project, "slices", "status")
    assert rc == 0 and out["maps"] == [], out
    assert script_run(installed_project, "slices", "check") == (0, {"status": "ok", "hard": [], "notes": [], "maps": []})


@requires_bash
@pytest.mark.parametrize("skill", ["speckit-clarify", "speckit-clarify-deep"])
def test_both_kinds_of_clarify_reach_the_hook(installed_project: Path, skill):
    text = (installed_project / ".claude/skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    assert "hooks.before_clarify" in text


@requires_bash
def test_the_clarify_context_skill_is_installed_ready_to_run(installed_project: Path):
    text = (installed_project / ".claude/skills/speckit-capabilities-clarify-context/SKILL.md").read_text(encoding="utf-8")
    assert "{SCRIPT}" not in text
    assert ".specify/extensions/capabilities/scripts/python/capabilities.py clarify-context" in text
    assert ".specify/extensions/capabilities/scripts/python/capabilities.py graph status" in text


@requires_bash
def test_a_project_from_before_gets_the_hook_and_keeps_its_config(tmp_path):
    """The documented way to bring an existing project up to date."""
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=project, check=True)
    specify(project, "init", "--here", "--force", "--non-interactive", "--ignore-agent-tools", "--integration", "claude", "--script", "sh", "--no-default-extensions")
    specify(project, "extension", "add", "capabilities")
    config = project / ".specify/extensions/capabilities/capabilities-config.yml"
    mine = config.read_bytes() + b"# a choice of this project\n"
    config.write_bytes(mine)
    registry = project / ".specify/extensions.yml"
    data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    data["hooks"]["before_clarify"] = [hook for hook in data["hooks"]["before_clarify"] if hook["extension"] != "capabilities"]
    # As 0.4.0 left it: context alone before specify.
    data["hooks"]["before_specify"] = [hook for hook in data["hooks"]["before_specify"] if hook["command"] != "speckit.capabilities.slice"]
    registry.write_text(yaml.safe_dump(data), encoding="utf-8")

    specify(project, "extension", "add", "capabilities", "--force")

    assert config.read_bytes() == mine
    hooks = yaml.safe_load(registry.read_text(encoding="utf-8"))["hooks"]
    assert [hook["command"] for hook in hooks["before_clarify"] if hook["extension"] == "capabilities"] == ["speckit.capabilities.clarify-context"]
    assert [hook["command"] for hook in hooks["before_specify"] if hook["extension"] == "capabilities"] == ["speckit.capabilities.slice", "speckit.capabilities.context"]


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
    specify(project, "init", "--here", "--force", "--non-interactive", "--ignore-agent-tools", "--integration", "claude", "--script", "sh", "--no-default-extensions")
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
    specify(project, "init", "--here", "--force", "--non-interactive", "--ignore-agent-tools", "--integration", "claude", "--script", "sh", "--no-default-extensions")
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
    assert "This command writes nothing, except the graph: `graphify-out/`" in text
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
    assert sorted(path.name for path in scripts.iterdir() if path.suffix == ".py") == ["cap_graph.py", "cap_slices.py", "capabilities.py"]
    for name in ("capabilities.py", "cap_slices.py"):
        main = (scripts / name).read_text(encoding="utf-8")
        assert '"graphify"' not in main and "GRAPHIFY_" not in main
    for name in COMMANDS:
        text = (EXT_DIR / "commands" / ("speckit.capabilities.%s.md" % name)).read_text(encoding="utf-8")
        assert "graphify update" not in text and "graphify query" not in text and "graphify explain" not in text


def test_bootstrap_builds_the_graph_first_and_takes_communities_as_hints():
    text = (EXT_DIR / "commands" / "speckit.capabilities.bootstrap.md").read_text(encoding="utf-8")
    assert "use them as hints and never save them" in text
    assert text.index("{SCRIPT} graph update") < text.index("`## Communities`") < text.index("**Stop and ask which capabilities")
    assert "`no-code` means there is no code to graph yet" in text
    assert "`graphify-out/` and `.graphifyignore`: those do not count" in text


def test_context_looks_in_the_catalog_then_the_graph_and_the_graph_never_decides():
    text = (EXT_DIR / "commands" / "speckit.capabilities.context.md").read_text(encoding="utf-8")
    assert text.index("`covers` text") < text.index("{SCRIPT} graph query") < text.index("{SCRIPT} graph anchors") < text.index("{SCRIPT} status --capability")
    assert "`graph query` does not work with Spanish" in text
    assert "never what the requirement is" in text
    assert "warn visibly that the graph was not used and go on" in text
    assert "there is no code to graph yet: say so and go on" in text


@pytest.mark.parametrize("name", ["context", "locate", "bootstrap"])
def test_prompts_that_use_the_graph_stop_without_it_and_install_nothing(name):
    text = (EXT_DIR / "commands" / ("speckit.capabilities.%s.md" % name)).read_text(encoding="utf-8")
    assert "If `available` is false, **stop**" in text
    assert "show the `install` command from that output without running it" in text
    assert "install anything" in text
    assert "uv tool install" not in text, "the command comes from the gate, so it has one source"


def test_the_context_prompt_gives_each_call_its_own_subcommand():
    frontmatter = (EXT_DIR / "commands" / "speckit.capabilities.context.md").read_text(encoding="utf-8").split("---")[1]
    assert yaml.safe_load(frontmatter)["scripts"]["py"] == "scripts/python/capabilities.py"


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
