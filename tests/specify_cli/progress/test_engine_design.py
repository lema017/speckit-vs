"""The progress of the design of a product: its own page, its place in the list of specs, and the
lines a studio command ends with.

The studio extension keeps the design in ``specs/_product/`` and its script knows what those files
mean. The engine loads that script from the project, adds the log and the documents, and draws.
The project of these tests is Oficio, the example of the studio tests.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from .conftest import OFICIO, REPO as ROOT, step_event, symlink
from .test_engine_render import HOSTILE, parse_page

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
STEPS_LINE = "Steps: Define: 2 decisions; Map: 2 of 2 areas; Mockup: 6 of 6 screens"
NEXT_LINE = "Next: /speckit.studio.mockup. Every area is drawn. Open the mockup and say what to change."


@pytest.fixture
def designed(project):
    """A project with the studio extension and the design of Oficio: two areas, both drawn."""
    project.design()
    return project


def product(project, name):
    return project.root / "specs" / "_product" / name


def edit(project, name, old, new):
    path = product(project, name)
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, "%s holds %r %d times" % (name, old, text.count(old))
    path.write_text(text.replace(old, new), encoding="utf-8")


def skills(project):
    (project.root / ".specify" / "init-options.json").write_text(json.dumps({"ai": "claude", "ai_skills": True}), encoding="utf-8")


def design_of(engine, project, now=NOW):
    return engine.build_design(project.root, project.root / ".specify" / "progress", now=now)


def page_data(path):
    return json.loads(parse_page(Path(path)).data)


def run(engine, project, *args):
    return engine.main(["--root", str(project.root), *args])


# -- A project without a design is drawn as before ---------------------------------------------


def test_a_project_without_a_design_has_no_design_page(engine, project):
    project.feature()
    drawn = engine.render_project(project.root)
    assert drawn["design"] is None
    assert page_data(drawn["index"])["design"] is None
    out = project.root / ".specify" / "progress"
    assert not (out / "design.html").exists() and not (out / ".design.json").exists()
    assert engine.design_status(project.root) is None


def test_a_design_without_the_studio_extension_is_not_shown(engine, project):
    shutil.copytree(str(OFICIO), str(project.root / "specs" / "_product"))
    assert engine.has_design(project.root) is True
    assert design_of(engine, project) is None and engine.render_project(project.root)["design"] is None


def test_a_folder_without_its_product_file_is_not_a_design(engine, designed):
    product(designed, "product.md").unlink()
    assert engine.has_design(designed.root) is False and design_of(engine, designed) is None


def test_a_design_behind_a_link_is_not_read(engine, designed, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    shutil.move(str(designed.root / "specs" / "_product"), str(elsewhere))
    symlink(designed.root / "specs" / "_product", elsewhere, target_is_directory=True)
    assert engine.has_design(designed.root) is False and engine.render_project(designed.root)["design"] is None


def test_a_studio_script_behind_a_link_is_not_loaded(engine, designed, tmp_path):
    script = designed.root / ".specify" / "extensions" / "studio" / "scripts" / "python" / "studio.py"
    elsewhere = tmp_path / "studio.py"
    shutil.move(str(script), str(elsewhere))
    symlink(script, elsewhere)
    assert engine.load_studio(designed.root) is None and design_of(engine, designed) is None


# -- What the page of the design says ----------------------------------------------------------


def test_the_design_page_says_how_far_each_step_is(engine, designed):
    data = design_of(engine, designed)
    assert (data["schema"], data["product"], data["owner"], data["problem"], data["generated"]) == (1, "Oficio", "Ana Pérez", None, "2026-01-02T03:04:05Z")
    assert [(step["name"], step["label"], step["command"], step["state"], step["fact"]) for step in data["steps"]] == [
        ("define", "Define", "/speckit.studio.define", "done", "2 decisions"),
        ("map", "Map", "/speckit.studio.map", "done", "2 of 2 areas"),
        ("mockup", "Mockup", "/speckit.studio.mockup", "done", "6 of 6 screens")]
    assert all(step["running"] is False and step["note"] is None and step["who"] is None for step in data["steps"])
    assert data["totals"]["areas"] == 2 and data["totals"]["drawn"] == 2 and data["screens"] == 6
    assert data["next"] == {"command": "/speckit.studio.mockup", "why": "Every area is drawn. Open the mockup and say what to change."}


def test_each_area_shows_its_own_steps(engine, designed):
    edit(designed, "navigation.md", "## Flows", "### talleres Talleres\n- Covers: Ver los talleres y apuntarse\n\n## Flows")
    product(designed, "mockup/inicio.html").unlink()
    edit(designed, "decisions.md", "- Status: decided\n- Answer: 5 intentos seguidos, 15 minutos", "- Status: asked")
    areas = {area["id"]: area for area in design_of(engine, designed)["areas"]}
    assert areas["acceso"]["steps"] == [
        {"name": "map", "label": "Map", "state": "active", "fact": "4 stories, 1 waiting", "running": False},
        {"name": "mockup", "label": "Mockup", "state": "done", "fact": "5 of 5 screens", "running": False}]
    assert (areas["acceso"]["title"], areas["acceso"]["state"], areas["acceso"]["screens"], areas["acceso"]["rules"]) == ("Acceso", "in-design", 5, {"draft": 6})
    assert [(chip["state"], chip["fact"]) for chip in areas["inicio"]["steps"]] == [("done", "1 story"), ("pending", "not yet")]
    assert [(chip["state"], chip["fact"]) for chip in areas["talleres"]["steps"]] == [("pending", "not yet"), ("pending", "not yet")]
    assert (areas["talleres"]["state"], areas["talleres"]["covers"], areas["talleres"]["command"]) == (
        "not-started", "Ver los talleres y apuntarse", "/speckit.studio.map talleres")


def test_the_page_says_what_was_understood_and_what_waits(engine, designed):
    data = design_of(engine, designed)
    assert data["summary"]["idea"].startswith("Una app para que los vecinos se apunten a talleres del barrio")
    assert [person["name"] for person in data["summary"]["people"]] == ["Ana", "Tomás"] and data["summary"]["look"] == "A, sobria y clara"
    assert [item["text"] for item in data["attention"]] == [
        "Open, Ana Pérez decides: ¿Hay cupo por taller?", "6 links in Inicio lead to something that is not designed yet."]


def test_the_documents_of_the_design_can_be_read_on_the_page(engine, designed):
    data = design_of(engine, designed)
    assert [doc["name"] for doc in data["documents"]] == [
        "vision.md", "actors.md", "navigation.md", "story-map.md", "capability-drafts.md", "decisions.md", "look-and-feel.md"]
    vision = data["documents"][0]
    assert vision["markdown"] is True and vision["truncated"] is False and vision["text"] == product(designed, "vision.md").read_text(encoding="utf-8")
    assert vision["href"] == "../../specs/_product/vision.md"
    assert data["links"] == [], "nobody built the mockup yet"
    assert design_of(engine, designed)["documents"] and engine.build_design(
        designed.root, designed.root / ".specify" / "progress", now=NOW, include_documents=False)["documents"] == []


def test_the_page_links_to_the_mockup_and_to_the_looks_once_they_are_built(engine, designed):
    studio = engine.load_studio(designed.root)
    kit = designed.root / ".specify" / "extensions" / "studio" / "mockup" / "_studio"
    studio.build(studio.Product(designed.root), kit)
    assert design_of(engine, designed)["links"] == [{"label": "Open the mockup", "href": "../../specs/_product/mockup/index.html"}]
    studio.directions(studio.Product(designed.root), kit)
    assert design_of(engine, designed)["links"] == [
        {"label": "Open the mockup", "href": "../../specs/_product/mockup/index.html"},
        {"label": "Compare the looks", "href": "../../specs/_product/mockup/_studio/directions.html"}]


def test_a_document_the_script_does_not_name_as_one_is_not_read(engine, designed, monkeypatch):
    skills(designed)
    studio = engine.load_studio(designed.root)
    real = studio.status
    monkeypatch.setattr(studio, "status", lambda found: dict(real(found), documents=["vision.md", "../../.specify/init-options.json", "mockup/entrar.html", 7]))
    assert [doc["name"] for doc in design_of(engine, designed)["documents"]] == ["vision.md"]


# -- How a command is written ------------------------------------------------------------------


def test_a_command_is_written_the_way_the_agent_of_the_project_takes_it(engine, designed):
    assert engine.command_text(designed.root, "speckit.studio.map", "acceso") == "/speckit.studio.map acceso"
    skills(designed)
    assert engine.command_text(designed.root, "speckit.studio.map", "acceso") == "/speckit-studio-map acceso"
    assert engine.command_text(designed.root, "speckit.studio.define") == "/speckit-studio-define"
    data = design_of(engine, designed)
    assert data["steps"][0]["command"] == "/speckit-studio-define" and data["next"]["command"] == "/speckit-studio-mockup"


@pytest.mark.parametrize("options", ["{not json", "[]", '{"ai_skills": "yes"}', '{"ai_skills": false}'])
def test_options_that_do_not_say_skills_leave_the_dots(engine, designed, options):
    (designed.root / ".specify" / "init-options.json").write_text(options, encoding="utf-8")
    assert engine.command_text(designed.root, "speckit.studio.define") == "/speckit.studio.define"


# -- What the log adds -------------------------------------------------------------------------


def stamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_a_step_that_was_started_and_not_closed_is_running(engine, designed):
    designed.log(product(designed, ""), [step_event("mockup", "in_progress", ts=stamp(NOW - timedelta(minutes=5)), area="acceso",
                                                    actor={"harness": "claude", "source": "configured"})])
    data = design_of(engine, designed)
    mockup = data["steps"][2]
    assert (mockup["running"], mockup["state"], mockup["who"], mockup["ts"]) == (True, "done", "claude", stamp(NOW - timedelta(minutes=5)))
    assert data["steps"][0]["running"] is False
    areas = {area["id"]: area for area in data["areas"]}
    assert [chip["running"] for chip in areas["acceso"]["steps"]] == [False, True]
    assert areas["acceso"]["steps"][1]["state"] == "done", "what the files prove is not undone by a new run"
    assert [chip["running"] for chip in areas["inicio"]["steps"]] == [False, False], "the step ran for another area"


def test_a_step_that_was_started_before_its_files_exist_is_active(engine, designed):
    product(designed, "mockup/inicio.html").unlink()
    for path in (designed.root / "specs" / "_product" / "mockup").glob("*.html"):
        path.unlink()
    designed.log(product(designed, ""), [step_event("mockup", "in_progress", ts=stamp(NOW), area="inicio")])
    data = design_of(engine, designed)
    assert (data["steps"][2]["state"], data["steps"][2]["fact"]) == ("active", "0 of 6 screens")
    areas = {area["id"]: area for area in data["areas"]}
    assert areas["inicio"]["steps"][1]["state"] == "active" and areas["acceso"]["steps"][1]["state"] == "pending"


def test_a_step_that_was_closed_is_not_running(engine, designed):
    designed.log(product(designed, ""), [step_event("map", "in_progress", ts=stamp(NOW - timedelta(minutes=9)), area="acceso"),
                                         step_event("map", "done", ts=stamp(NOW - timedelta(minutes=2)), area="acceso", note="5 pantallas")])
    data = design_of(engine, designed)
    assert (data["steps"][1]["running"], data["steps"][1]["note"]) == (False, "5 pantallas")
    assert data["areas"][0]["steps"][0]["running"] is False


def test_a_step_started_long_ago_is_not_running_any_more(engine, designed):
    designed.log(product(designed, ""), [step_event("define", "in_progress", ts=stamp(NOW - timedelta(hours=4, minutes=1)))])
    assert design_of(engine, designed)["steps"][0]["running"] is False
    designed.log(product(designed, ""), [step_event("define", "in_progress", ts=stamp(NOW - timedelta(hours=3, minutes=59)))])
    assert design_of(engine, designed)["steps"][0]["running"] is True


def test_a_start_without_a_time_is_not_running(engine, designed):
    designed.log(product(designed, ""), [step_event("define", "in_progress", ts="yesterday")])
    assert design_of(engine, designed)["steps"][0]["running"] is False


def test_the_note_shown_is_the_one_of_the_last_time_the_step_finished(engine, designed):
    designed.log(product(designed, ""), [step_event("define", "done", note="Dos personas"), step_event("define", "done", note="Tres personas"),
                                         step_event("define", "in_progress", ts=stamp(NOW), note="Otra ronda")])
    step = design_of(engine, designed)["steps"][0]
    assert (step["note"], step["running"]) == ("Tres personas", True)


def test_the_activity_is_the_log_of_the_design_newest_first(engine, designed):
    designed.log(product(designed, ""), [step_event("define", "done", ts="2026-01-01T10:00:00Z", note="Dos personas"),
                                         step_event("map", "done", ts="2026-01-01T11:00:00Z", area="acceso"),
                                         step_event("map", "in_progress", ts="2026-01-01T12:00:00Z", area="pagos"),
                                         {"v": 1, "ts": "2026-01-01T12:30:00Z", "kind": "task", "task": "T001", "status": "done"}])
    assert design_of(engine, designed)["activity"] == [
        {"step": "map", "status": "in_progress", "ts": "2026-01-01T12:00:00Z", "note": None, "area": "pagos", "area_title": None},
        {"step": "map", "status": "done", "ts": "2026-01-01T11:00:00Z", "note": None, "area": "acceso", "area_title": "Acceso"},
        {"step": "define", "status": "done", "ts": "2026-01-01T10:00:00Z", "note": "Dos personas", "area": None, "area_title": None}]


@pytest.mark.parametrize("area", ["Acceso", "acceso pagos", "../x", "a" * 61, "", 7, None])
def test_an_area_that_is_not_written_as_one_is_dropped_from_the_event(engine, area):
    event = engine.clean_event(step_event("map", "done", area=area))
    assert event is not None and "area" not in event


def test_an_area_written_as_one_is_kept(engine):
    assert engine.clean_event(step_event("map", "done", area="mis-inscripciones"))["area"] == "mis-inscripciones"
    assert engine.clean_event(step_event("map", "done", area="a" * 60))["area"] == "a" * 60


def test_lines_of_the_log_that_cannot_be_read_need_attention(engine, designed):
    designed.log(product(designed, ""), ["{broken", json.dumps(step_event("define", "done")), "also broken"])
    texts = [item["text"] for item in design_of(engine, designed)["attention"]]
    assert texts[-1] == "2 lines of the design's log could not be read."
    assert len(design_of(engine, designed)["activity"]) == 1


# -- A design nobody can read ------------------------------------------------------------------


def test_a_design_that_cannot_be_read_says_why_and_stops_nothing(engine, designed):
    designed.feature()
    edit(designed, "product.md", "<!-- studio-product:v1 -->\n", "")
    drawn = engine.render_project(designed.root)
    problem = "specs/_product/product.md has no <!-- studio-product:v1 --> line: `scaffold` writes it"
    assert page_data(drawn["design"]["path"]) == {"schema": 1, "generated": page_data(drawn["design"]["path"])["generated"], "product": "", "problem": problem}
    assert drawn["design"]["summary"]["problem"] == problem and "steps" not in drawn["design"]["summary"]
    assert page_data(drawn["index"])["design"]["problem"] == problem
    assert len(drawn["pages"]) == 1, "the page of the spec was still drawn"
    assert engine.design_lines(drawn["design"]["summary"], "file:///x") == ["The design cannot be read: " + problem, "Page: file:///x"]


def test_a_studio_script_that_cannot_be_loaded_is_a_problem_of_the_design_only(engine, designed):
    designed.feature()
    (designed.root / ".specify" / "extensions" / "studio" / "scripts" / "python" / "studio.py").write_text("def broken(:\n", encoding="utf-8")
    drawn = engine.render_project(designed.root)
    assert drawn["design"]["summary"]["problem"] and len(drawn["pages"]) == 1


def test_text_of_the_design_cannot_close_the_script_of_a_page_nor_reach_the_terminal(engine, designed, capsys):
    edit(designed, "product.md", "# Product: Oficio", "# Product: Oficio " + HOSTILE)
    drawn = engine.render_project(designed.root)
    for path in (drawn["design"]["path"], drawn["index"]):
        page = parse_page(Path(path))
        assert page.tags.count("script") == 2 and "img" not in page.tags, "the data and the code, and nothing a name could add"
    assert page_data(drawn["design"]["path"])["product"].startswith("Oficio </script><img src=x onerror=alert(1)>")
    assert run(engine, designed, "show") == 0
    shown = capsys.readouterr().out
    assert "\x1b" not in shown and " " not in shown and "Design of Oficio </script>" in shown


# -- Drawing -----------------------------------------------------------------------------------


def test_drawing_everything_draws_the_design_and_puts_it_on_top_of_the_list(engine, designed):
    designed.feature()
    drawn = engine.render_project(designed.root, now=NOW)
    out = designed.root / ".specify" / "progress"
    assert drawn["design"]["path"] == str(out / "design.html")
    summary = drawn["design"]["summary"]
    assert summary == {
        "file": "design.html", "generated": "2026-01-02T03:04:05Z", "product": "Oficio", "problem": None,
        "totals": {"areas": 2, "drawn": 2, "in_design": 0, "not_started": 0},
        "steps": [{"label": "Define", "state": "done", "fact": "2 decisions"}, {"label": "Map", "state": "done", "fact": "2 of 2 areas"},
                  {"label": "Mockup", "state": "done", "fact": "6 of 6 screens"}],
        "next": {"command": "/speckit.studio.mockup", "why": "Every area is drawn. Open the mockup and say what to change."},
        "attention": 2}
    assert page_data(drawn["index"])["design"] == summary
    assert json.loads((out / ".design.json").read_text(encoding="utf-8")) == summary
    assert page_data(out / "design.html")["product"] == "Oficio"
    assert 'name="generator" content="speckit-progress"' in (out / "design.html").read_text(encoding="utf-8")


def test_redrawing_one_spec_does_not_read_the_design(engine, designed, monkeypatch):
    feature = designed.feature()
    engine.render_project(designed.root, now=NOW)
    before = (designed.root / ".specify" / "progress" / "design.html").read_bytes()
    edit(designed, "product.md", "# Product: Oficio", "# Product: Otro nombre")
    monkeypatch.setattr(engine, "build_design", lambda *args, **kwargs: pytest.fail("a redraw of one spec read the design"))
    monkeypatch.setattr(engine, "load_studio", lambda *args, **kwargs: pytest.fail("a redraw of one spec loaded the studio script"))
    drawn = engine.render_project(designed.root, feature)
    assert drawn["design"]["summary"]["product"] == "Oficio", "the summary of the last time the design was drawn"
    assert page_data(drawn["index"])["design"]["product"] == "Oficio"
    assert (designed.root / ".specify" / "progress" / "design.html").read_bytes() == before


def test_redrawing_one_spec_before_the_design_was_ever_drawn_shows_no_design(engine, designed):
    feature = designed.feature()
    drawn = engine.render_project(designed.root, feature)
    assert drawn["design"] is None and page_data(drawn["index"])["design"] is None


@pytest.mark.parametrize("stored", ["{not json", "[]", '{"file": "other.html"}'])
def test_a_stored_summary_that_is_not_one_is_not_shown(engine, designed, stored):
    feature = designed.feature()
    engine.render_project(designed.root)
    (designed.root / ".specify" / "progress" / ".design.json").write_text(stored, encoding="utf-8")
    assert engine.render_project(designed.root, feature)["design"] is None


def test_a_design_that_is_gone_takes_its_page_and_its_summary_with_it(engine, designed):
    feature = designed.feature()
    engine.render_project(designed.root)
    out = designed.root / ".specify" / "progress"
    assert (out / "design.html").exists() and (out / ".design.json").exists()
    shutil.rmtree(str(designed.root / "specs" / "_product"))
    assert engine.render_project(designed.root, feature)["design"] is None, "a stored summary of a design that is gone is not shown"
    assert (out / "design.html").exists(), "a redraw of one spec removes no page"
    drawn = engine.render_project(designed.root)
    assert drawn["design"] is None and not (out / "design.html").exists() and not (out / ".design.json").exists()
    assert page_data(drawn["index"])["design"] is None


def test_a_spec_called_design_keeps_its_own_page(engine, designed):
    feature = designed.root / "specs" / "design"
    feature.mkdir()
    (feature / "spec.md").write_text("# Feature Specification: Design tokens\n", encoding="utf-8")
    drawn = engine.render_project(designed.root)
    assert [Path(page["path"]).name for page in drawn["pages"]] == ["design-2.html"]
    assert page_data(drawn["design"]["path"])["product"] == "Oficio"


def test_reading_the_design_for_a_terminal_writes_nothing(engine, designed):
    before = designed.written()
    summary = engine.design_status(designed.root, now=NOW)
    assert summary["product"] == "Oficio" and summary["steps"][0] == {"label": "Define", "state": "done", "fact": "2 decisions"}
    assert designed.written() == before


# -- The command a studio command ends with ----------------------------------------------------


def log_of(project):
    path = product(project, "progress.jsonl")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_design_records_the_step_and_says_how_far_the_design_is(engine, designed, capsys):
    assert run(engine, designed, "--harness", "claude", "design", "map", "done", "--area", "acceso", "--note", "5 pantallas y 6 reglas") == 0
    out = capsys.readouterr()
    link = (designed.root / ".specify" / "progress" / "design.html").resolve().as_uri()
    assert out.out.splitlines() == ["Design of Oficio", STEPS_LINE, NEXT_LINE, "Needs attention: 2, see the page", "Page: " + link]
    assert out.err == ""
    event = log_of(designed)[0]
    assert (event["kind"], event["step"], event["status"], event["area"], event["note"]) == ("step", "map", "done", "acceso", "5 pantallas y 6 reglas")
    assert event["actor"] == {"harness": "claude", "source": "configured"}
    assert (product(designed, ".gitattributes")).read_text(encoding="utf-8") == "progress.jsonl merge=union\n"
    assert page_data(designed.root / ".specify" / "progress" / "design.html")["activity"][0]["area_title"] == "Acceso"


def test_design_without_an_area_records_none(engine, designed, capsys):
    assert run(engine, designed, "design", "define", "in_progress") == 0
    assert "area" not in log_of(designed)[0] and log_of(designed)[0]["status"] == "in_progress"
    assert "Design of Oficio" in capsys.readouterr().out


def test_design_can_be_quiet(engine, designed, capsys):
    assert run(engine, designed, "design", "mockup", "done", "--quiet") == 0
    assert capsys.readouterr().out == "" and len(log_of(designed)) == 1


def test_design_before_there_is_a_design_records_nothing_and_says_where_to_start(engine, project, capsys):
    project.install_studio()
    assert run(engine, project, "design", "define", "in_progress") == 0
    out = capsys.readouterr()
    assert out.out.splitlines() == ["No design yet. It starts with /speckit.studio.define."] and out.err == ""
    assert not (project.root / "specs").exists()


@pytest.mark.parametrize("args", [
    ("design", "Define", "done"), ("design", "map", "finished"), ("design", "map", "note"), ("design", "map", "done", "--area", "Mis Talleres"),
    ("design", "map", "done", "--area", "a" * 61), ("design", "map"), ("design",)])
def test_design_refuses_what_is_not_a_step_a_state_or_an_area(engine, designed, args, capsys):
    with pytest.raises(SystemExit) as error:
        run(engine, designed, *args)
    assert error.value.code == 2 and log_of(designed) == []
    capsys.readouterr()


def test_a_log_that_cannot_be_written_is_reported_and_stops_nothing(engine, designed, capsys):
    product(designed, "progress.jsonl").mkdir()
    assert run(engine, designed, "design", "define", "done") == 0
    out = capsys.readouterr()
    assert "Design of Oficio" in out.out and "progress: " in out.err and "is not a file" in out.err


def test_the_design_page_opens_by_itself_the_first_time_only(engine, designed, monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(engine, "open_in_background", opened.append)
    monkeypatch.setattr(engine, "can_open_browser", lambda env=None, platform=None: True)
    monkeypatch.delenv("SPECKIT_PROGRESS_NO_BROWSER", raising=False)
    run(engine, designed, "design", "define", "in_progress")
    run(engine, designed, "design", "define", "done")
    assert opened == [(designed.root / ".specify" / "progress" / "design.html").resolve().as_uri()]
    capsys.readouterr()


# -- What /speckit.progress shows --------------------------------------------------------------


def test_show_reports_the_design_when_no_spec_is_the_current_one(engine, designed, capsys):
    assert run(engine, designed, "show") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[:3] == ["Design of Oficio", STEPS_LINE, NEXT_LINE] and lines[-1].startswith("Page: file://") and lines[-1].endswith("/design.html")
    assert "No specs yet." not in lines, "a design with no spec yet is not missing anything"


def test_show_lists_the_specs_after_the_design_when_none_is_the_current_one(engine, designed, capsys):
    designed.feature("001-login")
    designed.feature("002-logout")
    assert run(engine, designed, "show") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Design of Oficio" and lines[-2:] == ["001-login: 1 of 4 done", "002-logout: 1 of 4 done"]
    assert sum(line.startswith("Page: ") for line in lines) == 1 and "No specs yet." not in lines
    assert run(engine, designed, "show", "--design") == 0
    assert not any("001-login" in line for line in capsys.readouterr().out.splitlines()), "asked for the design, the design alone"


def test_show_reports_the_current_spec_when_there_is_one(engine, designed, capsys):
    designed.set_current(designed.feature())
    assert run(engine, designed, "show") == 0
    shown = capsys.readouterr().out
    assert "Design of Oficio" not in shown and "Login (001-login)" in shown and "001-login.html" in shown


def test_show_reports_the_design_when_asked_even_with_a_current_spec(engine, designed, capsys):
    designed.set_current(designed.feature())
    assert run(engine, designed, "show", "--design") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Design of Oficio" and lines[-1].endswith("/design.html")


def test_show_of_a_named_spec_is_about_that_spec(engine, designed, capsys):
    designed.feature()
    assert run(engine, designed, "show", "--feature", "001") == 0
    assert "Design of Oficio" not in capsys.readouterr().out


def test_show_of_a_spec_that_is_not_there_does_not_fall_back_to_the_design(engine, designed, capsys):
    designed.feature()
    assert run(engine, designed, "show", "--feature", "999") == 0
    out = capsys.readouterr()
    assert "Design of Oficio" not in out.out and "No spec named '999'" in out.err


def test_show_design_without_a_design_says_where_to_start(engine, project, capsys):
    project.feature()
    assert run(engine, project, "show", "--design") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "No design yet. It starts with /speckit.studio.define." and lines[1].startswith("Page: ") and lines[1].endswith("/index.html")


def test_show_opens_the_design_page_when_asked_to_open(engine, designed, monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(engine, "open_in_background", opened.append)
    monkeypatch.setattr(engine, "can_open_browser", lambda env=None, platform=None: True)
    monkeypatch.delenv("SPECKIT_PROGRESS_NO_BROWSER", raising=False)
    assert run(engine, designed, "show", "--open") == 0
    assert opened == [(designed.root / ".specify" / "progress" / "design.html").resolve().as_uri()]
    assert capsys.readouterr().out.splitlines()[-1] == "Opening it in your browser."


def test_the_lines_of_a_design_with_nothing_waiting_have_no_attention_line(engine, designed):
    summary = engine.design_status(designed.root)
    summary["attention"] = 0
    assert engine.design_lines(summary) == ["Design of Oficio", STEPS_LINE, NEXT_LINE]


# -- The templates -----------------------------------------------------------------------------


def test_the_design_page_names_and_colors_every_state(engine):
    page = (ROOT / "scripts" / "progress" / "design.html").read_text(encoding="utf-8")
    assert page.count("/*DATA*/null") == 1 and "default-src 'none'" in page
    for state in ("done", "active", "attention", "pending"):
        assert ".pipeline li.%s" % state in page and ".chips li.%s" % state in page
        assert "%s: \"" % state in page, "the page says in words what the state %s is" % state
    for state in ("not-started", "in-design", "drawn"):
        assert '"%s"' % state in page or "%s:" % state in page


def test_the_list_of_specs_draws_the_design_only_when_there_is_one():
    page = (ROOT / "scripts" / "progress" / "index.html").read_text(encoding="utf-8")
    assert 'if (D.design) document.getElementById("design").appendChild(design(D.design));' in page
