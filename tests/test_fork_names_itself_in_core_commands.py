"""The core commands say they belong to speckit-vs, so an agent that picks one does not stop where the original Spec Kit stops.

These tests read the command templates. They do not run an LLM.
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
COMMANDS = REPO_ROOT / "templates" / "commands"
FLOW = ("specify", "clarify", "clarify-deep", "plan", "tasks", "analyze", "implement")


def _frontmatter(name):
    text = (COMMANDS / f"{name}.md").read_text(encoding="utf-8")
    return text, yaml.safe_load(text.split("---")[1])


@pytest.mark.parametrize("name", FLOW + ("converge",))
def test_flow_command_description_names_the_fork_on_one_line(name):
    text, front = _frontmatter(name)
    description = front["description"]
    assert "Part of speckit-vs, a fork of Spec Kit" in description
    # One line, as every hand-written core description, and the original text is kept in front.
    assert sum(1 for line in text.split("---")[1].splitlines() if line.startswith("description:")) == 1
    assert f"description: {description}\n" in text
    assert not description.startswith("Part of speckit-vs")


@pytest.mark.parametrize("name", FLOW)
def test_flow_command_description_says_the_change_ends_with_converge_and_the_fold(name):
    _, front = _frontmatter(name)
    assert front["description"].endswith(
        "where a change ends only after converge and, when the capabilities extension is installed, the catalog fold."
    )


def test_converge_sends_a_converged_feature_to_the_fold_before_its_pr():
    text, front = _frontmatter("converge")
    assert front["description"].endswith("Once it reports converged and the capabilities extension is installed, run the catalog fold.")
    body = " ".join(text.split())
    assert "If `.specify/extensions/capabilities/` exists, the next step is `__SPECKIT_COMMAND_CAPABILITIES_FOLD__`" in body
    assert "does not count the feature as done, nor open its PR, before the fold" in body
    assert "Otherwise recommend proceeding to review / opening a PR." in body


@pytest.mark.parametrize("name", ["checklist", "constitution", "progress"])
def test_commands_outside_the_flow_keep_their_description(name):
    _, front = _frontmatter(name)
    assert "speckit-vs" not in front["description"]
