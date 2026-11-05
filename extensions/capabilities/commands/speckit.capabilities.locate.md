---
description: "Find where a behaviour lives, which change set it and which tests cover it. Read-only."
scripts:
  py: scripts/python/capabilities.py locate
---

# Capability Locate

Answer a question about existing behaviour from the catalog first. This command writes nothing.

## User Input

```text
$ARGUMENTS
```

## Steps

1. Run `{SCRIPT}` from the repository root and parse its JSON. If `journal_pending` is true, warn that an interrupted fold can leave the catalog out of date.
2. From the `covers` text of each entry in `capabilities`, pick those the question touches. The question and the catalog may be in different languages. A capability in `planned` has no rules yet: say so if it is the one asked about.
3. For each one, run `{SCRIPT} --capability <name>` and report, for each rule the question touches:
   - its ID and literal `text`;
   - `origin`, the change that set the current text. `changes` lists every change, `retired` the rules that no longer apply;
   - `code` and `tests`;
   - `state` and `observed` when `state` is not `conforming`: the code does not match the requirement, or nobody verified it;
   - a warning when `inferred` is true: the rule describes what the code does, nobody approved it as a requirement.
4. An anchor with `resolves: false` means the catalog lags the code: the file or the symbol is gone. Say so instead of presenting it as current. The same applies to a rule with `state: null`, which has no observation.
5. If the catalog does not answer, search the code with `rg`, using technical English terms too, and say explicitly that this part of the answer comes from the code and not from the catalog.

## Do not

Write, move or delete any file, run `fold`, or commit. If the catalog looks wrong, report it.
