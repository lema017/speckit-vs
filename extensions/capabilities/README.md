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
└── _changes/20261104-fix-expiry/ # rule changes and designs made outside specify
specs/_slices/
└── login.md                      # the slices of a request that was cut, in the order to build them
```

- `spec.md` holds the approved requirement. `implementation.md` holds what was observed. If they differ, neither overwrites the other: the rule is `discrepant` and CI blocks.
- Every feature spec declares a `## Capability Delta` with `From` and `To`, literal. `fold` copies `To` to the catalog by script.
- Under the catalog, capability directories match `^[a-z][a-z0-9-]*$`, records under `_changes/` are `YYYYMMDD-slug`, and `plan.md`, `tasks.md` and `README.md` are not allowed at any depth.

## Rules designed before they are built

A rule can be approved before its code exists. A design record under `_changes/` declares it with `DESIGNED`, and `publish-design` writes it to the catalog with the `[designed]` mark:

```bash
python3 .specify/extensions/capabilities/scripts/python/capabilities.py publish-design --change specs/_capabilities/_changes/20261111-design-login
```

```markdown
- **R-login-lockout** [designed]: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos. (specs/_capabilities/_changes/20261111-design-login)
```

| Operation | Who declares it | What it does |
|---|---|---|
| `DESIGNED` | A design record, only | Adds a `[designed]` rule (`From: (none)`) or redesigns one (`From` is its current text). It never touches a built rule |
| `REMOVED` | A design record, for a `[designed]` rule | Retires it. A spec cannot: to leave a designed rule out, run `defer` (below) |
| `IMPLEMENTED` | A spec | Builds the rule as designed: `From` and `To` are both the catalog's text. `fold` publishes it with its code and tests, and the mark goes |
| `MODIFIED` | A spec | Builds the rule with another text. That is a business decision, and `clarify-context` says so |

- `delta-block --implement R-a R-b` prints the `IMPLEMENTED` blocks with the catalog's text, for a spec to copy. `context` uses it.
- A spec does not add a rule over a `[designed]` one, nor validate it.
- Before the lock exists, `review` fixes an `IMPLEMENTED` block with a copy slip, where `To` equals `From` or the catalog's text: it writes the catalog's text in both and reports `normalized`. Any other difference is a conflict.
- A design record declares only `NEW-CAPABILITY`, `DESIGNED` and `REMOVED` of `[designed]` rules. `fold` does not take it and points to `publish-design`, which writes under the same publication lock. `recover` finishes it if it was interrupted.

**States.** The index gives each capability one: `designed` when all its rules are `[designed]`, `partial` when some are, `consolidated` when none are, and `retired` when it has no rules. An older row with no rules that says `consolidated` is accepted as it is.

**Format seal.** With the first `[designed]` rule, `index.md` gets `<!-- capability-catalog: 2 -->` under its title. From 0.3.0, a script that finds a newer format stops and asks for `specify upgrade`. `check` fails when the catalog holds `[designed]` rules without the seal, and `index --rebuild` writes it. A catalog with no `[designed]` rule stays as it was.

## One spec, one slice

A spec builds one slice: one thing a person can do and check from end to end. A request that holds several is cut before the spec is written, so each spec is small enough to review, test and correct on its own.

The cut is kept in a slice map, one file per request:

```text
specs/_slices/
└── login.md        # the slices of one request, in the order to build them
```

```markdown
# Slices: login

<!-- slice-map:v1 -->

### D-login-clave Entrar con usuario y clave
- Intent: Una persona registrada entra con su correo y su clave.
- Verify: Entro con ana@ejemplo.com y su clave y veo mi cuenta. Con la clave mala veo el error.
- Depends-On: none
- Rules: R-login-lockout

### D-login-social Entrar con Google, Facebook o GitHub
- Intent: Una persona entra con un proveedor y cae en la misma cuenta.
- Verify: Entro con Google y veo la cuenta que ya tenía con ese correo.
- Depends-On: D-login-clave
- Rules: R-login-oauth-providers, R-login-one-account-per-email

## Later

- R-login-reset-expiry: espera al correo transaccional
```

- `Intent`, `Verify`, `Depends-On` and `Rules` are required, one line each. `In`, `Out`, `Kind: enabler — <reason>` and `Dropped: <reason>` are optional.
- `Verify` is what a person does and sees. A layer has no such sentence, so it is not a slice.
- A slice depends only on slices above it in its map, or on slices of another map.
- `Rules` names the `[designed]` rules the slice builds. A rule is in one slice, or under `## Later` with the reason.
- An id is never reused. A slice that will not be built keeps its block and gets `Dropped`.

A spec names its slice in its `## Slice` section, which the spec template now carries. A request that was one slice on its own says so:

```markdown
## Slice *(mandatory)*

- Slice: D-login-social
- Out: Recuperar la clave (D-login-recuperar); Crear una cuenta (D-login-registro)
```

```markdown
- Slice: standalone — Borro una campaña y ya no aparece en la lista
```

The template also asks for one user story instead of three. A spec written before 0.5.0 has no `## Slice` section and is left alone.

**The state is read, never written**, so a map cannot go stale:

| State | When |
|---|---|
| `pending` | No spec names the slice |
| `specified` | A spec names it |
| `building` | That spec has `tasks.md` |
| `delivered` | Its tasks are closed and, when the spec changes rules, its delta is folded |
| `dropped` | The block says `Dropped` |

| Subcommand | What it gives |
|---|---|
| `slices status [--map <name>]` | Every map with its slices and their state, the `next` slice of each map, the specs that are `standalone`, and the `[designed]` rules no slice builds |
| `slices show <id>` | One slice with its siblings, the state of what it depends on, its rules with their text, and the `IMPLEMENTED` blocks of exactly those rules. `aim` is the block that tells the run what to build and what other slices own. Exit code 3 when the slice already has a spec, or waits for a slice that is not delivered |
| `slices check` | Whether the maps and the specs agree. Exit code 1 when they do not. `check` includes it |

`check` fails when:

- a map has no marker, has conflict markers, or a block that is not `### D-<name> <title>` with its fields;
- a slice id is used twice;
- a slice depends on one that does not exist, was dropped, comes later in the same map, or leads back to itself;
- a slice or `## Later` names a rule the catalog never had, a rule is in two slices, or in a slice and in `## Later`;
- a spec names a slice no map defines or one that was dropped, or two specs name the same slice;
- a spec builds, with `IMPLEMENTED`, a rule that belongs to another slice.

It leaves a note for an `enabler` slice, for a `[designed]` rule of a capability the maps touch that is in no slice and not in `## Later`, and for a rule of a slice that its spec does not build.

## Hooks

| Event | Command | Writes |
|---|---|---|
| `before_specify` | `slice`, then `context` | `slice` writes a slice map, only after you approve a cut. `context` writes nothing. Neither creates a branch |
| `after_specify` | `review` | The delta section if missing, and its lock |
| `before_clarify` | `clarify-context` | Nothing. It tells both `clarify` and `clarify-deep` what is settled, what to ask, and what the change reaches |
| `before_plan` | `review` | The lock, only after you decide |
| `after_implement` | `fold` | Catalog and lock |
| `after_converge` | `fold` | Catalog and lock |

Prompts run hooks in install order, so install `capabilities` before `git` if you want `fold` to run before the commit offer.

## Commands you run yourself

| Command | What it does | Writes |
|---|---|---|
| `speckit.capabilities.bootstrap` | Proposes a capability map for a project that already has code and waits for your approval. Then lists the chosen capabilities as `planned` and consolidates them through a record | The catalog, only after you approve. Rules stay `[inferred]` until you validate them with `--validate` |
| `speckit.capabilities.slice` | Cuts a request, or the `[designed]` rules of a capability, into slices of one spec each, and waits for your approval. With a slice id or `next`, it says what that slice builds and what other slices own | A slice map under `specs/_slices/`, only after you approve |
| `speckit.capabilities.locate` | Answers where a behaviour lives, which change set it and which tests cover it, from the catalog first. Says when part of the answer comes from the code | Nothing of yours. The graph leaves its own untracked files (see below) |

The script has subcommands for them: `scaffold --capability <name> --covers "<one line>"` and `locate [--capability <name>]`. `clarify-context [--change <dir>]` gives the hook the feature, its parsed delta and every capability, and ends with exit code 0 when there is no feature, because `clarify` reports that itself.

## Two branches on one capability

When two branches change the same capability, git merges the catalog's files line by line. The result can have conflict markers, or be clean and still be wrong, for example with two rows for one capability in the index. `review`, `prepare`, `fold` and `check` stop at the markers. You never resolve the catalog by hand: `rebase` builds it again for one change.

```bash
python3 .specify/extensions/capabilities/scripts/python/capabilities.py rebase --change specs/002-oauth
```

- **Sides.** During a merge, `HEAD` and `MERGE_HEAD`; after a merge commit, its two parents; otherwise `HEAD` and the base. The branch is the side that holds the change's document. The base is `--onto <ref>`, or `base_branch` in the config, or `main`.
- **What it builds.** It starts from the base's catalog files and applies this change's delta on top. From the branch it takes what this change wrote in `implementation.md`: Rule Status, Retirement Evidence, Approach, Decisions and Anchors. It never reads the catalog from the working tree, so it does not matter how git left it.
- **When the base changed a rule.** It stops with exit code 3, both texts and the choices for each rule. Run it again with one per rule:

| Choice | What happens |
|---|---|
| `--adopt R-x` | Only when the base redesigned a `[designed]` rule. The entry becomes `IMPLEMENTED` of the base's text, and the rule stays `unverified` until the code does it and `fold` runs again. The `FR` links are noted, because the spec may still say the old text |
| `--keep R-x` | The entry becomes `MODIFIED` from the base's text to this change's, and a `REMOVED` retires the base's text. It is a business decision for whoever approves the product |
| `--drop R-x [--reason "…"]` | The rule leaves this change, and its links are noted as out of scope. If it was the only rule, the delta says `Capabilities: none — <reason>` |

- When the delta changes, the lock is stamped again with the same seal, and fold's observations of the rules that stay are kept.
- It does not stage anything. Run `git add specs/_capabilities <the change>` and finish the merge.
- `--keep` of a rule the base retired is refused, because retired ids are not reused. Drop it, and add a new rule with `ADDED` if the spec still needs one.

`defer --change <spec> R-a R-b [--reason "…"]` takes rules out of a spec's delta. A `[designed]` rule stays designed for a later spec. If the spec was already folded, its catalog files are built again from `merge-base(HEAD, base)`, with the working tree as the branch.

`index --rebuild` writes `index.md` again from the capability directories, after a merge left it with markers or with two rows for one capability. It keeps the first row of each, recalculates its state, drops linked rows whose directory is gone, keeps `planned` rows, adds the missing directories and the seal.

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
| 6 | Only `graph`: Graphify cannot answer, and `reason` says why. `not-installed` stops the commands that use the graph. `no-code`, `update-failed` and `read-failed` continue with the anchors and `rg` |

## The code graph

[Graphify](https://github.com/Graphify-Labs/graphify) answers where code is and what a change affects. It never decides what the requirement is. It is a dependency of `specify`, so it lives in the environment of `specify` and not on your `PATH`. The gate looks beside the real `specify` first, then on `PATH`.

`context`, `clarify-context`, `locate` and `bootstrap` use it, and stop if it is missing: they show the command to reinstall `specify` without running it. `fold` uses `touched` and `anchors`, and goes on without the graph if it does not answer. `check` does not use it.

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
| `graph anchors [--capability <name>]` | Whether each anchor of the catalog still exists: `unique`, `ambiguous`, `by-name`, `missing`. It reads each `Code` line, and each row of `## Anchors` that names a file |
| `graph touched [--onto <branch>]` | The code files the branch changed since the base, with the symbols that hold the changed lines. `fold` offers them as `Code` and `## Anchors` |

`touched` compares the working tree with the merge base, so it counts what is committed and what is not, and untracked files whole. The base is `--onto`, `base_branch` in the config, or `main`, as `rebase` reads it.

- **A changed line goes to the symbol that holds it**: the last one in its file that starts at or before that line. A symbol that starts inside added lines is listed too. The graph gives where a symbol starts and not where it ends, so a line after the end of a method lands in that method. `fold` confirms each one in the code.
- **Up to 15 symbols per file**, those with the most changed lines. `omitted` says how many were left out.
- **The file itself** stands for the lines before its first symbol, such as imports and constants.
- **`other`** lists changed files the graph does not model, such as tests and configuration. The catalog, the features and `.specify/` are never listed.
- **Without the graph** it exits with 6 and still lists the changed lines of each file.

- Every read runs `update` first, because `query` does not say when the graph is old. In a repository of 350 source files that took 2 s with no changes and 44 s after a change. If it fails, nothing is read from the old graph.
- It writes `graphify-out/`, which ignores itself, and `.graphifyignore` if you have none. No tracked file changes.
- `by-name` means the graph has no such node, but the file contains the name: Graphify does not model a Java `static` field, for instance.
- Without Graphify, `status` says so and `anchors` checks by file and name, both with exit code 0. `explain`, `affected`, `query`, `update` and `touched` exit with 6.
- In a project with no code, `update` and the reads exit with 6 and `reason: no-code`. That is not a failure.
- `update`, `explain`, `affected` and `query` attempt no connection: a test intercepts the sockets of the real tool. They do load network modules, through `graphify.security`.
- The graph leaves tests out, so the tests a change reaches come from the catalog.

Validated with the real tool on Python, Java and TypeScript projects, and with one model through `clarify-context`, in test projects of up to 126 source files.

`clarify-context` passed its scenarios, but the same model without the hook did equally well in the seven scenarios compared, because the block for agents sends it to the catalog and it searched the code on its own. Each scenario ran once, and the hook cost about 20% more and took about 1.6 times as long. It adds a step that does not depend on an instruction an agent can ignore, not a measured improvement. Other models, large repositories and long interviews were not measured. The interview's subagents do not get the report, and neither does a session after its context is compacted.

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
| Design | A `[designed]` mark no `DESIGNED` entry set, a `DESIGNED` outside a design record, a spec that retires a `[designed]` rule or leaves it `[designed]` after `IMPLEMENTED`, or `[designed]` rules without the format seal |
| Merge markers | git's conflict markers are still in the change's document or in the catalog |

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

- A branch that still has 0.2.0 does not read `[designed]`. Once the base has one, its `check` fails with `line in ## Rules is not a rule`, and `Provenance` fails on every rule built with `IMPLEMENTED`. Merging the base brings the new script and the new catalog together: merge the base into open branches after you upgrade, and keep "Require branches to be up to date".
- `rebase` rebuilds one change per capability. If the branch also folded another change into the same capabilities, it refuses with exit code 2: merge them one at a time.
- `check` takes any `spec.md` that carries the delta marker as a change, also one that git does not track yet.
- `fold` on a feature that was already delivered rewrites its lock, and `check` rejects it with the way out: restore the lock with `git checkout`, and declare a new change to change a rule. It fails closed, but `fold` does not stop you first, because it does not know the base.
- Whether a request is one slice or several is the agent's judgement, and so is keeping the spec inside its slice. `check` catches a spec that builds a designed rule of another slice; it does not catch a spec that grew.
- The state of a slice comes from the working tree. A slice whose spec is on a branch that is not merged shows as `pending` here.
- When the cut is made in the same run as `specify`, a hook that already created a branch named it from the whole request. Give `specify` a slice id and the names match.
- The `init` step of a workflow has no way to opt out of the default install. Use `specify extension remove capabilities` afterwards.

`.specify/capabilities/` is local working state and is git-ignored. Delete it only when no fold is running and `recover` reports `clean`.
