# Capability Catalog

Lets a new session find out, without being told, what behaviour is in force, which change set it, where it is implemented and which tests cover it.

```bash
specify extension add capabilities
```

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

## What CI enforces

```bash
python3 .specify/extensions/capabilities/scripts/python/capabilities.py check --mode ci --base origin/main --report junit.xml
```

In a merge queue, add `--combined`: a changed anchored file is then revalidated by the mapped tests of that commit, and the output lists `revalidated`.

| Check | Fails when |
|---|---|
| Delta applied | The catalog does not say `To` |
| Base | The base does not say `From` (two incompatible branches) |
| Reverse | A catalog rule changed without an authorizing delta in this change |
| Provenance | A rule's tag does not point to a delta that sets that text |
| Sealed record | The delta or lock of a delivered change was edited, or the document removed |
| History | A row of the base was removed or edited, or a new row matches no delta |
| Evidence | A rule is not `conforming`, or its mapped tests did not pass in this run's report |
| Retirement | A retired rule has no evidence (see below) |
| Discovery | A new `spec.md` under `feature_roots`, or with `FR-###` lines anywhere, has no delta |

**Retiring a rule.** With `Replaced-By: R-x`, `R-x` must exist, be `conforming` and pass its tests. With `Replaced-By: none`, `implementation.md` needs a `## Retirement Evidence` block with at least one passing test that proves the behaviour is gone. `discrepant` there means it is still present, and blocks.

**Test references.** `path::[Class::]name`, matched to JUnit `classname` and `name`. All variants of a parametrized test must pass, and skipped does not count as passed. This mapping has been validated with `pytest` only.

## What you must configure

`ci/capabilities-check.yml` is an example and blocks nothing by itself. Without the last two steps, the result is only informative.

1. Copy it to `.github/workflows/` and put in your test command, with JUnit output.
2. Keep `pull_request` and `merge_group` as triggers.
3. Keep `fetch-depth: 0` and the PR head as `ref`.
4. Version `.specify/extensions/capabilities/`, so CI has the script and `feature_roots`.
5. **Mark `capabilities-check` as a required status check.**
6. **Turn on "Require branches to be up to date", or a merge queue.**

## What it cannot detect

- That `conforming` is true when the mapped test is weak.
- Conflicts of meaning between two different rules.
- Behaviour changed without a spec, in code no rule anchors, when no test breaks.
- A pull request that weakens its own check. CI runs the script, the config and the test command of the revision under review, so `check` only leaves a notice when `.specify/extensions/capabilities/` changes. Protect that directory and the workflow with code owners.

`.specify/capabilities/` is local working state and is git-ignored. Delete it only when no fold is running and `recover` reports `clean`.
