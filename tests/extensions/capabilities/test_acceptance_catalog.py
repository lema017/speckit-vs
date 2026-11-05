"""Acceptance 1: the catalog is validated in both directions, and the history backs it."""

from __future__ import annotations

import pytest

from .conftest import (
    CAT,
    EXPIRY_15,
    EXPIRY_30,
    HISTORY,
    IMPL,
    LOCKOUT_5,
    LOCKOUT_6,
    MARK,
    SPEC,
    TEST_EXPIRY,
    block,
    change_expiry,
    delta_block,
    deliver,
    hard_with,
    impl,
    modified,
)


def test_hand_edit_next_to_a_legitimate_change_fails_and_names_the_rule(repo):
    """The decisive case: the PR changes expiry for real and bumps lockout from 5 to 6 by hand."""
    change = change_expiry(repo)
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "ready"

    repo.replace(SPEC, LOCKOUT_5, LOCKOUT_6)
    repo.commit("sneak a second rule change in the same file")
    rc, out = repo.ci()

    assert rc == 1
    assert hard_with(out, "R-lockout", "without an authorizing delta", "quinto", "sexto")
    assert not hard_with(out, "R-session-expiry"), "the expiry delta and its tests do pass"
    assert out["states"][change] == "ready"


@pytest.mark.parametrize(
    "edit, expected",
    [
        (lambda text: text.replace("## Rules\n\n", "## Rules\n\n- **R-extra**: Regla agregada a mano. (specs/001-login)\n\n"), "added as"),
        (lambda text: text.replace("- **R-lockout**: %s (specs/001-login)\n\n" % LOCKOUT_5, ""), "removed"),
        (lambda text: text.replace("%s (specs/001-login)" % LOCKOUT_5, "%s (specs/002-x)" % LOCKOUT_5), "now says"),
        (lambda text: text.replace("**R-lockout**:", "**R-lockout** [inferred]:"), "now says"),
    ],
    ids=["added", "removed", "origin-retagged", "marked-inferred"],
)
def test_any_catalog_change_needs_an_authorizing_delta(repo, edit, expected):
    change_expiry(repo)
    repo.write(SPEC, edit(repo.read(SPEC)))
    repo.commit("hand edit")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "without an authorizing delta", expected)


def test_deleting_a_whole_capability_by_hand_fails(repo):
    repo.checkout("-b", "x")
    repo.git("rm", "-rq", CAT + "/login")
    repo.commit("drop capability")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-lockout", "without an authorizing delta", "removed")
    assert hard_with(out, "R-session-expiry", "without an authorizing delta", "removed")
    assert hard_with(out, "history was removed")


def test_a_delta_for_another_value_does_not_authorize_the_catalog_text(repo):
    change = change_expiry(repo)
    repo.replace(SPEC, EXPIRY_15, "La sesión expira tras 16 minutos de inactividad.")
    repo.commit("catalog drifts from To")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-session-expiry", "without an authorizing delta")
    assert hard_with(out, "delta requires")
    assert out["states"][change] == "reviewed"


def bootstrap_record(repo, op="INFERRED", rule="R-rate-limit", text="Se admiten 10 intentos por minuto."):
    record = CAT + "/_changes/20261104-bootstrap-login"
    from_text = "(none)" if op == "INFERRED" else text
    repo.write(record + "/capability-delta.md", "# Bootstrap\n\n" + delta_block("### %s %s\n- Capability: login\n- From: %s\n- To: %s\n- Links: none\n" % (op, rule, from_text, text)))
    return record


def rate_block():
    return block("R-rate-limit", "Limita a 10.", "unverified", "none", "`src/other.py`")


def test_bootstrap_operations_authorize_inferred_rules_and_their_validation(repo):
    repo.checkout("-b", "boot")
    record = bootstrap_record(repo)
    repo.review(record)
    repo.folded(record, impl(expiry="Expira a los 30 minutos.", more=rate_block()), "--no-tasks")
    repo.commit("bootstrap")
    assert "**R-rate-limit** [inferred]:" in repo.read(SPEC)
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][record] == "ready"

    deliver(repo, "boot", "validate")
    record = CAT + "/_changes/20261105-validate-login"
    repo.write(record + "/capability-delta.md", "# Validate\n\n" + delta_block("### VALIDATED R-rate-limit\n- Capability: login\n- From: Se admiten 10 intentos por minuto.\n- To: Se admiten 10 intentos por minuto.\n- Links: none\n"))
    repo.review(record)
    repo.folded(record, impl(expiry="Expira a los 30 minutos.", more=rate_block()), "--no-tasks")
    repo.commit("validated")
    assert "[inferred]" not in repo.read(SPEC)
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][record] == "ready"


def test_inferred_rule_written_by_hand_is_not_authorized(repo):
    repo.checkout("-b", "boot")
    repo.replace(SPEC, "## Rules\n\n", "## Rules\n\n- **R-rate-limit** [inferred]: Se admiten 10 intentos por minuto. (bootstrap/20261104)\n\n")
    repo.commit("no bootstrap record")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-rate-limit", "without an authorizing delta")
    assert hard_with(out, "R-rate-limit", "does not exist")


def test_validated_cannot_change_the_text(repo):
    repo.checkout("-b", "boot")
    record = bootstrap_record(repo)
    repo.review(record)
    repo.folded(record, impl(expiry="Expira a los 30 minutos.", more=rate_block()), "--no-tasks")
    repo.commit("bootstrap")
    deliver(repo, "boot", "validate")
    repo.replace(SPEC, "**R-rate-limit** [inferred]: Se admiten 10 intentos", "**R-rate-limit**: Se admiten 99 intentos")
    record = CAT + "/_changes/20261105-validate-login"
    repo.write(record + "/capability-delta.md", "# Validate\n\n" + delta_block("### VALIDATED R-rate-limit\n- Capability: login\n- From: Se admiten 10 intentos por minuto.\n- To: Se admiten 10 intentos por minuto.\n- Links: none\n"))
    repo.commit("validated with another value")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-rate-limit", "without an authorizing delta")


@pytest.mark.parametrize(
    "bad, message",
    [
        ("## Rules\n\nLa sesión también se cierra al salir.\n\n", "is not a rule"),
        ("## Rules\n\n- **R-lockout**: Copia. (specs/001-login)\n\n", "duplicate rule id"),
    ],
    ids=["free-text", "duplicate-id"],
)
def test_rules_section_is_parsed_strictly(repo, bad, message):
    repo.checkout("-b", "x")
    repo.replace(SPEC, "## Rules\n\n", bad)
    repo.commit("bad rules")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, message)


def test_behaviour_cannot_hide_outside_the_rules_section(repo):
    repo.checkout("-b", "x")
    repo.replace(SPEC, "## Related Capabilities", "## Edge Cases\n- Si el reloj adelanta, manda el servidor.\n\n## Related Capabilities")
    repo.commit("edge cases")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "Edge Cases", "not allowed")

    repo.replace(SPEC, "## Edge Cases\n- Si el reloj adelanta, manda el servidor.\n\n", "")
    repo.replace(SPEC, "## Related Capabilities", "## Related Capabilities\n- **R-hidden**: Regla escondida. (specs/001-login)")
    repo.commit("rule outside")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-hidden", "outside ## Rules")


def test_overview_prose_can_change_without_a_delta(repo):
    repo.checkout("-b", "x")
    repo.replace(SPEC, "## Overview\n", "## Overview\nAutenticación, sesión y más.\n")
    repo.commit("prose")
    rc, out = repo.ci()
    assert rc == 0, out


@pytest.mark.parametrize(
    "new_tag, message",
    [("specs/404-gone", "does not exist"), ("specs/001-login-copy", "sets"), ("../outside", "outside the repository"), (None, "no origin tag")],
    ids=["missing-origin", "origin-says-other", "outside-repo", "no-tag"],
)
def test_provenance_is_checked_on_every_ci_run(repo, new_tag, message):
    """Broken on main already, and this PR touches nothing related: the run still reports it."""
    if new_tag == "specs/001-login-copy":
        repo.write(new_tag + "/capability-delta.md", "# Otro\n\n" + delta_block(modified(rule="R-lockout", frm="x", to="Otro texto.", links="none")))
    tag = " (%s)" % new_tag if new_tag else ""
    repo.replace(SPEC, "%s (specs/001-login)" % LOCKOUT_5, LOCKOUT_5 + tag)
    repo.commit("broken on main")
    repo.checkout("-b", "unrelated")
    repo.write("docs/notes.txt", "nada que ver\n")
    repo.commit("unrelated")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-lockout", message)


def delivered_change(repo):
    change = change_expiry(repo)
    deliver(repo)
    return change


@pytest.mark.parametrize(
    "edit, message",
    [
        (lambda repo, c: repo.replace(c + "/spec.md", EXPIRY_15, "La sesión expira tras 16 minutos."), "delta of a delivered change was edited"),
        (lambda repo, c: repo.replace(c + "/spec.md", "## Capability Delta", "## Capability Delta (old)\n\n## Other"), "delta of a delivered change was edited"),
        (lambda repo, c: repo.replace(c + "/spec.md", MARK + "\n", ""), "marker gone"),
        (lambda repo, c: (repo.path / c / "spec.md").unlink(), "document deleted"),
        (lambda repo, c: (repo.path / c).rename(repo.path / "specs/002-renamed"), "document deleted"),
        (lambda repo, c: repo.replace(c + "/capability-delta.lock.json", '"schema": 1', '"schema": 2'), "lock of a delivered change"),
        (lambda repo, c: (repo.path / c / "capability-delta.lock.json").unlink(), "lock of a delivered change"),
    ],
    ids=["delta-edited", "section-renamed", "marker-removed", "doc-deleted", "doc-renamed", "lock-edited", "lock-removed"],
)
def test_a_delivered_record_is_sealed(repo, edit, message):
    change = delivered_change(repo)
    edit(repo, change)
    repo.commit("rewrite history")
    rc, out = repo.ci()
    assert rc == 1, out
    assert hard_with(out, message)


def test_editing_the_prose_of_a_delivered_spec_is_only_a_notice(repo):
    change = delivered_change(repo)
    repo.replace(change + "/spec.md", "System MUST", "The system MUST")
    repo.commit("typo")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "delivered"
    assert any("already delivered" in note for note in out["notes"])


def test_a_delivered_no_rule_change_record_is_sealed_too(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", "Capabilities: none — solo un texto de ayuda\n")
    repo.commit("no rule change")
    deliver(repo)
    repo.replace(change + "/spec.md", "solo un texto de ayuda", "otro motivo")
    repo.commit("rewrite reason")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "delta of a delivered change was edited")


@pytest.mark.parametrize(
    "edit, message",
    [
        (lambda repo: repo.replace(HISTORY, "| specs/001-login | ADDED R-lockout; ADDED R-session-expiry |\n", ""), "row removed or edited"),
        (lambda repo: repo.replace(HISTORY, "ADDED R-lockout; ADDED R-session-expiry", "ADDED R-lockout"), "row removed or edited"),
        (lambda repo: repo.replace(HISTORY, "## Retired Rules", "| specs/099-ghost | MODIFIED R-lockout |\n\n## Retired Rules"), "new row does not match"),
        (lambda repo: repo.write(HISTORY, repo.read(HISTORY) + "| R-ghost | Texto | specs/099-ghost | none |\n"), "new retired row does not match"),
    ],
    ids=["row-removed", "row-edited", "row-invented", "retired-invented"],
)
def test_history_is_append_only_and_new_rows_need_a_delta(repo, edit, message):
    repo.checkout("-b", "x")
    edit(repo)
    repo.commit("history by hand")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, message)


def test_removing_a_retired_row_fails(repo):
    repo.checkout("-b", "feat")
    change = repo.feature("002-x", "### REMOVED R-lockout\n- Capability: login\n- From: %s\n- To: (none)\n- Replaced-By: none\n- Links: FR-001\n" % LOCKOUT_5)
    repo.review(change)
    from .conftest import retirement_block

    repo.folded(change, impl(expiry="Expira a los 30 minutos.", with_lockout=False, retirement=retirement_block("R-lockout", change)))
    repo.commit("retire")
    deliver(repo)
    repo.replace(HISTORY, "| R-lockout | %s | %s | none |\n" % (LOCKOUT_5, change), "")
    repo.commit("forget it was retired")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "row removed or edited in Retired Rules")


def test_rule_status_may_change_without_a_delta_but_conforming_needs_evidence(repo):
    repo.checkout("-b", "observe")
    repo.replace(IMPL, "### R-session-expiry\n- Observed: Expira a los 30 minutos.\n- State: conforming", "### R-session-expiry\n- Observed: Sigue en 45.\n- State: discrepant")
    repo.commit("record a discrepancy")
    rc, out = repo.ci()
    assert rc == 0, out

    deliver(repo, "observe", "fix")
    repo.replace(IMPL, "### R-session-expiry\n- Observed: Sigue en 45.\n- State: discrepant", "### R-session-expiry\n- Observed: Ya expira a los 30.\n- State: conforming")
    repo.commit("bugfix restores conformity")
    rc, out = repo.ci()
    assert rc == 0, out

    rc, out = repo.ci("--deselect", TEST_EXPIRY)
    assert rc == 1
    assert hard_with(out, "Rule Status changed to conforming", TEST_EXPIRY, "missing")

    rc, out = repo.ci(fail="test_expiry")
    assert rc == 1
    assert hard_with(out, "Rule Status changed to conforming", TEST_EXPIRY, "failed")


def test_removing_a_status_block_of_a_rule_in_force_fails(repo):
    repo.checkout("-b", "x")
    text = repo.read(IMPL)
    repo.write(IMPL, text[:text.index("### R-lockout")] + text[text.index("### R-session-expiry"):])
    repo.commit("drop block")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-lockout", "Rule Status block removed")


def test_same_rule_id_in_two_capabilities_fails(repo):
    repo.checkout("-b", "feat")
    entries = "### NEW-CAPABILITY pagos\n- Covers: Cobros\n\n### ADDED R-lockout\n- Capability: pagos\n- From: (none)\n- To: Otra cosa.\n- Links: FR-001\n"
    change = repo.feature("002-x", entries)
    repo.review(change)
    repo.folded(change, {"pagos": "# pagos\n\n## Rule Status\n\n" + block("R-lockout", "x", tests=TEST_EXPIRY)})
    repo.commit("same id")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "R-lockout", "several capabilities")


def test_expiry_rule_constant_stays_in_sync():
    assert EXPIRY_30 != EXPIRY_15
