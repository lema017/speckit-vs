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
   | `merge-conflict` | 3 | A merge left conflict markers in `files`. Report `reason` and finish. Never resolve the catalog by hand: `{SCRIPT} rebase` rebuilds it |
   | `invalid` | 2 | Report the errors and finish |
   | `recover-needed` | 4 | Run `{SCRIPT} recover`, then start again. Never edit the catalog or delete the journal by hand. If it answers `manual`, show `edited_since` and stop |

2. Run `{SCRIPT} graph touched`. It updates the code graph, then lists the code files the branch changed since the base, with the symbols that hold the changed lines. Act on its exit code:

   - 0, `ok`: each symbol in `files` is a candidate for the `Code` of a rule or for a row of `## Anchors`.
     - The list says where the change is, not what it does. Decide which rule each symbol serves by reading the code, and leave out one that serves none.
     - A symbol holds the lines from where it starts to where the next one starts, so a line can land in the symbol above it. Confirm each one in the code.
     - Use only the files in `scope`. A file listed in `foreign` stays out.
     - `other` lists changed files the graph does not model, such as tests. Read them yourself for `Tests`.
     - When `omitted` is above 0, more symbols changed in that file than are listed. Read the file for the rest.
     - `found: ambiguous` means the name repeats in its file, and `class` says whose it is.
   - 6: warn that the graph was not used and say why (`reason`). Go on with `scope`. `files` still lists the changed lines.
   - 2: report the error and go on with `scope`.

3. Edit only the drafts under the `staging` directory that `prepare` reported: `<staging>/<capability>/implementation.md`. Limit what you read to `scope`. Files listed in `foreign` are not part of this change: do not use them, and report them.

4. For each rule in the delta except `REMOVED`, `IMPLEMENTED` included, write one block under `## Rule Status`:

   ```markdown
   ### R-session-expiry
   - Observed: <what the code does, with the value you read>
   - State: conforming | discrepant | unverified
   - Code: `src/auth/session.py::SessionManager`
   - Tests: `tests/auth/test_session.py::test_expiry`
   ```

   - **Read the code.** Write what it does, not what the spec asks. If the spec says 15 and the code says 30, write 30 with `State: discrepant`. Never soften it and never change the rule text.
   - Use `conforming` only if you verified it. If you could not determine it, use `unverified`.
   - `Code` is `file`, `file::Class`, `file::function` or `file::.method()`. `apply` rejects a symbol that does not appear in the file, so copy it from `graph touched` or from what you read.
   - `Tests` names tests that exercise this behaviour. At least one must fail if the value in the rule changes. A test that reads the same constant as the code keeps passing with any value, so it does not count. If no test fails when the value changes, use `State: unverified` and report it. `Tests: manual: <reason>` only if the project allows manual evidence.
   - Test references: pytest `file::[Class::]test`; JUnit `file::[Nested::]method`, or the `@DisplayName` text under Gradle, which does not report the method; Jest and Vitest `file::[describe::]title`, with each title as the file writes it, including `%d`.

5. For a `REMOVED` rule, delete its block from `## Rule Status`. If it has `Replaced-By: none`, add under `## Retirement Evidence`:

   ```markdown
   ### R-legacy-sso
   - Change: <the change path>
   - Observed: <how you verified the behaviour is gone>
   - State: conforming
   - Code: none
   - Tests: `tests/auth/test_login.py::test_sso_is_rejected`
   ```

   Use `State: discrepant` if the behaviour is still there. With a replacement rule, its own block is the evidence.

6. Update `Approach` and `Decisions` only from what the plan or research state. Do not invent reasons. A row of `Anchors` names a symbol of the change that is not the `Code` of one rule, such as an entry point or a class that holds several rules. Write its reference in backticks, its kind and what it does, as you read them in the code: `` | `src/auth/session.py::SessionManager` | class | Keeps the sessions of a user | ``.

7. Run `{SCRIPT} apply --staged <staging>`. Act on `status`:

   - `published`: continue.
   - `base-changed`, exit 3: another process changed the catalog or the inputs. Start again from step 1; your draft was written against an old version.
   - `busy`, exit 5: another process is publishing. Try again when it finishes.
   - `invalid-staging`, exit 2: fix the drafts and run `apply` again.

8. For each capability you folded, run `{SCRIPT} graph anchors --capability <capability>`. Report each anchor whose `found` is not `unique`, with the reason:

   - `by-name`: the graph does not model it, such as a constant or a field.
   - `ambiguous`: the name repeats in its file.
   - `missing`: the file or the name is not there. A `missing` row of `## Anchors` that this change wrote is a mistake in the draft: report it as one.

   With exit code 6, say that the anchors were checked by name only. This step changes nothing.

9. Run `{SCRIPT} check --mode dev --change <source>` and report the state. If a rule ends `discrepant` or `unverified` and it is not going to be fixed in this change, `{SCRIPT} defer <id>` takes it out of the delta: a `[designed]` rule goes back to designed, and the output names the requirements to mark out of scope. `prepared` means the catalog holds the requirement on this branch, even if a rule is `discrepant`. Only CI can report `ready`.

## Do not

Edit `spec.md`, `history.md` or `index.md` under the catalog by hand, touch `specs/NNN-*`, `README.md` or agent instruction files, or commit.
