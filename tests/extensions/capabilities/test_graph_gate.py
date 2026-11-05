"""The door to Graphify. With an executable that records what it receives, with no executable at all, and with the real tool if it is there."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from specify_cli._graphify import REINSTALL_COMMAND

from .conftest import PYTHON, ROOT, SCRIPT

GATE = SCRIPT.with_name("cap_graph.py")
REINSTALL = "uv tool install specify-cli --force --from git+https://github.com/lema017/speckit-vs.git"
MAIN = SCRIPT
PINNED = "0.9.102"
JAVA = "src/main/java/com/example/auth/SessionService.java"
# What real Graphify 0.9.102 wrote for the class in JAVA, cut down to the nodes used here.
REAL_GRAPH = {
    "directed": False,
    "multigraph": False,
    "graph": {"schema_version": 1, "graphify_version": PINNED},
    "nodes": [
        {"id": "a", "label": "SessionService", "source_file": JAVA, "source_location": "L6"},
        {"id": "b", "label": ".isExpired()", "source_file": JAVA, "source_location": "L10"},
        {"id": "c", "label": "SessionService.java", "source_file": JAVA, "source_location": "L1"},
        {"id": "d", "label": "duration", "source_file": ""},
    ],
    "links": [],
}
SOURCE = """public class SessionService {
    public static final Duration TIMEOUT = Duration.ofMinutes(15);
    public boolean isExpired(Duration idle) { return true; }
}
"""
# It knows its paths by being written with them: the door passes no other variable to the tool.
FAKE = """#!/bin/sh
printf '%s\\n' "$*" >> "{log}"
env >> "{env_log}"
case "$1" in
  --version) echo "graphify {version}"; exit 0 ;;
  update)
    {update_output}
    [ "{update_rc}" = 0 ] || exit {update_rc}
    mkdir -p graphify-out
    cp "{graph}" graphify-out/graph.json
    exit 0 ;;
  *) {answer}; exit {read_rc} ;;
esac
"""


class World:
    def __init__(self, tmp_path):
        self.root = tmp_path / "project"
        self.root.mkdir()
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self.tool_bin = tmp_path / "uv-tools" / "specify-cli" / "bin"
        self.log = tmp_path / "calls.log"
        self.env_log = tmp_path / "env.log"
        self.graph = tmp_path / "graph.json"
        self.graph.write_text(json.dumps(REAL_GRAPH), encoding="utf-8")
        self.env = {
            "PATH": str(self.bin) + os.pathsep + "/usr/bin" + os.pathsep + "/bin",
            "HOME": str(tmp_path),
            "ANTHROPIC_API_KEY": "secret-anthropic",
            "OPENAI_API_KEY": "secret-openai",
            "GEMINI_API_KEY": "secret-gemini",
        }

    def install(self, version=PINNED, update_rc=0, read_rc=0, answer='echo "output of $1"', update_output=":", into=None):
        if os.name == "nt":
            pytest.skip("the stand-in for Graphify is a shell script, which Windows cannot execute")
        path = (into or self.bin) / "graphify"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            FAKE.format(log=self.log, env_log=self.env_log, graph=self.graph, version=version, update_rc=update_rc, read_rc=read_rc, answer=answer, update_output=update_output),
            encoding="utf-8",
        )
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return self

    def install_specify(self, link=True):
        """A specify as ``uv tool install`` leaves it: the link on PATH, and the real one in the environment of the tool."""
        real = self.tool_bin / "specify"
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        real.chmod(real.stat().st_mode | stat.S_IEXEC)
        on_path = self.bin / "specify"
        if link:
            on_path.symlink_to(real)
        else:
            shutil.copy(str(real), str(on_path))
        return self

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run(self, *args, script=GATE):
        done = subprocess.run(
            [PYTHON, "-I", "-S", str(script), *args, "--root", str(self.root)],
            capture_output=True, encoding="utf-8", errors="replace", env=self.env,
        )
        return done.returncode, json.loads(done.stdout) if done.stdout.strip() else {"stderr": done.stderr}

    def calls(self):
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def seen_env(self):
        return self.env_log.read_text(encoding="utf-8") if self.env_log.exists() else ""

    def tree(self):
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


# ---------------------------------------------------------------- without the tool


def test_status_without_graphify_says_how_to_go_on(world):
    rc, out = world.run("status")
    assert rc == 0
    assert out["available"] is False and out["status"] == "degraded"
    assert out["install"] == REINSTALL
    assert "rg" in out["fallback"]


@pytest.mark.parametrize("args", [("update",), ("explain", "SessionService"), ("affected", JAVA + "::SessionService"), ("query", "session", "timeout")])
def test_without_graphify_every_read_is_degraded_and_nothing_is_written(world, args):
    rc, out = world.run(*args)
    assert rc == 6
    assert out["status"] == "degraded" and out["reason"] == "not-installed"
    assert world.tree() == []


@pytest.mark.parametrize("args", [("update",), ("explain", "SessionService"), ("affected", "SessionService"), ("query", "session")])
def test_without_graphify_the_way_out_is_to_reinstall_specify(world, args):
    _, out = world.run(*args)
    assert out["install"] == REINSTALL
    assert "graphifyy" not in out["install"]


def test_anchors_without_graphify_fall_back_to_the_file_and_the_name_and_say_so(world):
    world.write(JAVA, SOURCE)
    world.write(
        "specs/_capabilities/login/implementation.md",
        "## Rule Status\n\n### R-a\n- Code: `%s::TIMEOUT`, `%s::Gone`, `src/nope.java`\n- Tests: none\n" % (JAVA, JAVA),
    )
    before = world.tree()
    rc, out = world.run("anchors")
    assert rc == 0 and out["status"] == "degraded"
    assert {row["ref"]: row["found"] for row in out["anchors"]} == {JAVA + "::TIMEOUT": "by-name", JAVA + "::Gone": "missing", "src/nope.java": "missing"}
    assert out["missing"] == [JAVA + "::Gone", "src/nope.java"]
    assert any("file exists and contains the name" in warning for warning in out["warnings"])
    assert world.tree() == before


def test_the_main_script_reaches_the_gate_with_the_same_exit_code(world):
    rc, out = world.run("graph", "status", script=MAIN)
    assert rc == 0 and out["available"] is False
    rc, out = world.run("graph", "explain", "SessionService", script=MAIN)
    assert rc == 6 and out["reason"] == "not-installed"
    rc, _ = world.run("graph", "explain", script=MAIN)
    assert rc == 2


# ---------------------------------------------------------------- with the tool


def test_the_tool_runs_with_its_settings_and_no_llm_key(world):
    world.install()
    rc, out = world.run("explain", "SessionService")
    assert rc == 0 and out["status"] == "ok" and out["output"].startswith("output of explain")
    env = world.seen_env()
    assert "GRAPHIFY_BACKEND=none" in env and "GRAPHIFY_QUERY_LOG_DISABLE=1" in env
    assert "secret-" not in env and "API_KEY" not in env


@pytest.mark.parametrize(
    "args",
    [("status",), ("update",), ("explain", "X"), ("explain", "X", "--all"), ("affected", "X"), ("affected", "X", "--depth", "1"), ("query", "a", "b"), ("anchors",)],
)
def test_only_the_commands_the_plan_allows_reach_the_tool(world, args):
    world.install()
    world.run(*args)
    assert world.calls()
    for call in world.calls():
        assert call.split()[0] in ("--version", "update", "explain", "affected", "query"), call
        assert "--strict" not in call and "install" not in call and "watch" not in call and "extract" not in call


@pytest.mark.parametrize(
    "args, expected",
    [
        (("explain", "X"), ["update .", "--version", "explain X"]),
        (("explain", "X", "--all"), ["update .", "--version", "explain X --all"]),
        (("affected", "X", "--depth", "1"), ["update .", "--version", "affected X --depth 1"]),
        (("query", "session", "timeout"), ["update .", "--version", "query session timeout"]),
    ],
)
def test_every_read_updates_the_graph_first(world, args, expected):
    world.install()
    world.run(*args)
    assert world.calls() == expected


def test_a_failed_update_never_reads_an_old_graph(world):
    world.install(update_rc=1)
    world.write("graphify-out/graph.json", json.dumps(REAL_GRAPH))
    rc, out = world.run("explain", "X")
    assert rc == 6 and out["reason"] == "update-failed"
    assert not any(call.startswith("explain") for call in world.calls())


def test_a_version_other_than_the_validated_one_warns_and_still_runs(world):
    world.install(version="0.9.200")
    rc, out = world.run("status")
    assert rc == 0 and out["version"] == "0.9.200"
    assert out["warnings"] == ["Graphify 0.9.200 is not the validated %s" % PINNED]
    rc, out = world.run("explain", "X")
    assert rc == 0 and out["warnings"] == ["Graphify 0.9.200 is not the validated %s" % PINNED]
    world.install()
    (world.root / "graphify-out/graph.json").unlink()
    rc, out = world.run("status")
    assert out["warnings"] == [] and out["graph"] is False


@pytest.mark.parametrize("code, status", [(4, "not-found"), (3, "ambiguous")])
def test_the_answers_of_the_tool_keep_their_meaning(world, code, status):
    world.install(read_rc=code)
    rc, out = world.run("explain", "X")
    assert rc == 0 and out["status"] == status


def test_another_failure_of_the_tool_is_degraded_with_its_message(world):
    world.install(read_rc=1)
    rc, out = world.run("explain", "X")
    assert rc == 6 and out["reason"] == "read-failed"


def test_affected_warns_when_the_name_repeats_because_callers_may_be_false(world):
    world.install()
    graph = json.loads(json.dumps(REAL_GRAPH))
    graph["nodes"].append({"id": "e", "label": ".isExpired()", "source_file": "src/Other.java"})
    world.graph.write_text(json.dumps(graph), encoding="utf-8")
    rc, out = world.run("affected", JAVA + "::.isExpired()")
    assert rc == 0
    assert out["warnings"] == ["2 nodes share this name: confirm the callers in the code"]
    world.graph.write_text(json.dumps(REAL_GRAPH), encoding="utf-8")
    rc, out = world.run("affected", JAVA + "::.isExpired()")
    assert rc == 0 and out["warnings"] == []


def test_a_question_in_spanish_gets_a_warning(world):
    world.install()
    _, out = world.run("query", "sesión")
    assert any("technical English" in warning for warning in out["warnings"])
    _, out = world.run("query", "session")
    assert out["warnings"] == []


def test_long_output_is_cut_and_says_so(world):
    world.install(answer="yes x | head -c 30000")
    _, out = world.run("explain", "X")
    assert len(out["output"]) == 20000 and out["truncated"] is True


# ---------------------------------------------------------------- what it writes


def test_ignores_are_written_once_and_a_choice_of_the_project_is_kept(world):
    world.install()
    world.write(".gitignore", "node_modules/")
    rc, out = world.run("update")
    assert rc == 0 and out["wrote"] == [".graphifyignore", "graphify-out/.gitignore"]
    assert (world.root / "graphify-out/.gitignore").read_text(encoding="utf-8") == "*\n"
    ignore = (world.root / ".graphifyignore").read_text(encoding="utf-8").splitlines()
    for needle in ("tests/", "src/test/", "*.test.*", "*.md", "*.json", ".specify/", ".claude/", "node_modules/", "target/", "build/", "specs/"):
        assert needle in ignore
    assert (world.root / ".gitignore").read_text(encoding="utf-8") == "node_modules/"

    world.write(".graphifyignore", "mine/\n")
    rc, out = world.run("update")
    assert rc == 0 and out["wrote"] == []
    assert (world.root / ".graphifyignore").read_text(encoding="utf-8") == "mine/\n"


def test_a_project_it_cannot_write_to_is_degraded_and_not_a_traceback(world):
    world.install()
    world.write("graphify-out", "a file where the directory goes")
    rc, out = world.run("explain", "x")
    assert rc == 6 and out["status"] == "degraded", out
    assert world.calls() == []


def test_anchors_still_answer_by_name_in_a_project_it_cannot_write_to(world):
    """Anchors do not need the graph, so a directory it cannot create costs a warning and not the answer."""
    world.install()
    world.write("graphify-out", "a file where the directory goes")
    world.write("src/a.py", "class Thing:\n    pass\n")
    world.write("specs/_capabilities/login/implementation.md", "- Code: `src/a.py::Thing`\n")
    rc, out = world.run("anchors")
    assert rc == 0 and out["status"] == "degraded", out
    assert out["anchors"][0]["found"] == "by-name"


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="needs a file this user cannot read")
def test_a_file_it_cannot_read_is_degraded_and_not_a_traceback(world):
    world.write("src/a.py", "class Thing:\n    pass\n")
    world.write("specs/_capabilities/login/implementation.md", "- Code: `src/a.py::Thing`\n")
    secret = world.root / "src/a.py"
    secret.chmod(0)
    try:
        rc, out = world.run("anchors")
    finally:
        secret.chmod(0o644)
    assert rc == 6 and out["reason"] == "read-failed" and "a.py" in out["detail"], out


def test_a_root_that_does_not_exist_is_invalid_input(world, tmp_path):
    world.install()
    world.root = tmp_path / "nowhere"
    rc, out = world.run("status")
    assert rc == 2 and "--root" in out["stderr"], out


@pytest.mark.parametrize(
    "graph",
    [
        {"graph": {"schema_version": 1}, "nodes": ["not a node"]},
        {"graph": {"schema_version": 1}, "nodes": {"not": "a list"}},
        {"graph": ["not a table"], "nodes": []},
        ["not", "a", "graph"],
    ],
)
def test_a_graph_of_another_shape_falls_back_to_the_name(world, graph):
    world.install()
    world.graph.write_text(json.dumps(graph), encoding="utf-8")
    world.write("src/a.py", "class Thing:\n    pass\n")
    world.write("specs/_capabilities/login/implementation.md", "- Code: `src/a.py::Thing`\n")
    rc, out = world.run("anchors")
    assert rc == 0 and out["status"] == "degraded", out
    assert out["anchors"][0]["found"] == "by-name"


def test_a_node_whose_fields_are_not_text_is_left_out(world):
    world.install()
    world.graph.write_text(json.dumps({"graph": {"schema_version": 1}, "nodes": [{"source_file": ["not", "text"], "label": "x"}]}), encoding="utf-8")
    world.write("src/a.py", "class Thing:\n    pass\n")
    world.write("specs/_capabilities/login/implementation.md", "- Code: `src/a.py::Thing`\n")
    rc, out = world.run("anchors")
    assert rc == 0 and out["anchors"][0]["found"] == "by-name", out


def test_nothing_is_written_through_a_link_that_leaves_the_project(world, tmp_path):
    world.install()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (world.root / "graphify-out").symlink_to(elsewhere)
    (world.root / ".graphifyignore").symlink_to(elsewhere / "ignored")
    rc, out = world.run("update")
    assert rc == 0 and out["wrote"] == [], out
    assert not (elsewhere / ".gitignore").exists() and not (elsewhere / "ignored").exists()


# ---------------------------------------------------------------- anchors, with a graph


def anchored(world, *refs):
    world.write(JAVA, SOURCE)
    world.write("specs/_capabilities/login/implementation.md", "### R-a\n- Code: %s\n" % ", ".join("`%s`" % ref for ref in refs))
    world.write("specs/_capabilities/other/implementation.md", "### R-b\n- Code: `src/other.java`\n")


def test_anchors_read_the_graph_and_fall_back_for_what_it_does_not_model(world):
    world.install()
    anchored(world, JAVA + "::SessionService", JAVA + "::.isExpired()", JAVA + "::TIMEOUT", JAVA + "::Gone", JAVA)
    rc, out = world.run("anchors", "--capability", "login")
    assert rc == 0 and out["status"] == "ok"
    assert {row["ref"]: row["found"] for row in out["anchors"]} == {
        JAVA + "::SessionService": "unique",
        JAVA + "::.isExpired()": "unique",
        JAVA + "::TIMEOUT": "by-name",
        JAVA + "::Gone": "missing",
        JAVA: "unique",
    }
    assert out["missing"] == [JAVA + "::Gone"]


def test_an_anchor_outside_the_project_is_missing_even_if_the_file_exists(world, tmp_path):
    world.write(JAVA, SOURCE)
    (tmp_path / "outside.java").write_text("class Outside {}\n", encoding="utf-8")
    world.write("specs/_capabilities/login/implementation.md", "### R-a\n- Code: `../outside.java::Outside`\n")
    rc, out = world.run("anchors")
    assert rc == 0 and out["missing"] == ["../outside.java::Outside"]


def test_anchors_read_a_reference_as_the_main_script_does(world):
    world.write("src/a.py", "class Manager:\n    def expiry(self):\n        pass\n")
    world.write(
        "specs/_capabilities/login/implementation.md",
        "- Code: `src/a.py::Manager::expiry`, `src/a.py::Manager::gone`\n\n- Code: src/deleted.py::gone, none\n",
    )
    rc, out = world.run("anchors")
    found = {row["ref"]: row["found"] for row in out["anchors"]}
    assert found == {"src/a.py::Manager::expiry": "by-name", "src/a.py::Manager::gone": "missing", "src/deleted.py::gone": "missing"}, out
    assert out["missing"] == ["src/a.py::Manager::gone", "src/deleted.py::gone"]


def test_a_repeated_symbol_in_a_file_is_ambiguous(world):
    world.install()
    graph = json.loads(json.dumps(REAL_GRAPH))
    graph["nodes"].append({"id": "e", "label": ".isExpired()", "source_file": JAVA})
    world.graph.write_text(json.dumps(graph), encoding="utf-8")
    anchored(world, JAVA + "::.isExpired()")
    _, out = world.run("anchors", "--capability", "login")
    assert out["anchors"][0]["found"] == "ambiguous"


def test_anchors_cover_every_capability_unless_one_is_named(world):
    world.install()
    anchored(world, JAVA + "::SessionService")
    _, out = world.run("anchors")
    assert sorted(row["capability"] for row in out["anchors"]) == ["login", "other"]


@pytest.mark.parametrize("schema", [2, None])
def test_a_graph_format_not_validated_degrades_with_a_warning(world, schema):
    world.install()
    graph = json.loads(json.dumps(REAL_GRAPH))
    graph["graph"]["schema_version"] = schema
    world.graph.write_text(json.dumps(graph), encoding="utf-8")
    anchored(world, JAVA + "::SessionService", JAVA + "::Gone")
    rc, out = world.run("anchors", "--capability", "login")
    assert rc == 0 and out["status"] == "degraded"
    assert {row["found"] for row in out["anchors"]} == {"by-name", "missing"}
    assert any("format not recognised" in warning for warning in out["warnings"])


# ---------------------------------------------------------------- invalid input


@pytest.mark.parametrize(
    "args",
    [("explain",), ("explain", "a", "b"), ("affected",), ("query",), ("status", "x"), ("update", "x"), ("anchors", "x"), ("anchors", "--capability", "No/Good"), ("install",), ("extract",), ("watch",)],
)
def test_invalid_input_is_refused_before_the_tool_runs(world, args):
    world.install()
    rc, _ = world.run(*args)
    assert rc == 2
    assert world.calls() == []


@pytest.mark.parametrize("terms", [("explain", "--", "--strict"), ("affected", "--", "--help"), ("query", "--", "a", "--strict")])
def test_a_flag_cannot_reach_the_tool_after_a_double_dash(world, terms):
    world.install()
    done = subprocess.run(
        [PYTHON, "-I", "-S", str(GATE), "--root", str(world.root), *terms],
        capture_output=True, encoding="utf-8", errors="replace", env=world.env,
    )
    assert done.returncode == 2, done.stdout
    assert world.calls() == []


# ---------------------------------------------------------------- where the tool is found


def test_the_tool_beside_specify_is_found_with_nothing_on_path(world):
    world.install_specify().install(into=world.tool_bin)
    assert not (world.bin / "graphify").exists()
    rc, out = world.run("status")
    assert rc == 0 and out["available"] is True and out["version"] == PINNED and out["warnings"] == []
    rc, out = world.run("update")
    assert rc == 0 and out["status"] == "ok"


def test_the_tool_beside_specify_wins_over_the_one_on_path(world):
    world.install_specify().install(version="9.9.9").install(into=world.tool_bin)
    _, out = world.run("status")
    assert out["version"] == PINNED and out["warnings"] == []


def test_the_tool_on_path_still_works_and_warns_about_its_version(world):
    world.install_specify().install(version="9.9.9")
    _, out = world.run("status")
    assert out["available"] is True and out["version"] == "9.9.9"
    assert out["warnings"] == ["Graphify 9.9.9 is not the validated " + PINNED]


def test_specify_alone_does_not_count_as_the_tool(world):
    world.install_specify()
    rc, out = world.run("update")
    assert rc == 6 and out["reason"] == "not-installed"
    assert world.tree() == []


def test_a_copy_of_specify_finds_what_is_beside_the_copy(world):
    world.install_specify(link=False).install(into=world.tool_bin)
    rc, out = world.run("update")
    assert rc == 6 and out["reason"] == "not-installed"


# ---------------------------------------------------------------- a project without code


def test_a_project_without_code_is_not_a_failure_of_the_tool(world):
    world.install(update_rc=1, update_output='echo "[graphify watch] No code files found - nothing to rebuild."')
    for args in (("update",), ("query", "session")):
        rc, out = world.run(*args)
        assert rc == 6 and out["status"] == "degraded" and out["reason"] == "no-code"
        assert "install" not in out


def test_another_failed_update_is_still_a_failure(world):
    world.install(update_rc=1, update_output='echo "something else went wrong"')
    rc, out = world.run("update")
    assert rc == 6 and out["reason"] == "update-failed"
    assert "install" not in out


def test_no_code_in_a_successful_update_changes_nothing(world):
    world.install(update_output='echo "No code files found in one folder"')
    rc, out = world.run("update")
    assert rc == 0 and out["status"] == "ok"


# ---------------------------------------------------------------- the real tool, which arrives with specify


def real_graphify():
    """The one installed with this environment, as specify gets it. It is a dependency, so it must be there."""
    path = shutil.which("graphify", path=str(Path(sys.executable).parent))
    assert path, "graphifyy is a dependency of specify, so it must be beside this Python"
    return path


def test_the_dependency_and_the_gate_pin_the_same_version():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "graphifyy==" + PINNED in project["project"]["dependencies"]
    assert 'PINNED = "%s"' % PINNED in GATE.read_text(encoding="utf-8")


def test_the_installed_tool_is_the_pinned_version():
    done = subprocess.run([real_graphify(), "--version"], capture_output=True, encoding="utf-8", errors="replace")
    assert PINNED in done.stdout


# Every path out of the machine refuses and records. Which modules load proves nothing: graphify.security
# imports http.client, ssl and urllib.request in every command.
NETWORK_PROBE = """
import json, os, socket, sys

attempts = []
leave = os._exit

def report():
    sys.stderr.write("\\nNETWORK " + json.dumps({"attempts": attempts, "modules": sorted(sys.modules)}) + "\\n")
    sys.stderr.flush()

def report_and_leave(code):
    report()
    leave(code)

os._exit = report_and_leave

def refuse(*args, **kwargs):
    attempts.append(repr(args))
    raise OSError("no network in this test")

socket.socket.connect = refuse
socket.socket.connect_ex = refuse
socket.getaddrinfo = refuse
socket.create_connection = refuse
sys.argv = ["graphify", *sys.argv[1:]]
from graphify.__main__ import main
try:
    main()
except SystemExit:
    pass
finally:
    report()
"""


def network_use(root, *args):
    env = {key: value for key, value in os.environ.items() if key in ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")}
    # With the seed already set, update does not restart itself, which would leave the probe behind.
    env.update(GRAPHIFY_BACKEND="none", GRAPHIFY_QUERY_LOG_DISABLE="1", PYTHONHASHSEED="0")
    done = subprocess.run([sys.executable, "-c", NETWORK_PROBE, *args], cwd=str(root), env=env, capture_output=True, encoding="utf-8", errors="replace")
    line = next(line for line in done.stderr.splitlines() if line.startswith("NETWORK "))
    return json.loads(line[len("NETWORK "):])


@pytest.mark.parametrize("args", [("update", "."), ("affected", "src/session.py::helper"), ("query", "session expiry"), ("explain", "src/session.py::SessionManager")])
def test_the_commands_the_gate_uses_try_no_connection(tmp_path, args):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "session.py").write_text("class SessionManager:\n    def expiry(self):\n        return helper()\n\n\ndef helper():\n    return 15\n", encoding="utf-8")
    # The first update is a full build, the other commands read what it wrote.
    assert network_use(tmp_path, "update", ".")["attempts"] == []
    assert network_use(tmp_path, *args)["attempts"] == []


def test_the_network_probe_notices_a_connection(tmp_path):
    probe = NETWORK_PROBE.replace("from graphify.__main__ import main", "def main():\n    socket.create_connection(('example.invalid', 80))")
    done = subprocess.run([sys.executable, "-c", probe], cwd=str(tmp_path), capture_output=True, encoding="utf-8", errors="replace")
    line = next(line for line in done.stderr.splitlines() if line.startswith("NETWORK "))
    assert "example.invalid" in json.loads(line[len("NETWORK "):])["attempts"][0]


def test_specify_and_the_gate_offer_the_same_way_to_reinstall():
    assert 'INSTALL = "%s"' % REINSTALL_COMMAND in GATE.read_text(encoding="utf-8")
    assert REINSTALL == REINSTALL_COMMAND


@pytest.mark.skipif(os.name == "nt", reason="a link on PATH is how uv leaves specify on POSIX")
def test_a_new_project_reaches_the_tool_with_graphify_off_path(tmp_path):
    """The shape of ``uv tool install``. A real one was also checked by hand, since it needs the network."""
    on_path = tmp_path / "bin"
    on_path.mkdir()
    (on_path / "specify").symlink_to(shutil.which("specify", path=str(Path(sys.executable).parent)))
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    env = dict(os.environ, HOME=str(tmp_path), PATH=os.pathsep.join((str(on_path), "/usr/bin", "/bin")))
    assert shutil.which("graphify", path=env["PATH"]) is None
    subprocess.run(
        ["specify", "init", "--here", "--force", "--integration", "claude", "--script", "sh", "--ignore-agent-tools"],
        cwd=str(project), env=env, capture_output=True, encoding="utf-8", errors="replace", check=True,
    )
    assert (project / "graphify-out/graph.json").is_file()
    installed = project / ".specify/extensions/capabilities/scripts/python/cap_graph.py"
    done = subprocess.run([PYTHON, "-I", "-S", str(installed), "status", "--root", str(project)], env=env, capture_output=True, encoding="utf-8")
    out = json.loads(done.stdout)
    assert out["available"] is True and out["version"] == PINNED and out["graph"] is True


def test_the_real_tool_says_when_there_is_no_code(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    env = dict(os.environ, HOME=str(tmp_path), PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))
    done = subprocess.run([PYTHON, "-I", "-S", str(GATE), "update", "--root", str(root)], capture_output=True, encoding="utf-8", env=env)
    assert done.returncode == 6, done.stdout
    assert json.loads(done.stdout)["reason"] == "no-code"


def test_the_real_tool_answers_through_the_gate(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "session.py").write_text("class SessionManager:\n    def expiry(self):\n        return helper()\n\n\ndef helper():\n    return 15\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_session.py").write_text("def test_noise():\n    pass\n", encoding="utf-8")
    (root / "specs/_capabilities/login").mkdir(parents=True)
    (root / "specs/_capabilities/login/implementation.md").write_text("### R-a\n- Code: `src/session.py::SessionManager`, `src/session.py::Gone`\n", encoding="utf-8")
    env = dict(os.environ, HOME=str(tmp_path), PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))

    def gate(*args):
        done = subprocess.run([PYTHON, "-I", "-S", str(GATE), *args, "--root", str(root)], capture_output=True, encoding="utf-8", env=env)
        return done.returncode, json.loads(done.stdout)

    rc, out = gate("status")
    assert rc == 0 and out["available"] is True and out["version"] == PINNED and out["warnings"] == []
    rc, out = gate("explain", "src/session.py::SessionManager")
    assert rc == 0 and "SessionManager" in out["output"]
    rc, out = gate("affected", "src/session.py::helper")
    assert rc == 0 and "expiry" in out["output"]
    rc, out = gate("query", "session", "expiry")
    assert rc == 0 and "SessionManager" in out["output"]
    rc, out = gate("explain", "NoSuchThing")
    assert rc == 0 and out["status"] == "not-found"
    rc, out = gate("anchors")
    assert out["status"] == "ok"
    assert {row["ref"]: row["found"] for row in out["anchors"]} == {"src/session.py::SessionManager": "unique", "src/session.py::Gone": "missing"}
    labels = {node.get("source_file") for node in json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8"))["nodes"]}
    assert "tests/test_session.py" not in labels


def test_the_gate_needs_nothing_but_the_standard_library():
    done = subprocess.run([PYTHON, "-I", "-S", str(GATE), "--help"], capture_output=True, encoding="utf-8")
    assert done.returncode == 0 and "--capability" in done.stdout
