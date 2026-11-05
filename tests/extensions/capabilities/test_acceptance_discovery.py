"""Acceptance 4: CI finds the features wherever the project keeps them."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import requires_bash
from tests.parity_helpers import bash_cmd, install_scripts, json_stdout, make_repo, py_cmd, run

from .conftest import CAT, MARK, SPEC, added, delta_block, hard_with, modified, spec_text

PLAIN_SPEC = "# Login\n\nA feature with no requirement keys, hook, marker or lock.\n"
FR_SPEC = "# Login\n\n## Requirements\n\n- **FR-001**: System MUST log in.\n"


def new_file(repo, rel, text):
    repo.checkout("-b", "x")
    repo.write(rel, text)
    repo.commit("new file")


def test_configured_root_catches_a_spec_with_hook_marker_and_lock_omitted(repo):
    repo.config(feature_roots="specs, features")
    new_file(repo, "features/auth/login/spec.md", PLAIN_SPEC)
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "features/auth/login/spec.md", "without a capability delta")


def test_requirement_signature_catches_it_when_the_root_is_not_configured(repo):
    new_file(repo, "features/auth/login/spec.md", FR_SPEC)
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "features/auth/login/spec.md", "outside feature_roots", "add its root to feature_roots")


def test_a_plain_spec_outside_the_roots_is_not_flagged(repo):
    new_file(repo, "docs/spec.md", PLAIN_SPEC)
    rc, out = repo.ci()
    assert rc == 0, out


def test_root_globs_match_a_path_segment(repo):
    repo.config(feature_roots="modules/*/specs")
    new_file(repo, "modules/auth/specs/login/spec.md", PLAIN_SPEC)
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "modules/auth/specs/login/spec.md", "without a capability delta")


def test_a_delta_with_marker_is_evaluated_wherever_it_lives(repo):
    repo.checkout("-b", "x")
    repo.write("features/auth/login/spec.md", spec_text(added("R-new", "Regla nueva.")))
    repo.commit("marker, no review, no fold")
    rc, out = repo.ci()
    assert rc == 1
    assert out["states"]["features/auth/login"] == "drafted"
    assert hard_with(out, "features/auth/login", "not reviewed")
    assert hard_with(out, "R-new", "delta requires")


def test_the_full_flow_works_for_a_feature_outside_specs(repo):
    repo.checkout("-b", "x")
    repo.config(feature_roots="specs, features")
    change = "features/auth/login"
    repo.write(change + "/spec.md", spec_text(modified()))
    repo.write(change + "/tasks.md", "- [x] T001 src/auth/session.py\n")
    repo.set_code(expiry=15)
    repo.review(change)
    from .conftest import impl

    repo.folded(change, impl())
    repo.commit("feature outside specs")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "ready"
    assert "(features/auth/login)" in repo.read(SPEC)


def test_a_new_catalog_spec_is_not_a_feature_but_the_reverse_check_names_its_rules(repo):
    new_file(repo, CAT + "/pagos/spec.md", "# pagos\n\n## Overview\nCobros.\n\n## Rules\n\n- **R-pago**: Cobra en dólares. (specs/099-x)\n\n## Related Capabilities\n")
    rc, out = repo.ci()
    assert rc == 1
    assert not hard_with(out, "without a capability delta")
    assert not hard_with(out, "outside feature_roots")
    assert hard_with(out, "R-pago", "without an authorizing delta")


def test_a_catalog_spec_with_requirement_lines_is_never_taken_for_a_feature(repo):
    repo.checkout("-b", "x")
    repo.write(CAT + "/login/notes/spec.md", FR_SPEC)
    repo.commit("odd file")
    rc, out = repo.ci()
    assert not hard_with(out, "outside feature_roots")
    assert not hard_with(out, "without a capability delta")
    assert rc == 0, out


def test_an_old_spec_edited_is_not_flagged_but_a_renamed_one_is_new(repo):
    repo.write("specs/000-old/spec.md", FR_SPEC)
    repo.commit("before the extension")
    repo.checkout("-b", "x")
    repo.write("specs/000-old/spec.md", FR_SPEC + "\nEdited.\n")
    repo.commit("edit")
    rc, out = repo.ci()
    assert rc == 0, out

    (repo.path / "specs/000-old").rename(repo.path / "specs/000-moved")
    repo.commit("move")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "specs/000-moved/spec.md", "without a capability delta")


def test_a_change_record_without_marker_is_flagged(repo):
    new_file(repo, ".specify/bugs/x/capability-delta.md", "# Sin marcador\n")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, ".specify/bugs/x/capability-delta.md", "without a capability delta")


def test_touching_any_file_of_a_feature_reevaluates_it_without_spec_changes(repo):
    repo.checkout("-b", "first")
    change = repo.feature("002-x", modified(), tasks="- [ ] T001 src/auth/session.py\n")
    repo.review(change)
    repo.commit("spec only")
    repo.checkout("main")
    repo.merge("first")
    repo.checkout("-b", "second")
    repo.write(change + "/tasks.md", "- [x] T001 src/auth/session.py\n")
    repo.commit("second part, no fold")
    rc, out = repo.ci()
    assert rc == 1
    assert change in out["states"]
    assert hard_with(out, "delta requires")


# ---------------------------------------------------------------- the naming contract


@pytest.mark.parametrize(
    "rel, message",
    [
        (CAT + "/001-login/spec.md", "capability directories must match"),
        (CAT + "/Pagos/spec.md", "capability directories must match"),
        (CAT + "/_other/spec.md", "capability directories must match"),
        (CAT + "/notes.md", "only index.md"),
        (CAT + "/_changes/fix-expiry/capability-delta.md", "YYYYMMDD-slug"),
        (CAT + "/_changes/2026-11-04-fix/capability-delta.md", "YYYYMMDD-slug"),
        (CAT + "/login/plan.md", "file name is not allowed"),
        (CAT + "/login/tasks.md", "file name is not allowed"),
        (CAT + "/login/README.md", "file name is not allowed"),
        (CAT + "/_changes/20261104-fix-expiry/plan.md", "file name is not allowed"),
    ],
)
def test_the_naming_contract_is_enforced(repo, rel, message):
    new_file(repo, rel, "x\n")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, message)


def test_a_record_with_a_date_prefix_is_valid_under_changes(repo):
    repo.checkout("-b", "fix")
    record = CAT + "/_changes/20261104-fix-expiry"
    repo.write(record + "/capability-delta.md", "# Fix\n\n" + delta_block(modified(links="none")))
    repo.set_code(expiry=15)
    repo.review(record)
    from .conftest import impl

    repo.folded(record, impl(), "--no-tasks")
    repo.commit("fix outside specify")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][record] == "ready"


@pytest.mark.parametrize(
    "command",
    [pytest.param(bash_cmd, marks=requires_bash), py_cmd],
    ids=["bash", "python"],
)
def test_numbering_ignores_the_catalog_and_its_dated_records(tmp_path: Path, command):
    project = make_repo(tmp_path)
    install_scripts(project, "create-new-feature")
    templates = project / ".specify" / "templates"
    templates.mkdir(parents=True)
    (templates / "spec-template.md").write_text("# Spec\n", encoding="utf-8")
    record = project / "specs" / "_capabilities" / "_changes" / "20261104-fix-expiry"
    record.mkdir(parents=True)
    (record / "capability-delta.md").write_text("x\n", encoding="utf-8")
    (project / "specs" / "_capabilities" / "login").mkdir()
    (project / "specs" / "007-existing").mkdir()
    subprocess.run(["git", "init", "-q", "."], cwd=project, check=True)
    assert sys.executable
    result = run(command(project, "create-new-feature", "--json", "--dry-run", "--short-name", "next", "Next thing"), project)
    assert result.returncode == 0, result.stderr
    assert json_stdout(result)["BRANCH_NAME"] == "008-next"


def test_marker_constant_matches_the_template():
    from .conftest import EXT_DIR

    assert MARK in (EXT_DIR / "templates" / "spec-template.md").read_text(encoding="utf-8")
