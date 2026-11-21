<!-- SPECKIT CAPABILITIES START -->
## speckit-vs

This project uses speckit-vs (https://github.com/lema017/speckit-vs), a fork of Spec Kit. It is not the original Spec Kit: the fork adds a capability catalog, slices, `converge`, the catalog fold and a map of the code in Graphify, so what you know about the original is not the whole process here. Every `/speckit-*` command of this project belongs to the fork, also those named like the original's.

Every change to what the product does ends in the catalog, on one of two paths:

- **With the fork's commands.** Once you use one of them for a change, finish its flow: `specify`; `clarify` while the spec still has `[NEEDS CLARIFICATION]` markers; `plan`; `tasks`, whose hook runs `analyze`; `implement`; then `speckit.converge` until it reports the spec converged, then `speckit.capabilities.fold`. A spec is not done, and is not merged, before its fold.
- **Without them**, such as a plan of your own carried straight into code. No spec is needed. Before you call the work done, run `speckit.capabilities.record`: it finds what the branch changed, proposes the delta, and folds it. Its delta lives in `specs/_capabilities/_changes/<YYYYMMDD>-<name>/`.

On both paths:

- The delta names every rule a person can observe that the change adds, changes or removes, not only the main one.
- The fold records the code (`Code`) and the tests of each rule and checks that code against the Graphify graph. That map is how a later change finds the code to touch. Report a rule the graph cannot place; never leave it out.
- If you hand a command to a subagent, its hooks still run: run them yourself when it is done.

## Capability catalog

Before answering where a behaviour lives or why it is the way it is, and before changing existing behaviour, read `specs/_capabilities/index.md`. If the question or the change touches a listed capability, read its `spec.md` and the `Rule Status` section of its `implementation.md`.

- `spec.md` holds the approved requirement and, in parentheses, the change that set it. `history.md` lists earlier changes.
- `Rule Status` holds what the code was observed to do, with the symbol (`Code`) and the tests (`Tests`).
- If they differ, do not rewrite the requirement to match the code: report it.
- A rule marked `[designed]` is approved and not built: do not look for it in the code and do not treat it as current behaviour.

One spec builds one slice: one thing a person can do and check from end to end. `specs/_slices/` holds the slices of a larger request, and a spec names its slice under `## Slice`. Do not widen a spec to what another slice owns.

If `specs/_product/product.md` is there, the product was designed with its owner, and its `- Language:` line names their language. Speak and write to the person in that language in every command, whatever language the command is written in.

A task that comes after the catalog fold, such as opening the pull request, a deploy or a change to production data, carries `[post-merge]` after its id in `tasks.md`. Write it that way, leave its box open, and do not do it early.
<!-- SPECKIT CAPABILITIES END -->
