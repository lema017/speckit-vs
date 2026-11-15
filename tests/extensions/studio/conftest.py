"""A product folder to try the studio script on: Oficio, the example of the approved demo."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EXT_DIR = ROOT / "extensions" / "studio"
SCRIPT = Path(os.environ.get("STUDIO_TEST_SCRIPT") or EXT_DIR / "scripts" / "python" / "studio.py")
PYTHON = os.environ.get("STUDIO_TEST_PYTHON", sys.executable)
FIXTURE = Path(__file__).parent / "fixtures" / "oficio"
CAPABILITIES_DIR = ROOT / "extensions" / "capabilities"
PRODUCT = "specs/_product"


class Project:
    def __init__(self, path: Path):
        self.path = path
        self.product = path / PRODUCT
        # No test opens a browser or starts a server, and none takes a picture with the real browser unless it says which.
        self.env = {"SPECKIT_STUDIO_NO_BROWSER": "1", "SPECKIT_STUDIO_NO_SERVER": "1", "SPECKIT_STUDIO_BROWSER": str(path / "no-browser-here")}

    def run(self, command, *args, stdin=None):
        """(exit code, parsed answer). No site packages: the script uses the standard library only.

        The options go before what the command takes, as an agent may write them: before Python 3.12
        that order lost the letter of `pick`, and only an older Python shows it.
        """
        source = {"stdin": subprocess.DEVNULL} if stdin is None else {"input": stdin}
        done = subprocess.run([PYTHON, "-I", "-S", str(SCRIPT), command, "--root", str(self.path), *args],
                              capture_output=True, encoding="utf-8", errors="replace", env=dict(os.environ, **self.env), **source)
        try:
            out = json.loads(done.stdout) if done.stdout.strip() else {}
        except ValueError:
            out = {"raw": done.stdout}
        if done.stderr.strip():
            out["stderr"] = done.stderr.strip()[-600:]
        return done.returncode, out

    def read(self, name):
        return (self.product / name).read_text(encoding="utf-8")

    def write(self, name, text):
        path = self.product / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def edit(self, name, old, new, count=1):
        text = self.read(name)
        assert text.count(old) == count, "%s holds %r %d times" % (name, old, text.count(old))
        self.write(name, text.replace(old, new))

    def remove(self, name):
        (self.product / name).unlink()

    def check(self):
        return self.run("check")

    def hard(self, *needles):
        return [line for line in self.check()[1].get("hard", []) if all(needle in line for needle in needles)]

    def notes(self, *needles):
        return [line for line in self.check()[1].get("notes", []) if all(needle in line for needle in needles)]

    def status(self):
        rc, out = self.run("status")
        assert rc == 0, out
        return out

    def area(self, name):
        return next(area for area in self.status()["areas"] if area["id"] == name)

    def with_catalog(self):
        """The project gets the extension that keeps the approved rules, as `specify init` installs it."""
        target = self.path / ".specify" / "extensions" / "capabilities"
        if not target.exists():
            shutil.copytree(str(CAPABILITIES_DIR), str(target), ignore=shutil.ignore_patterns("__pycache__"))
        return self

    def catalog(self, capability):
        """What the catalog says of a capability, or None."""
        path = self.path / "specs" / "_capabilities" / capability / "spec.md"
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def records(self):
        """The design records of the project, by name."""
        base = self.path / "specs" / "_capabilities" / "_changes"
        return sorted(path.name for path in base.iterdir()) if base.is_dir() else []

    def built(self, name):
        """What a generated script file holds, as data."""
        text = (self.product / "mockup" / "_studio" / name).read_text(encoding="utf-8")
        return json.loads(text[text.index("= ") + 2:text.rindex(";")])


@pytest.fixture(scope="session")
def studio():
    """The script as a module, for what has no command of its own."""
    spec = importlib.util.spec_from_file_location("studio_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_server_by_accident(monkeypatch):
    """`open` starts a server of its own that outlives the command. No test does, unless it is about that."""
    monkeypatch.setenv("SPECKIT_STUDIO_NO_SERVER", "1")


@pytest.fixture
def served(oficio, studio):
    """The mockup of Oficio behind its server, in this process: (the project, the port, the session)."""
    import threading
    oficio.run("build")
    server, session = studio.make_server(oficio.path, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield oficio, server.server_address[1], session
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.fixture
def empty(tmp_path):
    """A project with no product yet."""
    return Project(tmp_path)


@pytest.fixture
def oficio(tmp_path):
    """Oficio: two areas, six screens with their pages, six rules in draft."""
    path = tmp_path / "repo"
    shutil.copytree(str(FIXTURE), str(path))
    return Project(path)
