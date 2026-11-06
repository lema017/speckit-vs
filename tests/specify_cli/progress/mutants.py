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
]


def run_tests(engine):
    env = dict(os.environ, SPECKIT_PROGRESS_ENGINE_UNDER_TEST=str(engine), PYTHONDONTWRITEBYTECODE="1")
    command = [sys.executable, "-m", "pytest", TESTS, "-x", "-q", "--no-header", "-p", "no:cacheprovider"]
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


def main():
    wanted = set(sys.argv[1:])
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
    print("%d not killed" % survivors, flush=True)
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
