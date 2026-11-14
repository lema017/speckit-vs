#!/usr/bin/env python3
"""Spec Kit progress engine: read a project's files and draw one page per spec.

Self-contained on purpose. Projects get a copy of this file and run it with whatever interpreter
they have, so it uses only the standard library and stays compatible with Python 3.9.

tasks.md decides what is done. specs/<feature>/progress.jsonl adds who, when and why, plus the
states a checkbox cannot hold. Everything read here was written by a model or a person, so it is
untrusted: pages carry it as escaped JSON and paint it only as text.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import re
import stat
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

try:
    import fcntl
except ImportError:  # Windows.
    fcntl = None
    import msvcrt

SCHEMA_VERSION = 1
GENERATOR = "speckit-progress"
OUTPUT_DIR = Path(".specify") / "progress"
PAGE_TEMPLATE = "page.html"
INDEX_TEMPLATE = "index.html"
LOG_NAME = "progress.jsonl"
ATTRIBUTES_NAME = ".gitattributes"
BROWSER_OFF_FILE = ".no-browser"
BROWSER_OFF_ENV = "SPECKIT_PROGRESS_NO_BROWSER"
OPENED_PREFIX = ".opened-"
DATA_PLACEHOLDER = "/*DATA*/null"

MAX_TASKS_BYTES = 5 * 1024 * 1024
MAX_LOG_BYTES = 20 * 1024 * 1024
MAX_DOC_BYTES = 256 * 1024
MAX_DOCS_TOTAL_BYTES = 2 * 1024 * 1024
MAX_CONTRACT_FILES = 20
MAX_NOTE_CHARS = 2000
MAX_FIELD_CHARS = 200
MAX_FILES_PER_EVENT = 50
MAX_FILE_NAME_CHARS = 400
ACTIVITY_LIMIT = 200
ABANDONED_AFTER_SECONDS = 4 * 3600
LOCK_PREFIX = ".lock-"
LOCK_TIMEOUT_SECONDS = 15
LOCK_POLL_SECONDS = 0.02
MAX_IDS_SHOWN = 100
MAX_HOOK_BYTES = 1024 * 1024
SESSION_CHARS = 8
REPLACE_ATTEMPTS = 40 if os.name == "nt" else 1  # Windows refuses while anyone holds the file open.
REPLACE_WAIT_SECONDS = 0.05

TASK_STATUSES = frozenset({"in_progress", "done", "blocked", "failed", "skipped", "note"})
OPEN_STATUSES = frozenset({"in_progress", "blocked", "failed", "skipped"})
STEP_STATUSES = frozenset({"in_progress", "done", "failed", "skipped", "note"})
TASK_COMMANDS = {"start": "in_progress", "done": "done", "block": "blocked", "fail": "failed", "skip": "skipped", "note": "note"}
TASK_REPORTS = {"in_progress": "started", "done": "done", "blocked": "blocked", "failed": "failed", "skipped": "skipped", "note": "note saved"}
ACTOR_SOURCES = frozenset({"observed", "configured", "declared"})
STEP_ALIASES = {"clarify-deep": "clarify"}
STEP_NAMES = ("constitution", "specify", "clarify", "plan", "checklist", "tasks", "analyze", "implement", "converge")
# The specify and clarify commands keep this checklist and check its boxes themselves. Every other
# checklist comes from the checklist command, which never checks a box: [x] there is a reviewer's.
SPEC_QUALITY_CHECKLIST = "requirements.md"
_UNSAFE_CODES = (
    list(range(0x00, 0x20)) + list(range(0x7f, 0xa0)) + [0x200e, 0x200f] + list(range(0x202a, 0x202f)) + list(range(0x2066, 0x206a))
)
_UNSAFE_TEXT = re.compile("[" + "".join(re.escape(chr(code)) for code in _UNSAFE_CODES) + "]")
_HARNESS_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,40}$")
_STATUS_WORDS = (
    ("in_progress", "in progress"),
    ("blocked", "blocked"),
    ("failed", "failed"),
    ("skipped", "skipped"),
    ("pending", "pending"),
)

_CHECKBOX = re.compile(r"^\s*[-*+]\s*\[([ xX])\]\s*(.*)$")
_LEADING_TAG = re.compile(r"^\[([^\]\n]{1,40})\]\s*")
_TASK_ID = re.compile(r"^(?:\*\*)?(T\d+)(?:\*\*)?(?![\w-]|\.\d)\s*(?:[:.\-\u2013\u2014]\s+|:\s*)?")
_BRACKETED_ID = re.compile(r"^T\d+$")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+)$")
_GOAL = re.compile(r"^\*\*(?:Goal|Purpose):?\*\*:?\s*(.+)$")
_LINE_BREAK = re.compile(r"\r\n?|\n")
_LINE_BREAK_BYTES = re.compile(rb"\r\n?|\n")
_FENCE = re.compile(r"^\s*(```+|~~~+)")
_QUESTION = re.compile(r"^\s*[-*+]\s+(?:\*\*)?Q:")
_REQUIREMENT = re.compile(r"\*\*(FR-\d+)\*\*")
_STEP_NAME = re.compile(r"^[a-z][a-z0-9.-]{0,40}$")
_AREA_NAME = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
MAX_AREA_CHARS = 60
_TASK_NAME = re.compile(r"^T\d+$")
_SAFE_FILE = re.compile(r"[^A-Za-z0-9._-]+")
_PROGRESS_CALL = re.compile(r"(?:^|[\s;&|(])(start|done|block|fail|skip|note)\s+(T\d+)\b")
_THEN_OPTION = re.compile(r"--then\s+(T\d+)\b")
_PHASE_HEADING = re.compile(r"^Phase\b", re.IGNORECASE)
MAX_TAGS_PER_TASK = 20

CONSTITUTION_PLACEHOLDERS = ("[PROJECT_NAME]", "[PRINCIPLE_1_NAME]")
SPEC_PLACEHOLDERS = ("[FEATURE NAME]",)
PLAN_PLACEHOLDERS = ("[FEATURE]", "[###-feature-name]")
TASKS_PLACEHOLDER = "# Tasks: [FEATURE NAME]"
TEMPLATE_HEAD_CHARS = 4096
OPEN_QUESTION = "[NEEDS CLARIFICATION"
DESIGN_DOCS = ("research.md", "data-model.md", "quickstart.md")
DOCUMENT_ORDER = ("spec.md", "plan.md", "research.md", "data-model.md", "quickstart.md", "tasks.md")
CONTRACT_SUFFIXES = (".md", ".markdown", ".yaml", ".yml", ".json", ".txt", ".graphql", ".proto")

CONSTITUTION_DOCUMENT = "constitution.md"
STEP_DOCUMENTS = {
    "constitution": CONSTITUTION_DOCUMENT,
    "specify": "spec.md",
    "clarify": "spec.md",
    "plan": "plan.md",
    "tasks": "tasks.md",
}


class ProgressError(Exception):
    """An expected failure the caller can show as a plain message."""


# -- Reading files ----------------------------------------------------------------------------


def read_limited(path, limit):
    """Return (text, truncated). Text is None when the file is missing, unreadable or a link."""
    try:
        if path.is_symlink() or not path.is_file():
            return None, False
        with path.open("rb") as handle:
            raw = handle.read(limit + 1)
    except OSError:
        return None, False
    truncated = len(raw) > limit
    if truncated:
        raw = raw[:limit]
    return raw.decode("utf-8-sig", errors="replace"), truncated


def visible_lines(text):
    """Yield (line number, line), skipping front matter, fenced code and HTML comments."""
    lines = _LINE_BREAK.split(text or "")  # Not splitlines(): editors count lines by these alone.
    start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, min(len(lines), 200)):
            stripped = lines[index].strip()
            if stripped == "---":
                start = index + 1
                break
            if stripped.startswith("#") or _CHECKBOX.match(lines[index]):
                break
    fence = None
    in_comment = False
    for index in range(start, len(lines)):
        line = lines[index]
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        marker = _FENCE.match(line)
        if fence is not None:
            if marker and marker.group(1)[0] == fence:
                fence = None
            continue
        if marker:
            fence = marker.group(1)[0]
            continue
        stripped = line.strip()
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_comment = True
            continue
        yield index + 1, line


# -- tasks.md ---------------------------------------------------------------------------------


def parse_heading(line):
    """Return (level, text) for a Markdown heading, or None. Linear on any line."""
    match = _HEADING.match(line)
    if not match:
        return None
    name = match.group(2).rstrip(" \t#").strip()
    return (len(match.group(1)), name) if name else None


def task_text_sha(text):
    """Fingerprint a task's text, so history can be told apart from a renumbered task."""
    return hashlib.sha256(" ".join((text or "").split()).encode("utf-8")).hexdigest()[:12]


def _parse_task_line(rest):
    """Split what follows a checkbox into (id, tags, text). The id is None when there is none."""
    tags = []
    remainder = rest.strip()
    task_id = None
    for _ in range(MAX_TAGS_PER_TASK):
        tag = _LEADING_TAG.match(remainder)
        if not tag:
            break
        if task_id is None and _BRACKETED_ID.match(tag.group(1)):
            task_id = tag.group(1)
        else:
            tags.append(tag.group(1).strip())
        remainder = remainder[tag.end():]
    if task_id is None:
        match = _TASK_ID.match(remainder)
        if not match:
            return None, [], rest.strip()
        task_id = match.group(1)
        remainder = remainder[match.end():]
    for _ in range(MAX_TAGS_PER_TASK):
        tag = _LEADING_TAG.match(remainder)
        if not tag:
            break
        tags.append(tag.group(1).strip())
        remainder = remainder[tag.end():]
    return task_id, tags, remainder.strip()


def parse_tasks(text):
    """Parse tasks.md. A checkbox that is not a task is reported, never dropped in silence."""
    phases = []
    unparsed = []
    current = None
    pending_name = None
    pending_goal = None
    section = None
    seen = {}

    def open_phase(name):
        phase = {"name": name, "goal": pending_goal, "tasks": []}
        phases.append(phase)
        return phase

    for number, line in visible_lines(text):
        heading = parse_heading(line)
        if heading:
            level, name = heading
            if level == 2 or (level > 2 and _PHASE_HEADING.match(name)):
                pending_name, pending_goal, section, current = name, None, None, None
            elif level > 2:
                section = name
            continue
        goal = _GOAL.match(line.strip())
        if goal and pending_goal is None:
            if current is not None and current["goal"] is None:
                current["goal"] = goal.group(1)
            elif current is None:
                pending_goal = goal.group(1)
            continue
        box = _CHECKBOX.match(line)
        if not box:
            continue
        task_id, tags, body = _parse_task_line(box.group(2))
        if task_id is None:
            unparsed.append({"line": number, "text": line.strip()[:MAX_FIELD_CHARS]})
            continue
        if current is None:
            current = open_phase(pending_name or "Tasks")
        parallel = any(tag.upper() == "P" for tag in tags)
        others = [tag for tag in tags if tag.upper() != "P"]
        task = {
            "id": task_id,
            "checked": box.group(1) != " ",
            "parallel": parallel,
            "story": others[0] if others else None,
            "tags": others[1:],
            "text": body,
            "line": number,
            "section": section,
        }
        current["tasks"].append(task)
        seen[task_id] = seen.get(task_id, 0) + 1
    duplicates = sorted(task_id for task_id, count in seen.items() if count > 1)
    return {"phases": phases, "unparsed": unparsed, "duplicates": duplicates}


# -- The log ----------------------------------------------------------------------------------


def _text_field(value, limit=MAX_FIELD_CHARS):
    return value[:limit] if isinstance(value, str) and value else None


def parse_timestamp(value):
    """Return an aware datetime, or None. Python 3.9 does not accept a trailing Z."""
    if not isinstance(value, str) or not value:
        return None
    candidate = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def clean_actor(raw):
    if not isinstance(raw, dict):
        return None
    actor = {key: _text_field(raw.get(key)) for key in ("harness", "agent", "session")}
    if not any(actor.values()):
        return None
    source = raw.get("source")
    actor["source"] = source if source in ACTOR_SOURCES else "declared"
    return actor


def clean_event(raw):
    """Keep only well-formed fields. Return None when the line cannot be understood."""
    if not isinstance(raw, dict):
        return None
    version = raw.get("v", SCHEMA_VERSION)
    if not isinstance(version, int) or isinstance(version, bool) or version > SCHEMA_VERSION:
        return None
    kind = raw.get("kind")
    status = raw.get("status")
    event = {"kind": kind, "status": status}
    if kind in ("task", "seen"):
        name = raw.get("task")
        if status not in TASK_STATUSES or not isinstance(name, str) or not _TASK_NAME.match(name):
            return None
        event["task"] = name
    elif kind == "step":
        name = raw.get("step")
        if status not in STEP_STATUSES or not isinstance(name, str) or not _STEP_NAME.match(name):
            return None
        event["step"] = STEP_ALIASES.get(name, name)
        area = raw.get("area")
        if isinstance(area, str) and len(area) <= MAX_AREA_CHARS and _AREA_NAME.match(area):
            event["area"] = area
    else:
        return None
    stamp = parse_timestamp(raw.get("ts"))
    event["ts"] = stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if stamp else None
    note = _text_field(raw.get("note"), MAX_NOTE_CHARS)
    if note:
        event["note"] = note
    files = raw.get("files")
    if isinstance(files, list):
        names = [_text_field(item, MAX_FILE_NAME_CHARS) for item in files[:MAX_FILES_PER_EVENT]]
        names = [name for name in names if name]
        if names:
            event["files"] = names
    sha = _text_field(raw.get("text_sha"), 64)
    if sha:
        event["text_sha"] = sha
    actor = clean_actor(raw.get("actor"))
    if actor:
        event["actor"] = actor
    return event


def apply_seen(events):
    """What a harness saw attaches to the report it saw being made, and is not an event of its own:
    the model says which task it was, the harness says who ran the call. A call that failed wrote
    no report, so what was seen of it attaches to nothing."""
    reports = {}
    kept = []
    for event in events:
        if event["kind"] != "seen":
            if event["kind"] == "task":
                reports.setdefault((event["task"], event["status"]), []).append(event)
            kept.append(event)
            continue
        seen = event.get("actor")
        waiting = [e for e in reports.get((event["task"], event["status"]), ()) if (e.get("actor") or {}).get("source") != "observed"]
        if not seen or not waiting:
            continue
        report = waiting[-1]
        declared = (report.get("actor") or {}).get("agent")
        report["actor"] = {
            "harness": seen.get("harness") or (report.get("actor") or {}).get("harness"),
            "agent": declared or seen.get("agent"),
            "session": seen.get("session"),
            "source": "observed" if seen.get("agent") or not declared else "declared",
        }
    return kept


def read_events(path):
    """Return (events, lines that could not be used, truncated)."""
    text, truncated = read_limited(path, MAX_LOG_BYTES)
    events = []
    bad = 0
    lines = (text or "").split("\n")
    if truncated and lines:
        lines = lines[:-1]  # The last line was cut in half by the size limit.
    for line in lines:
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            bad += 1
            continue
        event = clean_event(raw)
        if event is None:
            bad += 1
        else:
            events.append(event)
    return apply_seen(events), bad, truncated


# -- Crossing tasks.md with the log -----------------------------------------------------------


def actor_label(actor):
    if not actor:
        return None
    harness = actor.get("harness") or "unknown"
    agent = actor.get("agent")
    return harness + "/" + agent if agent and agent != "main" else harness


def reconcile_task(task, own_events):
    """tasks.md decides what is done. The log adds detail, and contradictions stay visible."""
    sha = task_text_sha(task["text"])
    current = [e for e in own_events if not e.get("text_sha") or e["text_sha"] == sha]
    older = [e for e in own_events if e.get("text_sha") and e["text_sha"] != sha]
    states = [e for e in current if e["status"] != "note"]
    declared = states[-1]["status"] if states else None
    if task["checked"]:
        status = "done"
    elif declared in OPEN_STATUSES:
        status = declared
    else:
        status = "pending"

    problem = None
    if declared == "done" and not task["checked"]:
        problem = "Its agent said it was done, but the box in tasks.md is empty."
    elif task["checked"] and declared in ("failed", "blocked"):
        problem = "Checked in tasks.md, but its last report was: " + declared + "."

    actor = next((e["actor"] for e in reversed(states) if e.get("actor")), None)
    if actor is None:
        actor = next((e["actor"] for e in reversed(current) if e.get("actor")), None)
    files = []
    for event in current:
        for name in event.get("files", ()):
            if name not in files:
                files.append(name)
    last_ts = next((e["ts"] for e in reversed(current) if e.get("ts")), None)
    view = dict(task)
    view.update(
        status=status,
        problem=problem,
        no_record=task["checked"] and not current,
        actor=actor,
        who=actor_label(actor),
        files=files,
        notes=[e for e in current if e.get("note")],
        history=states,
        older_history=older,
        last_ts=last_ts,
    )
    return view


def is_abandoned(task, now):
    """An unfinished task nobody has touched for hours: the session probably died."""
    if task["status"] != "in_progress":
        return False
    stamp = parse_timestamp(task.get("last_ts"))
    return stamp is None or now - stamp > timedelta(seconds=ABANDONED_AFTER_SECONDS)


# -- The steps of the workflow ----------------------------------------------------------------


def _has_placeholder(text, placeholders):
    return any(token in (text or "") for token in placeholders)


def _spec_facts(spec):
    questions = 0
    open_questions = 0
    requirements = set()
    for _, line in visible_lines(spec):
        if _QUESTION.match(line):
            questions += 1
        open_questions += line.count(OPEN_QUESTION)
        requirements.update(_REQUIREMENT.findall(line))
    return questions, open_questions, len(requirements)


def _checklist_facts(directory):
    rows = []
    folder = directory / "checklists"
    if not folder.is_dir() or folder.is_symlink():
        return rows
    for path in sorted(folder.glob("*.md")):
        text, _ = read_limited(path, MAX_DOC_BYTES)
        if text is None:
            continue
        boxes = [_CHECKBOX.match(line) for _, line in visible_lines(text)]
        boxes = [box for box in boxes if box]
        rows.append({
            "name": path.name,
            "checked": sum(1 for box in boxes if box.group(1) != " "),
            "total": len(boxes),
            "spec_quality": path.name == SPEC_QUALITY_CHECKLIST,
        })
    return rows


def _checklist_detail(row):
    owner = "spec quality, kept by the specify and clarify commands" if row["spec_quality"] else "reviewer checklist"
    return "%s: %d of %d (%s)" % (row["name"], row["checked"], row["total"], owner)


def _checklist_reasons(lists):
    """One entry per checklist with unchecked boxes, saying whose boxes they are."""
    reasons = []
    for row in lists:
        left = row["total"] - row["checked"]
        if not left:
            continue
        if row["spec_quality"]:
            text = "%s: %s %s unchecked. The specify and clarify commands keep this checklist." % (
                row["name"], _count(left, "spec-quality item"), "is" if left == 1 else "are")
        else:
            text = "%s: %s %s reviewer review." % (row["name"], _count(left, "item"), "awaits" if left == 1 else "await")
        reasons.append({"task": None, "text": text})
    return reasons


def _count(number, noun):
    return "%d %s%s" % (number, noun, "" if number == 1 else "s")


def _step(name, label, state, fact, details=None):
    return {
        "name": name,
        "label": label,
        "state": state,
        "fact": fact,
        "details": details or [],
        "document": STEP_DOCUMENTS.get(name),
        "actor": None,
        "who": None,
        "note": None,
    }


def build_steps(root, directory, phases, events, spec):
    """Each step says what its files prove; the log only adds who, and what files cannot show.

    Returns the steps and, for "Needs your attention", why each step that needs it does."""
    every = [task for phase in phases for task in phase["tasks"]]
    done = sum(1 for task in every if task["status"] == "done")
    started = any(task["status"] != "pending" for task in every)
    questions, open_questions, requirements = _spec_facts(spec)
    logged = {}
    notes = {}
    actors = {}
    for event in events:
        if event["kind"] != "step":
            continue
        if event["status"] != "note":
            logged[event["step"]] = event
        if event.get("note"):
            notes[event["step"]] = event["note"]
        if event.get("actor"):
            actors[event["step"]] = event["actor"]
    finished = {name for name, event in logged.items() if event["status"] == "done"}

    constitution, _ = read_limited(root / ".specify" / "memory" / "constitution.md", MAX_DOC_BYTES)
    if constitution is None:
        first = _step("constitution", "Constitution", "pending", "not written")
    elif _has_placeholder(constitution, CONSTITUTION_PLACEHOLDERS):
        first = _step("constitution", "Constitution", "pending", "template only")
    else:
        first = _step("constitution", "Constitution", "done", "project rules")

    if spec is None:
        specify = _step("specify", "Specify", "pending", "no spec")
    elif _has_placeholder(spec, SPEC_PLACEHOLDERS):
        specify = _step("specify", "Specify", "active", "draft")
    else:
        specify = _step("specify", "Specify", "done", _count(requirements, "requirement"))

    if open_questions:
        clarify = _step("clarify", "Clarify", "attention", "%d open" % open_questions)
    elif questions:
        clarify = _step("clarify", "Clarify", "done", _count(questions, "decision"))
    elif "clarify" in finished:
        clarify = _step("clarify", "Clarify", "done", "no questions")
    else:
        clarify = _step("clarify", "Clarify", "skipped", "not run")

    plan_text, _ = read_limited(directory / "plan.md", MAX_DOC_BYTES)
    design = [name for name in DESIGN_DOCS if (directory / name).is_file()]
    if (directory / "contracts").is_dir():
        design.append("contracts")
    if plan_text is None:
        plan = _step("plan", "Plan", "pending", "no plan")
    elif _has_placeholder(plan_text, PLAN_PLACEHOLDERS):
        plan = _step("plan", "Plan", "active", "draft")
    elif design:
        plan = _step("plan", "Plan", "done", _count(len(design), "design doc"), design)
    else:
        plan = _step("plan", "Plan", "done", "plan only")

    lists = _checklist_facts(directory)
    checked = sum(row["checked"] for row in lists)
    total = sum(row["total"] for row in lists)
    details = [_checklist_detail(row) for row in lists]
    if not lists:
        checklist = _step("checklist", "Checklist", "skipped", "not run")
    elif checked == total:
        checklist = _step("checklist", "Checklist", "done", "%d of %d" % (checked, total), details)
    elif any(row["spec_quality"] and row["checked"] < row["total"] for row in lists):
        checklist = _step("checklist", "Checklist", "attention", "%d of %d" % (checked, total), details)
    else:
        # Only reviewers' boxes are left: the command did its part, and the rest is review.
        generated = "generated \u00b7 " if "checklist" in finished else ""
        checklist = _step("checklist", "Checklist", "review", "%s%d of %d reviewed" % (generated, checked, total), details)

    if every:
        tasks = _step("tasks", "Tasks", "done", _count(len(every), "task"))
    else:
        tasks = _step("tasks", "Tasks", "pending", "no tasks")

    if "analyze" in finished:
        analyze = _step("analyze", "Analyze", "done", "reviewed")
    else:
        analyze = _step("analyze", "Analyze", "skipped", "no record")

    if not every:
        implement = _step("implement", "Implement", "pending", "not started")
    elif done == len(every):
        implement = _step("implement", "Implement", "done", "%d of %d" % (done, len(every)))
    elif started or "implement" in logged:
        implement = _step("implement", "Implement", "active", "%d of %d" % (done, len(every)))
    else:
        implement = _step("implement", "Implement", "pending", "0 of %d" % len(every))

    if any("convergence" in phase["name"].lower() for phase in phases):
        converge = _step("converge", "Converge", "done", "added tasks")
    elif "converge" in finished:
        converge = _step("converge", "Converge", "done", "no new tasks")
    else:
        converge = _step("converge", "Converge", "pending", "not run")

    if lists:
        checklist["document"] = "checklists/" + lists[0]["name"]

    steps = [first, specify, clarify, plan, checklist, tasks, analyze, implement, converge]
    reasons = []
    for step in steps:
        name = step["name"]
        step["actor"] = actors.get(name)
        step["who"] = actor_label(actors.get(name))
        step["note"] = notes.get(name)
        if name == "clarify" and open_questions:
            reasons.append({"task": None, "text": "Clarify: %s in spec.md %s still open." % (
                _count(open_questions, "question"), "is" if open_questions == 1 else "are")})
        elif name == "checklist":
            reasons.extend(_checklist_reasons(lists))
        status = logged[name]["status"] if name in logged else None
        if status == "in_progress" and step["state"] in ("pending", "skipped"):
            step["state"] = "active"
            step["fact"] = "started"
        elif status == "failed":
            step["state"] = "attention"
            note = step["note"]
            reasons.append({"task": None, "text": "%s: its last run failed%s" % (step["label"], ": " + note if note else ".")})
    return steps, reasons


# -- One spec ---------------------------------------------------------------------------------


def _relative_href(path, out_dir):
    return quote(os.path.relpath(str(path), str(out_dir)).replace(os.sep, "/"))


def collect_documents(root, directory, out_dir):
    paths = [(name, directory / name) for name in DOCUMENT_ORDER]
    for folder_name in ("checklists", "contracts"):
        folder = directory / folder_name
        if not folder.is_dir() or folder.is_symlink():
            continue
        found = sorted(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in CONTRACT_SUFFIXES)
        for path in found[:MAX_CONTRACT_FILES]:
            paths.append((path.relative_to(directory).as_posix(), path))
    paths.append((CONSTITUTION_DOCUMENT, root / ".specify" / "memory" / CONSTITUTION_DOCUMENT))
    documents = []
    budget = MAX_DOCS_TOTAL_BYTES
    for name, path in paths:
        text, truncated = read_limited(path, min(MAX_DOC_BYTES, max(budget, 0)))
        if text is None:
            continue
        budget -= len(text.encode("utf-8", errors="replace"))
        documents.append({
            "name": name,
            "markdown": path.suffix.lower() in (".md", ".markdown"),
            "text": text,
            "truncated": truncated,
            "href": _relative_href(path, out_dir),
        })
    return documents


def build_agents(tasks):
    rows = {}
    for task in tasks:
        label = task["who"] or "No record"
        row = rows.setdefault(label, {"label": label, "source": None, "done": 0, "active": []})
        if task["actor"] and row["source"] is None:
            row["source"] = task["actor"].get("source")
        if task["status"] == "done":
            row["done"] += 1
        elif task["status"] in ("in_progress", "blocked"):
            row["active"].append(task["id"])
    return [rows[key] for key in sorted(rows) if rows[key]["done"] or rows[key]["active"]]


def build_attention(tasks, parsed, bad_lines, tasks_truncated, log_truncated, refused_tasks, step_reasons=()):
    items = list(step_reasons)
    for task in tasks:
        if task["problem"]:
            items.append({"task": task["id"], "text": task["problem"]})
        elif task["status"] == "blocked" or task["status"] == "failed":
            last_note = task["notes"][-1]["note"] if task["notes"] else None
            text = task["status"].capitalize() + (": " + last_note if last_note else ".")
            items.append({"task": task["id"], "text": text})
        if task["older_history"]:
            count = len(task["older_history"])
            items.append({
                "task": task["id"],
                "text": "%d report%s for an earlier version of this task. The task's text has changed since."
                % (count, "" if count == 1 else "s"),
            })
    for task_id in parsed["duplicates"]:
        items.append({"task": task_id, "text": "This ID appears more than once in tasks.md."})
    count = len(parsed["unparsed"])
    if count:
        items.append({
            "task": None,
            "text": "%d checkbox line%s in tasks.md not counted, because the task format is not followed."
            % (count, "" if count == 1 else "s"),
        })
    if bad_lines:
        items.append({
            "task": None,
            "text": "%d line%s of the progress log could not be read." % (bad_lines, "" if bad_lines == 1 else "s"),
        })
    if tasks_truncated:
        items.append({"task": None, "text": "tasks.md is too large: only its first part was read."})
    if log_truncated:
        items.append({"task": None, "text": "The progress log is too large: only its first part was read."})
    if refused_tasks:
        items.append({"task": None, "text": "tasks.md is a symbolic link, so it was not read."})
    return items


def build_title(spec, directory):
    for _, line in visible_lines(spec):
        heading = parse_heading(line)
        if heading and heading[0] == 1:
            title = re.sub(r"^(?:Feature Specification|Specification|Spec)\s*:\s*", "", heading[1])
            if title and not _has_placeholder(title, SPEC_PLACEHOLDERS):
                return title
            break
    return directory.name


def build_feature(root, directory, out_dir, now=None, include_documents=True):
    """Build everything one page needs. Reads files only."""
    now = now or datetime.now(timezone.utc)
    spec, _ = read_limited(directory / "spec.md", MAX_DOC_BYTES)
    tasks_path = directory / "tasks.md"
    tasks_text, tasks_truncated = read_limited(tasks_path, MAX_TASKS_BYTES)
    if tasks_text and TASKS_PLACEHOLDER in tasks_text[:TEMPLATE_HEAD_CHARS]:
        tasks_text = None  # Still the template: its sample tasks are not this spec's work.
    parsed = parse_tasks(tasks_text)
    events, bad_lines, log_truncated = read_events(directory / LOG_NAME)

    by_task = {}
    for event in events:
        if event["kind"] == "task":
            by_task.setdefault(event["task"], []).append(event)
    phases = []
    every = []
    for phase in parsed["phases"]:
        views = [reconcile_task(task, by_task.get(task["id"], [])) for task in phase["tasks"]]
        every.extend(views)
        phases.append({"name": phase["name"], "goal": phase["goal"], "tasks": views})

    totals = {"total": len(every)}
    for status in ("done", "in_progress", "blocked", "failed", "skipped", "pending"):
        totals[status] = sum(1 for task in every if task["status"] == status)
    steps, step_reasons = build_steps(root, directory, phases, events, spec)

    data = {
        "schema": SCHEMA_VERSION,
        "id": directory.name,
        "title": build_title(spec, directory),
        "generated": now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "abandon_after_seconds": ABANDONED_AFTER_SECONDS,
        "totals": totals,
        "steps": steps,
        "phases": phases,
        "agents": build_agents(every),
        "attention": build_attention(
            every, parsed, bad_lines, tasks_truncated, log_truncated, tasks_path.is_symlink(), step_reasons
        ),
        "activity": list(reversed(events))[:ACTIVITY_LIMIT],
        "documents": collect_documents(root, directory, out_dir) if include_documents else [],
    }
    return data


def abandoned_tasks(data, now=None):
    now = now or datetime.now(timezone.utc)
    return [
        task["id"]
        for phase in data["phases"]
        for task in phase["tasks"]
        if is_abandoned(task, now)
    ]


# -- Finding specs ----------------------------------------------------------------------------


def _inside(root, path):
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def current_feature_dir(root):
    """The active spec, from the same sources as the scripts. Nothing outside the project counts."""
    raw = os.environ.get("SPECIFY_FEATURE_DIRECTORY", "")
    if not raw:
        text, _ = read_limited(root / ".specify" / "feature.json", 64 * 1024)
        if text:
            try:
                stored = json.loads(text)
            except ValueError:
                stored = None
            value = stored.get("feature_directory") if isinstance(stored, dict) else None
            raw = value if isinstance(value, str) else ""
    if not raw and os.environ.get("SPECIFY_FEATURE"):
        raw = str(Path("specs") / os.environ["SPECIFY_FEATURE"])
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    if path.is_symlink() or not path.is_dir() or not _inside(root, path):
        return None
    if path.resolve() == root.resolve():
        return None
    return path


def discover_features(root):
    """Every spec of the project. specs/_capabilities is the catalog, not a spec."""
    found = []
    specs = root / "specs"
    if specs.is_dir() and not specs.is_symlink():
        for path in sorted(specs.iterdir(), key=lambda item: item.name):
            if path.is_dir() and not path.is_symlink() and not path.name.startswith(("_", ".")):
                found.append(path)
    current = current_feature_dir(root)
    if current is not None and all(current.resolve() != path.resolve() for path in found):
        found.append(current)
    return found


def find_feature(root, reference):
    """Resolve a directory name or a unique prefix of one, such as 002."""
    features = discover_features(root)
    exact = [path for path in features if path.name == reference]
    if exact:
        return exact[0]
    matches = [path for path in features if path.name.startswith(reference)]
    if len(matches) == 1:
        return matches[0]
    names = ", ".join(path.name for path in features) or "none"
    if matches:
        raise ProgressError("'%s' matches more than one spec. Specs: %s" % (reference, names))
    raise ProgressError("No spec named '%s'. Specs: %s" % (reference, names))


# -- Drawing ----------------------------------------------------------------------------------


def as_script_json(data):
    """JSON that cannot end its <script> block, whatever a task or a note says."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for char, escape in (
        ("&", "\\u0026"),
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        text = text.replace(char, escape)
    return text


def fill_template(template, data):
    if DATA_PLACEHOLDER not in template:
        raise ProgressError("The page template has no place for its data.")
    return template.replace(DATA_PLACEHOLDER, as_script_json(data), 1)


def _load_template(name):
    path = Path(__file__).resolve().with_name(name)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProgressError("Cannot read the page template %s: %s" % (name, exc))


def ensure_output_dir(root):
    specify = root / ".specify"
    if not specify.is_dir() or specify.is_symlink():
        raise ProgressError("%s is not a Spec Kit project: it has no .specify/ directory." % root)
    out_dir = root / OUTPUT_DIR
    if out_dir.is_symlink():
        raise ProgressError("%s is a symbolic link. Refusing to write through it." % out_dir)
    if out_dir.exists() and not out_dir.is_dir():
        raise ProgressError("%s exists and is not a directory." % out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ignore = out_dir / ".gitignore"
    if not ignore.exists():
        write_atomic(ignore, "# Generated by Spec Kit. The history lives in specs/<feature>/progress.jsonl.\n*\n")
    return out_dir


def _stamp(moment):
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _replace(temporary, path):
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            os.replace(temporary, str(path))
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_WAIT_SECONDS)


def _new_temporary_file(folder):
    """A new file only this process can read, next to its target so the rename is atomic. It does
    what tempfile.mkstemp does, because importing tempfile costs a hook about 10 ms on every redraw.
    O_EXCL also refuses a link left under that name, and O_BINARY keeps Windows off the bytes."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    while True:
        temporary = os.path.join(str(folder), ".tmp-%s-%s" % (GENERATOR, os.urandom(8).hex()))
        try:
            return os.open(temporary, flags, 0o600), temporary
        except FileExistsError:
            continue


def write_atomic_bytes(path, data, mode=0o644):
    """Write through a temporary file, so a reader never sees half a file."""
    handle, temporary = _new_temporary_file(path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        try:
            os.chmod(temporary, mode)
        except OSError:
            pass
        _replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def write_atomic(path, text):
    write_atomic_bytes(path, text.encode("utf-8"))


# A slice map is specs/_slices/<name>.md, written by the capabilities extension: the slices of a
# larger request, in order. A spec names the slice it builds in its "## Slice" section, and the
# list of specs groups them by map. The engine reads those files itself, by the rules of the
# extension, so a redraw starts no other process.
SLICE_MAPS_DIR = "_slices"
SLICE_MAP_FORMAT = 1
DELTA_LOCK = "capability-delta.lock.json"
_SLICE_MAP_MARK = re.compile(r"<!-- slice-map:v(\d+) -->")
_SLICE_ID = re.compile(r"D-[a-z0-9]+(?:-[a-z0-9]+)*")
_SLICE_FIELD = re.compile(r"^- ([A-Za-z-]+): (.*)$")
_DELTA_MARK = "<!-- capability-delta:v1 -->"
_DELTA_ENTRY = re.compile(r"^### (?:ADDED|MODIFIED|REMOVED|INFERRED|VALIDATED|DESIGNED|IMPLEMENTED) R-[a-z0-9-]+\s*$", re.M)
_CONFLICT_SIDE = re.compile(r"^(?:<{7}|>{7})(?: |$)", re.M)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def _section(text, title):
    """The ``## <title>`` section of a document, up to the next ``## `` heading, or None."""
    match = re.search(r"^## " + re.escape(title) + r".*$", text, re.M)
    if not match:
        return None
    following = re.search(r"^## ", text[match.end():], re.M)
    return text[match.start():(match.end() + following.start()) if following else len(text)]


def read_slice_maps(root):
    """Every slice map of the project, in file order, with its slices in the order they were written.

    A map this engine cannot read is left out, and its specs are listed like any other spec: a
    link, a map with no marker or of a newer format, or one with conflict markers.
    """
    directory = Path(root) / "specs" / SLICE_MAPS_DIR
    try:
        if directory.is_symlink() or not directory.is_dir():
            return []
        paths = sorted(directory.glob("*.md"), key=lambda item: item.name)
    except OSError:
        return []
    maps = []
    for path in paths:
        text, truncated = read_limited(path, MAX_DOC_BYTES)
        if not text or truncated or _CONFLICT_SIDE.search(text):
            continue
        versions = [int(number) for number in _SLICE_MAP_MARK.findall(text)]
        if not versions or max(versions) > SLICE_MAP_FORMAT:
            continue
        found = {"name": path.stem, "request": "", "slices": []}
        current, fields, top = None, set(), True
        for line in _HTML_COMMENT.sub("", text).splitlines():
            if line.startswith("### "):
                slice_id, _, title = line[4:].strip().partition(" ")
                current, fields = None, set()
                if _SLICE_ID.fullmatch(slice_id):
                    current = {"id": slice_id, "title": title.strip(), "dropped": False, "depends_on": []}
                    found["slices"].append(current)
                continue
            if line.startswith("## "):
                current, top = None, False
                continue
            if current is None:
                if top and line.startswith("Request: "):
                    found["request"] = " ".join(line[len("Request: "):].split())
                continue
            match = _SLICE_FIELD.match(line)
            if not match or match.group(1).lower() in fields:
                continue  # A field counts once, as its first line.
            key, value = match.group(1).lower(), " ".join(match.group(2).split())
            fields.add(key)
            if key == "dropped":
                current["dropped"] = bool(value)
            elif key == "depends-on":
                current["depends_on"] = [part.strip() for part in value.split(",") if _SLICE_ID.fullmatch(part.strip())]
        if found["slices"]:
            maps.append(found)
    return maps


def spec_slice(directory):
    """(the slice a spec says it builds, or None; how far that spec is).

    A spec is ``specified`` until it has tasks, then ``building``, and ``delivered`` once every task
    is closed and, when the spec changes rules, its delta is folded into the catalog. The lock of
    the spec records the fold.
    """
    spec = read_limited(directory / "spec.md", MAX_DOC_BYTES)[0] or ""
    declared = None
    section = _section(_HTML_COMMENT.sub("", spec), "Slice")
    for line in section.splitlines()[1:] if section else ():
        match = _SLICE_FIELD.match(line)
        if match and match.group(1).lower() == "slice":
            value = " ".join(match.group(2).split())
            declared = value if _SLICE_ID.fullmatch(value) else None
            break
    lock = read_limited(directory / DELTA_LOCK, MAX_DOC_BYTES)[0]
    try:
        folded = bool(json.loads(lock).get("fold")) if lock else False
    except (ValueError, AttributeError):
        folded = False
    tasks = read_limited(directory / "tasks.md", MAX_TASKS_BYTES)[0]
    if tasks is None:
        return declared, "delivered" if folded else "specified"
    delta = _section(spec, "Capability Delta") if spec.count(_DELTA_MARK) == 1 and len(re.findall(r"^## Capability Delta", spec, re.M)) == 1 else None
    changes_rules = bool(delta) and _DELTA_MARK in delta and bool(_DELTA_ENTRY.search(_HTML_COMMENT.sub("", delta)))
    closed = not re.search(r"^\s*- \[ \]", tasks, re.M)
    return declared, "delivered" if closed and (folded or not changes_rules) else "building"


def slice_groups(maps, specs):
    """The maps as the list of specs shows them. ``specs`` holds (spec id, declared slice, state), in the order of the list."""
    claimed, known = {}, {}
    for spec_id, declared, state in specs:
        if declared:
            claimed.setdefault(declared, (spec_id, state))  # One spec builds one slice: the first one counts.
    for found in maps:
        for item in found["slices"]:
            known.setdefault(item["id"], item)

    def state_of(item):
        if item["dropped"]:
            return "dropped"
        return claimed[item["id"]][1] if item["id"] in claimed else "pending"

    groups = []
    for found in maps:
        views = []
        for item in found["slices"]:
            views.append({
                "id": item["id"],
                "title": item["title"],
                "state": state_of(item),
                "spec": claimed[item["id"]][0] if item["id"] in claimed else None,
                # A slice waits for the ones it depends on until they are delivered.
                "waiting_for": [dep for dep in item["depends_on"] if dep not in known or state_of(known[dep]) != "delivered"],
            })
        counted = [view for view in views if view["state"] != "dropped"]
        ready = [view["id"] for view in views if view["state"] == "pending" and not view["waiting_for"]]
        groups.append({
            "name": found["name"],
            "request": found["request"],
            "slices": views,
            "total": len(counted),
            "delivered": sum(1 for view in counted if view["state"] == "delivered"),
            "next": ready[0] if ready else None,
        })
    return groups


def project_slices(root):
    """The slice maps of a project, each slice with its state and the spec that builds it. Reads files only."""
    maps = read_slice_maps(root)
    if not maps:
        return []
    return slice_groups(maps, [(path.name,) + spec_slice(path) for path in discover_features(Path(root))])


# The design of the product is specs/_product/, written with the studio extension. The script of
# that extension knows what those files mean, so the engine loads it from the project and asks it;
# the engine adds the log, the documents and the page. Reading a design costs about as much as a
# whole redraw, so its page is drawn when the design or every page is asked for, and not after
# each task: then the list of specs shows the summary of the last time it was drawn.
DESIGN_DIR = Path("specs") / "_product"
DESIGN_MARK = "product.md"
DESIGN_TEMPLATE = "design.html"
DESIGN_SUMMARY = ".design.json"
STUDIO_SCRIPT = Path(".specify") / "extensions" / "studio" / "scripts" / "python" / "studio.py"
INIT_OPTIONS = Path(".specify") / "init-options.json"
_DOCUMENT_NAME = re.compile(r"^[a-z][a-z0-9-]*\.md$")
_STUDIO_MODULES = {}


def has_design(root):
    """True when the project keeps the design of a product."""
    directory = Path(root) / DESIGN_DIR
    return not directory.is_symlink() and (directory / DESIGN_MARK).is_file()


def load_studio(root):
    """The script of the studio extension as a module, or None when the project does not have it."""
    path = Path(root) / STUDIO_SCRIPT
    if path.is_symlink() or not path.is_file():
        return None
    key = str(path)
    if key not in _STUDIO_MODULES:
        import importlib.util  # Only here: most projects have no design to read.

        spec = importlib.util.spec_from_file_location("speckit_studio_script", key)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _STUDIO_MODULES[key] = module
    return _STUDIO_MODULES[key]


def command_text(root, name, args=""):
    """A command as the person types it: with hyphens where commands are skills, with dots elsewhere."""
    text, _ = read_limited(Path(root) / INIT_OPTIONS, 64 * 1024)
    try:
        options = json.loads(text) if text else {}
    except ValueError:
        options = {}
    skills = isinstance(options, dict) and options.get("ai_skills") is True
    shown = "/" + (name.replace(".", "-") if skills else name)
    return shown + (" " + args if args else "")


def _is_running(event, now):
    """A step somebody started and nobody closed, unless that was so long ago that its session is gone."""
    if not event or event["status"] != "in_progress":
        return False
    started = parse_timestamp(event.get("ts"))
    return started is not None and (now - started).total_seconds() <= ABANDONED_AFTER_SECONDS


def _area_fact(area, name):
    if area["steps"].get(name) == "pending":
        return "not yet"
    if name == "map":
        fact = "%d %s" % (area["stories"], "story" if area["stories"] == 1 else "stories")
        return fact + (", %d waiting" % area["asked"] if area["asked"] else "")
    return "%d of %s" % (area["pages"], _count(area["screens"], "screen"))


def build_design(root, out_dir, now=None, include_documents=True):
    """Everything the page of the design needs, or None when the project has no design to show."""
    root = Path(root)
    if not has_design(root):
        return None
    now = now or datetime.now(timezone.utc)
    directory = root / DESIGN_DIR
    data = {"schema": SCHEMA_VERSION, "generated": _stamp(now), "product": "", "problem": None}
    try:
        studio = load_studio(root)
        if studio is None:
            return None
        status = studio.status(studio.Product(root))
    except Exception as exc:  # A design nobody can read must not take the pages of the specs with it.
        data["problem"] = plain_text(exc, MAX_NOTE_CHARS) or type(exc).__name__
        return data
    events, bad_lines, log_truncated = read_events(directory / LOG_NAME)
    events = [event for event in events if event["kind"] == "step"]
    last, last_in_area, noted = {}, {}, {}
    for event in events:
        last[event["step"]] = event
        if event.get("area"):
            last_in_area[(event["step"], event["area"])] = event
        if event["status"] == "done" and event.get("note"):
            noted[event["step"]] = event["note"]
    titles = {area["id"]: area["title"] for area in status["areas"]}

    steps = []
    for step in status["steps"]:
        event = last.get(step["name"])
        running = _is_running(event, now)
        steps.append({
            "name": step["name"],
            "label": step["name"].capitalize(),
            "command": command_text(root, step["command"]),
            "state": "active" if running and step["state"] == "pending" else step["state"],
            "fact": step["fact"],
            "running": running,
            "note": noted.get(step["name"]),
            "who": actor_label(event.get("actor")) if event else None,
            "ts": event["ts"] if event else None,
        })
    areas = []
    for area in status["areas"]:
        chips = []
        for name in area["steps"]:
            running = _is_running(last_in_area.get((name, area["id"])), now)
            state = area["steps"][name]
            chips.append({"name": name, "label": name.capitalize(), "state": "active" if running and state == "pending" else state,
                          "fact": _area_fact(area, name), "running": running})
        areas.append({
            "id": area["id"], "title": area["title"], "covers": area["covers"], "state": area["state"], "screens": area["screens"],
            "rules": area["rules"], "open": area["open"], "steps": chips, "command": command_text(root, "speckit.studio.map", area["id"]),
        })
    attention = list(status["attention"])
    if bad_lines:
        attention.append({"kind": "log", "text": "%s of the design's log could not be read." % _count(bad_lines, "line")})
    if log_truncated:
        attention.append({"kind": "log", "text": "The design's log is too large: only its first part was read."})
    activity = []
    for event in list(reversed(events))[:ACTIVITY_LIMIT]:
        activity.append({"step": event["step"], "status": event["status"], "ts": event["ts"], "note": event.get("note"),
                         "area": event.get("area"), "area_title": titles.get(event.get("area"))})
    documents, links = [], []
    if include_documents:
        budget = MAX_DOCS_TOTAL_BYTES
        for name in status["documents"]:
            if not isinstance(name, str) or not _DOCUMENT_NAME.match(name):
                continue
            path = directory / name
            text, truncated = read_limited(path, min(MAX_DOC_BYTES, max(budget, 0)))
            if text is None:
                continue
            budget -= len(text.encode("utf-8", errors="replace"))
            documents.append({"name": name, "markdown": True, "text": text, "truncated": truncated, "href": _relative_href(path, out_dir)})
        mockup = directory / "mockup" / "index.html"
        if status["mockup"] and mockup.is_file():
            links.append({"label": "Open the mockup", "href": _relative_href(mockup, out_dir)})
        looks = directory / "mockup" / "_studio" / "directions.html"
        if looks.is_file() and not looks.is_symlink():
            links.append({"label": "Compare the looks", "href": _relative_href(looks, out_dir)})
    step = status["next"]
    data.update({
        "product": status["product"] or "",
        "owner": status["owner"],
        "totals": status["totals"],
        "steps": steps,
        "areas": areas,
        "summary": status["summary"],
        "next": {"command": command_text(root, step["command"], step["args"]), "why": step["why"]},
        "attention": attention,
        "activity": activity,
        "documents": documents,
        "links": links,
        "screens": status["totals"]["screens"],
    })
    return data


def design_summary(data):
    """What the list of specs and the terminal say about the design: little, and no document."""
    if data is None:
        return None
    summary = {"file": DESIGN_TEMPLATE, "generated": data["generated"], "product": data["product"], "problem": data["problem"]}
    if not data["problem"]:
        summary.update({
            "totals": {key: data["totals"][key] for key in ("areas", "drawn", "in_design", "not_started")},
            "steps": [{"label": step["label"], "state": step["state"], "fact": step["fact"]} for step in data["steps"]],
            "next": data["next"],
            "attention": len(data["attention"]),
        })
    return summary


def stored_design_summary(root, out_dir):
    """The summary of the last time the design was drawn, for a redraw that does not read the design."""
    if not has_design(root):
        return None
    text, _ = read_limited(out_dir / DESIGN_SUMMARY, 256 * 1024)
    try:
        summary = json.loads(text) if text else None
    except ValueError:
        return None
    return summary if isinstance(summary, dict) and summary.get("file") == DESIGN_TEMPLATE else None


def design_lines(summary, link=None):
    """How far the design is and what comes next, for the end of a command and for the terminal."""
    if summary["problem"]:
        lines = ["The design cannot be read: %s" % plain_text(summary["problem"], MAX_NOTE_CHARS)]
    else:
        lines = ["Design of %s" % plain_text(summary["product"]),
                 "Steps: " + "; ".join("%s: %s" % (step["label"], plain_text(step["fact"])) for step in summary["steps"]),
                 "Next: %s. %s" % (plain_text(summary["next"]["command"]), plain_text(summary["next"]["why"], MAX_NOTE_CHARS))]
        if summary["attention"]:
            lines.append("Needs attention: %d, see the page" % summary["attention"])
    if link:
        lines.append("Page: " + link)
    return lines


def design_status(root, now=None):
    """Read-only summary of the design for machines and for terminals, or None. Writes nothing."""
    root = Path(root)
    return design_summary(build_design(root, root / OUTPUT_DIR, now=now, include_documents=False))


def page_file_names(features):
    """One safe, unique file name per spec. index.html belongs to the list of specs, design.html to the design."""
    names = {}
    used = {INDEX_TEMPLATE.lower(), DESIGN_TEMPLATE.lower()}
    for path in features:
        stem = _SAFE_FILE.sub("_", path.name).strip("._") or "spec"
        candidate = stem + ".html"
        counter = 2
        while candidate.lower() in used:
            candidate = "%s-%d.html" % (stem, counter)
            counter += 1
        used.add(candidate.lower())
        names[str(path)] = candidate
    return names


def _summary(data, file_name, current, declared=None):
    return {
        "id": data["id"],
        "title": data["title"],
        "file": file_name,
        "current": current,
        "generated": data["generated"],
        "attention": len(data["attention"]),
        "totals": data["totals"],
        "slice": declared,
    }


def _remove_orphan_pages(out_dir, keep):
    """Drop pages of specs that no longer exist. Only pages this engine wrote are touched."""
    marker = ('name="generator" content="%s"' % GENERATOR).encode("ascii")
    for path in out_dir.glob("*.html"):
        if path.name in keep or path.is_symlink():
            continue
        try:
            # Closed first: Windows refuses to remove a file that is still open.
            with path.open("rb") as stream:
                ours = marker in stream.read(1024)
            if ours:
                path.unlink()
        except OSError:
            pass


def render_project(root, feature=None, now=None):
    """Draw the pages. With a feature, only that page and the list of specs are rewritten."""
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    out_dir = ensure_output_dir(root)
    features = discover_features(root)
    if feature is not None and all(feature.resolve() != path.resolve() for path in features):
        features.append(feature)
    names = page_file_names(features)
    current = current_feature_dir(root)
    current_key = current.resolve() if current is not None else None
    page = _load_template(PAGE_TEMPLATE)
    maps = read_slice_maps(root)
    summaries = []
    pages = []
    sliced = []
    for path in features:
        file_name = names[str(path)]
        draw = feature is None or feature.resolve() == path.resolve()
        data = build_feature(root, path, out_dir, now=now, include_documents=draw)
        is_current = current_key is not None and path.resolve() == current_key
        # Without a map no spec is read a second time.
        declared, state = spec_slice(path) if maps else (None, None)
        sliced.append((data["id"], declared, state))
        summaries.append(_summary(data, file_name, is_current, declared))
        if draw:
            target = out_dir / file_name
            write_atomic(target, fill_template(page, data))
            pages.append({"id": data["id"], "path": str(target), "current": is_current, "totals": data["totals"]})
    design = None
    if feature is None:
        data = build_design(root, out_dir, now=now)
        design = design_summary(data)
        if data is not None:
            write_atomic(out_dir / DESIGN_TEMPLATE, fill_template(_load_template(DESIGN_TEMPLATE), data))
            write_atomic(out_dir / DESIGN_SUMMARY, json.dumps(design, ensure_ascii=True))
    else:
        design = stored_design_summary(root, out_dir)
    index = out_dir / INDEX_TEMPLATE
    write_atomic(index, fill_template(_load_template(INDEX_TEMPLATE), {
        "generated": _stamp(now),
        "specs": summaries,
        "maps": slice_groups(maps, sliced),
        "design": design,
    }))
    if feature is None:
        _remove_orphan_pages(out_dir, set(names.values()) | {INDEX_TEMPLATE} | ({DESIGN_TEMPLATE} if design else set()))
        if design is None:
            try:
                (out_dir / DESIGN_SUMMARY).unlink()
            except OSError:
                pass
    return {"out_dir": str(out_dir), "index": str(index), "pages": pages,
            "design": {"path": str(out_dir / DESIGN_TEMPLATE), "summary": design} if design else None}


def can_open_browser(env=None, platform=None):
    """False when a browser would open where the person cannot see it: CI, SSH, no display."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if env.get("CI", "").strip().lower() not in ("", "0", "false"):
        return False
    if env.get("SSH_CONNECTION") or env.get("SSH_CLIENT") or env.get("SSH_TTY"):
        return False
    if platform.startswith("linux") and not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        return False
    return True


# -- Recording a step -------------------------------------------------------------------------


def step_belongs_to_spec(name, status):
    """The constitution belongs to the project. A /speckit.specify that is only starting has no
    spec yet: feature.json still names the previous one, which did not take this step."""
    if name == "constitution":
        return False
    return not (name == "specify" and status == "in_progress")


def make_actor(harness=None, agent=None):
    """Who is writing, as far as this process knows. A name the model gave counts as declared."""
    actor = {}
    if isinstance(harness, str) and _HARNESS_NAME.match(harness):
        actor["harness"] = harness
    name = plain_text(agent.strip()) if isinstance(agent, str) else ""
    if name:
        actor["agent"] = name
    if not actor:
        return None
    actor["source"] = "declared" if name else "configured"
    return actor


def _with_note_and_actor(event, note, actor):
    text = note.strip() if isinstance(note, str) else ""
    if text:
        event["note"] = text[:MAX_NOTE_CHARS]
    if actor:
        event["actor"] = actor
    return event


def make_step_event(name, status, harness=None, note=None, now=None):
    event = {"v": SCHEMA_VERSION, "ts": _stamp(now or datetime.now(timezone.utc)), "kind": "step", "step": name, "status": status}
    return _with_note_and_actor(event, note, make_actor(harness))


def _ensure_union_merge(directory):
    """Two branches that both add to the log keep both sets of lines instead of a conflict."""
    path = directory / ATTRIBUTES_NAME
    if path.is_symlink():
        return
    line = LOG_NAME + " merge=union\n"
    existing, _ = read_limited(path, 64 * 1024)
    if existing is None:
        if not path.exists():
            write_atomic(path, line)
    elif LOG_NAME not in existing:
        write_atomic(path, existing + ("" if existing.endswith("\n") else "\n") + line)


def _ends_mid_line(path):
    """True when the last write was cut short, so the next line must not continue it."""
    try:
        with path.open("rb") as stream:
            stream.seek(-1, os.SEEK_END)
            return stream.read(1) != b"\n"
    except OSError:
        return False


def append_event(directory, event):
    """Add one line to the spec's log, as one write. Never through a link, never to a non-file."""
    path = directory / LOG_NAME
    if path.is_symlink():
        raise ProgressError("%s is a symbolic link. Refusing to write through it." % path)
    if path.exists() and not path.is_file():
        raise ProgressError("%s is not a file." % path)
    _ensure_union_merge(directory)
    data = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8", "replace")
    if _ends_mid_line(path):
        data = b"\n" + data
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    handle = os.open(str(path), flags, 0o644)
    try:
        os.write(handle, data)
    finally:
        os.close(handle)


# -- Recording a task -------------------------------------------------------------------------


def clean_file_names(values):
    """--files takes a list, a comma-separated list, or both."""
    names = []
    for value in values or ():
        for name in value.split(","):
            name = plain_text(name.strip(), MAX_FILE_NAME_CHARS)
            if name and name not in names:
                names.append(name)
    return names[:MAX_FILES_PER_EVENT]


def make_task_event(name, status, text, harness=None, agent=None, note=None, files=None, now=None):
    event = {"v": SCHEMA_VERSION, "ts": _stamp(now or datetime.now(timezone.utc)), "kind": "task", "task": name, "status": status}
    if files:
        event["files"] = files
    event["text_sha"] = task_text_sha(text)
    return _with_note_and_actor(event, note, make_actor(harness, agent))


def _try_lock(handle):
    try:
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            msvcrt.locking(handle, msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES, errno.EDEADLK):
            return False
        raise
    return True


def _unlock(handle):
    if fcntl is not None:
        fcntl.flock(handle, fcntl.LOCK_UN)
    else:
        msvcrt.locking(handle, msvcrt.LK_UNLCK, 1)


@contextlib.contextmanager
def spec_lock(root, feature, timeout=None):
    """Only one writer per spec at a time. The system drops the lock when a process ends, however
    it ends, so a crash never leaves a spec locked."""
    name = hashlib.sha256(str(feature.resolve()).encode("utf-8", "replace")).hexdigest()[:16]
    path = ensure_output_dir(root) / (LOCK_PREFIX + name)
    if path.is_symlink():
        raise ProgressError("%s is a symbolic link. Refusing to write through it." % path)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    handle = os.open(str(path), flags, 0o644)
    try:
        limit = LOCK_TIMEOUT_SECONDS if timeout is None else timeout
        deadline = time.monotonic() + limit
        while not _try_lock(handle):
            if time.monotonic() >= deadline:
                raise ProgressError("Another agent held %s for %d seconds." % (feature.name, limit))
            time.sleep(LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            _unlock(handle)
    finally:
        os.close(handle)


def read_task_file(feature):
    """Return the exact bytes of tasks.md, for a change that must leave every other byte alone."""
    path = feature / "tasks.md"
    if path.is_symlink():
        raise ProgressError("%s is a symbolic link. Refusing to write through it." % path)
    if not path.is_file():
        raise ProgressError("%s does not exist yet." % path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_TASKS_BYTES + 1)
    if len(raw) > MAX_TASKS_BYTES:
        raise ProgressError("%s is over %d bytes." % (path, MAX_TASKS_BYTES))
    return raw


def find_task(parsed, name):
    """The one task with this id. Refuses a missing or repeated id, and writes nothing."""
    found = [task for phase in parsed["phases"] for task in phase["tasks"] if task["id"] == name]
    if len(found) > 1:
        lines = ", ".join(str(task["line"]) for task in found)
        raise ProgressError("%s appears %d times in tasks.md, on lines %s." % (name, len(found), lines))
    if found:
        return found[0]
    ids = [task["id"] for phase in parsed["phases"] for task in phase["tasks"]]
    listed = " ".join(ids[:MAX_IDS_SHOWN]) + (" and %d more" % (len(ids) - MAX_IDS_SHOWN) if len(ids) > MAX_IDS_SHOWN else "")
    raise ProgressError("%s is not in tasks.md. Valid ids: %s" % (plain_text(name, 40), listed or "none"))


def check_box(raw, number):
    """Return tasks.md with the box on this line checked. Every other byte stays: its line endings,
    its byte order mark, and anything that is not valid UTF-8."""
    start = 3 if raw.startswith(b"\xef\xbb\xbf") else 0
    for _ in range(number - 1):
        start = _LINE_BREAK_BYTES.search(raw, start).end()
    match = _LINE_BREAK_BYTES.search(raw, start)
    end = match.start() if match else len(raw)
    box = _CHECKBOX.match(raw[start:end].decode("utf-8", "replace"))
    position = start + len(box.string[:box.start(1)].encode("utf-8"))
    return raw[:position] + b"X" + raw[position + 1:]


def _mark_done(feature, raw, task):
    path = feature / "tasks.md"
    if not os.access(str(path), os.W_OK):
        raise ProgressError("%s is read-only." % path)
    write_atomic_bytes(path, check_box(raw, task["line"]), stat.S_IMODE(path.stat().st_mode))


def run_task_command(root, command, name, harness=None, agent=None, note=None, files=None, then=None, reference=None):
    """Record what happened to a task. Unlike a step, a failure here is reported as one, because
    the model has to know the box is still empty and mark it by hand."""
    feature = find_feature(root, reference) if reference else current_feature_dir(root)
    if feature is None:
        raise ProgressError("There is no current spec.")
    status = TASK_COMMANDS[command]
    problems = []
    with spec_lock(root, feature):
        raw = read_task_file(feature)
        parsed = parse_tasks(raw.decode("utf-8-sig", "replace"))
        task = find_task(parsed, name)
        following = find_task(parsed, then) if then else None
        if status == "done" and not task["checked"]:
            _mark_done(feature, raw, task)
        try:
            append_event(feature, make_task_event(name, status, task["text"], harness, agent, note, clean_file_names(files)))
            if following:
                append_event(feature, make_task_event(then, "in_progress", following["text"], harness, agent))
        except (ProgressError, OSError) as exc:
            if status != "done":
                raise
            problems.append(str(exc))  # The box is what counts, and the box is marked.
        drawn = _draw(root, feature, problems)
    if drawn and drawn["pages"]:
        open_once(root, drawn["pages"][0]["path"])
    report = "%s %s." % (name, TASK_REPORTS[status])
    if following:
        report += " %s %s." % (then, TASK_REPORTS["in_progress"])
    if drawn and drawn["pages"]:
        totals = drawn["pages"][0]["totals"]
        report += " %d of %d tasks done." % (totals["done"], totals["total"])
    _say(report)
    if status in ("in_progress", "blocked", "failed", "skipped") and task["checked"]:
        _say("%s is still checked in tasks.md, so it counts as done until you empty its box." % name)
    for problem in problems:
        _say("progress: %s" % plain_text(problem, MAX_NOTE_CHARS), sys.stderr)
    return 0


# -- What a harness runs by itself ------------------------------------------------------------


def _first_text(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def read_harness_message(raw):
    """Return (shell command, session, agent) from a hook's message, whichever harness sent it.

    Each harness names these differently. See tests/specify_cli/progress/test_hook_payloads.py for
    what each one sends. Only these three are read: the rest can hold anything, and none of it is
    ever stored."""
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return None, None, None
    if not isinstance(data, dict):
        return None, None, None
    wrapped = data.get("input") if isinstance(data.get("input"), dict) else {}  # OpenCode.
    result = data.get("output") if isinstance(data.get("output"), dict) else {}
    arguments = data.get("tool_input", data.get("toolArgs", wrapped.get("args", result.get("args"))))
    if isinstance(arguments, str):  # Copilot may send them as text.
        try:
            arguments = json.loads(arguments)
        except ValueError:
            arguments = {"command": arguments}
    command = _first_text(arguments.get("command")) if isinstance(arguments, dict) else None
    session = _first_text(data.get("session_id"), data.get("sessionId"), data.get("conversation_id"), wrapped.get("sessionID"))
    agent = _first_text(data.get("agent_id"), data.get("agentId"))
    return command, session, agent


def calls_in(command):
    """The task reports a shell command made, in order: [(task, status)]. --then reports two.

    Models often batch them, with the script in a variable or a function, so this looks for the
    words and not for the script's name. Something that only looks like a report attaches to
    nothing, or to a report of that very status: see apply_seen."""
    if not command or "progress." not in command:
        return []
    found = list(_PROGRESS_CALL.finditer(command))
    calls = []
    for index, match in enumerate(found):
        calls.append((match.group(2), TASK_COMMANDS[match.group(1)]))
        end = found[index + 1].start() if index + 1 < len(found) else len(command)
        following = _THEN_OPTION.search(command, match.end(), end) if match.group(1) == "done" else None
        if following:
            calls.append((following.group(1), "in_progress"))
    return calls


def make_seen_event(name, status, harness, session, agent, now=None):
    actor = {"source": "observed"}
    if isinstance(harness, str) and _HARNESS_NAME.match(harness):
        actor["harness"] = harness
    if session:
        actor["session"] = plain_text(session, SESSION_CHARS)
    if agent:
        actor["agent"] = plain_text(agent)
    return {"v": SCHEMA_VERSION, "ts": _stamp(now or datetime.now(timezone.utc)), "kind": "seen", "task": name, "status": status, "actor": actor}


def run_hook(root, harness, event, raw, now=None):
    """Note who made a report, redraw the page, and at the start of a session say where it stands.
    Returns the line for the model's context. It never holds a note: those can say anything."""
    root = Path(root)
    feature = current_feature_dir(root)
    if feature is None:
        return ""
    if event == "post_tool_use" and len(raw) <= MAX_HOOK_BYTES:
        command, session, agent = read_harness_message(raw)
        for name, status in calls_in(command):
            append_event(feature, make_seen_event(name, status, harness, session, agent, now))
    drawn = None
    try:
        with spec_lock(root, feature, timeout=0):
            drawn = render_project(root, feature, now)
    except ProgressError:
        pass  # Whoever holds the lock is about to draw it, or the next tool call will.
    if event != "session_start" or not drawn or not drawn["pages"]:
        return ""
    page = drawn["pages"][0]
    if not page["totals"]["total"]:
        return ""
    return "Spec Kit progress for %s: %d of %d tasks done. Page: %s\n" % (
        plain_text(page["id"]),
        page["totals"]["done"],
        page["totals"]["total"],
        Path(page["path"]).resolve().as_uri(),
    )


# -- Watching from another terminal -----------------------------------------------------------


def _source_dates(feature):
    dates = {}
    for name in ("tasks.md", LOG_NAME, "spec.md", "plan.md"):
        try:
            dates[name] = (feature / name).stat().st_mtime_ns
        except OSError:
            pass
    return dates


def watch_round(root, reference, last):
    """One look. Return (what was seen, the line to show if the page was redrawn)."""
    feature = find_feature(root, reference) if reference else current_feature_dir(root)
    if feature is None:
        return None, None
    seen = (str(feature), _source_dates(feature))
    if seen == last:
        return last, None
    try:
        with spec_lock(root, feature, timeout=0):
            drawn = render_project(root, feature)
    except ProgressError:
        return last, None  # Busy. The next look finds the change still there.
    page = drawn["pages"][0]
    totals = page["totals"]
    return seen, "%s: %d of %d tasks done" % (plain_text(page["id"]), totals["done"], totals["total"])


# -- Showing it to the person -----------------------------------------------------------------


def browser_is_off(root, env=None):
    env = os.environ if env is None else env
    if env.get(BROWSER_OFF_ENV, "").strip().lower() not in ("", "0", "false"):
        return True
    return (root / OUTPUT_DIR / BROWSER_OFF_FILE).exists()


def set_browser(root, enabled):
    """Turn the automatic opening on or off for this project. The pages are still drawn."""
    marker = ensure_output_dir(root) / BROWSER_OFF_FILE
    if enabled:
        if marker.exists():
            marker.unlink()
    else:
        write_atomic(marker, "Spec Kit does not open progress pages by itself here.\n")


def open_in_background(link):
    """In its own process, so a browser that hangs cannot hang the command that asked for it."""
    import subprocess  # Only here: a hook loads this file after every tool call.

    subprocess.Popen(
        [sys.executable, "-I", "-c", "import sys, webbrowser; webbrowser.open(sys.argv[1])", link],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )


def open_once(root, page, env=None, opener=None):
    """Open a spec's page the first time it is drawn, and only where the person can see it."""
    if browser_is_off(root, env) or not can_open_browser(env):
        return False
    page = Path(page)
    marker = root / OUTPUT_DIR / (OPENED_PREFIX + page.stem)
    try:
        os.close(os.open(str(marker), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644))
    except OSError:
        return False
    try:
        (opener or open_in_background)(page.resolve().as_uri())
    except (OSError, ValueError):
        return False
    return True


def open_now(root, link, env=None, opener=None):
    """Open a page because the person asked to see it: every time, unless opening pages is turned
    off here or nobody would see the browser. Returns the line that tells them what happened."""
    if browser_is_off(root, env):
        return "Not opened: pages are set not to open here. Open the link above."
    if not can_open_browser(env):
        return "Not opened: nobody would see a browser here (CI, SSH or no display). Open the link above."
    try:
        (opener or open_in_background)(link)
    except (OSError, ValueError):
        return "Not opened: the browser could not be started. Open the link above."
    return "Opening it in your browser."


def plain_text(value, limit=MAX_FIELD_CHARS):
    """File-derived text for a terminal or a model's context: no control or reordering characters."""
    return _UNSAFE_TEXT.sub(" ", str(value))[:limit]


def breakdown(totals):
    words = ["%d %s" % (totals[key], word) for key, word in _STATUS_WORDS if totals[key]]
    return ", ".join(words) or "nothing left"


def summary_lines(row, link=None, detail=False):
    """A short report. Notes stay out on purpose: they can hold anything, and this reaches a model."""
    totals = row["totals"]
    lines = ["%s (%s)" % (plain_text(row["title"]), plain_text(row["id"]))]
    if totals["total"]:
        lines.append("Tasks: %d of %d done, %s" % (totals["done"], totals["total"], breakdown(totals)))
    else:
        lines.append("Tasks: none yet")
    if detail:
        lines.append("Steps: " + "; ".join("%s: %s" % (step["label"], step["fact"]) for step in row["steps"]))
        for phase in row["phases"]:
            lines.append("  %s: %d of %d" % (plain_text(phase["name"]), phase["done"], phase["total"]))
        for task in row["active"]:
            who = " (%s)" % plain_text(task["who"]) if task["who"] else ""
            flag = ", possibly abandoned" if task["id"] in row["abandoned"] else ""
            lines.append("  %s %s%s%s: %s" % (task["id"], task["status"].replace("_", " "), flag, who, plain_text(task["text"])))
        for agent in row["agents"]:
            active = " (on %s)" % ", ".join(agent["active"]) if agent["active"] else ""
            lines.append("  %s: %d done%s" % (plain_text(agent["label"]), agent["done"], active))
    if row["attention"]:
        lines.append("Needs attention: %d, see the page" % len(row["attention"]))
    if link:
        lines.append("Page: " + link)
    return lines


def _say(text, stream=None):
    """Print whatever the output can encode. A character it cannot hold must not stop the command."""
    stream = sys.stdout if stream is None else stream
    encoding = getattr(stream, "encoding", None) or "utf-8"
    stream.write(text.encode(encoding, "replace").decode(encoding) + "\n")


def _draw(root, feature, problems):
    try:
        return render_project(root, feature)
    except (ProgressError, OSError) as exc:
        problems.append(str(exc))
        return None


def _resolve_feature(root, reference, problems):
    try:
        return find_feature(root, reference) if reference else current_feature_dir(root)
    except ProgressError as exc:
        problems.append(str(exc))
        return None


def _page_link(drawn, feature):
    if not drawn:
        return None
    page = drawn["pages"][0]["path"] if feature is not None and drawn["pages"] else drawn["index"]
    return Path(page).resolve().as_uri()


def _report(root, feature, drawn, problems, detail, after_design=False):
    """What the specs say. After the lines of the design, only the specs there are, and no link of their own."""
    link = None if after_design else _page_link(drawn, feature)
    try:
        rows = status_data(root, feature)
    except (ProgressError, OSError) as exc:
        problems.append(str(exc))
        return
    if feature is not None:
        for line in summary_lines(rows[0], link, detail):
            _say(line)
        return
    for row in rows:
        _say("%s: %d of %d done" % (plain_text(row["id"]), row["totals"]["done"], row["totals"]["total"]))
    if not rows and not after_design:
        _say("No specs yet.")
    if link:
        _say("Page: " + link)


def run_step_command(root, name, status, harness=None, note=None, reference=None, quiet=False):
    """Record a step and redraw. Problems are reported, never raised: the command's work comes first."""
    problems = []
    feature = _resolve_feature(root, reference, problems)
    belongs = step_belongs_to_spec(name, status)
    if belongs and feature is not None:
        try:
            append_event(feature, make_step_event(name, status, harness, note))
        except (ProgressError, OSError) as exc:
            problems.append(str(exc))
    drawn = _draw(root, feature, problems)
    if belongs and feature is not None and drawn and drawn["pages"]:
        open_once(root, drawn["pages"][0]["path"])
    if not quiet:
        _report(root, feature, drawn, problems, detail=False)
    for problem in problems:
        _say("progress: %s" % plain_text(problem, MAX_NOTE_CHARS), sys.stderr)
    return 0


def _design_link(drawn):
    design = drawn.get("design") if drawn else None
    return Path(design["path"]).resolve().as_uri() if design else None


def run_design_command(root, name, status, harness=None, note=None, area=None, quiet=False):
    """Record a step of the design, redraw and say how far the design is and what comes next.
    Problems are reported, never raised: the command's work comes first."""
    problems = []
    if has_design(root):
        event = make_step_event(name, status, harness, note)
        if isinstance(area, str) and len(area) <= MAX_AREA_CHARS and _AREA_NAME.match(area):
            event["area"] = area
        try:
            append_event(root / DESIGN_DIR, event)
        except (ProgressError, OSError) as exc:
            problems.append(str(exc))
    drawn = _draw(root, None, problems)
    link = _design_link(drawn)
    if link:
        open_once(root, drawn["design"]["path"])
    if not quiet:
        if link:
            for line in design_lines(drawn["design"]["summary"], link):
                _say(line)
        else:
            _say("No design yet. It starts with %s." % command_text(root, "speckit.studio.define"))
    for problem in problems:
        _say("progress: %s" % plain_text(problem, MAX_NOTE_CHARS), sys.stderr)
    return 0


def run_show_command(root, reference=None, open_page=False, design=False):
    """Redraw and report in full. For /speckit.progress, which also opens the page every time, and
    for the end of a command, which does not. The design is what is shown when it was asked for,
    and when the project has a design and no spec is the current one."""
    problems = []
    feature = None if design else _resolve_feature(root, reference, problems)
    drawn = _draw(root, feature, problems)
    link = _design_link(drawn) if feature is None and not reference else None
    if link:
        for line in design_lines(drawn["design"]["summary"], link):
            _say(line)
        if not design:
            _report(root, None, drawn, problems, detail=True, after_design=True)
    elif design:
        _say("No design yet. It starts with %s." % command_text(root, "speckit.studio.define"))
        link = _page_link(drawn, feature)
        if link:
            _say("Page: " + link)
    else:
        _report(root, feature, drawn, problems, detail=True)
        link = _page_link(drawn, feature)
    if open_page and link:
        _say(open_now(root, link))
    for problem in problems:
        _say("progress: %s" % plain_text(problem, MAX_NOTE_CHARS), sys.stderr)
    return 0


# -- Running it directly ----------------------------------------------------------------------


def status_data(root, feature=None, now=None):
    """Read-only summary for machines and for terminals. Writes nothing."""
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    current = current_feature_dir(root)
    targets = [feature] if feature is not None else discover_features(root)
    rows = []
    for path in targets:
        data = build_feature(root, path, root / OUTPUT_DIR, now=now, include_documents=False)
        rows.append({
            "id": data["id"],
            "title": data["title"],
            "current": current is not None and path.resolve() == current.resolve(),
            "totals": data["totals"],
            "abandoned": abandoned_tasks(data, now),
            "steps": [
                {"name": s["name"], "label": s["label"], "state": s["state"], "fact": s["fact"]}
                for s in data["steps"]
            ],
            "phases": [
                {
                    "name": phase["name"],
                    "total": len(phase["tasks"]),
                    "done": sum(1 for task in phase["tasks"] if task["status"] == "done"),
                }
                for phase in data["phases"]
            ],
            "active": [
                {"id": task["id"], "status": task["status"], "text": task["text"], "who": task["who"]}
                for phase in data["phases"]
                for task in phase["tasks"]
                if task["status"] in ("in_progress", "blocked", "failed")
            ],
            "agents": data["agents"],
            "attention": data["attention"],
        })
    return rows


def _parser():
    import argparse  # Only here: a hook loads this file after every tool call.

    parser = argparse.ArgumentParser(
        prog="progress",
        allow_abbrev=False,
        description="Draw or read the progress of a Spec Kit project.",
    )
    parser.add_argument("--root", default=".", help="Project root (default: current directory)")
    parser.add_argument("--harness", help="The integration running this command")
    shared = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    shared.add_argument("--root", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    shared.add_argument("--harness", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    shared.add_argument("--feature", help="Spec directory name, or a unique prefix of one")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    commands.add_parser("render", parents=[shared], allow_abbrev=False, help="Draw the pages. Prints JSON.")
    commands.add_parser("status", parents=[shared], allow_abbrev=False, help="Read the progress. Prints JSON, writes nothing.")
    show = commands.add_parser("show", parents=[shared], allow_abbrev=False, help="Draw the page and report in full.")
    show.add_argument("--open", action="store_true", dest="open_page", help="Also open the page in a browser, every time.")
    show.add_argument("--design", action="store_true", help="Show the design of the product instead of a spec.")
    design = commands.add_parser("design", parents=[shared], allow_abbrev=False, help="Record a step of the design, draw its page and report.")
    design.add_argument("name", help="The step: define, map or mockup")
    design.add_argument("status", choices=sorted(STEP_STATUSES - {"note"}))
    design.add_argument("--area", help="The area the step was about")
    design.add_argument("--note", help="One line about the step")
    design.add_argument("--quiet", action="store_true", help="Print nothing")
    step = commands.add_parser("step", parents=[shared], allow_abbrev=False, help="Record a step, draw the page and report.")
    step.add_argument("name", choices=STEP_NAMES + tuple(STEP_ALIASES))
    step.add_argument("status", choices=sorted(STEP_STATUSES))
    step.add_argument("--note", help="One line about the step")
    step.add_argument("--quiet", action="store_true", help="Print nothing")
    browser = commands.add_parser("browser", parents=[shared], allow_abbrev=False, help="Open pages by themselves, or not.")
    browser.add_argument("state", choices=("on", "off"))

    task = argparse.ArgumentParser(add_help=False, allow_abbrev=False, parents=[shared])
    task.add_argument("--agent", help="Who is doing this, when it is not the main agent")
    start = commands.add_parser("start", parents=[task], allow_abbrev=False, help="Say a task has started.")
    start.add_argument("task")
    done = commands.add_parser("done", parents=[task], allow_abbrev=False, help="Check a task's box and record it.")
    done.add_argument("task")
    done.add_argument("--note", help="One line on what changed and why")
    done.add_argument("--files", action="extend", nargs="+", help="The files it touched, separated by commas or spaces")
    done.add_argument("--then", help="The task that starts now")
    for name, verb in (("block", "is blocked"), ("fail", "failed"), ("skip", "is skipped")):
        closing = commands.add_parser(name, parents=[task], allow_abbrev=False, help="Say a task %s." % verb)
        closing.add_argument("task")
        closing.add_argument("--reason", required=True, help="Why, in one line")
    remark = commands.add_parser("note", parents=[task], allow_abbrev=False, help="Add a note to a task.")
    remark.add_argument("task")
    remark.add_argument("text", nargs="+")
    return parser


def _run_machine_command(args, root):
    try:
        feature = find_feature(root, args.feature) if args.feature else None
        if args.command == "render":
            result = render_project(root, feature)
        elif args.command == "status":
            result = status_data(root, feature)
        else:
            set_browser(root, args.state == "on")
            result = {"browser": args.state}
    except (ProgressError, OSError) as exc:
        sys.stderr.write("progress: %s\n" % exc)
        return 1
    sys.stdout.write(json.dumps(result, indent=1, ensure_ascii=True) + "\n")
    return 0


def _run_task_command(args, root):
    note = args.note if args.command == "done" else None
    if args.command in ("block", "fail", "skip"):
        note = args.reason
    elif args.command == "note":
        note = " ".join(args.text)
    try:
        return run_task_command(
            root,
            args.command,
            args.task,
            args.harness,
            args.agent,
            note,
            args.files if args.command == "done" else None,
            args.then if args.command == "done" else None,
            args.feature,
        )
    except (ProgressError, OSError) as exc:
        problem = str(exc)
    except Exception as exc:
        problem = "unexpected %s: %s" % (type(exc).__name__, exc)
    _say("progress: %s" % plain_text(problem, MAX_NOTE_CHARS), sys.stderr)
    _say("progress: nothing was recorded for %s." % plain_text(args.task, 40), sys.stderr)
    return 1


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.command == "step" and args.status == "note" and not (args.note or "").strip():
        parser.error("a note needs --note")
    if args.command in TASK_COMMANDS:
        if args.command in ("block", "fail", "skip") and not args.reason.strip():
            parser.error("%s needs a --reason" % args.command)
        if args.command == "note" and not " ".join(args.text).strip():
            parser.error("a note needs some text")
        if args.command == "done" and args.then == args.task:
            parser.error("--then has to name another task")
        return _run_task_command(args, root)
    if args.command == "design":
        if not _STEP_NAME.match(args.name):
            parser.error("a step of the design is a word such as define, map or mockup")
        if args.area is not None and not (len(args.area) <= MAX_AREA_CHARS and _AREA_NAME.match(args.area)):
            parser.error("--area takes the name of an area, in lowercase and hyphens")
    if args.command not in ("step", "show", "design"):
        return _run_machine_command(args, root)
    try:
        if args.command == "design":
            return run_design_command(root, args.name, args.status, args.harness, args.note, args.area, args.quiet)
        if args.command == "show":
            if args.design and args.feature:
                _say("progress: --design shows the design, so --feature was left aside.", sys.stderr)
            return run_show_command(root, args.feature, args.open_page, args.design)
        return run_step_command(root, args.name, args.status, args.harness, args.note, args.feature, args.quiet)
    except Exception as exc:
        _say("progress: unexpected %s: %s" % (type(exc).__name__, plain_text(exc, MAX_NOTE_CHARS)), sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
