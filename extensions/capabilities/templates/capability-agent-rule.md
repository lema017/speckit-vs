<!-- SPECKIT CAPABILITIES START -->
## Capability catalog

Before answering where a behaviour lives or why it is the way it is, and before changing existing behaviour, read `specs/_capabilities/index.md`. If the question or the change touches a listed capability, read its `spec.md` and the `Rule Status` section of its `implementation.md`.

- `spec.md` holds the approved requirement and, in parentheses, the change that set it. `history.md` lists earlier changes.
- `Rule Status` holds what the code was observed to do, with the symbol (`Code`) and the tests (`Tests`).
- If they differ, do not rewrite the requirement to match the code: report it.
- A rule marked `[designed]` is approved and not built: do not look for it in the code and do not treat it as current behaviour.

If you change a rule outside a Spec Kit feature, declare its delta and run the `speckit.capabilities.fold` command.
<!-- SPECKIT CAPABILITIES END -->
