---
description: "Report the state of the changes on this branch and the integrity of the catalog"
scripts:
  py: scripts/python/capabilities.py
---

# Capability Check

Reports where this branch stands. It writes nothing.

## User Input

```text
$ARGUMENTS
```

## Steps

1. Run `{SCRIPT} check --mode dev --base <base>`, where `<base>` is the branch given in the input, or `main` if none was given.
2. Report `states`, then `hard`, then `notes`. Exit 1 means `hard` has failures; exit 2 means the invocation was wrong.
3. Explain what each state still needs:

   | State | Meaning | Next step |
   |---|---|---|
   | `drafted` | Valid delta, not sealed | `speckit.capabilities.review` |
   | `reviewed` | Sealed, catalog does not hold `To` | `speckit.capabilities.fold` |
   | `prepared` | Catalog holds `To` on this branch | Open the PR; only CI reports `ready` |
   | `partial` | Integrated in parts, by project option | Finish the tasks and fold |
   | `delivered` | Already on the base; its delta is a sealed record | Nothing |
   | `no-rule-change` | `Capabilities: none` with a reason | Nothing |

4. `hard` and `notes` also hold what `{SCRIPT} slices check` finds. A line that starts with `specs/_slices/` is about a slice map, and one that starts with a spec is about its `## Slice` section. A hard line means the maps and the specs disagree: a slice id used twice, a dependency that does not exist or comes later, a rule in two slices, two specs for one slice, or a spec that builds a rule of another slice. `speckit.capabilities.slice` is where a map is changed.

Do not fix anything from this command.
