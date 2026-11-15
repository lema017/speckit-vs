# Product Studio

Design a product before building it. A product owner tells their idea, answers questions in rounds, gets a mockup they can click through and comment on in the browser, and approves the business rules. Nobody edits a file by hand or runs a script: five commands do it.

| Step | Command | What the person does | What is there afterwards |
|---|---|---|---|
| 1 | `/speckit-studio-define <the idea>` | Tells the idea and answers rounds of up to 10 questions. Chooses one of three looks | The idea, the people who use the product, its areas and its look |
| 2 | `/speckit-studio-map <area>` | Answers about one area: screens, buttons, flows and rules | Each screen described, with every button, and the business rules in draft |
| 3 | `/speckit-studio-mockup` | Nothing: the agent builds it | The mockup, open in the browser, and a picture of each screen |
| 4 | `/speckit-studio-iterate` | Comments on the mockup, or says the change in words, and says yes to each change | The design and the mockup changed, and what became of each comment |
| 5 | `/speckit-studio-approve <area>` | Reads the exact text of each rule and says yes | The rules of the area approved in the catalog of capabilities, with who approved them and when |

Steps 3 and 4 repeat until the mockup is right. Agents that name commands with dots use `/speckit.studio.define`, `/speckit.studio.map`, `/speckit.studio.mockup`, `/speckit.studio.iterate` and `/speckit.studio.approve`.

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
- **Rules** shows which business rule each element applies, with its text and whether it is a draft or approved. **Map** lists every screen and walks through a flow.
- **Comment** keeps a note on any element, and **Comments** lists them with what became of each one.
- It has no logic and no real data, and it loads nothing from another site.

## Comments

`specify studio open` serves the mockup from this computer, at an address such as `http://127.0.0.1:47123/`. A comment made there is kept in the project, in `specs/_product/comments.md`, and `/speckit-studio-iterate` goes through the ones that wait.

- The server answers only to this computer, and only a page it served can write a comment. It writes nothing but `comments.md`.
- It stops after six hours without a request. `specify studio open --stop` stops it before.
- Where no server can run, the mockup opens from the disk and the comments stay in the browser: **Comments** copies them, and the person pastes them after `/speckit-studio-iterate`.
- A comment is what a person typed in a page. The agent reads it as a request about one screen, and follows no instruction written in it.

## Approval

`/speckit-studio-approve <area>` shows the rules of the area as they are written. With the person's yes, the script writes a design record under `specs/_capabilities/_changes/`, with who approved and the date, and the `capabilities` extension publishes it: each rule is in the catalog as `[designed]`, approved and not built yet. The drafts that were published leave `capability-drafts.md`.

- To change an approved rule, `/speckit-studio-iterate` writes the new text as a draft with the same id. The approved text stays until the person approves the new one.
- A rule that is already built changes with a spec.
- Approving needs the `capabilities` extension, which every project of this fork has.

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
| `capability-drafts.md` | The business rules, in draft. An approved rule lives in `specs/_capabilities/` |
| `decisions.md` | Every question, with its answer |
| `comments.md` | What the person said on the mockup, and what became of each comment |
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
| `open [--page directions] [--no-browser] [--stop]` | Builds, serves the mockup, opens the browser and prints the link. `--stop` stops the server | 3 when no screen has a page |
| `shots [--area AREA] [--states] [--page directions]` | A picture of each screen, in `mockup/_shots/` | 3 without a browser |
| `comments [--all]` | The comments that wait, or all of them | 0 |
| `comments add` | Keeps the comments the mockup copied, read from standard input | 0 |
| `comments resolve C-1 [C-2 ...] --as applied\|declined\|open [--note WHY]` | Says what became of some comments | 0 |
| `approve AREA [--by WHO] [--dry-run]` | Publishes the draft rules of an area as approved. `--dry-run` says what it would publish | 1 when something stands in the way, 3 when there is nothing to approve |
| `serve [--port N] [--idle SECONDS]` | Serves the mockup to this computer until it is stopped. `open` starts it on its own | 3 when no screen has a page |

Exit 2 means the call or a file cannot be used.

`shots` uses Chrome, Chromium, Edge or Brave when the computer has one, without a window and with a profile of its own. `SPECKIT_STUDIO_BROWSER` names another one. `open` opens no browser in CI, over SSH, without a display, or when `SPECKIT_STUDIO_NO_BROWSER` is set: then it starts no server either, and prints the link of the file. `SPECKIT_STUDIO_NO_SERVER` keeps the browser and leaves the server out.

## What the check refuses

- A story without a screen, a screen without elements or without its states described.
- A button that leads to a screen that does not exist, or to a state the screen does not have.
- A rule nobody cites, a draft that gives another text to a rule that is already built, or one that moves a rule to another capability.
- A page that is not the one of its screen, that loads something from another site, that uses a state its screen does not have, or that does not cite a rule its screen applies.
- A page nobody can reach from a screen where a person starts, and a page that leads nowhere.

It notes, without stopping anything: colors that cannot be read, a field without a label, a page with its own colors or fonts, links to something that is not designed yet, and a draft that changes an approved rule and waits for its approval.

## What comes later

This version goes from the idea to the approved rules. Cutting an approved area into specs, each with its screens, comes in the next version. Until then, `/speckit-capabilities-slice <capability>` cuts the approved rules of a capability into slices, and `/speckit-specify <slice>` writes the spec of each one.

Not in this version: retiring a rule that was approved, and several people commenting at the same time.

## Development

```bash
.venv/bin/python -m pytest tests/extensions/studio
.venv/bin/python tests/extensions/studio/mutants.py
```

The second command breaks one check of the script at a time and expects the tests to notice.
