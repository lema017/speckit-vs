"""The bundled ``sliced`` workflow: the slices of a slice map, built one after another.

The walk is run for real, with the engine, the gate, the shell step and the script of the
capabilities extension. Only the coding agent is replaced: a small script that does what each
command leaves on disk, so the map moves on as it would with a model.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from specify_cli._assets import _locate_bundled_workflow
from specify_cli.integrations import get_integration
from specify_cli.workflows.engine import WorkflowDefinition, WorkflowEngine, validate_workflow
from specify_cli.workflows.step import gate as gate_module

REPO_ROOT = Path(__file__).parents[2]
SCRIPT = ".specify/extensions/capabilities/scripts/python/capabilities.py"
CART, PAY = "D-shop-cart", "D-shop-pay"
MAP = """# Slices: shop

<!-- slice-map:v1 -->

Request: A shop: a cart and a way to pay.

### D-shop-cart Add to the cart
- Intent: A buyer puts a product in the cart.
- Verify: I add a book and see it in the cart.
- Depends-On: none
- Rules: none

### D-shop-pay Pay for the cart
- Intent: A buyer pays for what is in the cart.
- Verify: I pay and see the receipt.
- Depends-On: D-shop-cart
- Rules: none
"""

# What the commands leave on disk. ``specify`` writes a spec that names the slice, ``tasks`` writes
# one open task and ``implement`` closes what is open, unless the file ``leave-open`` asks it not to.
# A file in the project root asks for a variant, for every slice or for the slices it lists:
# ``no-spec`` (specify writes nothing), ``big-spec`` (two stories) and ``big-tasks`` (26 tasks).
FAKE_AGENT = r'''
import json, re, sys
from pathlib import Path

prompt = sys.argv[1]
root = Path.cwd()
with open(root / "calls.txt", "a", encoding="utf-8") as log:
    log.write(" ".join(prompt.split()) + "\n")
feature = root / ".specify" / "feature.json"


def current():
    return root / json.loads(feature.read_text(encoding="utf-8"))["feature_directory"]


def asked_for(variant, slice_id):
    path = root / variant
    if not path.exists():
        return False
    listed = path.read_text(encoding="utf-8").split()
    return not listed or slice_id in listed


named = re.search(r"speckit[.-]specify\s+(D-[a-z0-9-]+)", prompt)
if named:
    slice_id = named.group(1)
    if not asked_for("no-spec", slice_id):
        number = len(list((root / "specs").glob("[0-9]*"))) + 1
        directory = root / "specs" / ("%03d-%s" % (number, slice_id[2:]))
        directory.mkdir(parents=True)
        stories = "### User Story 1 - One thing\n\n### User Story 2 - Another thing\n\n" if asked_for("big-spec", slice_id) else ""
        spec = "# Feature Specification: %s\n\n## Slice *(mandatory)*\n\n- Slice: %s\n- Out: none\n\n%s## Requirements\n\n- **FR-001**: The system MUST do it.\n"
        (directory / "spec.md").write_text(spec % (slice_id, slice_id, stories), encoding="utf-8")
        feature.write_text(json.dumps({"feature_directory": directory.relative_to(root).as_posix()}), encoding="utf-8")
elif re.search(r"speckit[.-]tasks", prompt):
    slice_id = re.search(r"^- Slice: (\S+)", (current() / "spec.md").read_text(encoding="utf-8"), re.M).group(1)
    count = 26 if asked_for("big-tasks", slice_id) else 1
    (current() / "tasks.md").write_text("".join("- [ ] T%03d Build part %d\n" % (n, n) for n in range(1, count + 1)), encoding="utf-8")
elif re.search(r"speckit[.-]implement", prompt) and not (root / "leave-open").exists():
    tasks = current() / "tasks.md"
    tasks.write_text(tasks.read_text(encoding="utf-8").replace("- [ ]", "- [x]"), encoding="utf-8")
'''

needs_python3 = pytest.mark.skipif(shutil.which("python3") is None, reason="the workflow runs the extension script with python3")


def shipped():
    return yaml.safe_load((REPO_ROOT / "workflows" / "sliced" / "workflow.yml").read_text(encoding="utf-8"))


def steps_by_id(steps, found=None):
    """Every step of the definition, however deep, by id."""
    found = {} if found is None else found
    for step in steps:
        found[step["id"]] = step
        for key in ("steps", "then", "else"):
            steps_by_id(step.get(key) or [], found)
    return found


class _Stdin:
    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty


class _Sys:
    def __init__(self, tty):
        self.stdin = _Stdin(tty)

    def __getattr__(self, name):
        return getattr(sys, name)


class Walk:
    """A project with a slice map, the extension script and the workflow installed, and an agent that is a script."""

    def __init__(self, root: Path, monkeypatch):
        self.root, self.monkeypatch, self.asked = root, monkeypatch, []
        shutil.copytree(REPO_ROOT / "extensions" / "capabilities", root / ".specify" / "extensions" / "capabilities",
                        ignore=shutil.ignore_patterns("__pycache__"))
        target = root / ".specify" / "workflows" / "sliced"
        target.mkdir(parents=True)
        shutil.copy(REPO_ROOT / "workflows" / "sliced" / "workflow.yml", target / "workflow.yml")
        agent = root / "fake_agent.py"
        agent.write_text(FAKE_AGENT, encoding="utf-8")
        monkeypatch.setattr(type(get_integration("claude")), "build_exec_args",
                            lambda self, prompt, **kwargs: [sys.executable, "-u", str(agent), prompt])
        self.terminal(True)

    def put_map(self, text=MAP, name="shop"):
        path = self.root / "specs" / "_slices" / (name + ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def terminal(self, tty):
        self.monkeypatch.setattr(gate_module, "sys", _Sys(tty))

    def answer(self, *choices, on_message=None):
        """What the person picks at each gate, in order. A gate nobody expected fails the test."""
        left = list(choices)

        def prompt(message, options):
            self.asked.append(message)
            if on_message:
                on_message(message)
            assert left, "a gate asked and no answer was left: %s" % message
            return left.pop(0)

        self.monkeypatch.setattr(gate_module.GateStep, "_prompt", staticmethod(prompt))

    def run(self, **inputs):
        engine = WorkflowEngine(self.root)
        return engine.execute(engine.load_workflow("sliced"), dict({"integration": "claude"}, **inputs))

    def resume(self, run_id):
        return WorkflowEngine(self.root).resume(run_id)

    def calls(self):
        """Each prompt the agent got, in order. An integration may write a command with a dot or with a dash."""
        log = self.root / "calls.txt"
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return [line.replace("/speckit-", "/speckit.", 1) for line in lines]

    def variant(self, name, *slice_ids):
        """Ask the agent for a variant of what it leaves, for these slices or for every slice."""
        (self.root / name).write_text(" ".join(slice_ids), encoding="utf-8")

    def accepted(self, directory):
        """What was recorded for a spec over the budget, or None."""
        path = self.root / "specs" / directory / "slice-budget.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def next(self):
        """What the project says comes now, asked outside the workflow."""
        done = subprocess.run([sys.executable, str(self.root / SCRIPT), "slices", "next", "--root", str(self.root)],
                              capture_output=True, encoding="utf-8")
        return json.loads(done.stdout)


@pytest.fixture
def walk(project_dir, monkeypatch):
    return Walk(project_dir, monkeypatch)


ONE_SLICE = ["/speckit.specify %s", "/speckit.plan", "/speckit.tasks", "/speckit.implement"]
SPLIT = "Reject to stop here and split it with speckit.capabilities.size."


def built(*slice_ids):
    return [line % slice_id if "%s" in line else line for slice_id in slice_ids for line in ONE_SLICE]


# -- What ships ----------------------------------------------------------------------------------


def test_the_workflow_is_valid_and_is_the_one_the_package_ships():
    directory = _locate_bundled_workflow("sliced")
    assert directory is not None
    definition = WorkflowDefinition.from_string((directory / "workflow.yml").read_text(encoding="utf-8"))
    assert validate_workflow(definition) == []
    assert (definition.id, str(definition.version)) == ("sliced", "1.0.0")


def test_each_round_asks_the_project_which_slice_comes_now():
    data = shipped()
    (walk_step,) = data["steps"]
    assert (walk_step["id"], walk_step["type"]) == ("walk", "do-while")
    assert walk_step["condition"] == "{{ steps.next-slice.output.data.reason != 'done' }}"
    assert walk_step["max_iterations"] >= 20, "one round per slice and one more that finds the map done"
    probe = walk_step["steps"][0]
    assert probe["id"] == "next-slice" and probe["type"] == "shell"
    assert probe["run"] == "python3 %s slices next" % SCRIPT
    # The name of the map is data: it travels in the environment and is never shell text.
    assert probe["strict"] is True and probe["output_format"] == "json"
    assert probe["env"] == {"SPECKIT_SLICE_MAP": "{{ inputs.map }}"}
    assert "{{" not in probe["run"]


def test_a_slice_is_built_only_after_a_person_approves_it():
    steps = steps_by_id(shipped()["steps"])
    build = steps["build-slice"]
    assert build["type"] == "if" and build["condition"] == "{{ steps.next-slice.output.data.reason == 'ready' }}"
    assert [step["id"] for step in build["then"]] == [
        "approve-slice", "specify", "measure-spec", "oversized-spec", "plan", "tasks", "measure-tasks", "oversized-tasks", "implement"]
    for gate in ("approve-slice", "review-spec", "review-oversized-spec", "approve-oversized-tasks", "wait-for-delivery"):
        assert steps[gate]["type"] == "gate"
        assert steps[gate]["options"] == ["approve", "reject"] and steps[gate]["on_reject"] == "abort"
        assert "verdict_input" not in steps[gate], "one answer would approve every later slice too"
    assert steps["specify"]["command"] == "speckit.specify"
    assert steps["specify"]["input"] == {"args": "{{ steps.next-slice.output.data.next }}"}
    for name in ("plan", "tasks", "implement"):
        assert steps[name]["command"] == "speckit." + name
        assert steps[name]["input"] == {"args": ""}, "the feature comes from the spec that specify just wrote"
    assert steps["nothing-ready"]["condition"] == "{{ steps.next-slice.output.data.reason in ['waiting', 'in-progress'] }}"
    assert [step["id"] for step in steps["nothing-ready"]["then"]] == ["wait-for-delivery"]


def test_the_catalogs_the_bundle_and_the_package_agree_with_the_workflow():
    version = str(shipped()["workflow"]["version"])
    entry = json.loads((REPO_ROOT / "workflows" / "catalog.json").read_text(encoding="utf-8"))["workflows"]["sliced"]
    assert (entry["id"], entry["version"], entry["bundled"]) == ("sliced", version, True)
    # This workflow exists in this fork only, so its entry points here and not at upstream.
    assert entry["url"] == "https://raw.githubusercontent.com/lema017/speckit-vs/main/workflows/sliced/workflow.yml"
    with (REPO_ROOT / "pyproject.toml").open("rb") as stream:
        included = tomllib.load(stream)["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert included["workflows/sliced"] == "specify_cli/core_pack/workflows/sliced"
    bundle = yaml.safe_load((REPO_ROOT / "bundles" / "sliced" / "bundle.yml").read_text(encoding="utf-8"))
    assert bundle["provides"] == {"workflows": [{"id": "sliced", "version": version}]}
    listed = json.loads((REPO_ROOT / "bundles" / "catalog.json").read_text(encoding="utf-8"))["bundles"]["sliced"]
    assert listed["version"] == bundle["bundle"]["version"]
    assert listed["download_url"] == "https://raw.githubusercontent.com/lema017/speckit-vs/main/bundles/sliced/bundle.yml"
    assert listed["provides"] == {"extensions": 0, "presets": 0, "steps": 0, "workflows": 1}


def test_the_docs_list_the_workflow_and_its_bundle():
    assert "| `sliced` |" in (REPO_ROOT / "docs" / "workflows" / "overview.md").read_text(encoding="utf-8")
    assert "| `sliced` |" in (REPO_ROOT / "docs" / "bundles" / "overview.md").read_text(encoding="utf-8")
    assert "`sliced/workflow.yml`" in (REPO_ROOT / "workflows" / "README.md").read_text(encoding="utf-8")


def test_a_slice_over_its_budget_goes_on_only_after_a_person_accepts_its_size():
    """The size step of the extension asks, and inside a command step nobody answers: the walk measures and asks at a gate."""
    steps = steps_by_id(shipped()["steps"])
    slice_in_the_environment = {"SPECKIT_SLICE": "{{ steps.next-slice.output.data.next }}"}
    for when, gate, accept, where in (("spec", "review-oversized-spec", "accept-spec-size", "spec review"), ("tasks", "approve-oversized-tasks", "accept-tasks-size", "tasks")):
        measure, branch = steps["measure-" + when], steps["oversized-" + when]
        assert measure["type"] == "shell" and measure["run"] == "python3 %s slices measure" % SCRIPT
        assert measure["strict"] is True and measure["output_format"] == "json" and measure["env"] == slice_in_the_environment
        assert branch["type"] == "if" and branch["condition"] == "{{ steps.measure-%s.output.data.status == 'over' }}" % when
        assert [step["id"] for step in branch["then"]] == [gate, accept], "the acceptance is recorded only after the gate"
        assert steps[gate]["message"].startswith("{{ steps.measure-%s.output.data.summary }} " % when)
        assert steps[gate]["message"].endswith(SPLIT)
        recorded = steps[accept]
        assert recorded["type"] == "shell" and recorded["strict"] is True and recorded["env"] == slice_in_the_environment
        assert recorded["run"] == 'python3 %s slices accept --reason "Accepted at the %s gate of the sliced workflow."' % (SCRIPT, where)
    # Within the budget the spec gets the review gate it always had, with its size in the message.
    assert [step["id"] for step in steps["oversized-spec"]["else"]] == ["review-spec"]
    assert steps["review-spec"]["message"].endswith(" {{ steps.measure-spec.output.data.summary }}")
    assert "else" not in steps["oversized-tasks"], "tasks within the budget are built without asking"


# -- The walk, with an agent that is a script ----------------------------------------------------


@needs_python3
def test_it_builds_every_pending_slice_in_the_order_of_the_map(walk):
    walk.put_map()
    walk.answer("approve", "approve", "approve", "approve")
    state = walk.run(map="shop")
    assert state.status.value == "completed", state.step_results
    assert walk.calls() == built(CART, PAY)
    assert walk.next()["reason"] == "done"
    assert len(walk.asked) == 4, "two gates for each slice, and none once the map is done"
    assert "shop: 0 of 2 slices delivered. Next: %s Add to the cart." % CART in walk.asked[0]
    assert "A person checks it by: I add a book and see it in the cart." in walk.asked[0]
    assert "Review the spec of %s before it is planned and built. Slice size: 0 stories (max 1), 1 requirement (max 10), " % CART in walk.asked[1]
    assert walk.asked[1].endswith("tasks not written (max 25). Within the slice budget.")
    assert "shop: 1 of 2 slices delivered. Next: %s Pay for the cart." % PAY in walk.asked[2]
    assert walk.accepted("001-shop-cart") is None and walk.accepted("002-shop-pay") is None
    # Three rounds: one per slice, and the one that finds nothing left.
    assert "walk:next-slice:2" in state.step_results and "walk:next-slice:3" not in state.step_results


@needs_python3
def test_the_map_can_be_left_out_when_only_one_has_a_slice_to_build(walk):
    walk.put_map()
    walk.answer("approve", "approve", "approve", "approve")
    assert walk.run().status.value == "completed"
    assert walk.calls() == built(CART, PAY)


@needs_python3
@pytest.mark.parametrize("answers, expected", [(["reject"], []), (["approve", "reject"], ["/speckit.specify " + CART]), (["approve", "approve", "reject"], built(CART))])
def test_a_rejected_gate_stops_the_walk_there(walk, answers, expected):
    walk.put_map()
    walk.answer(*answers)
    state = walk.run(map="shop")
    assert state.status.value == "aborted"
    assert walk.calls() == expected


@needs_python3
def test_a_slice_left_undelivered_makes_the_walk_wait_for_a_person(walk):
    walk.put_map()
    (walk.root / "leave-open").write_text("", encoding="utf-8")

    def finish_by_hand(message):
        if "Finish what is in progress" in message:
            (walk.root / "leave-open").unlink()
            (walk.root / "specs" / "001-shop-cart" / "tasks.md").write_text("- [x] T001 Build it\n", encoding="utf-8")

    walk.answer("approve", "approve", "approve", "approve", "approve", on_message=finish_by_hand)
    state = walk.run(map="shop")
    assert state.status.value == "completed", state.step_results
    assert "No slice is ready: %s waits for %s (building)." % (PAY, CART) in walk.asked[2]
    assert "Finish what is in progress, then approve to look again, or reject to stop here." in walk.asked[2]
    assert walk.calls() == built(CART, PAY), "the slice that was finished by hand is not built again"
    assert walk.next()["reason"] == "done"


@needs_python3
def test_the_walk_never_ends_as_done_while_a_slice_is_undelivered(walk):
    walk.put_map()
    (walk.root / "leave-open").write_text("", encoding="utf-8")
    walk.answer("approve", "approve", "reject")
    state = walk.run(map="shop")
    assert state.status.value == "aborted"
    assert walk.calls() == built(CART)
    assert walk.next()["reason"] == "waiting"


@needs_python3
def test_without_a_terminal_the_run_pauses_at_the_gate_and_goes_on_when_resumed(walk):
    walk.put_map()
    walk.terminal(False)
    walk.answer()
    paused = walk.run(map="shop")
    assert paused.status.value == "paused" and walk.calls() == [], "nothing is written before a person approves the slice"
    assert walk.resume(paused.run_id).status.value == "paused"
    walk.terminal(True)
    walk.answer("approve", "approve", "approve", "approve")
    assert walk.resume(paused.run_id).status.value == "completed"
    assert walk.calls() == built(CART, PAY)


@needs_python3
def test_a_project_without_a_slice_map_fails_before_any_command_runs(walk):
    walk.answer()
    state = walk.run(map="shop")
    assert state.status.value == "failed"
    assert walk.calls() == [] and walk.asked == []


@needs_python3
def test_the_name_of_the_map_is_never_run_as_a_command(walk):
    walk.put_map()
    walk.put_map(MAP.replace("shop", "blog"), name="blog")
    walk.answer()
    assert walk.run().status.value == "failed", "two maps have a slice to build, so one must be named"
    hostile = 'shop"; touch pwned; echo "'
    assert walk.run(map=hostile).status.value == "failed"
    assert not (walk.root / "pwned").exists()
    walk.answer("approve", "reject")
    assert walk.run(map="blog").status.value == "aborted"
    assert walk.calls() == ["/speckit.specify D-blog-cart"]


# -- A slice over its budget ---------------------------------------------------------------------


@needs_python3
def test_a_spec_over_the_budget_is_planned_only_after_a_person_accepts_its_size(walk):
    walk.put_map()
    walk.variant("big-spec", CART)
    walk.answer("approve", "approve", "approve", "approve")
    state = walk.run(map="shop")
    assert state.status.value == "completed", state.step_results
    assert walk.calls() == built(CART, PAY)
    assert len(walk.asked) == 4, "the size gate stands in for the review gate, and the tasks did not go over"
    assert "2 stories (max 1)" in walk.asked[1]
    assert "Over the slice budget in stories. Review the spec of %s. Approve to plan and build it as it is" % CART in walk.asked[1]
    assert walk.asked[1].endswith("the walk records that its size was accepted at this gate. " + SPLIT)
    record = walk.accepted("001-shop-cart")
    assert record["reason"] == "Accepted at the spec review gate of the sliced workflow."
    assert record["accepted"] == {"stories": 2, "requirements": 1, "rules": 0, "tasks": None}
    assert "Within the slice budget." in walk.asked[3] and walk.accepted("002-shop-pay") is None


@needs_python3
def test_tasks_over_the_budget_are_built_only_after_a_person_accepts_them(walk):
    walk.put_map()
    walk.variant("big-tasks", CART)
    walk.answer("approve", "approve", "approve", "approve", "approve")
    state = walk.run(map="shop")
    assert state.status.value == "completed", state.step_results
    assert walk.calls() == built(CART, PAY)
    assert len(walk.asked) == 5, "one more gate, for the slice whose tasks went over"
    assert "26 tasks (max 25). Over the slice budget in tasks. Approve to build %s as it is" % CART in walk.asked[2]
    assert walk.asked[2].endswith(SPLIT)
    record = walk.accepted("001-shop-cart")
    assert record["reason"] == "Accepted at the tasks gate of the sliced workflow."
    assert record["accepted"] == {"stories": 0, "requirements": 1, "rules": 0, "tasks": 26}
    assert walk.accepted("002-shop-pay") is None


@needs_python3
def test_a_size_that_was_accepted_is_asked_again_when_the_tasks_go_over_too(walk):
    walk.put_map()
    walk.variant("big-spec", CART)
    walk.variant("big-tasks", CART)
    walk.answer("approve", "approve", "approve", "approve", "approve")
    assert walk.run(map="shop").status.value == "completed"
    assert "Over the slice budget in stories. Review the spec of %s." % CART in walk.asked[1]
    assert "Over the slice budget in stories and tasks. Approve to build %s as it is" % CART in walk.asked[2]
    record = walk.accepted("001-shop-cart")
    assert record["reason"] == "Accepted at the tasks gate of the sliced workflow."
    assert record["accepted"] == {"stories": 2, "requirements": 1, "rules": 0, "tasks": 26}


@needs_python3
@pytest.mark.parametrize("variant, answers, expected", [
    ("big-spec", ["approve", "reject"], ["/speckit.specify " + CART]),
    ("big-tasks", ["approve", "approve", "reject"], ["/speckit.specify " + CART, "/speckit.plan", "/speckit.tasks"]),
])
def test_rejecting_the_size_of_a_slice_stops_the_walk_and_records_nothing(walk, variant, answers, expected):
    walk.put_map()
    walk.variant(variant)
    walk.answer(*answers)
    state = walk.run(map="shop")
    assert state.status.value == "aborted"
    assert walk.calls() == expected, "nothing is planned or built past the gate that was rejected"
    assert walk.accepted("001-shop-cart") is None


@needs_python3
def test_a_size_gate_without_a_terminal_pauses_the_run_and_resume_asks_it(walk):
    walk.put_map()
    walk.variant("big-tasks", CART)

    def lose_the_terminal(message):
        if "Review the spec of %s" % CART in message:
            walk.terminal(False)

    walk.answer("approve", "approve", on_message=lose_the_terminal)
    paused = walk.run(map="shop")
    assert paused.status.value == "paused"
    assert walk.calls() == ["/speckit.specify " + CART, "/speckit.plan", "/speckit.tasks"]
    assert walk.accepted("001-shop-cart") is None, "nothing is accepted while nobody answered"
    walk.terminal(True)
    walk.answer("approve", "approve", "approve")
    assert walk.resume(paused.run_id).status.value == "completed"
    assert walk.calls() == built(CART, PAY), "resuming does not run again what was already done"
    assert walk.accepted("001-shop-cart")["accepted"]["tasks"] == 26


@needs_python3
@pytest.mark.parametrize("missing, answers, expected", [
    (CART, ["approve"], ["/speckit.specify " + CART]),
    (PAY, ["approve", "approve", "approve"], built(CART) + ["/speckit.specify " + PAY]),
])
def test_the_walk_stops_when_specify_leaves_no_spec_for_the_slice(walk, missing, answers, expected):
    walk.put_map()
    walk.variant("no-spec", missing)
    walk.answer(*answers)
    state = walk.run(map="shop")
    assert state.status.value == "failed"
    assert walk.calls() == expected, "nothing is planned on the spec of another slice"
