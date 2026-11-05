"""What lets a session find the catalog without being told: the agent block, scaffold, bootstrap and locate."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import textwrap

import pytest

from .conftest import (
    hard_with,
    CAT,
    EXT_DIR,
    IMPL,
    INDEX,
    LOCKOUT_5,
    ROOT,
    SCRIPT,
    SESSION_CODE,
    SESSION_TESTS,
    SPEC,
    EXPIRY_15,
    EXPIRY_30,
    TEST_FREE,
    Repo,
    change_expiry,
    delta_block,
    deliver,
    impl,
    modified,
)
from .test_acceptance_concurrency import Holder

START = "<!-- SPECKIT CAPABILITIES START -->"
END = "<!-- SPECKIT CAPABILITIES END -->"
INIT_OPTIONS = ".specify/init-options.json"
AGENT_CONFIG = ".specify/extensions/agent-context/agent-context-config.yml"
BLOCK = (EXT_DIR / "templates" / "capability-agent-rule.md").read_text(encoding="utf-8").strip("\n")
BOOTSTRAP_PROMPT = (EXT_DIR / "commands" / "speckit.capabilities.bootstrap.md").read_text(encoding="utf-8")
RECORD = CAT + "/_changes/20261104-bootstrap-login"
RATE = "Se admiten 10 intentos por minuto."


@pytest.fixture
def bare(tmp_path) -> Repo:
    """A project with code and tests and no catalog."""
    repo = Repo(tmp_path / "bare")
    repo.path.mkdir()
    repo.git("init", "-q", "-b", "main", ".")
    repo.write("src/auth/session.py", SESSION_CODE.format(expiry=30, lockout=5))
    repo.write("tests/auth/test_session.py", SESSION_TESTS.format(expiry=30, lockout=5))
    repo.write("pytest.ini", "[pytest]\npythonpath = src\n")
    repo.write(".gitignore", "junit*.xml\n__pycache__/\n")
    repo.commit("code")
    return repo


def seal(repo, name="002-x"):
    """Review a new feature, which is when the block is written."""
    change = repo.feature(name, modified())
    return change, repo.review(change)


def options(repo, **values):
    repo.write(INIT_OPTIONS, json.dumps(values))


def forget_agents_md(repo):
    (repo.path / "AGENTS.md").unlink()


# ---------------------------------------------------------------- which file


@pytest.mark.parametrize("given, expected", [
    ({"integration": "claude"}, "CLAUDE.md"),
    ({"ai": "gemini"}, "GEMINI.md"),
    ({"integration": "copilot", "ai": "gemini"}, ".github/copilot-instructions.md"),
    ({"integration": "codex"}, "AGENTS.md"),
    ({"integration": "made-up"}, "AGENTS.md"),
    ({"integration": ["claude"]}, "AGENTS.md"),
    ({}, "AGENTS.md"),
])
def test_the_block_goes_to_the_file_of_the_integration(repo, given, expected):
    forget_agents_md(repo)
    options(repo, **given)
    out = seal(repo)[1]
    assert expected in out["setup"]
    assert START in repo.read(expected) and END in repo.read(expected)
    if expected != "AGENTS.md":
        assert not (repo.path / "AGENTS.md").exists()


@pytest.mark.parametrize("content", ["not json", "[]", "null", '"claude"'])
def test_unreadable_init_options_fall_back_to_agents_md(repo, content):
    forget_agents_md(repo)
    repo.write(INIT_OPTIONS, content)
    seal(repo)
    assert START in repo.read("AGENTS.md")


@pytest.mark.parametrize("config, expected", [
    ('context_file: "docs/AI.md"\n', ["docs/AI.md"]),
    ("context_file: docs/AI.md  # ours\n", ["docs/AI.md"]),
    ('context_files:\n  - "a/ONE.md"\n  - b/TWO.md\ncontext_file: "docs/AI.md"\n', ["a/ONE.md", "b/TWO.md"]),
    ('context_file: "docs/AI.md"\ncontext_files: ["a/ONE.md", b/TWO.md]\n', ["a/ONE.md", "b/TWO.md"]),
    ('context_files: []\ncontext_file: "docs/AI.md"\n', ["docs/AI.md"]),
    ('context_files:\n  - ../outside.md\ncontext_file: "docs/AI.md"\n', ["docs/AI.md"]),
])
def test_the_agent_context_configuration_wins_over_the_integration(repo, config, expected):
    forget_agents_md(repo)
    options(repo, integration="claude")
    repo.write(AGENT_CONFIG, config)
    out = seal(repo)[1]
    assert out["setup"] == expected
    for rel in expected:
        assert START in repo.read(rel)
    assert not (repo.path / "CLAUDE.md").exists()


@pytest.mark.parametrize("value", ["../outside.md", "/tmp/abs.md", "C:/abs.md", "a\\b.md", "a/../../b.md"])
def test_an_unsafe_configured_path_is_ignored(repo, value):
    forget_agents_md(repo)
    options(repo, integration="claude")
    repo.write(AGENT_CONFIG, "context_file: %s\n" % value)
    assert seal(repo)[1]["setup"] == ["CLAUDE.md"]


def test_the_commented_examples_of_the_real_config_do_not_count_and_its_values_do(repo):
    real = (ROOT / "extensions" / "agent-context" / "agent-context-config.yml").read_text(encoding="utf-8")
    assert "context_files" in real
    forget_agents_md(repo)
    options(repo, integration="claude")
    repo.write(AGENT_CONFIG, real)
    change, out = seal(repo)
    assert out["setup"] == ["CLAUDE.md"]

    assert 'context_file: ""' in real
    repo.write(AGENT_CONFIG, real.replace('context_file: ""', 'context_file: "docs/AI.md"'))
    rc, out = repo.cap("review", "--change", change, "--accept")
    assert rc == 0 and out["setup"] == ["docs/AI.md"]


def test_the_copy_of_the_map_matches_the_agent_context_extension():
    spec = importlib.util.spec_from_file_location("capabilities_map", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    agents = json.loads((ROOT / "extensions" / "agent-context" / "agent-context-defaults.json").read_text(encoding="utf-8"))["agents"]
    assert {key: module.AGENT_FILES.get(key, module.DEFAULT_AGENT_FILE) for key in agents} == agents
    assert set(module.AGENT_FILES) <= set(agents)
    assert module.DEFAULT_AGENT_FILE not in module.AGENT_FILES.values()


# ---------------------------------------------------------------- what it does to the file


def test_writing_the_block_twice_changes_nothing(repo):
    forget_agents_md(repo)
    change, out = seal(repo)
    assert out["setup"] == ["AGENTS.md"]
    before = repo.tree()
    rc, out = repo.cap("review", "--change", change, "--accept")
    assert rc == 0 and out["setup"] == []
    assert repo.tree() == before


def test_content_around_the_block_stays_byte_for_byte_and_an_old_block_is_refreshed(repo):
    head = "# Mine\n\n<!-- SPECKIT START -->\nagent-context's block\n<!-- SPECKIT END -->\n\n"
    tail = "\n\nMy closing notes without a final newline"
    repo.write("AGENTS.md", head + START + "\nold text\n" + END + tail)
    out = seal(repo)[1]
    assert out["setup"] == ["AGENTS.md"]
    assert repo.read("AGENTS.md") == head + BLOCK + tail


@pytest.mark.parametrize("existing, expected", [
    ("# Mine\n", "# Mine\n\n" + BLOCK + "\n"),
    ("# Mine", "# Mine\n\n" + BLOCK + "\n"),
    ("", BLOCK + "\n"),
])
def test_a_file_without_markers_keeps_its_content_and_gets_the_block_after_it(repo, existing, expected):
    repo.write("AGENTS.md", existing)
    seal(repo)
    assert repo.read("AGENTS.md") == expected


@pytest.mark.parametrize("content", [
    "x\n" + START + "\nno end\n",
    "x\n" + END + "\nno start\n",
    END + "\nreversed\n" + START + "\n",
    START + "\na\n" + END + "\n" + START + "\nb\n" + END + "\n",
])
def test_unbalanced_markers_leave_the_file_alone_and_are_reported(repo, content):
    repo.write("AGENTS.md", content)
    out = seal(repo)[1]
    assert out["setup"] == ["skipped AGENTS.md: unbalanced markers"]
    assert repo.read("AGENTS.md") == content


def test_crlf_files_keep_their_line_endings(repo):
    repo.write("AGENTS.md", "")
    (repo.path / "AGENTS.md").write_bytes(b"# Mine\r\nmore\r\n")
    seal(repo)
    data = (repo.path / "AGENTS.md").read_bytes()
    assert data.startswith(b"# Mine\r\nmore\r\n\r\n" + START.encode())
    assert b"\n" not in data.replace(b"\r\n", b"")


def test_a_refreshed_block_in_a_crlf_file_is_stable(repo):
    (repo.path / "AGENTS.md").write_bytes(b"# Mine\r\n")
    change = seal(repo)[0]
    first = (repo.path / "AGENTS.md").read_bytes()
    rc, out = repo.cap("review", "--change", change, "--accept")
    assert rc == 0 and out["setup"] == []
    assert (repo.path / "AGENTS.md").read_bytes() == first


def test_a_symlink_inside_the_repository_stays_a_symlink(repo):
    forget_agents_md(repo)
    repo.write("docs/agents.md", "# Mine\n")
    os.symlink("docs/agents.md", str(repo.path / "AGENTS.md"))
    out = seal(repo)[1]
    assert out["setup"] == ["AGENTS.md"]
    assert (repo.path / "AGENTS.md").is_symlink()
    assert repo.read("docs/agents.md").startswith("# Mine\n\n" + START)


def test_a_symlink_out_of_the_repository_is_not_followed(repo, tmp_path):
    forget_agents_md(repo)
    outside = tmp_path / "outside.md"
    outside.write_text("private\n", encoding="utf-8")
    os.symlink(str(outside), str(repo.path / "AGENTS.md"))
    assert seal(repo)[1]["setup"] == ["skipped AGENTS.md: it points outside the repository"]
    assert outside.read_text(encoding="utf-8") == "private\n"


def test_a_dangling_symlink_out_of_the_repository_creates_nothing(repo, tmp_path):
    forget_agents_md(repo)
    outside = tmp_path / "not-yet.md"
    os.symlink(str(outside), str(repo.path / "AGENTS.md"))
    assert seal(repo)[1]["setup"] == ["skipped AGENTS.md: it points outside the repository"]
    assert not outside.exists()


def test_a_file_that_is_not_utf8_is_left_alone(repo):
    (repo.path / "AGENTS.md").write_bytes(b"\xff\xfe binary")
    assert seal(repo)[1]["setup"] == ["skipped AGENTS.md: it cannot be read as UTF-8"]
    assert (repo.path / "AGENTS.md").read_bytes() == b"\xff\xfe binary"


def test_a_directory_in_the_way_does_not_stop_the_review(repo):
    forget_agents_md(repo)
    (repo.path / "AGENTS.md").mkdir()
    change, out = seal(repo)
    assert out["setup"] == ["skipped AGENTS.md: it cannot be read as UTF-8"]
    assert (repo.path / change / "capability-delta.lock.json").is_file()


def test_a_file_in_the_way_of_the_parent_directory_does_not_stop_the_review(repo):
    forget_agents_md(repo)
    options(repo, integration="copilot")
    repo.write(".github", "a file\n")
    out = seal(repo)[1]
    assert len(out["setup"]) == 1 and out["setup"][0].startswith("skipped .github/copilot-instructions.md")
    assert repo.read(".github") == "a file\n"


def test_mdc_files_get_the_frontmatter_their_agent_needs_and_keep_one_they_have(repo):
    forget_agents_md(repo)
    options(repo, integration="cursor-agent")
    change = seal(repo)[0]
    rel = ".cursor/rules/specify-rules.mdc"
    assert repo.read(rel) == "---\nalwaysApply: true\n---\n\n" + BLOCK + "\n"
    rc, out = repo.cap("review", "--change", change, "--accept")
    assert rc == 0 and out["setup"] == []

    custom = "---\nalwaysApply: true\ndescription: mine\n---\n\nbody\n"
    repo.write(rel, custom)
    repo.cap("review", "--change", change, "--accept")
    assert repo.read(rel) == custom + "\n" + BLOCK + "\n"


# ---------------------------------------------------------------- when


def test_a_review_that_fails_does_not_write_the_block(repo):
    forget_agents_md(repo)
    change = repo.feature("002-x", "### MODIFIED R-session-expiry\n- Capability: login\n- From: nothing like it\n")
    rc, _ = repo.cap("review", "--change", change)
    assert rc == 2
    assert not (repo.path / "AGENTS.md").exists()


def test_a_review_with_a_conflict_does_not_write_the_block(repo):
    forget_agents_md(repo)
    change = repo.feature("002-x", modified(frm="Otro texto."))
    rc, out = repo.cap("review", "--change", change)
    assert rc == 3 and out["status"] == "conflict"
    assert not (repo.path / "AGENTS.md").exists()


def test_a_blocked_prepare_does_not_write_the_block_and_a_ready_one_does(repo):
    change = repo.feature("002-x", modified(), tasks="- [ ] T001 Pending\n")
    repo.review(change)
    forget_agents_md(repo)
    rc, out = repo.cap("prepare", "--change", change)
    assert rc == 3 and out["status"] == "blocked"
    assert not (repo.path / "AGENTS.md").exists()

    repo.write(change + "/tasks.md", "- [x] T001 Done\n")
    out = repo.prepare(change)
    assert out["setup"] == ["AGENTS.md"]
    assert START in repo.read("AGENTS.md")


def test_the_block_is_not_listed_as_foreign_but_other_files_are(repo):
    options(repo, integration="claude")
    repo.commit("options")
    change = seal(repo)[0]
    assert START in repo.read("CLAUDE.md")
    repo.write("src/unrelated.py", "x = 1\n")
    out = repo.prepare(change)
    assert out["foreign"] == ["src/unrelated.py"]


def test_the_block_does_not_get_in_the_way_of_the_ci_check(repo):
    forget_agents_md(repo)
    repo.commit("no agent file on main")
    change = change_expiry(repo)
    assert START in repo.read("AGENTS.md")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["states"][change] == "ready"


# ---------------------------------------------------------------- scaffold


def test_scaffold_lists_a_planned_capability_without_creating_it(bare):
    rc, out = bare.cap("scaffold", "--capability", "payments", "--covers", "Cobros  y\nreembolsos")
    assert (rc, out["status"], out["capability"]) == (0, "planned", "payments")
    assert set(out["setup"]) == {".gitignore", ".gitattributes", "AGENTS.md"}
    assert "| payments | Cobros y reembolsos | planned | none |\n" in bare.read(INDEX)
    assert not (bare.path / CAT / "payments").exists()
    rc, out = bare.cap("status")
    assert out["planned"] == {"payments": "Cobros y reembolsos"}
    assert out["capabilities"] == {}


def test_scaffold_twice_changes_nothing(bare):
    bare.cap("scaffold", "--capability", "payments", "--covers", "Cobros")
    before = bare.tree()
    rc, out = bare.cap("scaffold", "--capability", "payments", "--covers", "Otra cosa")
    assert (rc, out["status"]) == (0, "unchanged")
    assert bare.tree() == before


def test_scaffold_does_not_touch_a_consolidated_capability(repo):
    before = repo.tree()
    rc, out = repo.cap("scaffold", "--capability", "login", "--covers", "Otra cosa")
    assert (rc, out["status"]) == (0, "unchanged")
    assert repo.tree() == before


def test_scaffold_does_not_touch_a_capability_that_has_a_directory_and_no_row(repo):
    repo.write(CAT + "/orphan/spec.md", "# orphan\n")
    before = repo.tree()
    rc, out = repo.cap("scaffold", "--capability", "orphan", "--covers", "x")
    assert (rc, out["status"]) == (0, "unchanged")
    assert repo.tree() == before


@pytest.mark.parametrize("args", [
    (),
    ("--capability", "payments"),
    ("--capability", "payments", "--covers", "  \n "),
    ("--capability", "payments", "--covers", "a | b"),
    ("--capability", "Payments", "--covers", "x"),
    ("--capability", "_changes", "--covers", "x"),
    ("--capability", "../up", "--covers", "x"),
    ("--covers", "x"),
])
def test_scaffold_rejects_bad_input_and_writes_nothing(bare, args):
    before = bare.tree()
    rc, out = bare.cap("scaffold", *args)
    assert (rc, out["status"]) == (2, "invalid")
    assert bare.tree() == before


def test_scaffold_waits_for_an_interrupted_fold(bare):
    bare.write(".specify/capabilities/journal", "{}")
    rc, out = bare.cap("scaffold", "--capability", "payments", "--covers", "x")
    assert (rc, out["status"]) == (4, "recover-needed")
    assert not (bare.path / INDEX).exists()


def test_scaffold_answers_busy_while_another_process_publishes(bare):
    with Holder(bare):
        rc, out = bare.cap("scaffold", "--capability", "payments", "--covers", "x")
    assert (rc, out["status"]) == (5, "busy")
    assert not (bare.path / INDEX).exists()


def test_a_planned_row_passes_the_check_and_context_sees_it(repo):
    repo.checkout("-b", "plan-it")
    rc, _ = repo.cap("scaffold", "--capability", "payments", "--covers", "Cobros")
    assert rc == 0
    repo.commit("planned")
    rc, out = repo.ci()
    assert rc == 0, out
    assert out["hard"] == []
    rc, out = repo.cap("status")
    assert out["planned"] == {"payments": "Cobros"}
    assert list(out["capabilities"]) == ["login"]


# ---------------------------------------------------------------- bootstrap, with the formats the prompt teaches


def prompt_blocks():
    found = re.findall(r"^ *```markdown\n(.*?)^ *```$", BOOTSTRAP_PROMPT, re.S | re.M)
    assert len(found) == 3
    return [textwrap.dedent(item) for item in found]


def fill(text, **values):
    for key, value in values.items():
        text = text.replace("<%s>" % key.replace("_", " "), value)
    assert "<capability-delta" not in text.replace("<!-- capability-delta", "")
    return text


def bootstrap_record(rule="R-session-expiry", text=EXPIRY_30, covers="Autenticación y sesión"):
    record = fill(prompt_blocks()[0], capability="login", the_same_line=covers, the_rule=text)
    return record.replace("R-<name>", rule)


def rule_block(rule, state, code, tests, observed="Lo observado, con su valor."):
    body = prompt_blocks()[1].replace("R-<name>", rule).replace("conforming | unverified", state)
    body = body.replace("<what the code does, with the value you read>", observed)
    body = body.replace("`<file>::<symbol>`", code)
    return body.replace("`<file>::<test>`", tests)


def run_bootstrap(repo, record_text, blocks):
    """The steps of the prompt, in order."""
    repo.write(RECORD + "/capability-delta.md", record_text)
    repo.review(RECORD)
    prepared = repo.prepare(RECORD, "--no-tasks")
    assert prepared["capabilities"] == ["login"]
    staged = repo.read(prepared["staging"] + "/login/implementation.md")
    repo.draft(prepared, staged.replace("## Rule Status\n", "## Rule Status\n\n" + blocks + "\n", 1))
    rc, out = repo.cap("apply", "--change", RECORD, "--staged", prepared["staging"], "--no-tasks")
    assert rc == 0 and out["status"] == "published", out


def test_bootstrap_from_nothing_to_ready_with_the_formats_of_the_prompt(bare):
    bare.git("checkout", "-q", "-b", "bootstrap")
    rc, out = bare.cap("scaffold", "--capability", "login", "--covers", "Autenticación y sesión")
    assert (rc, out["status"]) == (0, "planned")
    run_bootstrap(bare, bootstrap_record(), rule_block("R-session-expiry", "conforming", "`src/auth/session.py::SessionManager`", "`tests/auth/test_session.py::test_expiry`"))

    assert "- **R-session-expiry** [inferred]: %s (%s)" % (EXPIRY_30, RECORD) in bare.read(SPEC)
    index = bare.read(INDEX)
    assert "| [login](login/spec.md) | Autenticación y sesión | consolidated | `src/auth/session.py::SessionManager` |" in index
    assert "planned" not in index
    rc, out = bare.cap("check", "--mode", "dev", "--change", RECORD)
    assert rc == 0 and out["states"][RECORD] == "prepared", out

    bare.commit("bootstrap")
    rc, out = bare.ci()
    assert rc == 0, out
    assert out["states"][RECORD] == "ready"
    rc, out = bare.cap("status")
    assert out["capabilities"]["login"]["inferred"] == ["R-session-expiry"]
    assert out["planned"] == {}


def test_an_unverified_inferred_rule_with_no_tests_is_a_valid_outcome(bare):
    bare.git("checkout", "-q", "-b", "bootstrap")
    run_bootstrap(bare, bootstrap_record(), rule_block("R-session-expiry", "unverified", "`src/auth/session.py::SessionManager`", "none"))
    bare.commit("bootstrap")
    rc, out = bare.ci()
    assert rc == 0, out
    rc, out = bare.cap("status")
    assert out["capabilities"]["login"]["not_conforming"] == ["R-session-expiry"]


def test_a_planned_capability_still_has_to_be_declared_by_its_record(bare):
    bare.git("checkout", "-q", "-b", "bootstrap")
    bare.cap("scaffold", "--capability", "login", "--covers", "Del mapa aprobado")
    record = re.sub(r"### NEW-CAPABILITY login\n- Covers: [^\n]*\n\n", "", bootstrap_record())
    assert "NEW-CAPABILITY" not in record
    bare.write(RECORD + "/capability-delta.md", record)
    rc, out = bare.cap("review", "--change", RECORD)
    assert rc == 3 and "declare NEW-CAPABILITY" in out["conflicts"][0]


def test_consolidating_leaves_one_row_with_the_text_of_the_record(bare):
    bare.git("checkout", "-q", "-b", "bootstrap")
    bare.cap("scaffold", "--capability", "login", "--covers", "Del mapa aprobado")
    bare.cap("scaffold", "--capability", "payments", "--covers", "Cobros")
    run_bootstrap(bare, bootstrap_record(covers="Del registro"), rule_block("R-session-expiry", "unverified", "`src/auth/session.py::SessionManager`", "none"))
    index = bare.read(INDEX)
    assert "| [login](login/spec.md) | Del registro | consolidated |" in index
    assert "Del mapa aprobado" not in index
    assert "| payments | Cobros | planned | none |" in index
    rc, out = bare.cap("status")
    assert list(out["capabilities"]) == ["login"] and out["planned"] == {"payments": "Cobros"}


def test_validating_with_the_format_of_the_prompt_removes_the_mark_and_sets_the_origin(bare):
    bare.git("checkout", "-q", "-b", "bootstrap")
    run_bootstrap(bare, bootstrap_record(), rule_block("R-session-expiry", "unverified", "`src/auth/session.py::SessionManager`", "none"))
    bare.commit("bootstrap")
    deliver(bare, "bootstrap", "validate")

    rc, out = bare.cap("locate", "--capability", "login")
    literal = out["rules"][0]["text"]
    validated = fill(prompt_blocks()[2], capability="login", literal_text=literal).replace("R-<name>", "R-session-expiry")
    record = CAT + "/_changes/20261105-validate-login"
    bare.write(record + "/capability-delta.md", "# Validate\n\n" + delta_block(validated))
    bare.review(record)
    prepared = bare.prepare(record, "--no-tasks")
    rc, out = bare.cap("apply", "--change", record, "--staged", prepared["staging"], "--no-tasks")
    assert rc == 0 and out["status"] == "published", out
    assert "- **R-session-expiry**: %s (%s)" % (EXPIRY_30, record) in bare.read(SPEC)
    bare.commit("validated")
    rc, out = bare.ci()
    assert rc == 0, out
    assert out["states"][record] == "ready"


def test_a_validation_whose_text_differs_is_rejected(bare):
    bare.git("checkout", "-q", "-b", "bootstrap")
    run_bootstrap(bare, bootstrap_record(), rule_block("R-session-expiry", "unverified", "`src/auth/session.py::SessionManager`", "none"))
    bare.commit("bootstrap")
    record = CAT + "/_changes/20261105-validate-login"
    bare.write(record + "/capability-delta.md", "# Validate\n\n" + delta_block("### VALIDATED R-session-expiry\n- Capability: login\n- From: %s\n- To: %s\n- Links: none\n" % (EXPIRY_30, EXPIRY_15)))
    rc, out = bare.cap("review", "--change", record)
    assert rc == 2 and out["status"] == "invalid"
    assert "[inferred]" in bare.read(SPEC)


# ---------------------------------------------------------------- a limit, stated


def test_a_value_the_mapped_tests_do_not_pin_changes_with_only_a_notice(repo):
    """Not a virtue. The README states it, and this fails if the behaviour moves without the README moving too."""
    change = repo.feature("002-x", modified())
    repo.set_code(expiry=15)
    repo.review(change)
    repo.folded(change, impl(expiry_tests=TEST_FREE))
    repo.commit("mapped to a test that does not pin the value")
    deliver(repo, "main", "later")

    repo.set_code(expiry=99, tests=False)
    repo.commit("back to another value, with no delta")
    rc, out = repo.ci()
    assert rc == 0 and out["hard"] == [], out
    assert "R-session-expiry: anchored code changed without a delta" in out["notes"]


# ---------------------------------------------------------------- locate


def rule_named(out, rule_id):
    return next(rule for rule in out["rules"] if rule["id"] == rule_id)


def test_locate_answers_with_the_rule_its_origin_its_code_and_its_tests(repo):
    change = change_expiry(repo)
    rc, out = repo.cap("locate", "--capability", "login")
    assert rc == 0 and out["capability"] == "login"
    assert [rule["id"] for rule in out["rules"]] == ["R-lockout", "R-session-expiry"]
    rule = rule_named(out, "R-session-expiry")
    assert rule == {
        "id": "R-session-expiry",
        "text": EXPIRY_15,
        "inferred": False,
        "origin": change,
        "state": "conforming",
        "observed": "Expira a los 15 minutos.",
        "code": [{"ref": "src/auth/session.py::SessionManager", "resolves": True}],
        "tests": [{"ref": "tests/auth/test_session.py::test_expiry", "resolves": True}],
        "manual": None,
    }
    assert rule_named(out, "R-lockout")["text"] == LOCKOUT_5
    assert rule_named(out, "R-lockout")["origin"] == "specs/001-login"
    assert [row["change"] for row in out["changes"]] == ["specs/001-login", change]
    assert all(row["what"] for row in out["changes"])
    assert out["retired"] == {}


def test_locate_says_when_the_catalog_lags_the_code(repo):
    change_expiry(repo)
    repo.replace("src/auth/session.py", "SessionManager", "SessionStore")
    rule = rule_named(repo.cap("locate", "--capability", "login")[1], "R-session-expiry")
    assert rule["code"] == [{"ref": "src/auth/session.py::SessionManager", "resolves": False}]
    assert rule["tests"][0]["resolves"] is True

    (repo.path / "tests/auth/test_session.py").unlink()
    rule = rule_named(repo.cap("locate", "--capability", "login")[1], "R-session-expiry")
    assert rule["tests"] == [{"ref": "tests/auth/test_session.py::test_expiry", "resolves": False}]


def test_locate_shows_a_rule_nobody_observed_as_such(repo):
    text = repo.read(IMPL)
    repo.write(IMPL, re.sub(r"### R-lockout\n.*?(?=### R-session-expiry)", "", text, flags=re.S))
    rule = rule_named(repo.cap("locate", "--capability", "login")[1], "R-lockout")
    assert (rule["state"], rule["observed"], rule["code"], rule["tests"]) == (None, None, [], [])


def test_locate_marks_inferred_rules(bare):
    bare.git("checkout", "-q", "-b", "bootstrap")
    run_bootstrap(bare, bootstrap_record(), rule_block("R-session-expiry", "unverified", "`src/auth/session.py::SessionManager`", "none"))
    rule = rule_named(bare.cap("locate", "--capability", "login")[1], "R-session-expiry")
    assert rule["inferred"] is True and rule["state"] == "unverified" and rule["origin"] == RECORD


@pytest.mark.parametrize("args", [(), ("--capability", "login")])
def test_locate_writes_nothing(repo, args):
    before = repo.tree()
    rc, _ = repo.cap("locate", *args)
    assert rc == 0
    assert repo.tree() == before
    assert repo.git("status", "--porcelain").stdout == ""


def test_locate_without_a_capability_is_the_catalog_summary(repo):
    rc, out = repo.cap("locate")
    assert rc == 0 and out == repo.cap("status")[1]
    assert out["capabilities"]["login"]["covers"] == "Autenticación y sesión"


def test_locate_with_no_catalog_creates_nothing(bare):
    rc, out = bare.cap("locate")
    assert rc == 0 and out == {"catalog": False, "capabilities": {}, "planned": {}, "journal_pending": False}
    assert not (bare.path / "specs").exists() and not (bare.path / ".specify").exists()


@pytest.mark.parametrize("name", ["payments", "../login", "Login", "_changes"])
def test_locate_rejects_what_is_not_a_capability(repo, name):
    rc, out = repo.cap("locate", "--capability", name)
    assert (rc, out["status"]) == (2, "invalid")


# ---------------------------------------------------------------- a catalog git ignores


def test_a_catalog_git_ignores_blocks_check_because_ci_would_have_nothing_to_check(repo):
    """The .gitignore of Spec Kit itself ignores specs/. Nothing said so, and CI would have passed."""
    (repo.path / ".gitignore").write_text(read_gitignore(repo) + "specs/\n", encoding="utf-8")
    repo.git("rm", "-r", "-q", "--cached", "specs")
    repo.commit("the catalog is no longer versioned")
    rc, out = repo.ci()
    assert rc == 1
    assert hard_with(out, "specs/_capabilities", "git ignores it", "CI has nothing to check")


def test_setup_says_when_git_ignores_the_catalog(repo):
    (repo.path / ".gitignore").write_text(read_gitignore(repo) + "specs/\n", encoding="utf-8")
    repo.git("rm", "-r", "-q", "--cached", "specs")
    repo.commit("the catalog is no longer versioned")
    rc, out = repo.cap("scaffold", "--capability", "new-one", "--covers", "Algo nuevo")
    assert rc == 0, out
    assert any(line.startswith("skipped specs/_capabilities: git ignores it") for line in out["setup"]), out


def test_a_tracked_catalog_is_fine_even_if_a_rule_would_ignore_it(repo):
    (repo.path / ".gitignore").write_text(read_gitignore(repo) + "specs/\n", encoding="utf-8")
    repo.commit("the rule came later: what is tracked stays tracked")
    rc, out = repo.ci()
    assert rc == 0, out


def read_gitignore(repo):
    path = repo.path / ".gitignore"
    return path.read_text(encoding="utf-8") if path.exists() else ""
