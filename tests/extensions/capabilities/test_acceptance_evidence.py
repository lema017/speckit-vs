"""Acceptance 2: retirement evidence and the merge queue, with reports from real pytest runs."""

from __future__ import annotations

import importlib.util
import xml.etree.ElementTree as ET

import pytest

from .conftest import (
    EXPIRY_15,
    HISTORY,
    IMPL,
    LOCKOUT_3,
    LOCKOUT_5,
    SCRIPT,
    SPEC,
    TEST_EXPIRY,
    TEST_FREE,
    TEST_LOCKOUT,
    added,
    block,
    change_expiry,
    deliver,
    hard_with,
    impl,
    modified,
    removed,
    retirement_block,
)


def script_module():
    spec = importlib.util.spec_from_file_location("capabilities_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def retire(repo, replaced="none", retirement=None, more="", entries_extra=""):
    """Reviewed and folded REMOVED R-lockout on a new branch."""
    repo.checkout("-b", "retire")
    change = repo.feature("002-retire", removed("R-lockout", LOCKOUT_5, replaced=replaced) + entries_extra)
    repo.review(change)
    if retirement == "default":
        retirement = retirement_block("R-lockout", change)
    rc, out = repo.fold(change, impl(expiry="Expira a los 30 minutos.", with_lockout=False, retirement=retirement or "", more=more))
    repo.commit("retire")
    return change, rc, out


# ---------------------------------------------------------------- REMOVED with a replacement


def captcha(state="conforming", tests=TEST_LOCKOUT):
    return block("R-captcha", "Pide captcha.", state, tests)


def test_retired_rule_with_replacement_is_ready_when_the_replacement_passes(repo):
    change, rc, out = retire(repo, replaced="R-captcha", more=captcha(), entries_extra="\n" + added("R-captcha", "Pide captcha al quinto intento."))
    assert rc == 0, out
    assert "R-lockout" not in repo.read(SPEC)
    assert "| R-lockout | %s | %s | R-captcha |" % (LOCKOUT_5, change) in repo.read(HISTORY)
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "ready"


def test_replacement_must_exist(repo):
    change, rc, out = retire(repo, replaced="R-ghost", retirement=None)
    assert rc == 2
    assert "replacement R-ghost does not exist" in str(out)


@pytest.mark.parametrize(
    "state, ci_kwargs, message",
    [
        ("discrepant", {}, "replacement R-captcha: state is discrepant"),
        ("conforming", {"fail": "test_lockout"}, "mapped test %s failed" % TEST_LOCKOUT),
        ("conforming", {"pytest_args": ("--deselect", TEST_LOCKOUT)}, "mapped test %s missing" % TEST_LOCKOUT),
    ],
    ids=["replacement-discrepant", "replacement-test-fails", "replacement-test-absent"],
)
def test_replacement_evidence_blocks_when_it_does_not_hold(repo, state, ci_kwargs, message):
    retire(repo, replaced="R-captcha", more=captcha(state), entries_extra="\n" + added("R-captcha", "Pide captcha al quinto intento."))
    kwargs = dict(ci_kwargs)
    rc, out = repo.ci(*kwargs.pop("pytest_args", ()), **kwargs)
    assert rc == 1
    assert hard_with(out, message)


# ---------------------------------------------------------------- REMOVED without a replacement


def test_retired_rule_without_replacement_needs_a_passing_absence_test(repo):
    change, rc, out = retire(repo, retirement="default")
    assert rc == 0, out
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "ready"


def test_no_retirement_block_cannot_be_folded(repo):
    change, rc, out = retire(repo)
    assert rc == 2
    assert "needs a Retirement Evidence block" in str(out)


def by_hand_without_block(repo):
    repo.checkout("-b", "retire")
    change = repo.feature("002-retire", removed("R-lockout", LOCKOUT_5))
    repo.review(change)
    repo.folded(change, impl(expiry="Expira a los 30 minutos.", with_lockout=False, retirement=retirement_block("R-lockout", change)))
    text = repo.read(IMPL)
    repo.write(IMPL, text[:text.index("## Retirement Evidence")])
    repo.commit("evidence dropped by hand")
    return change


def test_ci_blocks_when_the_block_is_dropped_after_fold(repo):
    by_hand_without_block(repo)
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-lockout", "no Retirement Evidence block")


@pytest.mark.parametrize(
    "block_kwargs, ci_kwargs, message",
    [
        ({"tests": "none"}, {}, "at least one passing absence test"),
        ({"tests": TEST_FREE}, {"fail": "test_unrelated"}, "mapped test %s failed" % TEST_FREE),
        ({"tests": TEST_FREE}, {"pytest_args": ("--deselect", TEST_FREE)}, "mapped test %s missing" % TEST_FREE),
        ({"state": "discrepant", "observed": "Sigue bloqueando."}, {}, "behaviour is still present (Sigue bloqueando.)"),
        ({"state": "unverified"}, {}, "retirement state is unverified"),
        ({"tests": "manual: no se puede automatizar"}, {}, "manual evidence is not allowed"),
    ],
    ids=["no-tests", "absence-test-fails", "absence-test-absent", "still-present", "unverified", "manual-off"],
)
def test_retirement_evidence_blocks_when_it_does_not_hold(repo, block_kwargs, ci_kwargs, message):
    repo.checkout("-b", "retire")
    change = repo.feature("002-retire", removed("R-lockout", LOCKOUT_5))
    repo.review(change)
    repo.folded(change, impl(expiry="Expira a los 30 minutos.", with_lockout=False, retirement=retirement_block("R-lockout", change, **block_kwargs)))
    repo.commit("retire")
    kwargs = dict(ci_kwargs)
    rc, out = repo.ci(*kwargs.pop("pytest_args", ()), **kwargs)
    assert rc == 1, out
    assert hard_with(out, "R-lockout", message)


def test_manual_retirement_is_accepted_only_with_the_option(repo):
    repo.checkout("-b", "retire")
    repo.config(allow_manual_evidence="true")
    change = repo.feature("002-retire", removed("R-lockout", LOCKOUT_5))
    repo.review(change)
    repo.folded(change, impl(expiry="Expira a los 30 minutos.", with_lockout=False, retirement=retirement_block("R-lockout", change, tests="manual: requiere hardware")))
    repo.commit("retire")
    rc, out = repo.ci()
    assert rc == 0, out
    assert any("manual evidence accepted: requiere hardware" in note for note in out["notes"])


def test_retirement_block_must_name_its_change(repo):
    repo.checkout("-b", "retire")
    change = repo.feature("002-retire", removed("R-lockout", LOCKOUT_5))
    repo.review(change)
    prepared = repo.prepare(change)
    repo.draft(prepared, impl(expiry="Expira a los 30 minutos.", with_lockout=False, retirement=retirement_block("R-lockout", "specs/999-other")))
    rc, out = repo.cap("apply", "--change", change, "--staged", prepared["staging"])
    assert rc == 2
    assert "must name Change" in str(out)


def test_retired_rule_with_a_status_block_left_behind_cannot_be_folded(repo):
    repo.checkout("-b", "retire")
    change = repo.feature("002-retire", removed("R-lockout", LOCKOUT_5))
    repo.review(change)
    prepared = repo.prepare(change)
    repo.draft(prepared, impl(expiry="Expira a los 30 minutos.", retirement=retirement_block("R-lockout", change)))
    rc, out = repo.cap("apply", "--change", change, "--staged", prepared["staging"])
    assert rc == 2
    assert "still has a block for retired rule" in str(out)


def test_retirement_evidence_is_evaluated_only_with_its_removed_entry(repo):
    change, rc, _ = retire(repo, retirement="default")
    assert rc == 0
    deliver(repo, "retire", "later")
    repo.write("docs/notes.txt", "otra cosa\n")
    repo.commit("unrelated")
    rc, out = repo.ci("--deselect", TEST_FREE)
    assert rc == 0, out
    assert change not in out["states"]


# ---------------------------------------------------------------- the merge queue


def queue_commit(repo, other_change):
    """Two PRs in a merge queue: a folded one and another that touches the same anchored file."""
    change = change_expiry(repo)
    repo.checkout("main")
    repo.checkout("-b", "other")
    other_change(repo)
    repo.commit("other PR")
    repo.checkout("main")
    base = repo.git("rev-parse", "HEAD").stdout.strip()
    repo.checkout("-b", "queue")
    repo.merge("other")
    repo.merge("feat")
    return change, base


def harmless(repo):
    repo.write("src/auth/session.py", repo.read("src/auth/session.py") + "\n\n# refactor from another PR\n")


def breaking(repo):
    repo.write("src/auth/session.py", repo.read("src/auth/session.py") + "\n\nEXPIRY_MINUTES = 16  # another PR\n")


def test_combined_commit_revalidates_a_changed_anchor_with_this_commits_tests(repo):
    change, base = queue_commit(repo, harmless)

    rc, out = repo.ci(base=base)
    assert rc == 1, "without --combined a changed anchor is a failure"
    assert hard_with(out, "R-session-expiry", "observation is stale", "src/auth/session.py")

    rc, out = repo.ci(base=base, extra=("--combined",))
    assert rc == 0, out
    assert out["states"][change] == "ready"
    assert out["revalidated"] == [{"rule": "R-session-expiry", "files": ["src/auth/session.py"], "tests": [TEST_EXPIRY]}]


def test_combined_commit_fails_and_names_the_rule_when_another_pr_broke_the_behaviour(repo):
    change, base = queue_commit(repo, breaking)
    rc, out = repo.ci(base=base, extra=("--combined",))
    assert rc == 1
    assert hard_with(out, "R-session-expiry", "mapped test %s failed" % TEST_EXPIRY)
    assert hard_with(out, "R-session-expiry", "anchored file changed after fold (src/auth/session.py)", "could not be revalidated")
    assert out["revalidated"] == []
    assert out["states"][change] == "prepared"


def test_combined_commit_names_the_missing_evidence_when_the_report_lacks_the_test(repo):
    _, base = queue_commit(repo, harmless)
    rc, out = repo.ci("--deselect", TEST_EXPIRY, base=base, extra=("--combined",))
    assert rc == 1
    assert hard_with(out, "R-session-expiry", "mapped test %s missing" % TEST_EXPIRY)
    assert hard_with(out, "R-session-expiry", "anchored file changed after fold (src/auth/session.py)")
    assert out["revalidated"] == []


def queue_with_two_rule_changes(repo):
    expiry = change_expiry(repo)
    repo.checkout("main")
    repo.checkout("-b", "lock")
    lockout = repo.feature("003-lock", modified("R-lockout", LOCKOUT_5, LOCKOUT_3))
    repo.set_code(lockout=3)
    repo.review(lockout)
    repo.folded(lockout, impl(expiry="Expira a los 30 minutos.", lockout="Bloquea al tercero."))
    repo.commit("lockout PR")
    repo.checkout("main")
    base = repo.git("rev-parse", "HEAD").stdout.strip()
    repo.checkout("-b", "queue")
    repo.merge("feat")
    repo.merge("lock")
    return expiry, lockout, base


def test_two_folded_prs_sharing_an_anchored_file_pass_the_queue_with_this_commits_tests(repo):
    expiry, lockout, base = queue_with_two_rule_changes(repo)
    rc, out = repo.ci(base=base, extra=("--combined",))
    assert rc == 0, out
    assert out["states"] == {expiry: "ready", lockout: "ready"}
    assert sorted(item["rule"] for item in out["revalidated"]) == ["R-lockout", "R-session-expiry"]

    rc, out = repo.ci(base=base, fail="test_lockout", extra=("--combined",))
    assert rc == 1
    assert hard_with(out, lockout, "R-lockout", "could not be revalidated")
    assert not hard_with(out, "R-session-expiry")
    assert out["states"] == {expiry: "ready", lockout: "prepared"}


def test_combined_commit_fails_when_another_pr_removed_the_anchored_symbol(repo):
    def rename(other):
        other.replace("src/auth/session.py", "class SessionManager:", "class SessionStore:")

    _, base = queue_commit(repo, rename)
    rc, out = repo.ci(base=base, extra=("--combined",))
    assert rc == 1, "the tests still pass, and the observation no longer points at real code"
    assert hard_with(out, "R-session-expiry", "code anchor does not resolve", "SessionManager")


def test_combined_commit_with_an_unchanged_anchor_revalidates_nothing(repo):
    change = change_expiry(repo)
    base = repo.git("rev-parse", "main").stdout.strip()
    rc, out = repo.ci(base=base, extra=("--combined",))
    assert rc == 0, out
    assert out["revalidated"] == []
    assert out["states"][change] == "ready"


def test_combined_cannot_revalidate_manual_evidence(repo):
    repo.checkout("-b", "feat")
    repo.config(allow_manual_evidence="true")
    change = repo.feature("002-x", modified_expiry())
    repo.set_code(expiry=15)
    repo.review(change)
    repo.folded(change, impl(expiry_tests="manual: lo verificó QA"))
    repo.commit("manual")
    repo.checkout("main")
    repo.checkout("-b", "other")
    harmless(repo)
    repo.commit("other")
    repo.checkout("main")
    base = repo.git("rev-parse", "HEAD").stdout.strip()
    repo.checkout("-b", "queue")
    repo.merge("other")
    repo.merge("feat")
    rc, out = repo.ci(base=base, extra=("--combined",))
    assert rc == 1
    assert hard_with(out, "R-session-expiry", "manual evidence cannot revalidate")


def modified_expiry():
    return modified()


def test_the_old_switch_no_longer_exists(repo):
    change_expiry(repo)
    rc, _ = repo.cap("check", "--mode", "ci", "--base", "main", "--no-freshness")
    assert rc == 2


# ---------------------------------------------------------------- binding the report to the revision


def test_a_report_tracked_by_git_is_rejected(repo):
    change_expiry(repo)
    report = repo.junit()
    repo.git("add", "-f", report)
    repo.commit("commit the evidence")
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", report)
    assert rc == 1
    assert hard_with(out, "is tracked by git")
    assert hard_with(out, "no test report for this revision")


def test_a_report_older_than_the_commit_is_rejected(repo):
    change_expiry(repo)
    report = repo.junit()
    repo.write("docs/notes.txt", "x\n")
    repo.commit("later commit", date="2099-01-01T00:00:00+00:00")
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", report)
    assert rc == 1
    assert hard_with(out, "older than the evaluated commit")


def test_a_report_without_timestamp_is_accepted(repo):
    change_expiry(repo)
    report = repo.junit()
    tree = ET.parse(str(repo.path / report))
    for suite in tree.getroot().iter("testsuite"):
        suite.attrib.pop("timestamp", None)
    tree.write(str(repo.path / report))
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", report)
    assert rc == 0, out


def test_a_green_report_of_other_tests_is_not_evidence(repo):
    change_expiry(repo)
    rc, out = repo.ci("--deselect", TEST_EXPIRY)
    assert rc == 1
    assert hard_with(out, "mapped test %s missing" % TEST_EXPIRY)


def test_every_checked_task_with_no_report_is_not_evidence(repo):
    change_expiry(repo)
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main")
    assert rc == 1
    assert hard_with(out, "no test report for this revision")


# ---------------------------------------------------------------- JUnit mapping


MAP_TESTS = """import pytest


class TestGroup:
    def test_in_class(self):
        pass

    def test_also_in_class(self):
        pass


@pytest.mark.parametrize("value", [1, 2])
def test_param_ok(value):
    pass


@pytest.mark.parametrize("value", [1, 2])
def test_param_bad(value):
    assert value == 1


@pytest.mark.skip(reason="not now")
def test_skipped():
    pass


@pytest.mark.xfail(reason="known")
def test_xfail():
    assert False


def test_shared_name():
    pass


def test_fails():
    assert False
"""


@pytest.mark.parametrize(
    "ref, expected",
    [
        ("tests/map/test_map.py::test_shared_name", "passed"),
        ("tests/map/test_map.py::TestGroup::test_in_class", "passed"),
        ("tests/map/test_map.py::test_in_class", "missing"),
        ("tests/map/test_map.py::OtherGroup::test_in_class", "missing"),
        ("tests/map/test_map.py::test_param_ok", "passed"),
        ("tests/map/test_map.py::test_param_bad", "failed"),
        ("tests/map/test_map.py::test_param_bad[1]", "passed"),
        ("tests/map/test_map.py::test_param_bad[2]", "failed"),
        ("tests/map/test_map.py::test_skipped", "failed"),
        ("tests/map/test_map.py::test_xfail", "failed"),
        ("tests/map/test_map.py::test_fails", "failed"),
        ("tests/map/test_map.py::test_nothing", "missing"),
        ("tests/map/test_other.py::test_shared_name", "failed"),
        ("tests/ghost/test_map.py::test_shared_name", "missing"),
        ("map/test_map.py::test_shared_name", "passed"),
        ("test_map.py::test_shared_name", "passed"),
    ],
)
def test_references_map_to_a_real_pytest_report(repo, ref, expected):
    repo.write("tests/map/test_map.py", MAP_TESTS)
    repo.write("tests/map/test_other.py", "def test_shared_name():\n    assert False\n")
    report = repo.junit("tests/map")
    module = script_module()
    assert module.test_result(ref, module.junit_cases(repo.path / report)) == expected


# Written by hand from the documented shape of these reports, not from a real run. They pin one
# thing only: until a language is validated, its references block instead of passing by accident.
SUREFIRE = """<testsuite name="com.acme.auth.SessionTest" tests="1" failures="0">
  <testcase name="expiry" classname="com.acme.auth.SessionTest" time="0.01"/>
</testsuite>"""
JEST_JUNIT = """<testsuites name="jest tests"><testsuite name="session" tests="1">
  <testcase classname="session expires" name="session expires after 15 minutes" time="0.01"/>
</testsuite></testsuites>"""


@pytest.mark.parametrize(
    "report, ref",
    [
        (SUREFIRE, "src/test/java/com/acme/auth/SessionTest.java::expiry"),
        (SUREFIRE, "src/test/java/com/acme/auth/SessionTest.java::SessionTest::expiry"),
        (JEST_JUNIT, "tests/session.test.ts::session expires after 15 minutes"),
    ],
    ids=["java-method", "java-class", "typescript"],
)
def test_other_languages_fail_closed_until_they_are_validated(repo, report, ref):
    repo.write("report.xml", report)
    module = script_module()
    assert module.test_result(ref, module.junit_cases(repo.path / "report.xml")) == "missing"


# ---------------------------------------------------------------- options, off by default


def test_manual_evidence_is_off_by_default(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified_expiry())
    repo.set_code(expiry=15)
    repo.review(change)
    repo.folded(change, impl(expiry_tests="manual: lo verificó QA"))
    repo.commit("manual")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-session-expiry", "manual evidence is not allowed", "lo verificó QA")

    repo.config(allow_manual_evidence="true")
    repo.commit("opt in")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "ready"


def partial_feature(repo):
    repo.checkout("-b", "part1")
    change = repo.feature("002-x", modified_expiry(), tasks="- [x] T001 first part in src/auth/session.py\n- [ ] T002 second part\n")
    repo.review(change)
    repo.commit("first part")
    return change


def test_partial_features_are_blocked_by_default(repo):
    partial_feature(repo)
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "1 open tasks")


def test_partial_features_pass_with_the_option_while_the_catalog_is_untouched(repo):
    change = partial_feature(repo)
    repo.config(allow_partial_features="true")
    repo.commit("opt in")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "partial"
    assert any("integrated in parts" in note for note in out["notes"])


def test_partial_option_does_not_excuse_a_catalog_already_changed(repo):
    change = partial_feature(repo)
    repo.config(allow_partial_features="true")
    repo.replace(SPEC, "La sesión expira tras 30 minutos de inactividad. (specs/001-login)", "%s (%s)" % (EXPIRY_15, change))
    repo.commit("catalog folded by hand with open tasks")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "1 open tasks")


def test_partial_option_still_requires_a_sealed_delta(repo):
    repo.checkout("-b", "part1")
    repo.config(allow_partial_features="true")
    repo.feature("002-x", modified_expiry(), tasks="- [ ] T002 second part\n")
    repo.commit("not sealed")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "delta not reviewed")
