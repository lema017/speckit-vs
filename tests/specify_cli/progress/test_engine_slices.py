"""The list of specs groups them by slice map: the slices of a larger request, in order.

The capabilities extension writes the maps (``specs/_slices/<name>.md``) and the ``## Slice``
section of a spec. The engine reads them itself, so a redraw starts no other process.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import symlink
from .test_engine_render import HOSTILE, parse_page

MARK = "<!-- slice-map:v1 -->"
SIGN_UP, SIGN_IN, RESET, SOCIAL = "D-login-sign-up", "D-login-sign-in", "D-login-reset", "D-login-social"
OPEN = "- [x] T001 One\n- [ ] T002 Two\n"
CLOSED = "- [x] T001 One\n- [X] T002 Two\n"
FOLDED = json.dumps({"schema": 1, "fold": {"anchors": {}}})
SEALED = json.dumps({"schema": 1})


def block(slice_id, title, depends="none", more=""):
    return "### %s %s\n- Intent: A person does it.\n- Verify: I do it and see it.\n- Depends-On: %s\n- Rules: none\n%s\n" % (slice_id, title, depends, more)


def slice_map(project, *blocks, name="login", mark=MARK, request="Request: The whole login.\n\n"):
    directory = project.root / "specs" / "_slices"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name + ".md")
    path.write_text("# Slices: %s\n\n%s\n\n%s%s" % (name, mark, request, "".join(blocks)), encoding="utf-8", newline="\n")
    return path


def login(project):
    return slice_map(
        project,
        block(SIGN_UP, "Create an account"),
        block(SIGN_IN, "Sign in with a password", SIGN_UP),
        block(RESET, "Reset the password", SIGN_IN),
        block(SOCIAL, "Sign in with Google", SIGN_IN),
    )


def spec(slice_line=None, rules=False, title="Create an account"):
    """A spec that names its slice. Without ``slice_line`` it is a spec from before slices."""
    text = "# Feature Specification: %s\n\n" % title
    if slice_line:
        text += "## Slice *(mandatory)*\n\n- Slice: %s\n- Out: none\n\n" % slice_line
    text += "## Requirements\n\n- **FR-001**: The system MUST do it.\n\n## Capability Delta *(mandatory)*\n\n<!-- capability-delta:v1 -->\n"
    if rules:
        return text + "### ADDED R-accounts-unique-email\n- Capability: accounts\n- From: (none)\n- To: One account per email.\n- Links: FR-001\n"
    return text + "Capabilities: none - nothing changes\n"


def listed(engine, project):
    return json.loads(parse_page(Path(engine.render_project(project.root)["index"])).data)


def states(group):
    return [(view["id"], view["state"], view["spec"]) for view in group["slices"]]


# -- A project without maps is listed as before ------------------------------------------------


def test_without_a_map_the_list_has_no_groups_and_reads_no_spec_twice(engine, project, monkeypatch):
    project.feature("001-sign-up", spec=spec(SIGN_UP))
    monkeypatch.setattr(engine, "spec_slice", lambda directory: pytest.fail("no map, so no spec is read for its slice"))
    data = listed(engine, project)
    assert data["maps"] == []
    assert [row["slice"] for row in data["specs"]] == [None]
    assert engine.project_slices(project.root) == []


# -- A map and the state of its slices ---------------------------------------------------------


def test_a_map_lists_its_slices_in_the_order_it_was_written(engine, project):
    login(project)
    (group,) = listed(engine, project)["maps"]
    assert (group["name"], group["request"]) == ("login", "The whole login.")
    assert states(group) == [(SIGN_UP, "pending", None), (SIGN_IN, "pending", None), (RESET, "pending", None), (SOCIAL, "pending", None)]
    assert [view["title"] for view in group["slices"]] == ["Create an account", "Sign in with a password", "Reset the password", "Sign in with Google"]
    assert [view["waiting_for"] for view in group["slices"]] == [[], [SIGN_UP], [SIGN_IN], [SIGN_IN]]
    assert (group["total"], group["delivered"], group["next"]) == (4, 0, SIGN_UP)


@pytest.mark.parametrize("tasks, rules, lock, state", [
    (None, False, None, "specified"),
    (None, True, SEALED, "specified"),
    (None, True, FOLDED, "delivered"),
    (OPEN, False, None, "building"),
    (OPEN, True, FOLDED, "building"),
    (CLOSED, False, None, "delivered"),
    (CLOSED, True, None, "building"),
    (CLOSED, True, SEALED, "building"),
    (CLOSED, True, FOLDED, "delivered"),
    (CLOSED, True, "{", "building"),
    (CLOSED, True, "[]", "building"),
])
def test_the_state_of_a_slice_is_read_from_its_spec(engine, project, tasks, rules, lock, state):
    """Delivered needs every task closed and, when the spec changes rules, its delta folded."""
    login(project)
    directory = project.feature("001-sign-up", spec=spec(SIGN_UP, rules=rules), tasks=tasks)
    if lock is not None:
        (directory / "capability-delta.lock.json").write_text(lock, encoding="utf-8")
    data = listed(engine, project)
    assert states(data["maps"][0])[0] == (SIGN_UP, state, "001-sign-up")
    assert data["specs"][0]["slice"] == SIGN_UP
    assert data["maps"][0]["delivered"] == (1 if state == "delivered" else 0)


def test_only_a_rule_the_delta_really_changes_asks_for_a_fold(engine, project):
    login(project)
    example = "<!--\n### ADDED R-example-rule\n- Capability: example\n-->\nCapabilities: none"
    project.feature("001-sign-up", spec=spec(SIGN_UP).replace("Capabilities: none", example), tasks=CLOSED)
    twice = spec(SIGN_IN, rules=True) + "\n## Capability Delta *(mandatory)*\n\n<!-- capability-delta:v1 -->\n"
    project.feature("002-sign-in", spec=twice, tasks=CLOSED)
    assert [state for _, state, _ in states(listed(engine, project)["maps"][0])[:2]] == ["delivered", "delivered"], (
        "an example in a comment is no rule, and a delta written twice is not a delta: the extension reads no rule in either")


def test_the_next_slice_is_the_first_one_that_waits_for_nothing(engine, project):
    login(project)
    project.feature("001-sign-up", spec=spec(SIGN_UP), tasks=OPEN)
    group = listed(engine, project)["maps"][0]
    assert group["next"] is None, "the first slice is being built and the others wait for it"
    assert group["slices"][1]["waiting_for"] == [SIGN_UP]
    (project.root / "specs/001-sign-up/tasks.md").write_text(CLOSED, encoding="utf-8")
    group = listed(engine, project)["maps"][0]
    assert (group["delivered"], group["total"], group["next"]) == (1, 4, SIGN_IN)
    assert [view["waiting_for"] for view in group["slices"]] == [[], [], [SIGN_IN], [SIGN_IN]]


def test_a_dropped_slice_is_not_counted_and_is_never_next(engine, project):
    slice_map(project, block(SIGN_UP, "Create an account", more="- Dropped: accounts come from the company directory\n"), block(SIGN_IN, "Sign in"))
    group = listed(engine, project)["maps"][0]
    assert states(group) == [(SIGN_UP, "dropped", None), (SIGN_IN, "pending", None)]
    assert (group["total"], group["delivered"], group["next"]) == (1, 0, SIGN_IN)


def test_a_slice_waits_for_a_slice_of_another_map(engine, project):
    slice_map(project, block("D-accounts-profile", "Edit the profile"), name="accounts")
    slice_map(project, block(SIGN_IN, "Sign in", "D-accounts-profile, D-nowhere-else"))
    accounts, login_map = listed(engine, project)["maps"]
    assert (accounts["name"], login_map["name"]) == ("accounts", "login"), "maps come in file order"
    assert login_map["slices"][0]["waiting_for"] == ["D-accounts-profile", "D-nowhere-else"], "a slice no map defines is never delivered"
    assert login_map["next"] is None


# -- Which spec builds which slice -------------------------------------------------------------


def test_only_a_spec_that_names_a_slice_of_a_map_is_grouped(engine, project):
    login(project)
    project.feature("001-sign-up", spec=spec(SIGN_UP))
    project.feature("002-old", spec=spec())
    project.feature("003-alone", spec=spec("standalone - Delete a campaign"))
    project.feature("004-elsewhere", spec=spec("D-other-thing"))
    project.feature("005-template", spec=spec("[slice id from specs/_slices/]"))
    data = listed(engine, project)
    assert [row["slice"] for row in data["specs"]] == [SIGN_UP, None, None, "D-other-thing", None]
    assert [view["spec"] for view in data["maps"][0]["slices"]] == ["001-sign-up", None, None, None]


def test_the_first_spec_that_names_a_slice_is_the_one_that_builds_it(engine, project):
    login(project)
    project.feature("001-sign-up", spec=spec(SIGN_UP), tasks=None)
    project.feature("002-sign-up-again", spec=spec(SIGN_UP), tasks=CLOSED)
    assert states(listed(engine, project)["maps"][0])[0] == (SIGN_UP, "specified", "001-sign-up")


def test_the_slice_section_is_read_as_the_extension_reads_it(engine, project):
    login(project)
    commented = spec(SIGN_UP).replace("- Slice: %s" % SIGN_UP, "<!--\n- Slice: %s\n-->\n- Slice:   %s  " % (SIGN_IN, SIGN_UP))
    project.feature("001-sign-up", spec=commented)
    project.feature("002-twice", spec=spec(SIGN_IN).replace("- Out: none", "- Slice: %s\n- Out: none" % RESET))
    project.feature("003-later", spec=spec().replace("## Capability Delta", "## Capability Delta x\n\n## Slice\n\n- Slice: %s\n\n## Other" % SOCIAL))
    data = listed(engine, project)
    assert [row["slice"] for row in data["specs"]] == [SIGN_UP, SIGN_IN, SOCIAL], "a comment is skipped, the first line counts, the section can be anywhere"


def test_the_slices_folder_is_not_a_spec(engine, project):
    login(project)
    project.feature("001-sign-up", spec=spec(SIGN_UP))
    engine.render_project(project.root)
    out = project.root / ".specify" / "progress"
    assert sorted(path.name for path in out.iterdir()) == [".gitignore", "001-sign-up.html", "index.html"]


def test_the_slices_can_be_read_without_drawing_anything(engine, project):
    login(project)
    project.feature("001-sign-up", spec=spec(SIGN_UP), tasks=CLOSED)
    before = project.written()
    groups = engine.project_slices(project.root)
    assert project.written() == before
    assert groups == listed(engine, project)["maps"]


# -- A map the engine cannot read is left out --------------------------------------------------


@pytest.mark.parametrize("change", [
    lambda text: text.replace(MARK, ""),
    lambda text: text.replace(MARK, "<!-- slice-map:v2 -->"),
    lambda text: text.replace(MARK, MARK + "\n<!-- slice-map:v9 -->"),
    lambda text: text + "<<<<<<< HEAD\n### D-login-extra Extra\n=======\n>>>>>>> other\n",
    lambda text: "# Slices: login\n\n%s\n\nRequest: Nothing yet.\n" % MARK,
    lambda text: text.replace("### D-", "### X-"),
])
def test_a_map_that_cannot_be_read_leaves_its_specs_in_the_plain_list(engine, project, change):
    path = login(project)
    path.write_text(change(path.read_text(encoding="utf-8")), encoding="utf-8")
    project.feature("001-sign-up", spec=spec(SIGN_UP))
    data = listed(engine, project)
    assert data["maps"] == []
    assert [row["id"] for row in data["specs"]] == ["001-sign-up"]


def test_a_linked_map_or_folder_is_not_followed(engine, project, tmp_path):
    real = tmp_path / "elsewhere"
    real.mkdir()
    (real / "login.md").write_text("# Slices: login\n\n%s\n\n%s" % (MARK, block(SIGN_UP, "Create an account")), encoding="utf-8")
    (project.root / "specs").mkdir(exist_ok=True)
    symlink(project.root / "specs" / "_slices", real)
    assert engine.read_slice_maps(project.root) == []
    (project.root / "specs" / "_slices").unlink()
    (project.root / "specs" / "_slices").mkdir()
    symlink(project.root / "specs" / "_slices" / "login.md", real / "login.md")
    assert engine.read_slice_maps(project.root) == []


def test_only_what_the_map_says_outside_comments_is_read(engine, project):
    slice_map(
        project,
        "<!--\n### D-login-example An example\n- Depends-On: none\n-->\n",
        block(SIGN_UP, "Create an account", more="- Dropped: \n- Depends-On: %s\n" % SIGN_IN),
        "### Not a slice\n- Dropped: yes\n\n",
        block(SIGN_IN, "Sign in", " %s ,  D-login-other " % SIGN_UP),
        "## Later\n\n- R-login-reset-expiry: later\nRequest: not this one\n",
    )
    (found,) = engine.read_slice_maps(project.root)
    assert found == {"name": "login", "request": "The whole login.", "slices": [
        {"id": SIGN_UP, "title": "Create an account", "dropped": False, "depends_on": []},
        {"id": SIGN_IN, "title": "Sign in", "dropped": False, "depends_on": [SIGN_UP, "D-login-other"]},
    ]}, "an empty Dropped drops nothing, and a field counts once, as its first line"


# -- The list stays as safe with a map ---------------------------------------------------------


def test_hostile_text_in_a_map_stays_text(engine, project):
    slice_map(project, block(SIGN_UP, HOSTILE.strip()), request="Request: %s\n\n" % HOSTILE.strip())
    project.feature("001-sign-up", spec=spec(SIGN_UP))
    parsed = parse_page(Path(engine.render_project(project.root)["index"]))
    assert parsed.tags.count("script") == 2 and "img" not in parsed.tags
    group = json.loads(parsed.data)["maps"][0]
    # A map is read line by line, as the extension reads it, and U+2028 ends a line.
    first_line = HOSTILE.splitlines()[0]
    assert "</script><img" in first_line and "<!--<script>" in first_line
    assert group["slices"][0]["title"] == first_line
    assert group["request"] == first_line
