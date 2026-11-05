# Capability Catalog

Lets a new session find out, without being told, what behaviour is in force, which change set it, where it is implemented and which tests cover it.

```bash
specify extension add capabilities
```

`specify init` installs it in a new project, unless you pass `--no-default-extensions`, choose `--script ps` or an integration with no commands. A re-init never adds it, so `specify extension remove capabilities` lasts.

Disable it with `specify extension disable capabilities`. The core spec template comes back.

## What it adds to a project

```text
specs/_capabilities/
├── index.md                      # what each capability covers
├── login/
│   ├── spec.md                   # approved rules, written only by fold
│   ├── implementation.md         # what the code does, its state, code and tests
│   └── history.md                # changes and retired rules, append-only
└── _changes/20261104-fix-expiry/ # rule changes made outside specify
```

- `spec.md` holds the approved requirement. `implementation.md` holds what was observed. If they differ, neither overwrites the other: the rule is `discrepant` and CI blocks.
- Every feature spec declares a `## Capability Delta` with `From` and `To`, literal. `fold` copies `To` to the catalog by script.
- Under the catalog, capability directories match `^[a-z][a-z0-9-]*$`, records under `_changes/` are `YYYYMMDD-slug`, and `plan.md`, `tasks.md` and `README.md` are not allowed at any depth.

## Hooks

| Event | Command | Writes |
|---|---|---|
| `before_specify` | `context` | Nothing, and creates no branch |
| `after_specify` | `review` | The delta section if missing, and its lock |
| `before_plan` | `review` | The lock, only after you decide |
| `after_implement` | `fold` | Catalog and lock |
| `after_converge` | `fold` | Catalog and lock |

Prompts run hooks in install order, so install `capabilities` before `git` if you want `fold` to run before the commit offer.

## Commands you run yourself

| Command | What it does | Writes |
|---|---|---|
| `speckit.capabilities.bootstrap` | Proposes a capability map for a project that already has code and waits for your approval. Then lists the chosen capabilities as `planned` and consolidates them through a record | The catalog, only after you approve. Rules stay `[inferred]` until you validate them with `--validate` |
| `speckit.capabilities.locate` | Answers where a behaviour lives, which change set it and which tests cover it, from the catalog first. Says when part of the answer comes from the code | Nothing of yours. With Graphify installed, the graph leaves its own untracked files (see below) |

The script has two subcommands for them: `scaffold --capability <name> --covers "<one line>"` and `locate [--capability <name>]`.

## The block for agents

When `review` seals a delta, or `prepare` is `ready`, or `scaffold` lists a capability, a block between `<!-- SPECKIT CAPABILITIES START -->` and `<!-- SPECKIT CAPABILITIES END -->` is added or refreshed. It tells a session to read the catalog before answering where a behaviour lives or changing it.

- The file is the first of these: `context_files` or `context_file` in the `agent-context` configuration, the file of the integration in `.specify/init-options.json`, `AGENTS.md`.
- Everything outside the markers stays byte for byte, except the frontmatter a `.mdc` file needs (`alwaysApply`) when it has none. If the markers are unbalanced, or the file points outside the repository, the file is left alone and `setup` says so.
- Outside the Spec Kit flow this is an instruction an agent can ignore. It is not an enforcement mechanism; CI is.

## Script exit codes

`scripts/python/capabilities.py` uses the standard library only and needs Python 3.9+.

| Code | Meaning |
|---|---|
| 0 | Done |
| 1 | `check` found a failure. `check` reports project problems only with this code |
| 2 | Invalid input or bad invocation |
| 3 | A decision is needed, or the operation is blocked |
| 4 | A fold was interrupted and needs `recover` |
| 5 | Another process is publishing |
| 6 | Only `graph`: Graphify cannot answer. Use the anchors and `rg` |

## Optional: a code graph

[Graphify](https://github.com/Graphify-Labs/graphify) answers where code is and what a change affects. It never decides what the requirement is, and nothing else needs it. The extension never installs it.

```bash
uv tool install graphifyy==0.9.102
```

Everything goes through one door, with no LLM keys in its environment, and only `update`, `explain`, `affected` and `query` reach the tool:

```bash
python3 .specify/extensions/capabilities/scripts/python/capabilities.py graph status
```

| Subcommand | What it does |
|---|---|
| `graph status` | Whether it is installed, and a warning if the version is not `0.9.102` |
| `graph explain <anchor or name> [--all]` | The node and its connections |
| `graph affected <anchor> [--depth N]` | What calls or uses it. If the name repeats it warns: confirm in the code |
| `graph query <english words>` | Nodes around technical English keywords. Spanish or a whole question finds almost nothing |
| `graph anchors [--capability <name>]` | Whether each `Code` anchor of the catalog still exists: `unique`, `ambiguous`, `by-name`, `missing` |

- Every read runs `update` first, because `query` does not say when the graph is old. In a repository of 350 source files that took 2 s with no changes and 44 s after a change. If it fails, nothing is read from the old graph.
- It writes `graphify-out/`, which ignores itself, and `.graphifyignore` if you have none. No tracked file changes.
- `by-name` means the graph has no such node, but the file contains the name: Graphify does not model a Java `static` field, for instance.
- Without Graphify, `status` says so and `anchors` checks by file and name, both with exit code 0. `explain`, `affected`, `query` and `update` exit with 6.

Validated with the real tool on Python, Java and TypeScript projects. A model has not been run through this path.

## What CI enforces

```bash
python3 .specify/extensions/capabilities/scripts/python/capabilities.py check --mode ci --base origin/main --report junit.xml
```

`--report` takes files and directories, and more than one of each, for example `--report */target/surefire-reports`.

In a merge queue, add `--combined`: a changed anchored file is then revalidated by the mapped tests of that commit, and the output lists `revalidated`.

`states` reports each change on its own, so you can see which one is at fault. The exit code is what blocks: a change can say `ready` while a problem outside it returns 1.

`check` does not run tests. It reads your report, and only for the rules this pull request touches: those in its delta, those whose anchored code or test files it changes, and those whose Rule Status it changes. A pull request that touches none of them passes even if a mapped test of another rule is failing.

| Check | Fails when |
|---|---|
| Delta applied | The catalog does not say `To` |
| Base | The base does not say `From` (two incompatible branches) |
| Reverse | A catalog rule changed without an authorizing delta in this change |
| Provenance | A rule's tag does not point to a delta that sets that text |
| Sealed record | The delta or lock of a delivered change was edited, or the document removed |
| History | A row of the base was removed or edited, or a new row matches no delta |
| Evidence | A rule this change adds or modifies is not `conforming`, a rule it infers or validates is `discrepant`, or the mapped tests of a rule that says `conforming` did not pass in this run's report |
| Observation | With no delta: a rule's state changes while this change touches its anchored files, or a file anchored to a rule no longer exists, or that rule's mapped tests do not pass |
| Retirement | A retired rule has no evidence (see below) |
| Discovery | A new `spec.md` under `feature_roots`, or with `FR-###` lines anywhere, has no delta |

**Retiring a rule.** With `Replaced-By: R-x`, `R-x` must exist, be `conforming` and pass its tests. With `Replaced-By: none`, `implementation.md` needs a `## Retirement Evidence` block with at least one passing test that proves the behaviour is gone. `discrepant` there means it is still present, and blocks.

**Test references.** All variants of a parametrized test must pass, and skipped does not count as passed. A reference no report contains blocks, with `mapped test … missing`. These runners were validated with their real reports:

| Runner | Report | Reference | Watch out for |
|---|---|---|---|
| pytest | `--junitxml=junit.xml` | `tests/test_x.py::[Class::]test_y` | |
| Maven Surefire 3 | `target/surefire-reports` | `src/test/java/a/XTest.java::[Nested::]method` | |
| Gradle 8 | `build/test-results/test` | The same, or the `@DisplayName` text | It reports the display name and not the method. A `@ParameterizedTest` needs `name = "…{0}"` and a reference with that text; without it, its variants show up as `[1] x=1` and the method reads as missing. Skipped as up to date, it leaves an old report: run `cleanTest test` |
| Jest with `jest-junit` | `junit.xml` | `src/x.test.ts::[describe::]title` | Set `addFileAttribute: "true"`. Without it the report does not say which file a test is in, and every reference reads as missing |
| Vitest | `--reporter=junit --outputFile=junit.xml` | The same | |

A title with a value in it is written as in the file: `stays active at %d minutes`, `$a`, `${a}`, `{0}`. A title that is only a placeholder matches nothing and reads as missing.

A reference matches every test with that path and name, and all of them must pass. So in a monorepo, a test with the same path or class in two modules reads as one, and if one of those modules did not run, nothing notices.

A report that names no time zone, or no time, is judged by when the file was written.

## What you must configure

`ci/capabilities-check.yml` is an example and blocks nothing by itself. Without the last two steps, the result is only informative.

0. Version `specs/`. If `.gitignore` ignores it, `check` fails: CI would have nothing to check.
1. Copy it to `.github/workflows/` and put in your test command, with JUnit output.
2. Keep `pull_request` and `merge_group` as triggers.
3. Keep `fetch-depth: 0` and the PR head as `ref`.
4. Version `.specify/extensions/capabilities/`, so CI has the script and `feature_roots`.
5. **Mark `capabilities-check` as a required status check.**
6. **Turn on "Require branches to be up to date", or a merge queue.**

## What it cannot detect

- That `conforming` is true when the mapped test is weak.
- A value changed without a delta when the mapped tests do not pin it. `check` reads those tests in the report and leaves the notice `anchored code changed without a delta`; if they passed, so does `check`, even if another test of the project fails. `fold` and `bootstrap` ask the agent for a test that fails if the value changes. That is an instruction, not a control.
- That an `[inferred]` rule is right. `bootstrap` deduces it from the code. It can reach `ready` as `unverified` with no test. If it says `conforming`, its mapped tests must pass in the report, which shows the code does what those tests expect and not that the rule is what you wanted.
- A rule given up in two steps. A pull request that only records `discrepant` or `unverified` leaves a notice and passes, because recording what was seen is allowed. The next pull request can change that code without a delta, since nothing pins it any more. Read the notice in review.
- Conflicts of meaning between two different rules.
- Behaviour changed without a spec, in code no rule anchors, when no test breaks.
- A pull request that weakens its own check. CI runs the script, the config and the test command of the revision under review, so `check` only leaves a notice when `.specify/extensions/capabilities/` changes. Protect that directory and the workflow with code owners.

## Known limits

- `fold` on a feature that was already delivered rewrites its lock, and `check` rejects it with the way out: restore the lock with `git checkout`, and declare a new change to change a rule. It fails closed, but `fold` does not stop you first, because it does not know the base.
- The `init` step of a workflow has no way to opt out of the default install. Use `specify extension remove capabilities` afterwards.

`.specify/capabilities/` is local working state and is git-ignored. Delete it only when no fold is running and `recover` reports `clean`.
