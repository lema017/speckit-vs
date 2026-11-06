"""What the progress engine writes, and what it refuses to write or carry."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import pytest

from .conftest import symlink, task_event

ROOT = Path(__file__).resolve().parents[3]
HOSTILE = '</script><img src=x onerror=alert(1)><!--<script>alert(2)</script>\u2028\u2029&amp;\x1b[31m'


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.tags = []
        self.data = None
        self._in_data = False

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self._in_data = tag == "script" and ("id", "data") in attrs

    def handle_data(self, data):
        if self._in_data and self.data is None:
            self.data = data

    def handle_endtag(self, tag):
        self._in_data = False


def parse_page(path):
    parser = Tags()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def page_of(project, name="001-login"):
    return project.root / ".specify" / "progress" / (name + ".html")


def data_of(project, name="001-login"):
    return json.loads(parse_page(page_of(project, name)).data)


# -- What gets written -----------------------------------------------------------------------


def test_it_draws_a_page_per_spec_and_a_list(engine, project):
    project.feature("001-login")
    project.feature("002-logout")
    result = engine.render_project(project.root)
    out = project.root / ".specify" / "progress"
    assert sorted(path.name for path in out.iterdir()) == [".gitignore", "001-login.html", "002-logout.html", "index.html"]
    assert result["index"] == str(out / "index.html")
    assert [page["id"] for page in result["pages"]] == ["001-login", "002-logout"]


def test_the_output_folder_ignores_itself_in_git(engine, project):
    project.feature()
    engine.render_project(project.root)
    lines = (project.root / ".specify" / "progress" / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "*" in lines


def test_an_existing_ignore_file_is_left_alone(engine, project):
    project.feature()
    out = project.root / ".specify" / "progress"
    out.mkdir()
    (out / ".gitignore").write_text("mine\n", encoding="utf-8")
    engine.render_project(project.root)
    assert (out / ".gitignore").read_text(encoding="utf-8") == "mine\n"


def test_nothing_is_written_outside_its_folder(engine, project):
    directory = project.feature(events=[task_event()])
    before = {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()}
    engine.render_project(project.root)
    assert {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()} == before
    assert not (project.root / ".specify" / "feature.json").exists()


def test_no_temporary_files_stay_behind(engine, project):
    project.feature()
    engine.render_project(project.root)
    assert not [path for path in (project.root / ".specify" / "progress").iterdir() if path.name.startswith(".tmp-")]


def test_a_failed_write_keeps_the_old_page_and_cleans_up(engine, project, monkeypatch):
    project.feature()
    engine.render_project(project.root)
    before = page_of(project).read_bytes()

    def broken(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(engine.os, "replace", broken)
    with pytest.raises(OSError):
        engine.render_project(project.root)
    monkeypatch.undo()
    assert page_of(project).read_bytes() == before
    assert not [path for path in (project.root / ".specify" / "progress").iterdir() if path.name.startswith(".tmp-")]


def test_drawing_one_spec_keeps_the_others_and_updates_the_list(engine, project):
    first = project.feature("001-login")
    project.feature("002-logout")
    engine.render_project(project.root)
    other_before = page_of(project, "002-logout").read_bytes()
    project.log(first, [task_event("T002", "in_progress")])
    result = engine.render_project(project.root, first)
    assert [page["id"] for page in result["pages"]] == ["001-login"]
    assert page_of(project, "002-logout").read_bytes() == other_before
    assert data_of(project)["totals"]["in_progress"] == 1
    listed = json.loads(parse_page(project.root / ".specify" / "progress" / "index.html").data)
    assert [row["id"] for row in listed["specs"]] == ["001-login", "002-logout"]
    assert listed["specs"][0]["totals"]["in_progress"] == 1


def test_a_spec_that_is_gone_loses_its_page_but_foreign_pages_stay(engine, project):
    project.feature("001-login")
    gone = project.feature("002-logout")
    engine.render_project(project.root)
    out = project.root / ".specify" / "progress"
    (out / "notes.html").write_text("<html>mine</html>", encoding="utf-8")
    for path in gone.iterdir():
        path.unlink()
    gone.rmdir()
    engine.render_project(project.root)
    assert not (out / "002-logout.html").exists()
    assert (out / "notes.html").exists()
    assert (out / "001-login.html").exists()


def test_a_page_is_closed_before_it_is_removed(engine, project, monkeypatch):
    """Windows refuses to remove an open file, which would keep the page of a deleted spec forever."""
    project.feature("001-login")
    gone = project.feature("002-logout")
    engine.render_project(project.root)
    for path in gone.iterdir():
        path.unlink()
    gone.rmdir()
    opened = []
    real_open = Path.open
    real_unlink = Path.unlink

    def tracking_open(self, *args, **kwargs):
        stream = real_open(self, *args, **kwargs)
        opened.append((self, stream))
        return stream

    def tracking_unlink(self, *args, **kwargs):
        assert not any(path == self and not stream.closed for path, stream in opened), "%s is still open" % self
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)
    monkeypatch.setattr(Path, "unlink", tracking_unlink)
    engine.render_project(project.root)
    assert not (project.root / ".specify" / "progress" / "002-logout.html").exists()


def test_drawing_one_spec_does_not_remove_pages(engine, project):
    first = project.feature("001-login")
    gone = project.feature("002-logout")
    engine.render_project(project.root)
    for path in gone.iterdir():
        path.unlink()
    gone.rmdir()
    engine.render_project(project.root, first)
    assert (project.root / ".specify" / "progress" / "002-logout.html").exists()


def test_an_empty_project_gets_a_list_saying_so(engine, project):
    result = engine.render_project(project.root)
    assert result["pages"] == []
    assert json.loads(parse_page(Path(result["index"])).data)["specs"] == []


def test_a_spec_without_tasks_still_gets_a_page(engine, project):
    project.feature(tasks=None)
    engine.render_project(project.root)
    assert data_of(project)["totals"]["total"] == 0


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["index"], ["index-2.html"]),
        (["INDEX"], ["INDEX-2.html"]),
        (["a b", "a_b"], ["a_b.html", "a_b-2.html"]),
        (["..."], ["spec.html"]),
        (["caf\u00e9"], ["caf.html"]),
    ],
)
def test_page_names_are_safe_and_unique(engine, names, expected):
    paths = [Path("specs") / name for name in names]
    assert list(engine.page_file_names(paths).values()) == expected


def test_refuses_a_folder_that_is_not_a_project(engine, tmp_path):
    with pytest.raises(engine.ProgressError):
        engine.render_project(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_refuses_to_write_through_a_linked_output_folder(engine, project, tmp_path):
    project.feature()
    outside = tmp_path / "outside"
    outside.mkdir()
    symlink((project.root / ".specify" / "progress"), outside)
    with pytest.raises(engine.ProgressError):
        engine.render_project(project.root)
    assert list(outside.iterdir()) == []


def test_refuses_an_output_path_that_is_a_file(engine, project):
    project.feature()
    (project.root / ".specify" / "progress").write_text("x", encoding="utf-8")
    with pytest.raises(engine.ProgressError):
        engine.render_project(project.root)


def test_refuses_a_linked_specify_folder(engine, tmp_path):
    real = tmp_path / "real"
    (real / ".specify").mkdir(parents=True)
    root = tmp_path / "project"
    root.mkdir()
    symlink((root / ".specify"), real / ".specify")
    with pytest.raises(engine.ProgressError):
        engine.render_project(root)


def test_a_linked_page_is_replaced_and_its_target_left_alone(engine, project, tmp_path):
    project.feature()
    out = project.root / ".specify" / "progress"
    out.mkdir()
    outside = tmp_path / "victim.txt"
    outside.write_text("keep me", encoding="utf-8")
    symlink((out / "001-login.html"), outside)
    symlink((out / "index.html"), outside)
    engine.render_project(project.root)
    assert outside.read_text(encoding="utf-8") == "keep me"
    assert not (out / "001-login.html").is_symlink()
    assert not (out / "index.html").is_symlink()


# -- Which specs exist -----------------------------------------------------------------------


def names(paths):
    return [path.name for path in paths]


def test_the_catalog_and_hidden_folders_are_not_specs(engine, project):
    project.feature("001-login")
    (project.root / "specs" / "_capabilities").mkdir()
    (project.root / "specs" / ".cache").mkdir()
    (project.root / "specs" / "README.md").write_text("x", encoding="utf-8")
    assert names(engine.discover_features(project.root)) == ["001-login"]


def test_a_linked_spec_folder_is_ignored(engine, project, tmp_path):
    project.feature("001-login")
    outside = tmp_path / "outside"
    outside.mkdir()
    symlink((project.root / "specs" / "002-out"), outside)
    assert names(engine.discover_features(project.root)) == ["001-login"]


def test_a_linked_specs_folder_is_ignored(engine, project, tmp_path):
    outside = tmp_path / "outside"
    (outside / "001-out").mkdir(parents=True)
    symlink((project.root / "specs"), outside)
    assert engine.discover_features(project.root) == []


def test_no_specs_folder_means_no_specs(engine, project):
    assert engine.discover_features(project.root) == []


def test_the_current_spec_comes_from_feature_json(engine, project):
    directory = project.feature("001-login")
    project.feature("002-logout")
    project.set_current(directory)
    assert engine.current_feature_dir(project.root).name == "001-login"


def test_the_environment_outranks_feature_json(engine, project, monkeypatch):
    project.set_current(project.feature("001-login"))
    project.feature("002-logout")
    monkeypatch.setenv("SPECIFY_FEATURE_DIRECTORY", "specs/002-logout")
    assert engine.current_feature_dir(project.root).name == "002-logout"


def test_the_feature_name_is_the_last_resort(engine, project, monkeypatch):
    project.feature("001-login")
    monkeypatch.setenv("SPECIFY_FEATURE", "001-login")
    assert engine.current_feature_dir(project.root).name == "001-login"


def test_a_feature_elsewhere_in_the_project_is_included(engine, project):
    elsewhere = project.root / "work" / "feature-x"
    elsewhere.mkdir(parents=True)
    project.feature("001-login")
    project.set_current(elsewhere)
    assert names(engine.discover_features(project.root)) == ["001-login", "feature-x"]


@pytest.mark.parametrize("content", ["{not json", "[]", '{"feature_directory": 3}', '{"feature_directory": "specs/missing"}', '{"feature_directory": ""}', '{"feature_directory": "."}', '{"feature_directory": "a\\u0000b"}'])
def test_a_useless_feature_json_means_no_current_spec(engine, project, content):
    project.feature("001-login")
    (project.root / ".specify" / "feature.json").write_text(content, encoding="utf-8")
    assert engine.current_feature_dir(project.root) is None


def test_a_feature_outside_the_project_does_not_count(engine, project, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "spec.md").write_text("secret", encoding="utf-8")
    (project.root / ".specify" / "feature.json").write_text(json.dumps({"feature_directory": str(outside)}), encoding="utf-8")
    assert engine.current_feature_dir(project.root) is None
    assert engine.discover_features(project.root) == []
    (project.root / ".specify" / "feature.json").write_text(json.dumps({"feature_directory": "../outside"}), encoding="utf-8")
    assert engine.current_feature_dir(project.root) is None


def test_a_linked_feature_json_is_not_followed(engine, project, tmp_path):
    project.feature("001-login")
    outside = tmp_path / "feature.json"
    outside.write_text('{"feature_directory": "specs/001-login"}', encoding="utf-8")
    symlink((project.root / ".specify" / "feature.json"), outside)
    assert engine.current_feature_dir(project.root) is None


def test_a_linked_current_feature_is_refused(engine, project):
    real = project.feature("001-login")
    symlink((project.root / "work"), real, target_is_directory=True)
    (project.root / ".specify" / "feature.json").write_text('{"feature_directory": "work"}', encoding="utf-8")
    assert engine.current_feature_dir(project.root) is None


def test_finding_a_spec_by_name_or_prefix(engine, project):
    project.feature("001-login")
    project.feature("001-login-extra")
    project.feature("002-logout")
    assert engine.find_feature(project.root, "001-login").name == "001-login"
    assert engine.find_feature(project.root, "002").name == "002-logout"


@pytest.mark.parametrize(("reference", "message"), [("001", "more than one"), ("9", "No spec named")])
def test_finding_a_spec_fails_clearly(engine, project, reference, message):
    project.feature("001-login")
    project.feature("001-logout")
    with pytest.raises(engine.ProgressError, match=message):
        engine.find_feature(project.root, reference)


# -- Hostile content -------------------------------------------------------------------------


def hostile_project(project):
    tasks = "## %s\n**Goal**: %s\n- [ ] T001 %s\n- [ ] %s\n" % (HOSTILE, HOSTILE, HOSTILE, HOSTILE)
    directory = project.feature("001-login", spec="# %s\n" % HOSTILE, plan=HOSTILE, tasks=tasks)
    project.log(directory, [task_event("T001", "in_progress", note=HOSTILE, files=[HOSTILE], actor={"harness": HOSTILE, "agent": HOSTILE, "session": HOSTILE})])
    project.log(directory, [{"v": 1, "kind": "step", "step": "plan", "status": "done", "note": HOSTILE, "actor": {"harness": HOSTILE}}])
    return directory


def test_hostile_text_cannot_add_markup_and_arrives_intact(engine, project):
    hostile_project(project)
    engine.render_project(project.root)
    parsed = parse_page(page_of(project))
    assert parsed.tags.count("script") == 2
    assert "img" not in parsed.tags
    data = json.loads(parsed.data)
    assert data["phases"][0]["tasks"][0]["text"].strip() == HOSTILE.strip()
    assert data["phases"][0]["tasks"][0]["notes"][0]["note"] == HOSTILE
    assert data["documents"][0]["text"].startswith("# " + HOSTILE)


def test_the_list_of_specs_is_just_as_safe(engine, project):
    hostile_project(project)
    engine.render_project(project.root)
    parsed = parse_page(project.root / ".specify" / "progress" / "index.html")
    assert parsed.tags.count("script") == 2
    assert "img" not in parsed.tags
    assert json.loads(parsed.data)["specs"][0]["title"].strip() == HOSTILE.strip()


@pytest.mark.parametrize("char", ["<", ">", "&", "\u2028", "\u2029"])
def test_characters_that_could_end_a_script_are_escaped(engine, char):
    text = engine.as_script_json({"a": "x" + char + "y"})
    assert char not in text
    assert json.loads(text) == {"a": "x" + char + "y"}


def test_text_that_looks_like_the_placeholder_is_not_filled_in(engine):
    filled = engine.fill_template("A /*DATA*/null B /*DATA*/null", {"a": "/*DATA*/null"})
    assert filled.startswith('A {"a":"/*DATA*/null"} B')
    assert filled.endswith("B /*DATA*/null")


def test_a_template_with_no_place_for_data_is_refused(engine):
    with pytest.raises(engine.ProgressError):
        engine.fill_template("<html></html>", {})


@pytest.mark.parametrize("template", ["page.html", "index.html"])
def test_the_page_uses_no_way_to_turn_text_into_markup_or_code(template):
    source = (ROOT / "scripts" / "progress" / template).read_text(encoding="utf-8")
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "srcdoc", "setTimeout(\"", "setInterval(\""):
        assert forbidden not in source, forbidden


@pytest.mark.parametrize("template", ["page.html", "index.html"])
def test_the_page_loads_nothing_from_outside(template):
    source = (ROOT / "scripts" / "progress" / template).read_text(encoding="utf-8")
    urls = set(re.findall(r"https?://[^\s\"']+", source))
    assert urls <= {"http://www.w3.org/2000/svg"}
    assert " src=" not in source
    assert "@import" not in source
    assert "<link" not in source


@pytest.mark.parametrize("template", ["page.html", "index.html"])
def test_the_page_declares_its_limits_and_its_author(template):
    source = (ROOT / "scripts" / "progress" / template).read_text(encoding="utf-8")
    assert "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'" in source
    assert 'name="generator" content="speckit-progress"' in source[:1024]
    assert source.count("/*DATA*/null") == 1


def test_the_viewer_never_gives_a_document_a_real_link(engine):
    source = (ROOT / "scripts" / "progress" / "page.html").read_text(encoding="utf-8")
    assert 'el("a"' not in source
    assert source.count("setAttribute(\"href\"") == 1
    assert '$("vopen").setAttribute("href", doc.href)' in source


# -- Documents carried by the page -----------------------------------------------------------


def documents_of(engine, project, directory):
    return engine.collect_documents(project.root, directory, project.root / ".specify" / "progress")


def test_the_page_carries_every_document_in_order(engine, project):
    directory = project.feature()
    (directory / "research.md").write_text("r", encoding="utf-8")
    (directory / "checklists").mkdir()
    (directory / "checklists" / "ux.md").write_text("c", encoding="utf-8")
    (directory / "contracts").mkdir()
    (directory / "contracts" / "api.yaml").write_text("a: 1", encoding="utf-8")
    (directory / "contracts" / "image.png").write_bytes(b"\x89PNG")
    (project.root / ".specify" / "memory" / "constitution.md").write_text("rules", encoding="utf-8")
    docs = documents_of(engine, project, directory)
    assert [doc["name"] for doc in docs] == ["spec.md", "plan.md", "research.md", "tasks.md", "checklists/ux.md", "contracts/api.yaml", "constitution.md"]
    by_name = {doc["name"]: doc for doc in docs}
    assert by_name["spec.md"]["markdown"] is True
    assert by_name["contracts/api.yaml"]["markdown"] is False
    assert by_name["constitution.md"]["text"] == "rules"


def test_links_to_documents_are_relative_and_escaped(engine, project):
    directory = project.feature("001 caf\u00e9 #1")
    href = documents_of(engine, project, directory)[0]["href"]
    assert href == "../../specs/001%20caf%C3%A9%20%231/spec.md"
    assert "../../specs/" in href and ":" not in href


def test_a_linked_document_is_not_carried(engine, project, tmp_path):
    directory = project.feature(spec=None)
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET", encoding="utf-8")
    symlink((directory / "spec.md"), secret)
    (directory / "contracts").mkdir()
    symlink((directory / "contracts" / "api.md"), secret)
    symlink((directory / "checklists"), tmp_path, target_is_directory=True)
    docs = documents_of(engine, project, directory)
    assert "TOP SECRET" not in json.dumps(docs)
    assert "spec.md" not in [doc["name"] for doc in docs]
    assert "contracts/api.md" not in [doc["name"] for doc in docs]


def test_a_large_document_is_cut_and_marked(engine, project, monkeypatch):
    monkeypatch.setattr(engine, "MAX_DOC_BYTES", 10)
    directory = project.feature(spec="x" * 50, plan="short", tasks=None)
    by_name = {doc["name"]: doc for doc in documents_of(engine, project, directory)}
    assert (by_name["spec.md"]["text"], by_name["spec.md"]["truncated"]) == ("x" * 10, True)
    assert (by_name["plan.md"]["text"], by_name["plan.md"]["truncated"]) == ("short", False)


def test_the_documents_of_a_page_share_a_budget(engine, project, monkeypatch):
    monkeypatch.setattr(engine, "MAX_DOCS_TOTAL_BYTES", 15)
    directory = project.feature(spec="x" * 10, plan="y" * 10, tasks="z" * 10)
    docs = documents_of(engine, project, directory)
    assert sum(len(doc["text"]) for doc in docs) == 15
    assert [doc["truncated"] for doc in docs] == [False, True, True]


def test_many_contracts_are_bounded(engine, project, monkeypatch):
    monkeypatch.setattr(engine, "MAX_CONTRACT_FILES", 2)
    directory = project.feature()
    (directory / "contracts").mkdir()
    for number in range(5):
        (directory / "contracts" / ("c%d.md" % number)).write_text("x", encoding="utf-8")
    assert len([doc for doc in documents_of(engine, project, directory) if doc["name"].startswith("contracts/")]) == 2


# -- Reading without writing, and speed ------------------------------------------------------


def test_the_summary_for_terminals_writes_nothing(engine, project):
    project.feature(events=[task_event("T002", "in_progress", actor={"harness": "claude"})])
    before = project.written()
    rows = engine.status_data(project.root)
    assert project.written() == before
    assert rows[0]["totals"]["in_progress"] == 1
    assert rows[0]["active"][0]["id"] == "T002"
    assert rows[0]["abandoned"] == ["T002"]
    assert "documents" not in rows[0]
    assert [phase["done"] for phase in rows[0]["phases"]] == [1, 0]


def test_a_large_spec_is_drawn_quickly(engine, project):
    tasks = "## Phase 1\n" + "".join("- [ ] T%04d [P] [US1] Task number %d in src/file_%d.py\n" % (n, n, n) for n in range(1, 501))
    directory = project.feature(tasks=tasks)
    project.log(directory, [task_event("T%04d" % n, "in_progress", note="n", files=["f.py"], actor={"harness": "claude"}) for n in range(1, 501)])
    started = time.perf_counter()
    engine.render_project(project.root, directory)
    assert time.perf_counter() - started < 3


# -- Running on its own ----------------------------------------------------------------------


def engine_file():
    return Path(os.environ.get("SPECKIT_PROGRESS_ENGINE_UNDER_TEST") or ROOT / "scripts" / "progress" / "engine.py")


def test_the_engine_parses_on_python_3_9():
    ast.parse(engine_file().read_text(encoding="utf-8"), feature_version=(3, 9))


def test_the_engine_source_is_plain_ascii():
    assert engine_file().read_bytes().isascii()


def test_the_engine_needs_only_the_standard_library():
    tree = ast.parse(engine_file().read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative imports need a package"
            imported.add(node.module.split(".")[0])
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}


def run_engine(*args, cwd):
    return subprocess.run([sys.executable, "-I", str(engine_file()), *args], cwd=str(cwd), capture_output=True, text=True, check=False)


def test_it_runs_with_no_package_installed(project, tmp_path):
    project.feature()
    done = run_engine("render", "--root", str(project.root), cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["pages"][0]["id"] == "001-login"
    assert page_of(project).is_file()


def test_its_status_runs_on_its_own(project, tmp_path):
    project.feature()
    done = run_engine("status", "--root", str(project.root), "--feature", "001", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)[0]["totals"]["total"] == 4


def test_it_fails_clearly_outside_a_project(tmp_path):
    done = run_engine("render", "--root", str(tmp_path), cwd=tmp_path)
    assert done.returncode == 1
    assert "not a Spec Kit project" in done.stderr
    assert done.stdout == ""


def test_it_fails_clearly_for_an_unknown_spec(project, tmp_path):
    project.feature()
    done = run_engine("render", "--root", str(project.root), "--feature", "zzz", cwd=tmp_path)
    assert done.returncode == 1
    assert "No spec named" in done.stderr


def test_the_engine_is_packaged():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"scripts/progress" = "specify_cli/core_pack/scripts/progress"' in text
    for name in ("engine.py", "page.html", "index.html"):
        assert (ROOT / "scripts" / "progress" / name).is_file()


@pytest.mark.parametrize(
    ("env", "platform", "expected"),
    [
        ({}, "darwin", True),
        ({}, "win32", True),
        ({"DISPLAY": ":0"}, "linux", True),
        ({"WAYLAND_DISPLAY": "wayland-0"}, "linux", True),
        ({}, "linux", False),
        ({"CI": "true"}, "darwin", False),
        ({"CI": "1"}, "darwin", False),
        ({"CI": "false"}, "darwin", True),
        ({"CI": "0"}, "darwin", True),
        ({"CI": ""}, "darwin", True),
        ({"SSH_CONNECTION": "a b c d"}, "darwin", False),
        ({"SSH_CLIENT": "a b c"}, "darwin", False),
        ({"SSH_TTY": "/dev/ttys001"}, "darwin", False),
        ({"SSH_TTY": "/dev/ttys001", "DISPLAY": ":0"}, "linux", False),
    ],
)
def test_when_a_browser_may_open(engine, env, platform, expected):
    assert engine.can_open_browser(env, platform) is expected
