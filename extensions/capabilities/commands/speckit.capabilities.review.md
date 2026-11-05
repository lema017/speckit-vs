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

## Steps

1. Run `{SCRIPT} ensure`. It finds the feature through Spec Kit and inserts the section only if it is missing.
2. Run `{SCRIPT} review` and act on `status`:

   | Status | Exit | What to do |
   |---|---|---|
   | `stamped` | 0 | Report that the delta is sealed. Finish |
   | `unchanged` | 0 | Report that the spec matches what was sealed. Finish |
   | `invalid` | 2 | See step 3 |
   | `conflict` | 3 | The catalog does not hold the `From` the delta expects. Show `conflicts` and stop. Copy the text from the catalog only if the user confirms this change really starts from it |
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
   - `Links` must name `FR-###`, `SC-###` or `USn/ACm` keys that exist in this spec.
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
