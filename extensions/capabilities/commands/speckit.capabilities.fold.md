---
description: "Publish an approved delta to the catalog and record what the code does"
scripts:
  py: scripts/python/capabilities.py
---

# Capability Fold

Publishes the rule text of an approved delta to the catalog and records what the code actually does. The script copies rule text from the delta. You write only the observation.

## User Input

```text
$ARGUMENTS
```

## Steps

1. Run `{SCRIPT} prepare` and act on `status`:

   | Status | Exit | What to do |
   |---|---|---|
   | `unchanged`, `no-rule-change` | 0 | Report it and finish. Read no code |
   | `ready` | 0 | Report any `setup` entry that starts with `skipped`: that file for agents was left alone. Continue with step 2 |
   | `blocked` | 3 | Open tasks, or no `tasks.md`. Report it and finish: this hook also fires on partial implementations. Pass `--no-tasks` only for a change outside `specify` when the user asked for it |
   | `needs-review`, `conflict` | 3 | Report it and finish. Run `speckit.capabilities.review` |
   | `invalid` | 2 | Report the errors and finish |
   | `recover-needed` | 4 | Run `{SCRIPT} recover`, then start again. Never edit the catalog or delete the journal by hand. If it answers `manual`, show `edited_since` and stop |

2. Edit only the drafts under the `staging` directory that `prepare` reported: `<staging>/<capability>/implementation.md`. Limit what you read to `scope`. Files listed in `foreign` are not part of this change: do not use them, and report them.

3. For each rule in the delta except `REMOVED`, write one block under `## Rule Status`:

   ```markdown
   ### R-session-expiry
   - Observed: <what the code does, with the value you read>
   - State: conforming | discrepant | unverified
   - Code: `src/auth/session.py::SessionManager`
   - Tests: `tests/auth/test_session.py::test_expiry`
   ```

   - **Read the code.** Write what it does, not what the spec asks. If the spec says 15 and the code says 30, write 30 with `State: discrepant`. Never soften it and never change the rule text.
   - Use `conforming` only if you verified it. If you could not determine it, use `unverified`.
   - `Code` is `file`, `file::Class`, `file::function` or `file::.method()`. `apply` rejects a symbol that does not appear in the file, so copy it from what you read.
   - `Tests` names tests that exercise this behaviour. `Tests: manual: <reason>` only if the project allows manual evidence.

4. For a `REMOVED` rule, delete its block from `## Rule Status`. If it has `Replaced-By: none`, add under `## Retirement Evidence`:

   ```markdown
   ### R-legacy-sso
   - Change: <the change path>
   - Observed: <how you verified the behaviour is gone>
   - State: conforming
   - Code: none
   - Tests: `tests/auth/test_login.py::test_sso_is_rejected`
   ```

   Use `State: discrepant` if the behaviour is still there. With a replacement rule, its own block is the evidence.

5. Update `Approach`, `Decisions` and `Anchors` only from what the plan or research state. Do not invent reasons.

6. Run `{SCRIPT} apply --staged <staging>`. Act on `status`:

   - `published`: continue.
   - `base-changed`, exit 3: another process changed the catalog or the inputs. Start again from step 1; your draft was written against an old version.
   - `busy`, exit 5: another process is publishing. Try again when it finishes.
   - `invalid-staging`, exit 2: fix the drafts and run `apply` again.

7. Run `{SCRIPT} check --mode dev --change <source>` and report the state. `prepared` means the catalog holds the requirement on this branch, even if a rule is `discrepant`. Only CI can report `ready`.

## Do not

Edit `spec.md`, `history.md` or `index.md` under the catalog by hand, touch `specs/NNN-*`, `README.md` or agent instruction files, or commit.
