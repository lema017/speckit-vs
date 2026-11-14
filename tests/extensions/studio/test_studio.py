"""The studio script: the design of a product kept as files, checked, and turned into the files of its mockup.

The project is Oficio, the example of the approved demo: an app to sign up for neighbourhood workshops.
Its pages are the ones of that demo.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys

import pytest

from .conftest import EXT_DIR, FIXTURE, PRODUCT, PYTHON, SCRIPT

FIXTURE_PAGES = FIXTURE / "specs" / "_product" / "mockup"

LOGIN = "screens/SCR-login.md"
LOCKED = "screens/SCR-login-locked.md"
HOME = "screens/SCR-home.md"
PAGE = "mockup/entrar.html"
# The home page of the example leads to three things nobody designed yet. That is worth knowing and stops nothing.
PENDING = "specs/_product/mockup/inicio.html: 6 links lead to something that is not designed yet: #proponer, #taller, #talleres"
FINE = (0, {"status": "ok", "hard": [], "notes": [PENDING]})
IGNORED = ["mockup/_studio/", "mockup/index.html", "mockup/_shots/"]


# ---------------------------------------------------------------- scaffold: where a design starts


def test_scaffold_starts_a_product_and_brings_the_kit(empty):
    rc, out = empty.run("scaffold", "--name", "  Oficio   del barrio ", "--owner", "Ana Pérez", "--language", "ES")
    assert rc == 0 and out["status"] == "ok", out
    assert empty.read("product.md") == "# Product: Oficio del barrio\n\n<!-- studio-product:v1 -->\n\n- Owner: Ana Pérez\n- Language: es\n"
    assert empty.read(".gitignore").splitlines() == IGNORED, "what studio generates is not versioned"
    for name in ("kit.css", "runtime.js"):
        assert empty.read("mockup/_studio/" + name) == (EXT_DIR / "mockup" / "_studio" / name).read_text(encoding="utf-8")
    assert (empty.product / "screens").is_dir()
    assert out["written"] == [PRODUCT + "/" + name for name in ("product.md", ".gitignore", "mockup/_studio/kit.css", "mockup/_studio/runtime.js")]


def test_scaffold_needs_a_name_only_when_there_is_no_product(empty):
    rc, out = empty.run("scaffold")
    assert rc == 2 and out == {"status": "invalid", "errors": ["scaffold takes --name: how the product is called"]}
    assert not (empty.product / "product.md").exists()
    assert empty.run("scaffold", "--name", "Oficio")[0] == 0
    assert empty.run("scaffold") == (0, {"status": "ok", "written": []}), "a second run has nothing to write"


def test_scaffold_never_rewrites_what_a_person_wrote(oficio):
    oficio.edit("product.md", "- Owner: Ana Pérez", "- Owner: Rosa Díaz")
    oficio.write(".gitignore", "notas.txt\n")
    rc, out = oficio.run("scaffold", "--name", "Otro nombre")
    assert rc == 0 and PRODUCT + "/product.md" not in out["written"]
    assert "# Product: Oficio\n" in oficio.read("product.md") and "- Owner: Rosa Díaz" in oficio.read("product.md")
    assert oficio.read(".gitignore").splitlines() == ["notas.txt"] + IGNORED


def test_scaffold_replaces_a_copy_of_the_kit_that_is_not_the_one_of_this_version(oficio):
    oficio.write("mockup/_studio/kit.css", "/* an older kit */\n")
    rc, out = oficio.run("scaffold")
    assert rc == 0 and PRODUCT + "/mockup/_studio/kit.css" in out["written"]
    assert oficio.read("mockup/_studio/kit.css") == (EXT_DIR / "mockup" / "_studio" / "kit.css").read_text(encoding="utf-8")


def test_scaffold_does_not_write_through_a_link(empty, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("mine\n", encoding="utf-8")
    empty.product.mkdir(parents=True)
    try:
        os.symlink(str(outside), str(empty.product / "product.md"))
    except (OSError, NotImplementedError):
        pytest.skip("this machine cannot make links")
    rc, out = empty.run("scaffold", "--name", "Oficio")
    assert rc == 2 and "is a link" in out["errors"][0]
    assert outside.read_text(encoding="utf-8") == "mine\n"


@pytest.mark.parametrize("args, needle", [
    (("status", "--name", "Oficio"), "--name goes with scaffold"),
    (("check", "--owner", "Ana"), "--owner goes with scaffold"),
    (("build", "--language", "es"), "--language goes with scaffold"),
    (("approve",), "invalid choice"),
])
def test_a_wrong_call_is_refused(oficio, args, needle):
    rc, out = oficio.run(*args)
    assert rc == 2 and needle in out["stderr"]


# ---------------------------------------------------------------- status: how far the design is


def test_a_project_without_a_product_is_told_where_to_start(empty):
    assert empty.status() == {"status": "none", "next": {"command": "speckit.studio.define", "args": "", "why": "The product has no design yet."}}


def test_status_says_how_far_the_product_and_each_area_are(oficio):
    out = oficio.status()
    assert (out["status"], out["product"], out["owner"], out["language"]) == ("ok", "Oficio", "Ana Pérez", "es")
    assert out["define"] == {"state": "done", "missing": [], "decisions": 2, "asked": 0}
    assert out["open"] == [{"id": "Q-003", "scope": "define", "question": "¿Hay cupo por taller?", "owner": "Ana Pérez"}]
    assert [area["id"] for area in out["areas"]] == ["acceso", "inicio"], "in the order of navigation.md"
    assert oficio.area("acceso") == {
        "id": "acceso", "title": "Acceso", "covers": "Entrar, crear una cuenta y recuperar la contraseña", "state": "drawn", "stories": 4, "screens": 5,
        "pages": 5, "rules": {"draft": 6}, "asked": 0, "open": 0, "decisions": 1, "links_pending": 0, "steps": {"map": "done", "mockup": "done"}}
    assert out["check"] == {"hard": 0, "notes": 1}
    assert out["next"] == {"command": "speckit.studio.mockup", "args": "", "why": "Every area is drawn. Open the mockup and say what to change."}


@pytest.mark.parametrize("name", ["vision.md", "actors.md", "navigation.md", "look-and-feel.md"])
def test_the_first_conversation_is_not_done_while_one_of_its_files_is_missing(oficio, name):
    oficio.remove(name)
    out = oficio.status()
    assert out["define"]["state"] == "active" and out["define"]["missing"] == [name]
    assert out["next"] == {"command": "speckit.studio.define", "args": "", "why": "The product still lacks: %s." % name}


def test_a_theme_with_a_color_missing_does_not_count(oficio):
    oficio.edit("look-and-feel.md", "- ring: #8ea2f2\n", "")
    out = oficio.status()
    assert out["define"]["missing"] == ["look-and-feel.md"] and out["summary"]["look"] == ""


def test_a_question_that_waits_for_an_answer_keeps_its_conversation_open(oficio):
    oficio.edit("decisions.md", "### Q-003 ¿Hay cupo por taller?\n- Round: 1\n- Status: open\n- Owner: Ana Pérez", "### Q-003 ¿Hay cupo por taller?\n- Round: 1\n- Status: asked")
    out = oficio.status()
    assert out["define"] == {"state": "active", "missing": [], "decisions": 2, "asked": 1}
    assert out["next"]["why"] == "1 questions of the first conversation wait for an answer."
    assert out["open"] == [], "a question nobody answered yet is not one the person left open"
    oficio.edit("decisions.md", "### Q-004 ¿Cuántos intentos fallidos antes de bloquear, y por cuánto tiempo?\n- Round: 1\n- Status: decided\n- Answer: 5 intentos seguidos, 15 minutos",
                "### Q-004 ¿Cuántos intentos?\n- Status: asked")
    area = oficio.area("acceso")
    assert (area["asked"], area["steps"]["map"]) == (1, "active")
    assert oficio.area("inicio")["steps"]["map"] == "done", "the questions of one area do not hold another"


def test_an_open_question_does_not_hold_the_design(oficio):
    oficio.edit("decisions.md", "## map acceso\n", "## map acceso\n\n### Q-009 ¿Se avisa por correo al bloquear?\n- Status: open\n- Owner: Ana Pérez\n")
    area = oficio.area("acceso")
    assert (area["open"], area["steps"]["map"]) == (1, "done")


def test_an_area_nobody_described_comes_next(oficio):
    oficio.edit("navigation.md", "## Flows", "### talleres Talleres\n- Covers: Ver los talleres y apuntarse\n\n## Flows")
    area = oficio.area("talleres")
    assert (area["state"], area["steps"]["map"], area["steps"]["mockup"], area["stories"], area["screens"]) == ("not-started", "pending", "pending", 0, 0)
    assert oficio.status()["next"] == {"command": "speckit.studio.map", "args": "talleres", "why": "Talleres is not described yet."}


def test_an_area_is_half_described_while_a_story_has_no_screen(oficio):
    oficio.edit(HOME, "- Stories: ST-5", "- Stories: none")
    assert oficio.area("inicio")["steps"]["map"] == "active"
    assert oficio.status()["next"] == {"command": "speckit.studio.map", "args": "inicio", "why": "Inicio is half described."}


def test_an_area_is_drawn_when_every_screen_has_its_page(oficio):
    oficio.remove("mockup/bloqueada.html")
    area = oficio.area("acceso")
    assert (area["pages"], area["steps"]["mockup"]) == (4, "active")
    assert oficio.status()["next"] == {"command": "speckit.studio.mockup", "args": "", "why": "Acceso is described and 1 of its 5 screens has no page yet."}
    oficio.remove("mockup/registro.html")
    assert oficio.status()["next"]["why"] == "Acceso is described and 2 of its 5 screens have no page yet."
    for name in ("bloqueada.html", "registro.html"):
        oficio.write("mockup/" + name, (FIXTURE_PAGES / name).read_text(encoding="utf-8"))
    oficio.remove("mockup/inicio.html")
    assert oficio.area("inicio")["steps"]["mockup"] == "pending"
    assert oficio.status()["next"]["why"] == "Inicio is described and its screen has no page yet."


def test_drawing_what_is_described_comes_before_describing_another_area(oficio):
    oficio.edit("navigation.md", "## Flows", "### talleres Talleres\n- Covers: Ver los talleres y apuntarse\n\n## Flows")
    oficio.remove("mockup/inicio.html")
    assert oficio.status()["next"]["command"] == "speckit.studio.mockup"


def test_status_tells_a_draft_from_a_rule_the_catalog_already_has(oficio):
    oficio.edit("capability-drafts.md", "### R-login-lockout\n- Text: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos.\n- Example: Ana falla 5 veces a las 10:00 y puede volver a intentar a las 10:15.\n\n", "")
    oficio.edit("capability-drafts.md", "### R-login-oauth\n- Text: Se puede entrar con una cuenta de Google, Facebook o GitHub.\n- Example: Ana elige Google y llega a su inicio sin escribir una contraseña.\n\n", "")
    (oficio.path / "specs/_capabilities/login").mkdir(parents=True)
    (oficio.path / "specs/_capabilities/login/spec.md").write_text(
        "# login\n\n## Rules\n\n- **R-login-lockout** [designed]: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos. (specs/_capabilities/_changes/20261111-design-login)\n"
        "- **R-login-oauth**: Se puede entrar con una cuenta de Google, Facebook o GitHub. (specs/002-oauth)\n", encoding="utf-8")
    assert oficio.check() == FINE
    assert oficio.area("acceso")["rules"] == {"designed": 1, "implemented": 1, "draft": 4}


# ---------------------------------------------------------------- check: the files of the product


def test_the_example_passes_the_check(oficio):
    assert oficio.check() == FINE


def test_check_needs_a_product(empty):
    rc, out = empty.check()
    assert rc == 2 and out == {"status": "invalid", "errors": ["specs/_product/product.md is not there: the design starts with speckit.studio.define"]}


def test_a_product_file_without_its_mark_is_not_read(oficio):
    oficio.edit("product.md", "<!-- studio-product:v1 -->\n", "")
    rc, out = oficio.check()
    assert rc == 2 and out["errors"] == ["specs/_product/product.md has no <!-- studio-product:v1 --> line: `scaffold` writes it"]
    assert oficio.run("status")[0] == 2 and oficio.run("build")[0] == 2


def test_a_product_in_a_newer_format_asks_for_an_upgrade(oficio):
    oficio.edit("product.md", "studio-product:v1", "studio-product:v2")
    rc, out = oficio.check()
    assert rc == 2 and out["errors"] == ["specs/_product/product.md is in a newer format than this script reads: update with `specify upgrade`"]


@pytest.mark.parametrize("first", ["# Oficio", "## Product: Oficio", "# Product:   "])
def test_the_product_file_starts_with_its_name(oficio, first):
    oficio.edit("product.md", "# Product: Oficio", first)
    assert oficio.hard("product.md:1", "the first line is `# Product: <name>`")


@pytest.mark.parametrize("name, old, new, needle", [
    ("actors.md", "- Role: vecina\n", "", "Role is missing"),
    ("actors.md", "- Role: vecina\n", "- Role: vecina\n- Role: otra\n", "Role is written twice"),
    ("actors.md", "- Role: vecina\n", "- Role: vecina\n- Age: 40\n", "Age is not a field here; the fields are Role, About, Email"),
    ("actors.md", "### ACT-vecina Ana", "### Ana", "an actor is `### ACT-<name> <how the person is called>`"),
    ("actors.md", "### ACT-tallerista Tomás", "### ACT-vecina Tomás", "actor ACT-vecina is defined twice"),
    ("navigation.md", "### acceso Acceso", "### Acceso", "an area is `### <name> <title>`"),
    ("navigation.md", "- Covers: Entrar, crear una cuenta y recuperar la contraseña\n", "", "Covers is missing"),
    ("navigation.md", "### FL-1 Entrar con correo", "### Entrar con correo", "a flow is `### FL-<number> <title>`"),
    ("navigation.md", "- Steps: SCR-login > SCR-home\n", "- Steps: SCR-login > inicio\n", "Steps: inicio is not `SCR-<name>` or `SCR-<name>/<state>`"),
    ("story-map.md", "### ST-1 Entrar con correo", "### Entrar con correo", "a story is `### ST-<number> <title>`"),
    ("story-map.md", "- Actor: ACT-vecina\n- Story: Como vecina, entro con Google", "- Actor: Ana\n- Story: Como vecina, entro con Google", "Actor: Ana is not written as an id"),
    ("story-map.md", "- Rules: R-login-oauth", "- Rules: login oauth", "Rules: login oauth is not written as an id"),
    ("capability-drafts.md", "## login\n", "## Login\n", "a capability is `## <name>`, in lowercase and hyphens"),
    ("capability-drafts.md", "### R-login-lockout", "### lockout", "a rule is `### R-<name>`, in lowercase and hyphens"),
    ("capability-drafts.md", "- Example: Ana falla 5 veces a las 10:00 y puede volver a intentar a las 10:15.\n", "", "Example is missing"),
    ("capability-drafts.md", "### R-login-oauth", "### R-login-lockout", "rule R-login-lockout is defined twice"),
    ("decisions.md", "## map acceso", "## acceso", "a group of questions is `## define` or `## map <area>`"),
    ("decisions.md", "### Q-001 ¿Quién puede publicar un taller?", "### ¿Quién puede publicar un taller?", "a question is `### Q-<number> <the question>`"),
    ("decisions.md", "- Status: open", "- Status: maybe", "Status is asked, decided or open"),
    ("decisions.md", "- Answer: Cualquier vecino con cuenta\n", "", "a decided question says its Answer"),
    ("decisions.md", "- Owner: Ana Pérez\n", "", "an open question says its Owner: who decides it"),
    ("decisions.md", "### Q-002", "### Q-001", "question Q-001 is defined twice"),
    ("look-and-feel.md", "# Look and feel", "Look and feel", "the first line is `# Look and feel`"),
    ("look-and-feel.md", "- Direction: A, sobria y clara\n", "", "Direction is missing"),
    ("look-and-feel.md", "- Radius: 12px", "- Radius: big", "a radius is a number of px, such as 12px"),
    ("look-and-feel.md", "- Radius-Control: 8px", "- Radius-Control: 1000px", "a radius is a number of px, such as 12px"),
    ("look-and-feel.md", "## Dark", "## Night", "the section Dark is missing"),
    ("look-and-feel.md", "- primary: #3451c7", "- primary: blue", "primary: blue is not a color written as #rgb or #rrggbb"),
    ("look-and-feel.md", "- ring: #8ea2f2\n", "", "ring is missing"),
    ("look-and-feel.md", "- Font: system", "- Font: Georgia; } body { color: red", "Font is `system` or the names of fonts"),
    ("product.md", "- Language: es", "- Language: es\n- Device: watch", "Device is desktop or phone"),
    ("directions.md", "## B Verde de huerta", "## b verde de huerta", "a direction is `## <letter> <name>`"),
    ("directions.md", "## B Verde de huerta", "## B", "a direction is `## <letter> <name>`"),
    ("directions.md", "## B Verde de huerta", "## A Verde de huerta", "direction A is defined twice"),
    ("directions.md", "- Why: Cercana y de barrio. Formas redondas y un verde que recuerda a lo hecho a mano.\n", "", "Why is missing"),
    ("directions.md", "- Radius: 20px", "- Radius: 2em", "a radius is a number of px, such as 12px"),
    ("directions.md", "- Font: Georgia, serif", "- Font: url(x)", "Font is `system` or the names of fonts"),
    ("directions.md", "- primary: #1f7a4a", "- primary: green", "primary: green is not a color written as #rgb or #rrggbb"),
    ("directions.md", "- Sample-Action: Apuntarme", "- Sample-Button: Apuntarme", "Sample-Button is not a field here"),
])
def test_a_file_that_is_not_written_as_its_kind_fails_the_check(oficio, name, old, new, needle):
    oficio.edit(name, old, new)
    rc, out = oficio.check()
    assert rc == 1 and out["status"] == "invalid" and oficio.hard(name, needle), out["hard"]


@pytest.mark.parametrize("old, new, needle", [
    ("# SCR-login Entrar", "# Entrar", "the first line is `# SCR-<name> <title>`"),
    ("# SCR-login Entrar", "# SCR-entrar Entrar", "the file of SCR-entrar is called SCR-entrar.md"),
    ("- States: normal, error, cargando", "- States: error, cargando", "States must include normal"),
    ("- States: normal, error, cargando", "- States: normal, Con Error", "States: Con Error is not a state name"),
    ("- File: entrar.html", "- File: Entrar", "File: Entrar is not a page name such as entrar.html"),
    ("- Session: none", "- Session: maybe", "Session is none or required"),
    ("## Purpose\n\nEntrar a la cuenta con correo y contraseña, o con un proveedor.\n", "", "the section ## Purpose is missing or empty"),
    ('- button "Entrar" -> SCR-home', "- el botón Entrar lleva al inicio", 'an element is `- <kind> "<label>"`'),
    ("- cargando: El botón dice \"Entrando…\".\n", "", "## States does not say what the state cargando shows"),
    ("- cargando: El botón dice", "- enviando: El botón dice", "## States describes enviando, which is not in States"),
    ("- Area: acceso", "- Area: entrada", "the area entrada is not in navigation.md"),
    ("- Stories: ST-1, ST-2", "- Stories: ST-1, ST-9", "Stories names ST-9, which is not in story-map.md"),
    ('- link "Crea tu cuenta" -> SCR-signup', '- link "Crea tu cuenta" -> SCR-alta', '"Crea tu cuenta" leads to SCR-alta, which is not a screen'),
    ('- link "Crea tu cuenta" -> SCR-signup', '- link "Crea tu cuenta" -> SCR-signup/enviado', '"Crea tu cuenta" leads to SCR-signup/enviado, and SCR-signup has no such state'),
])
def test_a_screen_that_is_not_written_as_a_screen_fails_the_check(oficio, old, new, needle):
    oficio.edit(LOGIN, old, new)
    assert oficio.hard("screens/SCR-login.md", needle), oficio.check()[1]["hard"]


def test_an_element_may_lead_to_one_state_of_a_screen(oficio):
    assert '- button "Crear cuenta" -> SCR-home/vacio' in oficio.read("screens/SCR-signup.md")
    assert oficio.check()[0] == 0


def test_who_sees_a_screen_is_an_actor_of_the_product(oficio):
    oficio.edit(HOME, "- Session: required", "- Session: required\n- Seen-By: ACT-vecina, ACT-admin")
    assert oficio.hard("screens/SCR-home.md", "Seen-By names ACT-admin, which is not in actors.md")
    oficio.edit(HOME, "- Seen-By: ACT-vecina, ACT-admin", "- Seen-By: anyone")
    assert oficio.check()[0] == 0


def test_two_screens_do_not_share_a_page(oficio):
    oficio.edit(LOCKED, "- File: bloqueada.html", "- File: entrar.html")
    assert oficio.hard("entrar.html is also the page of SCR-login")


def test_a_story_names_an_area_and_actors_of_the_product(oficio):
    oficio.edit("story-map.md", "- Area: inicio", "- Area: portada")
    oficio.edit("story-map.md", "- Actor: ACT-vecina\n- Story: Como persona nueva", "- Actor: ACT-visita\n- Story: Como persona nueva")
    assert oficio.hard("story-map.md", "the area portada is not in navigation.md")
    assert oficio.hard("story-map.md", "ST-3 names the actor ACT-visita, which is not in actors.md")


def test_a_story_has_a_screen_or_says_it_has_no_interface(oficio):
    oficio.edit(HOME, "- Stories: ST-5", "- Stories: none")
    assert oficio.hard("story-map.md", "ST-5 has no screen")
    oficio.edit("story-map.md", "- Criteria: Veo la lista de mis talleres, o un aviso si todavía no tengo ninguno.", "- Criteria: Veo la lista.\n- Interface: none - llega por correo")
    assert not oficio.hard("ST-5 has no screen")


def test_a_rule_that_is_cited_exists_and_a_draft_is_cited(oficio):
    oficio.edit("story-map.md", "- Rules: R-reset-link", "- Rules: R-reset-link, R-reset-once")
    assert oficio.hard("ST-4 cites R-reset-once, which is not in capability-drafts.md nor in the catalog")
    oficio.edit("capability-drafts.md", "## password-reset", "## signup-extra\n\n- Covers: Otra cosa\n\n### R-signup-terms\n- Text: Hay que aceptar los términos.\n- Example: Sin marcar la casilla no se crea la cuenta.\n\n## password-reset")
    assert oficio.hard("capability-drafts.md", "no story and no screen cites R-signup-terms")


def test_a_draft_does_not_rewrite_a_rule_of_the_catalog(oficio):
    folder = oficio.path / "specs/_capabilities/login"
    folder.mkdir(parents=True)
    (folder / "spec.md").write_text("- **R-login-lockout** [designed]: Tras 3 intentos fallidos, la cuenta se bloquea 30 minutos. (specs/_capabilities/_changes/x)\n", encoding="utf-8")
    assert oficio.hard("capability-drafts.md", "R-login-lockout is in the catalog with another text; a draft does not rewrite an approved rule")
    (folder / "spec.md").write_text("- **R-login-lockout** [designed]: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos. (specs/_capabilities/_changes/x)\n", encoding="utf-8")
    assert oficio.check()[0] == 0
    assert oficio.notes("capability-drafts.md", "R-login-lockout is already in the catalog with this text; the draft can go")


def test_a_folder_of_the_catalog_that_is_not_a_capability_holds_no_rules(oficio):
    oficio.edit("story-map.md", "- Rules: R-reset-link", "- Rules: R-reset-link, R-old-rule")
    for name in ("_changes/20261111-design", "_archive"):
        folder = oficio.path / "specs/_capabilities" / name
        folder.mkdir(parents=True)
        (folder / "spec.md").write_text("- **R-old-rule**: Una regla vieja. (specs/001-x)\n", encoding="utf-8")
    assert oficio.hard("ST-4 cites R-old-rule")


@pytest.mark.parametrize("old, new, needle", [
    ("- Steps: SCR-login > SCR-home\n", "- Steps: SCR-login\n", "FL-1 needs at least two steps"),
    ("- Steps: SCR-login > SCR-home\n", "- Steps: SCR-login > SCR-portada\n", "FL-1 passes through SCR-portada, which is not a screen"),
    ("- Steps: SCR-login > SCR-home\n", "- Steps: SCR-login > SCR-home/error\n", "FL-1 passes through SCR-home/error, and SCR-home has no such state"),
])
def test_a_flow_goes_through_screens_and_states_that_exist(oficio, old, new, needle):
    oficio.edit("navigation.md", old, new)
    assert oficio.hard("navigation.md", needle)


@pytest.mark.parametrize("name", ["spec.md", "screens/capability-delta.md"])
def test_the_product_keeps_no_file_with_the_name_of_a_spec_file(oficio, name):
    oficio.write(name, "# x\n")
    assert oficio.hard(name, "the product keeps no file with that name")


def test_a_requirement_line_belongs_in_a_spec(oficio):
    oficio.edit("vision.md", "## Out of scope", "- **FR-001**: The system MUST x.\n\n## Out of scope")
    assert oficio.hard("vision.md", "a requirement line (FR-###) belongs in a spec, not in the product")


def test_a_comment_is_not_part_of_a_file_and_keeps_the_line_numbers(oficio):
    oficio.edit("actors.md", "# Actors\n", "# Actors\n\n<!--\n### ACT-ejemplo Ejemplo\n- Role: x\n-->\n")
    oficio.edit("actors.md", "- About: Vecino que da talleres\n", "")
    assert oficio.hard("actors.md:13", "About is missing")
    oficio.run("build")
    assert [person["id"] for person in oficio.built("product.js")["personas"]] == ["ACT-vecina", "ACT-tallerista"]


def test_what_sits_in_a_code_fence_is_not_read_as_a_block(oficio):
    oficio.edit("actors.md", "# Actors\n", "# Actors\n\n```\n### ACT-ejemplo\n```\n")
    assert oficio.check()[0] == 0


# ---------------------------------------------------------------- check: the pages of the mockup


def test_before_any_page_exists_the_check_looks_at_the_files_only(oficio):
    for page in sorted((oficio.product / "mockup").glob("*.html")):
        page.unlink()
    oficio.edit(LOGIN, "- Entry: yes\n", "")
    assert oficio.check() == (0, {"status": "ok", "hard": [], "notes": []})


@pytest.mark.parametrize("old, new, needle", [
    ('data-screen="SCR-login"', 'data-screen="SCR-entrar"', "<body data-screen> says SCR-entrar and this is the page of SCR-login"),
    ('data-area="acceso"', 'data-area="inicio"', "<body data-area> says inicio and SCR-login is in the area acceso"),
    ('  <script src="_studio/product.js"></script>\n', "", "the page does not load _studio/product.js"),
    ('  <link rel="stylesheet" href="_studio/kit.css">\n', "", "the page does not load _studio/kit.css"),
    ('href="recuperar.html"', 'href="https://example.com/recuperar"', "https://example.com/recuperar leaves the mockup"),
    ('<script src="_studio/runtime.js"></script>', '<script src="_studio/runtime.js"></script>\n  <script src="//cdn.example.com/x.js"></script>', "//cdn.example.com/x.js leaves the mockup"),
    ('href="recuperar.html"', 'href="olvide.html"', "olvide.html is not the page of any screen"),
    ('data-ref="R-login-attempts-warning"', 'data-ref="R-login-warning"', "data-ref cites R-login-warning, which is not a story nor a rule"),
    ('data-state="error" data-ref', 'data-state="fallo" data-ref', "data-state uses fallo, which is not a state of SCR-login"),
    ('data-ref="ST-2 R-login-oauth"', 'data-ref="ST-2"', "no element cites R-login-oauth with data-ref"),
])
def test_a_page_agrees_with_its_screen(oficio, old, new, needle):
    oficio.edit(PAGE, old, new)
    assert oficio.hard("mockup/entrar.html", needle), oficio.check()[1]["hard"]


def test_a_link_that_only_names_a_place_stays_inside_the_mockup(oficio):
    assert 'href="#taller"' in oficio.read("mockup/inicio.html")
    oficio.edit(PAGE, 'href="recuperar.html"', 'href="recuperar.html?estado=enviado#arriba"')
    assert oficio.check()[0] == 0


def test_a_person_starts_somewhere(oficio):
    oficio.edit(LOGIN, "- Entry: yes\n", "")
    assert oficio.hard("no screen says `- Entry: yes`")


def test_every_screen_is_reached_from_where_a_person_starts(oficio):
    oficio.edit("navigation.md", "### FL-2 Bloqueo por intentos fallidos\n- Area: acceso\n- Steps: SCR-login > SCR-login/error > SCR-login-locked\n\n", "")
    assert oficio.hard("mockup/bloqueada.html", "nothing leads to SCR-login-locked from a screen where a person starts")
    oficio.edit(LOCKED, "- Rules: R-login-lockout", "- Rules: R-login-lockout\n- Entry: yes")
    assert oficio.check()[0] == 0, "a second entry is reached by itself"


def test_a_step_of_a_flow_is_a_way_to_the_next_screen(oficio):
    assert "bloqueada.html" not in oficio.read(PAGE), "no link leads to the locked screen: the flow does"
    assert oficio.check()[0] == 0


def test_every_screen_leads_somewhere(oficio):
    page = oficio.read("mockup/bloqueada.html")
    oficio.write("mockup/bloqueada.html", re.sub(r'href="[a-z-]+\.html[^"]*"', 'href="#luego"', page))
    assert oficio.hard("mockup/bloqueada.html", "SCR-login-locked leads to no other screen")


@pytest.mark.parametrize("old, new, needle", [
    ('<html lang="es">', "<html>", "<html> has no lang"),
    ("<h1>Entra a tu cuenta</h1>", "<h1>Entra a tu cuenta</h1><h1>Otra vez</h1>", "the page has 2 h1 headings; it takes one"),
    ('<label for="email">Correo</label>', "<span>Correo</span>", "a field has no label"),
    ('<p class="divider">o con tu correo</p>', '<img src="logo.png">', "an image has no alt text"),
    ('<button class="toggle" type="button" aria-controls="password" aria-label="Mostrar contraseña">Mostrar</button>', '<button class="toggle" type="button"></button>', "a button has no text and no aria-label"),
    ('<p class="divider">o con tu correo</p>', '<p class="divider" style="color: #ff0000">o con tu correo</p>', "the page sets its own colors or fonts"),
    ("</head>", "<style>h1 { font-family: Georgia; }</style></head>", "the page sets its own colors or fonts"),
])
def test_how_a_page_is_written_is_worth_a_note_and_never_stops_the_design(oficio, old, new, needle):
    oficio.edit(PAGE, old, new)
    rc, out = oficio.check()
    assert rc == 0 and out["hard"] == [] and oficio.notes("mockup/entrar.html", needle), out


def test_a_field_named_by_aria_and_an_image_with_an_empty_alt_are_fine(oficio):
    oficio.edit(PAGE, '<label for="email">Correo</label>', "")
    oficio.edit(PAGE, 'id="email" name="email"', 'id="email" aria-label="Correo" name="email"')
    oficio.edit(PAGE, '<p class="divider">o con tu correo</p>', '<img src="logo.png" alt="">')
    oficio.edit(LOGIN, '- field "Correo"\n', '- field "Correo"\n- image "Logo"\n')
    assert oficio.check() == FINE


def test_colors_that_cannot_be_read_are_worth_a_note(oficio):
    oficio.edit("look-and-feel.md", "- muted: #565e6b", "- muted: #c9ccd1")
    rc, out = oficio.check()
    assert rc == 0
    assert oficio.notes("look-and-feel.md", "Light, muted on bg has a contrast of 1.5 and needs 4.5")
    assert oficio.notes("look-and-feel.md", "Light, muted on surface has a contrast of 1.6 and needs 4.5")
    assert not oficio.notes("Dark, muted")
    oficio.edit("look-and-feel.md", "- muted: #a3aab6", "- muted: #3a3f4a")
    assert oficio.notes("look-and-feel.md", "Dark, muted on bg has a contrast of 1.8 and needs 4.5")


# ---------------------------------------------------------------- build: the files of the mockup nobody edits


def test_build_writes_what_the_mockup_needs(oficio):
    rc, out = oficio.run("build")
    assert rc == 0 and out["status"] == "ok" and out["check"] == {"hard": 0, "notes": 1}
    assert out["written"] == [PRODUCT + "/mockup/" + name for name in (
        "_studio/kit.css", "_studio/runtime.js", "_studio/theme.css", "_studio/screens.js", "_studio/product.js", "index.html")]
    screens = oficio.built("screens.js")
    assert screens["areas"] == {"acceso": "Acceso", "inicio": "Inicio"}
    assert screens["pantallas"]["SCR-login"] == {"archivo": "entrar.html", "titulo": "Entrar", "area": "acceso", "estados": ["normal", "error", "cargando"]}
    assert screens["pantallas"]["SCR-home"]["sesion"] is True and "sesion" not in screens["pantallas"]["SCR-login"]
    assert screens["flujos"]["FL-2"] == {"titulo": "Bloqueo por intentos fallidos", "pasos": [["SCR-login", "normal"], ["SCR-login", "error"], ["SCR-login-locked", "normal"]]}
    assert screens["entrada"] == "SCR-login", "where a person without a session is sent"
    data = oficio.built("product.js")
    assert (data["producto"], data["idioma"], data["dispositivo"]) == ("Oficio", "es", "desktop")
    assert data["personas"][0] == {"id": "ACT-vecina", "nombre": "Ana", "rol": "vecina", "descripcion": "Vecina que se apunta a talleres", "correo": "ana@ejemplo.com"}
    assert data["historias"]["ST-5"] == "Como vecina, al entrar veo los talleres a los que me apunté."
    assert data["reglas"]["R-login-lockout"] == {"capacidad": "login", "texto": "Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos.",
                                                 "estado": "draft", "nota": "Ana falla 5 veces a las 10:00 y puede volver a intentar a las 10:15."}
    assert len(data["reglas"]) == 6


def test_the_theme_comes_from_the_look_and_feel_file(oficio):
    oficio.run("build")
    theme = oficio.read("mockup/_studio/theme.css")
    assert ":root {\n  --bg: #f4f5f7;\n" in theme and "  --ring: #3451c7;\n" in theme
    assert '  :root:not([data-theme="light"]) {\n    --bg: #0e1116;' in theme and ':root[data-theme="dark"] {\n  --bg: #0e1116;' in theme
    assert "  --radius: 12px;\n  --radius-control: 8px;\n  --font: system-ui, " in theme
    assert "http" not in theme and "@import" not in theme, "nothing in the theme loads from another site"
    oficio.edit("look-and-feel.md", "- Font: system", "- Font: Georgia")
    oficio.run("build")
    assert "  --font: Georgia, system-ui, " in oficio.read("mockup/_studio/theme.css")


@pytest.mark.parametrize("how", ["missing", "one color short"])
def test_a_theme_that_is_not_complete_is_not_written(oficio, how):
    if how == "missing":
        oficio.remove("look-and-feel.md")
    else:
        oficio.edit("look-and-feel.md", "- ring: #8ea2f2\n", "")
    rc, out = oficio.run("build")
    assert rc == 0 and PRODUCT + "/mockup/_studio/theme.css" not in out["written"]
    assert not (oficio.product / "mockup/_studio/theme.css").exists()
    assert PRODUCT + "/mockup/_studio/screens.js" in out["written"]


def test_a_rule_of_the_catalog_shows_its_state_in_the_mockup(oficio):
    oficio.edit("capability-drafts.md", "### R-login-lockout\n- Text: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos.\n- Example: Ana falla 5 veces a las 10:00 y puede volver a intentar a las 10:15.\n\n", "")
    folder = oficio.path / "specs/_capabilities/login"
    folder.mkdir(parents=True)
    (folder / "spec.md").write_text("- **R-login-lockout** [designed]: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos. (specs/_capabilities/_changes/x)\n", encoding="utf-8")
    oficio.run("build")
    assert oficio.built("product.js")["reglas"]["R-login-lockout"] == {
        "capacidad": "login", "texto": "Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos.", "estado": "designed", "nota": ""}
    (folder / "spec.md").write_text("- **R-login-lockout**: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos. (specs/001-acceso)\n", encoding="utf-8")
    oficio.run("build")
    assert oficio.built("product.js")["reglas"]["R-login-lockout"]["estado"] == "implemented"


def test_the_first_page_of_the_mockup_is_where_a_person_starts(oficio):
    oficio.run("build")
    index = oficio.read("mockup/index.html")
    assert '<html lang="es">' in index and "<title>Oficio</title>" in index
    assert '<script>location.replace("entrar.html" + location.search);</script>' in index
    assert '<a class="btn btn-primary" href="entrar.html">Entrar</a>' in index


def test_text_of_the_product_cannot_close_a_script_or_add_markup(oficio):
    oficio.edit("story-map.md", "Como vecina, al entrar veo los talleres a los que me apunté.", "Veo </script><script>alert(1)</script> mis talleres.")
    oficio.edit("product.md", "# Product: Oficio", '# Product: Oficio <b>"x"</b>')
    oficio.run("build")
    assert "</script>" not in oficio.read("mockup/_studio/product.js")
    assert oficio.built("product.js")["historias"]["ST-5"] == "Veo </script><script>alert(1)</script> mis talleres."
    assert "<title>Oficio &lt;b&gt;&quot;x&quot;&lt;/b&gt;</title>" in oficio.read("mockup/index.html")


def test_a_screen_without_a_page_name_is_left_out_of_the_mockup(oficio):
    oficio.edit(LOCKED, "- File: bloqueada.html\n", "")
    oficio.run("build")
    assert "SCR-login-locked" not in oficio.built("screens.js")["pantallas"]


def test_build_needs_a_product(empty):
    rc, out = empty.run("build")
    assert rc == 2 and "the design starts with speckit.studio.define" in out["errors"][0]


# ---------------------------------------------------------------- status: the steps, and what waits for the person


def test_status_lists_the_steps_with_what_their_files_prove(oficio):
    out = oficio.status()
    assert out["steps"] == [
        {"name": "define", "command": "speckit.studio.define", "state": "done", "fact": "2 decisions"},
        {"name": "map", "command": "speckit.studio.map", "state": "done", "fact": "2 of 2 areas"},
        {"name": "mockup", "command": "speckit.studio.mockup", "state": "done", "fact": "6 of 6 screens"}]
    assert out["totals"] == {"areas": 2, "not_started": 0, "in_design": 0, "drawn": 2, "screens": 6, "pages": 6, "rules": 6, "decisions": 3}


def test_a_product_that_only_has_a_name_has_every_step_ahead(empty):
    empty.run("scaffold", "--name", "Oficio")
    out = empty.status()
    assert [(step["state"], step["fact"]) for step in out["steps"]] == [("active", "Not started"), ("pending", "No areas yet"), ("pending", "No screens yet")]
    assert out["totals"]["areas"] == 0 and out["attention"] == [] and out["mockup"] is False and out["documents"] == []
    assert out["summary"] == {"idea": "", "people": [], "look": ""}


def test_the_first_step_says_what_it_decided_and_what_it_lacks(oficio):
    oficio.remove("look-and-feel.md")
    oficio.remove("actors.md")
    assert oficio.status()["steps"][0]["fact"] == "2 decisions, missing the people, the look"
    oficio.edit("decisions.md", "- Status: decided\n- Answer: Cualquier vecino con cuenta", "- Status: asked")
    step = oficio.status()["steps"][0]
    assert (step["state"], step["fact"]) == ("active", "1 decision, 1 waiting, missing the people, the look")


def test_the_map_step_counts_the_areas_that_are_described(oficio):
    oficio.edit("navigation.md", "## Flows", "### talleres Talleres\n- Covers: Ver los talleres y apuntarse\n\n## Flows")
    out = oficio.status()
    assert out["steps"][1] == {"name": "map", "command": "speckit.studio.map", "state": "active", "fact": "2 of 3 areas"}
    assert (out["totals"]["not_started"], out["totals"]["drawn"]) == (1, 2)
    for name in ("story-map.md", "capability-drafts.md"):
        oficio.write(name, "")
    for path in (oficio.product / "screens").glob("*.md"):
        path.unlink()
    step = oficio.status()["steps"][1]
    assert (step["state"], step["fact"]) == ("pending", "0 of 3 areas")


def test_the_mockup_step_counts_the_screens_that_have_a_page(oficio):
    oficio.remove("mockup/inicio.html")
    out = oficio.status()
    assert out["steps"][2] == {"name": "mockup", "command": "speckit.studio.mockup", "state": "active", "fact": "5 of 6 screens"}
    assert oficio.area("inicio")["state"] == "in-design" and out["totals"]["in_design"] == 1
    for path in (oficio.product / "mockup").glob("*.html"):
        path.unlink()
    step = oficio.status()["steps"][2]
    assert (step["state"], step["fact"]) == ("pending", "0 of 6 screens")


def test_a_mockup_that_does_not_agree_with_the_design_needs_attention(oficio):
    oficio.edit(PAGE, 'data-screen="SCR-login"', 'data-screen="SCR-otra"')
    out = oficio.status()
    assert out["steps"][2]["state"] == "attention" and out["steps"][2]["fact"] == "6 of 6 screens, 1 problem"
    found = [item for item in out["attention"] if item["kind"] == "check"]
    assert found == [{"kind": "check", "text": "The check found 1 problem in the design.",
                      "details": ["specs/_product/mockup/entrar.html: <body data-screen> says SCR-otra and this is the page of SCR-login"]}]


def test_a_problem_in_the_files_does_not_mark_a_mockup_nobody_drew(oficio):
    for path in (oficio.product / "mockup").glob("*.html"):
        path.unlink()
    oficio.edit("story-map.md", "- Actor: ACT-vecina\n- Story: Como vecina, entro con Google", "- Actor: ACT-nadie\n- Story: Como vecina, entro con Google")
    out = oficio.status()
    assert out["check"]["hard"] == 1 and (out["steps"][2]["state"], out["steps"][2]["fact"]) == ("pending", "0 of 6 screens")


def test_the_problems_shown_are_the_first_five(oficio):
    oficio.remove("actors.md")
    oficio.edit(PAGE, 'data-screen="SCR-login"', 'data-screen="SCR-otra"')
    found = next(item for item in oficio.status()["attention"] if item["kind"] == "check")
    assert found["text"] == "The check found 8 problems in the design." and len(found["details"]) == 5


def test_what_waits_for_the_person_is_listed(oficio):
    out = oficio.status()
    assert out["attention"] == [
        {"kind": "open", "text": "Open, Ana Pérez decides: ¿Hay cupo por taller?"},
        {"kind": "pending", "area": "inicio", "text": "6 links in Inicio lead to something that is not designed yet."}]
    oficio.edit("decisions.md", "- Status: decided\n- Answer: Cualquier vecino con cuenta", "- Status: asked")
    oficio.edit("decisions.md", "- Status: decided\n- Answer: 5 intentos seguidos, 15 minutos", "- Status: asked")
    page = oficio.read("mockup/inicio.html")
    oficio.write("mockup/inicio.html", page.replace('href="#taller"', 'href="entrar.html"').replace('href="#proponer"', 'href="entrar.html"'))
    texts = [item["text"] for item in oficio.status()["attention"]]
    assert texts == ["1 question about the product waits for an answer.", "1 question about Acceso waits for an answer.",
                     "Open, Ana Pérez decides: ¿Hay cupo por taller?", "1 link in Inicio leads to something that is not designed yet."]
    assert oficio.area("acceso")["decisions"] == 0, "a question that waits is not a decision"


def test_status_says_what_was_understood_and_what_can_be_read(oficio):
    out = oficio.status()
    assert out["summary"] == {
        "idea": "Una app para que los vecinos se apunten a talleres del barrio, y para que quien da un taller lo publique.",
        "people": [{"name": "Ana", "role": "vecina", "about": "Vecina que se apunta a talleres"}, {"name": "Tomás", "role": "tallerista", "about": "Vecino que da talleres"}],
        "look": "A, sobria y clara"}
    assert out["documents"] == ["vision.md", "actors.md", "navigation.md", "story-map.md", "capability-drafts.md", "decisions.md", "look-and-feel.md"]
    assert out["mockup"] is False, "nobody built the mockup yet"
    oficio.run("build")
    oficio.remove("vision.md")
    out = oficio.status()
    assert out["mockup"] is True and out["documents"][0] == "actors.md" and out["summary"]["idea"] == ""


def test_the_answer_is_utf8_whatever_the_console_speaks(oficio):
    """A Windows console has its own code page. The answer must not take it: an agent reads it as UTF-8."""
    done = subprocess.run([PYTHON, "-S", str(SCRIPT), "status", "--root", str(oficio.path)], capture_output=True,
                          env=dict(os.environ, PYTHONIOENCODING="cp1252", **oficio.env))
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout.decode("utf-8"))
    assert out["owner"] == "Ana Pérez" and out["open"][0]["question"] == "¿Hay cupo por taller?"
    assert out["summary"]["people"][1]["name"] == "Tomás"


def test_the_idea_is_the_first_paragraph_of_the_vision(oficio):
    oficio.write("vision.md", "# Visión\n\n<!-- nota -->\nUna app del barrio,\npara talleres.\n\nSegundo párrafo.\n")
    assert oficio.status()["summary"]["idea"] == "Una app del barrio, para talleres."


def test_the_product_says_where_it_is_used_most(oficio, empty):
    assert oficio.status()["device"] == "desktop"
    oficio.edit("product.md", "- Language: es", "- Language: es\n- Device: Phone")
    assert oficio.status()["device"] == "phone" and oficio.check() == FINE
    oficio.run("build")
    assert oficio.built("product.js")["dispositivo"] == "phone"
    empty.run("scaffold", "--name", "Oficio", "--device", "phone")
    assert empty.read("product.md").endswith("- Language: en\n- Device: phone\n")
    rc, out = empty.run("scaffold", "--device", "watch")
    assert rc == 2 and "invalid choice" in out["stderr"]


def test_a_question_keeps_what_is_needed_to_ask_it_again(oficio):
    oficio.edit("decisions.md", "### Q-003 ¿Hay cupo por taller?\n- Round: 1\n",
                "### Q-003 ¿Hay cupo por taller?\n- Round: 1\n- Options: a) Sí, con lista de espera; b) Sí, sin lista de espera; c) No hay cupo\n- Recommended: a\n")
    assert oficio.check() == FINE


# ---------------------------------------------------------------- check: what a page can do


def test_where_a_form_leads_is_a_link_like_any_other(oficio):
    oficio.edit(PAGE, 'data-goto="inicio.html?sesion=1"', 'data-goto="nada.html"')
    assert oficio.hard("mockup/entrar.html", "nada.html is not the page of any screen")


def test_a_rule_the_catalog_has_is_past_its_draft(oficio):
    folder = oficio.path / "specs/_capabilities/login"
    folder.mkdir(parents=True)
    (folder / "spec.md").write_text("- **R-login-lockout** [designed]: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos. (specs/_capabilities/_changes/x)\n", encoding="utf-8")
    assert oficio.notes("capability-drafts.md", "R-login-lockout is already in the catalog with this text; the draft can go")
    assert oficio.area("acceso")["rules"] == {"designed": 1, "draft": 5}
    oficio.run("build")
    assert oficio.built("product.js")["reglas"]["R-login-lockout"]["estado"] == "designed"


def test_corners_can_be_as_round_as_a_pill(oficio):
    oficio.edit("look-and-feel.md", "- Radius-Control: 8px", "- Radius-Control: 999px")
    assert oficio.check() == FINE
    oficio.run("build")
    assert "  --radius-control: 999px;\n" in oficio.read("mockup/_studio/theme.css")


def test_what_a_person_presses_or_fills_in_is_on_the_page_under_its_name(oficio):
    oficio.edit(LOGIN, '- button "Entrar" -> SCR-home', '- button "Acceder" -> SCR-home')
    oficio.edit(LOGIN, '- field "Contraseña"', '- field "Clave"')
    rc, out = oficio.check()
    assert rc == 0 and out["hard"] == [], "it is worth knowing, and stops nothing"
    assert oficio.notes("mockup/entrar.html", 'specs/_product/screens/SCR-login.md names the button "Acceder" and the page does not show it')
    assert oficio.notes("mockup/entrar.html", 'names the field "Clave" and the page does not show it')
    assert len(oficio.notes("and the page does not show it")) == 2


def test_a_name_counts_whatever_its_case_and_wherever_a_person_reads_it(oficio):
    oficio.edit(LOGIN, '- button "Entrar" -> SCR-home', '- button "ENTRA   a tu cuenta" -> SCR-home')
    oficio.edit(LOGIN, '- link "Crea tu cuenta" -> SCR-signup', '- link "Mostrar contraseña" -> SCR-signup')
    assert oficio.check() == FINE, "the heading says it in other letters, and the show button says it in its aria-label"


def test_a_name_that_is_only_in_a_script_is_not_on_the_page(oficio):
    oficio.edit(LOGIN, '- button "Entrar" -> SCR-home', '- button "Acceder" -> SCR-home')
    oficio.edit(PAGE, "</head>", '<script>var label = "Acceder";</script></head>')
    assert oficio.notes("mockup/entrar.html", 'names the button "Acceder" and the page does not show it')


def test_what_a_screen_only_describes_is_not_looked_for_by_name(oficio):
    oficio.edit(HOME, '- list "Mis talleres"', '- list "Una lista que la página no titula"\n- text "Un texto cualquiera"')
    assert oficio.check() == FINE


def test_a_picture_goes_on_a_page_only_when_its_screen_names_one(oficio):
    oficio.edit(PAGE, '<p class="divider">o con tu correo</p>', '<div class="ph">Foto del taller</div>')
    assert oficio.notes("mockup/entrar.html", "the page shows a picture and specs/_product/screens/SCR-login.md names no image")
    assert len(oficio.notes("the page shows a picture")) == 1
    oficio.edit(LOGIN, '- field "Correo"\n', '- field "Correo"\n- image "Foto del taller"\n')
    assert oficio.check() == FINE
    oficio.edit(LOGIN, '- image "Foto del taller"\n', "")
    oficio.edit(PAGE, '<div class="ph">Foto del taller</div>', '<img src="foto.png" alt="Foto del taller">')
    assert oficio.notes("mockup/entrar.html", "the page shows a picture")
    oficio.edit(PAGE, '<img src="foto.png" alt="Foto del taller">', '<span class="ph-thumb">Foto</span>')
    assert oficio.notes("mockup/entrar.html", "the page shows a picture")


def test_a_button_can_only_set_a_state_its_screen_has(oficio):
    oficio.edit(PAGE, '<a class="small forgot" href="recuperar.html">', '<button class="btn" type="button" data-set-state="error">Probar</button><a class="small forgot" href="recuperar.html">')
    assert oficio.check() == FINE
    oficio.edit(PAGE, 'data-set-state="error"', 'data-set-state="borrar"')
    assert oficio.hard("mockup/entrar.html", "data-state uses borrar, which is not a state of SCR-login")


def test_a_link_to_what_is_not_designed_yet_is_worth_a_note(oficio):
    assert oficio.notes("mockup/inicio.html", "6 links lead to something that is not designed yet: #proponer, #taller, #talleres")
    oficio.edit(PAGE, 'href="recuperar.html"', 'href="#"')
    assert not oficio.notes("mockup/entrar.html", "not designed yet"), "a bare # is not a promise of a screen"


def minimal(project):
    """The least a product needs to show one screen: the early mockup."""
    project.run("scaffold", "--name", "Mínimo")
    project.write("navigation.md", "# Navigation\n\n## Areas\n\n### notas Notas\n- Covers: Escribir notas\n")
    project.write("story-map.md", "# Stories\n\n### ST-1 Ver mis notas\n- Area: notas\n- Actor: none\n- Story: Veo mis notas.\n- Criteria: Están todas.\n")
    project.write("screens/SCR-notas.md", "# SCR-notas Notas\n\n- Area: notas\n- File: notas.html\n- States: normal\n- Stories: ST-1\n- Entry: yes\n\n"
                                          "## Purpose\n\nVer las notas.\n\n## Elements\n\n- list \"Notas\"\n")
    project.write("mockup/notas.html", '<!doctype html>\n<html lang="es">\n<head>\n<title>Notas</title>\n'
                  + "".join('<link rel="stylesheet" href="_studio/%s">\n' % name for name in ("theme.css", "kit.css"))
                  + "".join('<script src="_studio/%s"></script>\n' % name for name in ("product.js", "screens.js", "runtime.js"))
                  + '</head>\n<body data-screen="SCR-notas" data-area="notas">\n<div class="app"><main class="page"><h1 data-ref="ST-1">Notas</h1>'
                    '<a href="#nueva">Nueva nota</a></main></div>\n</body>\n</html>\n')


def test_a_product_of_one_screen_can_be_seen_early(empty):
    minimal(empty)
    rc, out = empty.check()
    assert rc == 0 and out["hard"] == [], "one screen has nowhere else to lead"
    out = empty.status()
    assert [step["state"] for step in out["steps"]] == ["active", "done", "done"]
    assert out["next"]["command"] == "speckit.studio.define", "the look is not chosen yet"
    rc, out = empty.run("build")
    assert rc == 0 and empty.built("screens.js")["entrada"] == "SCR-notas" and empty.built("product.js")["personas"] == []


def test_the_mockup_knows_no_entry_when_no_screen_is_one(oficio):
    oficio.edit(LOGIN, "- Entry: yes\n", "")
    oficio.run("build")
    assert oficio.built("screens.js")["entrada"] == ""


# ---------------------------------------------------------------- directions: the looks a person chooses from


def page_data(project):
    page = project.read("mockup/_studio/directions.html")
    start = page.index('<script type="application/json" id="data">') + len('<script type="application/json" id="data">')
    return json.loads(page[start:page.index("</script>", start)])


def test_directions_shows_every_complete_look_side_by_side(oficio):
    rc, out = oficio.run("directions")
    assert rc == 0 and out["page"] == PRODUCT + "/mockup/_studio/directions.html" and out["link"].startswith("file://") and out["link"].endswith(out["page"])
    assert out["directions"] == [{"id": "A", "name": "Sobria y clara", "complete": True}, {"id": "B", "name": "Verde de huerta", "complete": True},
                                 {"id": "C", "name": "Tinta y papel", "complete": True}]
    page = oficio.read("mockup/_studio/directions.html")
    assert "/*DATA*/null" not in page and '<link rel="stylesheet" href="kit.css">' in page
    assert oficio.read("mockup/_studio/kit.css") == (EXT_DIR / "mockup" / "_studio" / "kit.css").read_text(encoding="utf-8")
    data = page_data(oficio)
    assert (data["producto"], data["idioma"], data["dispositivo"]) == ("Oficio", "es", "desktop")
    assert data["muestra"] == {"titulo": "Talleres de esta semana", "accion": "Apuntarme", "entradas": [
        ["Pan de masa madre", "Sábado a las 10:00, con Rosa"], ["Arreglo de bicis", "Domingo a las 11:30, con Tomás"], ["Cerámica", "Martes a las 18:00, con Inés"]]}
    looks = {look["id"]: look for look in data["direcciones"]}
    assert sorted(looks) == ["A", "B", "C"]
    assert (looks["B"]["nombre"], looks["B"]["radio"], looks["B"]["radioControl"]) == ("Verde de huerta", "20px", "14px")
    assert looks["B"]["claro"]["primary"] == "#1f7a4a" and looks["B"]["oscuro"]["primary"] == "#5ccf8f" and looks["B"]["oscuro"]["shadow"] == "none"
    assert looks["C"]["fuente"].startswith("Georgia, serif, system-ui") and looks["A"]["fuente"].startswith("system-ui")
    assert [look["elegida"] for look in data["direcciones"]] == [True, False, False], "look-and-feel.md says A"


def test_a_direction_that_is_not_complete_is_left_out(oficio):
    oficio.edit("directions.md", "- ring: #7adba4\n", "")
    rc, out = oficio.run("directions")
    assert rc == 0 and [look["complete"] for look in out["directions"]] == [True, False, True]
    assert [look["id"] for look in page_data(oficio)["direcciones"]] == ["A", "C"]
    assert oficio.hard("directions.md", "ring is missing")


def test_directions_needs_one_complete_look(oficio):
    oficio.remove("directions.md")
    rc, out = oficio.run("directions")
    assert rc == 2 and out == {"status": "invalid", "errors": ["specs/_product/directions.md has no complete direction: each one is `## <letter> <name>` with its Light and Dark colors"]}
    assert not (oficio.product / "mockup/_studio/directions.html").exists()


def test_the_sample_screens_say_something_plain_without_sample_fields(oficio):
    oficio.edit("directions.md", "- Sample-Title: Talleres de esta semana\n", "")
    oficio.edit("directions.md", "- Sample-Action: Apuntarme\n", "")
    oficio.edit("directions.md", "Pan de masa madre | Sábado a las 10:00, con Rosa; ", "Pan de masa madre; ")
    oficio.run("directions")
    sample = page_data(oficio)["muestra"]
    assert (sample["titulo"], sample["accion"], sample["entradas"][0]) == ("", "", ["Pan de masa madre", ""])


def test_text_of_a_direction_cannot_close_the_script_of_the_page(oficio):
    oficio.edit("directions.md", "- Why: Neutra y ordenada.", "- Why: </script><script>alert(1)</script> Neutra y ordenada.")
    oficio.run("directions")
    assert "</script><script>alert(1)" not in oficio.read("mockup/_studio/directions.html")
    assert page_data(oficio)["direcciones"][0]["porque"].startswith("</script><script>alert(1)</script> Neutra")


def test_a_direction_whose_colors_cannot_be_read_is_worth_a_note(oficio):
    oficio.edit("directions.md", "- muted: #4f5f52", "- muted: #c9ccd1")
    rc, out = oficio.check()
    assert rc == 0 and oficio.notes("directions.md:", "direction B: Light, muted on bg has a contrast of 1.5 and needs 4.5")
    assert not oficio.notes("direction A") and not oficio.notes("direction B: Dark")


def test_pick_makes_a_direction_the_look_of_the_product(oficio):
    rc, out = oficio.run("pick", "B")
    assert rc == 0 and out["written"] == [PRODUCT + "/look-and-feel.md"] and out["check"] == {"hard": 0, "notes": 1}
    look = oficio.read("look-and-feel.md")
    assert look.startswith("# Look and feel\n\n- Direction: B Verde de huerta\n- Font: system\n- Radius: 20px\n- Radius-Control: 14px\n\n## Light\n\n- bg: #f3f6f1\n- surface: #ffffff\n")
    assert "\n## Dark\n\n- bg: #101511\n" in look and look.endswith("- ring: #7adba4\n")
    assert oficio.check() == FINE
    assert oficio.status()["summary"]["look"] == "B Verde de huerta"
    oficio.run("directions")
    assert [look["elegida"] for look in page_data(oficio)["direcciones"]] == [False, True, False]
    oficio.run("build")
    assert ":root {\n  --bg: #f3f6f1;\n" in oficio.read("mockup/_studio/theme.css")


def test_pick_gives_a_product_without_a_look_its_look(oficio):
    oficio.remove("look-and-feel.md")
    assert oficio.status()["define"]["missing"] == ["look-and-feel.md"]
    oficio.run("directions")
    assert [look["elegida"] for look in page_data(oficio)["direcciones"]] == [False, False, False]
    assert oficio.run("pick", "C")[0] == 0
    assert oficio.status()["define"]["state"] == "done"
    assert "  --font: Georgia, serif, system-ui, " in (oficio.run("build") and oficio.read("mockup/_studio/theme.css"))


def test_pick_reports_the_check_of_the_new_look(oficio):
    oficio.edit("directions.md", "- muted: #4f5f52", "- muted: #c9ccd1")
    assert len(oficio.check()[1]["notes"]) == 3, "the home page, and two pairs of direction B that cannot be read"
    rc, out = oficio.run("pick", "B")
    assert rc == 0 and out["check"] == {"hard": 0, "notes": 5}, "the look of the product now has the same two pairs"


def test_pick_refuses_a_direction_that_is_not_there_or_not_complete(oficio):
    before = oficio.read("look-and-feel.md")
    rc, out = oficio.run("pick", "Z")
    assert rc == 2 and out["errors"] == ["specs/_product/directions.md has no direction Z; it has A, B, C"]
    oficio.edit("directions.md", "- ring: #7adba4\n", "")
    rc, out = oficio.run("pick", "B")
    assert rc == 2 and out["errors"] == ["direction B is not complete: it needs every color of Light and of Dark"]
    assert oficio.read("look-and-feel.md") == before


@pytest.mark.parametrize("args, needle", [
    (("pick",), "pick takes the letter of a direction, such as A"),
    (("pick", "b"), "pick takes the letter of a direction, such as A"),
    (("status", "B"), "a letter goes with pick"),
    (("build", "--page", "directions"), "--page goes with open or shots"),
    (("open", "--area", "acceso"), "--area goes with shots"),
    (("open", "--states"), "--states goes with shots"),
    (("shots", "--no-browser"), "--no-browser goes with open"),
    (("build", "--device", "phone"), "--device goes with scaffold"),
])
def test_an_option_goes_with_its_command(oficio, args, needle):
    rc, out = oficio.run(*args)
    assert rc == 2 and needle in out["stderr"]


# ---------------------------------------------------------------- open: seeing the mockup


def test_open_builds_the_mockup_and_says_where_it_is(oficio):
    rc, out = oficio.run("open", "--no-browser")
    assert rc == 0 and out["status"] == "ok" and out["opened"] is False and out["check"] == {"hard": 0, "notes": 1}
    assert out["link"] == (oficio.product / "mockup" / "index.html").resolve().as_uri()
    assert "location.replace" in oficio.read("mockup/index.html") and oficio.built("screens.js")["entrada"] == "SCR-login"


def test_open_opens_no_browser_where_it_was_told_not_to(oficio):
    rc, out = oficio.run("open")
    assert rc == 0 and out["opened"] is False, "the tests run with SPECKIT_STUDIO_NO_BROWSER"


def test_open_shows_the_directions_when_asked(oficio):
    rc, out = oficio.run("open", "--page", "directions", "--no-browser")
    assert rc == 0 and out["link"] == (oficio.product / "mockup" / "_studio" / "directions.html").resolve().as_uri()
    assert not (oficio.product / "mockup" / "index.html").exists(), "the mockup was not asked for"


def test_open_has_nothing_to_show_before_the_first_page(oficio):
    for path in (oficio.product / "mockup").glob("*.html"):
        path.unlink()
    rc, out = oficio.run("open", "--no-browser")
    assert rc == 3 and out == {"status": "nothing", "errors": ["no screen has a page yet: speckit.studio.mockup draws them"]}
    assert not (oficio.product / "mockup" / "index.html").exists()


@pytest.mark.parametrize("wanted, allowed, opens", [(True, True, True), (False, True, False), (True, False, False)])
def test_open_opens_the_browser_when_asked_and_allowed(oficio, studio, monkeypatch, wanted, allowed, opens):
    seen = []
    monkeypatch.setattr("webbrowser.open", lambda link: seen.append(link) or True)
    monkeypatch.setattr(studio, "can_open", lambda: allowed)
    kit = EXT_DIR / "mockup" / "_studio"
    link, opened = studio.show(studio.Product(oficio.path), kit, None, wanted)
    assert opened is opens and seen == ([link] if opens else [])
    assert link == (oficio.product / "mockup" / "index.html").resolve().as_uri()


@pytest.mark.parametrize("env, platform, expected", [
    ({}, "darwin", True),
    ({"DISPLAY": ":0"}, "linux", True),
    ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", True),
    ({}, "linux", False),
    ({}, "win32", True),
    ({"CI": "true"}, "darwin", False),
    ({"CI": "0"}, "darwin", True),
    ({"SPECKIT_STUDIO_NO_BROWSER": "1"}, "darwin", False),
    ({"SPECKIT_STUDIO_NO_BROWSER": "false"}, "darwin", True),
    ({"SPECKIT_PROGRESS_NO_BROWSER": "1"}, "darwin", False),
    ({"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}, "darwin", False),
    ({"SSH_CLIENT": "1.2.3.4 5 22"}, "darwin", False),
    ({"SSH_TTY": "/dev/pts/0"}, "darwin", False),
])
def test_a_browser_opens_only_where_the_person_can_see_it(studio, env, platform, expected):
    assert studio.can_open(env, platform) is expected


# ---------------------------------------------------------------- shots: a picture of each screen

posix = pytest.mark.skipif(os.name == "nt", reason="the stand-in for the browser is a script with a shebang")

BROWSER = r"""#!%s
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "calls.jsonl"), "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
target = next(arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("--screenshot="))
skip = os.environ.get("FAKE_BROWSER_SKIP", "")
if not skip or (skip != "all" and skip not in sys.argv[-1]):
    with open(target, "wb") as picture:
        picture.write(b"" if os.environ.get("FAKE_BROWSER_EMPTY") else b"\x89PNG stand-in")
"""


@pytest.fixture
def browser(oficio, tmp_path):
    """A stand-in for the browser: it writes the picture it is asked for and keeps how it was called."""
    folder = tmp_path / "browser"
    folder.mkdir()
    script = folder / "browser"
    script.write_text(BROWSER % sys.executable, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    oficio.env["SPECKIT_STUDIO_BROWSER"] = str(script)

    def calls():
        log = folder / "calls.jsonl"
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return calls


@posix
def test_shots_takes_a_picture_of_each_screen_of_an_area(oficio, browser):
    rc, out = oficio.run("shots", "--area", "acceso")
    assert rc == 0 and out["failed"] == [] and out["check"] == {"hard": 0, "notes": 1}
    assert [shot["name"] for shot in out["shots"]] == ["SCR-forgot", "SCR-login-locked", "SCR-login", "SCR-reset", "SCR-signup"]
    assert out["shots"][2] == {"name": "SCR-login", "screen": "SCR-login", "state": "normal", "title": "Entrar", "file": PRODUCT + "/mockup/_shots/SCR-login.png"}
    for shot in out["shots"]:
        assert (oficio.path / shot["file"]).read_bytes() == b"\x89PNG stand-in"
    calls = browser()
    assert len(calls) == 5
    call = calls[2]
    assert call[0] == "--headless=new" and "--window-size=1280,800" in call and "--screenshot=" + str(oficio.product / "mockup/_shots/SCR-login.png") in call
    assert call[-1] == (oficio.product / "mockup" / "entrar.html").resolve().as_uri() + "?captura=1&modo=claro&sesion=0&persona=ACT-vecina"
    profile = next(arg.split("=", 1)[1] for arg in call if arg.startswith("--user-data-dir="))
    assert not os.path.exists(profile), "the profile the browser ran with is gone"
    assert (oficio.product / "mockup" / "_studio" / "screens.js").exists(), "the mockup was built before the pictures"


@posix
def test_shots_can_take_every_state_and_opens_a_session_where_one_is_needed(oficio, browser):
    rc, out = oficio.run("shots", "--area", "inicio", "--states")
    assert rc == 0 and [shot["name"] for shot in out["shots"]] == ["SCR-home", "SCR-home.vacio", "SCR-home.cargando"]
    assert [shot["state"] for shot in out["shots"]] == ["normal", "vacio", "cargando"]
    links = [call[-1].split("?", 1)[1] for call in browser()]
    assert links == ["captura=1&modo=claro&sesion=1&persona=ACT-vecina", "captura=1&modo=claro&sesion=1&persona=ACT-vecina&estado=vacio",
                     "captura=1&modo=claro&sesion=1&persona=ACT-vecina&estado=cargando"]


@posix
def test_shots_takes_every_screen_as_the_person_who_sees_it_and_in_the_size_of_the_device(oficio, browser):
    oficio.edit("product.md", "- Language: es", "- Language: es\n- Device: phone")
    oficio.edit(HOME, "- Layout: app\n", "- Layout: app\n- Seen-By: ACT-tallerista\n")
    rc, out = oficio.run("shots")
    assert rc == 0 and len(out["shots"]) == 6
    calls = browser()
    assert all("--window-size=500,1000" in call for call in calls), "the phone frame, in a window that holds it"
    home = next(call for call in calls if "/inicio.html?" in call[-1])
    assert home[-1].endswith("?captura=1&modo=claro&sesion=1&persona=ACT-tallerista")


@posix
def test_shots_skips_a_screen_that_has_no_page(oficio, browser):
    oficio.remove("mockup/bloqueada.html")
    rc, out = oficio.run("shots", "--area", "acceso")
    assert rc == 0 and "SCR-login-locked" not in [shot["name"] for shot in out["shots"]] and len(browser()) == 4


@posix
def test_shots_can_take_the_page_of_the_directions(oficio, browser):
    rc, out = oficio.run("shots", "--page", "directions")
    assert rc == 0 and out["shots"] == [{"name": "directions", "title": "Directions", "file": PRODUCT + "/mockup/_shots/directions.png"}]
    call = browser()[0]
    assert "--window-size=1440,1560" in call and call[-1] == (oficio.product / "mockup/_studio/directions.html").resolve().as_uri() + "?modo=claro"


@posix
def test_shots_says_which_pictures_the_browser_did_not_take(oficio, browser):
    stale = oficio.product / "mockup" / "_shots" / "SCR-reset.png"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"an older picture")
    oficio.env["FAKE_BROWSER_SKIP"] = "nueva-contrasena.html"
    rc, out = oficio.run("shots", "--area", "acceso")
    assert rc == 0 and [shot["name"] for shot in out["failed"]] == ["SCR-reset"] and len(out["shots"]) == 4
    assert not stale.exists(), "an older picture is not passed off as the new one"
    oficio.env["FAKE_BROWSER_SKIP"] = "all"
    rc, out = oficio.run("shots", "--area", "acceso")
    assert rc == 3 and out == {"status": "nothing", "errors": ["the browser took no picture: open the mockup instead"]}


@posix
def test_an_empty_picture_is_not_a_picture(oficio, browser):
    oficio.env["FAKE_BROWSER_EMPTY"] = "1"
    rc, out = oficio.run("shots", "--area", "inicio")
    assert rc == 3 and out["errors"] == ["the browser took no picture: open the mockup instead"]


def test_shots_without_a_browser_says_so(oficio):
    rc, out = oficio.run("shots")
    assert rc == 3 and out["status"] == "nothing" and "no Chrome, Chromium or Edge was found" in out["errors"][0] and "SPECKIT_STUDIO_BROWSER" in out["errors"][0]
    assert not (oficio.product / "mockup" / "_shots").exists()


@posix
def test_shots_refuses_an_area_that_is_not_there_and_waits_for_the_first_page(oficio, browser):
    rc, out = oficio.run("shots", "--area", "pagos")
    assert rc == 2 and out["errors"] == ["the area pagos is not in navigation.md"]
    for path in (oficio.product / "mockup").glob("*.html"):
        path.unlink()
    rc, out = oficio.run("shots")
    assert rc == 3 and out["errors"] == ["no screen has a page yet: speckit.studio.mockup draws them"] and browser() == []


def test_the_browser_for_the_pictures_can_be_named(studio, tmp_path):
    named = tmp_path / "my-browser"
    named.write_text("", encoding="utf-8")
    assert studio.find_browser({"SPECKIT_STUDIO_BROWSER": str(named)}) == str(named)
    assert studio.find_browser({"SPECKIT_STUDIO_BROWSER": str(tmp_path / "gone")}) is None, "a browser that is named and missing is not replaced by another"
