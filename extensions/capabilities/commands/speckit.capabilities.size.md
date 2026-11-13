---
description: "Measure the spec against the slice budget, and propose a split when it is over"
scripts:
  py: scripts/python/capabilities.py
---

# Capability Size

One spec builds one slice, and a slice has a size. This command measures the spec of the current feature against the slice budget of the project. When the spec is over the budget it proposes a split, and the user decides: split it, or go on and record why. It runs after `specify`, before `plan` and after `tasks`, and the user can run it alone.

## User Input

```text
$ARGUMENTS
```

## Rules

- Start your report with this line, verbatim:

  ```text
  CAPABILITIES SIZE
  ```

- **A spec is never split without the user's yes.** Until the user chooses, this command writes nothing. If you cannot ask the user, report the numbers and the split you would propose, say that nothing was changed, and finish: `check` notes the spec until it is split or its size is accepted.
- The budget is the project's decision. Do not edit `capabilities-config.yml`, and do not write `slice-budget.json` by hand: `slices accept` writes it.
- Do not make the spec fit by merging requirements, deleting scenarios or hiding text. What leaves the spec goes to another slice.
- Do not create or switch a branch. Do not install anything and do not commit.

## Steps

1. Run `{SCRIPT} slices measure` from the repository root and parse its JSON. With exit code 2, show `errors` and stop.
2. Print `summary`. With status `within`, finish. With status `accepted`, finish too: the user already accepted this size, and `accepted.reason` says why.
3. With status `over`, read the spec, and the map when `map` is not null, and propose a split for what `over` lists:
   - Name the one slice that stays in this spec: the smallest part a person can check first. Name each part that leaves, with the stories, requirements, success criteria and rules that go with it. A part that a `pending` slice of the map already owns goes back to that slice. Any other part becomes a new slice, with its title, what a person checks and what it depends on.
   - Cut as `speckit.capabilities.slice` cuts: by operation, by path or variant, by rule, by step of a workflow, by actor or interface. A layer, "tests for X" and "error handling for X" are not slices.
   - When only `tasks` is over, the cut is still by what a person can check, never by phase or by layer.
   - If nothing smaller can be checked on its own, say so and recommend going on. The first slice of a new capability often carries the rules that every later slice needs.
4. **Stop and ask**: split as proposed, change the split, or go on as it is. Going on needs the user's reason, in their words.
5. **Go on.** Run `{SCRIPT} slices accept --reason "<the user's reason>"`. It records the reason and the numbers in `slice-budget.json`, next to the spec, and changes nothing else. Report `written` and finish. If the spec later grows past those numbers, this command asks again.
6. **Split.** Do these in order: `defer` reads the delta as it is, so the delta changes before the text of the spec does.
   1. **The map.**
      - If `map` is not null, the spec builds a slice of that map. Add the new slices under the ones the map has, and narrow the `Intent`, `In`, `Out` and `Verify` of the slice that stays to what is left. A part that went back to a `pending` slice needs no new block: add to that block only what it did not say. This is the one case in which the block of a slice that has a spec is edited. Its id does not change.
      - If `standalone` is not null, write `specs/_slices/<name>.md` as `speckit.capabilities.slice` writes it, with the slice that stays first, and change the `- Slice:` line of the spec to its id.
      - A new slice depends on the slice that stays when it needs it. `Rules` names only rules that are in the catalog.
   2. **The delta.** For the rules in `## Capability Delta` that go with a slice that leaves, run `{SCRIPT} defer <ids> --reason "moved to <slice id>"`. A `[designed]` rule goes back to designed: name it in the `Rules` of the slice that builds it. A rule this spec added leaves the delta, and the spec of its slice adds it again.
   3. **The spec.** Remove the stories, requirements, success criteria, edge cases, entities and assumptions that go with the slices that leave. Keep the ids of what stays: do not renumber. Set `- Out:` under `## Slice` to the other slices of the map, each as `title (id)`. What leaves is kept in the `Intent`, `In` and `Verify` of its slice.
   4. Run `{SCRIPT} slices check`. If `hard` is not empty, fix the map or the spec and run it again.
   5. Run `{SCRIPT} slices measure` again and print `summary`. If the status is still `over`, say so and go back to step 3.
   6. If `plan.md` or `tasks.md` exist in the feature directory, they were written for the whole spec. Do not edit them: say that `plan` and `tasks` must run again for the spec that is left.
   7. The spec changed, so its delta is validated and sealed again. If `specify` or `plan` started this command, the `speckit.capabilities.review` that follows does it. Otherwise tell the user to run `speckit.capabilities.review`.
7. Report the size before and after, the slices that were added or that took a part back, with their ids, and the path of the map. Say that `specify` with a slice id, or with `next`, writes the spec of each one.
