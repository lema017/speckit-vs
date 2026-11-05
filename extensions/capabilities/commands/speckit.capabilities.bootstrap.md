---
description: "Propose a capability map for an existing project and consolidate the chosen capabilities as inferred rules"
scripts:
  py: scripts/python/capabilities.py
---

# Capability Bootstrap

Builds the first catalog of a project that already has code. Rules deduced here describe what the code does; they stay marked `[inferred]` until a person validates them.

## User Input

```text
$ARGUMENTS
```

The input is empty, `--scaffold-only`, one or more capability names, or `--validate <rule ids>`.

## Rules

- **Write nothing before the user approves the map.** A request to bootstrap is not approval of the map: propose it first. If you cannot ask the user, show the map and stop.
- Do not change code, tests, `specs/NNN-*` or agent instruction files, and do not commit.
- Take rules only from code and tests you read. Each rule is one observable sentence, with its value.
- Never write `[inferred]` by hand. The operation adds it.
- If the code looks wrong, record what it does and report the suspicion separately. Approving a different behaviour is a person's decision.

## Steps

If the input starts with `--validate`, go to **Validating rules**.

1. Run `{SCRIPT} status`. If `journal_pending` is true, run `{SCRIPT} recover` and start again; if it answers `manual`, show `edited_since` and stop.
2. Read the README, the entry points and the tests. Limit it to what the map needs.
3. Propose a table with `Capability`, `Covers` and `Entry point`. Names match `^[a-z][a-z0-9-]*$` and speak the language of the business, not of the code. Keep them few. Leave out what the project has already consolidated.
4. **Stop and ask which capabilities to keep or change.** Continue only when the user answers.
5. For each approved capability, run `{SCRIPT} scaffold --capability <name> --covers "<one line>"`. `planned` and `unchanged` are both fine. Report any `setup` entry that starts with `skipped`: that file for agents was left alone.
6. With `--scaffold-only`, report the map and finish. Without it, continue with the capabilities the user chose to consolidate now.
7. For each one, write `specs/_capabilities/_changes/<YYYYMMDD>-bootstrap-<capability>/capability-delta.md`:

   ```markdown
   # Bootstrap: <capability>

   ## Capability Delta
   <!-- capability-delta:v1 -->

   ### NEW-CAPABILITY <capability>
   - Covers: <the same line>

   ### INFERRED R-<name>
   - Capability: <capability>
   - From: (none)
   - To: <the rule>
   - Links: none
   ```

8. Run `{SCRIPT} review --change <record>`, then `{SCRIPT} prepare --change <record> --no-tasks`. Act on `status` as `speckit.capabilities.fold` describes.
9. In `<staging>/<capability>/implementation.md`, write one block under `## Rule Status` for each rule:

   ```markdown
   ### R-<name>
   - Observed: <what the code does, with the value you read>
   - State: conforming | unverified
   - Code: `<file>::<symbol>`
   - Tests: `<file>::<test>`
   ```

   Use `conforming` only if a test you read verifies it, and `unverified` otherwise, with `Tests: none`. Never `discrepant`: an inferred rule says what the code does, so there is nothing to differ from. `apply` rejects a symbol that does not appear in the file, so copy it from what you read. Do not invent reasons under `Decisions`.
10. Run `{SCRIPT} apply --change <record> --staged <staging> --no-tasks`. `invalid-staging`: fix the drafts and run it again. `base-changed`: start again from step 8. `busy`: try again when it finishes.
11. Run `{SCRIPT} check --mode dev --change <record>`. Report the capabilities, the rules, which are `unverified`, and any suspected bug. Remind the user that the rules stay `[inferred]` until validated.

## Validating rules

Only for rules the user names. Validating says a person approved the rule as a requirement; you cannot decide that.

1. Run `{SCRIPT} locate --capability <name>` and copy the literal `text` of each rule.
2. Write `specs/_capabilities/_changes/<YYYYMMDD>-validate-<capability>/capability-delta.md` with this block for each rule, `From` and `To` identical:

   ```markdown
   ### VALIDATED R-<name>
   - Capability: <capability>
   - From: <literal text>
   - To: <literal text>
   - Links: none
   ```

3. Continue with steps 8, 10 and 11. Do not change the `implementation.md` draft.
