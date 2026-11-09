"""``templates/commands/clarify-deep.md`` must stay a variant of ``clarify.md``.

The command shares the mechanics of ``clarify.md``: reading the feature paths,
writing answers into the spec, validating it, re-checking the checklist, and the
hooks. It changes how the decision tree is built and walked, and drops the rules
that keep ``clarify`` short. These tests fail when a merge changes the shared
mechanics in one file without the other, when a rule that keeps the interview
short comes back, and when the fork's install source drifts back to upstream.
"""

from pathlib import Path

from specify_cli import SKILL_DESCRIPTIONS, _version
from specify_cli.extensions import (
    _FALLBACK_CORE_COMMAND_NAMES,
    CORE_COMMAND_NAMES,
    REINSTALL_COMMAND,
)
from specify_cli.integrations.base import _CORE_COMMAND_TEMPLATE_ORDER
from specify_cli.integrations.claude import ClaudeIntegration
from specify_cli.integrations.copilot import _COPILOT_CORE_COMMANDS

ROOT = Path(__file__).parent.parent
COMMANDS = ROOT / "templates" / "commands"
CLARIFY = COMMANDS / "clarify.md"
DEEP = COMMANDS / "clarify-deep.md"

FORK = "lema017/speckit-vs"
UPSTREAM = "github/spec-kit"

# (start marker, end marker) of blocks that must be byte-identical.
SHARED_BLOCKS = (
    ("handoffs:\n", "\n---\n"),
    ("## User Input", "\n3. "),
    ("6. Integration after EACH accepted answer", "\n7. Validation"),
    ("8. Write the updated spec", "\nBehavior rules:"),
    ("Context for prioritization:", "\n## Completion Report"),
    ("## Done When", None),
)

# Lines kept from blocks that also contain authorized changes.
SHARED_LINE_PREFIXES = (
    "   - Clarifications session contains",
    "   - Updated sections contain",
    "   - No contradictory earlier statement",
    "   - Markdown structure valid",
    "   - Terminology consistency",
    "- If spec file missing",
    "- Avoid speculative tech stack",
    "- Respect user early termination",
    "- Sections touched",
    "- Spec quality checklist status",
    "- Suggested next command",
)

QUOTA_PHRASES = (
    "up to 5",
    "maximum 5",
    "Maximum of 5",
    "EXACTLY ONE",
    "<=5",
    "≤ 5",
    "5 asked",
    "exceed 5",
    "top 5",
    "quota",
)

# Rules of ``clarify`` that keep its five questions to the highest impact. In
# ``clarify-deep`` they stopped the interview after one round.
SHORT_INTERVIEW_PHRASES = (
    "materially impact",
    "materially change",
    "low-impact",
    "No critical ambiguities detected worth formal clarification",
    "whole frontier as one round",
)

SCOPE_RULE = "implementation method, tech-stack comparison, or task breakdown"


def _block(text: str, start: str, end: str | None) -> str:
    first = text.index(start)
    return text[first:] if end is None else text[first : text.index(end, first)]


def _line(text: str, prefix: str) -> str:
    matches = [line for line in text.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1, f"expected one line starting with {prefix!r}"
    return matches[0]


def _parity_mismatches(base: str, variant: str) -> list[str]:
    """Return the markers of shared content that differs between the two texts."""
    mismatches = [
        start
        for start, end in SHARED_BLOCKS
        if _block(base, start, end) != _block(variant, start, end)
    ]
    mismatches += [
        prefix
        for prefix in SHARED_LINE_PREFIXES
        if _line(base, prefix) != _line(variant, prefix)
    ]
    return mismatches


def _deep_text() -> str:
    return DEEP.read_text(encoding="utf-8")


def _clarify_text() -> str:
    return CLARIFY.read_text(encoding="utf-8")


def test_shared_content_matches_clarify() -> None:
    assert _parity_mismatches(_clarify_text(), _deep_text()) == []


def test_parity_check_detects_drift_in_a_shared_block() -> None:
    drifted = _clarify_text().replace("## Done When", "## Done When\n\n- extra", 1)
    assert _parity_mismatches(drifted, _deep_text()) == ["## Done When"]


def test_parity_check_detects_drift_in_a_shared_line() -> None:
    prefix = "- Avoid speculative tech stack"
    drifted = _clarify_text().replace(prefix, f"{prefix} changed", 1)
    assert _parity_mismatches(drifted, _deep_text()) == [prefix]


def test_no_question_quota_remains() -> None:
    text = _deep_text()
    assert [phrase for phrase in QUOTA_PHRASES if phrase in text] == []


def test_quota_check_would_catch_clarify_rules() -> None:
    text = _clarify_text()
    assert "Maximum of 5" in text
    assert "EXACTLY ONE" in text


def test_interview_method_is_present() -> None:
    text = _deep_text()
    for required in (
        "**design tree**",
        "**frontier**",
        "Every decision branches into the decisions that hang off it",
        "at most 10 questions, highest risk first",
        "**Facts vs decisions:**",
        "shared understanding",
        '"yes" accepts your recommended answer',
        "❓ **Q1**",
        "➡️",
    ):
        assert required in text


def test_tree_grows_from_this_spec_and_from_each_answer() -> None:
    text = _deep_text()
    for required in (
        "The interview covers **this spec only**",
        "**Inventory the spec.**",
        "**Look at every subject through every lens.**",
        "**What it touches:**",
        "**Look for what the spec does not name.**",
        "Never add nodes from another spec's own content.",
        "**Every answer opens its children.**",
        "run the inventory and the lenses of step 3 again on the updated spec",
        "**One decision per question.**",
        '**"I don\'t know."** A decision the user cannot make yet stays open',
        "`⚠️ Business decision`",
    ):
        assert required in text


def test_session_ends_only_on_the_definition_of_clear() -> None:
    text = _deep_text()
    for required in (
        "**The definition of clear.** The frontier can be empty only if",
        "**Adversarial pass.**",
        "places where two developers would build different things",
        "The session ends only after that confirmation.",
        "Round <N> · <X> settled · <Y> on the frontier · <Z> waiting",
    ):
        assert required in text
    assert (
        "The definition of clear: each item" in text.split("## Completion Report", 1)[1]
    )


def test_tree_file_is_written_and_resumed() -> None:
    text = _deep_text()
    assert "If `FEATURE_DIR/clarify-tree.md` exists, this is a resumed session." in text
    assert "write `FEATURE_DIR/clarify-tree.md` (atomic overwrite)" in text
    for heading in (
        "## Settled",
        "## Frontier",
        "## Waiting",
        "## Open",
        "## For the plan",
        "## Assumptions",
    ):
        assert f"      {heading}\n" in text


def test_one_question_at_a_time_is_available() -> None:
    assert (
        '("one at a time", "una a la vez"), each round has one question' in _deep_text()
    )


def test_no_short_interview_rule_remains() -> None:
    text = _deep_text()
    assert [phrase for phrase in SHORT_INTERVIEW_PHRASES if phrase in text] == []


def test_short_interview_check_would_catch_clarify_rules() -> None:
    text = _clarify_text()
    assert "materially impact" in text
    assert "low-impact" in text
    assert "No critical ambiguities detected worth formal clarification" in text


def test_planning_deferral_stays_bounded() -> None:
    text = _deep_text()
    assert SCOPE_RULE in text
    assert SCOPE_RULE in text.split("## Completion Report", 1)[1]


def test_uses_clarify_hooks_and_own_command_token() -> None:
    text = _deep_text()
    assert "hooks.before_clarify" in text
    assert "hooks.after_clarify" in text
    assert "before_clarify-deep" not in text
    assert "__SPECKIT_COMMAND_CLARIFY-DEEP__" in text
    assert "__SPECKIT_COMMAND_CLARIFY__" not in text


def test_clarify_keeps_its_question_limit() -> None:
    assert "up to 5" in _clarify_text()


def test_specify_offers_both_clarify_commands() -> None:
    frontmatter = (COMMANDS / "specify.md").read_text(encoding="utf-8").split("---")[1]
    assert "agent: speckit.clarify\n" in frontmatter
    assert "agent: speckit.clarify-deep\n" in frontmatter


def test_command_is_registered_as_core() -> None:
    assert "clarify-deep" in CORE_COMMAND_NAMES
    assert "clarify-deep" in _FALLBACK_CORE_COMMAND_NAMES
    assert "clarify-deep" in _CORE_COMMAND_TEMPLATE_ORDER
    assert "clarify-deep" in _COPILOT_CORE_COMMANDS
    assert "clarify-deep" in SKILL_DESCRIPTIONS


def test_integrations_discover_the_command_template() -> None:
    stems = [path.stem for path in ClaudeIntegration().list_command_templates()]
    assert "clarify-deep" in stems
    assert "clarify" in stems


def test_install_source_points_to_the_fork() -> None:
    assert FORK in _version.GITHUB_API_LATEST
    assert FORK in _version._GITHUB_SOURCE_URL
    assert FORK in REINSTALL_COMMAND
    assert UPSTREAM not in Path(_version.__file__).read_text(encoding="utf-8")
    assert UPSTREAM not in REINSTALL_COMMAND
