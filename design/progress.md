# Progress view architecture

This document records how the progress view is built and why. For how to use it, see
[See how far a spec has come](../docs/how-to/progress.md).

## Goal

Every spec gets a page that shows the whole plan, every task, the totals, what each agent did and is
doing, and the notes on each task. It works in every integration and every script variant, with no
server and no network, and it has no off switch.

Spec Kit does not run agents, it gives them instructions. So "mandatory" cannot mean the same thing
everywhere, and the design rests on one rule:

> Totals and completion never depend on what a model chooses to do. Whatever does depend on it is
> labelled as such on the page.

## Sources of truth

| Fact | Source | Depends on the model |
| --- | --- | --- |
| Which tasks exist, and which are checked | `tasks.md` | Only through its own edits to that file |
| Which steps have run, and when | `progress.jsonl`, written by `run-step` before and after each script | No |
| In progress, blocked, failed, skipped, notes, files | `progress.jsonl`, written by the task commands | Yes |
| Which harness made a report | Observed by a hook, otherwise the project setup | No |
| Which session or subagent made a report | Observed by a hook where the harness says so, otherwise declared | Depends on the harness |

`tasks.md` wins when the two disagree. A task checked by hand shows as done with no record of who did
it. A task reported as done whose box is empty shows under "needs attention". Nothing is invented to
fill a gap.

## Pieces

| Piece | Runs where | Depends on |
| --- | --- | --- |
| `scripts/progress/engine.py` | In the project, and from the CLI | Python 3.9+ standard library |
| `scripts/progress/hook.py` | In the project, inside the event dispatcher | `os`, `sys` until it finds something to do |
| `scripts/progress/page.html`, `index.html` | In the browser, from `file://` | Nothing |
| `scripts/{bash,powershell,python}/progress.*` | In the project | A Python if one exists, and they say so if not |
| `scripts/{bash,powershell,python}/run-step.*` | In the project, at the head of each core command | The real script's result |
| `src/specify_cli/progress/` | The `specify progress` commands | The engine, loaded by path |

The engine and the hook are plain ASCII and stay compatible with Python 3.9, because a project may
have only the Python that comes with its operating system. The CLI does not reimplement them: it loads
the same file a project runs, so the two cannot drift apart.

## The log

`specs/<id>/progress.jsonl` holds one JSON object per line, and is meant to be versioned with
`merge=union`. Each line is `{"v": 1, "ts": ..., "kind": ..., ...}`.

| Kind | Written by | Holds |
| --- | --- | --- |
| `step` | `run-step` | Step name, status, harness |
| `task` | The task commands | Task id, status, actor, note, files |
| `seen` | The native event hook | Task id, status, actor as the harness reported it |

A line the reader cannot understand is counted and shown, not dropped in silence. A line from a future
version is treated the same way.

A `seen` line is not an event of its own. `read_events` merges it into the last report of the same task
and status that nothing has observed yet, and removes it from the list. A call that failed wrote no
report, so what the harness saw of it attaches to nothing. The rule for the merged actor is:

```text
harness = seen.harness or report.harness
agent   = report.agent or seen.agent
session = seen.session
source  = "observed" if seen.agent or not report.agent else "declared"
```

So a name the model gave stays as the label of an agent the harness saw, and a name no harness
confirmed stays `declared`.

Only three things are read from a harness's message: the shell command, the session and the agent id.
The rest can hold anything, including the tool's output and, on Cursor, the user's email, and none of
it reaches the log. The session is cut to 8 characters.

## Writing under a lock

Agents can run in parallel, and a task report changes two files. `spec_lock` takes an advisory lock per
spec in `.specify/progress/.lock-<hash>` (`fcntl` or `msvcrt`, so a dead process leaves nothing behind).
`check_box` changes only the bytes of the checkbox, so line endings and encoding survive. A write
replaces the file atomically, with retries on Windows, where another process may hold it open. The test
suite runs 20 real processes at once and requires that nothing is lost.

The hook takes the lock with no wait. If it is busy, whoever holds it is about to draw the page, or the
next tool call will.

## Why a report goes through a script

The model reports with `progress.sh done T011 --note ... --then T012`. A script gives a checked box and
a log line in one call under one lock, which is why it replaces the model's hand edit of `tasks.md`.
When the call fails, its message says what to do, and the model marks the box by hand and carries on:
progress never stops the work. `--then` exists because each extra call costs a turn, and it is what
makes reporting "in progress" affordable.

Measured with Sonnet 5.5 on an 8-task project, in 3 pairs with and without these instructions: all 8
boxes were checked in all 6 runs, and the instructions cost $0.0164 more per run ($0.1002 against
$0.0838). The project is tiny, so that 19.6% is an upper guess for a real one rather than a measurement
of it.

## The native event hook

Handlers run after every tool call of a session, so this path decides whether the feature is
acceptable at all. Three decisions follow from that.

**It does not go through a command template.** The plan installed `.specify/templates/commands/progress.md`
and let the dispatcher resolve it, like every other event handler. That path imports `json`, `shlex` and
`subprocess`, and starts a second process. Instead, the command name is `speckit.progress-hook.<key>`, and
the first lines of `.specify/events.py`, with only `sys` imported, recognise that prefix and run `hook.py`
in the same process. The key in the name is how the hook knows its harness, which also corrects the
harness on directories several integrations share, such as `.agents/skills`.

**It usually stops after comparing file dates.** With no `progress.` in its message and a page newer
than `tasks.md`, `progress.jsonl`, `spec.md` and `plan.md`, it returns without loading the engine. The
same date counts as older, because a coarse file system can give two writes the same date.

Measured through the real dispatcher on macOS, 200 runs of each case, twice, on a 40-task spec, with a bare
Python start taking about 35 ms on Python 3.13 and 44 ms on the Python 3.9 macOS includes:

| Case | How often | p95, Python 3.13 | p95, Python 3.9 |
| --- | --- | --- | --- |
| Nothing changed | Nearly every tool call | 54 ms | 71 ms |
| The message mentions `progress.`, so the engine loads | Each report, and reads of the log | 102 ms | 138 ms |
| Something changed, so the page is redrawn | After a change | 103 ms | 140 ms |

The target was a p95 under 150 ms, and a `matcher` or a `stop`-only hook if it was missed. All three cases
meet it, so neither was needed. Version 1.5.0 missed it on Python 3.9 in the last two, at about 153 and 156 ms
with this same measurement.

**That margin depends on what the engine imports.** `argparse` and `subprocess` load only where they are used,
and writes make their own temporary file instead of importing `tempfile`, as the three together cost a
redraw about 20 ms. `test_a_redraw_imports_nothing_it_does_not_need` keeps them out. Caching the engine's
bytecode would save 15 ms more, but it would put a binary that runs after every tool call into the project,
so it was left out while the target is met without it.

**It never raises and never prints, except one line at the start of a session.** The line is what
`session_start` adds to the model's context: the spec, its totals and the page. It never holds a note,
because a note can say anything and this reaches a model.

Hooks are on by default in the 10 integrations with native events, only on the events each one has, and
`--events false` or a YAML override takes precedence. An adapter installed from a catalog gets none: its
events can mean anything, and code that runs by itself should not assume otherwise. See
`progress_hook_defaults`.

`.specify/events.py` is declared `shared` in each integration's manifest, and is deleted only with its
last user. With the defaults, every project with two integrations that have events now relies on that.

`calls_in` finds reports by looking for the words, not the script's name, because models batch calls with
`P=...; $P done T001` or functions. Something that only looks like a report attaches to nothing, or to a
report of that very status. `for t in ...; do $P done $t` cannot be seen, and stays `configured`.

## What each harness sends

Read from each harness's published hook reference on 2026-11-06. Sample messages are in
`tests/specify_cli/progress/test_hook_payloads.py`.

| Integration | Session field | Agent field | Evidence |
| --- | --- | --- | --- |
| `claude` | `session_id` | `agent_id`, inside a subagent | Documentation, and one live session |
| `codex` | `session_id`, the parent's for a subagent | None | Documentation |
| `copilot` | `sessionId` or `session_id` | None | Documentation; arguments may arrive as text |
| `cursor-agent` | `session_id` or `conversation_id` | None | Documentation, and one live session |
| `devin` | `session_id` | None | Documentation |
| `gemini` | `session_id` | None | Documentation; the shell argument's name is inferred |
| `opencode` | `input.sessionID` | None | Partial: the arguments are documented for `tool.execute.before`, and `sessionID` is not confirmed |
| `qwen` | `session_id` | `agent_id`, inside a subagent | Documentation |
| `tabnine` | `session_id` | None | Documentation; the shell argument's name is inferred |
| `vibe` | `session_id` | None | Documentation |

Two have been captured from a live session, both on 2026-11-06.

Claude Code 2.1.303, with Sonnet 5.5 on a 4-task spec, $0.16. It sent these fields as documented, including
`agent_id` for the subagent that reported a task. All 7 reports got their session, the model repeated the
session-start line word for word, and each hook exited 0 with nothing on stderr.

Cursor CLI 2026.11.05, with its Auto model on the same spec, in print mode (`-p`). It sent `session_id` as well
as the documented `conversation_id`, with the same value, and `user_email`, which is never stored. All 8 reports
got their session, and the model repeated the session-start line word for word. `stop` did not run in that
mode, and a shell command that failed sent no `postToolUse`. The report chained after that command had not
run either, so nothing was lost, and the last report had already redrawn the page.

The other eight rest on their documentation. A harness that sends something else leaves its reports
`configured` or `declared`, and the page says which. That is the failure mode on purpose.

## MCP

`specify progress` has no MCP tool and no `_mcp.py`. Only `artifact` and `workflow` have an inventory
today, and `event`, the nearest group to this one, has neither. `design/mcp.md` says not to add `_mcp.py`
merely for symmetry. A read tool is a candidate for a later version: the engine's `status` command
already returns the data as JSON.

## Out of this version

- An MCP read tool.
- Events from subagents, as opposed to the reports they make.
- Boxes for extension commands, and for workflow runs.
- Files attributed automatically from hooks. Only `--files` records them.
- Synchronising with GitHub or Jira.
- `specify progress serve`. A page reloads itself from `file://`, so nothing needed a server.
