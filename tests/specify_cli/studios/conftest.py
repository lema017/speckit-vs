"""Shared fixtures for the ``specify studio`` tests: a project with the design of Oficio."""

from __future__ import annotations

import shutil
import zoneinfo  # noqa: F401  Loaded before any test fakes sys.platform: the CLI's first run imports it, and it reads this platform's build data.
import webbrowser
from pathlib import Path

import pytest

from specify_cli.studios import _script as script_module

ROOT = Path(__file__).resolve().parents[3]
OFICIO = ROOT / "tests" / "extensions" / "studio" / "fixtures" / "oficio" / "specs" / "_product"
ENV_CLEARED = (
    "SPECIFY_INIT_DIR",
    "CI",
    "SSH_CONNECTION",
    "SSH_CLIENT",
    "SSH_TTY",
    "SPECKIT_STUDIO_NO_BROWSER",
    "SPECKIT_PROGRESS_NO_BROWSER",
)


class Project:
    """A throwaway Spec Kit project on disk."""

    def __init__(self, root: Path):
        self.root = root
        self.product = root / "specs" / "_product"
        (root / ".specify").mkdir(parents=True)

    def design(self) -> "Project":
        shutil.copytree(str(OFICIO), str(self.product))
        return self

    def edit(self, name, old, new):
        path = self.product / name
        text = path.read_text(encoding="utf-8")
        assert text.count(old) == 1, "%s holds %r %d times" % (name, old, text.count(old))
        path.write_text(text.replace(old, new), encoding="utf-8")

    def written(self):
        """Every file under the project, to prove a command wrote nothing."""
        return sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*") if path.is_file())


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """Nothing about the machine running the tests may decide what they see."""
    for name in ENV_CLEARED:
        monkeypatch.delenv(name, raising=False)
    script_module.load_script.cache_clear()
    yield
    script_module.load_script.cache_clear()


@pytest.fixture
def project(tmp_path, monkeypatch):
    """An empty Spec Kit project, and the commands run from inside it."""
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.chdir(root)
    return Project(root)


@pytest.fixture
def designed(project):
    """The project with the design of Oficio: two areas, six screens, all drawn."""
    return project.design()


@pytest.fixture
def opened(monkeypatch):
    """Record what would have opened. No test here may start a real browser."""
    calls = []

    def fake_open(url):
        calls.append(url)
        return True

    monkeypatch.setattr(webbrowser, "open", fake_open)
    monkeypatch.setattr("sys.platform", "darwin")
    return calls
