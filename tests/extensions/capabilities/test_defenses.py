"""The defenses that do not depend on the agent reading its instructions: what check notes when work skipped its fold.

A spec done and not folded, product code no change records, specs merged without their fold, and rules a later change cannot find.
"""

from __future__ import annotations

import json
import subprocess

from .conftest import CAT, IMPL, INDEX, MARK, PYTHON, SCRIPT, SPEC, added, block, change_expiry, impl, modified

DONE = "the work is done, no task is open"
NO_RECORD = "no change of the catalog records it"
MERGED = "merged without its fold"
NO_CODE = "without Code in Rule Status"
GONE = "its Code no longer exists"


def check(repo, *args):
    rc, out = repo.cap("check", *args)
    assert rc in (0, 1), out
    return out


def notes_with(out, *needles):
    return [line for line in out.get("notes", []) if all(needle in line for needle in needles)]


# ---------------------------------------------------------------- a spec done and not folded


def test_a_reviewed_spec_with_every_task_closed_is_noted_as_unfolded(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified())
    repo.set_code(expiry=15)
    repo.review(change)
    out = check(repo, "--base", "main")
    assert notes_with(out, change, DONE, "speckit.capabilities.fold"), out["notes"]


def test_a_drafted_spec_with_every_task_closed_is_noted_too(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified())
    assert notes_with(check(repo, "--base", "main"), change, DONE)


def test_a_spec_with_an_open_task_is_still_being_built(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified(), tasks="- [x] T001 Code\n- [ ] T002 Tests\n")
    repo.review(change)
    assert not notes_with(check(repo, "--base", "main"), DONE)


def test_the_tasks_of_the_fold_and_after_the_merge_do_not_hold_it_back(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified(), tasks="- [x] T001 Code\n- [ ] T002 Run /speckit-capabilities-fold\n- [ ] T003 [post-merge] Deploy\n")
    repo.review(change)
    assert notes_with(check(repo, "--base", "main"), change, DONE)


def test_a_spec_without_tasks_is_not_called_done(repo):
    repo.checkout("-b", "feat")
    repo.feature("002-x", modified(), tasks=None)
    assert not notes_with(check(repo, "--base", "main"), DONE)


def test_a_folded_spec_is_not_noted(repo):
    change_expiry(repo)
    out = check(repo, "--base", "main")
    assert not notes_with(out, DONE) and not notes_with(out, NO_RECORD)


# ---------------------------------------------------------------- product code that no change records


def test_product_code_changed_without_any_change_is_noted(repo):
    repo.checkout("-b", "feat")
    repo.set_code(expiry=15)
    out = check(repo, "--base", "main")
    assert notes_with(out, "2 product files", NO_RECORD, "speckit.capabilities.record"), out["notes"]


def test_documents_and_ignored_files_are_not_product_code(repo):
    repo.checkout("-b", "feat")
    repo.config(coverage_ignore="infra/*")
    repo.write("docs/guide.md", "x\n")
    repo.write("infra/main.tf", "x\n")
    assert not notes_with(check(repo, "--base", "main"), NO_RECORD)


def test_a_record_that_changes_no_rule_covers_the_branch(repo):
    repo.checkout("-b", "feat")
    repo.write("src/other.py", "x = 2\n")
    repo.write(CAT + "/_changes/20261121-tidy/capability-delta.md", "# Tidy\n\n## Capability Delta\n%s\n\nCapabilities: none — a refactor\n" % MARK)
    assert not notes_with(check(repo, "--base", "main"), NO_RECORD)


def test_a_record_still_pending_covers_the_branch_and_says_so_itself(repo):
    """The record is there; what it still owes is the fold, which check reports for the record."""
    repo.checkout("-b", "feat")
    repo.set_code(expiry=15)
    record = CAT + "/_changes/20261121-expiry"
    repo.write(record + "/capability-delta.md", "# Expiry\n\n## Capability Delta\n%s\n\n%s" % (MARK, modified(links="none")))
    out = check(repo, "--base", "main")
    assert not notes_with(out, NO_RECORD)
    assert record in out["states"]


def test_without_a_base_nothing_is_compared(repo):
    repo.set_code(expiry=15)
    assert not notes_with(check(repo), NO_RECORD)


# ---------------------------------------------------------------- merged without the fold


def test_a_spec_merged_without_its_fold_is_noted_on_main(repo):
    """The case of social-network: specs merged into main whose rules never reached the catalog."""
    done = repo.feature("002-done", added("R-remember-me", "Recuerda la sesión 30 días."))
    waiting = repo.feature("003-waiting", added("R-logout-all", "Cierra todas las sesiones."), tasks="- [x] T001 Code\n- [ ] T002 Validate\n")
    bare = repo.feature("004-bare", added("R-audit", "Registra cada ingreso."), tasks=None)
    repo.commit("merged without fold")
    out = check(repo, "--base", "main")
    assert notes_with(out, done, MERGED, "0 open tasks")
    assert notes_with(out, waiting, MERGED, "1 open task")
    assert notes_with(out, bare, MERGED, "no tasks.md")
    assert out["hard"] == [], "a note, not an error: the branch did not make it"


def test_a_merged_spec_is_a_note_in_ci_too(repo):
    repo.feature("002-done", added("R-remember-me", "Recuerda la sesión 30 días."))
    repo.commit("merged without fold")
    rc, out = repo.ci()
    assert notes_with(out, "specs/002-done", MERGED)
    assert not [line for line in out["hard"] if MERGED in line]


def test_a_spec_on_the_branch_is_reported_as_a_change_not_as_merged(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified())
    out = check(repo, "--base", "main")
    assert not notes_with(out, change, MERGED)


def test_folded_specs_are_not_noted_as_merged(repo):
    change_expiry(repo)
    repo.checkout("main")
    repo.merge("feat")
    assert not notes_with(check(repo, "--base", "main"), MERGED)


# ---------------------------------------------------------------- rules a later change cannot find


def test_a_built_rule_without_code_is_noted(repo):
    repo.write(IMPL, impl(more=block("R-extra", "x")).replace(
        block("R-lockout", "Bloquea al quinto intento.", tests="tests/auth/test_session.py::test_lockout"),
        "### R-lockout\n- Observed: Bloquea al quinto intento.\n- State: conforming\n- Code: none\n- Tests: `tests/auth/test_session.py::test_lockout`\n"))
    out = check(repo)
    assert notes_with(out, "login: 1 rule", NO_CODE, "R-lockout"), out["notes"]


def test_a_built_rule_without_a_rule_status_block_is_noted(repo):
    repo.write(IMPL, impl(with_lockout=False))
    assert notes_with(check(repo), "login: 1 rule", NO_CODE, "R-lockout")


def test_a_rule_with_its_code_is_not_noted(repo):
    out = check(repo)
    assert not notes_with(out, NO_CODE) and not notes_with(out, GONE)


def test_a_designed_rule_owes_no_code(repo):
    text = repo.read(SPEC)
    line = next(line for line in text.splitlines() if line.startswith("- **R-lockout**"))
    repo.write(SPEC, text.replace(line, line + "\n" + line.replace("**R-lockout**", "**R-later** [designed]")))
    assert not notes_with(check(repo), NO_CODE)


def test_code_that_is_gone_from_an_untouched_rule_is_noted(repo):
    repo.replace("src/auth/session.py", "class SessionManager", "class Sessions")
    repo.commit("rename on main")
    out = check(repo, "--base", "main")
    assert notes_with(out, "R-session-expiry", GONE, "src/auth/session.py::SessionManager"), out["notes"]


def test_code_gone_in_a_file_the_branch_touched_is_left_to_the_branch_check(repo):
    repo.checkout("-b", "feat")
    repo.replace("src/auth/session.py", "class SessionManager", "class Sessions")
    out = check(repo, "--base", "main")
    assert not notes_with(out, GONE)
    assert [line for line in out["notes"] if "anchor does not exist" in line]


# ---------------------------------------------------------------- review: requirements no rule links

TWO_FRS = "System MUST expire the session after 15 minutes.\n- **FR-002**: System MUST show the time left\n- **FR-003**: System MUST log each expiry"


def test_review_lists_the_requirements_no_rule_links(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified(links="FR-001"), fr=TWO_FRS)
    out = repo.review(change)
    assert out["status"] == "stamped" and out["unlinked"] == ["FR-002", "FR-003"]


def test_review_lists_them_again_when_the_spec_is_unchanged(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified(links="FR-001, FR-003"), fr=TWO_FRS)
    repo.review(change)
    out = repo.review(change)
    assert out["status"] == "unchanged" and out["unlinked"] == ["FR-002"]


def test_a_spec_that_says_no_rule_changes_has_every_requirement_unlinked(repo):
    """The 016 of social-network: twelve requirements and Capabilities: none."""
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", "Capabilities: none — solo un texto\n", fr=TWO_FRS)
    assert repo.review(change)["unlinked"] == ["FR-001", "FR-002", "FR-003"]


def test_every_requirement_linked_leaves_nothing(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified(links="FR-001, FR-002, FR-003, US1/AC1"), fr=TWO_FRS)
    assert repo.review(change)["unlinked"] == []


def test_a_record_without_requirements_has_nothing_unlinked(repo):
    repo.checkout("-b", "feat")
    record = CAT + "/_changes/20261121-expiry"
    repo.write(record + "/capability-delta.md", "# Expiry\n\n## Capability Delta\n%s\n\n%s" % (MARK, modified(links="none")))
    assert repo.review(record)["unlinked"] == []


# ---------------------------------------------------------------- the Stop hook of the agent


def stop(repo, payload='{"hook_event_name": "Stop", "stop_hook_active": false}'):
    """Run the hook as the agent's dispatcher does: in the project, the message on stdin, no --root."""
    done = subprocess.run([PYTHON, "-I", "-S", str(SCRIPT), "stop-check"], cwd=repo.path, input=payload,
                          capture_output=True, encoding="utf-8")
    assert done.returncode == 0 and not done.stderr, done
    return json.loads(done.stdout) if done.stdout.strip() else None


def test_stop_sends_the_agent_back_when_product_code_has_no_record(repo):
    repo.checkout("-b", "feat")
    repo.set_code(expiry=15)
    out = stop(repo)
    assert out["decision"] == "block"
    assert out["reason"].startswith("speckit-vs: ") and "2 product files" in out["reason"] and "speckit.capabilities.record" in out["reason"]


def test_stop_warns_once_and_not_again_while_nothing_changes(repo):
    repo.checkout("-b", "feat")
    repo.set_code(expiry=15)
    assert stop(repo)["decision"] == "block"
    assert stop(repo) is None
    repo.write("src/billing.py", "PRICE = 1\n")
    assert "3 product files" in stop(repo)["reason"], "a new state is a new warning"


def test_stop_blocks_at_every_stop_when_the_project_asks(repo):
    repo.checkout("-b", "feat")
    repo.config(stop_check="block")
    repo.set_code(expiry=15)
    assert stop(repo)["decision"] == "block"
    assert "every stop" in stop(repo)["reason"]


def test_stop_never_holds_an_agent_that_already_came_back(repo):
    repo.checkout("-b", "feat")
    repo.config(stop_check="block")
    repo.set_code(expiry=15)
    assert stop(repo, '{"stop_hook_active": true}') is None


def test_stop_is_silent_when_the_project_turns_it_off(repo):
    repo.checkout("-b", "feat")
    repo.config(stop_check="off")
    repo.set_code(expiry=15)
    assert stop(repo) is None


def test_stop_sends_the_agent_to_the_fold_of_a_finished_spec(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified())
    repo.set_code(expiry=15)
    repo.review(change)
    reason = stop(repo)["reason"]
    assert change in reason and "speckit.converge" in reason and "speckit.capabilities.fold" in reason
    assert "speckit.capabilities.record" not in reason


def test_stop_leaves_a_spec_being_built_alone(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified(), tasks="- [x] T001 Code\n- [ ] T002 Tests\n")
    repo.set_code(expiry=15)
    repo.review(change)
    assert stop(repo) is None


def test_stop_sends_a_pending_record_to_its_fold(repo):
    repo.checkout("-b", "feat")
    repo.set_code(expiry=15)
    record = CAT + "/_changes/20261121-expiry"
    repo.write(record + "/capability-delta.md", "# Expiry\n\n## Capability Delta\n%s\n\n%s" % (MARK, modified(links="none")))
    reason = stop(repo)["reason"]
    assert record in reason and "speckit.capabilities.fold" in reason


def test_stop_is_silent_once_the_branch_is_recorded(repo):
    change_expiry(repo)
    assert stop(repo) is None


def test_stop_is_silent_on_a_branch_that_changed_nothing(repo):
    repo.checkout("-b", "feat")
    assert stop(repo) is None


def test_stop_survives_what_it_cannot_read(repo):
    repo.checkout("-b", "feat")
    repo.set_code(expiry=15)
    repo.config(base_branch="nowhere")
    assert stop(repo) is None
    repo.config()
    repo.write(INDEX, "<<<<<<< HEAD\n")
    out = stop(repo, "not json")  # stop() asserts it exits 0 and writes nothing to stderr
    assert out is None or out["decision"] == "block"


def test_stop_is_silent_outside_a_git_repository(tmp_path):
    (tmp_path / "specs" / "_capabilities").mkdir(parents=True)
    done = subprocess.run([PYTHON, "-I", "-S", str(SCRIPT), "stop-check"], cwd=tmp_path, input="{}", capture_output=True, encoding="utf-8")
    assert done.returncode == 0 and done.stdout == "" and done.stderr == ""


def test_the_memory_of_the_warning_lives_inside_git(repo):
    repo.checkout("-b", "feat")
    repo.set_code(expiry=15)
    stop(repo)
    assert (repo.path / ".git" / "speckit-capabilities-stop").is_file()
    assert "speckit-capabilities-stop" not in repo.git("status", "--porcelain").stdout
