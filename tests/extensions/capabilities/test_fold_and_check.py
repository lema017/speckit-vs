"""The fold and check mechanism, ported from the prototype's cases to real pytest reports."""

from __future__ import annotations

import pytest

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
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    repo.commit("line endings changed")
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
