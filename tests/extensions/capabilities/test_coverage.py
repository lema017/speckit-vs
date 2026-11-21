"""coverage: what the branch changed in the product, what records it in the catalog, and what never reached it.

It is what speckit.capabilities.record starts from, for a change made without the fork's commands.
"""

from __future__ import annotations

from datetime import datetime

from .conftest import CAT, EXPIRY_30, MARK, added, change_expiry, impl, modified

RECORD_DIR = CAT + "/_changes/20261121-expiry"


def coverage(repo, *args):
    rc, out = repo.cap("coverage", *args)
    assert rc == 0, out
    return out


def record_delta(entries, title="Expiry made by hand"):
    return "# %s\n\n## Capability Delta\n%s\n\n%s" % (title, MARK, entries)


def test_nothing_changed_is_none(repo):
    repo.checkout("-b", "feat")
    out = coverage(repo)
    assert out["status"] == "none"
    assert out["code"] == [] and out["changes"] == {} and out["pending"] == []
    assert out["base"] == "main"


def test_code_changed_without_a_change_is_missing_and_names_its_capability(repo):
    repo.checkout("-b", "feat")
    repo.set_code(expiry=15)
    out = coverage(repo)
    assert out["status"] == "missing"
    assert out["code"] == ["src/auth/session.py", "tests/auth/test_session.py"]
    # The rules of login name the code and the test in Code and Tests.
    assert out["capabilities"] == {"login": ["src/auth/session.py", "tests/auth/test_session.py"]}
    assert out["unmapped"] == []


def test_new_code_no_rule_names_is_unmapped(repo):
    repo.checkout("-b", "feat")
    repo.write("src/billing.py", "PRICE = 10\n")
    out = coverage(repo)
    assert out["status"] == "missing"
    assert out["unmapped"] == ["src/billing.py"] and out["capabilities"] == {}


def test_committed_and_uncommitted_changes_both_count(repo):
    repo.checkout("-b", "feat")
    repo.write("src/billing.py", "PRICE = 10\n")
    repo.commit("billing")
    repo.write("src/other.py", "x = 2\n")
    assert coverage(repo)["code"] == ["src/billing.py", "src/other.py"]


def test_files_that_do_not_change_the_product_are_left_out(repo):
    repo.checkout("-b", "feat")
    for rel in ("README.md", "docs/guide.md", ".github/workflows/ci.yml", ".claude/settings.json", ".specify/memory/x.txt",
                "specs/_slices/a.md", "graphify-out/graph.json", ".graphifyignore", ".gitattributes"):
        repo.write(rel, "x\n")
    repo.replace(".gitignore", "junit*.xml\n", "junit*.xml\nbuild/\n")
    out = coverage(repo)
    assert out["status"] == "none" and out["code"] == []


def test_coverage_ignore_takes_globs_from_the_config(repo):
    repo.checkout("-b", "feat")
    repo.config(coverage_ignore="infra/*, scripts/dev-*")
    repo.write("infra/stack/main.tf", "x\n")
    repo.write("scripts/dev-seed.py", "x\n")
    repo.write("scripts/release.py", "x\n")
    assert coverage(repo)["code"] == ["scripts/release.py"]


def test_a_folded_spec_records_the_branch(repo):
    change = change_expiry(repo)
    out = coverage(repo)
    assert out["status"] == "recorded"
    assert out["changes"] == {change: "prepared"} and out["pending"] == []


def test_a_spec_reviewed_and_not_folded_is_unrecorded(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", modified())
    repo.set_code(expiry=15)
    repo.review(change)
    out = coverage(repo)
    assert out["status"] == "unrecorded"
    assert out["pending"] == [change] and out["changes"][change] == "reviewed"


def test_a_spec_that_changes_no_rule_records_the_branch(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", "Capabilities: none — solo un texto de ayuda\n")
    repo.write("src/other.py", "x = 2\n")
    out = coverage(repo)
    assert out["status"] == "recorded" and out["changes"] == {change: "no-rule-change"}


def test_a_record_without_a_spec_goes_from_missing_to_recorded(repo):
    repo.checkout("-b", "feat/expiry-by-hand")
    repo.set_code(expiry=15)
    assert coverage(repo)["status"] == "missing"
    repo.write(RECORD_DIR + "/capability-delta.md", record_delta(modified(frm=EXPIRY_30, links="none")))
    out = coverage(repo)
    assert out["status"] == "unrecorded" and out["pending"] == [RECORD_DIR]
    repo.review(RECORD_DIR)
    repo.folded(RECORD_DIR, impl(expiry="Expira a los 15 minutos."), "--no-tasks")
    out = coverage(repo)
    assert out["status"] == "recorded" and out["changes"] == {RECORD_DIR: "prepared"}
    assert out["unrecorded"] == []


def test_record_folder_is_named_after_the_branch_and_today(repo):
    today = datetime.now().strftime("%Y%m%d")
    repo.checkout("-b", "feat/Expiry_by.Hand")
    assert coverage(repo)["record"] == "%s/_changes/%s-expiry-by-hand" % (CAT, today)


def test_record_folder_on_the_base_branch_is_a_change(repo):
    today = datetime.now().strftime("%Y%m%d")
    assert coverage(repo)["record"] == "%s/_changes/%s-change" % (CAT, today)
    repo.config(base_branch="trunk")
    repo.git("branch", "trunk")
    repo.checkout("trunk")
    assert coverage(repo)["record"] == "%s/_changes/%s-change" % (CAT, today)


def test_a_merged_spec_without_its_fold_is_listed_with_its_open_tasks(repo):
    """The case that started this: specs merged into main whose rules never reached the catalog."""
    done = repo.feature("002-done", added("R-remember-me", "Recuerda la sesión 30 días.", links="FR-001"))
    waiting = repo.feature("003-waiting", added("R-logout-all", "Cierra todas las sesiones.", links="FR-001"),
                           tasks="- [x] T001 Code\n- [ ] T002 Validate in production\n- [ ] T003 [post-merge] Deploy\n")
    bare = repo.feature("004-bare", added("R-audit", "Registra cada ingreso.", links="FR-001"), tasks=None)
    repo.feature("005-none", "Capabilities: none — solo un texto\n")
    repo.commit("merged without fold")
    out = coverage(repo)
    assert out["status"] == "none", "nothing differs from main: the merge is done"
    assert out["unrecorded"] == [
        {"change": done, "open_tasks": 0},
        {"change": waiting, "open_tasks": 1},
        {"change": bare, "open_tasks": None},
    ]


def test_a_folded_spec_and_a_folded_record_are_not_unrecorded(repo):
    change = change_expiry(repo)
    repo.checkout("main")
    repo.merge("feat")
    out = coverage(repo)
    assert {"change": "specs/001-login", "open_tasks": 0} not in out["unrecorded"]
    assert all(item["change"] != change for item in out["unrecorded"])


def test_unrecorded_reads_record_folders_and_skips_the_catalog_and_slices(repo):
    repo.write(CAT + "/_changes/20261101-old/capability-delta.md", record_delta(added("R-remember-me", "Recuerda la sesión.", links="none")))
    repo.write("specs/_slices/login.md", "# Slices\n" + MARK + "\n")
    repo.commit("record never folded")
    assert coverage(repo)["unrecorded"] == [{"change": CAT + "/_changes/20261101-old", "open_tasks": 0}]


def test_base_flag_compares_with_a_commit_already_merged(repo):
    before = repo.git("rev-parse", "HEAD").stdout.strip()
    repo.set_code(lockout=3)
    repo.commit("tweak on main")
    assert coverage(repo)["status"] == "none"
    out = coverage(repo, "--base", before)
    assert out["status"] == "missing" and out["capabilities"] == {"login": ["src/auth/session.py", "tests/auth/test_session.py"]}


def test_unknown_base_is_invalid(repo):
    rc, out = repo.cap("coverage", "--base", "nowhere")
    assert rc == 2 and out["status"] == "invalid" and "base not found: nowhere" in out["errors"][0]


def test_problems_of_a_change_on_the_branch_are_reported(repo):
    repo.checkout("-b", "feat")
    broken = added("R-remember-me", "Recuerda la sesión.", links="none").replace("- Capability: login\n", "")
    repo.write(RECORD_DIR + "/capability-delta.md", record_delta(broken))
    out = coverage(repo)
    assert out["status"] == "unrecorded" and out["changes"][RECORD_DIR] == "invalid"
    assert any("missing capability" in problem for problem in out["problems"]), out["problems"]


def test_a_drafted_record_is_pending_until_reviewed_and_folded(repo):
    repo.checkout("-b", "feat")
    repo.write(RECORD_DIR + "/capability-delta.md", record_delta(added("R-remember-me", "Recuerda la sesión.", links="none")))
    out = coverage(repo)
    assert out["changes"][RECORD_DIR] == "drafted" and out["pending"] == [RECORD_DIR] and out["problems"] == []


def test_folders_that_start_with_an_underscore_are_not_specs(repo):
    """The catalog, the slice maps and the product live beside the specs under _ names, as the progress page reads them."""
    repo.write("specs/_drafts/spec.md", "# Draft\n\n" + record_delta(added("R-remember-me", "Recuerda la sesión.", links="none")))
    repo.commit("a draft beside the specs")
    assert coverage(repo)["unrecorded"] == []
