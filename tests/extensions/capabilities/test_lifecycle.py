"""F1 of the Studio plan: a capability is designed first and built later.

The ``[designed]`` mark, ``DESIGNED`` and ``IMPLEMENTED``, ``publish-design``, ``delta-block``,
``rebase``, ``defer`` and ``index --rebuild``. The two-branch cases rebuild the project of F0b with
the real script and compare the result with the files F0b wrote by hand in ``fixtures/f0b/expected``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from .conftest import (
    CAT,
    IMPL,
    INDEX,
    LOCKOUT_5,
    MARK,
    Repo,
    added,
    delta_block,
    hard_with,
    impl,
    modified,
    removed,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "f0b"
SEAL = "<!-- capability-catalog: 2 -->"
LOGIN = CAT + "/login"
DESIGN = CAT + "/_changes/20261111-design-login"
REDESIGN = CAT + "/_changes/20261112-redesign-login"
RETIRE = CAT + "/_changes/20261112-retire-lockout"
ACCESO = "specs/001-acceso"
OAUTH = "specs/002-oauth"
LOCKOUT_15 = "Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos."
LOCKOUT_30 = "Tras 3 intentos fallidos seguidos, la cuenta se bloquea 30 minutos."
OAUTH_RULE = "Se puede entrar con una cuenta de Google, Facebook o GitHub."
ACCESO_CODE = (("lockout.py.txt", "src/auth/lockout.py"), ("test_lockout.py.txt", "tests/test_lockout.py"))
OAUTH_CODE = (("oauth.py.txt", "src/auth/oauth.py"), ("test_oauth.py.txt", "tests/test_oauth.py"))
CATALOG_FILES = (INDEX, LOGIN + "/spec.md", LOGIN + "/implementation.md", LOGIN + "/history.md")
DROP_REASON = "R-login-lockout vuelve a diseño (rebase --drop); FR-002 y US1/AC1 quedan fuera de alcance"


def fixture(rel):
    return (FIX / rel).read_text(encoding="utf-8")


def record(repo, change, text):
    """A design record, published and committed on the current branch."""
    repo.write(change + "/capability-delta.md", text)
    rc, out = repo.cap("publish-design", "--change", change)
    assert rc == 0 and out["status"] == "published", out
    repo.commit("design: " + change)
    return out


def implement(repo, name, code):
    """A spec of F0b on its own branch: written, reviewed, built, folded with F0b's draft, and committed."""
    change = "specs/" + name
    for doc in ("spec.md", "tasks.md"):
        repo.write("%s/%s" % (change, doc), fixture("specs/%s/%s" % (name, doc)))
    for source, target in code:
        repo.write(target, fixture("code/" + source))
    repo.review(change)
    repo.folded(change, fixture("drafts/%s.md" % name))
    repo.commit("feat: " + name)
    return change


def build_design(path):
    """main with login designed: four [designed] rules, published from F0b's record."""
    repo = Repo(path)
    path.mkdir(parents=True)
    repo.git("init", "-q", "-b", "main", ".")
    repo.write(".gitignore", "junit*.xml\n__pycache__/\n")
    repo.write("src/__init__.py", "")
    repo.write("src/auth/__init__.py", "")
    record(repo, DESIGN, fixture("records/20261111-design-login.md"))
    return repo


def copied(source, tmp_path):
    path = tmp_path / "repo"
    shutil.copytree(str(source), str(path))
    return Repo(path)


@pytest.fixture(scope="session")
def design_repo(tmp_path_factory):
    path = tmp_path_factory.mktemp("lifecycle") / "design"
    build_design(path)
    return path


@pytest.fixture(scope="session")
def s1_repo(tmp_path_factory):
    """F0b scenario 1: 001-acceso builds R-login-lockout while main redesigns it."""
    path = tmp_path_factory.mktemp("lifecycle") / "s1"
    repo = build_design(path)
    repo.checkout("-b", "001-acceso")
    implement(repo, "001-acceso", ACCESO_CODE)
    repo.checkout("main")
    record(repo, REDESIGN, fixture("records/20261112-redesign-login.md"))
    return path


@pytest.fixture(scope="session")
def s2_repo(tmp_path_factory):
    """F0b scenario 2: 001-acceso, merged into main, and 002-oauth build two rules of login."""
    path = tmp_path_factory.mktemp("lifecycle") / "s2"
    repo = build_design(path)
    repo.checkout("-b", "001-acceso")
    implement(repo, "001-acceso", ACCESO_CODE)
    repo.checkout("main")
    repo.merge("001-acceso")
    repo.checkout("-b", "002-oauth", "main~1")
    implement(repo, "002-oauth", OAUTH_CODE)
    return path


def test_a_commit_in_a_test_repo_starts_no_git_maintenance(tmp_path):
    """copied() copies the session's repos: a maintenance still running there drops its lock mid-copy."""
    repo = Repo(tmp_path)
    repo.git("init", "-q", "-b", "main", ".")
    repo.write("a.txt", "a\n")
    repo.git("add", "-A")
    traced = repo.git("commit", "-qm", "a", env={"GIT_TRACE": "1"}).stderr
    assert "maintenance run" not in traced and "gc --auto" not in traced, traced


@pytest.fixture
def design(design_repo, tmp_path):
    return copied(design_repo, tmp_path)


def unsealed(text):
    return text.replace(SEAL + "\n\n", "")


# F0b wrote its files with the 0.2.0 index template; 0.3.0 changed its sentence (6.3 of the plan).
OLD_INDEX_LINE = "Current behaviour of the product, one directory per capability."
NEW_INDEX_LINE = "Behaviour of the product, designed and current, one directory per capability."


def assert_expected(repo, case, rels):
    for rel in rels:
        expected = fixture("expected/%s/%s" % (case, rel[:-3] + ".expected.md")).replace(OLD_INDEX_LINE, NEW_INDEX_LINE)
        assert unsealed(repo.read(rel)) == expected, rel


def merge_conflicted(repo, into, other, commit):
    """git merge leaves the catalog conflicted. With ``commit``, the merge is committed with its markers."""
    repo.checkout(into)
    done = repo.merge(other, ok=False)
    assert done.returncode != 0, done.stdout
    if commit:
        repo.git("add", "-A")
        repo.git("commit", "-qm", "merge %s with conflict markers" % other)


def finish(repo, message="finish the merge"):
    repo.git("add", "-A")
    repo.git("commit", "-qm", message)


# ---------------------------------------------------------------- two branches, against F0b


def test_s1_check_fails_on_base_before_the_merge(s1_repo, tmp_path):
    repo = copied(s1_repo, tmp_path)
    repo.checkout("001-acceso")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "IMPLEMENTED R-login-lockout", "main now says", "3 intentos")


@pytest.mark.parametrize("commit", [False, True], ids=["merging", "merge-committed"])
def test_s1_merge_leaves_markers_that_review_prepare_and_check_reject(s1_repo, tmp_path, commit):
    repo = copied(s1_repo, tmp_path)
    merge_conflicted(repo, "001-acceso", "main", commit)
    assert "<<<<<<<" in repo.read(LOGIN + "/spec.md")
    for command in ("review", "prepare"):
        rc, out = repo.cap(command, "--change", ACCESO)
        assert rc == 3 and out["status"] == "merge-conflict", out
        assert "rebase --change specs/001-acceso" in out["reason"]
    rc, out = repo.cap("check")
    assert rc == 1 and hard_with(out, LOGIN + "/spec.md", "conflict markers", "rebase")


@pytest.mark.parametrize("commit", [False, True], ids=["merging", "merge-committed"])
def test_s1_rebase_stops_with_both_texts_and_the_three_choices(s1_repo, tmp_path, commit):
    repo = copied(s1_repo, tmp_path)
    merge_conflicted(repo, "001-acceso", "main", commit)
    before = repo.tree()
    rc, out = repo.cap("rebase", "--change", ACCESO)
    assert rc == 3 and out["status"] == "decision", out
    [conflict] = out["conflicts"]
    assert conflict["rule"] == "R-login-lockout"
    assert conflict["spec"] == LOCKOUT_15 and conflict["base"] == LOCKOUT_30 and conflict["base_designed"] is True
    assert conflict["choices"] == ["adopt", "keep", "drop"]
    assert repo.tree() == before


@pytest.mark.parametrize("direction", ["base-into-branch", "branch-into-base"])
@pytest.mark.parametrize("commit", [False, True], ids=["merging", "merge-committed"])
@pytest.mark.parametrize("choice", ["keep", "adopt", "drop"])
def test_s1_rebase_writes_what_f0b_expected(s1_repo, tmp_path, choice, commit, direction):
    repo = copied(s1_repo, tmp_path)
    into, other = ("001-acceso", "main") if direction == "base-into-branch" else ("main", "001-acceso")
    merge_conflicted(repo, into, other, commit)
    extra = ("--reason", DROP_REASON) if choice == "drop" else ()
    rc, out = repo.cap("rebase", "--change", ACCESO, "--" + choice, "R-login-lockout", *extra)
    assert rc == 0 and out["status"] == "rebased", out
    assert out["delta_changed"] is True and out["stamped"] is True
    assert_expected(repo, "s1/" + choice, CATALOG_FILES + (ACCESO + "/spec.md",))
    rc, out = repo.cap("review", "--change", ACCESO)
    assert rc == 0 and out["status"] == "unchanged", out


@pytest.mark.parametrize("choice", ["keep", "drop"])
def test_s1_keep_and_drop_reach_ready(s1_repo, tmp_path, choice):
    repo = copied(s1_repo, tmp_path)
    merge_conflicted(repo, "001-acceso", "main", False)
    extra = ("--reason", DROP_REASON) if choice == "drop" else ()
    rc, out = repo.cap("rebase", "--change", ACCESO, "--" + choice, "R-login-lockout", *extra)
    assert rc == 0, out
    finish(repo)
    rc, out = repo.ci()
    assert rc == 0 and out["hard"] == [], out
    assert out["states"][ACCESO] == ("ready" if choice == "keep" else "no-rule-change")


def edit_code(repo, path, *edits):
    """Edit a file of the sample project and drop Python's bytecode caches.

    These edits keep the file's size. If pytest compiled the file in the same second, Python
    would take the cached bytecode as current and run the old code.
    """
    for old, new in edits:
        repo.replace(path, old, new)
    for cache in list(repo.path.rglob("__pycache__")):
        shutil.rmtree(cache)


def test_s1_adopt_blocks_until_the_code_changes_and_fold_observes_it_again(s1_repo, tmp_path):
    repo = copied(s1_repo, tmp_path)
    merge_conflicted(repo, "001-acceso", "main", False)
    rc, out = repo.cap("rebase", "--change", ACCESO, "--adopt", "R-login-lockout")
    assert rc == 0, out
    assert any("FR-002, US1/AC1" in note for note in out["notes"]), out
    finish(repo)
    rc, out = repo.ci()
    assert rc == 1 and hard_with(out, "R-login-lockout", "state is unverified")
    assert out["states"][ACCESO] != "ready"

    edit_code(repo, "src/auth/lockout.py", ("MAX_FAILURES = 5", "MAX_FAILURES = 3"), ("LOCK_MINUTES = 15", "LOCK_MINUTES = 30"))
    edit_code(
        repo, "tests/test_lockout.py", ("range(4)", "range(2)"), ("minutes=14, seconds=59", "minutes=29, seconds=59"),
        ("assert not policy.is_locked(T0 + timedelta(minutes=15))", "assert not policy.is_locked(T0 + timedelta(minutes=30))"),
    )
    draft = repo.read(LOGIN + "/implementation.md").replace("- State: unverified", "- State: conforming")
    draft = draft.replace("15 minutos al quinto fallo", "30 minutos al tercer fallo")
    repo.folded(ACCESO, draft)
    finish(repo, "fold again after the redesign")
    rc, out = repo.ci()
    assert rc == 0 and out["hard"] == [], out
    assert out["states"][ACCESO] == "ready"


@pytest.mark.parametrize("direction", ["base-into-branch", "branch-into-base"])
@pytest.mark.parametrize("commit", [False, True], ids=["merging", "merge-committed"])
def test_s2_two_branches_on_one_capability_rebuild_to_what_f0b_expected(s2_repo, tmp_path, commit, direction):
    repo = copied(s2_repo, tmp_path)
    into, other = ("002-oauth", "main") if direction == "base-into-branch" else ("main", "002-oauth")
    merge_conflicted(repo, into, other, commit)
    lock = repo.read(OAUTH + "/capability-delta.lock.json")
    rc, out = repo.cap("rebase", "--change", OAUTH)
    assert rc == 0 and out["status"] == "rebased", out
    assert out["delta_changed"] is False and out["stamped"] is False and out["resolved"] == []
    assert_expected(repo, "s2", CATALOG_FILES)
    assert repo.read(OAUTH + "/capability-delta.lock.json") == lock
    if direction == "base-into-branch":
        finish(repo)
        rc, out = repo.ci()
        assert rc == 0 and out["hard"] == [], out
        assert out["states"][OAUTH] == "ready"


def test_s2_union_merge_leaves_two_index_rows_that_check_rejects(s2_repo, tmp_path):
    repo = copied(s2_repo, tmp_path)
    merge_conflicted(repo, "002-oauth", "main", True)
    index = repo.read(INDEX)
    assert index.count("| [login](login/spec.md) |") == 2, index
    rc, out = repo.cap("check")
    assert hard_with(out, "duplicated capability login", "rebase --change", "index --rebuild")


def test_rebase_after_a_rebase_is_stable(s2_repo, tmp_path):
    repo = copied(s2_repo, tmp_path)
    merge_conflicted(repo, "002-oauth", "main", False)
    assert repo.cap("rebase", "--change", OAUTH)[0] == 0
    before = repo.tree()
    rc, out = repo.cap("rebase", "--change", OAUTH)
    assert rc == 0 and out["written"] == [], out
    assert repo.tree() == before


def test_rebase_without_a_merge_needs_the_base_to_exist(s1_repo, tmp_path):
    repo = copied(s1_repo, tmp_path)
    repo.checkout("001-acceso")
    rc, out = repo.cap("rebase", "--change", ACCESO, "--onto", "nowhere")
    assert rc == 2 and "base not found: nowhere" in out["errors"][0], out
    rc, out = repo.cap("rebase", "--change", ACCESO)
    assert rc == 3 and out["conflicts"][0]["base"] == LOCKOUT_30, out


def test_rebase_refuses_choices_it_cannot_take(s1_repo, tmp_path):
    repo = copied(s1_repo, tmp_path)
    merge_conflicted(repo, "001-acceso", "main", False)
    before = repo.tree()
    for args, needle in (
        (("--keep", "R-login-lockout", "--drop", "R-login-lockout"), "choose one of"),
        (("--keep", "R-login-nothing"), "not in the delta"),
    ):
        rc, out = repo.cap("rebase", "--change", ACCESO, *args)
        assert rc == 2 and needle in out["errors"][0], out
    assert repo.tree() == before


def test_rebase_of_a_rule_the_base_retired_only_drops_it(s1_repo, tmp_path):
    """3.2 says --keep turns it into ADDED; retired ids are never reused, so rebase refuses and says why."""
    repo = copied(s1_repo, tmp_path)
    repo.checkout("main")
    repo.git("reset", "-q", "--hard", "main~1")
    record(repo, RETIRE, delta_record(removed("R-login-lockout", LOCKOUT_15, links="none")))
    repo.checkout("001-acceso")
    rc, out = repo.ci()
    assert rc == 1 and hard_with(out, "R-login-lockout", "retired by " + RETIRE, "rebase --change " + ACCESO)
    merge_conflicted(repo, "001-acceso", "main", False)
    rc, out = repo.cap("rebase", "--change", ACCESO)
    assert rc == 3 and out["conflicts"][0]["retired_by"] == RETIRE and out["conflicts"][0]["choices"] == ["drop"], out
    for choice in ("keep", "adopt"):
        rc, out = repo.cap("rebase", "--change", ACCESO, "--" + choice, "R-login-lockout")
        assert rc == 2 and "retired ids are not reused" in out["errors"][0], out
    rc, out = repo.cap("rebase", "--change", ACCESO, "--drop", "R-login-lockout")
    assert rc == 0 and out["status"] == "rebased", out
    assert "R-login-lockout" not in repo.read(LOGIN + "/spec.md")
    assert "| R-login-lockout |" in repo.read(LOGIN + "/history.md")
    assert "### R-login-lockout" not in repo.read(LOGIN + "/implementation.md")
    assert "Capabilities: none" in repo.read(ACCESO + "/spec.md")
    finish(repo)
    rc, out = repo.ci()
    assert rc == 0 and out["hard"] == [], out


def test_rebase_of_a_change_never_folded_rewrites_only_its_delta(design, tmp_path):
    repo = design
    repo.checkout("-b", "001-acceso")
    for doc in ("spec.md", "tasks.md"):
        repo.write("%s/%s" % (ACCESO, doc), fixture("specs/001-acceso/" + doc))
    repo.review(ACCESO)
    repo.commit("spec only")
    repo.checkout("main")
    record(repo, REDESIGN, fixture("records/20261112-redesign-login.md"))
    repo.checkout("001-acceso")
    repo.merge("main")
    catalog = [repo.read(rel) for rel in CATALOG_FILES]
    rc, out = repo.cap("rebase", "--change", ACCESO, "--adopt", "R-login-lockout")
    assert rc == 0 and out["folded"] is False, out
    assert [repo.read(rel) for rel in CATALOG_FILES] == catalog
    assert "- From: %s\n- To: %s" % (LOCKOUT_30, LOCKOUT_30) in repo.read(ACCESO + "/spec.md")
    assert repo.cap("review", "--change", ACCESO)[1]["status"] == "unchanged"


# ---------------------------------------------------------------- publish-design


def delta_record(entries, title="# Diseño: login\n\nAprobado por: Ana (PO)\n"):
    return "%s\n## Capability Delta\n%s\n\n%s" % (title, MARK, entries)


def designed(rule, to, frm="(none)", capability="login"):
    return "### DESIGNED %s\n- Capability: %s\n- From: %s\n- To: %s\n- Links: none\n" % (rule, capability, frm, to)


def implemented(rule, text, links="FR-001", capability="login"):
    return "### IMPLEMENTED %s\n- Capability: %s\n- From: %s\n- To: %s\n- Links: %s\n" % (rule, capability, text, text, links)


def test_publish_design_writes_designed_rules_a_designed_row_and_the_seal(design):
    spec = design.read(LOGIN + "/spec.md")
    assert "- **R-login-lockout** [designed]: %s (%s)" % (LOCKOUT_15, DESIGN) in spec
    assert spec.count("[designed]") == 4
    index = design.read(INDEX)
    assert index.startswith("# Capabilities\n\n%s\n\n" % SEAL), index
    assert "| [login](login/spec.md) | Entrar a la cuenta con correo o con Google, Facebook o GitHub | designed | none |" in index
    assert "## Rule Status\n\n## Retirement Evidence" in design.read(LOGIN + "/implementation.md")
    assert "| %s | DESIGNED R-login-lockout; DESIGNED R-login-oauth-providers;" % DESIGN in design.read(LOGIN + "/history.md")
    assert json.loads(design.read(DESIGN + "/capability-delta.lock.json"))["source"] == DESIGN


def test_publish_design_again_changes_nothing(design):
    before = design.tree()
    rc, out = design.cap("publish-design", "--change", DESIGN)
    assert rc == 0 and out["status"] == "unchanged" and out["written"] == [], out
    assert design.tree() == before


def test_a_design_record_reaches_ready_without_code(design):
    design.checkout("-b", "design-2")
    record(design, CAT + "/_changes/20261113-design-signup", delta_record(designed("R-login-signup", "Registrarse pide correo y contraseña.")))
    rc, out = design.ci()
    assert rc == 0 and out["hard"] == [], out
    assert out["states"][CAT + "/_changes/20261113-design-signup"] == "ready"


def test_a_design_record_retires_a_designed_rule_without_evidence(design):
    design.checkout("-b", "retire")
    change = CAT + "/_changes/20261113-retire-reset"
    record(design, change, delta_record(removed("R-login-reset-expiry", "El enlace para recuperar la contraseña vence a los 30 minutos.", links="none")))
    assert "R-login-reset-expiry" not in design.read(LOGIN + "/spec.md")
    assert "| R-login-reset-expiry |" in design.read(LOGIN + "/history.md")
    rc, out = design.ci()
    assert rc == 0 and out["states"][change] == "ready", out


@pytest.mark.parametrize("entries, needle", [
    (designed("R-login-x", "Algo.") + "\n" + added("R-login-y", "Otra cosa.", links="none"), "a design record declares only"),
    (added("R-login-y", "Otra cosa.", links="none"), "publish-design publishes NEW-CAPABILITY, DESIGNED and REMOVED"),
    (designed("R-login-lockout", LOCKOUT_15, frm=LOCKOUT_15), "From equals To"),
    (designed("R-login-lockout", "(none)", frm=LOCKOUT_15), "To cannot be (none)"),
])
def test_publish_design_rejects_what_a_design_record_does_not_declare(design, entries, needle):
    change = CAT + "/_changes/20261113-bad"
    design.write(change + "/capability-delta.md", delta_record(entries))
    before = design.tree()
    rc, out = design.cap("publish-design", "--change", change)
    assert rc == 2 and any(needle in error for error in out["errors"]), out
    assert design.tree() == before


def test_publish_design_takes_only_design_records(design):
    design.write(ACCESO + "/spec.md", fixture("specs/001-acceso/spec.md"))
    rc, out = design.cap("publish-design", "--change", ACCESO)
    assert rc == 2 and "takes a design record" in out["errors"][0], out


def test_designed_over_a_built_rule_is_a_conflict_that_says_modified(repo):
    change = CAT + "/_changes/20261113-redesign-lockout"
    repo.write(change + "/capability-delta.md", delta_record(designed("R-lockout", "Otra regla.", frm=LOCKOUT_5)))
    rc, out = repo.cap("publish-design", "--change", change)
    assert rc == 3 and "the rule is implemented; a spec changes it with MODIFIED" in out["conflicts"][0], out


def test_a_new_designed_rule_cannot_take_an_id_in_use(design):
    change = CAT + "/_changes/20261113-dup"
    design.write(change + "/capability-delta.md", delta_record(designed("R-login-lockout", "Otro texto.")))
    rc, out = design.cap("publish-design", "--change", change)
    assert rc == 3 and "already exists" in out["conflicts"][0], out


def test_publish_design_refuses_to_retire_a_built_rule(s1_repo, tmp_path):
    repo = copied(s1_repo, tmp_path)
    repo.checkout("001-acceso")
    change = CAT + "/_changes/20261113-retire-built"
    repo.write(change + "/capability-delta.md", delta_record(removed("R-login-lockout", LOCKOUT_15, links="none")))
    rc, out = repo.cap("publish-design", "--change", change)
    assert rc == 2 and "the rule is built" in out["errors"][0], out


def test_publish_design_waits_for_the_lock_and_for_recover(design):
    from .test_acceptance_concurrency import Holder

    design.write(REDESIGN + "/capability-delta.md", fixture("records/20261112-redesign-login.md"))
    before = design.tree()
    with Holder(design):
        rc, out = design.cap("publish-design", "--change", REDESIGN)
        assert rc == 5 and out["status"] == "busy", out
    assert design.tree() == before
    rc, out = design.cap("publish-design", "--change", REDESIGN, env={"CAP_CRASH_AFTER": "1"})
    assert rc == 9, out
    rc, out = design.cap("publish-design", "--change", REDESIGN)
    assert rc == 4 and out["status"] == "recover-needed", out
    rc, out = design.cap("recover")
    assert rc == 0 and out["status"] == "recovered", out
    assert "- **R-login-lockout** [designed]: %s (%s)" % (LOCKOUT_30, REDESIGN) in design.read(LOGIN + "/spec.md")
    rc, out = design.cap("publish-design", "--change", REDESIGN)
    assert rc == 0 and out["status"] == "unchanged", out


# ---------------------------------------------------------------- operations in a spec


def spec_for(entries, frs=("El sistema MUST bloquear la cuenta.", "El sistema MUST aceptar otros proveedores.")):
    lines = "\n".join("- **FR-%03d**: %s" % (number, text) for number, text in enumerate(frs, 1))
    return "# Feature\n\n### User Story 1 - Entrar\n\n**Acceptance Scenarios**:\n\n1. **Given** x, **Then** y.\n\n## Requirements\n\n%s\n\n%s" % (lines, delta_block(entries))


def test_designed_in_a_spec_is_invalid(design):
    design.write("specs/003-x/spec.md", spec_for(designed("R-login-z", "Algo.")))
    rc, out = design.cap("review", "--change", "specs/003-x")
    assert rc == 2 and any("only a design record" in error for error in out["errors"]), out


@pytest.mark.parametrize("entry, needle", [
    ("### IMPLEMENTED R-login-lockout\n- Capability: login\n- From: (none)\n- To: %s\n- Links: FR-001\n" % LOCKOUT_15, "a new rule is ADDED"),
    ("### IMPLEMENTED R-login-lockout\n- Capability: login\n- From: %s\n- To: %s\n- Links: FR-001\n" % (LOCKOUT_15, LOCKOUT_30), "From must equal To"),
])
def test_implemented_keeps_the_text_of_the_rule(design, entry, needle):
    design.write("specs/003-x/spec.md", spec_for(entry))
    rc, out = design.cap("review", "--change", "specs/003-x")
    assert rc == 2 and any(needle in error for error in out["errors"]), out


def test_implemented_of_a_built_rule_is_a_conflict(repo):
    repo.write("specs/003-x/spec.md", spec_for(implemented("R-lockout", LOCKOUT_5)))
    rc, out = repo.cap("review", "--change", "specs/003-x")
    assert rc == 3 and "the rule is not [designed]" in out["conflicts"][0], out


@pytest.mark.parametrize("entry, needle", [
    (added("R-login-lockout", LOCKOUT_15), "a spec builds it with IMPLEMENTED"),
    (removed("R-login-lockout", LOCKOUT_15), "run capabilities.py defer"),
])
def test_a_spec_neither_adds_nor_retires_a_designed_rule(design, entry, needle):
    design.write("specs/003-x/spec.md", spec_for(entry))
    rc, out = design.cap("review", "--change", "specs/003-x")
    assert rc == 3 and needle in out["conflicts"][0], out


def test_a_design_record_does_not_go_through_fold(design):
    rc, out = design.cap("prepare", "--change", DESIGN, "--no-tasks")
    assert rc == 2 and "publish-design" in out["errors"][0], out


def test_implemented_without_code_or_fold_never_reaches_ready(design):
    """The hole F0b found: an IMPLEMENTED delta, reviewed, with its tasks done and nothing folded."""
    design.checkout("-b", "001-acceso")
    for doc in ("spec.md", "tasks.md"):
        design.write("%s/%s" % (ACCESO, doc), fixture("specs/001-acceso/" + doc))
    design.review(ACCESO)
    design.commit("spec, no code, no fold")
    rc, out = design.ci()
    assert rc == 1 and out["states"][ACCESO] != "ready", out
    assert hard_with(out, "IMPLEMENTED R-login-lockout", "still [designed]", "fold publishes it")
    assert not [note for note in out["notes"] if "already delivered" in note], out


def test_fold_of_implemented_is_done_once_applied(s1_repo, tmp_path):
    repo = copied(s1_repo, tmp_path)
    repo.checkout("001-acceso")
    assert "- **R-login-lockout**: %s (%s)" % (LOCKOUT_15, ACCESO) in repo.read(LOGIN + "/spec.md")
    rc, out = repo.cap("prepare", "--change", ACCESO)
    assert rc == 0 and out["status"] == "unchanged", out


def test_modified_builds_a_designed_rule_with_new_text_and_evidence(design):
    design.checkout("-b", "003-reset")
    old = "El enlace para recuperar la contraseña vence a los 30 minutos."
    new = "El enlace para recuperar la contraseña vence a los 20 minutos."
    change = "specs/003-reset"
    design.write(change + "/spec.md", spec_for(modified("R-login-reset-expiry", old, new, links="FR-001")))
    design.write(change + "/tasks.md", "- [x] T001 Reset en src/auth/reset.py\n")
    design.write("src/auth/reset.py", "RESET_MINUTES = 20\n")
    design.write("tests/test_reset.py", "from src.auth.reset import RESET_MINUTES\n\n\ndef test_reset_expiry():\n    assert RESET_MINUTES == 20\n")
    design.review(change)
    block = "### R-login-reset-expiry\n- Observed: Vence a los 20 minutos.\n- State: conforming\n- Code: `src/auth/reset.py::RESET_MINUTES`\n- Tests: `tests/test_reset.py::test_reset_expiry`\n"
    design.folded(change, design.read(LOGIN + "/implementation.md").replace("## Rule Status\n", "## Rule Status\n\n" + block))
    design.commit("feat: reset")
    assert "- **R-login-reset-expiry**: %s (%s)" % (new, change) in design.read(LOGIN + "/spec.md")
    assert "| partial |" in design.read(INDEX)
    rc, out = design.ci()
    assert rc == 0 and out["states"][change] == "ready", out


# ---------------------------------------------------------------- review normalizes IMPLEMENTED


def test_review_fixes_a_slip_in_from_alone(design):
    typo = OAUTH_RULE.replace("GitHub", "Github")
    entry = "### IMPLEMENTED R-login-oauth-providers\n- Capability: login\n- From: %s\n- To: %s\n- Links: FR-002\n" % (typo, OAUTH_RULE)
    design.write("specs/003-x/spec.md", spec_for(entry))
    rc, out = design.cap("review", "--change", "specs/003-x")
    assert rc == 0 and out["normalized"][0]["catalog"] == OAUTH_RULE, out


def test_review_does_not_normalize_after_the_seal(s1_repo, tmp_path):
    """Once sealed, a text that differs from the catalog means the base changed the rule: that is rebase's call."""
    repo = copied(s1_repo, tmp_path)
    repo.checkout("001-acceso")
    repo.git("checkout", "main", "--", CAT)
    before = repo.read(ACCESO + "/spec.md")
    rc, out = repo.cap("review", "--change", ACCESO)
    assert rc == 3 and out["status"] == "conflict" and "run rebase" in out["conflicts"][0], out
    assert repo.read(ACCESO + "/spec.md") == before


def test_review_writes_the_catalog_text_into_implemented_and_says_so(design):
    typo = OAUTH_RULE.replace("GitHub", "Github")
    design.write("specs/003-x/spec.md", spec_for(implemented("R-login-oauth-providers", typo, links="FR-002")))
    rc, out = design.cap("review", "--change", "specs/003-x")
    assert rc == 0 and out["status"] == "stamped", out
    assert out["normalized"] == [{"rule": "R-login-oauth-providers", "from": typo, "to": typo, "catalog": OAUTH_RULE}]
    text = design.read("specs/003-x/spec.md")
    assert "- From: %s\n- To: %s" % (OAUTH_RULE, OAUTH_RULE) in text and typo not in text
    assert design.cap("review", "--change", "specs/003-x")[1]["status"] == "unchanged"


# ---------------------------------------------------------------- conflict markers


def test_markers_in_a_delta_stop_review_prepare_and_check(design):
    text = spec_for(implemented("R-login-oauth-providers", OAUTH_RULE, links="FR-002"))
    design.write("specs/003-x/spec.md", text.replace("### IMPLEMENTED", "<<<<<<< HEAD\n### IMPLEMENTED", 1).rstrip("\n") + "\n>>>>>>> main\n")
    design.write("specs/003-x/tasks.md", "- [x] T001\n")
    for command in ("review", "prepare"):
        rc, out = design.cap(command, "--change", "specs/003-x")
        assert rc == 3 and out["status"] == "merge-conflict", out
    rc, out = design.cap("check", "--change", "specs/003-x")
    assert rc == 1 and hard_with(out, "specs/003-x", "conflict markers"), out


def test_markers_in_the_catalog_stop_apply_and_check(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified())
    repo.set_code(expiry=15)
    repo.review(change)
    prepared = repo.prepare(change)
    repo.draft(prepared, impl())
    repo.write(IMPL, repo.read(IMPL) + "<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> main\n")
    rc, out = repo.cap("apply", "--change", change, "--staged", prepared["staging"])
    assert rc == 3 and out["status"] == "merge-conflict" and out["files"] == [IMPL], out
    rc, out = repo.cap("check")
    assert rc == 1 and hard_with(out, IMPL, "conflict markers"), out


def test_a_heading_underline_is_not_a_conflict_marker(repo):
    before = repo.cap("check")
    repo.write(IMPL, repo.read(IMPL) + "\nNotas\n=======\n\nSin marcas.\n")
    assert "\n=======\n" in repo.read(IMPL)
    rc, out = repo.cap("check")
    assert not hard_with(out, "conflict markers"), out
    assert (rc, out.get("hard")) == (before[0], before[1].get("hard")), out


# ---------------------------------------------------------------- defer


def two_rule_branch(design, oauth_state="unverified"):
    design.checkout("-b", "003-login")
    change = "specs/003-login"
    entries = implemented("R-login-lockout", LOCKOUT_15, links="FR-001") + "\n" + implemented("R-login-oauth-providers", OAUTH_RULE, links="FR-002")
    design.write(change + "/spec.md", spec_for(entries))
    design.write(change + "/tasks.md", "- [x] T001 src/auth/lockout.py\n- [x] T002 src/auth/oauth.py\n")
    for source, target in ACCESO_CODE + OAUTH_CODE:
        design.write(target, fixture("code/" + source))
    design.review(change)
    draft = fixture("drafts/001-acceso.md").replace("## Retirement Evidence", fixture("drafts/002-oauth.md").split("## Rule Status\n\n")[1].split("\n## Retirement Evidence")[0].replace("conforming", oauth_state) + "\n## Retirement Evidence")
    design.folded(change, draft)
    design.commit("feat: 003-login")
    return change


def test_defer_takes_the_rule_out_and_it_goes_back_to_designed(design):
    change = two_rule_branch(design)
    rc, out = design.ci()
    assert rc == 1 and hard_with(out, "R-login-oauth-providers", "state is unverified")
    rc, out = design.cap("defer", "--change", change, "R-login-oauth-providers")
    assert rc == 0 and out["status"] == "deferred", out
    assert out["links"] == {"R-login-oauth-providers": ["FR-002"]} and out["designed"] == ["R-login-oauth-providers"]
    spec = design.read(LOGIN + "/spec.md")
    assert "- **R-login-oauth-providers** [designed]: %s (%s)" % (OAUTH_RULE, DESIGN) in spec
    assert "- **R-login-lockout**: %s (%s)" % (LOCKOUT_15, change) in spec
    assert "### R-login-oauth-providers" not in design.read(LOGIN + "/implementation.md")
    assert "| %s | IMPLEMENTED R-login-lockout |" % change in design.read(LOGIN + "/history.md")
    assert "R-login-oauth-providers" not in design.read(change + "/spec.md").split("## Capability Delta")[1]
    assert design.cap("review", "--change", change)[1]["status"] == "unchanged"
    design.commit("defer oauth")
    rc, out = design.ci()
    assert rc == 0 and out["hard"] == [] and out["states"][change] == "ready", out


def test_defer_of_the_only_rule_leaves_capabilities_none(design):
    design.checkout("-b", "001-acceso")
    implement(design, "001-acceso", ACCESO_CODE)
    rc, out = design.cap("defer", "--change", ACCESO, "R-login-lockout")
    assert rc == 0, out
    assert "Capabilities: none — R-login-lockout left this change (defer); FR-002, US1/AC1 out of scope" in design.read(ACCESO + "/spec.md")
    for rel in CATALOG_FILES:
        assert design.read(rel) == design.git("show", "main:" + rel).stdout, rel
    design.commit("defer")
    rc, out = design.ci()
    assert rc == 0 and out["states"][ACCESO] == "no-rule-change", out


def test_defer_before_fold_edits_only_the_delta(design):
    design.write("specs/003-x/spec.md", spec_for(implemented("R-login-lockout", LOCKOUT_15) + "\n" + implemented("R-login-oauth-providers", OAUTH_RULE, links="FR-002")))
    design.review("specs/003-x")
    catalog = [design.read(rel) for rel in CATALOG_FILES]
    rc, out = design.cap("defer", "--change", "specs/003-x", "R-login-lockout")
    assert rc == 0 and out["folded"] is False, out
    assert [design.read(rel) for rel in CATALOG_FILES] == catalog


@pytest.mark.parametrize("args, needle", [
    ((), "defer takes the ids"),
    (("R-login-nothing",), "not in the delta"),
])
def test_defer_says_what_it_needs(design, args, needle):
    design.write("specs/003-x/spec.md", spec_for(implemented("R-login-lockout", LOCKOUT_15)))
    rc, out = design.cap("defer", "--change", "specs/003-x", *args)
    assert rc == 2 and needle in out["errors"][0], out


def test_defer_is_for_specs_not_design_records(design):
    rc, out = design.cap("defer", "--change", DESIGN, "R-login-lockout")
    assert rc == 2 and "design record" in out["errors"][0], out


# ---------------------------------------------------------------- delta-block, status, locate, clarify-context


def test_delta_block_prints_implemented_with_the_catalog_text(design):
    rc, out = design.cap("delta-block", "--implement", "R-login-lockout", "R-login-oauth-providers")
    assert rc == 0, out
    assert out["blocks"][0]["block"] == "### IMPLEMENTED R-login-lockout\n- Capability: login\n- From: %s\n- To: %s\n- Links: FR-###" % (LOCKOUT_15, LOCKOUT_15)
    assert out["text"].count("### IMPLEMENTED") == 2


def test_delta_block_refuses_rules_that_are_not_designed(repo):
    rc, out = repo.cap("delta-block", "--implement", "R-lockout", "R-nothing")
    assert rc == 2 and len(out["errors"]) == 2 and "not [designed]" in out["errors"][0], out


def test_status_locate_and_clarify_context_show_designed_rules_and_the_state(s1_repo, tmp_path):
    repo = copied(s1_repo, tmp_path)
    repo.checkout("001-acceso")
    rc, out = repo.cap("status")
    assert out["capabilities"]["login"]["state"] == "partial"
    assert out["capabilities"]["login"]["designed"] == ["R-login-oauth-providers", "R-login-one-account-per-email", "R-login-reset-expiry"]
    rc, out = repo.cap("locate", "--capability", "login")
    assert out["state"] == "partial" and "R-login-lockout" not in out["designed"] and len(out["designed"]) == 3
    rc, out = repo.cap("status", "--capability", "login")
    assert out["state"] == "partial" and out["rules"]["R-login-oauth-providers"]["designed"] is True
    rc, out = repo.cap("clarify-context", "--change", ACCESO)
    assert out["capabilities"]["login"]["designed"] and out["delta"]["entries"][0]["op"] == "IMPLEMENTED"


# ---------------------------------------------------------------- the format seal, the index and check


def test_a_newer_catalog_format_stops_every_command(repo):
    repo.replace(INDEX, "# Capabilities\n", "# Capabilities\n\n<!-- capability-catalog: 3 -->\n")
    for command in (("status",), ("check",), ("index", "--rebuild")):
        rc, out = repo.cap(*command)
        assert rc == 2 and "format 3" in out["errors"][0] and "specify upgrade" in out["errors"][0], out


def test_a_catalog_without_designed_rules_gets_no_seal(repo):
    assert "capability-catalog" not in repo.read(INDEX)


def test_check_wants_the_seal_once_there_are_designed_rules(design):
    design.replace(INDEX, SEAL + "\n\n", "")
    rc, out = design.cap("check")
    assert rc == 1 and hard_with(out, "format seal", "index --rebuild"), out
    rc, out = design.cap("index", "--rebuild")
    assert rc == 0 and out["status"] == "rebuilt", out
    assert SEAL in design.read(INDEX)


def test_check_wants_each_index_row_to_say_what_its_rules_make_it(design):
    design.replace(INDEX, "| designed | none |", "| consolidated | none |")
    rc, out = design.cap("check")
    assert rc == 1 and hard_with(out, "login says consolidated but its rules make it designed"), out
    rc, out = design.cap("index", "--rebuild")
    assert rc == 0 and "| designed | none |" in design.read(INDEX)
    assert design.cap("check")[0] == 0


def test_index_rebuild_collapses_the_rows_of_a_union_merge(s2_repo, tmp_path):
    repo = copied(s2_repo, tmp_path)
    merge_conflicted(repo, "002-oauth", "main", True)
    rc, out = repo.cap("index", "--rebuild")
    assert rc == 0 and out["capabilities"] == {"login": "partial"}, out
    index = repo.read(INDEX)
    assert index.count("| [login](login/spec.md) |") == 1 and "| partial |" in index
    rc, out = repo.cap("index", "--rebuild")
    assert out["status"] == "unchanged"


def test_index_rebuild_retires_a_capability_left_without_rules_and_keeps_planned_rows(repo):
    old = CAT + "/old"
    repo.write(old + "/spec.md", "# old\n\n## Overview\nViejo\n\n## Rules\n\n## Related Capabilities\n")
    repo.write(INDEX, repo.read(INDEX).rstrip("\n") + "\n| [old](old/spec.md) | Viejo | consolidated | none |\n| payments | Cobros | planned | none |\n")
    rc, out = repo.cap("check")
    assert not hard_with(out, "old says"), out
    rc, out = repo.cap("index", "--rebuild")
    assert rc == 0 and out["capabilities"]["old"] == "retired", out
    index = repo.read(INDEX)
    assert "| [old](old/spec.md) | Viejo | retired | none |" in index and "| payments | Cobros | planned | none |" in index


def test_check_finds_a_designed_mark_its_origin_did_not_set(s1_repo, tmp_path):
    repo = copied(s1_repo, tmp_path)
    repo.checkout("001-acceso")
    repo.replace(LOGIN + "/spec.md", "- **R-login-lockout**:", "- **R-login-lockout** [designed]:")
    repo.commit("mark it by hand")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-login-lockout", "does not match the [designed] mark")
    assert hard_with(out, "R-login-lockout", "without an authorizing delta")
    assert hard_with(out, "IMPLEMENTED R-login-lockout", "still [designed]") and out["states"][ACCESO] != "ready"


def test_check_finds_a_designed_mark_removed_by_hand(design):
    design.checkout("-b", "sneak")
    design.replace(LOGIN + "/spec.md", "- **R-login-reset-expiry** [designed]:", "- **R-login-reset-expiry**:")
    design.commit("unmark by hand")
    rc, out = design.ci()
    assert rc == 1 and hard_with(out, "R-login-reset-expiry", "without an authorizing delta"), out


def test_check_refuses_a_spec_that_retires_a_designed_rule(design):
    design.checkout("-b", "sneak")
    rule = "El enlace para recuperar la contraseña vence a los 30 minutos."
    design.write("specs/003-x/spec.md", spec_for(removed("R-login-reset-expiry", rule)))
    design.replace(LOGIN + "/spec.md", "- **R-login-reset-expiry** [designed]: %s (%s)\n\n" % (rule, DESIGN), "")
    design.commit("retire a designed rule from a spec")
    rc, out = design.ci()
    assert rc == 1 and hard_with(out, "REMOVED R-login-reset-expiry", "retired only by a design record", "defer"), out


def test_rebase_refuses_a_branch_that_folded_another_change_into_the_capability(design):
    design.checkout("-b", "both")
    implement(design, "001-acceso", ACCESO_CODE)
    implement(design, "002-oauth", OAUTH_CODE)
    design.checkout("main")
    record(design, REDESIGN, fixture("records/20261112-redesign-login.md"))
    merge_conflicted(design, "both", "main", False)
    rc, out = design.cap("rebase", "--change", ACCESO, "--keep", "R-login-lockout")
    assert rc == 2 and "also folded specs/002-oauth" in out["errors"][0], out
