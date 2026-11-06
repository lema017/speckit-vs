"""What the page says about each step of the workflow and each spec."""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import SPEC, step_event, symlink, task_event

REPO = Path(__file__).resolve().parents[3]


def template(name):
    return (REPO / "templates" / name).read_text(encoding="utf-8")


def build(engine, project, directory):
    return engine.build_feature(project.root, directory, project.root / ".specify" / "progress")


def step(data, name):
    return next(item for item in data["steps"] if item["name"] == name)


def test_the_steps_are_in_workflow_order(engine, project):
    data = build(engine, project, project.feature())
    assert [item["name"] for item in data["steps"]] == ["constitution", "specify", "clarify", "plan", "checklist", "tasks", "analyze", "implement", "converge"]


# -- Constitution ----------------------------------------------------------------------------


def test_a_missing_constitution_is_not_done(engine, project):
    assert step(build(engine, project, project.feature()), "constitution")["state"] == "pending"


def test_the_untouched_constitution_template_is_not_done(engine, project):
    (project.root / ".specify" / "memory" / "constitution.md").write_text(template("constitution-template.md"), encoding="utf-8")
    item = step(build(engine, project, project.feature()), "constitution")
    assert (item["state"], item["fact"]) == ("pending", "template only")


def test_a_written_constitution_is_done(engine, project):
    (project.root / ".specify" / "memory" / "constitution.md").write_text("# Acme Constitution\n\n## Tests first\n", encoding="utf-8")
    assert step(build(engine, project, project.feature()), "constitution")["state"] == "done"


# -- Specify and clarify ---------------------------------------------------------------------


def test_no_spec_yet(engine, project):
    item = step(build(engine, project, project.feature(spec=None)), "specify")
    assert (item["state"], item["fact"]) == ("pending", "no spec")


def test_the_untouched_spec_template_is_a_draft(engine, project):
    item = step(build(engine, project, project.feature(spec=template("spec-template.md"))), "specify")
    assert item["state"] == "active"


def test_a_written_spec_counts_its_requirements(engine, project):
    spec = SPEC + "- **FR-001**: mentioned twice, counted once\n```\n- **FR-099**: in code\n```\n"
    item = step(build(engine, project, project.feature(spec=spec)), "specify")
    assert (item["state"], item["fact"]) == ("done", "2 requirements")


def test_clarify_not_run(engine, project):
    item = step(build(engine, project, project.feature()), "clarify")
    assert (item["state"], item["fact"]) == ("skipped", "not run")


def test_clarify_counts_the_answers_in_the_spec(engine, project):
    spec = SPEC + "\n## Clarifications\n\n### Session 2026-01-01\n\n- Q: How long? → A: Ten minutes\n- Q: Who? → A: Anyone\n"
    item = step(build(engine, project, project.feature(spec=spec)), "clarify")
    assert (item["state"], item["fact"]) == ("done", "2 decisions")


def test_front_matter_is_not_read_as_the_content_of_the_spec(engine, project):
    spec = "---\nnotes:\n- Q: from the header\n- **FR-900**: from the header\n---\n" + SPEC
    data = build(engine, project, project.feature(spec=spec))
    assert step(data, "clarify")["fact"] == "not run"
    assert step(data, "specify")["fact"] == "2 requirements"


def test_open_questions_need_attention_even_with_answers(engine, project):
    spec = SPEC + "\n- Q: How long? → A: Ten\n- **FR-003**: [NEEDS CLARIFICATION: which?] and [NEEDS CLARIFICATION: when?]\n"
    item = step(build(engine, project, project.feature(spec=spec)), "clarify")
    assert (item["state"], item["fact"]) == ("attention", "2 open")


def test_clarify_with_nothing_to_ask_is_done_once_logged(engine, project):
    item = step(build(engine, project, project.feature(events=[step_event(step="clarify")])), "clarify")
    assert (item["state"], item["fact"]) == ("done", "no questions")


def test_a_deep_clarify_counts_as_clarify(engine, project):
    data = build(engine, project, project.feature(events=[step_event(step="clarify-deep", actor={"harness": "claude"})]))
    assert step(data, "clarify")["who"] == "claude"


# -- Plan and checklist ----------------------------------------------------------------------


def test_no_plan_yet(engine, project):
    assert step(build(engine, project, project.feature(plan=None)), "plan")["state"] == "pending"


def test_the_untouched_plan_template_is_a_draft(engine, project):
    assert step(build(engine, project, project.feature(plan=template("plan-template.md"))), "plan")["state"] == "active"


def test_a_plan_alone(engine, project):
    item = step(build(engine, project, project.feature()), "plan")
    assert (item["state"], item["fact"]) == ("done", "plan only")


def test_a_plan_with_design_documents(engine, project):
    directory = project.feature()
    (directory / "research.md").write_text("x", encoding="utf-8")
    (directory / "contracts").mkdir()
    item = step(build(engine, project, directory), "plan")
    assert (item["state"], item["fact"], item["details"]) == ("done", "2 design docs", ["research.md", "contracts"])


def checklist_project(project, text):
    directory = project.feature()
    (directory / "checklists").mkdir()
    (directory / "checklists" / "ux.md").write_text(text, encoding="utf-8")
    return directory


def test_no_checklist(engine, project):
    assert step(build(engine, project, project.feature()), "checklist")["state"] == "skipped"


def test_an_unfinished_checklist_needs_attention(engine, project):
    item = step(build(engine, project, checklist_project(project, "- [x] CHK001 A\n- [ ] CHK002 B\n")), "checklist")
    assert (item["state"], item["fact"]) == ("attention", "1 of 2")
    assert item["details"] == ["ux.md: 1 of 2"]
    assert item["document"] == "checklists/ux.md"


def test_a_finished_checklist_is_done(engine, project):
    item = step(build(engine, project, checklist_project(project, "- [x] CHK001 A\n- [X] CHK002 B\n")), "checklist")
    assert (item["state"], item["fact"]) == ("done", "2 of 2")


# -- Tasks and after -------------------------------------------------------------------------


def test_no_tasks_yet(engine, project):
    data = build(engine, project, project.feature(tasks=None))
    assert step(data, "tasks")["state"] == "pending"
    assert step(data, "implement")["state"] == "pending"
    assert data["totals"]["total"] == 0


def test_tasks_written_and_none_started(engine, project):
    data = build(engine, project, project.feature(tasks="- [ ] T001 A\n- [ ] T002 B\n"))
    assert (step(data, "tasks")["state"], step(data, "tasks")["fact"]) == ("done", "2 tasks")
    assert (step(data, "implement")["state"], step(data, "implement")["fact"]) == ("pending", "0 of 2")


def test_counts_of_one_read_as_one(engine, project):
    spec = "# Login\n\n- **FR-001**: One rule\n\n- Q: How long? \u2192 A: Ten\n"
    directory = project.feature(spec=spec, tasks="- [ ] T001 A\n")
    (directory / "research.md").write_text("x", encoding="utf-8")
    data = build(engine, project, directory)
    assert step(data, "specify")["fact"] == "1 requirement"
    assert step(data, "clarify")["fact"] == "1 decision"
    assert step(data, "plan")["fact"] == "1 design doc"
    assert step(data, "tasks")["fact"] == "1 task"


def test_implementing(engine, project):
    data = build(engine, project, project.feature(tasks="- [x] T001 A\n- [ ] T002 B\n"))
    assert (step(data, "implement")["state"], step(data, "implement")["fact"]) == ("active", "1 of 2")


def test_implementing_with_work_in_progress_but_nothing_finished(engine, project):
    data = build(engine, project, project.feature(tasks="- [ ] T001 A\n", events=[task_event(status="in_progress")]))
    assert step(data, "implement")["state"] == "active"


def test_implementing_once_the_step_itself_has_started(engine, project):
    data = build(engine, project, project.feature(tasks="- [ ] T001 A\n", events=[step_event(step="implement", status="in_progress")]))
    assert step(data, "implement")["state"] == "active"


def test_implemented(engine, project):
    data = build(engine, project, project.feature(tasks="- [x] T001 A\n"))
    assert step(data, "implement")["state"] == "done"


def test_analyze_leaves_no_file_so_only_the_log_can_tell(engine, project):
    assert step(build(engine, project, project.feature()), "analyze")["state"] == "skipped"


def test_analyze_logged(engine, project):
    assert step(build(engine, project, project.feature(events=[step_event(step="analyze")])), "analyze")["state"] == "done"


def test_converge_added_tasks(engine, project):
    data = build(engine, project, project.feature(tasks="## Phase 2: Convergence\n- [ ] T001 A\n"))
    assert (step(data, "converge")["state"], step(data, "converge")["fact"]) == ("done", "added tasks")


def test_converge_found_nothing(engine, project):
    data = build(engine, project, project.feature(events=[step_event(step="converge")]))
    assert (step(data, "converge")["state"], step(data, "converge")["fact"]) == ("done", "no new tasks")


def test_converge_not_run(engine, project):
    assert step(build(engine, project, project.feature()), "converge")["state"] == "pending"


# -- What the log adds to a step -------------------------------------------------------------


def test_a_step_says_who_ran_it_and_what_they_noted(engine, project):
    actor = {"harness": "codex", "agent": "reviewer", "source": "observed"}
    item = step(build(engine, project, project.feature(events=[step_event(step="analyze", actor=actor, note="All good")])), "analyze")
    assert (item["who"], item["note"]) == ("codex/reviewer", "All good")


def test_a_step_in_progress_shows_as_active(engine, project):
    item = step(build(engine, project, project.feature(events=[step_event(step="analyze", status="in_progress")])), "analyze")
    assert item["state"] == "active"


def test_a_step_that_failed_needs_attention(engine, project):
    item = step(build(engine, project, project.feature(events=[step_event(step="plan", status="failed")])), "plan")
    assert item["state"] == "attention"


def test_the_last_report_of_a_step_is_the_one_shown(engine, project):
    events = [step_event(step="analyze", status="failed"), step_event(step="analyze", status="done", note="fixed")]
    item = step(build(engine, project, project.feature(events=events)), "analyze")
    assert (item["state"], item["note"]) == ("done", "fixed")


@pytest.mark.parametrize("name", ["clarify", "analyze", "converge"])
def test_a_step_with_no_file_is_not_done_until_it_says_so(engine, project, name):
    item = step(build(engine, project, project.feature(events=[step_event(step=name, status="in_progress")])), name)
    assert item["state"] == "active"
    other = project.feature("002-other", events=[step_event(step=name, status="note", note="thinking")])
    assert step(build(engine, project, other), name)["state"] != "done"


def test_a_note_after_the_step_finished_changes_nothing_but_the_note(engine, project):
    events = [step_event(step="analyze", status="done", actor={"harness": "claude"}), step_event(step="analyze", status="note", note="One more thing", actor={"harness": "codex"})]
    item = step(build(engine, project, project.feature(events=events)), "analyze")
    assert (item["state"], item["note"], item["who"]) == ("done", "One more thing", "codex")


def test_the_last_note_survives_a_report_without_one(engine, project):
    events = [step_event(step="analyze", status="failed", note="Bad"), step_event(step="analyze", status="done")]
    item = step(build(engine, project, project.feature(events=events)), "analyze")
    assert (item["state"], item["note"]) == ("done", "Bad")


def test_files_outrank_the_log_for_a_step_that_is_done(engine, project):
    item = step(build(engine, project, project.feature(events=[step_event(step="plan", status="in_progress")])), "plan")
    assert item["state"] == "done"


# -- Totals, attention and agents ------------------------------------------------------------


def test_totals_add_up(engine, project):
    tasks = "- [x] T001 A\n- [ ] T002 B\n- [ ] T003 C\n- [ ] T004 D\n- [ ] T005 E\n- [ ] T006 F\n"
    events = [task_event("T002", "in_progress"), task_event("T003", "blocked"), task_event("T004", "failed"), task_event("T005", "skipped")]
    totals = build(engine, project, project.feature(tasks=tasks, events=events))["totals"]
    assert totals == {"total": 6, "done": 1, "in_progress": 1, "blocked": 1, "failed": 1, "skipped": 1, "pending": 1}


def attention_of(engine, project, **kwargs):
    return build(engine, project, project.feature(**kwargs))["attention"]


def test_nothing_to_attend_to(engine, project):
    assert attention_of(engine, project, tasks="- [ ] T001 A\n- [x] T002 B\n") == []


def test_a_contradiction_needs_attention(engine, project):
    items = attention_of(engine, project, tasks="- [ ] T001 A\n", events=[task_event(status="done")])
    assert [item["task"] for item in items] == ["T001"]
    assert "box in tasks.md is empty" in items[0]["text"]


@pytest.mark.parametrize("status", ["blocked", "failed"])
def test_a_stopped_task_says_why(engine, project, status):
    items = attention_of(engine, project, tasks="- [ ] T001 A\n", events=[task_event(status=status, note="No access")])
    assert items == [{"task": "T001", "text": status.capitalize() + ": No access"}]


def test_a_stopped_task_with_no_reason(engine, project):
    items = attention_of(engine, project, tasks="- [ ] T001 A\n", events=[task_event(status="blocked")])
    assert items == [{"task": "T001", "text": "Blocked."}]


def test_a_changed_task_says_its_history_is_older(engine, project):
    items = attention_of(engine, project, tasks="- [ ] T001 A\n", events=[task_event(status="done", text_sha="other")])
    assert len(items) == 1 and "earlier version" in items[0]["text"]


def test_a_repeated_id_needs_attention(engine, project):
    items = attention_of(engine, project, tasks="- [ ] T001 A\n- [ ] T001 B\n")
    assert items == [{"task": "T001", "text": "This ID appears more than once in tasks.md."}]


def test_uncounted_lines_are_reported_with_their_number(engine, project):
    items = attention_of(engine, project, tasks="- [ ] T001 A\n- [ ] no id\n- [ ] no id either\n")
    assert items == [{"task": None, "text": "2 checkbox lines in tasks.md not counted, because the task format is not followed."}]


def test_unreadable_log_lines_are_reported(engine, project):
    items = attention_of(engine, project, events=["{oops"])
    assert items == [{"task": None, "text": "1 line of the progress log could not be read."}]


def test_cut_files_are_reported(engine, project, monkeypatch):
    directory = project.feature(tasks="- [ ] T001 A\n" * 5, events=[task_event(task="T%03d" % n) for n in range(1, 9)])
    monkeypatch.setattr(engine, "MAX_TASKS_BYTES", 20)
    monkeypatch.setattr(engine, "MAX_LOG_BYTES", 100)
    texts = [item["text"] for item in build(engine, project, directory)["attention"]]
    assert "tasks.md is too large: only its first part was read." in texts
    assert "The progress log is too large: only its first part was read." in texts


def test_a_task_file_that_is_a_link_is_refused_and_reported(engine, project, tmp_path):
    directory = project.feature(tasks=None)
    outside = tmp_path / "outside.md"
    outside.write_text("- [ ] T001 From outside\n", encoding="utf-8")
    symlink((directory / "tasks.md"), outside)
    data = build(engine, project, directory)
    assert data["totals"]["total"] == 0
    assert data["attention"] == [{"task": None, "text": "tasks.md is a symbolic link, so it was not read."}]


def test_agents_show_their_work_and_what_they_are_on(engine, project):
    tasks = "- [x] T001 A\n- [x] T002 B\n- [ ] T003 C\n- [ ] T004 D\n- [x] T005 E\n- [ ] T006 F\n"
    claude = {"harness": "claude", "source": "observed"}
    codex = {"harness": "codex"}
    events = [
        task_event("T001", "done", actor=claude),
        task_event("T002", "done", actor=codex),
        task_event("T003", "in_progress", actor=claude),
        task_event("T004", "blocked", actor=codex),
    ]
    agents = build(engine, project, project.feature(tasks=tasks, events=events))["agents"]
    assert agents == [
        {"label": "No record", "source": None, "done": 1, "active": []},
        {"label": "claude", "source": "observed", "done": 1, "active": ["T003"]},
        {"label": "codex", "source": "declared", "done": 1, "active": ["T004"]},
    ]


def test_an_agent_that_only_failed_is_not_listed_as_working(engine, project):
    agents = build(engine, project, project.feature(tasks="- [ ] T001 A\n", events=[task_event(status="failed", actor={"harness": "codex"})]))["agents"]
    assert agents == []


def test_activity_is_newest_first_and_bounded(engine, project, monkeypatch):
    monkeypatch.setattr(engine, "ACTIVITY_LIMIT", 2)
    data = build(engine, project, project.feature(events=[task_event("T001"), task_event("T002"), task_event("T003")]))
    assert [event["task"] for event in data["activity"]] == ["T003", "T002"]


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("# Feature Specification: Login\n", "Login"),
        ("# Specification: Login\n", "Login"),
        ("# Login ##\n", "Login"),
        ("---\nx: y\n---\n# Login\n", "Login"),
        ("# Feature Specification: [FEATURE NAME]\n", "001-login"),
        ("## Only a subheading\n", "001-login"),
        (None, "001-login"),
    ],
)
def test_the_title_comes_from_the_spec_or_the_folder(engine, project, spec, expected):
    assert build(engine, project, project.feature(spec=spec))["title"] == expected
