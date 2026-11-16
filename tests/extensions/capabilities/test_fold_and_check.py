"""The fold and check mechanism, ported from the prototype's cases to real pytest reports."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from . import conftest as capabilities_conftest
from .conftest import (
    CAT,
    EXPIRY_15,
    EXPIRY_20,
    EXPIRY_30,
    HISTORY,
    IMPL,
    INDEX,
    LOCKOUT_3,
    LOCKOUT_5,
    MARK,
    PYTHON,
    SCRIPT,
    SPEC,
    TEST_EXPIRY,
    TEST_LOCKOUT,
    EXT_DIR,
    added,
    block,
    change_expiry,
    delta_block,
    deliver,
    hard_with,
    impl,
    modified,
    removed,
    retirement_block,
    spec_text,
)


def on_branch_reviewed(repo, to=15, text=EXPIRY_15, name="002-x", code=True):
    repo.checkout("-b", "feat")
    change = repo.feature(name, modified(to=text))
    if code:
        repo.set_code(expiry=to)
    repo.review(change)
    return change


# ---------------------------------------------------------------- the delta is verifiable


def test_id_present_with_old_text_fails_and_names_both_texts(repo):
    change = on_branch_reviewed(repo)
    repo.commit("feature, no fold")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "30 minutos", "15 minutos", "delta requires")
    rc, out = repo.cap("check", "--mode", "dev", "--change", change)
    assert rc == 0, "dev warns and does not block"
    assert out["states"][change] == "reviewed"


def test_fold_copies_to_literally_and_tags_the_origin(repo):
    change = on_branch_reviewed(repo)
    repo.folded(change, impl())
    assert "%s (%s)" % (EXPIRY_15, change) in repo.read(SPEC)
    repo.commit("fold")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "ready"


def test_reverting_the_text_by_hand_fails_again(repo):
    change_expiry(repo)
    repo.replace(SPEC, "15 minutos", "30 minutos")
    repo.commit("revert")
    rc, out = repo.ci()
    assert rc == 1


def test_stale_from_is_a_conflict_and_nothing_is_written(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified(frm="La sesión expira tras 45 minutos."))
    before = repo.tree()
    rc, out = repo.cap("review", "--change", change)
    assert rc == 3 and out["status"] == "conflict"
    assert repo.tree() == before


def test_one_wrong_entry_among_several_writes_nothing(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified() + "\n" + modified("R-lockout", "Un texto que no coincide.", LOCKOUT_3))
    before = repo.tree()
    rc, out = repo.cap("review", "--change", change)
    assert rc == 3 and out["status"] == "conflict"
    assert repo.tree() == before


def test_no_rule_change_passes_with_a_reason(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", "Capabilities: none — solo cambia un texto de ayuda\n")
    assert repo.review(change)["status"] == "stamped"
    rc, out = repo.cap("prepare", "--change", change)
    assert (rc, out["status"]) == (0, "no-rule-change")
    repo.commit("no rule change")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "no-rule-change"


@pytest.mark.parametrize(
    "entries, message",
    [
        ("### MODIFY R-x\n- Capability: login\n", "unrecognized block"),
        (modified() + "- Owner: nadie\n", "unknown field Owner"),
        (modified(frm=EXPIRY_15, to=EXPIRY_15), "From equals To"),
        (modified(links="FR-999"), "link FR-999 not found"),
        (modified(capability="001-login"), "invalid capability name"),
        (added("R-a", "x") + "\n" + added("R-a", "y"), "repeated rule"),
        ("### ADDED R-a\n- Capability: login\n- From: algo\n- To: x\n- Links: FR-001\n", "From must be (none)"),
        ("### REMOVED R-a\n- Capability: login\n- From: x\n- To: y\n- Links: FR-001\n", "To must be (none)"),
        ("### REMOVED R-a\n- Capability: login\n- From: x\n- To: (none)\n- Links: FR-001\n", "missing Replaced-By"),
        ("### ADDED R-a\n- Capability: login\n- From: (none)\n- Links: FR-001\n", "missing to"),
        ("### NEW-CAPABILITY pagos\n", "no rule uses it"),
        (modified() + "\nCapabilities: none — motivo\n", "at once"),
    ],
)
def test_invalid_deltas_are_rejected(repo, entries, message):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", entries)
    before = repo.tree()
    rc, out = repo.cap("review", "--change", change)
    assert rc == 2 and out["status"] == "invalid", out
    assert message in str(out["errors"])
    assert repo.tree() == before


def test_rule_added_to_an_unknown_capability_needs_new_capability(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", added("R-a", "x", capability="pagos"))
    rc, out = repo.cap("review", "--change", change)
    assert rc == 3 and "declare NEW-CAPABILITY" in str(out["conflicts"])


def test_a_delta_in_a_spec_must_link_to_it(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified(links="none"))
    rc, out = repo.cap("review", "--change", change)
    assert rc == 2 and "link none not found" in str(out["errors"])


# ---------------------------------------------------------------- two branches


def branch_with(repo, branch, name, text, to):
    repo.checkout("main")
    return change_expiry(repo, name=name, to=to, text=text, branch=branch)


def test_two_branches_from_the_same_rule(repo):
    branch_with(repo, "a", "002-a", EXPIRY_15, 15)
    change_b = branch_with(repo, "b", "003-b", EXPIRY_20, 20)

    rc, out = repo.ci()
    assert rc == 0, "B alone against a main without A has no conflict yet: %s" % out

    repo.checkout("main")
    repo.merge("a")
    repo.checkout("b")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "started from", "30 minutos", "15 minutos", "20 minutos")

    merged = repo.merge("main", ok=False)
    conflicted = repo.git("diff", "--name-only", "--diff-filter=U").stdout.split()
    assert merged.returncode != 0
    assert SPEC in conflicted, "git marks the conflict in the catalog"

    repo.git("checkout", "--ours", "--", *conflicted)
    repo.commit("merge, keep b")
    rc, out = repo.ci()
    assert rc == 1, "resolving in favour of B is not enough"
    assert hard_with(out, "started from")

    repo.replace(change_b + "/spec.md", "- From: " + EXPIRY_30, "- From: " + EXPIRY_15)
    repo.review(change_b, "--accept")
    repo.folded(change_b, impl(expiry="Expira a los 20 minutos."))
    repo.commit("conscious change from 15")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change_b] == "ready"


def test_two_branches_with_the_same_result_is_a_notice(repo):
    branch_with(repo, "a", "002-a", EXPIRY_15, 15)
    branch_with(repo, "b", "003-b", EXPIRY_15, 15)
    repo.checkout("main")
    repo.merge("a")
    repo.checkout("b")
    rc, out = repo.ci()
    assert rc == 0, out
    assert any("already delivered" in note for note in out["notes"])


def test_different_rules_of_one_capability_merge_clean(repo):
    branch_with(repo, "a", "002-a", EXPIRY_15, 15)
    repo.checkout("main")
    repo.checkout("-b", "b")
    change = repo.feature("003-b", modified("R-lockout", LOCKOUT_5, LOCKOUT_3))
    repo.set_code(lockout=3)
    repo.review(change)
    repo.folded(change, impl(expiry="Expira a los 30 minutos.", lockout="Bloquea al tercero."))
    repo.commit("b")
    rc, out = repo.ci()
    assert rc == 0, out
    repo.checkout("main")
    repo.merge("a")
    merged = repo.merge("b", ok=False)
    assert merged.returncode == 0, merged.stdout + merged.stderr
    spec, history = repo.read(SPEC), repo.read(HISTORY)
    assert LOCKOUT_3 in spec and EXPIRY_15 in spec
    assert "specs/002-a" in history and "specs/003-b" in history


def test_same_new_capability_in_two_branches(repo):
    for branch, name, covers, text in (("a", "002-a", "Cobros", "Cobra en dólares."), ("b", "003-b", "Pagos", "Cobra en euros.")):
        repo.checkout("main")
        repo.checkout("-b", branch)
        change = repo.feature(name, "### NEW-CAPABILITY pagos\n- Covers: %s\n\n%s" % (covers, added("R-pago", text, capability="pagos")))
        repo.review(change)
        repo.folded(change, {"pagos": "# pagos\n\n## Rule Status\n\n" + block("R-pago", "x", tests=TEST_EXPIRY, code="`src/other.py`")})
        repo.commit(branch)
    repo.checkout("main")
    repo.merge("a")
    repo.checkout("b")
    repo.merge("main", ok=False)
    conflicted = repo.git("diff", "--name-only", "--diff-filter=U").stdout.split()
    assert CAT + "/pagos/spec.md" in conflicted
    assert INDEX not in conflicted, "merge=union covers the index"
    repo.git("checkout", "--ours", "--", *conflicted)
    repo.commit("merge")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "duplicated capability pagos")


# ---------------------------------------------------------------- interrupted fold


def reference_tree(repo_factory):
    repo = repo_factory()
    change = on_branch_reviewed(repo)
    repo.folded(change, impl())
    return repo.tree()


@pytest.fixture
def fresh(template_repo, tmp_path):
    import shutil

    from .conftest import Repo

    counter = {"n": 0}

    def make():
        counter["n"] += 1
        path = tmp_path / ("r%d" % counter["n"])
        shutil.copytree(str(template_repo), str(path))
        return Repo(path)

    return make


def test_a_cut_at_every_point_blocks_check_and_recover_converges(fresh):
    want = reference_tree(fresh)
    crashed = 0
    for point in range(0, 6):
        repo = fresh()
        change = on_branch_reviewed(repo)
        rc, _ = repo.fold(change, impl(), env={"CAP_CRASH_AFTER": str(point)})
        if rc != 9:
            assert repo.tree() == want
            continue
        crashed += 1
        rc, out = repo.cap("check", "--mode", "dev", "--change", change)
        assert rc == 1 and "run recover" in str(out["hard"])
        for command in ("review", "prepare"):
            rc, out = repo.cap(command, "--change", change)
            assert rc == 4 and out["status"] == "recover-needed"
        rc, out = repo.cap("recover")
        assert (rc, out["status"]) == (0, "recovered")
        assert repo.tree() == want
    assert crashed == 4, "implementation, spec, history and lock are the four writes of this case"


def test_a_cut_before_the_journal_leaves_the_catalog_intact(fresh):
    want = reference_tree(fresh)
    repo = fresh()
    change = on_branch_reviewed(repo)
    prepared = repo.prepare(change)
    repo.draft(prepared, impl())
    rc, _ = repo.cap("apply", "--change", change, "--staged", prepared["staging"], env={"CAP_CRASH_AFTER": "before-journal"})
    assert rc == 9
    assert not (repo.path / ".specify/capabilities/journal").exists()
    assert EXPIRY_30 in repo.read(SPEC)
    rc, out = repo.cap("apply", "--change", change, "--staged", prepared["staging"])
    assert rc == 0, out
    assert repo.tree() == want


def test_a_cut_after_the_last_write_only_needs_closing(fresh):
    want = reference_tree(fresh)
    repo = fresh()
    change = on_branch_reviewed(repo)
    rc, _ = repo.fold(change, impl(), env={"CAP_CRASH_AFTER": "end"})
    assert rc == 9
    rc, out = repo.cap("recover")
    assert (rc, out["status"]) == (0, "recovered")
    assert repo.tree() == want


def test_recover_does_not_overwrite_a_file_edited_after_the_cut(repo):
    change = on_branch_reviewed(repo)
    rc, _ = repo.fold(change, impl(), env={"CAP_CRASH_AFTER": "1"})
    assert rc == 9
    repo.write(SPEC, "editado a mano\n")
    before = repo.tree()
    rc, out = repo.cap("recover")
    assert rc == 4 and out["status"] == "manual"
    assert SPEC in out["edited_since"]
    assert repo.tree() == before


def test_recover_on_a_clean_project(repo):
    rc, out = repo.cap("recover")
    assert (rc, out["status"]) == (0, "clean")


def test_a_failed_recover_keeps_blocking(repo):
    change = on_branch_reviewed(repo)
    repo.fold(change, impl(), env={"CAP_CRASH_AFTER": "1"})
    repo.write(SPEC, "editado a mano\n")
    repo.cap("recover")
    rc, out = repo.cap("check", "--mode", "dev", "--change", change)
    assert rc == 1


# ---------------------------------------------------------------- idempotence and scope


def test_a_second_fold_with_the_same_inputs_changes_nothing(repo):
    change = on_branch_reviewed(repo)
    repo.folded(change, impl())
    first = repo.tree()
    rc, out = repo.cap("prepare", "--change", change)
    assert (rc, out["status"]) == (0, "unchanged")
    assert repo.tree() == first
    assert repo.read(HISTORY).count("| %s |" % change) == 1


def test_foreign_local_changes_stay_out_and_are_listed(repo):
    change = on_branch_reviewed(repo)
    repo.folded(change, impl())
    repo.write("src/other.py", "x = 2\n")
    repo.write("notes-local.txt", "wip\n")
    rc, out = repo.cap("prepare", "--change", change)
    assert out["status"] == "unchanged"
    assert "src/other.py" in out["foreign"] and "notes-local.txt" in out["foreign"]


def test_a_change_inside_the_scope_needs_a_new_fold(repo):
    change = on_branch_reviewed(repo)
    repo.folded(change, impl())
    repo.set_code(expiry=16)
    rc, out = repo.cap("prepare", "--change", change)
    assert out["status"] == "ready"


def test_folding_again_after_a_delta_change_rewrites_its_history_row(repo):
    change = on_branch_reviewed(repo)
    repo.folded(change, impl())
    repo.write(change + "/spec.md", spec_text(modified() + "\n" + modified("R-lockout", LOCKOUT_5, LOCKOUT_3)))
    repo.set_code(lockout=3)
    repo.review(change, "--accept")
    repo.folded(change, impl(lockout="Bloquea al tercero."))
    assert repo.read(HISTORY).count("| %s |" % change) == 1
    assert "MODIFIED R-session-expiry; MODIFIED R-lockout" in repo.read(HISTORY)
    repo.commit("one row")
    rc, out = repo.ci()
    assert rc == 0, out


# ---------------------------------------------------------------- requirement and observation


def test_code_at_30_keeps_the_requirement_at_15_and_blocks_only_in_ci(repo):
    change = on_branch_reviewed(repo, code=False)
    repo.folded(change, impl(expiry="Sigue expirando a los 30 minutos.", expiry_state="discrepant"))
    spec, implementation = repo.read(SPEC), repo.read(IMPL)
    assert "15 minutos" in spec and EXPIRY_30 not in spec
    assert "Sigue expirando a los 30 minutos." in implementation and "State: discrepant" in implementation
    repo.commit("fold discrepant")
    rc, out = repo.cap("check", "--mode", "dev", "--change", change)
    assert rc == 0
    assert out["states"][change] == "prepared"
    rc, out = repo.ci()
    assert rc == 1, "the mapped test passes, and it still blocks"
    assert hard_with(out, "R-session-expiry", "state is discrepant", "Sigue expirando")
    assert out["states"][change] == "prepared"


def test_unverified_blocks_like_discrepant(repo):
    change = on_branch_reviewed(repo)
    repo.folded(change, impl(expiry_state="unverified"))
    repo.commit("fold")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "state is unverified")
    assert out["states"][change] == "prepared"


def test_a_discrepancy_in_another_rule_does_not_block_an_unrelated_pr(repo):
    repo.replace(IMPL, "- Observed: Bloquea al quinto intento.\n- State: conforming", "- Observed: Bloquea al sexto.\n- State: discrepant")
    repo.commit("known discrepancy on main")
    repo.checkout("-b", "other")
    repo.write("docs/notes.txt", "x\n")
    repo.commit("unrelated")
    rc, out = repo.ci()
    assert rc == 0, out


def test_an_approved_delta_on_an_inferred_rule_clears_the_mark(repo):
    repo.checkout("-b", "boot")
    record = CAT + "/_changes/20261104-bootstrap-login"
    repo.write(record + "/capability-delta.md", "# Bootstrap\n\n" + delta_block("### INFERRED R-rate\n- Capability: login\n- From: (none)\n- To: Admite 10 por minuto.\n- Links: none\n"))
    repo.review(record)
    observed = block("R-rate", "Admite 10.", "unverified", "none", "`src/other.py`")
    repo.folded(record, impl(expiry="Expira a los 30 minutos.", more=observed), "--no-tasks")
    repo.commit("bootstrap")
    assert "**R-rate** [inferred]" in repo.read(SPEC)
    deliver(repo, "boot", "approve")
    change = repo.feature("002-rate", modified("R-rate", "Admite 10 por minuto.", "Admite 5 por minuto."))
    repo.review(change)
    repo.folded(change, impl(expiry="Expira a los 30 minutos.", more=block("R-rate", "Admite 5.", tests=TEST_EXPIRY, code="`src/other.py`")))
    repo.commit("approved")
    assert "[inferred]" not in repo.read(SPEC)
    rc, out = repo.ci()
    assert rc == 0, out


# ---------------------------------------------------------------- evidence


def test_failing_mapped_test_blocks(repo):
    change_expiry(repo)
    rc, out = repo.ci(fail="test_expiry")
    assert rc == 1
    assert hard_with(out, "mapped test %s failed" % TEST_EXPIRY)


def test_stale_observation_is_rejected_at_the_pr_head(repo):
    change_expiry(repo)
    repo.set_code(expiry=30)
    repo.commit("regression after fold, with its test")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-session-expiry", "observation is stale", "src/auth/session.py")


def test_changing_a_mapped_test_after_fold_is_stale_too(repo):
    change_expiry(repo)
    repo.write("tests/auth/test_session.py", repo.read("tests/auth/test_session.py") + "\n# weaker now\n")
    repo.commit("test edited after fold")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "observation is stale", "tests/auth/test_session.py")


def test_conforming_without_a_code_anchor_is_not_ready(repo):
    change = on_branch_reviewed(repo)
    repo.folded(change, impl().replace("### R-session-expiry\n- Observed: Expira a los 15 minutos.\n- State: conforming\n- Code: `src/auth/session.py::SessionManager`", "### R-session-expiry\n- Observed: Expira a los 15 minutos.\n- State: conforming\n- Code: none"))
    repo.commit("fold")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-session-expiry", "no code anchor")


def test_no_mapped_test_is_not_ready(repo):
    change = on_branch_reviewed(repo)
    repo.folded(change, impl(expiry_tests="none"))
    repo.commit("fold")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-session-expiry", "no mapped test")


# ---------------------------------------------------------------- tasks and skipped hooks


def test_open_tasks_stop_the_fold(repo):
    change = on_branch_reviewed(repo)
    repo.write(change + "/tasks.md", "- [x] T001 done in src/auth/session.py\n- [ ] T002 convergence task\n")
    before = repo.tree()
    rc, out = repo.cap("prepare", "--change", change)
    assert rc == 3 and out["status"] == "blocked" and "1 open tasks" in out["reason"]
    assert repo.tree() == before


def test_a_task_for_after_the_merge_does_not_hold_the_fold(repo):
    """A deploy or a change to production data can only be done once the change is merged: its box stays open, and marked."""
    change = on_branch_reviewed(repo)
    later = "- [ ] T002 [post-merge] Deploy the API\n- [ ] T003 [US1] [Post-Merge] Delete the old rows in production\n"
    repo.write(change + "/tasks.md", "- [x] T001 done in src/auth/session.py\n" + later)
    rc, out = repo.cap("prepare", "--change", change)
    assert rc == 0 and out["status"] == "ready" and out["post_merge"] == 2, out
    repo.folded(change, impl())
    repo.commit("folded, with two tasks for after the merge")
    rc, out = repo.cap("check", "--mode", "dev", "--base", "main", "--change", change)
    assert rc == 0 and "%s: 2 open tasks for after the merge, marked [post-merge]" % change in out["notes"], out
    assert not [note for note in out["notes"] if note.endswith("open tasks")]
    rc, out = repo.ci()
    assert rc == 0 and out["states"][change] == "ready", out
    # One open task for after the merge, and one that is of the code: that one holds the fold.
    repo.write(change + "/tasks.md", "- [ ] T001 change src/auth/session.py\n- [ ] T002 [post-merge] Deploy the API\n")
    rc, out = repo.cap("prepare", "--change", change)
    assert rc == 3 and out["status"] == "blocked" and out["reason"] == "1 open tasks", out
    rc, out = repo.cap("check", "--mode", "dev", "--base", "main", "--change", change)
    assert "%s: 1 open tasks" % change in out["notes"] and "%s: 1 open task for after the merge, marked [post-merge]" % change in out["notes"], out
    # With none of them, nothing is said.
    repo.write(change + "/tasks.md", "- [x] T001 done in src/auth/session.py\n")
    rc, out = repo.cap("prepare", "--change", change)
    assert "post_merge" not in out
    rc, out = repo.cap("check", "--mode", "dev", "--base", "main", "--change", change)
    assert not [note for note in out["notes"] if "after the merge" in note]


def test_no_tasks_file_asks_for_an_explicit_flag(repo):
    change = on_branch_reviewed(repo)
    (repo.path / change / "tasks.md").unlink()
    rc, out = repo.cap("prepare", "--change", change)
    assert rc == 3 and "no tasks.md" in out["reason"]
    rc, out = repo.cap("prepare", "--change", change, "--no-tasks")
    assert rc == 0 and out["status"] == "ready"


def test_skipped_hooks_fail_for_both_causes(repo):
    repo.checkout("-b", "feat")
    repo.feature("002-x", modified())
    repo.commit("no review, no fold")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "not reviewed")
    assert hard_with(out, "delta requires")


def test_the_real_template_section_left_unfilled_fails(repo):
    repo.checkout("-b", "feat")
    template = (EXT_DIR / "templates" / "spec-template.md").read_text(encoding="utf-8")
    repo.write("specs/002-x/spec.md", template)
    repo.commit("template placeholder left")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "delta is empty")


def test_a_new_spec_with_no_section_fails(repo):
    repo.checkout("-b", "feat")
    repo.write("specs/002-x/spec.md", "# Feature\n\n## Requirements\n\n- **FR-001**: x\n")
    repo.commit("spec with no delta at all")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "without a capability delta")


# ---------------------------------------------------------------- changes after review


def test_a_requirement_changed_after_review_is_presented_and_not_sealed(repo):
    change = on_branch_reviewed(repo)
    repo.replace(change + "/spec.md", "after 15 minutes", "after 10 minutes")
    before = repo.tree()
    rc, out = repo.cap("review", "--change", change)
    assert rc == 3 and out["status"] == "changed"
    assert "FR-001" in out["linked"]
    assert out["rules"] == ["R-session-expiry"], "the person has to know which approved rule is at stake"
    assert out["other_text"] is False
    assert repo.tree() == before

    rc, out = repo.cap("prepare", "--change", change)
    assert rc == 3 and out["status"] == "needs-review"

    repo.review(change, "--accept")
    rc, out = repo.cap("review", "--change", change)
    assert (rc, out["status"]) == (0, "unchanged")


def test_template_duplicated_by_a_preset_is_invalid(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified())
    repo.write(change + "/spec.md", repo.read(change + "/spec.md") + "\n" + delta_block(modified()))
    rc, out = repo.cap("review", "--change", change)
    assert rc == 2 and "more than once" in str(out["errors"])


def test_section_lost_to_a_preset_is_inserted_once_and_must_be_completed(repo):
    repo.checkout("-b", "feat")
    change = "specs/002-x"
    repo.write(change + "/spec.md", "# Feature\n\n## Requirements\n\n- **FR-001**: x\n")
    rc, out = repo.cap("ensure", "--change", change)
    assert out["status"] == "inserted"
    first = repo.read(change + "/spec.md")
    assert MARK in first
    rc, out = repo.cap("ensure", "--change", change)
    assert out["status"] == "present"
    assert repo.read(change + "/spec.md") == first
    rc, out = repo.cap("review", "--change", change)
    assert rc == 2 and "empty" in str(out["errors"])


def test_a_change_directory_outside_the_repository_is_refused(repo, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "spec.md").write_text("# fuera\n", encoding="utf-8")
    for command in ("ensure", "review", "prepare"):
        rc, out = repo.cap(command, "--change", str(outside))
        assert rc == 2 and "outside the repository" in str(out["errors"])
    assert (outside / "spec.md").read_text(encoding="utf-8") == "# fuera\n"


def test_clarify_edits_are_detected(repo):
    change = on_branch_reviewed(repo)
    original = repo.read(change + "/spec.md")

    repo.write(change + "/spec.md", original[:original.index("## Capability Delta")])
    rc, out = repo.cap("review", "--change", change)
    assert rc == 2 and "missing" in str(out["errors"])

    repo.write(change + "/spec.md", original.replace("- From: " + EXPIRY_30, "- From: La sesión expira tras 45 minutos."))
    rc, out = repo.cap("review", "--change", change)
    assert rc == 3 and out["status"] == "conflict"

    repo.write(change + "/spec.md", original.replace("- To: " + EXPIRY_15, "- To: La sesión expira tras 10 minutos."))
    rc, out = repo.cap("review", "--change", change)
    assert rc == 3 and out["status"] == "changed" and out["delta_changed"] is True


def test_text_outside_the_tracked_keys_is_reported_as_such_and_not_sealed(repo):
    change = on_branch_reviewed(repo)
    repo.replace(change + "/spec.md", "## Requirements", "## Clarifications\n\n- Q: From when? -> A: From login.\n\n## Requirements")
    before = repo.tree()
    rc, out = repo.cap("review", "--change", change)
    assert rc == 3 and out["status"] == "changed"
    assert (out["sections"], out["linked"], out["rules"], out["other_text"]) == ([], [], [], True)
    assert repo.tree() == before

    rc, out = repo.cap("prepare", "--change", change)
    assert rc == 3 and out["status"] == "needs-review"


def test_a_changed_requirement_no_rule_links_to_names_no_rule(repo):
    change = on_branch_reviewed(repo)
    repo.replace(change + "/spec.md", "- **FR-001**:", "- **FR-009**: System MUST log out.\n- **FR-001**:")
    rc, out = repo.cap("review", "--change", change)
    assert rc == 3 and out["sections"] == ["FR-009"]
    assert (out["linked"], out["rules"], out["other_text"]) == ([], [], False)


# ---------------------------------------------------------------- changes outside specify


def test_a_bugfix_without_a_rule_change_passes_with_a_notice_while_its_tests_pass(repo):
    repo.checkout("-b", "fix")
    repo.write("src/auth/session.py", repo.read("src/auth/session.py") + "\n# fix\n")
    repo.commit("fix without rule change")
    rc, out = repo.ci()
    assert rc == 0, out
    assert any("without a delta" in note for note in out["notes"])
    rc, out = repo.ci(fail="test_expiry")
    assert rc == 1
    assert hard_with(out, "anchored code changed", TEST_EXPIRY, "failed")


def test_a_bugfix_that_changes_a_rule_uses_a_record(repo):
    repo.checkout("-b", "fix")
    record = CAT + "/_changes/20261104-fix-expiry"
    repo.write(record + "/capability-delta.md", "# Fix\n\n" + delta_block(modified(links="none")))
    repo.set_code(expiry=15)
    repo.review(record)
    rc, out = repo.cap("prepare", "--change", record)
    assert rc == 3 and "no tasks.md" in out["reason"]
    repo.folded(record, impl(), "--no-tasks")
    repo.commit("fold fix")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][record] == "ready"


def test_a_record_under_specify_bugs_is_discovered(repo):
    repo.checkout("-b", "fix")
    record = ".specify/bugs/fix-expiry"
    repo.write(record + "/capability-delta.md", "# Fix\n\n" + delta_block(modified(links="none")))
    repo.set_code(expiry=15)
    repo.review(record)
    repo.folded(record, impl(), "--no-tasks")
    repo.commit("bug change")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][record] == "ready"


# ---------------------------------------------------------------- several capabilities and retired ids


def test_a_delta_over_two_capabilities_keeps_them_and_the_index_coherent(repo):
    repo.checkout("-b", "feat")
    entries = modified() + "\n### NEW-CAPABILITY pagos\n- Covers: Cobros\n\n" + added("R-pago", "Cobra en dólares.", capability="pagos")
    change = repo.feature("002-x", entries)
    repo.set_code(expiry=15)
    repo.review(change)
    repo.folded(change, {"login": impl(), "pagos": "# pagos\n\n## Rule Status\n\n" + block("R-pago", "Cobra.", tests=TEST_LOCKOUT, code="`src/other.py`")})
    assert "[pagos](pagos/spec.md) | Cobros" in repo.read(INDEX)
    for name in ("spec.md", "implementation.md", "history.md"):
        assert (repo.path / CAT / "pagos" / name).is_file()
    assert EXPIRY_15 in repo.read(SPEC)
    repo.commit("two capabilities")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "ready"


def retired_on_main(repo):
    repo.checkout("-b", "rem")
    change = repo.feature("002-rem", removed("R-lockout", LOCKOUT_5))
    repo.review(change)
    repo.folded(change, impl(expiry="Expira a los 30 minutos.", with_lockout=False, retirement=retirement_block("R-lockout", change)))
    repo.commit("remove")
    deliver(repo, "rem", "reuse")


def test_a_retired_id_is_not_reused(repo):
    retired_on_main(repo)
    change = repo.feature("003-reuse", added("R-lockout", "Otra regla con el mismo ID."))
    before = repo.tree()
    rc, out = repo.cap("review", "--change", change)
    assert rc == 3 and "retired" in str(out["conflicts"])
    assert repo.tree() == before


def test_a_retired_id_forced_by_hand_is_rejected(repo):
    retired_on_main(repo)
    change = repo.feature("003-reuse", added("R-lockout", "Otra regla con el mismo ID."))
    repo.replace(SPEC, "## Rules\n\n", "## Rules\n\n- **R-lockout**: Otra regla con el mismo ID. (%s)\n\n" % change)
    repo.commit("forced")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-lockout", "retired")


@pytest.mark.parametrize(
    "draft, message",
    [
        ("# login\n\n## Rule Status\n", "no Rule Status block"),
        (impl(expiry_tests="tests/no/existe.py::test_x"), "anchor does not exist"),
        (impl(expiry_state="aprobado"), "invalid state"),
    ],
    ids=["no-block", "missing-anchor", "invalid-state"],
)
def test_an_invalid_draft_is_not_published(repo, draft, message):
    change = on_branch_reviewed(repo)
    before = repo.tree()
    rc, out = repo.fold(change, draft)
    assert rc == 2 and out["status"] == "invalid-staging"
    assert message in str(out["errors"])
    assert repo.tree() == before


@pytest.mark.parametrize(
    "code, expected",
    [
        ("`src/auth/session.py::SessionManager`", 0),
        ("`src/auth/session.py::.expiry()`", 0),
        ("`src/auth/session.py`", 0),
        ("`src/auth/session.py::Ghost`", 2),
        ("`src/auth/session.py::SessionManagerX`", 2),
        ("`src/auth/ghost.py::SessionManager`", 2),
    ],
    ids=["class", "method", "file-only", "invented-symbol", "partial-word", "missing-file"],
)
def test_a_code_anchor_must_name_something_that_is_in_the_file(repo, code, expected):
    change = on_branch_reviewed(repo)
    default = "`src/auth/session.py::SessionManager`"
    draft = impl().replace("Expira a los 15 minutos.\n- State: conforming\n- Code: " + default, "Expira a los 15 minutos.\n- State: conforming\n- Code: " + code)
    before = repo.tree()
    rc, out = repo.fold(change, draft)
    assert rc == expected, out
    if expected:
        assert "anchor does not exist" in str(out["errors"])
        assert repo.tree() == before


def test_a_test_reference_with_class_and_variant_resolves(repo):
    change = on_branch_reviewed(repo)
    repo.write("tests/auth/test_group.py", "class TestGroup:\n    def test_in_class(self):\n        pass\n")
    rc, out = repo.fold(change, impl(expiry_tests="tests/auth/test_group.py::OtherGroup::test_in_class"))
    assert rc == 2
    assert "anchor does not exist" in str(out["errors"])
    rc, out = repo.fold(change, impl(expiry_tests="tests/auth/test_group.py::TestGroup::test_in_class[1]"))
    assert rc == 0, out


def test_a_status_edit_with_an_invented_symbol_is_caught_without_a_delta(repo):
    repo.checkout("-b", "observe")
    repo.replace(IMPL, "### R-lockout\n- Observed: Bloquea al quinto intento.\n- State: conforming\n- Code: `src/auth/session.py::SessionManager`", "### R-lockout\n- Observed: Otra lectura.\n- State: conforming\n- Code: `src/auth/session.py::Ghost`")
    repo.commit("hand edit of the anchor")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-lockout", "anchor does not exist", "Ghost")


def test_a_feature_with_timestamp_numbering_goes_through_the_whole_flow(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("20260319-143022-user-auth", modified())
    repo.set_code(expiry=15)
    repo.review(change)
    repo.folded(change, impl())
    repo.commit("timestamp feature")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "ready"
    assert "(specs/20260319-143022-user-auth)" in repo.read(SPEC)


def test_a_pr_that_edits_the_extension_leaves_a_notice_and_changes_no_verdict(repo):
    repo.checkout("-b", "x")
    repo.config(allow_manual_evidence="true")
    repo.commit("config change")
    rc, out = repo.ci()
    assert rc == 0, out
    assert any("edits the extension that evaluates it" in note and "capabilities-config.yml" in note for note in out["notes"])


def test_a_missing_draft_directory_is_invalid(repo):
    change = on_branch_reviewed(repo)
    prepared = repo.prepare(change)
    (repo.path / prepared["staging"] / "login" / "implementation.md").unlink()
    rc, out = repo.cap("apply", "--change", change, "--staged", prepared["staging"])
    assert rc == 2 and out["status"] == "invalid-staging"


# ---------------------------------------------------------------- exit codes and setup


def with_a_remote(repo, tmp_path):
    """main follows origin/main, as in a clone."""
    origin = tmp_path / "origin.git"
    repo.git("clone", "-q", "--bare", str(repo.path), str(origin))
    repo.git("remote", "add", "origin", str(origin))
    repo.git("fetch", "-q", "origin")
    repo.git("branch", "-q", "--set-upstream-to=origin/main", "main")


def test_a_base_that_fell_behind_its_remote_is_compared_at_the_remote(repo, tmp_path):
    """The local main is an old picture of the base: what main took since would read as changed by this branch."""
    with_a_remote(repo, tmp_path)
    change = change_expiry(repo)
    repo.git("push", "-q", "origin", "feat:main")
    repo.git("fetch", "-q", "origin")
    repo.checkout("-b", "next", "origin/main")
    following = repo.feature("003-y", modified(frm=EXPIRY_15, to=EXPIRY_20))
    repo.set_code(expiry=20)
    repo.review(following)
    repo.folded(following, impl(expiry="Expira a los 20 minutos."))
    repo.commit("the next change")
    rc, out = repo.cap("check", "--mode", "dev", "--base", "main")
    assert rc == 0 and out["hard"] == [], out
    assert "main is 1 commit behind origin/main: compared with origin/main; git fetch origin main:main brings it up to date" in out["notes"]
    assert change not in out["states"] and following in out["states"], "main took the first one, on the remote: it is not of this branch"
    # Named as the remote, or by its commit, nothing is behind anything.
    for base in ("origin/main", repo.git("rev-parse", "origin/main").stdout.strip()):
        rc, out = repo.cap("check", "--mode", "dev", "--base", base)
        assert rc == 0 and not [note for note in out["notes"] if "behind" in note or "diverged" in note], out
    # Two commits behind.
    repo.git("push", "-q", "origin", "next:main")
    repo.git("fetch", "-q", "origin")
    rc, out = repo.cap("check", "--mode", "dev", "--base", "main")
    assert rc == 0 and [note for note in out["notes"] if note.startswith("main is 2 commits behind origin/main: compared with origin/main")], out
    # A branch that follows another local branch: there is nothing to fetch, and the note does not say to.
    repo.git("branch", "-q", "-f", "old", "main")
    repo.git("branch", "-q", "local/next", "next")
    repo.git("branch", "-q", "--set-upstream-to=local/next", "old")
    rc, out = repo.cap("check", "--mode", "dev", "--base", "old")
    assert rc == 0 and "old is 2 commits behind local/next: compared with local/next" in out["notes"], out


def test_a_base_that_went_its_own_way_is_compared_as_asked_and_said(repo, tmp_path):
    with_a_remote(repo, tmp_path)
    change_expiry(repo)
    repo.git("push", "-q", "origin", "feat:main")
    repo.git("fetch", "-q", "origin")
    repo.checkout("main")
    repo.write("src/other.py", "x = 2\n")
    repo.commit("only here")
    repo.checkout("feat")
    rc, out = repo.cap("check", "--mode", "dev", "--base", "main")
    assert rc == 0, out
    assert "main and origin/main have diverged: compared with main, as asked, which lacks 1 commit of origin/main" in out["notes"]
    assert not [note for note in out["notes"] if "compared with origin/main" in note]
    # A base that is ahead of its remote, and not behind, is the newest there is.
    repo.git("push", "-q", "origin", "feat:refs/heads/feat")
    repo.git("branch", "-q", "--set-upstream-to=origin/feat", "feat")
    repo.checkout("-b", "later")
    repo.checkout("feat")
    repo.write("src/other.py", "x = 3\n")
    repo.commit("ahead of the remote")
    repo.checkout("later")
    rc, out = repo.cap("check", "--mode", "dev", "--base", "feat")
    assert rc == 0 and not [note for note in out["notes"] if "behind" in note or "diverged" in note], out


@pytest.mark.parametrize(
    "args",
    [
        ("check", "--mode", "ci"),
        ("check", "--mode", "dev", "--combined"),
        ("check", "--mode", "ci", "--base", "no-such-ref"),
        ("check", "--mode", "ci", "--base", "main", "--report", "nothing.xml"),
        ("check", "--mode", "nope"),
        ("nonsense",),
        ("apply", "--change", "specs/001-login"),
        ("status", "--capability", "ghost"),
    ],
)
def test_bad_invocations_exit_2(repo, args):
    rc, _ = repo.cap(*args)
    assert rc == 2


def test_an_unparsable_report_exits_2(repo):
    repo.write("broken.xml", "<testsuite")
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", "broken.xml")
    assert rc == 2 and "not valid XML" in str(out["errors"])


def test_check_reports_project_problems_only_as_1(repo):
    repo.checkout("-b", "feat")
    repo.feature("002-x", "### MODIFY R-x\n")
    repo.commit("invalid delta")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "unrecognized block")


def test_setup_appends_once_and_keeps_what_is_there(repo):
    repo.write(".gitignore", "mine\n")
    repo.write(".gitattributes", "*.png binary\n")
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified())
    out = repo.review(change)
    assert sorted(out["setup"]) == [".gitattributes", ".gitignore"]
    first = repo.read(".gitignore"), repo.read(".gitattributes")
    assert first[0].startswith("mine\n") and ".specify/capabilities/" in first[0]
    assert first[1].startswith("*.png binary\n") and "specs/_capabilities/index.md merge=union" in first[1]
    assert repo.review(change, "--accept")["setup"] == []
    assert (repo.read(".gitignore"), repo.read(".gitattributes")) == first


def test_a_failed_review_does_not_touch_the_project(repo):
    repo.write(".gitignore", "mine\n")
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified(frm="Otro texto."))
    repo.cap("review", "--change", change)
    assert repo.read(".gitignore") == "mine\n"


def test_digests_ignore_line_endings(repo):
    change = change_expiry(repo)
    path = repo.path / "src/auth/session.py"
    data = path.read_bytes()
    # Flip them, whichever way this platform wrote them. Git may normalize them, so the commit can be empty.
    path.write_bytes(data.replace(b"\r\n", b"\n") if b"\r\n" in data else data.replace(b"\n", b"\r\n"))
    repo.git("add", "-A")
    repo.git("commit", "--allow-empty", "-qm", "line endings changed")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "ready"


def test_status_reports_the_catalog_without_writing(repo):
    before = repo.tree()
    rc, out = repo.cap("status")
    assert rc == 0
    assert out["catalog"] is True and out["journal_pending"] is False
    assert out["capabilities"]["login"]["covers"] == "Autenticación y sesión"
    assert out["capabilities"]["login"]["rules"] == 2
    rc, out = repo.cap("status", "--capability", "login")
    assert out["rules"]["R-session-expiry"]["text"] == EXPIRY_30
    assert out["rule_status"]["R-session-expiry"]["tests"] == [TEST_EXPIRY]
    assert repo.tree() == before


# ---------------------------------------------------------------- the rule Windows applies to fsync

# Windows refuses fsync on a descriptor opened read-only and POSIX allows it, so a fold could pass on
# Linux and macOS and still die on Windows. This runs a script under the rule of Windows.
STRICT_FSYNC = """\
import errno, fcntl, os, runpy, stat, sys

real_fsync = os.fsync

def strict_fsync(descriptor):
    regular = stat.S_ISREG(os.fstat(descriptor).st_mode)
    if regular and fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY:
        raise OSError(errno.EBADF, "Bad file descriptor")
    real_fsync(descriptor)

os.fsync = strict_fsync
sys.argv[0] = {target!r}
runpy.run_path({target!r}, run_name="__main__")
"""
needs_posix = pytest.mark.skipif(os.name != "posix", reason="Windows applies the real rule, so every fold there covers this")


def under_strict_fsync(tmp_path, target):
    wrapper = tmp_path / "strict_fsync.py"
    wrapper.write_text(STRICT_FSYNC.format(target=str(target)), encoding="utf-8")
    return wrapper


@needs_posix
@pytest.mark.parametrize(("mode", "refused"), [("rb", True), ("r+b", False)])
def test_the_strict_fsync_refuses_only_a_read_only_descriptor(tmp_path, mode, refused):
    data = tmp_path / "data"
    data.write_bytes(b"x")
    probe = tmp_path / "probe.py"
    probe.write_text("import os\nwith open(%r, %r) as handle:\n    os.fsync(handle.fileno())\n" % (str(data), mode), encoding="utf-8")
    done = subprocess.run([PYTHON, "-I", "-S", str(under_strict_fsync(tmp_path, probe))], capture_output=True, encoding="utf-8")
    assert (done.returncode != 0) is refused, done.stderr
    assert ("Bad file descriptor" in done.stderr) is refused


@needs_posix
def test_a_fold_publishes_under_the_fsync_rule_of_windows(repo, tmp_path, monkeypatch):
    change = on_branch_reviewed(repo)
    monkeypatch.setattr(capabilities_conftest, "SCRIPT", under_strict_fsync(tmp_path, SCRIPT))
    repo.folded(change, impl())
    assert EXPIRY_15 in repo.read(SPEC)


# ---------------------------------------------------------------- the index: what a capability covers, and where its code starts


ROW = "| [login](login/spec.md) | %s | consolidated | %s |"
COVERS = "Autenticación y sesión"
ENTRY = "src/auth/session.py::SessionManager"
OTHER_ENTRY = "src/other.py::x"


def test_index_sets_what_a_capability_covers_and_its_overview_follows(repo):
    assert ROW % (COVERS, "`%s`" % ENTRY) in repo.read(INDEX) and "## Overview\n%s\n" % COVERS in repo.read(SPEC)
    rc, out = repo.cap("index", "--capability", "login", "--covers", "  Sesión y   bloqueo de la cuenta ")
    assert rc == 0, out
    assert sorted(out.pop("written")) == [INDEX, SPEC]
    assert out == {"status": "updated", "capability": "login", "covers": "Sesión y bloqueo de la cuenta", "entry": ENTRY, "overview": "updated"}
    assert ROW % ("Sesión y bloqueo de la cuenta", "`%s`" % ENTRY) in repo.read(INDEX)
    assert "## Overview\nSesión y bloqueo de la cuenta\n" in repo.read(SPEC) and COVERS not in repo.read(SPEC)
    rc, out = repo.cap("check")
    assert rc == 0 and out["hard"] == [], out
    before = repo.tree()
    rc, out = repo.cap("index", "--capability", "login", "--covers", "Sesión y bloqueo de la cuenta")
    assert rc == 0 and (out["status"], out["written"], out["overview"]) == ("unchanged", [], "kept") and repo.tree() == before
    # An Overview a person wrote is theirs: it does not follow.
    repo.replace(SPEC, "## Overview\nSesión y bloqueo de la cuenta\n", "## Overview\nTodo lo de entrar, contado a mano.\n")
    rc, out = repo.cap("index", "--capability", "login", "--covers", "Entrar y salir")
    assert rc == 0 and (out["overview"], out["written"]) == ("kept", [INDEX]), out
    assert "Todo lo de entrar, contado a mano." in repo.read(SPEC) and ROW % ("Entrar y salir", "`%s`" % ENTRY) in repo.read(INDEX)


def test_index_sets_the_entry_point_to_code_that_is_there(repo):
    rc, out = repo.cap("index", "--capability", "login", "--entry", OTHER_ENTRY)
    assert rc == 0 and (out["status"], out["entry"], out["covers"], out["written"]) == ("updated", OTHER_ENTRY, COVERS, [INDEX]), out
    assert ROW % (COVERS, "`%s`" % OTHER_ENTRY) in repo.read(INDEX)
    rc, out = repo.cap("index", "--capability", "login", "--entry", "`%s`" % ENTRY, "--covers", "Entrar")
    assert rc == 0 and (out["entry"], out["covers"]) == (ENTRY, "Entrar") and ROW % ("Entrar", "`%s`" % ENTRY) in repo.read(INDEX)
    for gone in ("src/auth/gone.py::SessionManager", "src/auth/session.py::NoSuchName"):
        before = repo.tree()
        rc, out = repo.cap("index", "--capability", "login", "--entry", gone)
        assert rc == 2 and "the entry point does not exist: %s" % gone in out["errors"][0], out
        assert repo.tree() == before
    rc, out = repo.cap("index", "--capability", "login", "--entry", "none")
    assert rc == 0 and out["entry"] == "none" and ROW % ("Entrar", "none") in repo.read(INDEX)


@pytest.mark.parametrize(
    "args, needle",
    [
        (("--capability", "login"), "index --capability takes --covers, --entry, or both"),
        (("--capability", "Login", "--covers", "x"), "index --capability takes a name matching"),
        (("--covers", "x"), "index --capability takes a name matching"),
        (("--entry", ENTRY), "index --capability takes a name matching"),
        (("--capability", "login", "--covers", "a | b"), "index takes --covers as one line of text without |"),
        (("--capability", "login", "--covers", "   "), "index takes --covers as one line of text without |"),
        (("--capability", "ghost", "--covers", "x"), "ghost has no row in index.md"),
        (("--capability", "payments", "--covers", "x"), "payments has no row in index.md"),
        (("--capability", "login", "--covers", "x", "--rebuild"), "index takes --rebuild or --capability, not both"),
        ((), "index takes --rebuild, or --capability with --covers, --entry or both"),
    ],
)
def test_index_refuses_what_it_cannot_set(repo, args, needle):
    rc, out = repo.cap("scaffold", "--capability", "payments", "--covers", "Cobros")
    assert rc == 0, out
    before = repo.tree()
    rc, out = repo.cap("index", *args)
    assert rc == 2 and needle in out["errors"][0], out
    assert repo.tree() == before


def test_index_waits_for_an_interrupted_fold(repo):
    repo.write(".specify/capabilities/journal", "{}")
    before = repo.read(INDEX)
    rc, out = repo.cap("index", "--capability", "login", "--covers", "Entrar")
    assert (rc, out["status"]) == (4, "recover-needed") and repo.read(INDEX) == before


def test_check_says_when_an_entry_point_names_nothing(repo):
    """A retirement can take away the code an index row points to, and nothing else would say so."""
    repo.checkout("-b", "feat")
    assert repo.cap("index", "--capability", "login", "--entry", OTHER_ENTRY)[0] == 0
    os.remove(str(repo.path / "src" / "other.py"))
    repo.commit("the code of the entry point is gone")
    message = "index.md: the entry point of login does not exist: %s; set it with capabilities.py index --capability login --entry <path::symbol>" % OTHER_ENTRY
    rc, out = repo.cap("check", "--mode", "dev", "--base", "main")
    assert rc == 0 and message in out["notes"], out
    rc, out = repo.cap("check")
    assert rc == 0 and message in out["notes"], "with no base to compare with, too"
    rc, out = repo.ci()
    assert rc == 1 and message in out["hard"], out
    assert repo.cap("index", "--capability", "login", "--entry", ENTRY)[0] == 0
    rc, out = repo.ci()
    assert not [line for line in out["hard"] + out["notes"] if "entry point" in line], out
    assert repo.cap("index", "--capability", "login", "--entry", "none")[0] == 0
    rc, out = repo.ci()
    assert not [line for line in out["hard"] + out["notes"] if "entry point" in line], "none is no promise"


def test_a_fold_that_retires_rules_repairs_the_entry_point_and_asks_to_read_covers(repo):
    assert repo.cap("index", "--capability", "login", "--entry", OTHER_ENTRY)[0] == 0
    repo.commit("the entry point is in another file")
    repo.checkout("-b", "rem")
    change = repo.feature("002-rem", removed("R-lockout", LOCKOUT_5))
    os.remove(str(repo.path / "src" / "other.py"))
    repo.review(change)
    out = repo.folded(change, impl(expiry="Expira a los 30 minutos.", with_lockout=False, retirement=retirement_block("R-lockout", change)))
    assert out["entry_points"] == [{"capability": "login", "was": OTHER_ENTRY, "now": ENTRY}]
    assert out["review_covers"] == [{"capability": "login", "covers": COVERS, "removed": 1, "left": 1}]
    assert ROW % (COVERS, "`%s`" % ENTRY) in repo.read(INDEX)


def test_a_fold_that_retires_nothing_leaves_the_index_row_as_it_is(repo):
    assert repo.cap("index", "--capability", "login", "--entry", OTHER_ENTRY)[0] == 0
    repo.commit("the entry point is in another file")
    change = on_branch_reviewed(repo)
    out = repo.folded(change, impl())
    assert "entry_points" not in out and "review_covers" not in out, out
    assert ROW % (COVERS, "`%s`" % OTHER_ENTRY) in repo.read(INDEX), "an entry point that is there is kept, whatever the first anchor is"


def test_index_rebuild_replaces_an_entry_point_that_names_nothing(repo):
    assert repo.cap("index", "--capability", "login", "--entry", OTHER_ENTRY)[0] == 0
    rc, out = repo.cap("index", "--rebuild")
    assert rc == 0 and out["status"] == "unchanged", "it is there: rebuilding keeps it"
    os.remove(str(repo.path / "src" / "other.py"))
    rc, out = repo.cap("index", "--rebuild")
    assert rc == 0 and out["status"] == "rebuilt" and ROW % (COVERS, "`%s`" % ENTRY) in repo.read(INDEX), out


# ---------------------------------------------------------------- REOBSERVED: the code of a rule moved, and what the rule says did not


LOCKOUT_LINE = "- **R-lockout**: %s (specs/001-login)" % LOCKOUT_5
MOVED_NOTE = "R-lockout: anchored code changed without a delta; if the rule still holds, declare REOBSERVED R-lockout and the fold looks at it again"


def reobserved(rule="R-lockout", reason="El archivo cambió por otra regla; el bloqueo es el mismo.", capability="login", more=""):
    return "### REOBSERVED %s\n- Capability: %s\n- Reason: %s\n%s" % (rule, capability, reason, more)


def test_a_rule_whose_code_moved_is_observed_again_without_changing_it(repo):
    """The expiry changes in the file the lockout is anchored to. The lockout still holds: the fold looks at it again, and nothing else."""
    change = change_expiry(repo)
    rc, out = repo.cap("check", "--mode", "dev", "--base", "main")
    assert MOVED_NOTE in out["notes"], out
    repo.write(change + "/spec.md", repo.read(change + "/spec.md").rstrip("\n") + "\n\n" + reobserved())
    repo.review(change, "--accept")
    spec_before = repo.read(SPEC)
    repo.folded(change, impl(lockout="Bloquea al quinto intento, con LOCK_AT."))
    repo.commit("the lockout, observed again")
    assert repo.read(SPEC) == spec_before and LOCKOUT_LINE in spec_before, "its text, its origin and its marks are the ones it had"
    assert "### R-lockout\n- Observed: Bloquea al quinto intento, con LOCK_AT.\n" in repo.read(IMPL)
    assert "| %s | MODIFIED R-session-expiry; REOBSERVED R-lockout |" % change in repo.read(HISTORY)
    lock = json.loads(repo.read(change + "/capability-delta.lock.json"))
    assert sorted(lock["fold"]["anchors"]) == ["R-lockout", "R-session-expiry"]
    rc, out = repo.cap("check", "--mode", "dev", "--base", "main")
    assert rc == 0 and not [note for note in out["notes"] if "anchored code changed" in note], out
    rc, out = repo.ci()
    assert rc == 0 and out["states"][change] == "ready" and out["hard"] == [], out


def test_a_change_can_do_nothing_but_observe_a_rule_again(repo):
    """A rename, a comment: no requirement changes, and the record of what the code does is brought up to date."""
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", reobserved())
    repo.replace("src/auth/session.py", "Server-side sessions.", "Sessions kept on the server.")
    out = repo.review(change)
    assert out["status"] == "stamped", out
    spec_before, index_before = repo.read(SPEC), repo.read(INDEX)
    prepared = repo.prepare(change)
    assert prepared["capabilities"] == ["login"]
    repo.draft(prepared, impl(expiry="Expira a los 30 minutos.", lockout="Bloquea al quinto intento; la clase se describe de otro modo."))
    rc, out = repo.cap("apply", "--change", change, "--staged", prepared["staging"])
    assert rc == 0 and out["status"] == "published", out
    assert repo.read(SPEC) == spec_before and repo.read(INDEX) == index_before
    assert "la clase se describe de otro modo" in repo.read(IMPL)
    assert "| %s | REOBSERVED R-lockout |" % change in repo.read(HISTORY)
    rc, out = repo.cap("prepare", "--change", change)
    assert rc == 0 and out["status"] == "unchanged", "the same code: there is nothing new to look at"
    repo.commit("observed again")
    rc, out = repo.ci()
    assert rc == 0 and out["states"][change] == "ready" and out["hard"] == [], out
    assert not [note for note in out["notes"] if "anchored code changed" in note and "R-lockout" in note]
    # The code moves once more: the fold is asked for again.
    repo.replace("src/auth/session.py", "Sessions kept on the server.", "Sessions, on the server.")
    rc, out = repo.cap("prepare", "--change", change)
    assert rc == 0 and out["status"] == "ready", out


def test_observing_again_owes_the_evidence_of_any_other_rule(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", reobserved())
    repo.replace("src/auth/session.py", "Server-side sessions.", "Sessions kept on the server.")
    repo.review(change)
    repo.folded(change, impl(expiry="Expira a los 30 minutos."))
    repo.commit("observed again")
    rc, out = repo.ci(fail="test_lockout")
    assert rc == 1 and hard_with(out, change, "R-lockout: mapped test %s failed" % TEST_LOCKOUT), out
    repo.replace("src/auth/session.py", "Sessions kept on the server.", "Sessions, on the server.")
    repo.commit("the code moved after the fold")
    rc, out = repo.ci()
    assert rc == 1 and hard_with(out, change, "R-lockout: observation is stale"), out


def test_a_rule_observed_again_and_not_verified_is_not_ready(repo):
    """Looking again is a claim about the code, like building the rule: it does not pass as unverified."""
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", reobserved())
    repo.replace("src/auth/session.py", "Server-side sessions.", "Sessions kept on the server.")
    repo.review(change)
    repo.folded(change, impl(expiry="Expira a los 30 minutos.", lockout="No se pudo leer.", lockout_state="unverified"))
    repo.commit("looked at, and not verified")
    rc, out = repo.ci()
    assert rc == 1 and out["states"][change] != "ready" and hard_with(out, change, "R-lockout", "unverified"), out


def test_observing_again_without_a_block_or_before_the_fold_is_not_ready(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", reobserved())
    repo.replace("src/auth/session.py", "Server-side sessions.", "Sessions kept on the server.")
    repo.review(change)
    repo.commit("declared, not folded")
    rc, out = repo.ci()
    assert rc == 1 and out["states"][change] != "ready" and hard_with(out, change, "R-lockout"), out
    rc, out = repo.fold(change, impl(expiry="Expira a los 30 minutos.", with_lockout=False))
    assert rc == 2 and out["errors"] == ["no Rule Status block for R-lockout"], out


@pytest.mark.parametrize(
    "entries, needle",
    [
        (reobserved(more="- From: %s\n" % LOCKOUT_5), "REOBSERVED R-lockout: takes no From; it changes no text, and a change of text is MODIFIED"),
        (reobserved(more="- To: %s\n" % LOCKOUT_3), "REOBSERVED R-lockout: takes no To; it changes no text, and a change of text is MODIFIED"),
        (reobserved(more="- Replaced-By: none\n"), "REOBSERVED R-lockout: takes no Replaced-By"),
        ("### REOBSERVED R-lockout\n- Capability: login\n", "REOBSERVED R-lockout: missing reason"),
        ("### REOBSERVED R-lockout\n- Reason: Porque sí.\n", "REOBSERVED R-lockout: missing capability"),
        (reobserved(more="- Links: FR-999\n"), "REOBSERVED R-lockout: link FR-999 not found in the change"),
        (reobserved() + "\n" + reobserved(), "REOBSERVED R-lockout: repeated rule"),
        (modified() + "- Reason: Porque sí.\n", "MODIFIED R-session-expiry: takes no Reason; that is for REOBSERVED"),
    ],
)
def test_a_reobservation_that_is_not_one_is_rejected(repo, entries, needle):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", entries)
    rc, out = repo.cap("review", "--change", change)
    assert rc == 2 and needle in " | ".join(out["errors"]), out


def test_a_reobservation_takes_a_link_or_none(repo):
    repo.checkout("-b", "feat")
    for name, more in (("002-a", "- Links: FR-001\n"), ("003-b", "- Links: none\n"), ("004-c", "")):
        change = repo.feature(name, reobserved(more=more))
        assert repo.review(change)["status"] == "stamped"


@pytest.mark.parametrize(
    "rule, needle",
    [
        ("R-nothing", "REOBSERVED R-nothing: rule not found"),
    ],
)
def test_a_rule_that_is_not_there_cannot_be_observed(repo, rule, needle):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", reobserved(rule))
    rc, out = repo.cap("review", "--change", change)
    assert rc == 3 and out["status"] == "conflict" and needle in out["conflicts"], out


def test_a_retired_rule_cannot_be_observed_and_rebase_only_drops_it(repo):
    """The branch observes the lockout again; meanwhile the base retired it."""
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", reobserved())
    repo.replace("src/auth/session.py", "Server-side sessions.", "Sessions kept on the server.")
    repo.review(change)
    repo.folded(change, impl(expiry="Expira a los 30 minutos."))
    repo.commit("observed again")
    repo.checkout("main")
    repo.checkout("-b", "rem")
    retire = repo.feature("003-rem", removed("R-lockout", LOCKOUT_5))
    repo.review(retire)
    repo.folded(retire, impl(expiry="Expira a los 30 minutos.", with_lockout=False, retirement=retirement_block("R-lockout", retire)))
    repo.commit("retire the lockout")
    repo.checkout("main")
    repo.merge("rem")
    repo.checkout("feat")
    rc, out = repo.cap("check", "--mode", "dev", "--base", "main")
    assert rc == 1 and hard_with(out, "REOBSERVED R-lockout: main has no built rule with this id; run capabilities.py rebase --change " + change), out
    rc, out = repo.cap("rebase", "--change", change)
    assert rc == 3 and out["conflicts"][0]["choices"] == ["drop"] and out["conflicts"][0]["spec"] is None, out
    for choice in ("keep", "adopt"):
        rc, out = repo.cap("rebase", "--change", change, "--" + choice, "R-lockout")
        assert rc == 2, out
    rc, out = repo.cap("rebase", "--change", change, "--drop", "R-lockout")
    assert rc == 0 and out["status"] == "rebased", out
    assert "Capabilities: none" in repo.read(change + "/spec.md") and "R-lockout**" not in repo.read(SPEC)


def test_observing_a_rule_again_does_not_let_its_text_change(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", reobserved())
    repo.replace("src/auth/session.py", "Server-side sessions.", "Sessions kept on the server.")
    repo.review(change)
    repo.folded(change, impl(expiry="Expira a los 30 minutos."))
    repo.replace(SPEC, LOCKOUT_5, LOCKOUT_3)
    repo.commit("and the text, by hand")
    rc, out = repo.ci()
    assert rc == 1 and hard_with(out, "R-lockout", "catalog rule changed without an authorizing delta"), out
