"""What clarify gets before its first question: the script behind the hook, and the prompt that uses it."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import CAT, EXPIRY_15, EXPIRY_30, EXT_DIR, INDEX, PYTHON, SCRIPT, modified

PROMPT = EXT_DIR / "commands" / "speckit.capabilities.clarify-context.md"
JOURNAL = ".specify/capabilities/journal"
BROKEN_OPTIONS = ["not json", "[]"]


def ask(repo, *args):
    rc, out = repo.cap("clarify-context", *args)
    assert rc == 0, out
    return out


def feature(repo, entries=None, name="002-x"):
    repo.checkout("-b", "feat")
    return repo.feature(name, entries or modified(to=EXPIRY_15))


# ---------------------------------------------------------------- the script


def test_it_gives_the_feature_the_parsed_delta_and_every_capability(repo):
    change = feature(repo)
    out = ask(repo, "--change", change)
    assert out["feature"] == change
    assert out["spec"] == change + "/spec.md"
    assert out["catalog"] is True and out["journal_pending"] is False
    assert out["capabilities"]["login"]["covers"] == "Autenticación y sesión"
    assert out["delta_errors"] == []
    entry = out["delta"]["entries"][0]
    assert (entry["op"], entry["id"], entry["capability"], entry["from"], entry["to"]) == ("MODIFIED", "R-session-expiry", "login", EXPIRY_30, EXPIRY_15)
    assert "raw" not in out["delta"]


def test_it_lists_what_is_planned(repo):
    change = feature(repo)
    repo.cap("scaffold", "--capability", "billing", "--covers", "Facturas y cobros")
    out = ask(repo, "--change", change)
    assert out["planned"] == {"billing": "Facturas y cobros"}


def test_a_spec_that_declares_no_rules_says_so(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", "Capabilities: none - nothing here changes behaviour\n")
    out = ask(repo, "--change", change)
    assert out["delta"]["none"] == "nothing here changes behaviour"
    assert out["delta"]["entries"] == []


def test_without_a_delta_it_still_answers_and_says_why(repo):
    repo.checkout("-b", "feat")
    repo.write("specs/002-x/spec.md", "# Feature\n\nNo delta here.\n")
    out = ask(repo, "--change", "specs/002-x")
    assert out["spec"] == "specs/002-x/spec.md"
    assert out["delta"] is None
    assert out["delta_errors"] == ["delta section missing"]


def test_without_a_spec_the_feature_has_nothing_to_read(repo):
    repo.write("specs/002-x/plan.md", "x\n")
    out = ask(repo, "--change", "specs/002-x")
    assert out["feature"] == "specs/002-x"
    assert out["spec"] is None and out["delta"] is None


def test_without_a_feature_it_ends_well_because_clarify_reports_it(repo):
    out = ask(repo)
    assert out["feature"] is None and out["spec"] is None
    assert out["capabilities"]["login"]["rules"] == 2


@pytest.mark.parametrize("options", BROKEN_OPTIONS)
def test_broken_init_options_do_not_stop_clarify(repo, options):
    repo.write(".specify/init-options.json", options)
    out = ask(repo)
    assert out["feature"] is None and out["catalog"] is True


def test_the_status_of_the_catalog_is_the_same_data(repo):
    change = feature(repo)
    _, status = repo.cap("status")
    out = ask(repo, "--change", change)
    for key in ("catalog", "capabilities", "planned", "journal_pending"):
        assert out[key] == status[key]


def test_without_a_catalog_there_is_nothing_to_load(repo):
    change = feature(repo)
    shutil.rmtree(str(repo.path / CAT))
    out = ask(repo, "--change", change)
    assert out["catalog"] is False
    assert out["capabilities"] == {} and out["planned"] == {}


def test_an_interrupted_fold_is_reported(repo):
    change = feature(repo)
    (repo.path / JOURNAL).mkdir(parents=True)
    assert ask(repo, "--change", change)["journal_pending"] is True


def test_a_feature_outside_the_repository_counts_as_no_feature(repo, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "spec.md").write_text("# Secret\n", encoding="utf-8")
    out = ask(repo, "--change", os.path.relpath(str(outside), str(repo.path)))
    assert out["feature"] is None and out["spec"] is None


def test_it_writes_nothing(repo):
    change = feature(repo)
    repo.commit("feature")
    before, status = repo.tree(), repo.git("status", "--porcelain").stdout
    ask(repo, "--change", change)
    assert repo.tree() == before
    assert repo.git("status", "--porcelain").stdout == status


# ---------------------------------------------------------------- the steps of the prompt, with the real tool


def gate(repo, *args):
    env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))
    done = subprocess.run([PYTHON, "-I", "-S", str(SCRIPT), "graph", *args, "--root", str(repo.path)], capture_output=True, encoding="utf-8", errors="replace", env=env)
    return done.returncode, json.loads(done.stdout)


def test_the_steps_of_the_prompt_leave_only_the_files_of_the_graph(repo):
    """Everything the prompt runs, in order. The spec, the catalog and every tracked file stay as they were."""
    change = feature(repo)
    repo.commit("feature")
    spec = repo.read(change + "/spec.md")
    catalog = repo.read(INDEX)
    rc, out = gate(repo, "status")
    assert rc == 0 and out["available"] is True
    ask(repo, "--change", change)
    rc, out = gate(repo, "query", "session", "expiry")
    assert rc == 0 and "SessionManager" in out["output"]
    rc, out = gate(repo, "anchors")
    assert "src/auth/session.py::SessionManager" in [row["ref"] for row in out["anchors"]]
    rc, located = repo.cap("locate", "--capability", "login")
    assert rc == 0
    anchor = next(row for row in located["rules"] if row["id"] == "R-session-expiry")["code"][0]["ref"]
    assert gate(repo, "affected", anchor)[0] == 0
    assert repo.read(change + "/spec.md") == spec and repo.read(INDEX) == catalog
    status = repo.git("status", "--porcelain").stdout.split("\n")
    assert [line for line in status if line] == ["?? .graphifyignore"]


# ---------------------------------------------------------------- the prompt


@pytest.mark.parametrize(
    "rule",
    [
        "A conflict or a rule that is not confirmed is a question, never an answer.",
        "is never a settled fact",
        "Copy the text of a rule literally",
        "Say where each line comes from: the catalog, the graph or the code.",
        "never what the requirement is",
        "Do not edit the spec, the delta or the catalog.",
        "Do not install anything.",
        "`graph query` does not work with Spanish",
        "up to **10 anchors in total**",
        "say how many you left out",
        "do not touch its `From`",
        "The graph leaves tests out",
    ],
)
def test_the_prompt_keeps_its_rules(rule):
    assert rule in PROMPT.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "heading",
    [
        "CAPABILITIES CLARIFY CONTEXT (read-only)",
        "Settled facts: do not ask these",
        "Conflicts with approved rules: ask, never settle",
        "Not confirmed: ask",
        "Reach beyond the delta, from the graph: confirm in the code",
        "To look up more",
    ],
)
def test_the_report_separates_facts_from_decisions(heading):
    assert heading in PROMPT.read_text(encoding="utf-8")


def test_the_prompt_stops_without_graphify_and_goes_on_without_code():
    text = PROMPT.read_text(encoding="utf-8")
    assert text.index("{SCRIPT} graph status") < text.index("{SCRIPT} clarify-context")
    assert "If `available` is false, **stop**" in text
    assert "without running it" in text
    assert "`no-code`: there is no code to graph yet." in text
    assert "`update-failed` or `read-failed`: warn visibly that the graph was not used" in text


def test_the_prompt_chooses_from_the_delta_the_covers_and_the_graph():
    text = PROMPT.read_text(encoding="utf-8")
    assert "those named by `capability` in `delta.entries`" in text
    assert "those whose `covers` text the spec touches" in text
    assert "those the graph reveals" in text
    assert text.index("{SCRIPT} graph query") < text.index("{SCRIPT} graph anchors") < text.index("{SCRIPT} locate --capability") < text.index("{SCRIPT} graph affected")
