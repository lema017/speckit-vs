---
description: "Load the approved rules a request touches. Read-only; creates no branch."
scripts:
  py: scripts/python/capabilities.py status
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
- Do not write any file. The feature directory does not exist yet.
- Do not run `check-prerequisites`: before the directory exists it can return the previous feature.

## Steps

1. Run `{SCRIPT}` from the repository root and parse its JSON.
2. If `capabilities` is empty, say in one line that the catalog has no capabilities yet, and finish.
3. If `journal_pending` is true, warn that an interrupted fold must be recovered with `speckit.capabilities.fold`.
4. From the `covers` text of each capability, pick only those the request touches. If none, say so and finish.
5. For each one, run `{SCRIPT} --capability <name>` and report:
   - the literal text of the rules the request affects, with their IDs;
   - rules whose `state` is not `conforming`, with what was observed;
   - rules marked `inferred`: they describe what the code does, nobody approved them as requirements.
6. Tell the next step that the spec must declare a `## Capability Delta` that names those IDs and copies their current text literally into `From`.
