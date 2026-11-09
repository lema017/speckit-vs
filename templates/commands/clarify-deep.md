---
description: Interview the user in rounds along a decision tree built from the current feature spec, opening the decisions each answer creates until the spec passes a definition of clear, and encode the answers back into the spec.
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

3. Load the current spec file. The interview covers **this spec only**: the rest of the project is a source of facts and of conflicts, never of questions of its own.
   - **Resume.** If `FEATURE_DIR/clarify-tree.md` exists, this is a resumed session. Load it:
      - its settled decisions stay settled;
      - its frontier, waiting, and plan items are the starting tree;
      - its question numbering continues;
      - a settled decision that the spec no longer reflects is reopened.
   - **Inventory the spec.** List every subject it names:
      - each actor or role, user story, and acceptance scenario;
      - each functional requirement;
      - each entity, with its states and transitions;
      - each external integration;
      - each non-functional requirement and success criterion;
      - each assumption and glossary term;
      - each `[NEEDS CLARIFICATION]` marker, TODO, or vague adjective ("fast", "robust", "intuitive") that has no number.
   - **Look at every subject through every lens.** Each pair of subject and lens that the spec does not answer becomes a node of the design tree:
      - **Who:** which role does it, and with which permissions.
      - **What:** the data and fields, which are required, and the validation rules.
      - **When:** what triggers it, in what order, and with what timing.
      - **How much:** limits, volumes, and numeric targets.
      - **What if:** error, empty, duplicate, concurrent use, abusive input, and an external service that is down, slow, or answers something unexpected.
      - **How we know:** the observable acceptance criterion a tester would check.
      - **What not:** what is explicitly out of scope.
      - **What it touches:** only for a subject the spec shares with the capability catalog, another spec, or the code. Does this feature reuse it as it is, extend it, or change it?
   - **Look for what the spec does not name.** A feature of this kind usually has subjects that a spec can leave out entirely. For each one that is missing, add a node that asks whether it applies. Once it is in scope, its lenses follow:
      - other actors who touch the same data: support or operations staff, administrators, auditors, scheduled jobs;
      - the rest of the main entity's life: change, cancel, delete, expire, and what happens when its owner closes the account;
      - other channels: physical store, mobile, email and its language, API;
      - money: currency, taxes, rounding;
      - time: time zones, schedules and recurrence, how long data is kept;
      - history: what is recorded, who can see it, and for how long;
      - combinations: other features or promotions it can or cannot be combined with, and transfer or sharing between users.
   - **Use the rest of the project for facts and for conflicts.**
      - Facts come from the constitution, the code, the report of the `before_clarify` hooks, and the capability catalog.
      - When this spec names an entity, actor, or flow that another spec under `specs/` defines and the catalog does not cover, read that spec for facts about what this spec names, and nothing else. Never add nodes from another spec's own content.
      - Each conflict becomes a node:
         - the spec contradicts an approved rule: ask whether the rule changes or the spec does;
         - the spec relies on a rule that is inferred or not conforming;
         - the graph or the code shows the change reaching beyond what the spec says: ask whether that is in scope.
   - **Cross-check with the taxonomy.** For each category below that the spec leaves Partial or Missing, make sure the tree holds the nodes that category implies:

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

   - **Leave a pair out of the tree only when:**
      - the spec, its `## Clarifications`, the tree file, or a fact already settles it;
      - its answer would change neither what gets built nor how it is tested;
      - it is about implementation method, tech-stack comparison, or task breakdown. List it under `For the plan` in the tree file instead of dropping it.

4. Build (internally) the **design tree** from those nodes. Do NOT output the tree.
    - Every decision branches into the decisions that hang off it. A node whose question only makes sense once another node is answered hangs off that node. For example, how many rows an export can hold hangs off whether there is an export at all.
    - The **frontier** is every open node whose prerequisites are all settled.
    - There is no limit on the total number of questions. Ask every decision that a developer or a tester would otherwise have to guess, until every branch is resolved.
    - Answers already recorded under `## Clarifications`, or settled in the tree file, count as settled; do not ask them again.
    - **One decision per question.** A recommended answer must not settle anything that was not asked. If it needs a value of its own, such as a time limit, a maximum, or a format, that value is a child node for a later round. For example, `➡️ Yes, the link expires after 30 minutes, and earlier links stop working` settles two decisions: recommend the first, and ask whether earlier links keep working as a question of its own.
    - **Order the frontier by risk.** First the decisions that unblock the most other nodes, then those whose wrong guess would cost the most rework.
    - **A tree too big for one interview.** If the first inventory leaves more than about 60 open nodes, the feature is probably too big. Before the first round, say so, propose how to split it, and ask whether to split it or go on.

5. Round-based questioning loop (interactive):
    - A round asks the frontier, at most 10 questions, highest risk first. The rest of the frontier waits for the next round. Then wait for the user's answers before starting the next round. A question that depends on an answer still open in this round belongs to a later round.
    - If the user input asks for one question at a time ("one at a time", "una a la vez"), each round has one question.
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
       - **Business decisions.** A decision about price, policy, legal or contractual terms, or what is in or out of scope gets `⚠️ Business decision` after its title. Ask the user to answer it in their own words: "yes" alone does not settle it.
       - Answers are open: the user replies in their own words. Offer lettered, mutually exclusive options only when the decision really has discrete choices; they never limit the answer.
       - Base each recommendation on:
          - Best practices for the project type
          - Common patterns in similar implementations
          - Risk reduction (security, performance, maintainability)
          - Alignment with any explicit project goals or constraints visible in the spec
          - The facts you looked up
    - Close each round with one status line: `Round <N> · <X> settled · <Y> on the frontier · <Z> waiting · open branches: <names>`.
    - After the user answers a round:
       - The user can answer by number ("1 yes, 2 the second option, 3 no, because..."). "yes" uses your previously stated recommendation as the answer.
       - If an answer is ambiguous, ask for a quick disambiguation and do not advance that branch.
       - A question left unanswered stays on the frontier; never assume its answer.
       - **"I don't know."** A decision the user cannot make yet stays open; never fill it in. At the end of that round, list those decisions and offer, for each one: take your recommendation, keep it open under `Open` in the tree file and say who should decide, or record it as an assumption to confirm later. Keep going with the branches that do not depend on them: an unknown answer holds back only its own children.
       - Integrate each accepted answer (step 6).
       - **Every answer opens its children.** For each accepted answer, look for the decisions it creates, through the same lenses as step 3. Add each one as a child node unless it is already settled or out of scope. An answer is a leaf only after you looked for its consequences and found none.
       - Then run the inventory and the lenses of step 3 again on the updated spec, and look for contradictions between the new answers and what the spec already says. Each contradiction is a node.
       - Write the tree file (below). The new frontier is the next round.
       - If an answer changes a decision already settled, reopen that branch in the next round.
    - **The definition of clear.** The frontier can be empty only if the updated spec passes every item. Each item that fails adds nodes:
       1. No `[NEEDS CLARIFICATION]` marker, TODO, or vague adjective without its number remains.
       2. Each functional requirement describes an observable result that can be tested.
       3. Each user story has acceptance scenarios, including at least one error or edge path.
       4. Each entity has its fields, which are required, how it is identified, and its states and transitions.
       5. Each role has explicit permissions for each action.
       6. Each integration says what happens when it fails, is slow, or answers something unexpected.
       7. Each non-functional requirement has a numeric target, or says why it has none.
       8. What is out of scope is listed explicitly.
       9. Terms are consistent and defined.
       10. Each assumption is confirmed by the user, or listed as open with its reason.
    - **Adversarial pass.** When the frontier is empty and the definition of clear passes, read the updated spec as if you had never seen this conversation. Use a sub-agent with a fresh context window and only the spec if this agent supports them; otherwise reread only the spec yourself. Look for:
       - places where two developers would build different things;
       - acceptance criteria a tester could not check;
       - anything assumed without being said.
       Each finding the spec does not settle is a node; ask them as the next round. Repeat the pass until it finds nothing new or the user stops.
    - **End.** When the frontier is empty, the definition of clear passes, and the adversarial pass finds nothing new, show a summary:
       - the decisions, grouped by area;
       - the assumptions confirmed;
       - what goes to the plan;
       - anything left open.
      Then ask the user to confirm that you have reached a shared understanding. If the only nodes left are decisions the user cannot make yet, show the same summary with them under open, each with who should decide, and ask whether to stop here or to settle them now with your recommendations. The session ends only after that confirmation. End earlier only when the user signals completion ("done", "good", "no more"), and report what remains unresolved.
    - Never reveal questions outside the current frontier in advance.
    - If, at the start, the spec passes the definition of clear and the adversarial pass finds nothing, report that the spec has no open decisions, and show the definition of clear as the evidence.
    - **The tree file.** After each round's answers are integrated, write `FEATURE_DIR/clarify-tree.md` (atomic overwrite). It is the interview's memory: a later run of this command resumes from it. Keep one short line per node:

      ```markdown
      # Clarify tree: <feature>

      Round <N> · <X> settled · <Y> on the frontier · <Z> waiting

      ## Settled
      - Q<n> (round <r>): <question> → <answer>

      ## Frontier
      - <question> (<subject> · <lens>)

      ## Waiting
      - <question> (after Q<n>)

      ## Open
      - Q<n>: <question> (the user does not know yet; who decides: <role>)

      ## For the plan
      - <item>

      ## Assumptions
      - <assumption> → confirmed in Q<n> | open: <reason>
      ```

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

- If the spec has no open decisions at the start, respond: "No open decisions: the spec passes the definition of clear." and suggest proceeding.
- If spec file missing, instruct user to run `__SPECKIT_COMMAND_SPECIFY__` first (do not create a new spec here).
- Avoid speculative tech stack questions unless the absence blocks functional clarity.
- Respect user early termination signals ("stop", "done", "proceed").
- If no questions were asked, show the definition of clear with every item passing, then suggest advancing.
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
- Number of rounds, and of questions asked & answered.
- Path to updated spec, and to `FEATURE_DIR/clarify-tree.md`.
- Sections touched (list names).
- Decisions by area, what goes to the plan, and the assumptions confirmed and still open.
- The definition of clear: each item, and why each one that does not pass does not.
- Spec quality checklist status (if `FEATURE_DIR/checklists/requirements.md` was re-validated): show before/after pass counts (e.g., "Spec Quality Checklist: 12/16 → 15/16 items passing") and list any items that changed state — both newly checked (unchecked → checked) and any regressions (checked → unchecked). If any items remain unchecked, list them as areas needing attention.
- Coverage summary table listing each taxonomy category with Status: Resolved (was Partial/Missing and addressed), Deferred (postponed by the user, or remaining item is specifically implementation method, tech-stack comparison, or task breakdown), Clear (already sufficient), Outstanding (still Partial/Missing: low impact, or left open when the user ended the session early).
- If any Outstanding or Deferred remain, recommend whether to proceed to `__SPECKIT_COMMAND_PLAN__` or run `__SPECKIT_COMMAND_CLARIFY-DEEP__` again later post-plan. A new run resumes from the tree file.
- Suggested next command.

## Done When

- [ ] Spec ambiguities identified and clarifications integrated into spec file
- [ ] Spec quality checklist re-validated against updated spec (if `FEATURE_DIR/checklists/requirements.md` exists)
- [ ] Extension hooks dispatched or skipped according to the rules in Mandatory Post-Execution Hooks above
- [ ] Completion reported to user with questions answered, sections touched, checklist status, and coverage summary
