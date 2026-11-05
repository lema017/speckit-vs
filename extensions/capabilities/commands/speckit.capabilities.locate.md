---
description: "Find where a behaviour lives, which change set it and which tests cover it. Read-only."
scripts:
  py: scripts/python/capabilities.py
---

# Capability Locate

Answer a question about existing behaviour from the catalog first. This command writes nothing, except the graph: `graphify-out/` and, if missing, `.graphifyignore`.

## User Input

```text
$ARGUMENTS
```

## Steps

1. Run `{SCRIPT} locate` from the repository root and parse its JSON. If `journal_pending` is true, warn that an interrupted fold can leave the catalog out of date.
2. From the `covers` text of each entry in `capabilities`, pick those the question touches. The question and the catalog may be in different languages. A capability in `planned` has no rules yet: say so if it is the one asked about.
3. For each one, run `{SCRIPT} locate --capability <name>` and report, for each rule the question touches:
   - its ID and literal `text`;
   - `origin`, the change that set the current text. `changes` lists every change, `retired` the rules that no longer apply;
   - `code` and `tests`;
   - `state` and `observed` when `state` is not `conforming`: the code does not match the requirement, or nobody verified it;
   - a warning when `inferred` is true: the rule describes what the code does, nobody approved it as a requirement.
4. An anchor with `resolves: false` means the catalog lags the code: the file or the symbol is gone. Say so instead of presenting it as current. The same applies to a rule with `state: null`, which has no observation.
5. If the catalog does not answer, or the question is what a change would affect, run `{SCRIPT} graph status`. If `available` is false, **stop**: say that Graphify is part of this fork and is missing, and show the `install` command from that output without running it. Otherwise:
   - For an anchor from the catalog, or a name, run `{SCRIPT} graph explain <anchor>` or `{SCRIPT} graph affected <anchor>`. If it warns that a name repeats, confirm the callers in the code.
   - For a topic, run `{SCRIPT} graph query <technical English keywords>`. It does not work with Spanish or with a whole question.
   - Report its `warnings`. With exit code 6, `not-found` or `ambiguous`, go to the next step.
6. If you still have no answer, search the code with `rg`, using technical English terms too.
7. Say explicitly which part of the answer comes from the graph or the code and not from the catalog. The graph says where code is and what connects to it, never what the requirement is.

## Do not

Write, move or delete any file yourself, install anything, run `fold`, or commit. If the catalog looks wrong, report it.
