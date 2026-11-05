---
description: "Give clarify the settled rules, the conflicts and the reach of a spec before its first question. Read-only."
scripts:
  py: scripts/python/capabilities.py
---

# Capability Clarify Context

Tell the interview that follows what the catalog and the code graph already know about this spec, so it does not ask what is settled and does see what the change reaches. This command writes nothing, except the graph: `graphify-out/` and, if missing, `.graphifyignore`.

## User Input

```text
$ARGUMENTS
```

## Rules

- Do not edit the spec, the delta or the catalog. Do not run `speckit.capabilities.review` or `speckit.capabilities.fold`. Do not commit. Do not install anything.
- Do not settle anything for the user. A conflict or a rule that is not confirmed is a question, never an answer.
- A rule with `inferred: true`, or with a `state` other than `conforming`, is never a settled fact. Nobody approved the first; the second does not match the code, or nobody verified it.
- Copy the text of a rule literally, whatever language it is in.
- Say where each line comes from: the catalog, the graph or the code. The graph says where code is and what connects to it, never what the requirement is.

## Steps

1. Run `{SCRIPT} graph status` from the repository root and parse its JSON. If `available` is false, **stop**: say that Graphify is part of this fork and is missing, show the `install` command from that output without running it, and say that the clarification must not continue until it is installed.
2. Run `{SCRIPT} clarify-context` and parse its JSON. If `feature` or `spec` is null, say so in one line and finish: the command that called this one reports it.
3. If `capabilities` and `planned` are both empty, say in one line that the catalog has nothing for this spec yet, and finish.
4. If `journal_pending` is true, warn that an interrupted fold can leave the catalog out of date and must be recovered with `speckit.capabilities.fold`.
5. Read the spec at `spec`. Choose the capabilities to open, as the union of:
   - those named by `capability` in `delta.entries`;
   - those whose `covers` text the spec touches, in `capabilities` and `planned`. The spec and the catalog may be in different languages. A capability in `planned` has no rules yet: say so if it is the one the spec touches;
   - those the graph reveals: run `{SCRIPT} graph query <technical English keywords from the spec>`, keep the file paths in its output, run `{SCRIPT} graph anchors`, and add the capability of each anchor whose `ref` is in one of those files. `graph query` does not work with Spanish or with a whole sentence.
6. Read the answer of each graph command. With exit code 6, `reason` says why:
   - `no-code`: there is no code to graph yet. Say it on the `Graph` line and go on without the graph.
   - `update-failed` or `read-failed`: warn visibly that the graph was not used, say so on the `Graph` line, and look for the code with `rg` instead.

   With status `not-found` or `ambiguous`, the graph adds nothing for that term: go on.
7. For each capability you chose that has rules, run `{SCRIPT} locate --capability <name>`.
8. For the rules the spec changes, including those named in `delta.entries`, run `{SCRIPT} graph affected <ref>` for each `code` anchor with `resolves: true`, up to **10 anchors in total**. If there are more, say how many you left out. If it warns that a name repeats, say the callers must be confirmed in the code. Keep what is outside the anchors of those rules. The graph leaves tests out: the tests a change reaches are the `tests` of the rule in the catalog.
9. Compare the spec with the rules, and report in this format, verbatim headings first, leaving out any section with nothing in it:

   ```text
   CAPABILITIES CLARIFY CONTEXT (read-only)
   Feature: <feature>
   Graph: <ok and the version | no-code | not used, and why>

   Settled facts: do not ask these
   - <rule id> (<capability>, <state>, <origin>): "<literal text>"

   Conflicts with approved rules: ask, never settle
   - <what the spec says, with its FR or line> against <rule id>: "<literal text>". <Whether the delta names the rule>

   Not confirmed: ask
   - <rule id> [inferred]: "<literal text>". It describes the code; nobody approved it
   - <rule id> [<state>]: the rule says "<literal text>"; observed: <observed>

   Reach beyond the delta, from the graph: confirm in the code
   - <anchor> is also used by <file:line>; <the capability that covers it, or: no capability covers it>

   To look up more
   {SCRIPT} locate --capability <name>
   {SCRIPT} graph affected <anchor>
   ```

10. Report only rules the spec touches, not everything you opened. Settled facts are answers: the interview does not ask them. Conflicts, rules not confirmed and reach beyond the delta are for the interview to ask. If an answer later changes an approved rule, do not touch its `From`: `speckit.capabilities.review` surfaces it before the plan.
