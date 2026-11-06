"""How the progress engine reads tasks.md."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from .conftest import symlink

REPO = Path(__file__).resolve().parents[3]


def only_task(engine, line):
    phases = engine.parse_tasks(line + "\n")["phases"]
    assert len(phases) == 1 and len(phases[0]["tasks"]) == 1, phases
    return phases[0]["tasks"][0]


def test_reads_every_part_of_a_task_line(engine):
    task = only_task(engine, "- [ ] T012 [P] [US2] Add the form in src/form.py")
    assert task["id"] == "T012"
    assert task["checked"] is False
    assert task["parallel"] is True
    assert task["story"] == "US2"
    assert task["text"] == "Add the form in src/form.py"
    assert task["line"] == 1


@pytest.mark.parametrize("mark", ["x", "X"])
def test_either_case_of_x_means_checked(engine, mark):
    assert only_task(engine, "- [%s] T001 Done" % mark)["checked"] is True


@pytest.mark.parametrize(
    "line",
    [
        "* [ ] T001 Do it",
        "+ [ ] T001 Do it",
        "  - [ ] T001 Do it",
        "- [ ] **T001** Do it",
        "- [ ] T001: Do it",
        "- [ ] T001 - Do it",
        "- [ ] [T001] Do it",
        "-[ ] T001 Do it",
    ],
)
def test_common_ways_of_writing_a_task_are_understood(engine, line):
    task = only_task(engine, line)
    assert (task["id"], task["text"]) == ("T001", "Do it")


@pytest.mark.parametrize(
    "line",
    ["- [ ] Do it without an id", "- [ ] TASK1 Not an id", "- [ ] T1.2 Not an id", "- [ ] T1-a Not an id", "- [ ] t001 Lowercase"],
)
def test_a_checkbox_without_an_id_is_reported_and_not_counted(engine, line):
    parsed = engine.parse_tasks("## Phase 1\n" + line + "\n")
    assert parsed["phases"] == []
    assert parsed["unparsed"] == [{"line": 2, "text": line}]


def test_a_line_that_is_not_a_checkbox_is_neither_a_task_nor_reported(engine):
    parsed = engine.parse_tasks("T001 is mentioned here\n- a bullet T002\n")
    assert parsed == {"phases": [], "unparsed": [], "duplicates": []}


def test_level_two_headings_group_tasks_and_level_three_names_a_section(engine):
    parsed = engine.parse_tasks("## One\n- [ ] T001 A\n### Inner\n- [ ] T002 B\n## Two\n- [ ] T003 C\n")
    assert [phase["name"] for phase in parsed["phases"]] == ["One", "Two"]
    first = parsed["phases"][0]["tasks"]
    assert (first[0]["section"], first[1]["section"]) == (None, "Inner")
    assert parsed["phases"][1]["tasks"][0]["section"] is None


def test_a_heading_without_tasks_is_not_a_phase(engine):
    parsed = engine.parse_tasks("## Notes\ntext\n## One\n- [ ] T001 A\n## Dependencies\nmore\n")
    assert [phase["name"] for phase in parsed["phases"]] == ["One"]


def test_tasks_before_any_heading_get_a_group_of_their_own(engine):
    assert engine.parse_tasks("- [ ] T001 A\n")["phases"][0]["name"] == "Tasks"


def test_phases_written_one_level_deeper_are_still_phases(engine):
    parsed = engine.parse_tasks("## Tasks\n### Phase 1: A\n- [ ] T001 A\n### Phase 2: B\n- [ ] T002 B\n")
    assert [phase["name"] for phase in parsed["phases"]] == ["Phase 1: A", "Phase 2: B"]


@pytest.mark.parametrize("goal", ["**Goal**: Sign in", "**Purpose**: Sign in", "**Goal:** Sign in", "**Goal** Sign in"])
def test_the_goal_of_a_phase_is_kept(engine, goal):
    parsed = engine.parse_tasks("## One\n\n%s\n\n- [ ] T001 A\n" % goal)
    assert parsed["phases"][0]["goal"] == "Sign in"


def test_a_goal_does_not_leak_into_the_next_phase(engine):
    parsed = engine.parse_tasks("## One\n**Goal**: First\n- [ ] T001 A\n## Two\n- [ ] T002 B\n")
    assert [phase["goal"] for phase in parsed["phases"]] == ["First", None]


def test_a_goal_written_after_the_first_task_is_kept(engine):
    parsed = engine.parse_tasks("## One\n- [ ] T001 A\n**Goal**: Late\n")
    assert parsed["phases"][0]["goal"] == "Late"


@pytest.mark.parametrize(
    "wrapped",
    [
        "```\n- [ ] T999 In code\n```\n",
        "~~~md\n- [ ] T999 In code\n~~~\n",
        "<!-- - [ ] T999 In a comment -->\n",
        "<!--\n- [ ] T999 In a comment\n-->\n",
        "---\ndescription: x\n- [ ] T999 not front matter once a task appears\n---\n",
    ],
)
def test_hidden_content_is_not_read_as_tasks(engine, wrapped):
    parsed = engine.parse_tasks(wrapped + "- [ ] T001 Real\n")
    ids = [task["id"] for phase in parsed["phases"] for task in phase["tasks"]]
    assert "T001" in ids
    if "front matter" not in wrapped:
        assert ids == ["T001"]


def test_front_matter_is_skipped(engine):
    parsed = engine.parse_tasks("---\ndescription: \"- [ ] T999 in front matter\"\nkey: value\n---\n- [ ] T001 Real\n")
    assert [task["id"] for phase in parsed["phases"] for task in phase["tasks"]] == ["T001"]


def test_a_rule_on_the_first_line_is_not_front_matter(engine):
    parsed = engine.parse_tasks("---\n## One\n- [ ] T001 A\n---\n")
    assert parsed["phases"][0]["name"] == "One"


def test_a_fence_only_closes_with_its_own_kind(engine):
    parsed = engine.parse_tasks("```\n~~~\n- [ ] T999 still code\n```\n- [ ] T001 Real\n")
    assert [task["id"] for task in parsed["phases"][0]["tasks"]] == ["T001"]


def test_a_repeated_id_is_flagged_and_both_lines_stay_visible(engine):
    parsed = engine.parse_tasks("- [ ] T001 A\n- [ ] T001 B\n- [ ] T002 C\n")
    assert parsed["duplicates"] == ["T001"]
    assert len(parsed["phases"][0]["tasks"]) == 3


def test_windows_line_endings_are_fine(engine):
    parsed = engine.parse_tasks("## One\r\n- [ ] T001 A\r\n")
    assert parsed["phases"][0]["tasks"][0]["text"] == "A"


@pytest.mark.parametrize("char", ["\u2028", "\u2029", "\x0b", "\x0c", "\x1c", "\x85"])
def test_only_real_line_breaks_end_a_line(engine, char):
    parsed = engine.parse_tasks("- [ ] T001 One%s- [ ] T002 Hidden\n- [ ] T003 Next\n" % char)
    tasks = parsed["phases"][0]["tasks"]
    assert [task["id"] for task in tasks] == ["T001", "T003"]
    assert tasks[1]["line"] == 2


def test_a_byte_order_mark_does_not_hide_the_first_line(engine, tmp_path):
    path = tmp_path / "tasks.md"
    path.write_bytes(b"\xef\xbb\xbf- [ ] T001 A\n")
    text, truncated = engine.read_limited(path, 1000)
    assert engine.parse_tasks(text)["phases"][0]["tasks"][0]["id"] == "T001"
    assert truncated is False


def test_bytes_that_are_not_utf8_do_not_stop_the_read(engine, tmp_path):
    path = tmp_path / "tasks.md"
    path.write_bytes(b"- [ ] T001 caf\xe9\n")
    text, _ = engine.read_limited(path, 1000)
    assert engine.parse_tasks(text)["phases"][0]["tasks"][0]["id"] == "T001"


@pytest.mark.parametrize("text", [None, "", "\n\n"])
def test_no_text_means_no_tasks(engine, text):
    assert engine.parse_tasks(text) == {"phases": [], "unparsed": [], "duplicates": []}


def test_a_file_over_the_limit_is_cut_and_says_so(engine, tmp_path):
    path = tmp_path / "big.md"
    path.write_text("x" * 50, encoding="utf-8")
    assert engine.read_limited(path, 10) == ("x" * 10, True)
    assert engine.read_limited(path, 50) == ("x" * 50, False)


def test_reading_refuses_links_and_directories(engine, tmp_path):
    target = tmp_path / "secret.md"
    target.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.md"
    symlink(link, target)
    assert engine.read_limited(link, 100) == (None, False)
    assert engine.read_limited(tmp_path, 100) == (None, False)
    assert engine.read_limited(tmp_path / "missing.md", 100) == (None, False)


@pytest.mark.parametrize(
    "line",
    [
        "# " + "#" * 300_000 + "x",
        "- [ ] " + "[a]" * 300_000,
        "- [ ] T001 " + "[a]" * 300_000,
        "- " * 300_000,
        " " * 300_000 + "x",
    ],
)
def test_a_hostile_line_cannot_stall_the_page(engine, line):
    started = time.perf_counter()
    engine.parse_tasks(line + "\n")
    assert time.perf_counter() - started < 5


def test_the_real_task_template_has_no_tasks_to_count(engine, project):
    template = (REPO / "templates" / "tasks-template.md").read_text(encoding="utf-8")
    directory = project.feature(tasks=template)
    data = engine.build_feature(project.root, directory, project.root / ".specify" / "progress")
    assert data["totals"]["total"] == 0
    assert data["attention"] == []


def test_a_finished_task_file_that_mentions_the_template_title_late_still_counts(engine, project):
    tasks = "# Tasks: Login\n\n- [ ] T001 A\n\n" + "x\n" * 3000 + "# Tasks: [FEATURE NAME]\n"
    directory = project.feature(tasks=tasks)
    data = engine.build_feature(project.root, directory, project.root / ".specify" / "progress")
    assert data["totals"]["total"] == 1
