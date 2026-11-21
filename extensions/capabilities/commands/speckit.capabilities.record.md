---
description: "Record in the catalog a change made without the fork's commands: find what the branch changed, propose its delta, and fold it with its code mapped in Graphify"
scripts:
  py: scripts/python/capabilities.py
---

# Capability Record

A change to what the product does ends in the catalog, also when it was made without the fork's commands: a plan of your own carried straight into code, a fix, a tweak. It needs no spec. This command finds what the branch changed, proposes the delta of rules a person can observe, and, with the user's yes, writes it, reviews it and folds it. The fold maps each rule to its code in the Graphify graph, as it does for a spec.

## User Input

```text
$ARGUMENTS
```

The input may name a base to compare with (`--base <ref>`, such as the commit before the work), or describe the change. Use the description to understand the code, never as the rule text.

## Rules

- **Write nothing before the user approves the delta.** If you cannot ask the user, show the proposal and stop: the work is not recorded yet, and say so.
- Take rules only from code and tests you read. Each rule is one sentence a person can observe, with its value. Name every rule the change adds, changes or removes, not only the main one.
- Do not change code, tests or `specs/NNN-*`, and do not commit.

## Steps

1. Run `{SCRIPT} coverage`, with `--base <ref>` when the input names one. Act on `status`:

   | Status | What to do |
   |---|---|
   | `none` | Nothing in the product changed against `base`. Report it, then step 2 |
   | `recorded` | Every change on the branch is in the catalog: report `changes`, then step 2 |
   | `unrecorded` | `pending` lists changes of the catalog on the branch that were not folded. A spec there goes on with its own flow, ending in `speckit.capabilities.fold`. A folder under `specs/_capabilities/_changes/` continues at step 6 with that folder. Then step 2 |
   | `missing` | The product changed and nothing records it. Continue with step 3 |

   Report `problems` if there are any.
2. If `unrecorded` lists specs or records, say that their rules never reached the catalog, with the `open_tasks` of each: `0` means the work is done, `null` means the spec has no `tasks.md`. For each one the user wants recorded, run `speckit.capabilities.fold` with its folder. Finish unless the status was `missing`.
3. Run `{SCRIPT} graph touched`, with `--onto <ref>` when the input named a base. It lists the symbols that hold the changed lines. With exit code 6 the graph was not used: say why (`reason`) and read the files in `code` instead.
4. Read the changed code and its tests. For each capability in `capabilities`, which already has rules anchored in those files, read its `spec.md` and the `Rule Status` of its `implementation.md`. A file in `unmapped` has no rule yet: find the capability it belongs to in `specs/_capabilities/index.md`, or propose a new one.
5. Propose the delta in a table, with `Operation`, `Rule`, `Capability`, `From` and `To`:
   - `MODIFIED` when the code now does something else than an approved rule says. Copy `From` literally from the catalog.
   - `ADDED` for a rule that is new, with `- From: (none)`. `REMOVED` for a rule the change took away, with `- To: (none)` and `- Replaced-By:`, a rule id or `none`.
   - `REOBSERVED` for a rule whose code moved and which still holds: only `- Capability:` and `- Reason:`, no `From` or `To`.
   - `NEW-CAPABILITY` first, with `- Covers:`, when the rules belong to no capability of the index.

   **Stop and ask the user to approve, change or drop each row.** Continue only with their answer. A row they drop is not recorded.
6. Write `<record>/capability-delta.md`, where `record` is the folder `coverage` proposed, or the one step 1 found:

   ```markdown
   # <what the change did, in one line>

   ## Capability Delta
   <!-- capability-delta:v1 -->

   ### ADDED R-<name>
   - Capability: <capability>
   - From: (none)
   - To: <the rule>
   - Links: none
   ```

7. Run `speckit.capabilities.review` with the folder, then `speckit.capabilities.fold` with the folder. The fold writes the `Code` and the `Tests` of each rule and checks them against the graph.
8. Run `{SCRIPT} coverage` again, with the same base. Report its `status`, which should be `recorded`, the capabilities and rules recorded, and any rule the graph could not place.
