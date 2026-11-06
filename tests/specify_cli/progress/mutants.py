"""Prove the progress tests have teeth: remove each control and require a failure.

Not collected by pytest. Run it by hand from the repository root:

    .venv/bin/python tests/specify_cli/progress/mutants.py [name ...]

Each mutant is one exact replacement in a temporary copy of the engine. A mutant that no test
catches is a control nothing is really testing, so the run exits with 1.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "scripts" / "progress"
TESTS = "tests/specify_cli/progress"
TIME_LIMIT_SECONDS = 180

MUTANTS = [
    # Reading files.
    ("link-followed-on-read", "if path.is_symlink() or not path.is_file():\n            return None, False", "if not path.is_file():\n            return None, False"),
    ("size-limit-off", "    truncated = len(raw) > limit\n    if truncated:\n        raw = raw[:limit]\n", "    truncated = False\n"),
    ("byte-order-mark-kept", 'raw.decode("utf-8-sig", errors="replace")', 'raw.decode("utf-8", errors="replace")'),
    ("bad-bytes-stop-the-read", 'raw.decode("utf-8-sig", errors="replace")', 'raw.decode("utf-8-sig")'),
    ("lines-split-on-any-mark", '_LINE_BREAK.split(text or "")', '(text or "").splitlines()'),
    ("front-matter-read", 'if lines and lines[0].strip() == "---":', "if False:"),
    ("front-matter-swallows-tasks", 'if stripped.startswith("#") or _CHECKBOX.match(lines[index]):\n                break', "if False:\n                break"),
    ("code-read-as-tasks", "        if marker:\n            fence = marker.group(1)[0]\n            continue\n", ""),
    ("any-fence-closes-code", "if marker and marker.group(1)[0] == fence:", "if marker:"),
    ("comments-read-as-tasks", 'if stripped.startswith("<!--"):', "if False:"),
    # Reading tasks.
    ("uncounted-lines-hidden", 'unparsed.append({"line": number, "text": line.strip()[:MAX_FIELD_CHARS]})', "pass"),
    ("repeated-ids-hidden", "duplicates = sorted(task_id for task_id, count in seen.items() if count > 1)", "duplicates = []"),
    ("dotted-text-is-an-id", "(?![\\w-]|\\.\\d)", "(?![\\w-])"),
    ("parallel-lost", 'parallel = any(tag.upper() == "P" for tag in tags)', "parallel = False"),
    ("line-number-lost", '"line": number,', '"line": 1,'),
    ("box-never-checked", '"checked": box.group(1) != " ",', '"checked": False,'),
    ("deep-phases-ignored", "if level == 2 or (level > 2 and _PHASE_HEADING.match(name)):", "if level == 2:"),
    ("goal-leaks-to-next-phase", "pending_name, pending_goal, section, current = name, None, None, None", "pending_name, section, current = name, None, None"),
    ("late-goal-lost", 'if current is not None and current["goal"] is None:\n                current["goal"] = goal.group(1)\n            elif current is None:', "if current is None:"),
    ("slow-heading-match", '_HEADING = re.compile(r"^(#{1,6})[ \\t]+(.+)$")', '_HEADING = re.compile(r"^(#{1,6})\\s+(.+?)\\s*#*\\s*$")'),
    ("tags-not-capped", "    for _ in range(MAX_TAGS_PER_TASK):\n        tag = _LEADING_TAG.match(remainder)\n        if not tag:\n            break\n        if task_id is None", "    while True:\n        tag = _LEADING_TAG.match(remainder)\n        if not tag:\n            break\n        if task_id is None"),
    ("template-tasks-counted", "if tasks_text and TASKS_PLACEHOLDER in tasks_text[:TEMPLATE_HEAD_CHARS]:", "if False:"),
    ("template-title-anywhere", "TASKS_PLACEHOLDER in tasks_text[:TEMPLATE_HEAD_CHARS]", "TASKS_PLACEHOLDER in tasks_text"),
    # Reading the log.
    ("future-version-read", " or version > SCHEMA_VERSION:", ":"),
    ("boolean-version-read", " or isinstance(version, bool)", ""),
    ("any-task-status", "if status not in TASK_STATUSES or not isinstance(name, str)", "if not isinstance(name, str)"),
    ("any-task-name", " or not _TASK_NAME.match(name):", ":"),
    ("any-step-status", "if status not in STEP_STATUSES or not isinstance(name, str)", "if not isinstance(name, str)"),
    ("any-step-name", " or not _STEP_NAME.match(name):", ":"),
    ("clarify-deep-apart", 'event["step"] = STEP_ALIASES.get(name, name)', 'event["step"] = name'),
    ("note-not-cut", 'note = _text_field(raw.get("note"), MAX_NOTE_CHARS)', 'note = raw.get("note") if isinstance(raw.get("note"), str) else None'),
    ("files-not-capped", "for item in files[:MAX_FILES_PER_EVENT]]", "for item in files]"),
    ("file-names-not-checked", "names = [name for name in names if name]", "names = [item for item in files]"),
    ("any-source-trusted", 'actor["source"] = source if source in ACTOR_SOURCES else "declared"', 'actor["source"] = source'),
    ("lowercase-z-rejected", 'value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value', 'value[:-1] + "+00:00" if value.endswith("Z") else value'),
    ("half-line-read", "        lines = lines[:-1]  # The last line was cut in half by the size limit.\n", "        pass\n"),
    ("broken-lines-not-counted", "        except ValueError:\n            bad += 1\n            continue", "        except ValueError:\n            continue"),
    ("not-understood-lines-not-counted", "        if event is None:\n            bad += 1\n", "        if event is None:\n            pass\n"),
    # Crossing tasks with the log.
    ("box-ignored", 'if task["checked"]:\n        status = "done"', 'if False:\n        status = "done"'),
    ("word-counts-as-done", "elif declared in OPEN_STATUSES:\n        status = declared", "elif declared:\n        status = declared"),
    ("contradiction-silent", 'if declared == "done" and not task["checked"]:', "if False:"),
    ("failure-under-a-box-silent", 'elif task["checked"] and declared in ("failed", "blocked"):', "elif False:"),
    ("old-reports-count", 'current = [e for e in own_events if not e.get("text_sha") or e["text_sha"] == sha]', "current = list(own_events)"),
    ("old-history-lost", 'older = [e for e in own_events if e.get("text_sha") and e["text_sha"] != sha]', "older = []"),
    ("note-decides-the-state", 'states = [e for e in current if e["status"] != "note"]', "states = list(current)"),
    ("first-report-decides", 'declared = states[-1]["status"] if states else None', 'declared = states[0]["status"] if states else None'),
    ("nobody-recorded-hidden", 'no_record=task["checked"] and not current,', "no_record=False,"),
    ("files-repeated", "if name not in files:", "if True:"),
    ("first-author-wins", 'actor = next((e["actor"] for e in reversed(states) if e.get("actor")), None)', 'actor = next((e["actor"] for e in states if e.get("actor")), None)'),
    ("author-from-a-note-lost", '        actor = next((e["actor"] for e in reversed(current) if e.get("actor")), None)\n', "        pass\n"),
    ("never-abandoned", "return stamp is None or now - stamp > timedelta(seconds=ABANDONED_AFTER_SECONDS)", "return False"),
    ("unknown-age-not-abandoned", "return stamp is None or now - stamp > timedelta(seconds=ABANDONED_AFTER_SECONDS)", "return stamp is not None and now - stamp > timedelta(seconds=ABANDONED_AFTER_SECONDS)"),
    ("any-status-abandoned", 'if task["status"] != "in_progress":\n        return False', 'if False:\n        return False'),
    ("stopped-task-without-a-reason", 'text = task["status"].capitalize() + (": " + last_note if last_note else ".")', 'text = task["status"].capitalize() + "."'),
    ("changed-task-not-reported", 'if task["older_history"]:', "if False:"),
    ("repeated-ids-not-reported", 'for task_id in parsed["duplicates"]:', "for task_id in []:"),
    ("uncounted-lines-not-reported", '    count = len(parsed["unparsed"])\n', "    count = 0\n"),
    ("broken-log-not-reported", "    if bad_lines:\n", "    if False:\n"),
    ("cut-tasks-not-reported", "    if tasks_truncated:\n", "    if False:\n"),
    ("cut-log-not-reported", "    if log_truncated:\n", "    if False:\n"),
    ("linked-tasks-not-reported", "    if refused_tasks:\n", "    if False:\n"),
    # The steps.
    ("constitution-template-counts", "elif _has_placeholder(constitution, CONSTITUTION_PLACEHOLDERS):", "elif False:"),
    ("spec-template-counts", "elif _has_placeholder(spec, SPEC_PLACEHOLDERS):", "elif False:"),
    ("plan-template-counts", "elif _has_placeholder(plan_text, PLAN_PLACEHOLDERS):", "elif False:"),
    ("open-questions-silent", "    if open_questions:\n        clarify", "    if False:\n        clarify"),
    ("any-report-finishes-a-step", 'finished = {name for name, event in logged.items() if event["status"] == "done"}', "finished = set(logged)"),
    ("note-overwrites-the-report", 'if event["status"] != "note":\n            logged[event["step"]] = event', 'if True:\n            logged[event["step"]] = event'),
    ("checklist-always-done", "elif checked == total:", "elif True:"),
    ("started-work-not-shown", 'elif started or "implement" in logged:', "elif False:"),
    ("all-done-not-shown", "elif done == len(every):", "elif False:"),
    ("convergence-phase-missed", 'if any("convergence" in phase["name"].lower() for phase in phases):', "if False:"),
    ("step-in-progress-hidden", 'if status == "in_progress" and step["state"] in ("pending", "skipped"):', "if False:"),
    ("failed-step-hidden", 'elif status == "failed":', "elif False:"),
    # Which specs exist.
    ("catalog-is-a-spec", ' and not path.name.startswith(("_", "."))', ""),
    ("linked-spec-read", "if path.is_dir() and not path.is_symlink() and not path.name", "if path.is_dir() and not path.name"),
    ("linked-specs-folder-read", "if specs.is_dir() and not specs.is_symlink():", "if specs.is_dir():"),
    ("feature-may-leave-the-project", " or not _inside(root, path):", ":"),
    ("linked-feature-read", "if path.is_symlink() or not path.is_dir()", "if not path.is_dir()"),
    ("project-root-as-a-feature", "if path.resolve() == root.resolve():\n        return None", "if False:\n        return None"),
    ("environment-ignored", 'raw = os.environ.get("SPECIFY_FEATURE_DIRECTORY", "")', 'raw = ""'),
    ("feature-name-ignored", 'if not raw and os.environ.get("SPECIFY_FEATURE"):', "if False:"),
    ("first-prefix-match-wins", "if len(matches) == 1:", "if matches:"),
    ("current-feature-left-out", "if current is not None and all(current.resolve() != path.resolve() for path in found):", "if False:"),
    # Drawing.
    ("angle-bracket-left-in-script", '("<", "\\\\u003c"),', ""),
    ("closing-bracket-left-in-script", '(">", "\\\\u003e"),', ""),
    ("ampersand-left-in-script", '("&", "\\\\u0026"),', ""),
    ("line-separator-left-in-script", '("\\u2028", "\\\\u2028"),', ""),
    ("paragraph-separator-left-in-script", '("\\u2029", "\\\\u2029"),', ""),
    ("data-filled-everywhere", "template.replace(DATA_PLACEHOLDER, as_script_json(data), 1)", "template.replace(DATA_PLACEHOLDER, as_script_json(data))"),
    ("template-without-a-slot-accepted", 'raise ProgressError("The page template has no place for its data.")', "pass"),
    ("output-not-ignored", '    if not ignore.exists():\n        write_atomic(ignore,', '    if False:\n        write_atomic(ignore,'),
    ("ignore-file-overwritten", "    if not ignore.exists():\n", "    if True:\n"),
    ("linked-output-followed", "if out_dir.is_symlink():", "if False:"),
    ("output-file-accepted", "if out_dir.exists() and not out_dir.is_dir():", "if False:"),
    ("linked-specify-accepted", "if not specify.is_dir() or specify.is_symlink():", "if not specify.is_dir():"),
    ("write-follows-links", "os.replace(temporary, str(path))", 'open(str(path), "wb").write(open(temporary, "rb").read())'),
    ("temporary-file-left", "        try:\n            os.unlink(temporary)\n        except OSError:\n            pass\n        raise", "        raise"),
    ("foreign-pages-removed", "if marker in stream.read(1024):", "if True:"),
    ("orphan-pages-stay", "        _remove_orphan_pages(out_dir, set(names.values()) | {INDEX_TEMPLATE})\n", "        pass\n"),
    ("one-spec-removes-pages", "    if feature is None:\n        _remove_orphan_pages", "    if True:\n        _remove_orphan_pages"),
    ("spec-can-take-the-index-name", "used = {INDEX_TEMPLATE.lower()}", "used = set()"),
    ("page-names-may-repeat", "while candidate.lower() in used:", "while False:"),
    ("page-name-not-cleaned", '_SAFE_FILE.sub("_", path.name).strip("._") or "spec"', "path.name"),
    ("document-link-not-escaped", 'return quote(os.path.relpath(str(path), str(out_dir)).replace(os.sep, "/"))', 'return os.path.relpath(str(path), str(out_dir)).replace(os.sep, "/")'),
    ("documents-without-a-budget", "min(MAX_DOC_BYTES, max(budget, 0))", "MAX_DOC_BYTES"),
    ("contracts-not-capped", "found[:MAX_CONTRACT_FILES]", "found"),
    ("binary-contracts-carried", " and path.suffix.lower() in CONTRACT_SUFFIXES", ""),
    ("linked-document-folder-read", 'if not folder.is_dir() or folder.is_symlink():\n            continue\n        found', 'if not folder.is_dir():\n            continue\n        found'),
    ("constitution-not-carried", 'paths.append((CONSTITUTION_DOCUMENT, root / ".specify" / "memory" / CONSTITUTION_DOCUMENT))', "pass"),
    # Opening.
    ("browser-opens-in-ci", 'if env.get("CI", "").strip().lower() not in ("", "0", "false"):', "if False:"),
    ("false-ci-counts", '.strip().lower() not in ("", "0", "false"):', '.strip().lower() not in ("",):'),
    ("browser-opens-over-ssh", 'if env.get("SSH_CONNECTION") or env.get("SSH_CLIENT") or env.get("SSH_TTY"):', "if False:"),
    ("browser-opens-with-no-display", 'if platform.startswith("linux") and not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):', "if False:"),
    # Reading without writing.
    ("status-writes", "    targets = [feature] if feature is not None else discover_features(root)\n    rows = []\n", "    targets = [feature] if feature is not None else discover_features(root)\n    ensure_output_dir(root)\n    rows = []\n"),
    ("status-ignores-the-chosen-spec", "targets = [feature] if feature is not None else discover_features(root)", "targets = discover_features(root)"),
    # Recording a step.
    ("constitution-written-to-a-spec", 'if name == "constitution":\n        return False\n', ""),
    ("new-spec-written-to-the-old-one", 'return not (name == "specify" and status == "in_progress")', "return True"),
    ("finished-specify-not-recorded", 'return not (name == "specify" and status == "in_progress")', 'return name != "specify"'),
    ("any-harness-accepted", "if isinstance(harness, str) and _HARNESS_NAME.match(harness):", "if harness:"),
    ("harness-pattern-too-loose", '_HARNESS_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,40}$")', '_HARNESS_NAME = re.compile(r"^.{1,60}$")'),
    ("harness-claims-to-be-observed", '"source": "configured"', '"source": "observed"'),
    ("long-note-not-cut", 'event["note"] = text[:MAX_NOTE_CHARS]', 'event["note"] = text'),
    ("blank-note-kept", 'text = note.strip() if isinstance(note, str) else ""', 'text = note if isinstance(note, str) else ""'),
    ("non-text-note-crashes", 'text = note.strip() if isinstance(note, str) else ""', 'text = note.strip() if note else ""'),
    ("no-union-merge", "    _ensure_union_merge(directory)\n    data =", "    data ="),
    ("attributes-link-followed", '    path = directory / ATTRIBUTES_NAME\n    if path.is_symlink():\n        return\n', "    path = directory / ATTRIBUTES_NAME\n"),
    ("attributes-replaced", 'write_atomic(path, existing + ("" if existing.endswith("\\n") else "\\n") + line)', "write_atomic(path, line)"),
    ("attributes-run-together", '("" if existing.endswith("\\n") else "\\n")', '""'),
    ("attributes-added-twice", "elif LOG_NAME not in existing:", "else:"),
    ("cut-line-swallows-the-next", 'if _ends_mid_line(path):\n        data = b"\\n" + data\n', ""),
    ("log-link-followed", 'path = directory / LOG_NAME\n    if path.is_symlink():\n        raise ProgressError("%s is a symbolic link. Refusing to write through it." % path)\n', "path = directory / LOG_NAME\n"),
    ("log-non-file-accepted", 'if path.exists() and not path.is_file():\n        raise ProgressError("%s is not a file." % path)\n    _ensure', "_ensure"),
    ("log-overwritten", "os.O_WRONLY | os.O_APPEND | os.O_CREAT", "os.O_WRONLY | os.O_TRUNC | os.O_CREAT"),
    ("bad-characters-stop-the-log", '+ "\\n").encode("utf-8", "replace")', '+ "\\n").encode("utf-8")'),
    ("non-ascii-escaped-in-the-log", 'json.dumps(event, ensure_ascii=False, separators=(",", ":"))', 'json.dumps(event, separators=(",", ":"))'),
    # The fact a step that only started shows.
    ("started-step-keeps-old-fact", '            step["fact"] = "started"\n', ""),
    # Opening the page.
    ("opens-every-time", "os.O_WRONLY | os.O_CREAT | os.O_EXCL", "os.O_WRONLY | os.O_CREAT"),
    ("opens-over-ssh-and-ci", "if browser_is_off(root, env) or not can_open_browser(env):", "if browser_is_off(root, env):"),
    ("off-switch-ignored", "if browser_is_off(root, env) or not can_open_browser(env):", "if not can_open_browser(env):"),
    ("env-switch-ignored", 'if env.get(BROWSER_OFF_ENV, "").strip().lower() not in ("", "0", "false"):\n        return True\n', ""),
    ("env-switch-any-value", 'if env.get(BROWSER_OFF_ENV, "").strip().lower() not in ("", "0", "false"):', "if BROWSER_OFF_ENV in env:"),
    ("project-switch-ignored", "return (root / OUTPUT_DIR / BROWSER_OFF_FILE).exists()", "return False"),
    ("cannot-turn-back-on", "    if enabled:\n        if marker.exists():\n            marker.unlink()\n    else:\n", "    if not enabled:\n"),
    ("turning-on-twice-fails", "        if marker.exists():\n            marker.unlink()\n", "        marker.unlink()\n"),
    ("mark-problem-raises", "    except OSError:\n        return False\n    try:\n        (opener", "    except ValueError:\n        return False\n    try:\n        (opener"),
    ("browser-problem-raises", "as_uri())\n    except (OSError, ValueError):\n", "as_uri())\n    except ValueError:\n"),
    ("project-steps-open-the-page", 'if belongs and feature is not None and drawn and drawn["pages"]:', 'if feature is not None and drawn and drawn["pages"]:'),
    ("no-spec-opens-the-first-page", 'if belongs and feature is not None and drawn and drawn["pages"]:', 'if belongs and drawn and drawn["pages"]:'),
    ("browser-blocks-the-command", '''subprocess.Popen(
        [sys.executable, "-I", "-c", "import sys, webbrowser; webbrowser.open(sys.argv[1])", link],''', '''subprocess.run(
        [sys.executable, "-I", "-c", "import sys, webbrowser, time; time.sleep(9); webbrowser.open(sys.argv[1])", link],'''),
    # The report.
    ("control-characters-reach-the-terminal", 'return _UNSAFE_TEXT.sub(" ", str(value))[:limit]', "return str(value)[:limit]"),
    ("long-text-not-cut", 'return _UNSAFE_TEXT.sub(" ", str(value))[:limit]', 'return _UNSAFE_TEXT.sub(" ", str(value))'),
    ("title-not-cleaned", 'lines = ["%s (%s)" % (plain_text(row["title"]), plain_text(row["id"]))]', 'lines = ["%s (%s)" % (row["title"], plain_text(row["id"]))]'),
    ("phase-not-cleaned", '"  %s: %d of %d" % (plain_text(phase["name"]), phase["done"], phase["total"])', '"  %s: %d of %d" % (phase["name"], phase["done"], phase["total"])'),
    ("task-text-not-cleaned", 'flag, who, plain_text(task["text"])))', 'flag, who, task["text"]))'),
    ("who-not-cleaned", '''who = " (%s)" % plain_text(task["who"]) if task["who"] else ""''', '''who = " (%s)" % task["who"] if task["who"] else ""'''),
    ("agent-not-cleaned", 'lines.append("  %s: %d done%s" % (plain_text(agent["label"]), agent["done"], active))', 'lines.append("  %s: %d done%s" % (agent["label"], agent["done"], active))'),
    ("report-has-no-link", '    if link:\n        lines.append("Page: " + link)\n', ""),
    ("report-hides-attention", '    if row["attention"]:\n        lines.append("Needs attention: %d, see the page" % len(row["attention"]))\n', ""),
    ("short-report-is-long", "_report(root, feature, drawn, problems, detail=False)", "_report(root, feature, drawn, problems, detail=True)"),
    ("full-report-is-short", "_report(root, feature, drawn, problems, detail=True)", "_report(root, feature, drawn, problems, detail=False)"),
    ("quiet-is-not-quiet", "    if not quiet:\n        _report(", "    if True:\n        _report("),
    ("abandoned-not-flagged", 'flag = ", possibly abandoned" if task["id"] in row["abandoned"] else ""', 'flag = ""'),
    ("output-encoding-errors-raise", 'stream.write(text.encode(encoding, "replace").decode(encoding) + "\\n")', 'stream.write(text + "\\n")'),
    ("no-specs-says-nothing", '    if not rows:\n        _say("No specs yet.")\n', ""),
    ("list-of-specs-has-no-link", '    if not rows:\n        _say("No specs yet.")\n    if link:\n        _say("Page: " + link)\n', '    if not rows:\n        _say("No specs yet.")\n'),
    ("link-always-to-the-list", 'page = drawn["pages"][0]["path"] if feature is not None and drawn["pages"] else drawn["index"]', 'page = drawn["index"]'),
    # Nothing may stop the command.
    ("log-problem-stops-the-step", '''            append_event(feature, make_step_event(name, status, harness, note))
        except (ProgressError, OSError) as exc:
            problems.append(str(exc))''', '''            append_event(feature, make_step_event(name, status, harness, note))
        except ValueError as exc:
            problems.append(str(exc))'''),
    ("draw-problem-stops-the-step", '''        return render_project(root, feature)
    except (ProgressError, OSError) as exc:
        problems.append(str(exc))
        return None''', '''        return render_project(root, feature)
    except ValueError as exc:
        problems.append(str(exc))
        return None'''),
    ("unknown-spec-stops-the-step", '''        return find_feature(root, reference) if reference else current_feature_dir(root)
    except ProgressError as exc:''', '''        return find_feature(root, reference) if reference else current_feature_dir(root)
    except ValueError as exc:'''),
    ("problems-not-reported", '''    if not quiet:
        _report(root, feature, drawn, problems, detail=False)
    for problem in problems:
        _say("progress: %s" % plain_text(problem, MAX_NOTE_CHARS), sys.stderr)
''', '''    if not quiet:
        _report(root, feature, drawn, problems, detail=False)
'''),
    ("surprise-fails-the-command", '''    except Exception as exc:
        _say("progress: unexpected %s: %s" % (type(exc).__name__, plain_text(exc, MAX_NOTE_CHARS)), sys.stderr)
        return 0
''', '''    except ValueError as exc:
        return 0
'''),
    # The command line.
    ("empty-note-accepted", 'if args.command == "step" and args.status == "note" and not (args.note or "").strip():\n        parser.error("a note needs --note")\n', ""),
    ("options-can-be-abbreviated", 'step = commands.add_parser("step", parents=[shared], allow_abbrev=False,', 'step = commands.add_parser("step", parents=[shared],'),
    ("harness-first-is-lost", 'shared.add_argument("--harness", default=argparse.SUPPRESS, help=argparse.SUPPRESS)', 'shared.add_argument("--harness", help=argparse.SUPPRESS)'),
    ("root-first-is-lost", 'shared.add_argument("--root", default=argparse.SUPPRESS, help=argparse.SUPPRESS)', 'shared.add_argument("--root", default=".", help=argparse.SUPPRESS)'),
    ("clarify-deep-refused", 'step.add_argument("name", choices=STEP_NAMES + tuple(STEP_ALIASES))', 'step.add_argument("name", choices=STEP_NAMES)'),
    ("any-step-name-accepted", 'step.add_argument("name", choices=STEP_NAMES + tuple(STEP_ALIASES))', 'step.add_argument("name")'),
    ("any-step-status-accepted", 'step.add_argument("status", choices=sorted(STEP_STATUSES))', 'step.add_argument("status")'),
]

# The wrappers, in a temporary copy of the scripts and templates. A survivor here means a model
# could see something change, or a page problem could reach the command.
WRAPPER_MUTANTS = [
    ("bash-exit-code-lost", "scripts/bash/run-step.sh", 'exit "$status"', "exit 0"),
    ("bash-engine-output-leaks", "scripts/bash/run-step.sh", "--quiet </dev/null >/dev/null 2>&1", "--quiet </dev/null"),
    ("bash-engine-stderr-leaks", "scripts/bash/run-step.sh", "--quiet </dev/null >/dev/null 2>&1", "--quiet </dev/null >/dev/null"),
    ("bash-records-failures", "scripts/bash/run-step.sh", 'if [ "$status" -eq 0 ]; then', "if true; then"),
    ("bash-records-nothing", "scripts/bash/run-step.sh", 'if [ "$status" -eq 0 ]; then', "if false; then"),
    ("bash-arguments-resplit", "scripts/bash/run-step.sh", '"$BASH" "$script" "$@"', '"$BASH" "$script" $*'),
    ("bash-engine-eats-stdin", "scripts/bash/run-step.sh", '"$BASH" "$script" "$@"', '"$BASH" "$script" "$@" </dev/null'),
    ("bash-harness-dropped", "scripts/bash/run-step.sh", '--harness "$harness" ', ""),
    ("bash-no-argument-check", "scripts/bash/run-step.sh", 'if [ "$#" -lt 3 ]; then', "if false; then"),
    ("bash-script-not-anchored", "scripts/bash/run-step.sh", 'if [ -f "$script_dir/../../$script" ]; then', "if false; then"),
    ("bash-own-scripts-folder-wins", "scripts/bash/run-step.sh", 'if [ -f "$script_dir/../../$script" ]; then', 'if [ ! -f "$script" ] && [ -f "$script_dir/../../$script" ]; then'),
    ("python-own-scripts-folder-wins", "scripts/python/run_step.py", "return str(anchored) if anchored.is_file() else script", "return str(anchored) if anchored.is_file() and not Path(script).is_file() else script"),
    ("bash-page-failure-fails", "scripts/bash/progress.sh", 'is missing. Run: specify integration upgrade" >&2\n    exit 0', 'is missing. Run: specify integration upgrade" >&2\n    exit 1'),
    ("bash-no-python-fails", "scripts/bash/progress.sh", 'no specify command here." >&2\nexit 0', 'no specify command here." >&2\nexit 1'),
    ("bash-no-fallback-to-specify", "scripts/bash/progress.sh", 'if command -v specify >/dev/null 2>&1; then', "if false; then"),
    ("bash-old-python-accepted", "scripts/bash/progress.sh", "sys.exit(0 if sys.version_info >= (3, 9) else 1)", "sys.exit(0)"),
    ("bash-engine-not-isolated", "scripts/bash/progress.sh", 'exec $candidate -I "$engine"', 'exec $candidate "$engine"'),
    ("bash-needs-external-tools", "scripts/bash/progress.sh", 'script_dir="$(CDPATH=\'\' cd -- "$script_dir" && pwd)"', 'script_dir="$(CDPATH=\'\' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"'),
    ("bash-root-is-the-current-folder", "scripts/bash/progress.sh", '--root "$project_root" "$@"\n    fi', '--root "." "$@"\n    fi'),
    ("python-exit-code-lost", "scripts/python/run_step.py", "return 128 - status if status < 0 else status", "return 0"),
    ("python-records-failures", "scripts/python/run_step.py", "    if status == 0:\n        update_progress", "    if True:\n        update_progress"),
    ("python-records-nothing", "scripts/python/run_step.py", "    if status == 0:\n        update_progress", "    if False:\n        update_progress"),
    ("python-engine-output-leaks", "scripts/python/run_step.py", "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL", "stderr=subprocess.DEVNULL"),
    ("python-engine-stderr-leaks", "scripts/python/run_step.py", "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL", "stdout=subprocess.DEVNULL"),
    ("python-harness-dropped", "scripts/python/run_step.py", 'command += ["--harness", harness, "step"', 'command += ["step"'),
    ("python-arguments-dropped", "scripts/python/run_step.py", "[sys.executable, locate(script), *rest]", "[sys.executable, locate(script)]"),
    ("python-no-argument-check", "scripts/python/run_step.py", "if len(argv) < 3:", "if False:"),
    ("python-script-not-anchored", "scripts/python/run_step.py", "locate(script), *rest", "script, *rest"),
    ("python-missing-engine-fails", "scripts/python/progress.py", 'specify integration upgrade", file=sys.stderr)\n        return 0', 'specify integration upgrade", file=sys.stderr)\n        return 1'),
    ("python-engine-not-isolated", "scripts/python/progress.py", '[sys.executable, "-I", str(engine)', "[sys.executable, str(engine)"),
    ("python-root-wrong", "scripts/python/progress.py", "str(here.parents[2])", 'str(".")'),
]


# These two run the repository's own files, so a changed copy of the engine would not reach them.
ENGINE_TESTS = ["--ignore=%s/test_install.py" % TESTS, "--ignore=%s/test_wrappers.py" % TESTS]


def run_tests(engine, sources=None):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if sources is None:
        env["SPECKIT_PROGRESS_ENGINE_UNDER_TEST"] = str(engine)
        command = [sys.executable, "-m", "pytest", TESTS, *ENGINE_TESTS]
    else:
        env["SPECKIT_PROGRESS_SOURCES_UNDER_TEST"] = str(sources)
        command = [sys.executable, "-m", "pytest", "%s/test_wrappers.py" % TESTS, "-n", "6"]
    command += ["-x", "-q", "--no-header", "-p", "no:cacheprovider"]
    try:
        done = subprocess.run(command, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=TIME_LIMIT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return None, "ran past %d s" % TIME_LIMIT_SECONDS
    failed = [line.split(" ")[1].split("::")[-1] for line in done.stdout.splitlines() if line.startswith("FAILED ")]
    return done.returncode, ", ".join(failed) or done.stdout.strip().splitlines()[-1:]


def run_mutant(name, old, new, workspace):
    folder = workspace / name
    shutil.copytree(SOURCE, folder, ignore=shutil.ignore_patterns("__pycache__"))
    engine = folder / "engine.py"
    text = engine.read_text(encoding="utf-8")
    if text.count(old) < 1:
        return "no-match", "the text to replace is not in the engine"
    engine.write_text(text.replace(old, new, 1), encoding="utf-8")
    code, detail = run_tests(engine)
    shutil.rmtree(folder, ignore_errors=True)
    if code == 0:
        return "SURVIVED", ""
    return "killed", detail


def run_wrapper_mutant(name, relative, old, new, workspace):
    folder = workspace / name
    for part in ("scripts", "templates"):
        shutil.copytree(ROOT / part, folder / part, ignore=shutil.ignore_patterns("__pycache__"))
    target = folder / relative
    text = target.read_text(encoding="utf-8")
    if text.count(old) < 1:
        return "no-match", "the text to replace is not in %s" % relative
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    code, detail = run_tests(None, sources=folder)
    shutil.rmtree(folder, ignore_errors=True)
    if code == 0:
        return "SURVIVED", ""
    return "killed", detail


def main():
    wanted = set(sys.argv[1:])
    known = {entry[0] for entry in MUTANTS} | {entry[0] for entry in WRAPPER_MUTANTS}
    if wanted - known:
        # Running nothing would otherwise report that nothing survived.
        print("no such mutant: %s" % ", ".join(sorted(wanted - known)), flush=True)
        return 2
    survivors = 0
    with tempfile.TemporaryDirectory(prefix="progress-mutants-") as directory:
        workspace = Path(directory)
        baseline = workspace / "baseline"
        shutil.copytree(SOURCE, baseline, ignore=shutil.ignore_patterns("__pycache__"))
        code, detail = run_tests(baseline / "engine.py")
        if code != 0:
            print("the tests fail before any mutation: %s" % detail, flush=True)
            return 2
        for name, old, new in MUTANTS:
            if wanted and name not in wanted:
                continue
            status, detail = run_mutant(name, old, new, workspace)
            if status != "killed":
                survivors += 1
            print("%-38s %-8s %s" % (name, status, detail), flush=True)
        for name, relative, old, new in WRAPPER_MUTANTS:
            if wanted and name not in wanted:
                continue
            status, detail = run_wrapper_mutant(name, relative, old, new, workspace)
            if status != "killed":
                survivors += 1
            print("%-38s %-8s %s" % (name, status, detail), flush=True)
    print("%d not killed" % survivors, flush=True)
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
