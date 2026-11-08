"""The wrappers a model runs instead of each command's first script.

The model parses that script's output, so the promise is byte for byte: same stdout, same stderr,
same exit code, whatever happens to the progress page. Every case runs the real command from the
real template, once as it was and once through the wrapper, from the same starting state.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from rich.console import Console

from specify_cli.shared_infra import install_shared_infra
from tests.conftest import _has_working_bash
from tests.parity_helpers import HAS_PWSH, WINDOWS_POWERSHELL

# mutants.py points this at a changed copy of the scripts and templates. Nothing else sets it.
REPO = Path(os.environ.get("SPECKIT_PROGRESS_SOURCES_UNDER_TEST") or Path(__file__).resolve().parents[3])
TEMPLATES = REPO / "templates" / "commands"
COMMANDS = sorted(path.stem for path in TEMPLATES.glob("*.md") if path.stem != "progress")

_HAS_BASH = _has_working_bash()
_SHELLS = (["pwsh"] if HAS_PWSH else []) + ([WINDOWS_POWERSHELL] if WINDOWS_POWERSHELL else [])


def _variants():
    """Every way to run a script here. Windows PowerShell 5.1 is its own case, not a stand-in."""
    found = []
    if _HAS_BASH:
        found.append(("sh", ["bash"]))
    found.append(("py", [sys.executable]))
    for shell in _SHELLS:
        found.append(("ps", [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]))
    return found


def _variant_id(variant):
    return variant[0] if variant[0] != "ps" else Path(variant[1][0]).stem.lower()


VARIANTS = _variants()
SCRIPT_TYPES = sorted({variant[0] for variant in VARIANTS})

SPEC = "# Feature Specification: Login\n\n- **FR-001**: Sign in.\n"
PLAN = "# Implementation Plan: Login\n\nBuild it.\n"
TASKS = "# Tasks: Login\n\n## Phase 1\n\n- [X] T001 Create\n- [ ] T002 Lint\n"


def header_command(command: str, script_type: str) -> list[str]:
    """The template's own script line, as it reaches the project."""
    text = (TEMPLATES / (command + ".md")).read_text(encoding="utf-8")
    line = re.search(r"^\s*%s: (.+)$" % script_type, text, re.MULTILINE).group(1)
    return re.sub(r"(^| )scripts/", r"\1.specify/scripts/", line).split()


def split_header(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Return the whole wrapped command and the script it wraps, with its arguments."""
    return tokens, tokens[3:]


def build(root: Path, script_type: str, state: str) -> None:
    """The same starting point every time, at the same path, so absolute paths in output match."""
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    install_shared_infra(
        root, script_type, version="0.0.0", core_pack=None, repo_root=REPO, console=Console(quiet=True),
    )
    if state == "no-spec":
        return
    directory = root / "specs" / "001-login"
    directory.mkdir(parents=True)
    (directory / "spec.md").write_text(SPEC, encoding="utf-8")
    (root / ".specify" / "feature.json").write_text(
        json.dumps({"feature_directory": "specs/001-login"}), encoding="utf-8"
    )
    if state == "only-spec":
        return
    (directory / "plan.md").write_text(PLAN, encoding="utf-8")
    (directory / "tasks.md").write_text(TASKS, encoding="utf-8")


def run_tool(variant, tokens, root: Path, env=None, stdin=None):
    return subprocess.run(
        variant[1] + tokens,
        cwd=root,
        capture_output=True,
        input=stdin if stdin is not None else b"",
        env=env or clean_env(),
        check=False,
        timeout=120,
    )


def clean_env():
    env = {key: value for key, value in os.environ.items() if not key.startswith("SPECIFY_") and key != "CI"}
    env["SPECKIT_PROGRESS_NO_BROWSER"] = "1"
    return env


def same(direct, wrapped):
    assert wrapped.stdout == direct.stdout
    assert wrapped.stderr == direct.stderr
    assert wrapped.returncode == direct.returncode


def read_log(root: Path):
    path = root / "specs" / "001-login" / "progress.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def root(tmp_path):
    return tmp_path / "project"


# -- Same output, whatever the state of the project --------------------------------------------


@pytest.mark.parametrize("state", ["ready", "only-spec", "no-spec"])
@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_output_and_exit_code_are_the_same_with_and_without_the_wrapper(root, variant, command, state):
    wrapped_tokens, direct_tokens = split_header(header_command(command, variant[0]))
    build(root, variant[0], state)
    direct = run_tool(variant, direct_tokens, root)
    build(root, variant[0], state)
    wrapped = run_tool(variant, wrapped_tokens, root)
    same(direct, wrapped)


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_ready_project_really_succeeds_so_the_comparison_means_something(root, variant, command):
    wrapped_tokens, _ = split_header(header_command(command, variant[0]))
    build(root, variant[0], "ready")
    result = run_tool(variant, wrapped_tokens, root)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.decode("utf-8", "replace"))


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_the_progress_command_asks_for_its_page_to_open(root, variant):
    tokens, _ = split_header(header_command("progress", variant[0]))
    assert tokens[-2:] == ["show", "--open"]
    build(root, variant[0], "ready")
    result = run_tool(variant, tokens, root)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.decode("utf-8", "replace").splitlines()
    assert lines[-2].startswith("Page: file:") and lines[-2].endswith("/001-login.html")
    # --open reached the engine through the wrapper. The switch clean_env sets keeps a real browser shut.
    assert lines[-1] == "Not opened: pages are set not to open here. Open the link above."


# -- Same output, whatever happens to the page -------------------------------------------------

BROKEN_ENGINES = {
    "syntax-error": "this is not python\n",
    "crash": "raise RuntimeError('boom')\n",
    "exit-code": "import sys\nsys.exit(7)\n",
    "noisy": "import sys\nprint('garbage on stdout')\nsys.stderr.write('garbage on stderr\\n')\n",
}


@pytest.mark.parametrize("broken", sorted(BROKEN_ENGINES))
@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_broken_engine_changes_nothing_the_model_sees(root, variant, broken):
    wrapped_tokens, direct_tokens = split_header(header_command("analyze", variant[0]))
    build(root, variant[0], "ready")
    direct = run_tool(variant, direct_tokens, root)
    build(root, variant[0], "ready")
    (root / ".specify" / "scripts" / "progress" / "engine.py").write_text(BROKEN_ENGINES[broken], encoding="utf-8")
    wrapped = run_tool(variant, wrapped_tokens, root)
    same(direct, wrapped)
    assert direct.returncode == 0


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_missing_engine_changes_nothing_the_model_sees(root, variant):
    wrapped_tokens, direct_tokens = split_header(header_command("analyze", variant[0]))
    build(root, variant[0], "ready")
    direct = run_tool(variant, direct_tokens, root)
    build(root, variant[0], "ready")
    shutil.rmtree(root / ".specify" / "scripts" / "progress")
    wrapped = run_tool(variant, wrapped_tokens, root)
    same(direct, wrapped)


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_page_that_cannot_be_written_changes_nothing_the_model_sees(root, variant):
    wrapped_tokens, direct_tokens = split_header(header_command("analyze", variant[0]))
    build(root, variant[0], "ready")
    direct = run_tool(variant, direct_tokens, root)
    build(root, variant[0], "ready")
    (root / ".specify" / "progress").write_text("a file, not a folder", encoding="utf-8")
    wrapped = run_tool(variant, wrapped_tokens, root)
    same(direct, wrapped)


@pytest.mark.skipif(os.name == "nt" or not _HAS_BASH, reason="builds a PATH out of POSIX tools")
def test_no_python_at_all_changes_nothing_the_model_sees_in_bash(root, tmp_path):
    variant = ("sh", ["bash"])
    wrapped_tokens, direct_tokens = split_header(header_command("analyze", "sh"))
    tools = tmp_path / "tools-without-python"
    tools.mkdir()
    for folder in ("/usr/bin", "/bin"):
        for tool in Path(folder).iterdir():
            name = tool.name
            if name.startswith(("python", "py")) or name == "specify" or os.path.lexists(tools / name):
                continue
            (tools / name).symlink_to(tool)
    env = clean_env()
    env["PATH"] = str(tools)
    build(root, "sh", "ready")
    direct = run_tool(variant, direct_tokens, root, env=env)
    build(root, "sh", "ready")
    wrapped = run_tool(variant, wrapped_tokens, root, env=env)
    same(direct, wrapped)
    assert read_log(root) == []


# -- Arguments and input reach the real script as they were ------------------------------------


def dispatcher_header(command: str, script_type: str) -> list[str]:
    """The header as the event dispatcher leaves it: only the first path is anchored under .specify."""
    tokens = header_command(command, script_type)
    return [tokens[0], *[token.replace(".specify/scripts/", "scripts/") for token in tokens[1:]]]


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_script_named_the_way_the_event_dispatcher_leaves_it_still_runs(root, variant):
    build(root, variant[0], "ready")
    command = dispatcher_header("analyze", variant[0])
    assert command[3].startswith("scripts/")
    direct = run_tool(variant, split_header(header_command("analyze", variant[0]))[1], root)
    wrapped = run_tool(variant, command, root)
    assert wrapped.returncode == 0, wrapped.stderr
    same(direct, wrapped)
    assert [(event["step"], event["status"]) for event in read_log(root)] == [("analyze", "in_progress")]


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_scripts_folder_the_project_has_of_its_own_does_not_win(root, variant):
    build(root, variant[0], "ready")
    command = dispatcher_header("analyze", variant[0])
    theirs = root / command[3]
    theirs.parent.mkdir(parents=True)
    theirs.write_text("this is not a script that runs\n", encoding="utf-8")
    direct = run_tool(variant, split_header(header_command("analyze", variant[0]))[1], root)
    same(direct, run_tool(variant, command, root))
    assert direct.returncode == 0


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_script_that_is_nowhere_fails_and_records_nothing(root, variant):
    build(root, variant[0], "ready")
    command = header_command("analyze", variant[0])
    command[3] = command[3].replace("check-prerequisites", "no-such").replace("check_prerequisites", "no_such")
    done = run_tool(variant, command, root)
    assert done.returncode != 0
    assert read_log(root) == []


def probe_script(root: Path, script_type: str, exit_code: int = 0) -> list[str]:
    """A script that reports exactly what it received. Returns the wrapper's name and its path."""
    folder = root / ".specify" / "scripts"
    if script_type == "sh":
        path = folder / "bash" / "probe.sh"
        path.write_text(
            '#!/usr/bin/env bash\nfor a in "$@"; do printf "[%%s]\\n" "$a"; done\ncat\nexit %d\n' % exit_code,
            encoding="utf-8",
        )
        return [".specify/scripts/bash/run-step.sh", ".specify/scripts/bash/probe.sh"]
    if script_type == "py":
        path = folder / "python" / "probe.py"
        path.write_text(
            "import sys\nfor a in sys.argv[1:]:\n    print('[%s]' % a)\nsys.stdout.write(sys.stdin.read())\n"
            "sys.stdout.flush()\nsys.exit(" + str(exit_code) + ")\n",
            encoding="utf-8",
        )
        return [".specify/scripts/python/run_step.py", ".specify/scripts/python/probe.py"]
    path = folder / "powershell" / "probe.ps1"
    path.write_text(
        "param([switch]$Json, [string]$Template, [Parameter(Position=0)][string]$First)\n"
        'Write-Output "[Json=$Json]"\n'
        'Write-Output "[Template=$Template]"\n'
        'Write-Output "[First=$First]"\n'
        "exit %d\n" % exit_code,
        encoding="utf-8",
    )
    return [".specify/scripts/powershell/run-step.ps1", ".specify/scripts/powershell/probe.ps1"]


@pytest.mark.parametrize(
    "variant", [v for v in VARIANTS if v[0] != "ps"], ids=_variant_id
)
def test_arguments_and_input_arrive_untouched(root, variant):
    build(root, variant[0], "ready")
    wrapper, probe = probe_script(root, variant[0])
    arguments = ["--json", "two words", 'with "quotes"', "$HOME", "*", "", "--harness", "x"]
    result = run_tool(variant, [wrapper, "analyze", "claude", probe, *arguments], root, stdin=b"from stdin\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().replace("\r\n", "\n") == "".join("[%s]\n" % a for a in arguments) + "from stdin\n"


@pytest.mark.parametrize("shell", _SHELLS)
@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (["-Json"], "[Json=True]\n[Template=]\n[First=]\n"),
        (["-Json", "-Template", "plan-template"], "[Json=True]\n[Template=plan-template]\n[First=]\n"),
        (["spec-template", "-Json"], "[Json=True]\n[Template=]\n[First=spec-template]\n"),
        ([], "[Json=False]\n[Template=]\n[First=]\n"),
    ],
)
@pytest.mark.parametrize("mode", ["-File", "-Command"])
def test_powershell_switches_arrive_as_switches(root, shell, mode, arguments, expected):
    build(root, "ps", "ready")
    wrapper, probe = probe_script(root, "ps")
    tokens = [wrapper, "analyze", "claude", probe, *arguments]
    command = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", mode] + (tokens if mode == "-File" else [" ".join(tokens)])
    result = subprocess.run(command, cwd=root, capture_output=True, env=clean_env(), check=False, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().replace("\r\n", "\n") == expected


@pytest.mark.parametrize("exit_code", [0, 1, 3, 77])
@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_the_exit_code_is_the_real_scripts(root, variant, exit_code):
    build(root, variant[0], "ready")
    wrapper, probe = probe_script(root, variant[0], exit_code)
    assert run_tool(variant, [wrapper, "analyze", "claude", probe], root).returncode == exit_code


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_script_that_fails_records_nothing(root, variant):
    build(root, variant[0], "ready")
    wrapper, probe = probe_script(root, variant[0], 3)
    run_tool(variant, [wrapper, "analyze", "claude", probe], root)
    assert read_log(root) == []
    assert not (root / ".specify" / "progress").exists()


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_too_few_arguments_are_refused(root, variant):
    build(root, variant[0], "ready")
    wrapper, _ = probe_script(root, variant[0])
    result = run_tool(variant, [wrapper, "analyze"], root)
    assert result.returncode == 2
    assert b"usage" in result.stderr
    assert result.stdout == b""


# -- What gets recorded ------------------------------------------------------------------------


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_step_that_starts_is_recorded_and_the_page_is_drawn(root, variant):
    build(root, variant[0], "ready")
    run_tool(variant, header_command("analyze", variant[0]), root)
    events = read_log(root)
    assert [(event["step"], event["status"]) for event in events] == [("analyze", "in_progress")]
    # The raw template still says __AGENT__ here, and that is nobody's name.
    assert "actor" not in events[0]
    assert (root / ".specify" / "progress" / "001-login.html").is_file()


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_the_harness_named_on_the_command_line_is_the_one_recorded(root, variant):
    build(root, variant[0], "ready")
    tokens = header_command("analyze", variant[0])
    tokens[2] = "codex"
    run_tool(variant, tokens, root)
    assert read_log(root)[0]["actor"] == {"harness": "codex", "source": "configured"}


@pytest.mark.parametrize("command", ["constitution", "specify"])
@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_steps_without_a_spec_of_their_own_write_nothing_to_the_log(root, variant, command):
    build(root, variant[0], "ready")
    run_tool(variant, header_command(command, variant[0]), root)
    assert read_log(root) == []


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_it_also_works_from_a_project_path_with_spaces(tmp_path, variant):
    root = tmp_path / "a folder with spaces"
    build(root, variant[0], "ready")
    result = run_tool(variant, header_command("analyze", variant[0]), root)
    assert result.returncode == 0, result.stderr
    assert read_log(root)[0]["step"] == "analyze"


# -- The progress command itself ---------------------------------------------------------------


def progress_tokens(script_type: str) -> list[str]:
    return {
        "sh": [".specify/scripts/bash/progress.sh"],
        "py": [".specify/scripts/python/progress.py"],
        "ps": [".specify/scripts/powershell/progress.ps1"],
    }[script_type]


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_show_reports_and_links_to_the_page(root, variant):
    build(root, variant[0], "ready")
    result = run_tool(variant, [*progress_tokens(variant[0]), "--harness", "claude", "show"], root)
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "Tasks: 1 of 2 done, 1 pending" in text
    assert "/.specify/progress/001-login.html" in text.replace("\\", "/")


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_note_with_quotes_and_spaces_is_recorded_exactly(root, variant):
    build(root, variant[0], "ready")
    note = 'Found "two" issues in C:\\temp\\ and $HOME'
    result = run_tool(
        variant,
        [*progress_tokens(variant[0]), "--harness", "claude", "step", "analyze", "done", "--note", note],
        root,
    )
    assert result.returncode == 0, result.stderr
    assert read_log(root)[0]["note"] == note


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_it_works_from_a_folder_inside_the_project(root, variant):
    build(root, variant[0], "ready")
    inside = root / "src" / "deep"
    inside.mkdir(parents=True)
    absolute = str(root / progress_tokens(variant[0])[0])
    result = run_tool(variant, [absolute, "--harness", "claude", "step", "plan", "done"], inside)
    assert result.returncode == 0, result.stderr
    assert read_log(root)[0]["step"] == "plan"
    assert not (inside / ".specify").exists()


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_missing_engine_warns_and_exits_zero(root, variant):
    build(root, variant[0], "ready")
    shutil.rmtree(root / ".specify" / "scripts" / "progress")
    result = run_tool(variant, [*progress_tokens(variant[0]), "show"], root)
    assert result.returncode == 0
    assert b"was not updated" in result.stderr
    assert result.stdout == b""


@pytest.mark.skipif(os.name == "nt" or not _HAS_BASH, reason="builds a PATH out of POSIX tools")
def test_no_python_and_no_specify_warns_and_exits_zero(root, tmp_path):
    build(root, "sh", "ready")
    env = clean_env()
    env["PATH"] = str(tmp_path / "empty")
    result = subprocess.run(
        ["/bin/bash", ".specify/scripts/bash/progress.sh", "show"],
        cwd=root, capture_output=True, env=env, check=False, timeout=60,
    )
    assert result.returncode == 0
    assert b"no Python 3.9 or newer" in result.stderr


@pytest.mark.skipif(os.name == "nt" or not _HAS_BASH, reason="builds a PATH out of POSIX tools")
def test_without_python_it_falls_back_to_the_specify_command(root, tmp_path):
    build(root, "sh", "ready")
    tools = tmp_path / "tools"
    tools.mkdir()
    fake = tools / "specify"
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding="utf-8")
    fake.chmod(0o755)
    env = clean_env()
    env["PATH"] = "%s" % tools
    result = subprocess.run(
        ["/bin/bash", ".specify/scripts/bash/progress.sh", "show"],
        cwd=root, capture_output=True, env=env, check=False, timeout=60,
    )
    lines = result.stdout.decode().splitlines()
    assert lines[:4] == ["progress", "engine", "--root", os.path.realpath(root)]
    assert lines[-1] == "show"


@pytest.mark.skipif(os.name == "nt" or not _HAS_BASH, reason="builds a PATH out of POSIX tools")
def test_a_python_too_old_is_passed_over(root, tmp_path):
    build(root, "sh", "ready")
    tools = tmp_path / "tools"
    tools.mkdir()
    old = tools / "python3"
    old.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    old.chmod(0o755)
    good = tools / "python"
    good.write_text('#!/bin/sh\nexec "%s" "$@"\n' % sys.executable, encoding="utf-8")
    good.chmod(0o755)
    env = clean_env()
    env["PATH"] = str(tools)
    result = subprocess.run(
        ["/bin/bash", ".specify/scripts/bash/progress.sh", "show"],
        cwd=root, capture_output=True, env=env, check=False, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert b"Tasks: 1 of 2 done" in result.stdout


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_the_engine_ignores_python_modules_planted_next_to_it(root, variant):
    build(root, variant[0], "ready")
    planted = root / ".specify" / "scripts" / "progress" / "json.py"
    planted.write_text("raise SystemExit('planted module ran')\n", encoding="utf-8")
    script = {
        "sh": ".specify/scripts/bash/progress.sh",
        "py": ".specify/scripts/python/progress.py",
        "ps": ".specify/scripts/powershell/progress.ps1",
    }[variant[0]]
    result = run_tool(variant, [script, "show"], root)
    assert result.returncode == 0, result.stderr
    assert b"Tasks: 1 of 2 done" in result.stdout


OLD_PYTHON = """\
import sys
import types
if sys.argv[1:2] == ["-c"]:
    real_exit = sys.exit
    sys.modules["sys"] = types.SimpleNamespace(version_info=(3, 8, 0), exit=real_exit)
    exec(sys.argv[2])
print("the old python ran the engine")
"""


@pytest.mark.skipif(os.name == "nt" or not _HAS_BASH, reason="builds a PATH out of POSIX tools")
def test_a_python_too_old_for_the_engine_is_passed_over_in_bash(root, tmp_path):
    build(root, "sh", "ready")
    folder = tmp_path / "old-python"
    folder.mkdir()
    (folder / "fake.py").write_text(OLD_PYTHON, encoding="utf-8")
    python3 = folder / "python3"
    python3.write_text('#!/bin/sh\nexec "%s" -I "%s" "$@"\n' % (sys.executable, folder / "fake.py"), encoding="utf-8")
    python3.chmod(0o755)
    env = clean_env()
    env["PATH"] = str(folder) + os.pathsep + env["PATH"]
    result = run_tool(("sh", ["bash"]), [".specify/scripts/bash/progress.sh", "show"], root, env=env)
    assert result.returncode == 0, result.stderr
    assert b"the old python ran" not in result.stdout


# -- The calls a model makes during /speckit.implement -----------------------------------------


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_done_marks_the_box_and_every_word_arrives_as_written(root, variant):
    build(root, variant[0], "ready")
    note = 'Found "two" issues in C:\\temp\\ and $HOME'
    result = run_tool(
        variant,
        [
            *progress_tokens(variant[0]), "--harness", "claude", "done", "T002",
            "--note", note, "--files", "src/a b.py,src/c.py", "--agent", "backend 1",
        ],
        root,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().strip() == "T002 done. 2 of 2 tasks done."
    assert "- [X] T002" in (root / "specs" / "001-login" / "tasks.md").read_text(encoding="utf-8")
    event = read_log(root)[0]
    assert event["note"] == note
    assert event["files"] == ["src/a b.py", "src/c.py"]
    assert event["actor"] == {"harness": "claude", "agent": "backend 1", "source": "declared"}


@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_task_call_that_fails_says_so_through_the_wrapper(root, variant):
    build(root, variant[0], "ready")
    before = (root / "specs" / "001-login" / "tasks.md").read_bytes()
    result = run_tool(variant, [*progress_tokens(variant[0]), "--harness", "claude", "done", "T099"], root)
    assert result.returncode == 1
    assert "T001 T002" in result.stderr.decode()
    assert (root / "specs" / "001-login" / "tasks.md").read_bytes() == before
    assert read_log(root) == []


@pytest.mark.parametrize("arguments", [["--harness", "claude", "done", "T002"], ["start", "T002"], ["note", "T002", "x"]])
@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_a_task_call_without_the_engine_fails_so_the_box_gets_marked_by_hand(root, variant, arguments):
    build(root, variant[0], "ready")
    shutil.rmtree(root / ".specify" / "scripts" / "progress")
    result = run_tool(variant, [*progress_tokens(variant[0]), *arguments], root)
    assert result.returncode == 1
    assert "the page was not updated" in result.stderr.decode()


@pytest.mark.parametrize("arguments", [["--harness", "claude", "show"], ["step", "plan", "note", "--note", "done"]])
@pytest.mark.parametrize("variant", VARIANTS, ids=_variant_id)
def test_any_other_call_without_the_engine_still_exits_zero(root, variant, arguments):
    build(root, variant[0], "ready")
    shutil.rmtree(root / ".specify" / "scripts" / "progress")
    assert run_tool(variant, [*progress_tokens(variant[0]), *arguments], root).returncode == 0


@pytest.mark.skipif(os.name == "nt" or not _HAS_BASH, reason="builds a PATH out of POSIX tools")
@pytest.mark.parametrize(
    ("arguments", "expected"),
    [(["--harness", "claude", "done", "T002"], 1), (["block", "T002", "--reason", "x"], 1), (["--harness", "claude", "show"], 0)],
)
def test_no_python_at_all_fails_a_task_call_in_bash_and_only_a_task_call(root, tmp_path, arguments, expected):
    tools = tmp_path / "tools-without-python"
    tools.mkdir()
    for folder in ("/usr/bin", "/bin"):
        for tool in Path(folder).iterdir():
            name = tool.name
            if name.startswith(("python", "py")) or name == "specify" or os.path.lexists(tools / name):
                continue
            (tools / name).symlink_to(tool)
    env = clean_env()
    env["PATH"] = str(tools)
    build(root, "sh", "ready")
    result = run_tool(("sh", ["bash"]), [*progress_tokens("sh"), *arguments], root, env=env)
    assert result.returncode == expected
    assert b"no Python" in result.stderr


@pytest.mark.parametrize("shell", _SHELLS)
@pytest.mark.parametrize("mode", ["-File", "-Command"])
def test_powershell_keeps_a_comma_list_of_files_in_one_piece(root, shell, mode):
    """In -Command, PowerShell has already turned a,b into a list when the script receives it."""
    build(root, "ps", "ready")
    tokens = [progress_tokens("ps")[0], "--harness", "claude", "done", "T002", "--files", "src/a.py,src/b.py"]
    command = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", mode] + (tokens if mode == "-File" else [" ".join(tokens)])
    result = subprocess.run(command, cwd=root, capture_output=True, env=clean_env(), check=False, timeout=120)
    assert result.returncode == 0, result.stderr
    assert read_log(root)[0]["files"] == ["src/a.py", "src/b.py"]
