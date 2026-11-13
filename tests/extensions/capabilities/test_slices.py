"""Slices: one spec builds one thing a person can do and check.

The maps under ``specs/_slices/``, the ``## Slice`` section of a spec, the state read from the
specs, and what ``check`` reports when they disagree. The project is F0b's login: four designed
rules, cut into four slices.
"""

from __future__ import annotations

import importlib.util
import json
import re

import pytest

from .conftest import CAT, CONFIG, EXT_DIR as EXT, INDEX, MARK, ROOT, added, delta_block, removed
from .test_lifecycle import ACCESO_CODE, DESIGN, build_design, copied, delta_record, designed, fixture, record

MAP = "specs/_slices/login.md"
MAP_MARK = "<!-- slice-map:v1 -->"
CLAVE, SOCIAL, RECUPERAR, REGISTRO = "D-login-clave", "D-login-social", "D-login-recuperar", "D-login-registro"
LOCKOUT, OAUTH, ONE_ACCOUNT, RESET = "R-login-lockout", "R-login-oauth-providers", "R-login-one-account-per-email", "R-login-reset-expiry"
ACCESO = "specs/001-acceso"
BIG = "specs/002-grande"
NO_RULES = "Capabilities: none — no cambia ninguna regla\n"
BUDGET = {"stories": 1, "requirements": 10, "rules": 4, "tasks": 25}


@pytest.fixture(scope="session")
def designed_repo(tmp_path_factory):
    path = tmp_path_factory.mktemp("slices") / "design"
    build_design(path)
    return path


@pytest.fixture
def design(designed_repo, tmp_path):
    """main with login designed: four [designed] rules and no slice map yet."""
    return copied(designed_repo, tmp_path)


def block(slice_id, title="Entrar", depends="none", rules="none", more=None, without=()):
    fields = {"Intent": "Una persona entra a su cuenta.", "Verify": "Entro y veo mi cuenta.", "Depends-On": depends, "Rules": rules}
    fields.update(more or {})
    return "### %s %s\n%s" % (slice_id, title, "".join("- %s: %s\n" % item for item in fields.items() if item[0] not in without))


def slice_map(*blocks, later="", mark=MAP_MARK):
    text = "# Slices: login\n\n%s\n\nRequest: Login completo.\n\n%s" % (mark, "\n".join(blocks))
    return text + ("\n## Later\n\n" + later if later else "")


def put(repo, *blocks, name="login", **options):
    repo.write("specs/_slices/%s.md" % name, slice_map(*blocks, **options))


def login(repo):
    """F0b's login cut into four slices: each designed rule in the one slice that builds it."""
    put(
        repo,
        block(CLAVE, "Entrar con usuario y clave", rules=LOCKOUT),
        block(SOCIAL, "Entrar con Google, Facebook o GitHub", depends=CLAVE, rules="%s, %s" % (OAUTH, ONE_ACCOUNT)),
        block(RECUPERAR, "Recuperar la clave", depends=CLAVE, rules=RESET),
        block(REGISTRO, "Crear una cuenta", depends=CLAVE),
    )


def declared(value, out="none"):
    return "## Slice *(mandatory)*\n\n- Slice: %s\n- Out: %s\n\n" % (value, out)


def spec(value=None, entries=NO_RULES):
    """A spec with one story. ``value`` is what its ## Slice says; None is a spec from before slices."""
    return "# Feature\n\n%s### User Story 1 - Entrar\n\n**Acceptance Scenarios**:\n\n1. **Given** a, **Then** b.\n\n## Requirements\n\n- **FR-001**: System MUST x.\n\n%s" % (
        "" if value is None else declared(value), delta_block(entries))


def acceso(repo, value=CLAVE):
    """F0b's spec that builds the lockout rule, naming its slice."""
    text = fixture("specs/001-acceso/spec.md")
    if value is not None:
        text = text.replace("## User Scenarios", declared(value) + "## User Scenarios", 1)
    repo.write(ACCESO + "/spec.md", text)


def deliver(repo):
    """001-acceso built, reviewed and folded, as fold leaves it."""
    acceso(repo)
    repo.write(ACCESO + "/tasks.md", fixture("specs/001-acceso/tasks.md"))
    for source, target in ACCESO_CODE:
        repo.write(target, fixture("code/" + source))
    repo.review(ACCESO)
    repo.folded(ACCESO, fixture("drafts/001-acceso.md"))


def check(repo):
    return repo.cap("slices", "check")


def hard(repo, *needles):
    out = check(repo)[1]
    return [line for line in out["hard"] if all(needle in line for needle in needles)]


def notes(repo, *needles):
    out = check(repo)[1]
    return [line for line in out["notes"] if all(needle in line for needle in needles)]


def status(repo, *args):
    rc, out = repo.cap("slices", "status", *args)
    assert rc == 0, out
    return out


def slices(repo):
    return {item["id"]: item for found in status(repo)["maps"] for item in found["slices"]}


# ---------------------------------------------------------------- the shape of a map


def test_a_project_without_maps_has_nothing_to_report(design):
    assert check(design) == (0, {"status": "ok", "hard": [], "notes": [], "maps": []})
    out = status(design)
    assert out["maps"] == [] and out["standalone"] == []
    assert out["unassigned_designed"] == [LOCKOUT, OAUTH, ONE_ACCOUNT, RESET]


def test_a_map_lists_its_slices_in_the_order_it_was_written(design):
    login(design)
    assert check(design) == (0, {"status": "ok", "hard": [], "notes": [], "maps": [MAP]})
    found = status(design)["maps"][0]
    assert (found["map"], found["name"], found["request"]) == (MAP, "login", "Login completo.")
    assert [item["id"] for item in found["slices"]] == [CLAVE, SOCIAL, RECUPERAR, REGISTRO]
    social = found["slices"][1]
    assert social["title"] == "Entrar con Google, Facebook o GitHub"
    assert social["intent"] == "Una persona entra a su cuenta." and social["verify"] == "Entro y veo mi cuenta."
    assert social["depends_on"] == [CLAVE] and social["rules"] == [OAUTH, ONE_ACCOUNT]


def test_a_file_without_the_marker_is_not_a_map(design):
    put(design, block(CLAVE), mark="")
    rc, out = check(design)
    assert rc == 1 and out["status"] == "invalid"
    assert out["hard"] == ["%s: not a slice map, the marker is missing: %s" % (MAP, MAP_MARK)]


def test_a_map_of_a_newer_format_is_not_read(design):
    put(design, block(CLAVE), mark="<!-- slice-map:v2 -->")
    assert hard(design, "uses slice map format 2 and this script reads up to 1: update with specify upgrade")
    assert status(design)["maps"][0]["slices"] == []


def test_a_map_with_conflict_markers_is_not_read(design):
    design.write(MAP, "<<<<<<< HEAD\n" + slice_map(block(CLAVE)) + "=======\n" + block(SOCIAL) + ">>>>>>> other\n")
    assert hard(design, MAP, "merge conflict markers")


def test_a_heading_that_is_not_a_slice_is_an_error(design):
    put(design, "### Login con clave\n- Intent: x\n", block(CLAVE))
    assert hard(design, "heading is not a slice", "### Login con clave")
    assert list(slices(design)) == [CLAVE]


@pytest.mark.parametrize("field", ["Intent", "Verify", "Depends-On", "Rules"])
def test_a_slice_needs_each_required_field(design, field):
    put(design, block(CLAVE, without=(field,)))
    assert hard(design) == ["%s: %s: field %s is missing" % (MAP, CLAVE, field)]


def test_a_slice_needs_a_title(design):
    put(design, block(CLAVE, title=""))
    assert hard(design, CLAVE, "the heading has no title")


def test_a_field_a_map_does_not_know_is_an_error(design):
    put(design, block(CLAVE, more={"Status": "done"}))
    assert hard(design) == ["%s: %s: unknown field Status" % (MAP, CLAVE)]


def test_a_field_written_twice_is_an_error(design):
    put(design, block(CLAVE) + "- Intent: Otra cosa.\n")
    assert hard(design) == ["%s: %s: field Intent appears twice" % (MAP, CLAVE)]


def test_a_field_takes_one_line(design):
    put(design, block(CLAVE) + "  y sigue en otra línea\n")
    assert hard(design, CLAVE, "unexpected line, a field takes one line", "y sigue en otra línea")


@pytest.mark.parametrize("field, value, needle", [
    ("Depends-On", "login-clave", "Depends-On takes slice ids or none: login-clave"),
    ("Rules", "lockout", "Rules takes rule ids or none: lockout"),
    ("Kind", "technical", "Kind takes `enabler"),
])
def test_a_field_takes_only_what_it_is_for(design, field, value, needle):
    put(design, block(CLAVE, more={field: value}))
    assert hard(design, CLAVE, needle)


def test_what_sits_in_a_comment_is_not_part_of_the_map(design):
    put(design, block(CLAVE), "<!--\n%s-->\n" % block("D-login-ejemplo", more={"Status": "x"}))
    assert check(design)[0] == 0
    assert list(slices(design)) == [CLAVE]


def test_a_line_under_later_names_a_rule_and_a_reason(design):
    put(design, block(CLAVE), later="- %s: espera al correo\n- recuperar la clave\n" % RESET)
    assert hard(design) == ["%s: line in ## Later is not `- R-<id>: <reason>`: - recuperar la clave" % MAP]
    assert status(design)["maps"][0]["later"] == [{"rule": RESET, "reason": "espera al correo"}]


# ---------------------------------------------------------------- what a map names


def test_a_slice_id_is_used_once_in_a_map(design):
    put(design, block(CLAVE), block(CLAVE, "Otra"))
    assert hard(design) == ["%s: slice id %s is already used in %s; an id is never reused" % (MAP, CLAVE, MAP)]


def test_a_slice_id_is_used_once_across_maps(design):
    put(design, block(CLAVE))
    put(design, block(CLAVE), name="registro")
    assert hard(design) == ["specs/_slices/registro.md: slice id %s is already used in %s; an id is never reused" % (CLAVE, MAP)]


def test_a_dependency_must_exist(design):
    put(design, block(CLAVE, depends="D-login-otra"))
    assert hard(design) == ["%s: %s depends on D-login-otra, which no map defines" % (MAP, CLAVE)]


def test_a_slice_does_not_depend_on_itself(design):
    put(design, block(CLAVE, depends=CLAVE))
    assert hard(design) == ["%s: %s depends on itself" % (MAP, CLAVE)]


def test_a_slice_depends_only_on_slices_above_it(design):
    put(design, block(CLAVE, depends=SOCIAL), block(SOCIAL))
    assert hard(design) == ["%s: %s depends on %s, which comes later in the map; a slice depends only on slices above it" % (MAP, CLAVE, SOCIAL)]
    put(design, block(SOCIAL), block(CLAVE, depends=SOCIAL))
    assert check(design)[0] == 0


def test_a_slice_may_depend_on_a_slice_of_another_map(design):
    put(design, block(CLAVE))
    put(design, block("D-perfil-foto", depends=CLAVE), name="perfil")
    assert check(design)[0] == 0
    assert slices(design)["D-perfil-foto"]["waiting_for"] == [CLAVE]


def test_a_cycle_across_maps_is_an_error(design):
    put(design, block(CLAVE, depends="D-perfil-foto"))
    put(design, block("D-perfil-foto", depends=CLAVE), name="perfil")
    assert hard(design) == ["dependency cycle: %s > D-perfil-foto > %s" % (CLAVE, CLAVE)]


def test_a_slice_does_not_depend_on_a_dropped_one(design):
    put(design, block(CLAVE, more={"Dropped": "no se hará"}), block(SOCIAL, depends=CLAVE))
    assert hard(design) == ["%s: %s depends on %s, which was dropped" % (MAP, SOCIAL, CLAVE)]


def test_a_rule_a_slice_names_is_in_the_catalog(design):
    put(design, block(CLAVE, rules="R-login-no-existe"))
    assert hard(design) == ["%s: %s names R-login-no-existe, which is not in the catalog" % (MAP, CLAVE)]


def test_a_rule_retired_after_the_cut_is_still_known(design):
    put(design, block(CLAVE, rules=RESET), later="- %s: después\n" % LOCKOUT)
    record(design, CAT + "/_changes/20261113-retire-reset", delta_record(removed(RESET, "El enlace para recuperar la contraseña vence a los 30 minutos.", links="none")))
    assert check(design)[0] == 0


def test_a_rule_is_built_by_one_slice(design):
    put(design, block(CLAVE, rules=LOCKOUT), block(SOCIAL, rules="%s, %s" % (OAUTH, LOCKOUT)))
    assert hard(design) == ["%s is in several slices: %s, %s; a rule is built by one slice" % (LOCKOUT, CLAVE, SOCIAL)]


def test_the_rules_of_a_dropped_slice_are_free_again(design):
    put(design, block(CLAVE, rules=LOCKOUT, more={"Dropped": "se parte de otra forma"}), block(SOCIAL, rules=LOCKOUT))
    assert check(design)[0] == 0
    put(design, block(CLAVE, rules="R-login-no-existe", more={"Dropped": "ya no"}))
    assert check(design)[0] == 0


def test_a_rule_is_in_a_slice_or_left_for_later_never_both(design):
    put(design, block(CLAVE, rules=LOCKOUT), later="- %s: después\n" % LOCKOUT)
    assert hard(design) == ["%s: %s is in ## Later and in %s" % (MAP, LOCKOUT, CLAVE)]


def test_a_rule_left_for_later_is_in_the_catalog(design):
    put(design, block(CLAVE), later="- R-login-no-existe: después\n")
    assert hard(design) == ["%s: ## Later names R-login-no-existe, which is not in the catalog" % MAP]


def test_an_enabler_is_a_note_and_never_a_failure(design):
    put(design, block(CLAVE, more={"Kind": "enabler — sin cuentas no hay nada que mostrar"}))
    rc, out = check(design)
    assert rc == 0 and out["notes"] == ["%s: %s is an enabler, nothing a person can check on its own: sin cuentas no hay nada que mostrar" % (MAP, CLAVE)]
    assert slices(design)[CLAVE]["enabler"] == "sin cuentas no hay nada que mostrar"


def test_designed_rules_no_slice_builds_are_listed(design):
    put(design, block(CLAVE, rules=LOCKOUT), later="- %s: espera al correo\n" % RESET)
    assert status(design)["unassigned_designed"] == [OAUTH, ONE_ACCOUNT]
    assert check(design)[1]["notes"] == ["%s is [designed] and in no slice and not in ## Later" % rule for rule in (OAUTH, ONE_ACCOUNT)]


def test_a_map_that_names_no_rule_does_not_note_the_designed_ones(design):
    put(design, block(CLAVE))
    assert check(design)[1]["notes"] == []
    assert len(status(design)["unassigned_designed"]) == 4


def test_only_the_capabilities_a_map_touches_are_noted(design):
    record(design, CAT + "/_changes/20261113-design-pagos", delta_record(
        "### NEW-CAPABILITY pagos\n- Covers: Cobrar un pedido\n\n" + designed("R-pagos-moneda", "Se cobra en colones.", capability="pagos")))
    login(design)
    assert check(design)[1]["notes"] == []
    assert status(design)["unassigned_designed"] == ["R-pagos-moneda"]


# ---------------------------------------------------------------- what a spec says about its slice


def test_a_spec_from_before_slices_is_left_alone(design):
    design.write("specs/001-viejo/spec.md", spec())
    assert check(design) == (0, {"status": "ok", "hard": [], "notes": [], "maps": []})


def test_a_spec_that_is_a_slice_on_its_own_says_so(design):
    design.write("specs/001-borrar/spec.md", spec("standalone — Borro una campaña y ya no aparece en la lista"))
    assert check(design)[0] == 0
    assert status(design)["standalone"] == [{"spec": "specs/001-borrar", "outcome": "Borro una campaña y ya no aparece en la lista", "state": "specified"}]


@pytest.mark.parametrize("value, needle", [
    ("[slice id from specs/_slices/, or: standalone — <what a person can do and check>]", "## Slice still holds the placeholder of the template"),
    ("login con clave", "Slice takes a slice id or `standalone"),
    ("standalone", "Slice takes a slice id or `standalone"),
])
def test_a_slice_section_names_a_slice_or_says_standalone(design, value, needle):
    design.write("specs/001-x/spec.md", spec(value))
    assert hard(design, "specs/001-x: ", needle)


def test_a_slice_section_without_the_line_is_an_error(design):
    design.write("specs/001-x/spec.md", spec().replace("### User Story 1", "## Slice *(mandatory)*\n\n<!--\n- Slice: standalone — ejemplo\n-->\n\n### User Story 1"))
    assert hard(design, "specs/001-x: ## Slice names no slice")


def test_a_spec_names_a_slice_a_map_defines(design):
    login(design)
    design.write("specs/001-x/spec.md", spec("D-login-otra"))
    assert hard(design) == ["specs/001-x: names slice D-login-otra, which no map defines"]


def test_a_spec_does_not_name_a_dropped_slice(design):
    put(design, block(CLAVE, more={"Dropped": "no se hará"}))
    design.write("specs/001-x/spec.md", spec(CLAVE))
    assert hard(design) == ["specs/001-x: names slice %s, which was dropped" % CLAVE]


def test_one_spec_builds_one_slice(design):
    login(design)
    design.write("specs/001-x/spec.md", spec(REGISTRO))
    design.write("specs/002-y/spec.md", spec(REGISTRO))
    assert hard(design) == ["%s is named by several specs: specs/001-x, specs/002-y; one spec builds one slice" % REGISTRO]


def test_a_spec_builds_only_the_designed_rules_of_its_slice(design):
    login(design)
    acceso(design, SOCIAL)
    assert hard(design) == ["%s: builds %s, which belongs to %s; name that slice in ## Slice or move the rule in the map" % (ACCESO, LOCKOUT, CLAVE)]
    acceso(design, CLAVE)
    assert check(design)[0] == 0


def test_a_spec_that_names_no_slice_does_not_build_a_rule_a_slice_owns(design):
    login(design)
    acceso(design, None)
    assert hard(design, ACCESO, "builds %s, which belongs to %s" % (LOCKOUT, CLAVE))
    acceso(design, "standalone — Bloqueo tras cinco fallos")
    assert hard(design, ACCESO, "builds %s, which belongs to %s" % (LOCKOUT, CLAVE))


def test_specs_are_looked_for_under_the_feature_roots(design):
    login(design)
    design.write("specs/001-x/spec.md", spec(REGISTRO))
    assert slices(design)[REGISTRO]["spec"] == "specs/001-x"
    design.config(feature_roots="features")
    assert slices(design)[REGISTRO]["spec"] is None
    design.write("features/pagos/001-y/spec.md", spec(REGISTRO))
    assert slices(design)[REGISTRO]["spec"] == "features/pagos/001-y"


# ---------------------------------------------------------------- the state, read from the project


def test_the_state_of_a_slice_follows_its_spec_its_tasks_and_the_fold(design):
    login(design)
    found = slices(design)
    assert {item["state"] for item in found.values()} == {"pending"}
    assert found[CLAVE]["ready"] and not found[SOCIAL]["ready"] and found[SOCIAL]["waiting_for"] == [CLAVE]
    assert status(design)["maps"][0]["next"] == CLAVE

    acceso(design)
    found = slices(design)[CLAVE]
    assert (found["state"], found["spec"], found["ready"]) == ("specified", ACCESO, False)
    assert status(design)["maps"][0]["next"] is None

    design.write(ACCESO + "/tasks.md", "- [x] T001 Contar los fallos\n- [ ] T002 Bloquear la cuenta\n")
    assert slices(design)[CLAVE]["state"] == "building"

    design.write(ACCESO + "/tasks.md", fixture("specs/001-acceso/tasks.md"))
    assert slices(design)[CLAVE]["state"] == "building", "closed tasks are not delivered while the rule is not folded"

    deliver(design)
    found = slices(design)
    assert found[CLAVE]["state"] == "delivered"
    assert found[SOCIAL]["ready"] and found[SOCIAL]["waiting_for"] == []
    assert status(design)["maps"][0]["next"] == SOCIAL
    assert check(design)[0] == 0


def test_a_slice_without_rule_changes_is_delivered_when_its_tasks_close(design):
    login(design)
    design.write("specs/001-registro/spec.md", spec(REGISTRO))
    assert slices(design)[REGISTRO]["state"] == "specified"
    design.write("specs/001-registro/tasks.md", "- [ ] T001 Formulario\n")
    assert slices(design)[REGISTRO]["state"] == "building"
    design.write("specs/001-registro/tasks.md", "- [x] T001 Formulario\n")
    assert slices(design)[REGISTRO]["state"] == "delivered"


def test_a_folded_spec_without_tasks_is_delivered(design):
    """A change folded with --no-tasks has no tasks.md and is in the catalog all the same."""
    login(design)
    deliver(design)
    (design.path / ACCESO / "tasks.md").unlink()
    assert slices(design)[CLAVE]["state"] == "delivered"


def test_a_built_rule_waits_for_no_slice(design):
    put(design, block(CLAVE))
    deliver(design)
    assert "- **%s**: " % LOCKOUT in design.read(CAT + "/login/spec.md"), "built, so no longer [designed]"
    assert status(design)["unassigned_designed"] == [OAUTH, ONE_ACCOUNT, RESET]


def test_a_dropped_slice_is_never_next(design):
    put(design, block(CLAVE, more={"Dropped": "se hará con otro proveedor"}), block(SOCIAL))
    found = slices(design)
    assert (found[CLAVE]["state"], found[CLAVE]["ready"], found[CLAVE]["dropped"]) == ("dropped", False, "se hará con otro proveedor")
    assert status(design)["maps"][0]["next"] == SOCIAL


def test_a_designed_rule_its_spec_does_not_build_is_an_issue(design):
    put(design, block(CLAVE, rules="%s, %s" % (LOCKOUT, RESET)), later="- %s: después\n- %s: después\n" % (OAUTH, ONE_ACCOUNT))
    assert slices(design)[CLAVE]["issues"] == [], "no spec yet, so nothing to compare"
    acceso(design)
    issue = "%s is still [designed] and %s does not build it" % (RESET, ACCESO)
    assert slices(design)[CLAVE]["issues"] == [issue]
    assert check(design) == (0, {"status": "ok", "hard": [], "maps": [MAP], "notes": ["%s: %s: %s; move the rule to another slice or to ## Later" % (MAP, CLAVE, issue)]})


def test_status_reads_one_map_by_name_or_by_path(design):
    login(design)
    put(design, block("D-perfil-foto"), name="perfil")
    assert [found["name"] for found in status(design)["maps"]] == ["login", "perfil"]
    assert [found["name"] for found in status(design, "--map", "perfil")["maps"]] == ["perfil"]
    assert [found["name"] for found in status(design, "--map", MAP)["maps"]] == ["login"]
    rc, out = design.cap("slices", "status", "--map", "pagos")
    assert rc == 2 and out["errors"] == ["slice map not found: pagos"]


def test_status_says_how_many_problems_check_has(design):
    put(design, block(CLAVE, depends="D-login-otra", more={"Kind": "enabler — base"}))
    assert status(design)["check"] == {"hard": 1, "notes": 1}


# ---------------------------------------------------------------- show: one slice, to aim a run at it


def test_show_gives_what_a_run_needs_to_build_one_slice(design):
    login(design)
    rc, out = design.cap("slices", "show", CLAVE)
    assert rc == 0 and out["status"] == "ok", out
    assert out["map"] == MAP and out["request"] == "Login completo."
    assert out["slice"]["id"] == CLAVE and out["slice"]["state"] == "pending"
    assert [(item["id"], item["state"]) for item in out["siblings"]] == [(SOCIAL, "pending"), (RECUPERAR, "pending"), (REGISTRO, "pending")]
    assert out["write"] == "- Slice: %s\n- Out: Entrar con Google, Facebook o GitHub (%s); Recuperar la clave (%s); Crear una cuenta (%s)\n" % (CLAVE, SOCIAL, RECUPERAR, REGISTRO)
    assert [(rule["id"], rule["capability"], rule["designed"]) for rule in out["rules"]] == [(LOCKOUT, "login", True)]
    assert out["rules"][0]["text"] == "Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos."


def test_show_hands_the_blocks_of_exactly_the_rules_of_the_slice(design):
    login(design)
    out = design.cap("slices", "show", SOCIAL)[1]
    assert out["implement"]["ids"] == [OAUTH, ONE_ACCOUNT]
    assert out["implement"]["text"] == design.cap("delta-block", "--implement", OAUTH, ONE_ACCOUNT)[1]["text"]
    assert design.cap("slices", "show", REGISTRO)[1]["implement"] == {"ids": [], "text": ""}


def test_show_asks_for_a_decision_when_the_slice_waits_for_another(design):
    login(design)
    rc, out = design.cap("slices", "show", SOCIAL)
    assert rc == 3 and out["status"] == "blocked", out
    assert out["slice"]["waiting_for"] == [CLAVE] and out["depends_on"] == [{"id": CLAVE, "state": "pending"}]


def test_show_asks_for_a_decision_when_the_slice_has_a_spec(design):
    login(design)
    deliver(design)
    rc, out = design.cap("slices", "show", CLAVE)
    assert rc == 3 and out["status"] == "has-spec" and out["slice"]["spec"] == ACCESO, out
    assert out["implement"] == {"ids": [], "text": ""}, "a built rule is not offered again"
    rc, out = design.cap("slices", "show", SOCIAL)
    assert rc == 0 and out["status"] == "ok" and out["depends_on"] == [{"id": CLAVE, "state": "delivered"}], out


def test_show_leaves_dropped_slices_out_of_the_siblings(design):
    put(design, block(CLAVE), block(SOCIAL, "Entrar con Google", more={"Dropped": "no se hará"}), block(REGISTRO, "Crear una cuenta"))
    out = design.cap("slices", "show", CLAVE)[1]
    assert [item["id"] for item in out["siblings"]] == [REGISTRO]
    assert out["write"] == "- Slice: %s\n- Out: Crear una cuenta (%s)\n" % (CLAVE, REGISTRO)
    put(design, block(CLAVE))
    assert design.cap("slices", "show", CLAVE)[1]["write"] == "- Slice: %s\n- Out: none\n" % CLAVE


def test_show_writes_the_block_that_aims_the_run(design):
    login(design)
    out = design.cap("slices", "show", CLAVE)[1]
    assert out["aim"] == (
        "SLICE FOR THIS RUN\n"
        "%s — Entrar con usuario y clave\n"
        "Build exactly this: Una persona entra a su cuenta.\n"
        "A person checks it by: Entro y veo mi cuenta.\n"
        "Other slices own this, so do not specify it, ask about it or build it: Entrar con Google, Facebook o GitHub (%s); Recuperar la clave (%s); Crear una cuenta (%s)\n"
        "Depends on: none\n"
        "Rules to build:\n"
        "- %s: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos.\n"
        "\n"
        "Write under ## Slice in the spec:\n"
        "%s" % (CLAVE, SOCIAL, RECUPERAR, REGISTRO, LOCKOUT, out["write"]))
    both = design.cap("slices", "show", SOCIAL)[1]["aim"]
    assert "\nRules to build:\n- %s: " % OAUTH in both and "\n- %s: " % ONE_ACCOUNT in both, "one line per rule"


def test_the_block_names_what_the_slice_takes_in_and_what_it_waits_for(design):
    put(design, block(CLAVE, more={"In": "formulario; sesión iniciada"}), block(SOCIAL, "Entrar con Google", depends=CLAVE),
        block(REGISTRO, "Crear una cuenta", depends="%s, %s" % (CLAVE, SOCIAL)))
    assert "\nIn: formulario; sesión iniciada\nA person checks it by: " in design.cap("slices", "show", CLAVE)[1]["aim"]
    rc, out = design.cap("slices", "show", SOCIAL)
    assert rc == 3, "a slice that waits still gets its block: the user may go on"
    assert "\nIn:" not in out["aim"], "a slice without In has no such line"
    assert "\nDepends on: %s (pending)\nRules to build: none\n\nWrite under ## Slice in the spec:\n%s" % (CLAVE, out["write"]) in out["aim"]
    assert out["aim"].endswith("- Out: Entrar (%s); Crear una cuenta (%s)\n" % (CLAVE, REGISTRO))
    assert "\nDepends on: %s (pending), %s (pending)\n" % (CLAVE, SOCIAL) in design.cap("slices", "show", REGISTRO)[1]["aim"]


@pytest.mark.parametrize("slice_id, needle", [("D-login-otra", "slice not found: D-login-otra"), (SOCIAL, "slice %s was dropped: no se hará" % SOCIAL)])
def test_show_rejects_a_slice_that_cannot_be_built(design, slice_id, needle):
    put(design, block(CLAVE), block(SOCIAL, more={"Dropped": "no se hará"}))
    rc, out = design.cap("slices", "show", slice_id)
    assert rc == 2 and out == {"status": "invalid", "errors": [needle]}


@pytest.mark.parametrize("args, needle", [
    (("show",), "show takes one slice id"),
    (("show", CLAVE, SOCIAL), "show takes one slice id"),
    (("status", CLAVE), "status takes no ids"),
    (("check", "--map", "login"), "--map goes with status and next"),
    (("next", CLAVE), "next takes no ids"),
    (("measure", CLAVE), "measure takes no ids"),
    (("status", "--change", BIG), "--change goes with measure and accept"),
    (("measure", "--reason", "porque sí"), "--reason goes with accept"),
    (("status", "--slice", CLAVE), "--slice goes with measure and accept"),
    (("next", "--slice", CLAVE), "--slice goes with measure and accept"),
    (("measure", "--slice", CLAVE, "--change", BIG), "name the spec with --change or its slice with --slice, not both"),
    (("accept", "--slice", CLAVE, "--change", BIG, "--reason", "porque sí"), "name the spec with --change or its slice with --slice, not both"),
    (("split",), "invalid choice"),
])
def test_a_wrong_invocation_is_refused(design, args, needle):
    login(design)
    rc, out = design.cap("slices", *args)
    assert rc == 2 and needle in out["stderr"], out


def test_a_catalog_of_a_newer_format_stops_the_slices_too(design):
    login(design)
    design.replace(INDEX, "<!-- capability-catalog: 2 -->", "<!-- capability-catalog: 3 -->")
    rc, out = design.cap("slices", "status")
    assert rc == 2 and "uses catalog format 3" in out["errors"][0], out


# ---------------------------------------------------------------- check: the catalog's own report carries the slices


def test_check_reports_what_the_slices_disagree_on(design):
    login(design)
    assert design.cap("check", "--mode", "dev")[0] == 0
    acceso(design, SOCIAL)
    rc, out = design.cap("check", "--mode", "dev")
    assert rc == 1, out
    assert "%s: builds %s, which belongs to %s; name that slice in ## Slice or move the rule in the map" % (ACCESO, LOCKOUT, CLAVE) in out["hard"]


def test_check_carries_the_notes_of_the_slices(design):
    put(design, block(CLAVE, rules=LOCKOUT, more={"Kind": "enabler — base de cuentas"}), later="- %s: a\n- %s: b\n- %s: c\n" % (OAUTH, ONE_ACCOUNT, RESET))
    rc, out = design.cap("check", "--mode", "dev")
    assert rc == 0, out
    assert "%s: %s is an enabler, nothing a person can check on its own: base de cuentas" % (MAP, CLAVE) in out["notes"]


def test_a_design_record_is_not_a_spec_that_names_a_slice(design):
    login(design)
    assert MARK in design.read(DESIGN + "/capability-delta.md")
    design.write(DESIGN + "/spec.md", spec("D-login-otra"))
    assert hard(design, "D-login-otra") == []


# ---------------------------------------------------------------- next: the slice to build now, for a loop that walks a map


def upcoming(repo, *args, env=None):
    return repo.cap("slices", "next", *args, env=env)


def one_slice(repo, value=CLAVE, done=False):
    """A map with one slice and the spec that builds it. The spec changes no rule, so closed tasks deliver it."""
    put(repo, block(CLAVE, "Entrar con usuario y clave"))
    repo.write(BIG + "/spec.md", sized(value=value))
    if done:
        repo.write(BIG + "/tasks.md", tasks(2, done=2))


def test_next_names_the_first_slice_that_waits_for_nothing(design):
    login(design)
    rc, out = upcoming(design)
    assert rc == 0, out
    assert (out["status"], out["reason"], out["next"], out["name"], out["map"]) == ("ok", "ready", CLAVE, "login", MAP)
    assert (out["slice"]["id"], out["slice"]["title"], out["slice"]["verify"]) == (CLAVE, "Entrar con usuario y clave", "Entro y veo mi cuenta.")
    assert (out["total"], out["delivered"]) == (4, 0)
    assert out["summary"] == "login: 0 of 4 slices delivered. Next: %s Entrar con usuario y clave." % CLAVE


def test_next_moves_on_as_slices_are_delivered(design):
    login(design)
    acceso(design)
    rc, out = upcoming(design)
    assert rc == 0 and (out["status"], out["reason"], out["next"], out["slice"]) == ("none", "waiting", None, None), out
    assert out["in_progress"] == [{"id": CLAVE, "state": "specified", "spec": ACCESO}]
    assert out["pending"] == [{"id": SOCIAL, "waiting_for": [CLAVE]}, {"id": RECUPERAR, "waiting_for": [CLAVE]}, {"id": REGISTRO, "waiting_for": [CLAVE]}]
    assert out["summary"] == "login: 0 of 4 slices delivered. No slice is ready: %s waits for %s (specified); %s waits for %s (specified); %s waits for %s (specified)." % (
        SOCIAL, CLAVE, RECUPERAR, CLAVE, REGISTRO, CLAVE)
    deliver(design)
    out = upcoming(design)[1]
    assert (out["status"], out["next"], out["delivered"]) == ("ok", SOCIAL, 1)
    assert out["summary"].startswith("login: 1 of 4 slices delivered. Next: %s " % SOCIAL)


def test_next_says_when_a_started_slice_is_all_that_is_left(design):
    one_slice(design)
    out = upcoming(design)[1]
    assert (out["status"], out["reason"], out["pending"]) == ("none", "in-progress", [])
    assert out["in_progress"] == [{"id": CLAVE, "state": "specified", "spec": BIG}]
    assert out["summary"] == "login: 0 of 1 slices delivered. No slice is left to start: %s is specified." % CLAVE


def test_next_says_when_the_map_is_done_and_counts_no_dropped_slice(design):
    one_slice(design, done=True)
    design.write(MAP, design.read(MAP) + "\n" + block(SOCIAL, "Entrar con Google", more={"Dropped": "no se hará"}))
    rc, out = upcoming(design)
    assert rc == 0 and (out["status"], out["reason"], out["next"]) == ("none", "done", None), out
    assert (out["total"], out["delivered"], out["pending"], out["in_progress"]) == (1, 1, [], [])
    assert out["summary"] == "login: 1 of 1 slices delivered. Every slice is delivered."


def test_next_refuses_to_walk_maps_that_disagree(design):
    put(design, block(CLAVE, depends="D-otro-lado"))
    rc, out = design.cap("slices", "status")
    assert out["check"]["hard"] == 1
    rc, out = upcoming(design)
    assert rc == 1 and out["status"] == "invalid" and "D-otro-lado" in out["hard"][0], "the maps are fixed before any slice is built"


def test_next_takes_the_map_from_the_option_or_from_the_environment(design):
    login(design)
    put(design, block("D-otro-uno", "Otra cosa"), name="otro")
    rc, out = upcoming(design)
    assert rc == 3 and out["status"] == "ambiguous" and out["maps"] == ["login", "otro"], out
    assert out["errors"] == ["several maps have a next slice: login, otro; name one with --map"]
    assert upcoming(design, "--map", "otro")[1]["next"] == "D-otro-uno"
    assert upcoming(design, "--map", "specs/_slices/otro.md")[1]["next"] == "D-otro-uno"
    assert upcoming(design, env={"SPECKIT_SLICE_MAP": "otro"})[1]["next"] == "D-otro-uno"
    assert upcoming(design, "--map", "login", env={"SPECKIT_SLICE_MAP": "otro"})[1]["next"] == CLAVE, "the option wins"
    assert upcoming(design, env={"SPECKIT_SLICE_MAP": ""})[0] == 3, "an empty variable names no map"
    for args, env in ((("--map", "nada"), None), ((), {"SPECKIT_SLICE_MAP": "nada"})):
        rc, out = upcoming(design, *args, env=env)
        assert rc == 2 and out == {"status": "invalid", "errors": ["slice map not found: nada"]}


def test_next_over_every_map_when_none_is_named_and_none_is_ready(design):
    one_slice(design)
    put(design, block("D-otro-uno", "Otra cosa", depends=CLAVE), name="otro")
    rc, out = upcoming(design)
    assert rc == 0 and (out["status"], out["reason"], out["name"], out["map"]) == ("none", "waiting", None, None), out
    assert out["summary"] == "all maps: 0 of 2 slices delivered. No slice is ready: D-otro-uno waits for %s (specified)." % CLAVE


def test_next_needs_a_slice_map(design):
    rc, out = upcoming(design)
    assert rc == 2 and out == {"status": "invalid", "errors": ["no slice map under specs/_slices: speckit.capabilities.slice writes one"]}


# ---------------------------------------------------------------- the progress page reads the maps on its own


def page_slices(repo):
    """What the list of specs of the progress page shows. Its engine reads the maps itself, to start no process on a redraw."""
    location = importlib.util.spec_from_file_location("progress_engine_for_slices", str(ROOT / "scripts" / "progress" / "engine.py"))
    engine = importlib.util.module_from_spec(location)
    location.loader.exec_module(engine)
    return [
        (found["name"], found["next"], [(view["id"], view["state"], view["spec"] and "specs/" + view["spec"], view["waiting_for"]) for view in found["slices"]])
        for found in engine.project_slices(repo.path)
    ]


def script_slices(repo):
    return [
        (found["name"], found["next"], [(item["id"], item["state"], item["spec"], item["waiting_for"]) for item in found["slices"]])
        for found in status(repo)["maps"]
    ]


def test_the_progress_page_and_the_script_agree_on_every_state(design):
    login(design)
    assert page_slices(design) == script_slices(design) and script_slices(design)[0][1] == CLAVE
    acceso(design)
    assert page_slices(design) == script_slices(design) and slices(design)[CLAVE]["state"] == "specified"
    design.write(ACCESO + "/tasks.md", "- [x] T001 Hecho\n- [ ] T002 Falta\n")
    assert page_slices(design) == script_slices(design) and slices(design)[CLAVE]["state"] == "building"
    design.write(ACCESO + "/tasks.md", "- [x] T001 Hecho\n- [x] T002 Hecho\n")
    assert page_slices(design) == script_slices(design) and slices(design)[CLAVE]["state"] == "building", "tasks closed, delta not folded"
    deliver(design)
    assert page_slices(design) == script_slices(design) and slices(design)[CLAVE]["state"] == "delivered"
    assert script_slices(design)[0][1] == SOCIAL
    design.write(BIG + "/spec.md", sized(value=REGISTRO))
    design.write(BIG + "/tasks.md", tasks(2, done=2))
    assert page_slices(design) == script_slices(design) and slices(design)[REGISTRO]["state"] == "delivered", "no rules, so closed tasks deliver it"
    put(design, block(CLAVE, rules=LOCKOUT), block(SOCIAL, "Entrar con Google", depends=CLAVE, more={"Dropped": "no se hará"}), block(RECUPERAR, depends=SOCIAL), name="otro")
    assert page_slices(design) == script_slices(design)


# ---------------------------------------------------------------- size: a spec against the slice budget


def sized(stories=1, requirements=1, rules=0, value="standalone — Entrar a la cuenta"):
    """A spec with this many stories, requirements and added rules. ``value`` is what its ## Slice says; None is a spec from before slices."""
    text = "# Feature\n\n%s" % ("" if value is None else declared(value))
    for number in range(1, stories + 1):
        text += "### User Story %d - Parte %d\n\n**Acceptance Scenarios**:\n\n1. **Given** a, **Then** b.\n\n" % (number, number)
    text += "## Requirements\n\n%s\n" % "".join("- **FR-%03d**: System MUST x%d.\n" % (number, number) for number in range(1, requirements + 1))
    text += "## Success Criteria\n\n- **SC-001**: Se ve en menos de un minuto.\n\n"
    return text + delta_block("\n".join(added("R-login-extra-%d" % number, "Regla extra %d." % number) for number in range(1, rules + 1)) or NO_RULES)


def tasks(total, done=0):
    return "# Tasks\n\n- una nota que no es una tarea\n%s" % "".join("- [%s] T%03d Hacer %d\n" % ("x" if number <= done else " ", number, number) for number in range(1, total + 1))


def size(repo, change=BIG):
    rc, out = repo.cap("slices", "measure", "--change", change)
    assert rc == 0, out
    return out


def accept(repo, reason, change=BIG):
    return repo.cap("slices", "accept", "--change", change, "--reason", reason)


def test_measure_counts_what_a_spec_holds(design):
    design.write(BIG + "/spec.md", sized(requirements=10, rules=4))
    out = size(design)
    assert out["status"] == "within" and out["over"] == [] and out["accepted"] is None
    assert out["counts"] == {"stories": 1, "requirements": 10, "scenarios": 1, "criteria": 1, "rules": 4, "tasks": None}
    assert out["budget"] == BUDGET
    assert out["summary"] == "Slice size: 1 story (max 1), 10 requirements (max 10), 4 rules (max 4), tasks not written (max 25). Within the slice budget."
    assert (out["spec"], out["slice"], out["standalone"], out["map"]) == (BIG, None, "Entrar a la cuenta", None)


@pytest.mark.parametrize("held, what, count", [({"stories": 2}, "stories", 2), ({"requirements": 11}, "requirements", 11), ({"rules": 5}, "rules", 5)])
def test_one_more_than_the_budget_is_over(design, held, what, count):
    design.write(BIG + "/spec.md", sized(**held))
    out = size(design)
    assert out["status"] == "over" and out["over"] == [{"what": what, "count": count, "max": BUDGET[what]}]
    assert out["summary"].endswith(" Over the slice budget in %s." % what)


def test_the_line_names_everything_that_is_over(design):
    design.write(BIG + "/spec.md", sized(stories=2, requirements=11, rules=5))
    design.write(BIG + "/tasks.md", tasks(26))
    assert size(design)["summary"].endswith(" Over the slice budget in stories, requirements, rules and tasks.")
    accept(design, "Todo va junto.")
    design.write(BIG + "/spec.md", sized(stories=3, requirements=12, rules=6))
    assert size(design)["summary"].endswith(" It grew past what was accepted in stories, requirements and rules.")


def test_tasks_count_once_they_are_written(design):
    design.write(BIG + "/spec.md", sized())
    design.write(BIG + "/tasks.md", tasks(25, done=3))
    out = size(design)
    assert out["counts"]["tasks"] == 25 and out["status"] == "within", "done and open tasks count, a plain bullet does not"
    design.write(BIG + "/tasks.md", tasks(26, done=26))
    out = size(design)
    assert out["over"] == [{"what": "tasks", "count": 26, "max": 25}] and "26 tasks (max 25)" in out["summary"]


def test_what_is_commented_out_is_not_counted(design):
    example = "<!--\n### User Story 9 - Ejemplo\n\n- **FR-099**: System MUST ejemplo.\n-->\n\n## Requirements"
    design.write(BIG + "/spec.md", sized().replace("## Requirements", example))
    design.write(BIG + "/tasks.md", "<!--\n- [ ] T000 Ejemplo\n-->\n- [ ] T001 Hacer\n")
    counts = size(design)["counts"]
    assert (counts["stories"], counts["requirements"], counts["tasks"]) == (1, 1, 1)


def test_measure_says_which_map_holds_the_spec(design):
    login(design)
    design.write(BIG + "/spec.md", sized(value=REGISTRO))
    out = size(design)
    assert (out["slice"], out["standalone"], out["map"]) == (REGISTRO, None, MAP)


def test_measure_needs_a_spec(design):
    rc, out = design.cap("slices", "measure", "--change", "specs/404-nada")
    assert rc == 2 and out == {"status": "invalid", "errors": ["no spec.md in specs/404-nada"]}


def test_measure_and_accept_find_the_spec_by_its_slice(design):
    login(design)
    acceso(design)
    design.write(BIG + "/spec.md", sized(stories=2, value=REGISTRO))
    by_change = size(design)
    assert by_change["status"] == "over" and by_change["spec"] == BIG
    assert design.cap("slices", "measure", "--slice", REGISTRO) == (0, by_change)
    assert design.cap("slices", "measure", env={"SPECKIT_SLICE": REGISTRO}) == (0, by_change), "a walk names the slice in the environment"
    rc, out = design.cap("slices", "accept", "--reason", "Va junto.", env={"SPECKIT_SLICE": REGISTRO})
    assert rc == 0 and (out["status"], out["written"]) == ("accepted", BIG + "/slice-budget.json")
    assert json.loads((design.path / BIG / "slice-budget.json").read_text(encoding="utf-8"))["reason"] == "Va junto."
    assert not (design.path / ACCESO / "slice-budget.json").exists(), "only the spec of that slice is touched"
    rc, out = design.cap("slices", "accept", "--slice", REGISTRO, "--reason", "Sigue junto.")
    assert rc == 0 and out["accepted"]["reason"] == "Sigue junto."


def test_what_is_named_on_the_command_line_wins_over_the_slice_in_the_environment(design):
    login(design)
    acceso(design)
    design.write(BIG + "/spec.md", sized(value=REGISTRO))
    env = {"SPECKIT_SLICE": CLAVE}
    assert design.cap("slices", "measure", env=env)[1]["spec"] == ACCESO
    assert design.cap("slices", "measure", "--change", BIG, env=env)[1]["spec"] == BIG
    assert design.cap("slices", "measure", "--slice", REGISTRO, env=env)[1]["spec"] == BIG
    assert design.cap("slices", "measure", "--change", BIG, env={"SPECKIT_SLICE": "D-login-nada"})[0] == 0


def test_a_slice_is_measured_only_when_one_spec_builds_it(design):
    login(design)
    for command in (("measure",), ("accept", "--reason", "Va junto.")):
        rc, out = design.cap("slices", *command, "--slice", "D-login-nada")
        assert rc == 2 and out == {"status": "invalid", "errors": ["no slice map defines D-login-nada"]}
        rc, out = design.cap("slices", *command, env={"SPECKIT_SLICE": REGISTRO})
        assert rc == 2 and out == {"status": "invalid", "errors": ["no spec builds %s yet" % REGISTRO]}
    design.write(BIG + "/spec.md", sized(stories=2, value=REGISTRO))
    design.write("specs/003-otra/spec.md", sized(stories=2, value=REGISTRO))
    for command in (("measure",), ("accept", "--reason", "Va junto.")):
        rc, out = design.cap("slices", *command, "--slice", REGISTRO)
        assert rc == 2 and out["errors"] == ["%s and specs/003-otra build %s: one slice takes one spec" % (BIG, REGISTRO)]
    assert not list(design.path.glob("specs/*/slice-budget.json")), "nothing is accepted for a slice that two specs claim"


def test_the_config_changes_the_budget(design):
    design.write(BIG + "/spec.md", sized(stories=2, requirements=12))
    assert size(design)["status"] == "over"
    design.config(slice_max_stories=2, slice_max_requirements=12)
    out = size(design)
    assert out["status"] == "within" and out["budget"] == {"stories": 2, "requirements": 12, "rules": 4, "tasks": 25}


@pytest.mark.parametrize("value", ["0", "-1", "many", "2.5"])
def test_a_budget_that_is_not_a_number_is_refused(design, value):
    design.write(BIG + "/spec.md", sized())
    design.config(slice_max_rules=value)
    problem = "slice_max_rules in %s takes a whole number above 0: %s" % (CONFIG, value)
    rc, out = design.cap("slices", "measure", "--change", BIG)
    assert rc == 2 and out["errors"] == [problem]
    rc, out = check(design)
    assert rc == 1 and out["hard"] == [problem], "check says it once, whatever the number of specs"


def test_the_config_template_holds_the_budget_the_script_uses(design):
    template = (EXT / "config-template.yml").read_text(encoding="utf-8")
    assert {what: int(value) for what, value in re.findall(r"^slice_max_([a-z]+): (\d+)$", template, re.M)} == BUDGET
    design.write(BIG + "/spec.md", sized())
    design.write(CONFIG, template)
    assert size(design)["budget"] == BUDGET


def test_accept_records_why_a_spec_stays_over_the_budget(design):
    design.write(BIG + "/spec.md", sized(stories=3, requirements=12))
    before = design.read(BIG + "/spec.md")
    rc, out = accept(design, "  Las tres historias\n comparten una pantalla. ")
    assert rc == 0 and out["status"] == "accepted" and out["written"] == BIG + "/slice-budget.json", out
    numbers = {"stories": 3, "requirements": 12, "rules": 0, "tasks": None}
    assert json.loads(design.read(BIG + "/slice-budget.json")) == {"schema": 1, "reason": "Las tres historias comparten una pantalla.", "accepted": numbers}
    assert design.read(BIG + "/spec.md") == before, "the spec is not touched, so its seal holds"
    out = size(design)
    assert out["status"] == "accepted" and out["accepted"] == {"reason": "Las tres historias comparten una pantalla.", "counts": numbers}
    assert out["over"] == [{"what": "stories", "count": 3, "max": 1, "accepted": 3}, {"what": "requirements", "count": 12, "max": 10, "accepted": 12}]
    assert out["summary"].endswith(" Over the slice budget in stories and requirements; accepted: Las tres historias comparten una pantalla.")


def test_a_spec_that_grows_past_what_was_accepted_is_over_again(design):
    design.write(BIG + "/spec.md", sized(stories=2))
    assert accept(design, "Dos pasos de un mismo flujo.")[1]["status"] == "accepted"
    design.write(BIG + "/spec.md", sized(stories=2, requirements=11))
    out = size(design)
    assert out["status"] == "over"
    assert out["over"] == [{"what": "stories", "count": 2, "max": 1, "accepted": 2}, {"what": "requirements", "count": 11, "max": 10, "accepted": 1}]
    assert out["summary"].endswith(" Over the slice budget in stories and requirements. It grew past what was accepted in requirements.")
    design.write(BIG + "/spec.md", sized(stories=2))
    assert size(design)["status"] == "accepted", "back to what was accepted"
    design.write(BIG + "/tasks.md", tasks(26))
    out = size(design)
    assert out["status"] == "over" and {"what": "tasks", "count": 26, "max": 25} in out["over"], "the tasks did not exist when the size was accepted"
    assert accept(design, "Dos pasos de un mismo flujo, con sus tareas.")[1]["status"] == "accepted"
    assert json.loads(design.read(BIG + "/slice-budget.json"))["accepted"]["tasks"] == 26


def test_accept_needs_a_reason_and_a_spec_over_the_budget(design):
    design.write(BIG + "/spec.md", sized(stories=2))
    for args in ((), ("--reason", "  ")):
        rc, out = design.cap("slices", "accept", "--change", BIG, *args)
        assert rc == 2 and out["errors"] == ["accept takes --reason: why this spec stays over the slice budget"]
    assert not (design.path / BIG / "slice-budget.json").exists()
    design.write(BIG + "/spec.md", sized())
    rc, out = accept(design, "por si acaso")
    assert rc == 0 and out["status"] == "within" and out["written"] is None
    assert not (design.path / BIG / "slice-budget.json").exists(), "nothing to accept when the spec is within the budget"


@pytest.mark.parametrize("text", [
    "{",
    "[]",
    '{"reason": "x"}',
    '{"reason": " ", "accepted": {"stories": 2, "requirements": 1, "rules": 0, "tasks": null}}',
    '{"reason": "x", "accepted": {"stories": "2", "requirements": 1, "rules": 0, "tasks": null}}',
    '{"reason": "x", "accepted": {"stories": 2}}',
])
def test_a_budget_file_written_by_hand_is_refused(design, text):
    design.write(BIG + "/spec.md", sized(stories=2))
    design.write(BIG + "/slice-budget.json", text)
    problem = "%s/slice-budget.json cannot be read; write it again with `slices accept`" % BIG
    rc, out = design.cap("slices", "measure", "--change", BIG)
    assert rc == 2 and out["errors"] == [problem]
    assert hard(design, "slice-budget.json") == [problem]


def test_check_notes_a_spec_over_the_budget_until_its_size_is_accepted(design):
    login(design)
    design.write(BIG + "/spec.md", sized(stories=2, value=REGISTRO))
    line = "%s: Slice size: 2 stories (max 1), 1 requirement (max 10), 0 rules (max 4), tasks not written (max 25). Over the slice budget in stories. Split it, or record why with `slices accept`" % BIG
    assert notes(design, BIG) == [line]
    assert check(design)[0] == 0, "a size is a note, never a failure"
    assert status(design)["check"] == {"hard": 0, "notes": 1}
    assert line in design.cap("check", "--mode", "dev")[1]["notes"], "the catalog's own check carries it"
    accept(design, "Registro y bienvenida se prueban juntos.")
    assert notes(design, BIG) == []


def test_check_measures_only_specs_that_name_a_slice_and_are_not_delivered(design):
    # A spec from before slices that builds a designed rule: the slices know it, and still do not measure it.
    built = design.cap("delta-block", "--implement", LOCKOUT)[1]["text"].replace("FR-###", "FR-001")
    design.write(BIG + "/spec.md", sized(stories=3, value=None).replace(NO_RULES, built))
    rc, out = check(design)
    assert rc == 0 and out["hard"] == [], out
    assert notes(design, BIG) == [], "a spec from before slices is left alone"
    assert size(design)["status"] == "over", "measure still answers when asked"
    design.write(BIG + "/spec.md", sized(stories=3))
    design.write(BIG + "/tasks.md", tasks(2, done=1))
    assert len(notes(design, BIG)) == 1
    design.write(BIG + "/tasks.md", tasks(2, done=2))
    assert slices_state(design, BIG) == "delivered"
    assert notes(design, BIG) == [], "what was delivered is not measured again"


def slices_state(repo, change):
    return {item["spec"]: item["state"] for item in status(repo)["standalone"]}[change]


def test_clarify_context_says_what_other_slices_own(design):
    login(design)
    design.write(BIG + "/spec.md", sized(stories=2, value=REGISTRO).replace("- Out: none", "- Out: Entrar con usuario y clave (%s)" % CLAVE))
    rc, out = design.cap("clarify-context", "--change", BIG)
    assert rc == 0, out
    found = out["slice"]
    assert (found["slice"], found["standalone"], found["map"], found["errors"]) == (REGISTRO, None, MAP, [])
    assert found["out"] == "Entrar con usuario y clave (%s)" % CLAVE
    assert [(item["id"], item["title"], item["state"]) for item in found["siblings"]] == [
        (CLAVE, "Entrar con usuario y clave", "pending"), (SOCIAL, "Entrar con Google, Facebook o GitHub", "pending"), (RECUPERAR, "Recuperar la clave", "pending")]
    assert found["siblings"][0]["intent"] == "Una persona entra a su cuenta."
    assert found["size"] == {"status": "over", "summary": size(design)["summary"]}


def test_clarify_context_leaves_dropped_slices_out(design):
    put(design, block(CLAVE), block(SOCIAL, "Entrar con Google", more={"Dropped": "no se hará"}), block(REGISTRO, "Crear una cuenta"))
    design.write(BIG + "/spec.md", sized(value=CLAVE))
    assert [item["id"] for item in design.cap("clarify-context", "--change", BIG)[1]["slice"]["siblings"]] == [REGISTRO]


def test_clarify_context_of_a_spec_on_its_own_or_from_before_slices(design):
    design.write(BIG + "/spec.md", sized())
    found = design.cap("clarify-context", "--change", BIG)[1]["slice"]
    assert (found["slice"], found["standalone"], found["map"], found["siblings"]) == (None, "Entrar a la cuenta", None, [])
    assert found["size"]["status"] == "within"
    design.write(BIG + "/spec.md", sized(value=None))
    assert design.cap("clarify-context", "--change", BIG)[1]["slice"] is None
    design.write(BIG + "/spec.md", sized(value="[slice id]"))
    assert design.cap("clarify-context", "--change", BIG)[1]["slice"]["errors"] == ["## Slice still holds the placeholder of the template"]
