"""Slices: one spec builds one thing a person can do and check.

The maps under ``specs/_slices/``, the ``## Slice`` section of a spec, the state read from the
specs, and what ``check`` reports when they disagree. The project is F0b's login: four designed
rules, cut into four slices.
"""

from __future__ import annotations

import pytest

from .conftest import CAT, INDEX, MARK, delta_block, removed
from .test_lifecycle import ACCESO_CODE, DESIGN, build_design, copied, delta_record, designed, fixture, record

MAP = "specs/_slices/login.md"
MAP_MARK = "<!-- slice-map:v1 -->"
CLAVE, SOCIAL, RECUPERAR, REGISTRO = "D-login-clave", "D-login-social", "D-login-recuperar", "D-login-registro"
LOCKOUT, OAUTH, ONE_ACCOUNT, RESET = "R-login-lockout", "R-login-oauth-providers", "R-login-one-account-per-email", "R-login-reset-expiry"
ACCESO = "specs/001-acceso"
NO_RULES = "Capabilities: none — no cambia ninguna regla\n"


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
    (("check", "--map", "login"), "--map goes with status"),
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
