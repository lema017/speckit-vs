"""Shared fixtures for the ``specify progress`` tests.

SPECKIT_PROGRESS_ENGINE_UNDER_TEST lets mutants.py run these tests against a changed copy of the
engine. Nothing outside this test folder reads it.
"""

from __future__ import annotations

import json
import os
import shutil
import zoneinfo  # noqa: F401  Loaded before any test fakes sys.platform: the CLI's first run imports it, and it reads this platform's build data.
from pathlib import Path

import pytest

from specify_cli.progress import _engine as engine_module

ENV_CLEARED = (
    "SPECIFY_FEATURE",
    "SPECIFY_FEATURE_DIRECTORY",
    "SPECIFY_INIT_DIR",
    "CI",
    "SSH_CONNECTION",
    "SSH_CLIENT",
    "SSH_TTY",
)

REPO = Path(__file__).resolve().parents[3]
STUDIO = REPO / "extensions" / "studio"
OFICIO = REPO / "tests" / "extensions" / "studio" / "fixtures" / "oficio" / "specs" / "_product"

SPEC = """# Feature Specification: Login

## Requirements

- **FR-001**: The system MUST let people sign in.
- **FR-002**: The system MUST lock after five failures.
"""

PLAN = """# Implementation Plan: Login

## Summary

Build it.
"""

TASKS = """# Tasks: Login

## Phase 1: Setup

**Purpose**: Get ready

- [X] T001 Create the project
- [ ] T002 [P] Add the linter

## Phase 2: User Story 1

### Implementation for User Story 1

- [ ] T003 [P] [US1] Add the form in src/form.py
- [ ] T004 [US1] Connect the form in src/app.py

## Dependencies

Nothing here is a task.
"""


class Project:
    """A throwaway Spec Kit project on disk."""

    def __init__(self, root: Path):
        self.root = root
        (root / ".specify" / "memory").mkdir(parents=True)

    def feature(self, name="001-login", spec=SPEC, plan=PLAN, tasks=TASKS, events=None) -> Path:
        directory = self.root / "specs" / name
        directory.mkdir(parents=True)
        for file_name, text in (("spec.md", spec), ("plan.md", plan), ("tasks.md", tasks)):
            if text is not None:
                # The same bytes on every system: some tests compare them, and CRLF has its own test.
                (directory / file_name).write_text(text, encoding="utf-8", newline="\n")
        if events is not None:
            self.log(directory, events)
        return directory

    def log(self, directory: Path, events) -> None:
        lines = [event if isinstance(event, str) else json.dumps(event) for event in events]
        with (directory / "progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("".join(line + "\n" for line in lines))

    def set_current(self, directory: Path) -> None:
        relative = directory.relative_to(self.root).as_posix()
        (self.root / ".specify" / "feature.json").write_text(json.dumps({"feature_directory": relative}), encoding="utf-8")

    def install_studio(self) -> None:
        """Give the project the studio extension, whose script knows what a design says."""
        target = self.root / ".specify" / "extensions" / "studio"
        shutil.copytree(str(STUDIO), str(target), ignore=shutil.ignore_patterns("__pycache__"))

    def design(self) -> Path:
        """Give the project the studio extension and the design of Oficio: two areas, both drawn."""
        self.install_studio()
        shutil.copytree(str(OFICIO), str(self.root / "specs" / "_product"))
        return self.root / "specs" / "_product"

    def written(self):
        """Every file under the project, to prove a command wrote nothing. Bytecode a loaded script left does not count."""
        return sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*") if path.is_file() and "__pycache__" not in path.parts)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """Nothing about the machine running the tests may decide what they see."""
    for name in ENV_CLEARED:
        monkeypatch.delenv(name, raising=False)
    override = os.environ.get("SPECKIT_PROGRESS_ENGINE_UNDER_TEST")
    engine_module.load_engine.cache_clear()
    if override:
        monkeypatch.setattr(engine_module, "engine_path", lambda: Path(override))
    yield
    engine_module.load_engine.cache_clear()


@pytest.fixture
def engine():
    return engine_module.load_engine()


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    return Project(root)


@pytest.fixture
def in_project(project, monkeypatch):
    monkeypatch.chdir(project.root)
    return project


def symlink(link, target, **kwargs):
    """Make a link, or skip where the platform or its permissions do not allow one."""
    try:
        link.symlink_to(target, **kwargs)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")


def task_event(task="T001", status="done", **fields):
    event = {"v": 1, "ts": "2026-01-02T03:04:05Z", "kind": "task", "task": task, "status": status}
    event.update(fields)
    return event


def step_event(step="plan", status="done", **fields):
    event = {"v": 1, "ts": "2026-01-02T03:04:05Z", "kind": "step", "step": step, "status": status}
    event.update(fields)
    return event
