"""Evidence from the runners the README promises, read from the reports they really write.

``reports/`` holds what Maven Surefire, Gradle, Jest and Vitest wrote for one small project. See its README.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from .conftest import SCRIPT, hard_with, impl, modified

REPORTS = Path(__file__).parent / "reports"
JAVA = "src/test/java/com/example/auth/"
SERVICE = JAVA + "SessionServiceTest.java"
BROKEN = JAVA + "BrokenRuleTest.java"
CONTROLLER = JAVA + "SessionControllerTest.java"
TS = "src/auth/session.test.ts"
SOURCES = {SERVICE: "SessionServiceTest.java", BROKEN: "BrokenRuleTest.java", CONTROLLER: "SessionControllerTest.java"}


def script_module():
    spec = importlib.util.spec_from_file_location("capabilities_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cases_of(runner):
    module = script_module()
    return module, [case for path in sorted((REPORTS / runner).glob("*.xml")) for case in module.junit_cases(path)]


SCRIPT_CASES = [
    (TS + "::SessionManager::expires after 15 minutes", "passed"),
    (TS + "::SessionManager::when idle::stays active at %d minutes", "passed"),
    (TS + "::SessionManager::when idle::stays active at 1 minutes", "passed"),
    (TS + "::SessionManager::remembers the device", "failed"),
    (TS + "::the limit is 15", "passed"),
    (TS + "::this one fails", "failed"),
    (TS + "::SessionManager::nothing here", "missing"),
    (TS + "::expires after 15 minutes", "missing"),
    ("src/other/session.test.ts::the limit is 15", "missing"),
    ("auth/session.test.ts::the limit is 15", "passed"),
]


@pytest.mark.parametrize(
    "runner, ref, expected",
    [
        ("surefire", SERVICE + "::timeoutIsFifteenMinutes", "passed"),
        ("surefire", SERVICE + "::expiresAfterTheLimit", "passed"),
        ("surefire", SERVICE + "::staysActiveWithinTheLimit", "passed"),
        ("surefire", SERVICE + "::namedVariants", "passed"),
        ("surefire", SERVICE + "::rememberMeIsNotImplemented", "failed"),
        ("surefire", SERVICE + "::WhenIdle::aMinuteMoreExpires", "passed"),
        ("surefire", SERVICE + "::aMinuteMoreExpires", "missing"),
        ("surefire", SERVICE + "::nothingHere", "missing"),
        ("surefire", BROKEN + "::thisOneFails", "failed"),
        ("surefire", CONTROLLER + "::sixteenIdleMinutesAreExpired", "passed"),
        ("surefire", "src/test/java/com/other/SessionServiceTest.java::timeoutIsFifteenMinutes", "missing"),
        ("gradle", SERVICE + "::timeoutIsFifteenMinutes", "passed"),
        ("gradle", SERVICE + "::una sesion de 16 minutos expira", "passed"),
        ("gradle", SERVICE + "::expiresAfterTheLimit", "missing"),
        ("gradle", SERVICE + "::staysActiveWithinTheLimit", "missing"),
        ("gradle", SERVICE + "::active at {0} minutes", "passed"),
        ("gradle", SERVICE + "::active at 2 minutes", "passed"),
        ("gradle", SERVICE + "::namedVariants", "missing"),
        ("gradle", SERVICE + "::rememberMeIsNotImplemented", "failed"),
        ("gradle", SERVICE + "::WhenIdle::aMinuteMoreExpires", "passed"),
        ("gradle", BROKEN + "::thisOneFails", "failed"),
        *[("jest", ref, expected) for ref, expected in SCRIPT_CASES],
        *[("vitest", ref, expected) for ref, expected in SCRIPT_CASES],
        ("jest-defaults", TS + "::the limit is 15", "missing"),
        ("jest-defaults", TS + "::this one fails", "missing"),
    ],
)
def test_references_map_to_real_reports(runner, ref, expected):
    module, cases = cases_of(runner)
    assert module.test_result(ref, cases) == expected


@pytest.mark.parametrize(
    "title, name, expected",
    [
        ("at %d minutes", "at 15 minutes", True),
        ("at $value minutes", "at 15 minutes", True),
        ("at {0} minutes", "at 15 minutes", True),
        ("at %d minutes", "after 15 minutes", False),
        ("at %d minutes", "at  minutes", False),
        ("at 15 minutes", "at 16 minutes", False),
        ("a.b", "axb", False),
    ],
)
def test_a_title_as_the_file_writes_it(title, name, expected):
    assert script_module().title_matches(title, name) is expected


@pytest.mark.parametrize(
    "ref",
    [
        "src/x.test.ts::%s",
        "src/x.test.ts::{0}",
        "src/x.test.ts::${value}",
        "src/x.test.ts::a block::%s",
        "src/test/java/a/XTest.java::{0}",
    ],
)
def test_a_title_with_nothing_but_placeholders_names_no_test(ref):
    """It would match every test of the file, and a report with another test would pass it."""
    module = script_module()
    cases = [("a block other", "src/x.test.ts", True, ""), ("other", "a.XTest", True, "")]
    assert module.test_result(ref, cases) == "missing"


def test_a_template_literal_matches_as_one_placeholder():
    module = script_module()
    assert module.title_matches("caps at ${LIMIT} tries", "caps at 5 tries")
    assert not module.title_matches("caps at ${LIMIT} tries", "caps at 5 calls")


def test_one_spelling_of_an_anchored_path():
    module = script_module()
    assert module.anchor_file("./src/a.py::Thing") == "src/a.py"
    assert module.anchor_file("src/a.py::Thing") == "src/a.py"


def test_a_title_with_a_comma_stays_one_reference():
    text = "## Rule Status\n\n### R-x\n- Tests: `a.ts::one, two`, `a.ts::three`\n- Code: a.py::f, b.py::g\n\n### R-y\n- Tests: none\n"
    found = script_module().blocks(text, "Rule Status")
    assert found["R-x"]["tests"] == ["a.ts::one, two", "a.ts::three"]
    assert found["R-x"]["code"] == ["a.py::f", "b.py::g"]
    assert found["R-y"]["tests"] == []


# ---------------------------------------------------------------- through check


def java_change(repo, ref):
    """A change whose rule is mapped to a JUnit test. The Python tests of the fixture still cover the other rule."""
    repo.checkout("-b", "feat")
    for rel, name in SOURCES.items():
        repo.write(rel, (REPORTS / "sources" / name).read_text(encoding="utf-8"))
    change = repo.feature("002-x", modified())
    repo.set_code(expiry=15)
    repo.review(change)
    repo.folded(change, impl(expiry_tests=ref))
    repo.commit("mapped to JUnit")
    return change


def copy_report(repo, runner, target):
    """A plain copy: the file is written now, as a run of the runner would write it."""
    directory = repo.path / target
    directory.mkdir(parents=True)
    for path in sorted((REPORTS / runner).glob("*.xml")):
        shutil.copyfile(str(path), str(directory / path.name))
    return target


@pytest.mark.parametrize(
    "runner, target, ref",
    [
        ("surefire", "target/surefire-reports", SERVICE + "::staysActiveWithinTheLimit"),
        ("gradle", "build/test-results/test", SERVICE + "::timeoutIsFifteenMinutes"),
    ],
)
def test_a_directory_of_real_reports_is_evidence(repo, runner, target, ref):
    change = java_change(repo, ref)
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", repo.junit(), copy_report(repo, runner, target))
    assert rc == 0, out
    assert out["states"][change] == "ready"


@pytest.mark.parametrize(
    "ref, needle",
    [
        (SERVICE + "::rememberMeIsNotImplemented", "failed"),
        (BROKEN + "::thisOneFails", "failed"),
        (SERVICE + "::aMinuteMoreExpires", "missing"),
    ],
)
def test_a_skipped_failed_or_absent_junit_test_blocks(repo, ref, needle):
    java_change(repo, ref)
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", repo.junit(), copy_report(repo, "surefire", "target/surefire-reports"))
    assert rc == 1
    assert hard_with(out, "mapped test %s %s" % (ref, needle))


def test_gradle_loses_the_method_of_a_parametrized_test_and_that_blocks(repo):
    ref = SERVICE + "::staysActiveWithinTheLimit"
    java_change(repo, ref)
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", repo.junit(), copy_report(repo, "gradle", "build/test-results/test"))
    assert rc == 1
    assert hard_with(out, "mapped test %s missing" % ref)


def test_one_tracked_file_in_a_directory_rejects_the_evidence(repo):
    java_change(repo, SERVICE + "::timeoutIsFifteenMinutes")
    target = copy_report(repo, "surefire", "target/surefire-reports")
    repo.git("add", "-f", target + "/TEST-com.example.auth.BrokenRuleTest.xml")
    repo.commit("commit part of the evidence")
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", repo.junit(), target)
    assert rc == 1
    assert hard_with(out, "TEST-com.example.auth.BrokenRuleTest.xml is tracked by git")


def test_a_directory_with_no_report_is_invalid_input(repo):
    (repo.path / "target").mkdir()
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", "target")
    assert rc == 2
    assert "no XML test report in target" in str(out)


def test_an_absent_report_is_invalid_input(repo):
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", "target/nothing")
    assert rc == 2
    assert "test report not found" in str(out)


def test_a_broken_file_in_a_directory_is_invalid_input(repo):
    target = copy_report(repo, "surefire", "target/surefire-reports")
    repo.write(target + "/TEST-broken.xml", "<testsuite")
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", target)
    assert rc == 2
    assert "not valid XML" in str(out) and "TEST-broken.xml" in str(out)


def test_a_report_with_no_time_is_judged_by_when_the_file_was_written(repo):
    java_change(repo, SERVICE + "::timeoutIsFifteenMinutes")
    junit = repo.junit()
    target = copy_report(repo, "surefire", "target/surefire-reports")
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", junit, target)
    assert rc == 0, out
    old = (repo.path / target / "TEST-com.example.auth.SessionServiceTest.xml")
    os.utime(str(old), (1000000000, 1000000000))
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", junit, target)
    assert rc == 1
    assert hard_with(out, "TEST-com.example.auth.SessionServiceTest.xml is older than the evaluated commit")


@pytest.mark.parametrize("zone", ["Asia/Kolkata", "America/Los_Angeles", "UTC"])
def test_a_time_with_no_zone_does_not_depend_on_where_the_machine_is(repo, zone):
    """Gradle and Jest write UTC with no zone. Read as local time, east of Greenwich a fresh report looked hours old."""
    java_change(repo, SERVICE + "::timeoutIsFifteenMinutes")
    junit = repo.junit()
    target = copy_report(repo, "gradle", "build/test-results/test")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    for path in (repo.path / target).glob("*.xml"):
        text = path.read_text(encoding="utf-8")
        start = text.index('timestamp="') + len('timestamp="')
        path.write_text(text[:start] + now + text[start + len(now):], encoding="utf-8")
    rc, out = repo.cap("check", "--mode", "ci", "--base", "main", "--report", junit, target, env={"TZ": zone})
    assert rc == 0, out


def test_a_test_runner_rooted_below_the_repository(repo):
    """Real pytest with its root in a subdirectory: the classname has no prefix for that directory."""
    report = repo.junit("--rootdir=tests", "tests")
    module = script_module()
    cases = module.junit_cases(repo.path / report)
    assert any(case[1] == "auth.test_session" for case in cases)
    assert module.test_result("tests/auth/test_session.py::test_expiry", cases) == "passed"
    assert module.test_result("other/auth/test_session.py::test_expiry", cases) == "passed"
    assert module.test_result("tests/other/test_session.py::test_expiry", cases) == "missing"
