#!/usr/bin/env python3
"""Spec Kit progress engine: read a project's files and draw one page per spec.

Self-contained on purpose. Projects get a copy of this file and run it with whatever interpreter
they have, so it uses only the standard library and stays compatible with Python 3.9.

tasks.md decides what is done. specs/<feature>/progress.jsonl adds who, when and why, plus the
states a checkbox cannot hold. Everything read here was written by a model or a person, so it is
untrusted: pages carry it as escaped JSON and paint it only as text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

SCHEMA_VERSION = 1
GENERATOR = "speckit-progress"
OUTPUT_DIR = Path(".specify") / "progress"
PAGE_TEMPLATE = "page.html"
INDEX_TEMPLATE = "index.html"
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

TASK_STATUSES = frozenset({"in_progress", "done", "blocked", "failed", "skipped", "note"})
OPEN_STATUSES = frozenset({"in_progress", "blocked", "failed", "skipped"})
STEP_STATUSES = frozenset({"in_progress", "done", "failed", "skipped", "note"})
ACTOR_SOURCES = frozenset({"observed", "configured", "declared"})
STEP_ALIASES = {"clarify-deep": "clarify"}

_CHECKBOX = re.compile(r"^\s*[-*+]\s*\[([ xX])\]\s*(.*)$")
_LEADING_TAG = re.compile(r"^\[([^\]\n]{1,40})\]\s*")
_TASK_ID = re.compile(r"^(?:\*\*)?(T\d+)(?:\*\*)?(?![\w-]|\.\d)\s*(?:[:.\-\u2013\u2014]\s+|:\s*)?")
_BRACKETED_ID = re.compile(r"^T\d+$")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+)$")
_GOAL = re.compile(r"^\*\*(?:Goal|Purpose):?\*\*:?\s*(.+)$")
_LINE_BREAK = re.compile(r"\r\n?|\n")
_FENCE = re.compile(r"^\s*(```+|~~~+)")
_QUESTION = re.compile(r"^\s*[-*+]\s+(?:\*\*)?Q:")
_REQUIREMENT = re.compile(r"\*\*(FR-\d+)\*\*")
_STEP_NAME = re.compile(r"^[a-z][a-z0-9.-]{0,40}$")
_TASK_NAME = re.compile(r"^T\d+$")
_SAFE_FILE = re.compile(r"[^A-Za-z0-9._-]+")
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
    if kind == "task":
        name = raw.get("task")
        if status not in TASK_STATUSES or not isinstance(name, str) or not _TASK_NAME.match(name):
            return None
        event["task"] = name
    elif kind == "step":
        name = raw.get("step")
        if status not in STEP_STATUSES or not isinstance(name, str) or not _STEP_NAME.match(name):
            return None
        event["step"] = STEP_ALIASES.get(name, name)
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
    return events, bad, truncated


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
        })
    return rows


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
    """Each step says what its files prove; the log only adds who, and what files cannot show."""
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
    details = ["%s: %d of %d" % (row["name"], row["checked"], row["total"]) for row in lists]
    if not lists:
        checklist = _step("checklist", "Checklist", "skipped", "not run")
    elif checked == total:
        checklist = _step("checklist", "Checklist", "done", "%d of %d" % (checked, total), details)
    else:
        checklist = _step("checklist", "Checklist", "attention", "%d of %d" % (checked, total), details)

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
    for step in steps:
        name = step["name"]
        step["actor"] = actors.get(name)
        step["who"] = actor_label(actors.get(name))
        step["note"] = notes.get(name)
        status = logged[name]["status"] if name in logged else None
        if status == "in_progress" and step["state"] in ("pending", "skipped"):
            step["state"] = "active"
        elif status == "failed":
            step["state"] = "attention"
    return steps


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


def build_attention(tasks, parsed, bad_lines, tasks_truncated, log_truncated, refused_tasks):
    items = []
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
    events, bad_lines, log_truncated = read_events(directory / "progress.jsonl")

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

    data = {
        "schema": SCHEMA_VERSION,
        "id": directory.name,
        "title": build_title(spec, directory),
        "generated": now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "abandon_after_seconds": ABANDONED_AFTER_SECONDS,
        "totals": totals,
        "steps": build_steps(root, directory, phases, events, spec),
        "phases": phases,
        "agents": build_agents(every),
        "attention": build_attention(
            every, parsed, bad_lines, tasks_truncated, log_truncated, tasks_path.is_symlink()
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


def write_atomic(path, text):
    """Write through a temporary file, so a reader never sees half a page."""
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-" + GENERATOR + "-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(text.encode("utf-8"))
        try:
            os.chmod(temporary, 0o644)
        except OSError:
            pass
        os.replace(temporary, str(path))
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def page_file_names(features):
    """One safe, unique file name per spec. index.html belongs to the list of specs."""
    names = {}
    used = {INDEX_TEMPLATE.lower()}
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


def _summary(data, file_name, current):
    return {
        "id": data["id"],
        "title": data["title"],
        "file": file_name,
        "current": current,
        "generated": data["generated"],
        "attention": len(data["attention"]),
        "totals": data["totals"],
    }


def _remove_orphan_pages(out_dir, keep):
    """Drop pages of specs that no longer exist. Only pages this engine wrote are touched."""
    marker = ('name="generator" content="%s"' % GENERATOR).encode("ascii")
    for path in out_dir.glob("*.html"):
        if path.name in keep or path.is_symlink():
            continue
        try:
            with path.open("rb") as stream:
                if marker in stream.read(1024):
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
    summaries = []
    pages = []
    for path in features:
        file_name = names[str(path)]
        draw = feature is None or feature.resolve() == path.resolve()
        data = build_feature(root, path, out_dir, now=now, include_documents=draw)
        is_current = current_key is not None and path.resolve() == current_key
        summaries.append(_summary(data, file_name, is_current))
        if draw:
            target = out_dir / file_name
            write_atomic(target, fill_template(page, data))
            pages.append({"id": data["id"], "path": str(target), "current": is_current, "totals": data["totals"]})
    index = out_dir / INDEX_TEMPLATE
    write_atomic(index, fill_template(_load_template(INDEX_TEMPLATE), {
        "generated": now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "specs": summaries,
    }))
    if feature is None:
        _remove_orphan_pages(out_dir, set(names.values()) | {INDEX_TEMPLATE})
    return {"out_dir": str(out_dir), "index": str(index), "pages": pages}


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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Draw or read the progress of a Spec Kit project.")
    parser.add_argument("command", choices=("render", "status"))
    parser.add_argument("--root", default=".", help="Project root (default: current directory)")
    parser.add_argument("--feature", help="Spec directory name, or a unique prefix of one")
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        feature = find_feature(root, args.feature) if args.feature else None
        if args.command == "render":
            result = render_project(root, feature)
        else:
            result = status_data(root, feature)
    except (ProgressError, OSError) as exc:
        sys.stderr.write("progress: %s\n" % exc)
        return 1
    sys.stdout.write(json.dumps(result, indent=1, ensure_ascii=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
