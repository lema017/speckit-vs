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

4. Some lines say what to do next:

   | Line | Meaning | Next step |
   |---|---|---|
   | `<rule>: anchored code changed without a delta` | A file that rule is anchored to changed in this branch, and no change names the rule | Read what changed. If the rule still holds, add `### REOBSERVED <rule>` to the delta of the change that moved the code, with `- Capability:` and `- Reason:`, then `speckit.capabilities.review` and `speckit.capabilities.fold`. If the behaviour changed, that is `MODIFIED`, and the person decides it |
   | `index.md: the entry point of <capability> does not exist` | The code that row points to is gone | `{SCRIPT} index --capability <capability> --entry <path::symbol>` |
   | `<base> is N commits behind <remote>: compared with <remote>` | The local base is old, so the check used its remote | Nothing. `git fetch origin <base>:<base>` brings it up to date |
   | `mapped test … did not run, its suite did not load: <reason>` | The test is in the file, and the runner could not load the file on this machine | Fix what the reason names, and run the tests again. It is not a test that is missing |
   | `N open tasks for after the merge, marked [post-merge]` | Tasks that can only be done once the change is merged | Nothing before the merge |

5. `hard` and `notes` also hold what `{SCRIPT} slices check` finds. A line that starts with `specs/_slices/` is about a slice map, and one that starts with a spec is about its `## Slice` section or its size. A hard line means the maps and the specs disagree: a slice id used twice, a dependency that does not exist or comes later, a rule in two slices, two specs for one slice, or a spec that builds a rule of another slice. `speckit.capabilities.slice` is where a map is changed. A note that starts with `Slice size:` is a spec over the slice budget that is not delivered yet: `speckit.capabilities.size` proposes a split, or records why the spec stays as it is.

Do not fix anything from this command.
