---
description: "Cut a request, or the designed rules of a capability, into slices of one spec each, and aim this run at one slice"
scripts:
  py: scripts/python/capabilities.py
---

# Capability Slice

One spec builds one slice: one thing a person can do and check from end to end. This command decides whether a request is one slice or several, proposes the cut, saves it when the user approves, and aims the run at one slice. It runs before `specify`, and the user can run it alone.

## User Input

```text
$ARGUMENTS
```

The input is the request given to `specify`, a slice id such as `D-login-social`, the word `next`, or the name of a capability whose designed rules are to be cut.

## Rules

- Start your report with these two lines, verbatim:

  ```text
  CAPABILITIES SLICE
  No branch was created. This output contains no BRANCH_NAME and no FEATURE_NUM.
  ```

- Do not create, switch or name a branch. Do not output `BRANCH_NAME` or `FEATURE_NUM`. Do not create the feature directory or a spec: `specify` writes one spec per run.
- **The only file you write is a slice map under `specs/_slices/`, and only after the user approves the cut.** A request is not approval of a cut: propose it first. If you cannot ask the user, show the proposal, say that nothing was saved and no spec was written, and stop.
- A map says what a slice is made of, never how far it is. `slices status` reads the state from the specs.
- Never edit or remove a slice that has a spec, and never reuse an id. A slice that will not be built gets `- Dropped: <reason>`.
- Do not run `check-prerequisites`: before the feature directory exists it can return the previous feature.
- Do not install anything and do not commit.
- Write the map in the language the user writes in. The keys stay in English.

## Steps

1. Run `{SCRIPT} slices status` from the repository root and parse its JSON. If `check.hard` is not 0, run `{SCRIPT} slices check`, show `hard` and stop: the maps and the specs disagree, and that is fixed first.
2. **The input names a slice.** With `next`, take the `next` of the map; if several maps have one, ask which. If no map has one, take the first slice whose state is `pending`: it waits for another slice, and `show` says for which. If no slice is `pending`, say that every slice has a spec, and stop. Run `{SCRIPT} slices show <id>`:

   | Status | Exit | What to do |
   |---|---|---|
   | `ok` | 0 | Go to step 6 |
   | `has-spec` | 3 | The slice already has the spec at `slice.spec`. Say so and stop: that spec is the place to change it |
   | `blocked` | 3 | `slice.waiting_for` lists slices it depends on that are not delivered. Say so and ask whether to go on. If you cannot ask, stop |
   | `invalid` | 2 | Show `errors` and stop |

3. **The input is the name of a capability** that has rules in `unassigned_designed`: go to **Cutting designed rules**.
4. **The input is a request.** If one `pending` slice of a map has the same outcome, say which and take it as in step 2. If you are not sure it is the same, ask.
5. **Judge the request.** List the different things a person could do and check when the work is done. The request is one slice when all of this holds:
   - one actor reaches one outcome: "after this, *who* can *do what*, and I check it by *how*", with no "and" that joins two outcomes;
   - there is one way in, with only the errors of that way;
   - it can be shown working on its own, on top of what is already delivered, through every layer it needs;
   - it is worth showing without a second user story.

   If it is one slice, write nothing. Print this and finish:

   ```text
   SLICE FOR THIS RUN
   - Slice: standalone — <the outcome, in one sentence>
   - Out: none
   ```

   If it is more than one, go to **Proposing a cut**.
6. **Aim the run at the slice.** Print the `aim` of the answer of `slices show`, verbatim. The script wrote it, and it reads like this:

   ```text
   SLICE FOR THIS RUN
   D-login-social — Entrar con Google, Facebook o GitHub
   Build exactly this: Una persona entra con un proveedor y cae en la misma cuenta.
   A person checks it by: Entro con Google y veo la cuenta que ya tenía con ese correo.
   Other slices own this, so do not specify it, ask about it or build it: Entrar con usuario y clave (D-login-clave)
   Depends on: D-login-clave (delivered)
   Rules to build:
   - R-login-oauth-providers: Se puede entrar con Google, Facebook o GitHub.

   Write under ## Slice in the spec:
   - Slice: D-login-social
   - Out: Entrar con usuario y clave (D-login-clave)
   ```

   - If `implement.text` is not empty, print it after the block. Those are the `IMPLEMENTED` blocks for the spec's `## Capability Delta`, with the catalog's text: the spec copies them and replaces `FR-###` in `Links` with its own requirements. It builds no other `[designed]` rule.
   - Then say: what the user typed is wider than this run. For the rest of this run the feature description is this slice. The short name, the spec and the capability context come from it.
   - If a `BRANCH_NAME` already appeared in this run, say that the branch was named from the whole request before the cut.

## Proposing a cut

1. Cut along the first of these that gives slices a person can check one by one:

   | Cut by | Example |
   |---|---|
   | Operation | create, edit, cancel |
   | Path or variant | sign in with a password, sign in with a social account. Variants that share one flow and one rule stay together: three OAuth providers are one slice |
   | Rule | the basic flow first, then each rule that can be checked alone, such as a lockout |
   | Step of a workflow | each step ends in a state a person can see |
   | Actor or interface | what the customer does, what the administrator does |

2. These are not slices: a layer ("the backend of login", "the tables"), "tests for X", "error handling for X", and work that leaves nothing a person can check.
3. Shared foundations, such as accounts or a session, are not a slice of their own: the first slice carries the minimum it needs. Only when nothing a person can check fits without them, propose one slice with `- Kind: enabler — <why nothing smaller can be checked>` and say so. At most one in a map.
4. Order the slices. The first is the smallest one that works end to end. A slice depends only on slices above it.
5. For each `[designed]` rule the request touches, name it in the `Rules` of the one slice that builds it. Run `{SCRIPT} status`, and `{SCRIPT} status --capability <name>` for the capabilities the request touches, to read the rules and their text. A designed rule that waits goes under `## Later` with the reason.
6. Show the proposal as a table with the id, the slice, what a person checks, what it depends on and its rules. Then **stop and ask**: approve the cut, change it, or build everything in one spec.
   - With "everything in one spec", write nothing. Print the `standalone` block of step 5 with the outcome of the whole request, say that the user chose one spec for all of it, and finish.
7. With approval, write `specs/_slices/<name>.md`. `<name>` is the subject of the request in lowercase letters, digits and dashes. If the file exists, add the new slices under the ones it has.

   ```markdown
   # Slices: login

   <!-- slice-map:v1 -->

   Request: Login completo: usuario y clave, redes sociales, recuperar clave y registro.

   ### D-login-clave Entrar con usuario y clave
   - Intent: Una persona registrada entra con su correo y su clave.
   - In: formulario; validar credenciales; sesión iniciada; error genérico
   - Out: redes sociales (D-login-social); recuperar clave (D-login-recuperar)
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

   - An id is `D-<map name>-<short name>`, in lowercase letters, digits and dashes.
   - `Intent`, `Verify`, `Depends-On` and `Rules` are required, each on one line. `Depends-On` and `Rules` take ids separated by commas, or `none`.
   - `Verify` is what a person does and sees. If you cannot write it, it is not a slice.
   - `In` and `Out` are optional. `Out` names what a reader could expect here and another slice builds.
8. Run `{SCRIPT} slices check`. If `hard` is not empty, fix the map and run it again. Report each of `notes`.
9. If `specify` started this command, go to step 2 with the first slice, or with the one the user chose. If the user ran it alone, report the path of the map and its slices, and say that `specify` with a slice id, or with `next`, writes the spec of one slice.

## Cutting designed rules

1. Run `{SCRIPT} status --capability <name>`. The rules marked `designed` are approved and not built.
2. Give each one to a slice. Start from one rule per slice, and put together only rules that cannot be checked apart. Every designed rule ends in exactly one slice or under `## Later`.
3. A rule cannot be in two slices. If two slices each need part of it, propose a design record that replaces it with one rule per slice. Changing the text of an approved rule is a business decision: show the texts and wait for approval. The record is published with `{SCRIPT} publish-design --change <record>` before the map names the new ids.
4. Go on with **Proposing a cut** from its step 3.
