"""``templates/commands/clarify-deep.md`` must stay a variant of ``clarify.md``.

The command is a copy of ``clarify.md`` that changes only how questions are
asked. These tests fail when a merge changes the shared behavior in one file
without the other, and when the fork's install source drifts back to upstream.
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
    ("## User Input", "\n4. "),
    ("6. Integration after EACH accepted answer", "\n7. Validation"),
    ("8. Write the updated spec", "\nBehavior rules:"),
    ("Context for prioritization:", "\n## Completion Report"),
    ("## Done When", None),
)

# Lines kept from blocks that also contain authorized changes.
SHARED_LINE_PREFIXES = (
    "    - Only include questions whose answers",
    "    - Exclude questions already answered",
    "    - Favor clarifications that reduce",
    "    - If no valid questions exist at start",
    "   - Clarifications session contains",
    "   - Updated sections contain",
    "   - No contradictory earlier statement",
    "   - Markdown structure valid",
    "   - Terminology consistency",
    "- If no meaningful ambiguities found",
    "- If spec file missing",
    "- Avoid speculative tech stack",
    "- Respect user early termination",
    "- If no questions asked due to full coverage",
    "- Number of questions asked",
    "- Path to updated spec",
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
        "whole frontier as one round",
        "**Facts vs decisions:**",
        "shared understanding",
        '"yes" accepts your recommended answer',
        "❓ **Q1**",
        "➡️",
    ):
        assert required in text


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
