---
description: "Validate the capability delta and surface spec changes made after review"
scripts:
  py: scripts/python/capabilities.py
---

# Capability Review

Runs after the spec is written and again before planning. It checks that the delta is valid and shows what changed in the spec since it was sealed. It never decides for you.

## User Input

```text
$ARGUMENTS
```

**A change without a spec.** When the user input names a folder under `specs/_capabilities/_changes/`, skip step 1 and add `--change <that folder>` to every `{SCRIPT}` call.

## Steps

1. Run `{SCRIPT} ensure`. It finds the spec through the fork's scripts and inserts the section only if it is missing.
2. Run `{SCRIPT} review` and act on `status`:

   | Status | Exit | What to do |
   |---|---|---|
   | `stamped` | 0 | Report that the delta is sealed. If there is `normalized`, report each `rule` with the text it had and the catalog's text, which review wrote into its `From` and `To`: an `IMPLEMENTED` never changes a rule. Report any `setup` entry that starts with `skipped`: that file for agents was left alone. Then step 5 |
   | `unchanged` | 0 | Report that the spec matches what was sealed. Then step 5 |
   | `invalid` | 2 | See step 3 |
   | `conflict` | 3 | The catalog does not hold the `From` the delta expects. Show `conflicts` and stop. Copy the text from the catalog only if the user confirms this change really starts from it. If the base branch changed the rule, the way out is `{SCRIPT} rebase`, never an edit by hand |
   | `merge-conflict` | 3 | A merge left conflict markers in `files`. Show `reason` and stop: the catalog is never resolved by hand, `{SCRIPT} rebase` rebuilds it |
   | `changed` | 3 | See step 4 |

3. **`invalid`.** If the errors are only about the delta being empty, complete it from the spec and the catalog, and run step 2 again:

   ```markdown
   ### MODIFIED R-session-expiry
   - Capability: login
   - From: <the rule's current text, literal, from specs/_capabilities/login/spec.md>
   - To: <the new text, one sentence>
   - Links: FR-003, US1/AC2
   ```

   - `ADDED` has `From: (none)`. `REMOVED` has `To: (none)` and `Replaced-By: <rule id or none>`.
   - A rule marked `[designed]` is approved and not built. The spec builds it with `IMPLEMENTED`, with the catalog's text in both `From` and `To`; `{SCRIPT} delta-block --implement <id>` prints the block. Building it with another text is `MODIFIED`, a business decision. A spec never declares `DESIGNED`, and never retires a `[designed]` rule: to leave one out, run `{SCRIPT} defer <id>`.
   - A rule whose code this change moves, while what the rule says stays the same, is `REOBSERVED`: `- Capability:` and `- Reason: <what moved, and why the rule still holds>`, with no `From` and no `To`. The fold looks at its code again and changes nothing else. It is not a way to change a rule.
   - `Links` must name `FR-###`, `SC-###` or `USn/ACm` keys that exist in this spec. A `REOBSERVED` rule may leave them out.
   - A capability that does not exist yet needs `### NEW-CAPABILITY <name>` with `- Covers: <business language>`.
   - If no rule changes, write `Capabilities: none — <reason>`.

   For any other error, show it and stop. Never delete or rewrite `From` to make an error go away.

4. **`changed`.** The script lists which `sections` changed, which are `linked` from the delta, the `rules` those links belong to, and whether `delta_changed`. `other_text: true` means only text outside those keys changed, such as a `Clarifications` entry, and such text can change meaning too. The script does not judge meaning; you do. Compare each change with its previous text, from `git diff` or from what you read earlier in this session, and classify it. If you cannot see the previous text, treat it as a change of meaning:

   - **Cosmetic** (wording that keeps the same behaviour): report the IDs and run `{SCRIPT} review --accept`.
   - **Meaning** (a value, a condition or a behaviour changed): do not fix anything on your own. Name the changed items and the `rules`, show the difference and these options, and wait for the user:
     1. Update the delta to match, then `{SCRIPT} review --accept`.
     2. Revert the spec.
     3. Stop.

   If you cannot ask the user, stop on any change of meaning. `fold` refuses to publish until this is decided.

5. **`unlinked`** lists the requirements (`FR-###`) that no rule of the delta links. A spec whose requirements reach the catalog as one or two rules usually left rules out, and a rule left out of the delta never reaches the catalog. For each one, read it and decide:
   - **It sets something a person can observe** (a value, a limit, a message, who may do what): it belongs in the delta. Propose the entry with that requirement in its `Links`, as in step 3, and ask the user. With their yes, add it and run `{SCRIPT} review --accept`.
   - **It does not** (a log, a technical constraint, a step of the build), or a rule of the delta already holds it: say so in one line.

   Report every unlinked requirement with what you decided. If you cannot ask the user, report them and the entries you would add, and go on: the fold publishes only what the delta names. Finish.
