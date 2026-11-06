"""How the progress engine reads progress.jsonl and crosses it with tasks.md."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from .conftest import step_event, symlink, task_event

NOW = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)


def a_task(checked=False, text="Add the form", task_id="T001"):
    return {"id": task_id, "checked": checked, "text": text, "parallel": False, "story": None, "tags": [], "line": 3, "section": None}


def crossed(engine, events, checked=False, text="Add the form"):
    return engine.reconcile_task(a_task(checked, text), [engine.clean_event(event) for event in events])


# -- One line of the log ---------------------------------------------------------------------


def test_a_good_task_event_keeps_its_fields(engine):
    event = engine.clean_event(
        task_event(
            status="done",
            note="ok",
            files=["a.py", "b.py"],
            text_sha="abc",
            actor={"harness": "claude", "agent": "main", "session": "s1", "source": "observed"},
        )
    )
    assert event == {
        "kind": "task",
        "status": "done",
        "task": "T001",
        "ts": "2026-01-02T03:04:05Z",
        "note": "ok",
        "files": ["a.py", "b.py"],
        "text_sha": "abc",
        "actor": {"harness": "claude", "agent": "main", "session": "s1", "source": "observed"},
    }


def test_a_good_step_event_is_kept(engine):
    event = engine.clean_event(step_event(step="analyze", status="done"))
    assert (event["kind"], event["step"], event["status"]) == ("step", "analyze", "done")


def test_clarify_deep_counts_as_the_clarify_step(engine):
    assert engine.clean_event(step_event(step="clarify-deep"))["step"] == "clarify"


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "text",
        3,
        [],
        {},
        {"kind": "task"},
        {"kind": "other", "task": "T001", "status": "done"},
        task_event(status="finished"),
        task_event(status=None),
        task_event(task="1"),
        task_event(task="T1a"),
        task_event(task=7),
        task_event(task=None),
        task_event(v=2),
        task_event(v="1"),
        task_event(v=True),
        step_event(status="blocked"),
        step_event(step="Bad Name"),
        step_event(step=""),
        step_event(step=7),
    ],
)
def test_a_line_that_cannot_be_understood_is_dropped(engine, bad):
    assert engine.clean_event(bad) is None


def test_a_line_without_a_version_is_read_as_the_current_one(engine):
    event = task_event()
    del event["v"]
    assert engine.clean_event(event)["task"] == "T001"


def test_an_older_version_is_still_read(engine):
    assert engine.clean_event(task_event(v=0)) is not None


def test_long_fields_are_cut(engine):
    event = engine.clean_event(
        task_event(
            note="n" * (engine.MAX_NOTE_CHARS + 5),
            files=["f" * (engine.MAX_FILE_NAME_CHARS + 5)] + ["g"] * (engine.MAX_FILES_PER_EVENT + 5),
            text_sha="s" * 100,
            actor={"harness": "h" * (engine.MAX_FIELD_CHARS + 5)},
        )
    )
    assert len(event["note"]) == engine.MAX_NOTE_CHARS
    assert len(event["files"]) == engine.MAX_FILES_PER_EVENT
    assert len(event["files"][0]) == engine.MAX_FILE_NAME_CHARS
    assert len(event["text_sha"]) == 64
    assert len(event["actor"]["harness"]) == engine.MAX_FIELD_CHARS


@pytest.mark.parametrize(
    "fields",
    [
        {"note": 3},
        {"note": ""},
        {"note": ["x"]},
        {"files": "a.py"},
        {"files": [1, None, ""]},
        {"text_sha": 5},
        {"actor": "claude"},
        {"actor": {}},
        {"actor": {"harness": 3}},
    ],
)
def test_fields_of_the_wrong_type_are_ignored_and_the_event_survives(engine, fields):
    event = engine.clean_event(task_event(**fields))
    assert event is not None
    assert set(event) <= {"kind", "status", "task", "ts"}


def test_an_unknown_source_is_treated_as_declared_by_the_agent(engine):
    assert engine.clean_event(task_event(actor={"harness": "x", "source": "trust me"}))["actor"]["source"] == "declared"
    assert engine.clean_event(task_event(actor={"harness": "x"}))["actor"]["source"] == "declared"
    assert engine.clean_event(task_event(actor={"harness": "x", "source": "observed"}))["actor"]["source"] == "observed"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-01-02T03:04:05Z", "2026-01-02T03:04:05Z"),
        ("2026-01-02T03:04:05z", "2026-01-02T03:04:05Z"),
        ("2026-01-02T05:04:05+02:00", "2026-01-02T03:04:05Z"),
        ("2026-01-02T03:04:05", "2026-01-02T03:04:05Z"),
        ("yesterday", None),
        (7, None),
        ("", None),
        (None, None),
    ],
)
def test_times_are_normalized_or_dropped(engine, raw, expected):
    assert engine.clean_event(task_event(ts=raw))["ts"] == expected


# -- The whole file --------------------------------------------------------------------------


def test_a_broken_line_is_counted_and_the_rest_still_read(engine, project):
    directory = project.feature(events=[task_event(), "{not json", task_event(status="made up"), "", task_event(task="T002")])
    events, bad, truncated = engine.read_events(directory / "progress.jsonl")
    assert [event["task"] for event in events] == ["T001", "T002"]
    assert (bad, truncated) == (2, False)


def test_no_log_is_not_an_error(engine, project):
    directory = project.feature()
    assert engine.read_events(directory / "progress.jsonl") == ([], 0, False)


def test_a_log_over_the_limit_drops_its_half_line(engine, project, monkeypatch):
    directory = project.feature(events=[task_event(task="T%03d" % number) for number in range(1, 20)])
    size = len((directory / "progress.jsonl").read_bytes())
    monkeypatch.setattr(engine, "MAX_LOG_BYTES", size - 5)
    events, bad, truncated = engine.read_events(directory / "progress.jsonl")
    assert (bad, truncated) == (0, True)
    assert len(events) == 18


def test_a_log_that_is_a_link_is_not_followed(engine, project, tmp_path):
    directory = project.feature()
    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"kind":"task","task":"T001","status":"done"}\n', encoding="utf-8")
    symlink((directory / "progress.jsonl"), outside)
    assert engine.read_events(directory / "progress.jsonl") == ([], 0, False)


# -- tasks.md decides, the log explains ------------------------------------------------------


@pytest.mark.parametrize(
    ("checked", "statuses", "expected", "has_problem"),
    [
        (True, ["done"], "done", False),
        (True, [], "done", False),
        (False, [], "pending", False),
        (False, ["done"], "pending", True),
        (False, ["in_progress"], "in_progress", False),
        (False, ["blocked"], "blocked", False),
        (False, ["failed"], "failed", False),
        (False, ["skipped"], "skipped", False),
        (False, ["note"], "pending", False),
        (True, ["failed"], "done", True),
        (True, ["blocked"], "done", True),
        (True, ["in_progress"], "done", False),
        (True, ["note"], "done", False),
        (False, ["in_progress", "blocked"], "blocked", False),
        (False, ["in_progress", "done"], "pending", True),
        (False, ["done", "in_progress"], "in_progress", False),
        (False, ["failed", "note"], "failed", False),
        (True, ["failed", "done"], "done", False),
    ],
)
def test_the_table_of_box_and_report(engine, checked, statuses, expected, has_problem):
    view = crossed(engine, [task_event(status=status) for status in statuses], checked=checked)
    assert view["status"] == expected
    assert bool(view["problem"]) is has_problem


def test_a_checked_task_with_no_report_says_nobody_recorded_it(engine):
    assert crossed(engine, [], checked=True)["no_record"] is True
    assert crossed(engine, [task_event()], checked=True)["no_record"] is False
    assert crossed(engine, [], checked=False)["no_record"] is False


def test_reports_about_an_older_text_do_not_decide_the_state(engine):
    old = engine.task_text_sha("The old text")
    view = crossed(engine, [task_event(status="done", text_sha=old, note="old note", files=["old.py"])])
    assert view["status"] == "pending"
    assert view["problem"] is None
    assert view["notes"] == []
    assert view["files"] == []
    assert len(view["older_history"]) == 1


def test_reports_about_the_current_text_count(engine):
    same = engine.task_text_sha("Add   the\tform")
    view = crossed(engine, [task_event(status="blocked", text_sha=same)])
    assert view["status"] == "blocked"
    assert view["older_history"] == []


def test_a_report_without_a_fingerprint_counts(engine):
    assert crossed(engine, [task_event(status="blocked")])["status"] == "blocked"


def test_the_author_is_whoever_reported_the_last_state(engine):
    first = {"harness": "claude", "source": "observed"}
    second = {"harness": "codex", "source": "declared"}
    third = {"harness": "gemini", "source": "declared"}
    view = crossed(
        engine,
        [
            task_event(status="in_progress", actor=first),
            task_event(status="done", actor=second),
            task_event(status="note", note="later", actor=third),
        ],
        checked=True,
    )
    assert view["actor"]["harness"] == "codex"
    assert view["who"] == "codex"


def test_a_note_names_the_author_when_nobody_reported_a_state(engine):
    view = crossed(engine, [task_event(status="note", note="x", actor={"harness": "codex"})])
    assert view["who"] == "codex"


def test_no_report_means_no_author(engine):
    view = crossed(engine, [])
    assert (view["actor"], view["who"]) == (None, None)


def test_files_are_listed_once_in_the_order_they_appeared(engine):
    view = crossed(engine, [task_event(status="in_progress", files=["b.py", "a.py"]), task_event(status="done", files=["a.py", "c.py"])], checked=True)
    assert view["files"] == ["b.py", "a.py", "c.py"]


def test_notes_and_history_stay_apart(engine):
    view = crossed(engine, [task_event(status="in_progress"), task_event(status="note", note="hello"), task_event(status="done", note="finished")], checked=True)
    assert [event["note"] for event in view["notes"]] == ["hello", "finished"]
    assert [event["status"] for event in view["history"]] == ["in_progress", "done"]


@pytest.mark.parametrize(
    ("actor", "expected"),
    [
        (None, None),
        ({"harness": "claude"}, "claude"),
        ({"harness": "claude", "agent": "main"}, "claude"),
        ({"harness": "claude", "agent": "reviewer"}, "claude/reviewer"),
        ({"agent": "reviewer"}, "unknown/reviewer"),
    ],
)
def test_the_name_shown_for_an_agent(engine, actor, expected):
    assert engine.actor_label(actor) == expected


def test_the_fingerprint_ignores_spacing_only(engine):
    assert engine.task_text_sha("a  b") == engine.task_text_sha(" a\tb ")
    assert engine.task_text_sha("a b") != engine.task_text_sha("a c")


# -- A task nobody finished ------------------------------------------------------------------


def working(last_ts, status="in_progress"):
    return {"status": status, "last_ts": last_ts}


def stamp(**ago):
    return (NOW - timedelta(**ago)).isoformat().replace("+00:00", "Z")


def test_recent_work_is_not_abandoned(engine):
    assert engine.is_abandoned(working(stamp(minutes=5)), NOW) is False
    assert engine.is_abandoned(working(stamp(seconds=engine.ABANDONED_AFTER_SECONDS)), NOW) is False


def test_old_work_is_possibly_abandoned(engine):
    assert engine.is_abandoned(working(stamp(seconds=engine.ABANDONED_AFTER_SECONDS + 1)), NOW) is True


def test_work_of_unknown_age_is_possibly_abandoned(engine):
    assert engine.is_abandoned(working(None), NOW) is True
    assert engine.is_abandoned(working("not a time"), NOW) is True


@pytest.mark.parametrize("status", ["done", "blocked", "failed", "pending", "skipped"])
def test_only_work_in_progress_can_be_abandoned(engine, status):
    assert engine.is_abandoned(working(stamp(days=30), status), NOW) is False
