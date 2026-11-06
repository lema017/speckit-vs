"""The calls a model makes during /speckit.implement: start, done, block, fail, skip, note."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time

import pytest

from specify_cli.progress import _engine as engine_module

from .conftest import symlink

EIGHT = "# Tasks\n\n## Phase 1\n\n" + "".join("- [ ] T%03d Task number %d\n" % (n, n) for n in range(1, 9))


def read_log(directory):
    path = directory / "progress.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def tasks_bytes(directory):
    return (directory / "tasks.md").read_bytes()


@pytest.fixture
def current(project):
    directory = project.feature(tasks=EIGHT)
    project.set_current(directory)
    return directory


@pytest.fixture
def run(project, engine, capsys, monkeypatch):
    monkeypatch.setenv("SPECKIT_PROGRESS_NO_BROWSER", "1")

    def call(*arguments):
        code = engine.main(["--root", str(project.root), "--harness", "claude", *arguments])
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return call


def nothing_changed(directory, before):
    assert tasks_bytes(directory) == before
    assert not (directory / "progress.jsonl").exists()


# -- Each command ------------------------------------------------------------------------------


def test_start_records_the_task_and_leaves_the_box_alone(run, current, engine):
    before = tasks_bytes(current)
    code, out, err = run("start", "T003")
    assert (code, err) == (0, "")
    assert out == "T003 started. 0 of 8 tasks done.\n"
    assert tasks_bytes(current) == before
    event = read_log(current)[0]
    assert event["kind"] == "task"
    assert event["task"] == "T003"
    assert event["status"] == "in_progress"
    assert event["text_sha"] == engine.task_text_sha("Task number 3")
    assert event["actor"] == {"harness": "claude", "source": "configured"}
    assert event["ts"].endswith("Z")
    assert engine.clean_event(event) is not None


def test_done_checks_the_box_and_records_what_it_was_told(run, current):
    code, out, err = run("done", "T002", "--note", "Reused the route", "--files", "src/a.py,src/b.py")
    assert (code, err) == (0, "")
    assert out == "T002 done. 1 of 8 tasks done.\n"
    assert b"- [X] T002 Task number 2\n" in tasks_bytes(current)
    assert tasks_bytes(current).count(b"[X]") == 1
    event = read_log(current)[0]
    assert event["status"] == "done"
    assert event["note"] == "Reused the route"
    assert event["files"] == ["src/a.py", "src/b.py"]


def test_files_can_come_separated_by_spaces_or_commas_and_in_several_options(run, current):
    assert run("done", "T002", "--files", "a.py", "b.py", "--files", "c.py,d.py")[0] == 0
    assert read_log(current)[0]["files"] == ["a.py", "b.py", "c.py", "d.py"]


def test_then_closes_one_task_and_opens_the_next_in_one_call(run, current, engine):
    code, out, _ = run("done", "T001", "--then", "T002")
    assert code == 0
    assert out == "T001 done. T002 started. 1 of 8 tasks done.\n"
    assert [(e["task"], e["status"]) for e in read_log(current)] == [("T001", "done"), ("T002", "in_progress")]
    assert read_log(current)[1]["text_sha"] == engine.task_text_sha("Task number 2")
    assert b"- [ ] T002" in tasks_bytes(current)


def test_the_note_stays_on_the_task_that_closed_not_on_the_next(run, current):
    run("done", "T001", "--note", "Only about one", "--files", "a.py", "--then", "T002")
    following = read_log(current)[1]
    assert "note" not in following
    assert "files" not in following


@pytest.mark.parametrize(("command", "status"), [("block", "blocked"), ("fail", "failed"), ("skip", "skipped")])
def test_a_task_that_stops_records_why_and_keeps_its_box_empty(run, current, command, status):
    before = tasks_bytes(current)
    code, out, err = run(command, "T004", "--reason", "Because of T003")
    assert (code, err) == (0, "")
    assert out.startswith("T004 %s." % status)
    assert tasks_bytes(current) == before
    event = read_log(current)[0]
    assert (event["status"], event["note"]) == (status, "Because of T003")


def test_note_takes_its_words_with_or_without_quotes(run, current):
    run("note", "T001", "Using the existing route")
    run("note", "T001", "Using", "several", "words")
    notes = [e["note"] for e in read_log(current)]
    assert notes == ["Using the existing route", "Using several words"]
    assert all(e["status"] == "note" for e in read_log(current))


def test_the_page_reads_what_was_recorded(run, current, project, engine):
    run("start", "T001")
    run("done", "T002", "--note", "Fine")
    run("block", "T003", "--reason", "Waiting")
    run("fail", "T004", "--reason", "Broken")
    run("skip", "T005", "--reason", "Dropped")
    run("note", "T006", "Just a thought")
    row = engine.status_data(project.root, current)[0]
    assert row["totals"]["done"] == 1
    assert row["totals"]["in_progress"] == 1
    assert row["totals"]["blocked"] == 1
    assert row["totals"]["failed"] == 1
    assert row["totals"]["skipped"] == 1
    assert row["totals"]["pending"] == 3
    page = (project.root / ".specify" / "progress" / "001-login.html").read_text(encoding="utf-8")
    assert "Just a thought" in page


def test_every_call_redraws_the_page(run, current, project):
    run("start", "T001")
    page = project.root / ".specify" / "progress" / "001-login.html"
    first = page.read_text(encoding="utf-8")
    run("done", "T001")
    assert page.read_text(encoding="utf-8") != first


def test_the_first_call_opens_the_page_once_like_a_step_does(project, current, engine, monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "open_in_background", calls.append)
    monkeypatch.setattr(engine, "can_open_browser", lambda env=None: True)
    monkeypatch.delenv("SPECKIT_PROGRESS_NO_BROWSER", raising=False)
    assert engine.main(["--root", str(project.root), "start", "T001"]) == 0
    assert engine.main(["--root", str(project.root), "done", "T001"]) == 0
    assert len(calls) == 1
    assert calls[0].endswith("/.specify/progress/001-login.html")


def test_it_reports_one_line_because_a_model_reads_every_word(run, current):
    _, out, _ = run("done", "T001", "--note", "Note text stays out", "--then", "T002")
    assert out.count("\n") == 1
    assert "Note text" not in out


def test_a_task_named_by_feature_goes_to_that_spec(project, run, current):
    other = project.feature(name="002-other", tasks="## P\n\n- [ ] T001 Other\n")
    code, _, _ = run("done", "T001", "--feature", "002")
    assert code == 0
    assert b"[X] T001 Other" in tasks_bytes(other)
    assert not read_log(current)


# -- Who did it --------------------------------------------------------------------------------


def test_a_name_the_model_gives_is_labelled_as_declared(run, current, project, engine):
    run("start", "T001", "--agent", "backend-1")
    assert read_log(current)[0]["actor"] == {"harness": "claude", "agent": "backend-1", "source": "declared"}
    row = engine.status_data(project.root, current)[0]
    assert row["active"][0]["who"] == "claude/backend-1"


def test_then_carries_the_agent_to_the_next_task(run, current):
    run("done", "T001", "--agent", "backend-1", "--then", "T002")
    assert read_log(current)[1]["actor"]["agent"] == "backend-1"


def test_a_blank_agent_counts_as_none(run, current):
    run("start", "T001", "--agent", "  ")
    assert read_log(current)[0]["actor"] == {"harness": "claude", "source": "configured"}


def test_an_agent_name_cannot_carry_control_characters(engine):
    assert engine.make_actor("claude", "a\x1b[31mb")["agent"] == "a [31mb"


def test_with_no_harness_and_no_agent_there_is_no_actor(project, current, engine, capsys):
    assert engine.main(["--root", str(project.root), "start", "T001"]) == 0
    assert "actor" not in read_log(current)[0]


# -- What it refuses ---------------------------------------------------------------------------


def test_an_unknown_id_lists_the_valid_ones_and_writes_nothing(run, current):
    before = tasks_bytes(current)
    code, out, err = run("done", "T099")
    assert (code, out) == (1, "")
    assert "T099 is not in tasks.md" in err
    assert "T001 T002 T003 T004 T005 T006 T007 T008" in err
    assert "nothing was recorded for T099" in err
    nothing_changed(current, before)


@pytest.mark.parametrize("name", ["t001", "1", "../../etc", "T001 T002", ""])
def test_anything_that_is_not_an_id_is_refused_the_same_way(run, current, name):
    before = tasks_bytes(current)
    code, _, err = run("start", name)
    assert code == 1
    assert "Valid ids" in err
    nothing_changed(current, before)


def test_the_list_of_ids_has_a_limit(project, run):
    many = "## P\n\n" + "".join("- [ ] T%04d x\n" % n for n in range(1, 151))
    project.set_current(project.feature(tasks=many))
    _, _, err = run("start", "T9999")
    assert "T0100 and 50 more" in err
    assert "T0101" not in err


def test_an_unknown_next_task_writes_nothing_at_all(run, current):
    before = tasks_bytes(current)
    code, _, err = run("done", "T001", "--then", "T099")
    assert code == 1
    assert "T099" in err
    nothing_changed(current, before)


def test_then_cannot_name_the_same_task(project, engine, current, capsys):
    before = tasks_bytes(current)
    with pytest.raises(SystemExit) as stop:
        engine.main(["--root", str(project.root), "done", "T001", "--then", "T001"])
    assert stop.value.code == 2
    nothing_changed(current, before)


@pytest.mark.parametrize(
    "arguments",
    [
        ["block", "T001"],
        ["fail", "T001"],
        ["skip", "T001"],
        ["block", "T001", "--reason", "  "],
        ["fail", "T001", "--reason", ""],
        ["note", "T001"],
        ["note", "T001", "  "],
        ["start"],
        ["done"],
        ["start", "T001", "--then", "T002"],
        ["block", "T001", "--reason", "x", "--then", "T002"],
    ],
)
def test_a_call_written_wrong_is_a_usage_error_and_writes_nothing(project, engine, current, capsys, arguments):
    before = tasks_bytes(current)
    with pytest.raises(SystemExit) as stop:
        engine.main(["--root", str(project.root), *arguments])
    assert stop.value.code == 2
    nothing_changed(current, before)


def test_a_repeated_id_is_refused_because_no_one_can_tell_which_box(project, run):
    directory = project.feature(tasks="## P\n\n- [ ] T001 One\n- [ ] T001 Another\n")
    project.set_current(directory)
    before = tasks_bytes(directory)
    code, _, err = run("done", "T001")
    assert code == 1
    assert "T001 appears 2 times" in err
    assert "lines 3, 4" in err
    nothing_changed(directory, before)


def test_an_id_inside_a_code_block_is_not_a_task(project, run):
    directory = project.feature(tasks="## P\n\n```\n- [ ] T001 Example\n```\n\n- [ ] T002 Real\n")
    project.set_current(directory)
    before = tasks_bytes(directory)
    assert run("done", "T001")[0] == 1
    nothing_changed(directory, before)


def test_without_a_current_spec_it_says_so(project, run):
    project.feature()
    code, _, err = run("start", "T001")
    assert code == 1
    assert "no current spec" in err


def test_a_spec_named_by_feature_has_to_exist(project, run, current):
    code, _, err = run("start", "T001", "--feature", "999")
    assert code == 1
    assert "nothing was recorded" in err


def test_without_a_task_list_it_says_so(project, run):
    directory = project.feature(tasks=None)
    project.set_current(directory)
    code, _, err = run("start", "T001")
    assert code == 1
    assert "does not exist yet" in err


def test_a_project_without_spec_kit_is_refused(tmp_path, engine, capsys):
    (tmp_path / "specs" / "001-x").mkdir(parents=True)
    (tmp_path / "specs" / "001-x" / "tasks.md").write_text("- [ ] T001 x\n", encoding="utf-8")
    assert engine.main(["--root", str(tmp_path), "start", "T001"]) == 1
    assert "progress:" in capsys.readouterr().err


def test_a_linked_task_list_is_refused(project, run, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("- [ ] T001 Secret\n", encoding="utf-8")
    directory = project.feature(tasks=None)
    project.set_current(directory)
    symlink(directory / "tasks.md", outside)
    code, _, err = run("done", "T001")
    assert code == 1
    assert "symbolic link" in err
    assert outside.read_text(encoding="utf-8") == "- [ ] T001 Secret\n"
    assert not (directory / "progress.jsonl").exists()


def test_a_task_list_too_large_to_read_whole_is_refused(project, run, engine, monkeypatch):
    directory = project.feature(tasks="- [ ] T001 x\n" + "y" * 200)
    project.set_current(directory)
    monkeypatch.setattr(engine, "MAX_TASKS_BYTES", 100)
    before = tasks_bytes(directory)
    code, _, err = run("done", "T001")
    assert code == 1
    assert "is over 100 bytes" in err
    nothing_changed(directory, before)


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="needs file permissions")
def test_a_read_only_task_list_is_not_replaced_behind_its_back(run, current):
    path = current / "tasks.md"
    path.chmod(0o444)
    before = tasks_bytes(current)
    code, _, err = run("done", "T001")
    assert code == 1
    assert "read-only" in err
    nothing_changed(current, before)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_the_task_list_keeps_its_permissions(run, current):
    path = current / "tasks.md"
    path.chmod(0o600)
    assert run("done", "T001")[0] == 0
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


# -- When only part of it works ----------------------------------------------------------------


def test_a_box_that_is_marked_counts_even_if_the_log_cannot_be_written(run, current, tmp_path):
    outside = tmp_path / "outside.jsonl"
    outside.write_text("", encoding="utf-8")
    symlink(current / "progress.jsonl", outside)
    code, out, err = run("done", "T001")
    assert code == 0
    assert out.startswith("T001 done.")
    assert "symbolic link" in err
    assert b"[X] T001" in tasks_bytes(current)
    assert outside.read_text(encoding="utf-8") == ""


def test_a_start_that_cannot_be_written_is_a_failure(run, current, tmp_path):
    outside = tmp_path / "outside.jsonl"
    outside.write_text("", encoding="utf-8")
    symlink(current / "progress.jsonl", outside)
    code, out, err = run("start", "T001")
    assert (code, out) == (1, "")
    assert "nothing was recorded" in err


def test_a_page_that_cannot_be_drawn_does_not_undo_the_work(run, current, engine, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(engine, "render_project", broken)
    code, out, err = run("done", "T001")
    assert code == 0
    assert out == "T001 done.\n"
    assert "disk full" in err
    assert b"[X] T001" in tasks_bytes(current)
    assert read_log(current)[0]["status"] == "done"


def test_something_unexpected_is_reported_as_a_failure(run, current, engine, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(engine, "parse_tasks", broken)
    code, _, err = run("start", "T001")
    assert code == 1
    assert "unexpected RuntimeError: boom" in err


def test_a_box_already_checked_is_left_as_it_was_and_the_call_still_counts(project, run):
    directory = project.feature(tasks="## P\n\n- [x] T001 Lowercase\n")
    project.set_current(directory)
    before = (directory / "tasks.md").stat().st_mtime_ns
    assert run("done", "T001", "--note", "Second look")[0] == 0
    assert (directory / "tasks.md").stat().st_mtime_ns == before
    assert tasks_bytes(directory) == b"## P\n\n- [x] T001 Lowercase\n"
    assert read_log(directory)[0]["note"] == "Second look"


@pytest.mark.parametrize(
    ("command", "extra"),
    [("start", []), ("block", ["--reason", "x"]), ("fail", ["--reason", "x"]), ("skip", ["--reason", "x"])],
)
def test_reopening_a_checked_task_says_the_box_still_decides(project, run, command, extra):
    directory = project.feature(tasks="## P\n\n- [X] T001 Done\n")
    project.set_current(directory)
    code, out, _ = run(command, "T001", *extra)
    assert code == 0
    assert "T001 is still checked in tasks.md" in out


@pytest.mark.parametrize(("command", "extra"), [("done", []), ("note", ["text"])])
def test_closing_or_noting_a_checked_task_needs_no_warning(project, run, command, extra):
    directory = project.feature(tasks="## P\n\n- [X] T001 Done\n")
    project.set_current(directory)
    assert "still checked" not in run(command, "T001", *extra)[1]


# -- The rest of tasks.md stays byte for byte --------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (b"## P\n\n- [ ] T001 x\n- [ ] T002 y\n", b"## P\n\n- [ ] T001 x\n- [X] T002 y\n"),
        (b"## P\r\n\r\n- [ ] T001 x\r\n- [ ] T002 y\r\n", b"## P\r\n\r\n- [ ] T001 x\r\n- [X] T002 y\r\n"),
        (b"## P\r\r- [ ] T001 x\r- [ ] T002 y\r", b"## P\r\r- [ ] T001 x\r- [X] T002 y\r"),
        (b"## P\r\n\n- [ ] T001 x\r- [ ] T002 y\n", b"## P\r\n\n- [ ] T001 x\r- [X] T002 y\n"),
        (b"## P\n\n- [ ] T002 y", b"## P\n\n- [X] T002 y"),
        (b"\xef\xbb\xbf- [ ] T002 y\n", b"\xef\xbb\xbf- [X] T002 y\n"),
        (b"\xef\xbb\xbf## P\n\n- [ ] T002 y\n", b"\xef\xbb\xbf## P\n\n- [X] T002 y\n"),
        (b"## P\n\nbad \xff bytes\n- [ ] T002 y \xfe\n", b"## P\n\nbad \xff bytes\n- [X] T002 y \xfe\n"),
        ("## P\n\ncafé\n- [ ] T002 café\n".encode(), "## P\n\ncafé\n- [X] T002 café\n".encode()),
        ("a b c\x85d\n- [ ] T002 y\n".encode(), "a b c\x85d\n- [X] T002 y\n".encode()),
        (" - [ ] T002 y\n".encode(), " - [X] T002 y\n".encode()),
        ("-　[ ] T002 y\n".encode(), "-　[X] T002 y\n".encode()),
        (b"  * [ ] T002 y\n", b"  * [X] T002 y\n"),
        (b"\t+ [ ] T002 y\n", b"\t+ [X] T002 y\n"),
        (b"-[ ] T002 y\n", b"-[X] T002 y\n"),
        (b"- [ ] **T002** y\n", b"- [X] **T002** y\n"),
        (b"- [ ] [T002] y\n", b"- [X] [T002] y\n"),
        (b"---\ntitle: x\n---\n\n- [ ] T002 y\n", b"---\ntitle: x\n---\n\n- [X] T002 y\n"),
        (b"```\n- [ ] T001 x\n```\n\n- [ ] T002 y\n", b"```\n- [ ] T001 x\n```\n\n- [X] T002 y\n"),
        (b"<!-- - [ ] T001 x -->\n- [ ] T002 y\n", b"<!-- - [ ] T001 x -->\n- [X] T002 y\n"),
    ],
)
def test_only_that_box_changes(project, run, before, after):
    directory = project.feature(tasks=None)
    project.set_current(directory)
    (directory / "tasks.md").write_bytes(before)
    code, _, err = run("done", "T002")
    assert code == 0, err
    assert tasks_bytes(directory) == after


# -- One writer at a time ----------------------------------------------------------------------


def test_a_lock_held_too_long_fails_and_writes_nothing(run, current, project, engine, monkeypatch):
    monkeypatch.setattr(engine, "LOCK_TIMEOUT_SECONDS", 0)
    before = tasks_bytes(current)
    with engine.spec_lock(project.root, current):
        code, out, err = run("done", "T001")
    assert (code, out) == (1, "")
    assert "Another agent held 001-login" in err
    nothing_changed(current, before)


def test_the_lock_waits_for_its_turn(run, current, project, engine):
    import threading

    release = threading.Event()
    held = threading.Event()

    def holder():
        with engine.spec_lock(project.root, current):
            held.set()
            release.wait(10)

    thread = threading.Thread(target=holder)
    thread.start()
    held.wait(10)
    threading.Timer(0.3, release.set).start()
    started = time.monotonic()
    code = run("done", "T001")[0]
    waited = time.monotonic() - started
    thread.join()
    assert code == 0
    assert waited >= 0.25
    assert b"[X] T001" in tasks_bytes(current)


def test_the_page_is_drawn_while_the_lock_is_held(run, current, engine, monkeypatch):
    draw = engine.render_project
    found = []

    def checking(root, feature, *args, **kwargs):
        try:
            with engine.spec_lock(root, feature, timeout=0):
                found.append("free")
        except engine.ProgressError:
            found.append("held")
        return draw(root, feature, *args, **kwargs)

    monkeypatch.setattr(engine, "render_project", checking)
    assert run("done", "T001")[0] == 0
    assert found == ["held"]


def test_the_lock_is_free_again_afterwards(run, current, project, engine):
    assert run("start", "T001")[0] == 0
    with engine.spec_lock(project.root, current, timeout=0):
        pass


def test_the_lock_is_free_again_after_a_failure(run, current, project, engine):
    assert run("done", "T099")[0] == 1
    with engine.spec_lock(project.root, current, timeout=0):
        pass


def test_two_specs_do_not_wait_for_each_other(project, engine):
    first = project.feature(name="001-a")
    second = project.feature(name="002-b")
    with engine.spec_lock(project.root, first, timeout=0):
        with engine.spec_lock(project.root, second, timeout=0):
            pass


def test_a_problem_that_is_not_a_busy_lock_is_not_treated_as_one(engine, monkeypatch):
    def broken(*args):
        raise OSError(5, "input/output error")

    target = "fcntl" if engine.fcntl is not None else "msvcrt"
    monkeypatch.setattr(getattr(engine, target), "flock" if target == "fcntl" else "locking", broken)
    with pytest.raises(OSError):
        engine._try_lock(0)


def test_a_linked_lock_file_is_refused(project, engine, current, tmp_path):
    with engine.spec_lock(project.root, current):
        pass
    lock = next((project.root / ".specify" / "progress").glob(".lock-*"))
    lock.unlink()
    outside = tmp_path / "outside"
    outside.write_text("keep", encoding="utf-8")
    symlink(lock, outside)
    with pytest.raises(engine.ProgressError):
        with engine.spec_lock(project.root, current):
            pass
    assert outside.read_text(encoding="utf-8") == "keep"


def test_a_dead_process_leaves_no_lock_behind(project, current, engine):
    """It holds the lock, gets killed, and the next caller goes straight in."""
    code = (
        "import importlib.util, sys, time\n"
        "from pathlib import Path\n"
        "spec = importlib.util.spec_from_file_location('engine', sys.argv[1])\n"
        "engine = importlib.util.module_from_spec(spec)\n"
        "sys.modules['engine'] = engine\n"
        "spec.loader.exec_module(engine)\n"
        "with engine.spec_lock(Path(sys.argv[2]), Path(sys.argv[3])):\n"
        "    print('held', flush=True)\n"
        "    time.sleep(120)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-I", "-c", code, str(engine_module.engine_path()), str(project.root), str(current)],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "held"
        with pytest.raises(engine.ProgressError):
            with engine.spec_lock(project.root, current, timeout=0):
                pass
    finally:
        process.kill()
        process.communicate()
    with engine.spec_lock(project.root, current, timeout=5):
        pass


def test_the_lock_stays_out_of_git(run, current, project):
    run("start", "T001")
    ignore = (project.root / ".specify" / "progress" / ".gitignore").read_text(encoding="utf-8")
    assert "*" in ignore.splitlines()


def test_twenty_agents_at_once_lose_nothing(project, monkeypatch):
    """Real processes on one file. Without the lock, boxes and pages get lost."""
    tasks = "# Tasks\n\n## Phase 1\n\n" + "".join("- [ ] T%03d [P] Task %d\n" % (n, n) for n in range(1, 21))
    directory = project.feature(tasks=tasks)
    project.set_current(directory)
    env = dict(os.environ, SPECKIT_PROGRESS_NO_BROWSER="1")
    engine_file = str(engine_module.engine_path())
    processes = [
        subprocess.Popen(
            [
                sys.executable, "-I", engine_file, "--root", str(project.root), "--harness", "claude",
                "done", "T%03d" % n, "--note", "Agent %d" % n, "--agent", "agent-%d" % n,
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for n in range(1, 21)
    ]
    results = [(process.communicate(timeout=120), process.returncode) for process in processes]
    assert [code for _, code in results] == [0] * 20, [err for (_, err), _ in results]
    text = tasks_bytes(directory).decode()
    assert text.count("- [X] T") == 20
    assert "- [ ] T" not in text
    events = read_log(directory)
    assert sorted(e["task"] for e in events) == ["T%03d" % n for n in range(1, 21)]
    assert {e["note"] for e in events} == {"Agent %d" % n for n in range(1, 21)}
    page = (project.root / ".specify" / "progress" / "001-login.html").read_text(encoding="utf-8")
    assert '"done":20' in page.replace(" ", "")


# -- Replacing a file on Windows ---------------------------------------------------------------


def test_a_file_someone_holds_open_is_tried_again(engine, tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "REPLACE_ATTEMPTS", 3)
    monkeypatch.setattr(engine, "REPLACE_WAIT_SECONDS", 0)
    real = os.replace
    calls = []

    def flaky(source, target):
        calls.append(target)
        if len(calls) < 3:
            raise PermissionError(13, "in use")
        real(source, target)

    monkeypatch.setattr(engine.os, "replace", flaky)
    path = tmp_path / "file"
    engine.write_atomic(path, "text")
    assert len(calls) == 3
    assert path.read_text(encoding="utf-8") == "text"


def test_a_file_that_stays_held_fails_and_leaves_no_temporary_behind(engine, tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "REPLACE_ATTEMPTS", 2)
    monkeypatch.setattr(engine, "REPLACE_WAIT_SECONDS", 0)

    def always(source, target):
        raise PermissionError(13, "in use")

    monkeypatch.setattr(engine.os, "replace", always)
    with pytest.raises(PermissionError):
        engine.write_atomic(tmp_path / "file", "text")
    assert list(tmp_path.iterdir()) == []


# -- Small pieces ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (None, []),
        ([], []),
        (["a.py"], ["a.py"]),
        (["a.py,b.py"], ["a.py", "b.py"]),
        (["a.py", "b.py"], ["a.py", "b.py"]),
        (["a.py, b.py", "c.py"], ["a.py", "b.py", "c.py"]),
        (["a.py,,a.py,"], ["a.py"]),
        (["a\x1bb.py"], ["a b.py"]),
    ],
)
def test_file_names(engine, values, expected):
    assert engine.clean_file_names(values) == expected


def test_file_names_have_limits(engine):
    assert len(engine.clean_file_names(["f%d" % n for n in range(engine.MAX_FILES_PER_EVENT + 5)])) == engine.MAX_FILES_PER_EVENT
    assert len(engine.clean_file_names(["x" * 1000])[0]) == engine.MAX_FILE_NAME_CHARS


def test_a_long_note_is_cut(run, current, engine):
    run("note", "T001", "x" * (engine.MAX_NOTE_CHARS + 50))
    assert len(read_log(current)[0]["note"]) == engine.MAX_NOTE_CHARS


def test_a_note_in_another_language_stays_readable_in_the_log(run, current):
    run("note", "T001", "Déjé la ruta 日本語")
    assert "Déjé la ruta 日本語" in (current / "progress.jsonl").read_text(encoding="utf-8")


def test_a_line_the_engine_writes_is_a_line_the_engine_reads(engine):
    event = engine.make_task_event("T001", "done", "Text", "claude", "a", "Note", ["a.py"])
    cleaned = engine.clean_event(json.loads(json.dumps(event)))
    assert cleaned["task"] == "T001"
    assert cleaned["note"] == "Note"
    assert cleaned["files"] == ["a.py"]
    assert cleaned["actor"]["source"] == "declared"


def test_redoing_tasks_md_keeps_old_history_apart(project, run, current, engine):
    run("done", "T001", "--note", "Old work")
    (current / "tasks.md").write_text("## P\n\n- [ ] T001 A different task now\n", encoding="utf-8")
    row = engine.status_data(project.root, current)[0]
    assert row["totals"]["done"] == 0
    assert row["totals"]["pending"] == 1
