"""Acceptance 3: prepare, apply and recover against a second process."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from .conftest import EXPIRY_15, IMPL, LOCKOUT_3, LOCKOUT_5, PYTHON, SCRIPT, SPEC, hard_with, impl, modified

HOLDER = """
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("capabilities_holder", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with module.publish_lock(pathlib.Path(sys.argv[2])):
    print("held", flush=True)
    sys.stdin.read()
"""


def reviewed(repo, name="002-x", entries=None, code=True):
    change = repo.feature(name, entries or modified())
    if code:
        repo.set_code(expiry=15)
    repo.review(change)
    return change


def apply_staged(repo, change, prepared):
    return repo.cap("apply", "--change", change, "--staged", prepared["staging"])


def test_two_processes_on_one_change_the_second_detects_it_and_keeps_the_first(repo):
    repo.checkout("-b", "feat")
    change = reviewed(repo)
    first, second = repo.prepare(change), repo.prepare(change)
    assert first["staging"] != second["staging"], "two drafts must not share a directory"
    repo.draft(first, impl(expiry="Observado por el primero."))
    repo.draft(second, impl(expiry="Observado por el segundo."))

    rc, out = apply_staged(repo, change, first)
    assert rc == 0 and out["status"] == "published", out
    after_first = repo.tree()

    rc, out = apply_staged(repo, change, second)
    assert rc == 3 and out["status"] == "base-changed", out
    assert repo.tree() == after_first
    assert "Observado por el primero." in repo.read(IMPL)
    assert "Observado por el segundo." not in repo.read(IMPL)

    rc, out = repo.cap("prepare", "--change", change)
    assert rc == 0 and out["status"] == "unchanged"


def test_two_changes_on_one_capability_the_second_must_redraft_on_the_new_base(repo):
    repo.checkout("-b", "feat")
    expiry = reviewed(repo, "002-expiry")
    lockout = reviewed(repo, "003-lockout", modified("R-lockout", LOCKOUT_5, LOCKOUT_3), code=False)
    first, second = repo.prepare(expiry), repo.prepare(lockout)
    repo.draft(first, impl())
    repo.draft(second, impl(lockout="Bloquea al tercero, según el segundo.", expiry="Vista vieja: 30."))

    rc, out = apply_staged(repo, expiry, first)
    assert rc == 0, out
    after_first = repo.tree()

    rc, out = apply_staged(repo, lockout, second)
    assert rc == 3 and out["status"] == "base-changed", out
    assert repo.tree() == after_first

    fresh = repo.prepare(lockout)
    assert "Expira a los 15 minutos." in repo.read("%s/login/implementation.md" % fresh["staging"]), "the new draft starts from the first result"
    repo.set_code(lockout=3)
    repo.draft(fresh, impl(lockout="Bloquea al tercero."))
    rc, out = apply_staged(repo, lockout, repo_refresh(repo, lockout, fresh))
    assert rc == 0, out
    assert EXPIRY_15 in repo.read(SPEC) and LOCKOUT_3 in repo.read(SPEC)
    repo.commit("both")

    # The second change edited a file the first change's observation is anchored to.
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, expiry, "R-session-expiry", "observation is stale", "src/auth/session.py")

    # Observing again settles it, and the rule text does not move.
    repo.folded(expiry, impl(lockout="Bloquea al tercero."))
    repo.commit("observe again")
    rc, out = repo.ci()
    assert rc == 0, out
    assert set(out["states"].values()) == {"ready"}


def repo_refresh(repo, change, previous):
    """Code in scope changed after that prepare, so take a new one and keep the draft."""
    draft = repo.read("%s/login/implementation.md" % previous["staging"])
    fresh = repo.prepare(change)
    repo.draft(fresh, draft)
    return fresh


@pytest.mark.parametrize(
    "interfere, status",
    [
        (lambda repo, change: repo.write("src/auth/session.py", repo.read("src/auth/session.py") + "# edited\n"), "base-changed"),
        (lambda repo, change: repo.replace(change + "/spec.md", "after 15 minutes", "after 10 minutes"), "needs-review"),
        (lambda repo, change: repo.replace(change + "/spec.md", "- To: La sesión expira tras 15", "- To: La sesión expira tras 10"), "needs-review"),
        (lambda repo, change: repo.replace(SPEC, "La sesión expira tras 30 minutos", "La sesión expira tras 45 minutos"), "conflict"),
        (lambda repo, change: repo.write(change + "/tasks.md", "- [ ] T009 new task\n"), "blocked"),
        (lambda repo, change: repo.write(IMPL, repo.read(IMPL) + "\n# edited\n"), "base-changed"),
        (lambda repo, change: repo.write(SPEC.replace("spec.md", "history.md"), repo.read(SPEC.replace("spec.md", "history.md")) + "\n"), "base-changed"),
    ],
    ids=["code-in-scope", "fr-edited", "to-edited", "catalog-edited", "task-reopened", "implementation-edited", "history-edited"],
)
def test_apply_checks_its_inputs_again_after_the_model_drafted(repo, interfere, status):
    repo.checkout("-b", "feat")
    change = reviewed(repo)
    prepared = repo.prepare(change)
    repo.draft(prepared, impl())
    interfere(repo, change)
    before = repo.tree()
    rc, out = apply_staged(repo, change, prepared)
    assert rc == 3 and out["status"] == status, out
    assert repo.tree() == before


def test_apply_without_a_prepared_draft_is_refused(repo):
    repo.checkout("-b", "feat")
    change = reviewed(repo)
    before = repo.tree()
    rc, out = repo.cap("apply", "--change", change, "--staged", ".specify/capabilities/staging/none")
    assert rc == 3 and out["status"] == "needs-prepare"
    assert repo.tree() == before


def test_apply_with_the_draft_of_another_change_is_refused(repo):
    repo.checkout("-b", "feat")
    change = reviewed(repo)
    other = reviewed(repo, "003-other", "Capabilities: none — sin reglas\n", code=False)
    prepared = repo.prepare(change)
    repo.draft(prepared, impl())
    before = repo.tree()
    rc, out = repo.cap("apply", "--change", other, "--staged", prepared["staging"])
    assert (rc, out["status"]) == (0, "no-rule-change")
    assert repo.tree() == before

    third = reviewed(repo, "004-third", modified("R-lockout", LOCKOUT_5, LOCKOUT_3), code=False)
    rc, out = repo.cap("apply", "--change", third, "--staged", prepared["staging"])
    assert rc == 3 and out["status"] == "base-changed"
    assert repo.tree() != "" and LOCKOUT_3 not in repo.read(SPEC)


class Holder:
    """Holds the publish lock from a separate process, through the script's own primitive."""

    def __init__(self, repo):
        self.process = subprocess.Popen(
            [sys.executable, "-c", HOLDER, str(SCRIPT), str(repo.path)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf-8",
        )

    def __enter__(self):
        assert self.process.stdout.readline().strip() == "held"
        return self

    def __exit__(self, *_):
        self.process.communicate("")


def test_while_a_process_holds_the_lock_apply_and_recover_answer_busy_and_write_nothing(repo):
    repo.checkout("-b", "feat")
    change = reviewed(repo)
    prepared = repo.prepare(change)
    repo.draft(prepared, impl())
    before = repo.tree()
    with Holder(repo):
        rc, out = apply_staged(repo, change, prepared)
        assert rc == 5 and out["status"] == "busy", out
        rc, out = repo.cap("recover")
        assert rc == 5 and out["status"] == "busy", out
        rc, out = repo.cap("review", "--change", change, "--accept")
        assert rc == 5 and out["status"] == "busy", out
        assert repo.tree() == before
    rc, out = apply_staged(repo, change, prepared)
    assert rc == 0 and out["status"] == "published", out


def test_recover_does_not_touch_a_publication_in_progress(repo):
    repo.checkout("-b", "feat")
    change = reviewed(repo)
    rc, out = repo.fold(change, impl(), env={"CAP_CRASH_AFTER": "1"})
    assert rc == 9
    before = repo.tree()
    with Holder(repo):
        rc, out = repo.cap("recover")
        assert rc == 5
        assert (repo.path / ".specify/capabilities/journal").exists()
        assert repo.tree() == before
    rc, out = repo.cap("recover")
    assert rc == 0 and out["status"] == "recovered"


def test_a_crashed_process_does_not_leave_the_lock_taken(repo):
    repo.checkout("-b", "feat")
    change = reviewed(repo)
    rc, _ = repo.fold(change, impl(), env={"CAP_CRASH_AFTER": "before-journal"})
    assert rc == 9
    prepared = repo.prepare(change)
    repo.draft(prepared, impl())
    rc, out = apply_staged(repo, change, prepared)
    assert rc == 0 and out["status"] == "published", out


@pytest.mark.parametrize("round_number", range(4))
def test_simultaneous_applies_publish_once_and_leave_a_consistent_tree(repo, round_number):
    repo.checkout("-b", "feat")
    change = reviewed(repo)
    drafts = [repo.prepare(change) for _ in range(2)]
    repo.draft(drafts[0], impl(expiry="Observado A."))
    repo.draft(drafts[1], impl(expiry="Observado B."))
    env = dict(os.environ)
    processes = [
        subprocess.Popen(
            [PYTHON, "-I", "-S", str(SCRIPT), "apply", "--root", str(repo.path), "--change", change, "--staged", draft["staging"]],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", env=env,
        )
        for draft in drafts
    ]
    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=60)
        assert not stderr.strip(), stderr
        results.append((process.returncode, json.loads(stdout)))

    published = [out for rc, out in results if rc == 0 and out["status"] == "published"]
    assert len(published) == 1, results
    other = next(item for item in results if item[1] is not published[0])
    assert other[0] in (3, 5), results

    assert not (repo.path / ".specify/capabilities/journal").exists()
    implementation = repo.read(IMPL)
    assert ("Observado A." in implementation) != ("Observado B." in implementation)
    assert EXPIRY_15 in repo.read(SPEC)
    repo.commit("one publication")
    rc, out = repo.ci()
    assert rc == 0, out
