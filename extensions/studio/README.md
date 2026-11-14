# Product Studio

Design a product before building it. A product owner tells their idea, answers questions in rounds, and gets a mockup they can click through in the browser. Nobody edits a file by hand or runs a script: three commands do it.

| Step | Command | What the person does | What is there afterwards |
|---|---|---|---|
| 1 | `/speckit-studio-define <the idea>` | Tells the idea and answers rounds of up to 10 questions. Chooses one of three looks | The idea, the people who use the product, its areas and its look |
| 2 | `/speckit-studio-map <area>` | Answers about one area: screens, buttons, flows and rules | Each screen described, with every button, and the business rules in draft |
| 3 | `/speckit-studio-mockup` | Nothing: the agent builds it | The mockup, open in the browser, and a picture of each screen |

Agents that name commands with dots use `/speckit.studio.define`, `/speckit.studio.map` and `/speckit.studio.mockup`.

To see the mockup again at any time:

```bash
specify studio open
```

`/speckit-progress` shows how far the design is: which steps ran, how each area stands, what waits for the person and which command comes next.

## How the conversation goes

- Questions come in rounds of at most 10. Each one is a single decision, with options, a recommended one and why it matters.
- The person answers in a few words: `1 a, 2 b, 3 recommended, 4 I don't know`.
- "I don't know" is an answer: the question stays open with who decides it, and stops nothing.
- Business decisions (prices, policies, deadlines, permissions) are marked, and the agent never takes them.
- Every question and its answer is kept, so the person can stop and go on another day.

The rules the agent follows are in [guide/conversation.md](guide/conversation.md).

## What the mockup does

- One page per screen. The buttons lead where the design says.
- A bar at the bottom changes the person who is looking, the state of the screen (empty, loading, wrong), phone or window, and light or dark.
- **Rules** shows which business rule each element applies, with its text. **Map** lists every screen and walks through a flow. **Comment** keeps a note on any element.
- It has no logic and no real data, and it loads nothing from another site.

## Where the design lives

Everything decided is a Markdown file under `specs/_product/`. The format of each file is in [guide/files.md](guide/files.md), and how a page is written with the kit is in [guide/kit.md](guide/kit.md).

| File | What it holds |
|---|---|
| `product.md` | The name, who approves, the language, where it is used most |
| `vision.md` | The idea, the problem, what is in and out, the glossary |
| `actors.md` | The people who use the product |
| `navigation.md` | The areas and the flows |
| `story-map.md` | What each person does, and why |
| `screens/SCR-<name>.md` | One screen: its elements and its states |
| `capability-drafts.md` | The business rules, in draft |
| `decisions.md` | Every question, with its answer |
| `directions.md`, `look-and-feel.md` | The three looks, and the one chosen |
| `mockup/` | One page per screen. `_studio/`, `index.html` and `_shots/` are generated and not versioned |

## The script

The commands run `scripts/python/studio.py`. It uses the standard library only, runs on Python 3.9 and answers in JSON. It decides nothing: it reads the files, says whether they agree, and writes what nobody edits by hand.

| Command | What it does | Exit |
|---|---|---|
| `scaffold --name NAME [--owner WHO] [--language es] [--device phone]` | Starts `specs/_product/` and brings the kit. Never rewrites what a person wrote | 0 |
| `status` | How far the design is: the steps, each area, what waits, what comes next | 0 |
| `check` | Whether the files and the pages agree. `hard` has to be fixed; `notes` are worth knowing | 1 when `hard` is not empty |
| `build` | Writes the kit, the look and the data of the mockup | 0 |
| `directions` | Writes the page that shows the looks of `directions.md` side by side | 0 |
| `pick LETTER` | Makes one direction the look of the product | 0 |
| `open [--page directions] [--no-browser]` | Builds, opens the browser and prints the link | 3 when no screen has a page |
| `shots [--area AREA] [--states] [--page directions]` | A picture of each screen, in `mockup/_shots/` | 3 without a browser |

Exit 2 means the call or a file cannot be used.

`shots` uses Chrome, Chromium, Edge or Brave when the computer has one, without a window and with a profile of its own. `SPECKIT_STUDIO_BROWSER` names another one. `open` opens no browser in CI, over SSH, without a display, or when `SPECKIT_STUDIO_NO_BROWSER` is set.

## What the check refuses

- A story without a screen, a screen without elements or without its states described.
- A button that leads to a screen that does not exist, or to a state the screen does not have.
- A rule nobody cites, or a draft that rewrites a rule the catalog already approved.
- A page that is not the one of its screen, that loads something from another site, that uses a state its screen does not have, or that does not cite a rule its screen applies.
- A page nobody can reach from a screen where a person starts, and a page that leads nowhere.

It notes, without stopping anything: colors that cannot be read, a field without a label, a page with its own colors or fonts, and links to something that is not designed yet.

## What comes later

This version covers the conversation and the mockup. Applying comments from the mockup, approving the rules, and cutting an area into specs come in the next versions. Until then, the rules stay in draft, and a change to the mockup is asked for in the chat.

## Development

```bash
.venv/bin/python -m pytest tests/extensions/studio
.venv/bin/python tests/extensions/studio/mutants.py
```

The second command breaks one check of the script at a time and expects the tests to notice.
