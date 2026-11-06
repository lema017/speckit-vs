---
description: Identify underspecified areas in the current feature spec by interviewing the user in rounds along a decision tree, asking as many targeted questions as the spec needs and encoding answers back into the spec.
handoffs:
  - label: Build Technical Plan
    agent: speckit.plan
    prompt: Create a plan for the spec. I am building with...
scripts:
   sh: scripts/bash/run-step.sh clarify __AGENT__ scripts/bash/check-prerequisites.sh --json --paths-only
   ps: scripts/powershell/run-step.ps1 clarify __AGENT__ scripts/powershell/check-prerequisites.ps1 -Json -PathsOnly
   py: scripts/python/run_step.py clarify __AGENT__ scripts/python/check_prerequisites.py --json --paths-only
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Pre-Execution Checks

**Check for extension hooks (before clarification)**:
- Check if `.specify/extensions.yml` exists in the project root.
- If it exists, read it and look for entries under the `hooks.before_clarify` key
- If the YAML cannot be parsed or is invalid, do not skip silently: tell the user that `.specify/extensions.yml` could not be read (include the parser error) and that no hooks were checked, including any mandatory (`optional: false`) hooks registered there, then continue normally
- Filter out hooks where `enabled` is explicitly `false`. Treat hooks without an `enabled` field as enabled by default.
- For each remaining hook, do **not** attempt to interpret or evaluate hook `condition` expressions:
  - If the hook has no `condition` field, or it is null/empty, treat the hook as executable
  - If the hook defines a non-empty `condition`, skip the hook and leave condition evaluation to the HookExecutor implementation
- For each executable hook, output the following based on its `optional` flag:
  - **Optional hook** (`optional: true`):
    ```
    ## Extension Hooks

    **Optional Pre-Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```
  - **Mandatory hook** (`optional: false`):
    ```
    ## Extension Hooks

    **Automatic Pre-Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}

    Wait for the result of the hook command before proceeding to the Outline.
    ```
    After emitting the block above you MUST actually invoke the hook and wait for it to finish before continuing. Run it the same way you would run the command yourself in this agent/session (the invocation may differ from the literal `{command}` id shown above, e.g. a skills-mode agent runs it as `/skill:speckit-...` or `$speckit-...`). Emitting the block alone does not run the hook.
- If no hooks are registered or `.specify/extensions.yml` does not exist, skip silently

## Outline

Goal: Detect and reduce ambiguity or missing decision points in the active feature specification and record the clarifications directly in the spec file.

Note: This clarification workflow is expected to run (and be completed) BEFORE invoking `__SPECKIT_COMMAND_PLAN__`. If the user explicitly states they are skipping clarification (e.g., exploratory spike), you may proceed, but must warn that downstream rework risk increases.

Execution steps:

1. Run `{SCRIPT}` from repo root **once** (combined `--json --paths-only` mode / `-Json -PathsOnly`). Parse minimal JSON payload fields:
   - `FEATURE_DIR`
   - `FEATURE_SPEC`
   - (Optionally capture `IMPL_PLAN`, `TASKS` for future chained flows.)
   - If JSON parsing fails, abort and instruct user to re-run `__SPECKIT_COMMAND_SPECIFY__` or verify feature branch environment.
   - For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

2. **IF EXISTS**: Load `/memory/constitution.md` for project principles and governance constraints.

3. Load the current spec file. Perform a structured ambiguity & coverage scan using this taxonomy. For each category, mark status: Clear / Partial / Missing. Produce an internal coverage map used for prioritization (do not output raw map unless no questions will be asked).

   Functional Scope & Behavior:
   - Core user goals & success criteria
   - Explicit out-of-scope declarations
   - User roles / personas differentiation

   Domain & Data Model:
   - Entities, attributes, relationships
   - Identity & uniqueness rules
   - Lifecycle/state transitions
   - Data volume / scale assumptions

   Interaction & UX Flow:
   - Critical user journeys / sequences
   - Error/empty/loading states
   - Accessibility or localization notes

   Non-Functional Quality Attributes:
   - Performance (latency, throughput targets)
   - Scalability (horizontal/vertical, limits)
   - Reliability & availability (uptime, recovery expectations)
   - Observability (logging, metrics, tracing signals)
   - Security & privacy (authN/Z, data protection, threat assumptions)
   - Compliance / regulatory constraints (if any)

   Integration & External Dependencies:
   - External services/APIs and failure modes
   - Data import/export formats
   - Protocol/versioning assumptions

   Edge Cases & Failure Handling:
   - Negative scenarios
   - Rate limiting / throttling
   - Conflict resolution (e.g., concurrent edits)

   Constraints & Tradeoffs:
   - Technical constraints (language, storage, hosting)
   - Explicit tradeoffs or rejected alternatives

   Terminology & Consistency:
   - Canonical glossary terms
   - Avoided synonyms / deprecated terms

   Completion Signals:
   - Acceptance criteria testability
   - Measurable Definition of Done style indicators

   Misc / Placeholders:
   - TODO markers / unresolved decisions
   - Ambiguous adjectives ("robust", "intuitive") lacking quantification

   For each category with Partial or Missing status, add a candidate question opportunity unless:
   - Clarification would not materially change implementation or validation strategy
   - The item is specifically about implementation method, tech-stack comparison, or task breakdown (note internally)

4. Build (internally) a **design tree** of the decisions still open in this spec. Each candidate question opportunity from the scan opens a branch, and each decision hangs off the decisions that must be settled first. The **frontier** is the set of decisions whose prerequisites are all settled. Do NOT output the tree. Apply these constraints:
    - There is no fixed limit on questions: ask every question that passes these constraints, until every branch is resolved, and none that does not.
    - Only include questions whose answers materially impact architecture, data modeling, task decomposition, test design, UX behavior, operational readiness, or compliance validation.
    - Exclude questions already answered, trivial stylistic preferences, or plan-level execution details (unless blocking correctness).
    - Favor clarifications that reduce downstream rework risk or prevent misaligned acceptance tests.
    - Answers already recorded under `## Clarifications` count as settled; do not ask them again.

5. Round-based questioning loop (interactive):
    - Present the whole frontier as one round, then wait for the user's answers before starting the next round. A question that depends on an answer still open in this round belongs to a later round.
    - **Facts vs decisions:** facts are your job; decisions belong to the user.
       - Before asking, look up anything the repository or the feature artifacts can settle, without modifying files. Use a sub-agent with a fresh context window if this agent supports them; otherwise look it up yourself.
       - Do not hold a round back for a lookup: only the questions that depend on its result wait.
       - Never ask the user for something you could look up, and never settle a decision on the user's behalf.
    - **Question writing quality (applies to every question):**
       - Number questions continuously across the session and format each one as follows, separating questions with a `---` line:

         ```text
         ❓ **Q1** - **<short title>**: <full interrogative ending with ?>

         Why it matters: <one plain-language sentence>

         <options, only when they help>

         ➡️ <your recommended answer> - <brief reasoning>
         ```

       - The question text before the `?` must make sense on its own. NEVER use a topic label, section heading, or requirement id as the question itself. For example, `Acceptance device/runtime matrix (FR-023)` is INVALID — it is a label, not a question.
       - After the `?`, the only permitted suffix is an optional parenthesized requirement/question id, for example `<full interrogative>? (FR-023)`.
       - "Why it matters" states the stake for acceptance or shipping.
       - Use everyday wording; introduce jargon only if defined in the same sentence. Self-check: a reader who does not know Spec Kit must be able to answer from the question alone. Terse is fine; cryptic labels are not.
       - Word each question so that "yes" accepts your recommended answer.
       - Answers are open: the user replies in their own words. Offer lettered, mutually exclusive options only when the decision really has discrete choices; they never limit the answer.
       - Base each recommendation on:
          - Best practices for the project type
          - Common patterns in similar implementations
          - Risk reduction (security, performance, maintainability)
          - Alignment with any explicit project goals or constraints visible in the spec
          - The facts you looked up
    - Close each round with one line stating how many decisions are settled and which open branches you can see.
    - After the user answers a round:
       - The user can answer by number ("1 yes, 2 the second option, 3 no, because..."). "yes" uses your previously stated recommendation as the answer.
       - If an answer is ambiguous, ask for a quick disambiguation and do not advance that branch.
       - A question left unanswered stays on the frontier; never assume its answer.
       - Integrate each accepted answer (step 6), then recompute the tree: an answer can open, close, or reorder branches, and the new frontier is the next round.
       - If an answer changes a decision already settled, reopen that branch in the next round.
    - The session ends when the frontier is empty and the user confirms you have reached a shared understanding. End earlier only when the user signals completion ("done", "good", "no more"), and report what remains unresolved.
    - Never reveal questions outside the current frontier in advance.
    - If no valid questions exist at start, immediately report no critical ambiguities.

6. Integration after EACH accepted answer (incremental update approach):
    - Maintain in-memory representation of the spec (loaded once at start) plus the raw file contents.
    - For the first integrated answer in this session:
       - Ensure a `## Clarifications` section exists (create it just after the highest-level contextual/overview section per the spec template if missing).
       - Under it, create (if not present) a `### Session YYYY-MM-DD` subheading for today.
    - Append a bullet line immediately after acceptance: `- Q: <question> → A: <final answer>`.
    - Then immediately apply the clarification to the most appropriate section(s):
       - Functional ambiguity → Update or add a bullet in Functional Requirements.
       - User interaction / actor distinction → Update User Stories or Actors subsection (if present) with clarified role, constraint, or scenario.
       - Data shape / entities → Update Data Model (add fields, types, relationships) preserving ordering; note added constraints succinctly.
       - Non-functional constraint → Add/modify measurable criteria in Success Criteria > Measurable Outcomes (convert vague adjective to metric or explicit target).
       - Edge case / negative flow → Add a new bullet under Edge Cases / Error Handling (or create such subsection if template provides placeholder for it).
       - Terminology conflict → Normalize term across spec; retain original only if necessary by adding `(formerly referred to as "X")` once.
    - If the clarification invalidates an earlier ambiguous statement, replace that statement instead of duplicating; leave no obsolete contradictory text.
    - Save the spec file AFTER each integration to minimize risk of context loss (atomic overwrite).
    - Preserve formatting: do not reorder unrelated sections; keep heading hierarchy intact.
    - Keep each inserted clarification minimal and testable (avoid narrative drift).

7. Validation (performed after EACH write plus final pass):
   - Clarifications session contains exactly one bullet per accepted answer (no duplicates).
   - Updated sections contain no lingering vague placeholders the new answer was meant to resolve.
   - No contradictory earlier statement remains (scan for now-invalid alternative choices removed).
   - Markdown structure valid; only allowed new headings: `## Clarifications`, `### Session YYYY-MM-DD`.
   - Terminology consistency: same canonical term used across all updated sections.

8. Write the updated spec back to `FEATURE_SPEC`.

9. **Re-validate Spec Quality Checklist** (if it exists):
   - Check if `FEATURE_DIR/checklists/requirements.md` exists.
   - If it does NOT exist, skip this step silently.
   - If it exists:
     1. Read the checklist file.
     2. Identify all GitHub task-list checkbox lines — lines matching `- [ ]`, `- [x]`, or `- [X]` (case-insensitive, tolerant of leading whitespace for nested items) outside of code fences. Ignore all other content (headings, notes, non-checkbox bullets, metadata).
     3. For each checkbox line, record its current marker state (checked or unchecked) and item text into a before-snapshot list.
     4. Re-evaluate each checkbox item against the **updated** spec (the version just saved in step 7).
     5. For each checkbox item, update only if the checked/unchecked state actually changes:
        - If the item now passes and was unchecked: change `[ ]` to `[x]`.
        - If the item now fails and was checked: change `[x]`/`[X]` to `[ ]`.
        - If the state is unchanged: leave the marker as-is (preserve existing case to avoid cosmetic diffs).
     6. Save the updated checklist file. **Only toggle the `[ ]`/`[x]` marker portion of checkbox lines whose state changed.** All other file content — headings, metadata, notes, line ordering, whitespace — must remain unchanged to avoid noisy diffs.
     7. Compare the before-snapshot with the current state to compute three lists for the Completion Report:
        - **Newly passing**: items that changed from unchecked to checked.
        - **Regressions**: items that changed from checked to unchecked.
        - **Still unchecked**: items that remain unchecked.
     8. Record the before/after pass counts as checked/total checkbox items (e.g., "12/16 → 15/16 items passing").

Behavior rules:

- If no meaningful ambiguities found (or all potential questions would be low-impact), respond: "No critical ambiguities detected worth formal clarification." and suggest proceeding.
- If spec file missing, instruct user to run `__SPECKIT_COMMAND_SPECIFY__` first (do not create a new spec here).
- Avoid speculative tech stack questions unless the absence blocks functional clarity.
- Respect user early termination signals ("stop", "done", "proceed").
- If no questions asked due to full coverage, output a compact coverage summary (all categories Clear) then suggest advancing.
- If the user ends the session early or postpones a decision while high-impact categories remain unresolved, explicitly flag them under Outstanding or Deferred with rationale.

Context for prioritization: {ARGS}

## Mandatory Post-Execution Hooks

**You MUST complete this section before reporting completion to the user.**

First run `{PROGRESS} step clarify done --note "<one line: what was decided>"` once to record this step. End your report to the user with its output. If it fails, say so in one line and carry on: progress never blocks this command.

Check if `.specify/extensions.yml` exists in the project root.
- If it does not exist, or no hooks are registered under `hooks.after_clarify`, skip to the Completion Report.
- If it exists, read it and look for entries under the `hooks.after_clarify` key.
- If the YAML cannot be parsed or is invalid, do not skip silently: tell the user that `.specify/extensions.yml` could not be read (include the parser error) and that no hooks were checked, including any mandatory (`optional: false`) hooks registered there, then continue to the Completion Report.
- Filter out hooks where `enabled` is explicitly `false`. Treat hooks without an `enabled` field as enabled by default.
- For each remaining hook, do **not** attempt to interpret or evaluate hook `condition` expressions:
  - If the hook has no `condition` field, or it is null/empty, treat the hook as executable
  - If the hook defines a non-empty `condition`, skip the hook and leave condition evaluation to the HookExecutor implementation
- For each executable hook, output the following based on its `optional` flag:
  - **Mandatory hook** (`optional: false`) — **You MUST emit `EXECUTE_COMMAND:` for each mandatory hook**:
    ```
    ## Extension Hooks

    **Automatic Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}
    ```
    After emitting the block above you MUST actually invoke the hook and wait for it to finish before continuing. Run it the same way you would run the command yourself in this agent/session (the invocation may differ from the literal `{command}` id shown above, e.g. a skills-mode agent runs it as `/skill:speckit-...` or `$speckit-...`). Emitting the block alone does not run the hook.
  - **Optional hook** (`optional: true`):
    ```
    ## Extension Hooks

    **Optional Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```

## Completion Report

Report completion (after questioning loop ends or early termination):
- Number of questions asked & answered.
- Path to updated spec.
- Sections touched (list names).
- Spec quality checklist status (if `FEATURE_DIR/checklists/requirements.md` was re-validated): show before/after pass counts (e.g., "Spec Quality Checklist: 12/16 → 15/16 items passing") and list any items that changed state — both newly checked (unchecked → checked) and any regressions (checked → unchecked). If any items remain unchecked, list them as areas needing attention.
- Coverage summary table listing each taxonomy category with Status: Resolved (was Partial/Missing and addressed), Deferred (postponed by the user, or remaining item is specifically implementation method, tech-stack comparison, or task breakdown), Clear (already sufficient), Outstanding (still Partial/Missing: low impact, or left open when the user ended the session early).
- If any Outstanding or Deferred remain, recommend whether to proceed to `__SPECKIT_COMMAND_PLAN__` or run `__SPECKIT_COMMAND_CLARIFY-DEEP__` again later post-plan.
- Suggested next command.

## Done When

- [ ] Spec ambiguities identified and clarifications integrated into spec file
- [ ] Spec quality checklist re-validated against updated spec (if `FEATURE_DIR/checklists/requirements.md` exists)
- [ ] Extension hooks dispatched or skipped according to the rules in Mandatory Post-Execution Hooks above
- [ ] Completion reported to user with questions answered, sections touched, checklist status, and coverage summary
