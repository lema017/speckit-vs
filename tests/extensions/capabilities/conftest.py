"""Real git repositories, the script as a subprocess, and real pytest JUnit reports.

The script runs with ``-I -S``: no site-packages, so PyYAML or anything else
installed in the test environment cannot leak in. Set ``CAP_TEST_PYTHON`` to
run the script under another interpreter, such as Python 3.9.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EXT_DIR = ROOT / "extensions" / "capabilities"
SCRIPT = Path(os.environ.get("CAP_TEST_SCRIPT") or EXT_DIR / "scripts" / "python" / "capabilities.py")
PYTHON = os.environ.get("CAP_TEST_PYTHON", sys.executable)
CAT = "specs/_capabilities"
SPEC = CAT + "/login/spec.md"
IMPL = CAT + "/login/implementation.md"
HISTORY = CAT + "/login/history.md"
INDEX = CAT + "/index.md"
CONFIG = ".specify/extensions/capabilities/capabilities-config.yml"
MARK = "<!-- capability-delta:v1 -->"
EXPIRY_30 = "La sesión expira tras 30 minutos de inactividad."
EXPIRY_15 = "La sesión expira tras 15 minutos de inactividad."
EXPIRY_20 = "La sesión expira tras 20 minutos de inactividad."
LOCKOUT_5 = "La cuenta se bloquea al quinto intento fallido."
LOCKOUT_3 = "La cuenta se bloquea al tercer intento fallido."
LOCKOUT_6 = "La cuenta se bloquea al sexto intento fallido."
TEST_EXPIRY = "tests/auth/test_session.py::test_expiry"
TEST_LOCKOUT = "tests/auth/test_session.py::test_lockout"
TEST_FREE = "tests/auth/test_session.py::test_unrelated"
SESSION_CODE = """EXPIRY_MINUTES = {expiry}


class SessionManager:
    \"\"\"Server-side sessions.\"\"\"

    def expiry(self):
        return EXPIRY_MINUTES


LOCK_AT = {lockout}
"""
SESSION_TESTS = """import os

from auth.session import EXPIRY_MINUTES, LOCK_AT


def gate(name):
    assert os.environ.get("CAP_FAIL") != name


def test_expiry():
    gate("test_expiry")
    assert EXPIRY_MINUTES == {expiry}


def test_lockout():
    gate("test_lockout")
    assert LOCK_AT == {lockout}


def test_unrelated():
    gate("test_unrelated")
"""


def block(rule, observed, state="conforming", tests=TEST_EXPIRY, code="`src/auth/session.py::SessionManager`"):
    shown = tests if tests.startswith(("manual:", "none")) else "`%s`" % tests
    return "### %s\n- Observed: %s\n- State: %s\n- Code: %s\n- Tests: %s\n" % (rule, observed, state, code, shown)


def impl(expiry="Expira a los 15 minutos.", expiry_state="conforming", lockout="Bloquea al quinto intento.", lockout_state="conforming", expiry_tests=TEST_EXPIRY, retirement="", more="", with_lockout=True):
    parts = []
    if with_lockout:
        parts.append(block("R-lockout", lockout, lockout_state, TEST_LOCKOUT))
    parts.append(block("R-session-expiry", expiry, expiry_state, expiry_tests))
    if more:
        parts.append(more)
    body = "\n".join(parts)
    tail = "\n## Retirement Evidence\n\n" + retirement if retirement else ""
    return "# login: implementation\n\n## Rule Status\n\n%s%s" % (body, tail)


def retirement_block(rule, change, state="conforming", tests=TEST_FREE, observed="El comportamiento ya no existe."):
    shown = tests if tests.startswith(("manual:", "none")) else "`%s`" % tests
    return "### %s\n- Change: %s\n- Observed: %s\n- State: %s\n- Code: none\n- Tests: %s\n" % (rule, change, observed, state, shown)


def delta_block(entries):
    return "## Capability Delta *(mandatory)*\n\n%s\n%s" % (MARK, entries)


def modified(rule="R-session-expiry", frm=EXPIRY_30, to=EXPIRY_15, capability="login", links="FR-001, US1/AC1"):
    return "### MODIFIED %s\n- Capability: %s\n- From: %s\n- To: %s\n- Links: %s\n" % (rule, capability, frm, to, links)


def added(rule, to, capability="login", links="FR-001"):
    return "### ADDED %s\n- Capability: %s\n- From: (none)\n- To: %s\n- Links: %s\n" % (rule, capability, to, links)


def removed(rule, frm, replaced="none", capability="login", links="FR-001"):
    return "### REMOVED %s\n- Capability: %s\n- From: %s\n- To: (none)\n- Replaced-By: %s\n- Links: %s\n" % (rule, capability, frm, replaced, links)


def spec_text(entries, fr="System MUST expire the session after 15 minutes."):
    return "# Feature\n\n### User Story 1 - Expiry\n\n**Acceptance Scenarios**:\n\n1. **Given** idle, **Then** logged out.\n\n## Requirements\n\n- **FR-001**: %s\n\n%s" % (fr, delta_block(entries))


class Repo:
    def __init__(self, path: Path):
        self.path = path

    def git(self, *args, ok=True, env=None):
        full_env = dict(os.environ)
        full_env.update(env or {})
        # No automatic maintenance. Recent git starts `git maintenance run --auto --detach`
        # after a commit or a merge, and it creates and removes .git/objects/maintenance.lock
        # in the background. A fixture repo copied with copytree meanwhile failed on macOS CI.
        done = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
             "-c", "maintenance.auto=false", "-c", "gc.auto=0", *args],
            cwd=self.path, capture_output=True, encoding="utf-8", errors="replace", env=full_env,
        )
        if ok and done.returncode:
            raise AssertionError("git %s: %s" % (args, done.stderr))
        return done

    def cap(self, command, *args, env=None):
        full_env = dict(os.environ)
        full_env.update(env or {})
        done = subprocess.run(
            [PYTHON, "-I", "-S", str(SCRIPT), command, "--root", str(self.path), *args],
            capture_output=True, encoding="utf-8", errors="replace", env=full_env,
        )
        try:
            out = json.loads(done.stdout) if done.stdout.strip() else {}
        except ValueError:
            out = {"raw": done.stdout}
        if done.stderr.strip():
            out["stderr"] = done.stderr.strip()[-600:]
        return done.returncode, out

    def write(self, rel, text):
        path = self.path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read(self, rel):
        return (self.path / rel).read_text(encoding="utf-8")

    def replace(self, rel, old, new):
        text = self.read(rel)
        assert old in text, "%r not in %s" % (old, rel)
        self.write(rel, text.replace(old, new))

    def commit(self, message="change", date=None):
        self.git("add", "-A")
        env = {"GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date} if date else None
        self.git("commit", "-qm", message, env=env)

    def checkout(self, *args):
        self.git("checkout", "-q", *args)

    def merge(self, branch, ok=True):
        return self.git("merge", "-q", "--no-edit", branch, ok=ok)

    def tree(self):
        digest = hashlib.sha256()
        for path in sorted(self.path.rglob("*")):
            rel = path.relative_to(self.path).as_posix()
            if not path.is_file() or rel.startswith((".git/", ".specify/capabilities/", ".pytest_cache/")) or "__pycache__" in rel or rel.startswith("junit"):
                continue
            digest.update(rel.encode("utf-8"))
            digest.update(path.read_bytes())
        return digest.hexdigest()[:16]

    def set_code(self, expiry=None, lockout=None, tests=True):
        rel = "src/auth/session.py"
        text = self.read(rel)
        test_rel = "tests/auth/test_session.py"
        test_text = self.read(test_rel)
        if expiry is not None:
            text = re.sub(r"^EXPIRY_MINUTES = \d+", "EXPIRY_MINUTES = %d" % expiry, text, flags=re.M)
            test_text = re.sub(r"EXPIRY_MINUTES == \d+", "EXPIRY_MINUTES == %d" % expiry, test_text)
        if lockout is not None:
            text = re.sub(r"^LOCK_AT = \d+", "LOCK_AT = %d" % lockout, text, flags=re.M)
            test_text = re.sub(r"LOCK_AT == \d+", "LOCK_AT == %d" % lockout, test_text)
        self.write(rel, text)
        if tests:
            self.write(test_rel, test_text)

    def feature(self, name, entries, fr="System MUST expire the session after 15 minutes.", tasks="- [x] T001 Change expiry in src/auth/session.py\n"):
        directory = "specs/" + name
        self.write(directory + "/spec.md", spec_text(entries, fr))
        self.write(directory + "/plan.md", "Change src/auth/session.py\n")
        if tasks is not None:
            self.write(directory + "/tasks.md", tasks)
        return directory

    def review(self, change, *args):
        rc, out = self.cap("review", "--change", change, *args)
        assert rc == 0, out
        return out

    def prepare(self, change, *args):
        rc, out = self.cap("prepare", "--change", change, *args)
        assert rc == 0 and out["status"] == "ready", out
        return out

    def draft(self, prepared, drafts):
        """Write what the model would write. ``drafts`` is text for login, or {capability: text}."""
        if isinstance(drafts, str):
            drafts = {"login": drafts}
        for capability, text in drafts.items():
            self.write("%s/%s/implementation.md" % (prepared["staging"], capability), text)

    def fold(self, change, drafts, *args, env=None):
        prepared = self.prepare(change, *args)
        self.draft(prepared, drafts)
        return self.cap("apply", "--change", change, "--staged", prepared["staging"], *args, env=env)

    def folded(self, change, drafts, *args):
        rc, out = self.fold(change, drafts, *args)
        assert rc == 0 and out["status"] == "published", out
        return out

    def junit(self, *pytest_args, name="junit.xml", fail=None):
        """Run real pytest on the fixture project. Returns the report path."""
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "COV_", "CAP_")) and k != "PYTHONPATH"}
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        if fail:
            env["CAP_FAIL"] = fail
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml=" + name, *pytest_args],
            cwd=self.path, capture_output=True, encoding="utf-8", errors="replace", env=env,
        )
        assert (self.path / name).is_file(), "pytest wrote no report"
        return name

    def ci(self, *pytest_args, base="main", extra=(), fail=None):
        return self.cap("check", "--mode", "ci", "--base", base, "--report", self.junit(*pytest_args, fail=fail), *extra)

    def config(self, **values):
        self.write(CONFIG, "".join("%s: %s\n" % item for item in values.items()))


def build_template(path: Path) -> None:
    """main with one delivered feature: rules R-lockout and R-session-expiry, through the real pipeline."""
    repo = Repo(path)
    path.mkdir(parents=True)
    repo.git("init", "-q", "-b", "main", ".")
    repo.write("src/auth/session.py", SESSION_CODE.format(expiry=30, lockout=5))
    repo.write("src/other.py", "x = 1\n")
    repo.write("tests/auth/test_session.py", SESSION_TESTS.format(expiry=30, lockout=5))
    repo.write("pytest.ini", "[pytest]\npythonpath = src\n")
    repo.write(".gitignore", "junit*.xml\n__pycache__/\n")
    entries = "### NEW-CAPABILITY login\n- Covers: Autenticación y sesión\n\n" + added("R-lockout", LOCKOUT_5) + "\n" + added("R-session-expiry", EXPIRY_30)
    directory = repo.feature("001-login", entries, fr="System MUST expire the session after 30 minutes.")
    repo.review(directory)
    repo.folded(directory, impl(expiry="Expira a los 30 minutos."))
    repo.commit("base")


@pytest.fixture(scope="session")
def template_repo(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("capabilities") / "template"
    build_template(path)
    return path


@pytest.fixture
def repo(template_repo, tmp_path) -> Repo:
    path = tmp_path / "repo"
    shutil.copytree(str(template_repo), str(path))
    return Repo(path)


def change_expiry(repo: Repo, name="002-x", to=15, text=EXPIRY_15, branch="feat", code=True, observed=None, state="conforming"):
    """On a new branch: reviewed, folded and committed change of the expiry rule."""
    repo.checkout("-b", branch)
    change = repo.feature(name, modified(to=text))
    if code:
        repo.set_code(expiry=to)
    repo.review(change)
    repo.folded(change, impl(expiry=observed or "Expira a los %d minutos." % to, expiry_state=state))
    repo.commit("feature " + name)
    return change


def deliver(repo: Repo, branch="feat", next_branch="next"):
    """Integrate a branch into main and start another one."""
    repo.checkout("main")
    repo.merge(branch)
    repo.checkout("-b", next_branch)


def hard_with(out, *needles):
    return [line for line in out.get("hard", []) if all(needle in line for needle in needles)]
