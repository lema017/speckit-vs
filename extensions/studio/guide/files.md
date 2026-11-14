# The files of a design

Everything decided in the design conversation is a file under `specs/_product/`. The studio script reads them, checks that they agree, and builds the mockup from them. The keys (`- Area:`, `## Elements`) are always in English. What they say is in the language of the product.

A field is one line: `- Key: value`. Ids are written exactly as shown: `ACT-vecina`, `ST-3`, `SCR-login`, `FL-2`, `R-login-lockout`, `Q-12`. A list of ids is separated by commas, and `none` is an empty list.

| File | What it holds | Who writes it |
|---|---|---|
| `product.md` | The name, who approves, the language, where it is used most | `scaffold`, then you |
| `vision.md` | The idea in words: the problem, for whom, what is in and out, the glossary | You |
| `actors.md` | The people who use the product | You |
| `navigation.md` | The areas of the product and its flows | You |
| `story-map.md` | What each person does, and why | You |
| `screens/SCR-<name>.md` | One screen: what it shows, its elements, its states | You |
| `capability-drafts.md` | The business rules, in draft | You |
| `decisions.md` | Every question asked, with its answer | You |
| `directions.md` | The looks the person chooses from | You |
| `look-and-feel.md` | The look that was chosen | `pick`. Never by hand |
| `mockup/<page>.html` | One page per screen | You, with the kit |
| `mockup/_studio/`, `mockup/index.html`, `mockup/_shots/` | The kit, the data and the pictures | The script. Never by hand |

The product keeps no `spec.md`, no `capability-delta.md` and no requirement lines (`- **FR-001**`): those belong to a spec.

## product.md

```markdown
# Product: Oficio

<!-- studio-product:v1 -->

- Owner: Ana Pérez
- Language: es
- Device: phone
```

`scaffold` writes it. `Device` is `phone` or `desktop`: where the product is used most. The mockup opens in that size.

## vision.md

Plain text. Its first paragraph is the idea in one or two sentences: the progress page shows it. After it, these sections:

```markdown
Una app para que los vecinos se apunten a talleres del barrio, y para que quien da un taller lo publique.

## Problem

Enterarse de los talleres y apuntarse sin llamar a nadie.

## In

- Ver los talleres de la semana y apuntarse.

## Out

- Pagos y valoraciones, en esta versión.

## Glossary

- Taller: una actividad con fecha, lugar y cupo. Nunca "evento".
```

## actors.md

```markdown
### ACT-vecina Ana
- Role: vecina
- About: Vecina que se apunta a talleres
- Email: ana@ejemplo.com
```

One block per kind of person. The title after the id is a first name: the mockup greets the person with it. `Email` is optional and is sample data.

## navigation.md

```markdown
## Areas

### acceso Acceso
- Covers: Entrar, crear una cuenta y recuperar la contraseña

## Flows

### FL-2 Bloqueo por intentos fallidos
- Area: acceso
- Steps: SCR-login > SCR-login/error > SCR-login-locked
```

An area is `### <name> <title>`: the name in lowercase and hyphens, and it is what `speckit.studio.map` takes. A flow is a path through screens, at least two steps, each `SCR-<name>` or `SCR-<name>/<state>`.

## story-map.md

```markdown
### ST-1 Entrar con correo
- Area: acceso
- Actor: ACT-vecina, ACT-tallerista
- Story: Como vecina, entro con mi correo y mi contraseña para ver mis talleres.
- Criteria: Con el correo y la contraseña correctos llego a mi inicio.
- Rules: R-login-lockout
```

Every story needs a screen that names it in `- Stories:`. A story with nothing to see says `- Interface: none - <why>`.

## screens/SCR-&lt;name&gt;.md

The file is named after the id: `screens/SCR-login.md`.

```markdown
# SCR-login Entrar

- Area: acceso
- File: entrar.html
- Layout: auth
- Seen-By: anyone
- Session: none
- States: normal, error, cargando
- Stories: ST-1, ST-2
- Rules: R-login-lockout, R-login-oauth
- Entry: yes

## Purpose

Entrar a la cuenta con correo y contraseña, o con un proveedor.

## Elements

- field "Correo"
- field "Contraseña"
- button "Entrar" -> SCR-home
- button "Continuar con Google" -> SCR-home: simulado
- link "¿Olvidaste tu contraseña?" -> SCR-forgot
- link "Crea tu cuenta" -> SCR-signup

## States

- error: La contraseña no coincide. Avisa cuántos intentos quedan.
- cargando: El botón dice "Entrando…".
```

- `Area`, `File` and `States` are required. `States` always includes `normal`, and every other state is described under `## States`.
- `File` is the page of the screen, in lowercase: `entrar.html`. Two screens never share a page.
- `Seen-By` is `anyone` or the actors who see it. `Session` is `none` or `required`.
- `Entry: yes` marks a screen where a person starts. The mockup needs at least one, and every page has to be reachable from one.
- An element is `- <kind> "<label>"`, followed by `-> SCR-<name>` or `-> SCR-<name>/<state>` when it leads somewhere, and by `: <note>` for what else matters. The kind is one word: `button`, `link`, `field`, `list`, `text`, `image`, `tab`, `menu`.
- `Rules` are the rules the screen applies. Its page has to cite each one on the element that applies it.

## capability-drafts.md

```markdown
## login
- Covers: Entrar a la cuenta y protegerla

### R-login-lockout
- Text: Tras 5 intentos fallidos seguidos, la cuenta se bloquea 15 minutos.
- Example: Ana falla 5 veces a las 10:00 y puede volver a intentar a las 10:15.
```

A capability is `## <name>`: one thing the product can do, in lowercase and hyphens. A rule is one behaviour, with its number, in business words, and with an example. A story or a screen has to cite every rule. A rule that is already in `specs/_capabilities/` is approved: cite it, and never write a draft with another text for it.

## decisions.md

```markdown
## define

### Q-2 ¿El taller se paga dentro de la app?
- Round: 1
- Business: yes
- Options: a) No: es gratis o se paga en persona; b) Sí, con tarjeta
- Recommended: a
- Status: decided
- Answer: No. Es gratis o se paga en persona.
- Why: Evita pagos, devoluciones y lo legal en la primera versión.

### Q-3 ¿Hay cupo por taller?
- Round: 1
- Status: open
- Owner: Ana Pérez

## map acceso
```

A group is `## define` or `## map <area>`. `Status` is `asked` (it waits for an answer), `decided` (it needs its `Answer`) or `open` (the person does not know yet: it needs its `Owner`, who decides it). A number is used once in the whole file: the next question is the highest number plus one.

## directions.md

```markdown
# Directions

- Sample-Title: Talleres de esta semana
- Sample-Items: Pan de masa madre | Sábado a las 10:00; Arreglo de bicis | Domingo a las 11:30; Cerámica | Martes a las 18:00
- Sample-Action: Apuntarme

## A Sobria y clara

- Why: Neutra y ordenada. No distrae: lo que se ve son los talleres.
- Font: system
- Radius: 12px
- Radius-Control: 8px

### Light

- bg: #f4f5f7
- surface: #ffffff
- text: #161a21
- muted: #565e6b
- border: #d6dae1
- field-border: #8a919c
- primary: #3451c7
- primary-hover: #2a43a8
- on-primary: #ffffff
- link: #2f4bb8
- danger: #b42318
- danger-bg: #fdecea
- success: #146c37
- success-bg: #e7f4ec
- ring: #3451c7

### Dark

- bg: #0e1116
  …the same fifteen colors
```

- A direction is `## <letter> <name>`, with `- Why:` in one or two sentences the person can read, and its `### Light` and `### Dark` colors: all fifteen, each as `#rrggbb`.
- `Font` is `system` or names of fonts the computer already has, such as `Georgia, serif`. The mockup loads nothing from another site, so a font that has to be downloaded does not work.
- `Radius` is the corner of a card, `Radius-Control` the corner of a button or a field, both in px, up to three digits: `999px` makes a pill.
- The `Sample-` fields put the words of the product on the two sample screens: a title, three things with their second line, and the main action.
- `check` notes every pair of colors that cannot be read: text and `muted` on `bg` and `surface`, `link` on both, `on-primary` on `primary`, `danger` on `danger-bg` and `success` on `success-bg` need a contrast of 4.5; `field-border` on `surface` and `ring` on both need 3. Fix the colors until `check` has no note about `directions.md`.
