---
description: "Load the approved rules a request touches. Read-only; creates no branch."
scripts:
  py: scripts/python/capabilities.py
---

# Capability Context

Load what the catalog says about this request before the spec is written. This command is read-only.

## User Input

```text
$ARGUMENTS
```

## Rules

- Start your report with these two lines, verbatim:

  ```text
  CAPABILITIES CONTEXT (read-only)
  No branch was created. This output contains no BRANCH_NAME and no FEATURE_NUM.
  ```

- Do not create, switch or name a branch. Do not output `BRANCH_NAME` or `FEATURE_NUM`.
- Do not write any file yourself. The feature directory does not exist yet. The graph keeps its own files, `graphify-out/` and `.graphifyignore`.
- Do not install anything.
- Do not run `check-prerequisites`: before the directory exists it can return the previous feature.

## Steps

1. Run `{SCRIPT} graph status` from the repository root and parse its JSON. If `available` is false, **stop**: say that Graphify is part of this fork and is missing, and show the `install` command from that output without running it.
2. Run `{SCRIPT} status` and parse its JSON.
3. If `capabilities` is empty, say in one line that the catalog has no capabilities yet, and finish. A capability in `planned` is listed but holds no rules, so there is nothing to load from it.
4. If `journal_pending` is true, warn that an interrupted fold must be recovered with `speckit.capabilities.fold`.
5. From the `covers` text of each capability, pick those the request touches. The request and the catalog may be in different languages.
6. Add those `covers` did not reveal: run `{SCRIPT} graph query <technical English keywords from the request>`, keep the file paths in its output, run `{SCRIPT} graph anchors`, and add the capability of each anchor whose `ref` is in one of those files. `graph query` does not work with Spanish or with a whole sentence. The graph says where code is, never what the requirement is.
   - With exit code 6 and `no-code`, there is no code to graph yet: say so and go on.
   - With exit code 6 and `update-failed` or `read-failed`, warn visibly that the graph was not used and go on.
   - With status `not-found` or `ambiguous`, the graph adds nothing for that term: go on.
7. If you picked none, say so and finish.
8. For each one, run `{SCRIPT} status --capability <name>` and report:
   - the literal text of the rules the request affects, with their IDs;
   - rules whose `state` is not `conforming`, with what was observed;
   - rules marked `inferred`: they describe what the code does, nobody approved them as requirements;
   - rules marked `designed`: the business approved them and nobody built them yet. They are not current behaviour, so do not look for them in the code.
   Say which capabilities only the graph revealed.
9. Tell the next step that the spec must declare a `## Capability Delta` that names those IDs and copies their current text literally into `From`.
10. If the request builds `designed` rules, run `{SCRIPT} delta-block --implement <ids>` and hand its `text` to the next step: one `### IMPLEMENTED` block per rule, with the catalog's text in `From` and `To`. The spec replaces `FR-###` in `Links` with its own requirements and acceptance criteria, and changes nothing else in the block. A spec that builds a `designed` rule with other text declares `MODIFIED` instead, and that is a business decision.
