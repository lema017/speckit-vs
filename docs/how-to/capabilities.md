# How to keep a catalog of current behaviour

Feature specs say what one change wanted, not what is true today. After a few features, finding the current session timeout means reading every spec that touched it, in order. The `capabilities` extension keeps one catalog of the rules in force, so a new session can find out what behaviour is current, which change set it, where it is implemented and which tests cover it.

## Install it

A new project gets the extension from `specify init`. Everything else is your choice:

| You want | Run |
|---|---|
| A new project without it | `specify init my-project --no-default-extensions` |
| To add it to an existing project | `specify extension add capabilities` |
| To remove it | `specify extension remove capabilities` |

Running `specify init --here --force` again never adds it, so removing it lasts.

With `--script ps` the extension is not installed unless you ask for it with `--extension capabilities`: its prompts call `python3`, and it has not been run on Windows.

## What a change looks like

You use Spec Kit as usual. The extension adds hooks to the flow:

1. **`/speckit.specify`** loads the rules the request touches before writing the spec, and asks the spec to declare a `## Capability Delta`:

   ```markdown
   ### MODIFIED R-session-expiry
   - Capability: login
   - From: La sesión expira tras 30 minutos de inactividad.
   - To: La sesión expira tras 15 minutos de inactividad.
   - Links: FR-001
   ```

   `From` and `To` are literal. `review` then seals the delta with a lock.

2. **`/speckit.clarify`** can change the spec. **`/speckit.plan`** compares the spec with the lock and shows you any change of meaning. You decide.

3. **`/speckit.implement`** ends with `fold`, which copies `To` to the catalog by script and writes what the code was observed to do. If the requirement says 15 and the code still says 30, the requirement stays at 15 and the rule is `discrepant`.

4. **CI** runs `check` on the pull request. A folded change is `prepared` on the branch and `ready` only once `check` has run against this revision and its test report.

The catalog lives in the repository:

```text
specs/_capabilities/
├── index.md                      # what each capability covers
├── login/
│   ├── spec.md                   # approved rules
│   ├── implementation.md         # what the code does, its state, code and tests
│   └── history.md                # changes and retired rules, append-only
└── _changes/20261104-fix-expiry/ # rule changes made outside specify
```

## Ask where something lives

Ask in a new session. The question and the catalog can be in different languages:

```text
Where does the session expire, which change set the current limit and which test covers it?
```

The first time the catalog is used, the extension adds a block to your agent's instructions that points to it. It is an instruction an agent can ignore, not a control. To be sure, run:

```text
/speckit.capabilities.locate where does the session expire?
```

It answers from the catalog first, warns when an anchor no longer exists, and says when part of the answer comes from the code. It changes none of your files; if you add the code graph below, the graph leaves its own untracked ones.

## Start from an existing project

```text
/speckit.capabilities.bootstrap
```

It reads the code, proposes a map of capabilities and waits for you to approve it. It writes nothing before that. Rules deduced this way are marked `[inferred]`, because nobody approved them as requirements. Validate the ones you agree with:

```text
/speckit.capabilities.bootstrap --validate R-session-expiry
```

The agent is told to mark a rule `conforming` only if a test would fail when its value changes, and `unverified` otherwise. In CI, `check` reads the result of the test mapped to a `conforming` rule in your test report, when the pull request touches that rule, and blocks if it failed or is missing. It cannot tell whether that test pins the value, so read what the agent reports.

## Make CI block the merge

Version `specs/`. If your `.gitignore` ignores it, `check` fails, because CI would have nothing to check.

The workflow in `.specify/extensions/capabilities/ci/capabilities-check.yml` is an example and blocks nothing by itself. Follow [What you must configure](https://github.com/lema017/speckit-vs/blob/main/extensions/capabilities/README.md#what-you-must-configure) in the extension's README. Without marking the check as required and turning on up-to-date branches or a merge queue, the result is only informative.

The check needs a test report. It reads what pytest, Maven Surefire, Gradle, Jest with `jest-junit` and Vitest write, and each has its own form of test reference and its own traps. See [Test references](https://github.com/lema017/speckit-vs/blob/main/extensions/capabilities/README.md#what-ci-enforces).

## Add a code graph, if you want one

[Graphify](https://github.com/Graphify-Labs/graphify) answers where code is and what a change affects. The extension works without it, never installs it, and never lets it decide what a requirement is.

```bash
uv tool install graphifyy==0.9.102
```

With it on your path, `locate` uses the graph for what the catalog does not answer: it follows an anchor or a name, or looks around technical English keywords. The first use writes `graphify-out/`, which ignores itself, and a `.graphifyignore` if you have none. No tracked file changes. Every read updates the graph first: in a repository of 350 source files that took 2 seconds with no changes and 44 seconds after a change.

## What it cannot do

- Tell whether a `conforming` rule is true when its mapped test is weak.
- Notice a value changed without a delta when no mapped test pins it.
- Check rules a pull request does not touch. It reads the report only for rules in the delta, or whose anchored files or state the pull request changes.
- Notice a module that did not run, when a test with the same path or class exists in another module.
- Stop a rule from being given up in two steps. A pull request that only records `discrepant` passes with a notice, and the next one can change that code without a delta.
- Tell whether an `[inferred]` rule is right.
- Stop a pull request from weakening its own check. Protect `.specify/extensions/capabilities/` and the workflow with code owners.
- Keep an agent from invoking its skills on its own. `--no-model-invocation` applies only to the skills of Spec Kit's core.

It has been validated with Claude Code and one model. Each agent scenario ran once. It has not been run on Windows, nor under GitHub Actions, and no model has used the graph.
