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

You use the fork's commands as usual. The extension adds hooks to the flow:

1. **`/speckit.specify`** first decides whether the request is one slice: one thing a person can do and check from end to end. If it holds several, it proposes the cut, waits for your approval and writes the spec of one slice only (see [One spec, one slice](#one-spec-one-slice)). Then it loads the rules that slice touches, and asks the spec to declare a `## Capability Delta`:

   ```markdown
   ### MODIFIED R-session-expiry
   - Capability: login
   - From: La sesión expira tras 30 minutos de inactividad.
   - To: La sesión expira tras 15 minutos de inactividad.
   - Links: FR-001
   ```

   `From` and `To` are literal. `review` then seals the delta with a lock, and lists the requirements no rule of the delta links. For each one that sets something a person can observe, it proposes the rule and asks you.

2. **`/speckit.clarify`** and **`/speckit.clarify-deep`** first run a hook that reads the catalog and the code graph. It tells the interview which rules are settled, so it does not ask them, and what to ask: a spec that contradicts an approved rule, a rule nobody approved or that the code does not follow, and code the change reaches beyond its delta. The interview can change the spec. **`/speckit.plan`** compares the spec with the lock and shows you any change of meaning. You decide.

3. **`/speckit.tasks`** ends with the `analyze` hook, which checks that the spec, the plan and the tasks agree. The last task of `tasks.md` runs converge and then the fold.

4. **`/speckit.implement`** ends with `fold`, which copies `To` to the catalog by script and writes what the code was observed to do. If the requirement says 15 and the code still says 30, the requirement stays at 15 and the rule is `discrepant`.

   Then `/speckit.converge` compares the code with the spec until it reports converged, and the fold runs again.

5. **CI** runs `check` on the pull request. A folded change is `prepared` on the branch and `ready` only once `check` has run against this revision and its test report.

A change made without the fork's commands, such as a plan of your own carried straight into code, still ends in the catalog. It needs no spec:

1. Run `/speckit.capabilities.record`. It finds what the branch changed, and which capabilities already have rules in that code, and proposes the delta: every rule a person can observe that the change adds, changes or removes. You approve, change or drop each one.
2. It writes the delta in `specs/_capabilities/_changes/<YYYYMMDD>-<name>/capability-delta.md`, then runs `review` and the fold with that folder. The fold maps each rule to its code in the [code graph](#the-code-graph), as it does for a spec.

To compare with the commit before the work, when it was already merged, pass `--base <commit>`. `record` also lists every spec whose delta never reached the catalog, merged or not.

The block the extension writes in the agent file, such as `CLAUDE.md`, names the fork and asks the agent to take one of these two paths for every change. Two things notice when it did not:

- **The agent's `Stop` hook**, in Claude Code and Codex. When the agent is about to end its turn with a spec done and not folded, or with product code that nothing records, it sends the agent back once with what is missing. `stop_check: block` in `capabilities-config.yml` sends it back at every stop, and `off` turns it off.
- **`check`** notes the same, plus the specs merged without their fold and the rules whose code a later change cannot find.

Three things come up when a change retires a feature, or only moves code:

| What happens | What you do |
|---|---|
| A task can only be done after the fold: opening the pull request, a deploy, production data | Write `[post-merge]` after its id. It stays open and holds nothing back |
| A task says to run the fold itself | Nothing to do: it does not hold the fold, and the fold closes it |
| The change moves the code of a rule it does not change, and `check` notes `anchored code changed without a delta` | Add `### REOBSERVED <rule>` to the delta, with `- Capability:` and `- Reason:`. The fold looks at that rule again and changes nothing else |
| A capability lost rules, and its line in the index still names them | The fold lists it under `review_covers`. `index --capability <name> --covers "<one line>"` sets the new line, and `--entry <path::symbol>` where its code starts |

The [README of the extension](https://github.com/lema017/speckit-vs/blob/main/extensions/capabilities/README.md#when-a-change-retires-rules-or-only-moves-code) has the detail.

The catalog lives in the repository:

```text
specs/_capabilities/
├── index.md                      # what each capability covers
├── login/
│   ├── spec.md                   # approved rules
│   ├── implementation.md         # what the code does, its state, code and tests
│   └── history.md                # changes and retired rules, append-only
└── _changes/20261104-fix-expiry/ # rule changes and designs made outside specify
specs/_slices/
└── login.md                      # the slices of a request that was cut
```

## One spec, one slice

A spec that covers a whole area, such as "login", takes long to review and to build, and you find out late that it was not what you wanted. So one spec builds one slice: sign in with a password is one spec, sign in with a social account is another, recovering the password is a third.

Ask for the whole thing as usual:

```text
/speckit.specify Login completo: usuario y clave, redes sociales, recuperar clave y registro
```

Before any spec is written, you get the cut to approve, change, or refuse:

| Slice | What a person checks | Depends on |
|---|---|---|
| `D-login-clave` Entrar con usuario y clave | Entro con mi correo y mi clave y veo mi cuenta | none |
| `D-login-social` Entrar con Google, Facebook o GitHub | Entro con Google y veo la cuenta que ya tenía | `D-login-clave` |
| `D-login-recuperar` Recuperar la clave | Pido el enlace, cambio la clave y entro | `D-login-clave` |
| `D-login-registro` Crear una cuenta | Me registro y entro | `D-login-clave` |

With your approval the cut is saved in `specs/_slices/login.md`, and this run writes the spec of the first slice only. The spec says which slice it is and what the others own, so the interview does not ask about them and the plan does not build them. When that slice is built, `fold` tells you which one comes next:

```text
/speckit.specify next
```

Before that slice is built, `next` names the first slice that still has no spec, says which slice it waits for, and asks whether to go on.

A request that is already one slice goes straight to its spec, with one line that says so.

To build the slices of a map one after another, with a gate before each one, install and run the `sliced` workflow:

```bash
specify bundle catalog add https://raw.githubusercontent.com/lema017/speckit-vs/main/bundles/catalog.json --id fork
specify bundle add sliced
specify workflow run sliced --input map=login
```

The first command tells the project about the bundle catalog of this fork, once. The default catalog is the one of `github/spec-kit`, which does not list `sliced`.

Each round asks the project which slice comes now, waits for your approval, and runs `specify`, a spec review gate, `plan`, `tasks` and `implement` for it. It ends when every slice is delivered. If a slice is started and not delivered, the slices that depend on it wait: the run says which, and looks again when you approve.

A spec can leave points marked `[NEEDS CLARIFICATION]`, and one written from a design marks what the design left out. No step of the run answers them, and `plan` does not start on such a spec. So the run stops at a gate after `specify` and says how many there are: answer them with `/speckit-clarify` in your agent, then approve.

The spec review gate shows the size of the slice. When a slice is over its budget, after `specify` or after `tasks`, the run stops at a gate with the numbers. Approve and it goes on with the slice as it is, and records next to the spec that its size was accepted at that gate. Reject and the run stops, so you can split the slice with `/speckit.capabilities.size`.

A slice also has a size: one story, and by default at most 15 requirements, 4 rules and 25 tasks. After `specify`, before `plan` and after `tasks`, the spec is measured. Over the budget you get a proposal to split it, and you decide: split it, or go on with a reason that is recorded next to the spec. The numbers are in `capabilities-config.yml`.

**From a design.** When the rules were approved before the code (`[designed]`), as [`/speckit.studio.approve`](studio.md#approve-the-rules) leaves them, cut them the same way:

```text
/speckit.capabilities.slice login
```

Each designed rule goes to the one slice that builds it, or is left for later with a reason. `/speckit.specify D-login-clave` then builds exactly the rules of that slice, and the rest stay designed.

**From a design with screens.** A product designed with the [studio extension](studio.md#cut-the-area-into-specs) is cut by area, with `/speckit.studio.slice <area>`. The map is the same file, and each slice also names the story it builds and the screens that show it:

```markdown
- Stories: ST-1
- Screens: SCR-login, SCR-home
```

`/speckit.specify D-acceso-clave` then loads the design of that slice before it writes the spec: the story with its criteria, each screen with its elements and its states, and what was decided about the product and about the area. The clarify interview does not ask those decisions again.

To see where everything stands, with the state of each slice read from the specs:

```bash
python3 .specify/extensions/capabilities/scripts/python/capabilities.py slices status
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

It answers from the catalog first, warns when an anchor no longer exists, and says when part of the answer comes from the code. It changes none of your files; the [code graph](#the-code-graph) leaves its own, which no tracked file depends on.

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

## The code graph

[Graphify](https://github.com/Graphify-Labs/graphify) answers where code is and what a change affects. It is part of this fork: it installs with `specify`, in the environment of `specify` and not on your `PATH`, and `specify init` builds the first graph. It never decides what a requirement is.

- `context` and `clarify-context` use it to find capabilities that their `covers` text did not reveal, and `clarify-context` to show what a change reaches beyond its delta.
- `locate` uses it for what the catalog does not answer: it follows an anchor or a name, or looks around technical English keywords.
- `bootstrap` builds it first, and takes its groupings only as hints.
- `fold` uses it to list the symbols that hold the lines the change touched, as candidates for each rule's code and anchors, and then to check the anchors it wrote.
- `check` does not use it, so CI does not need it.

If Graphify is missing, these commands stop and show the command to reinstall `specify`, except `fold`, which warns and goes on without it. The agent installs nothing. A project with no code yet is reported and the command goes on, and so is a graph that cannot be built, with a visible warning and a search with `rg` instead. `specify check` reports the version and does not say the CLI is ready without it.

The first use writes `graphify-out/`, which ignores itself, and a `.graphifyignore` if you have none. No tracked file changes. Every read updates the graph first: in a repository of 350 source files that took 2 seconds with no changes and 44 seconds after a change. The graph leaves tests out, so the tests a change reaches come from the catalog.

To bring a project you already have up to date, run `specify upgrade` from its directory. It updates `specify`, then adds the extension again, which keeps your configuration, registers the new hook and brings the block in your agent file up to date. By hand, reinstall `specify` and add the extension again:

```bash
uv tool install specify-cli --force --from git+https://github.com/lema017/speckit-vs.git
```

```bash
specify extension add capabilities --force
```

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
