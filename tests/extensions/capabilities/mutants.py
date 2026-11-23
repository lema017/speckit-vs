"""Prove the acceptance tests have teeth: remove each control and require a failure.

Not collected by pytest. Run it by hand from the repository root:

    .venv/bin/python tests/extensions/capabilities/mutants.py [name ...]

Each mutant is one exact replacement in a temporary copy of the extension. A
mutant that no test catches is a control nothing is really testing, so the run
exits with 1.

CAP_MUTANT_TESTS narrows the tests a run uses to the ones a pytest ``-k``
expression selects, to try a few mutants quickly. A mutant that survives under
it has to be run again without it.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXT = ROOT / "extensions" / "capabilities"
MODULES = [
    "test_acceptance_catalog.py",
    "test_acceptance_evidence.py",
    "test_acceptance_concurrency.py",
    "test_acceptance_discovery.py",
    "test_fold_and_check.py",
    "test_discovery_tools.py",
    "test_report_languages.py",
    "test_lifecycle.py",
]
GATE_MODULES = ["test_graph_gate.py"]
CLARIFY_MODULES = ["test_clarify_context.py"]

MUTANTS = [
    ("setup-writes-nothing", 'so the agent follows the fork from the first command."""\n    return emit({"setup": ensure_setup(root), "status": "ok"})', 'so the agent follows the fork from the first command."""\n    return emit({"setup": [], "status": "ok"})'),
    # Acceptance 1: the catalog, in both directions.
    ("reverse-check-off", "            self.check_reverse()\n", "            pass\n"),
    ("reverse-accepts-any-delta-on-the-rule", 'if entry["to"] != after["text"] or after["tag"] != source:', "if False:"),
    ("history-check-off", "            self.check_history()\n", "            pass\n"),
    ("provenance-off", "        self.check_provenance()\n", "        pass\n"),
    ("sealed-delta-off", 'if norm(now) != norm(delta_before["raw"]):', "if False:"),
    ("sealed-lock-off", "if self.show(self.merge_base, lock_rel) != read(self.root / lock_rel):", "if False:"),
    ("registered-delta-removal-off", "if MARK in before and (text is None or MARK not in text):", "if False:"),
    ("strict-rules-off", 'self.hard.extend("%s: %s" % (cap_rel(name, "spec.md"), error) for error in catalog_errors(text))', "pass"),
    ("rule-status-check-off", "            self.check_rule_status_changes()\n", "            pass\n"),
    ("naming-contract-off", "self.hard.extend(naming_errors(self.root))", "pass"),
    # Acceptance 2: evidence for REMOVED and the merge queue.
    ("retirement-evidence-off", 'rule_id, replacement = entry["id"], entry["replaced-by"]\n', 'rule_id, replacement = entry["id"], entry["replaced-by"]\n        return []\n'),
    ("absence-test-optional", 'if not row["manual"] and not row["tests"]:', "if False:"),
    ("stale-allowed-at-pr-head", "if not self.combined:", "if False:"),
    ("combined-skips-tests", "if test_problems:", "if False:"),
    ("combined-accepts-manual", 'if row["manual"]:\n            return ["%s: anchored file changed', 'if False:\n            return ["%s: anchored file changed'),
    ("failed-tests-ignored", 'return ["%s: mapped test %s %s" % (rule_id, ref, result) for ref, result in results if result != "passed"]', "return []"),
    ("old-report-accepted", "elif self.written_at(tree, path) < head_time - REPORT_SKEW_SECONDS:", "elif False:"),
    ("zone-less-time-is-trusted", "return moment.timestamp() if moment.tzinfo else None", "return moment.timestamp()"),
    ("age-ignores-the-file", "return min(moments) if moments else path.stat().st_mtime", "return min(moments) if moments else float('inf')"),
    ("report-directory-not-read", "found = sorted(item for item in path.rglob(\"*.xml\") if item.is_file())", "found = sorted(item for item in path.glob(\"TEST-a*.xml\") if item.is_file())"),
    ("empty-report-directory-accepted", 'raise CapError("no XML test report in %s" % value)', "pass"),
    ("script-test-file-ignored", "if same_file(parts[0], case[3] or case[1]) and title_matches(", "if title_matches("),
    ("script-test-classname-ignored", "same_file(parts[0], case[3] or case[1])", "same_file(parts[0], case[3])"),
    ("title-separator-kept", 'case[0].replace(" > ", " ")', "case[0]"),
    ("title-slots-off", "return len(pieces) > 1 and re.fullmatch(", "return False and re.fullmatch("),
    ("nested-class-not-read", 'classname = case[1].replace("$", ".")', "classname = case[1]"),
    ("method-suffix-not-read", 'case[0].startswith((name + "[", name + "("))', 'case[0].startswith(name + "[")'),
    ("package-prefix-not-allowed", ' or expected.endswith("." + classname)', ""),
    ("comma-splits-a-title", 'quoted = re.findall(r"`([^`]+)`", value)', "quoted = None"),
    ("tracked-report-accepted", 'if git(self.root, "ls-files", "--error-unmatch", "--", str(path)) is not None:', "if False:"),
    ("skipped-counts-as-passed", 'child.tag in ("failure", "error", "skipped")', 'child.tag in ("failure", "error")'),
    ("one-variant-is-enough", 'return "passed" if all(case[2] for case in hits) else "failed"', 'return "passed" if any(case[2] for case in hits) else "failed"'),
    ("any-module-matches", 'same_class = classname == expected or classname.endswith("." + expected) or expected.endswith("." + classname)', "same_class = True"),
    ("manual-evidence-on", 'if self.config["allow_manual_evidence"]:', "if True:"),
    ("partial-features-on", 'if tasks and self.config["allow_partial_features"] and reviewed', "if tasks and reviewed"),
    ("partial-ignores-catalog", 'and reviewed and not any(done for _, done in applied):', "and reviewed:"),
    # Acceptance 3: two processes.
    ("flock-off", "fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)", "pass"),
    ("apply-without-lock", "manifest = json.loads(manifest_text)\n    with publish_lock(root):", "manifest = json.loads(manifest_text)\n    if True:"),
    ("base-token-not-checked", 'if state["token"] != manifest.get("token") or state["source"] != manifest.get("source"):', "if False:"),
    ("shared-staging-directory", 'staging = "%s/%s-%s" % (STAGING, sha(state["source"]), uuid.uuid4().hex[:8])', 'staging = "%s/%s" % (STAGING, sha(state["source"]))'),
    # Acceptance 4: discovery.
    ("feature-roots-off", 'elif under_root(name, self.config["feature_roots"]):', "elif False:"),
    ("fr-signature-off", "elif FR_LINE.search(text):", "elif False:"),
    ("catalog-counts-as-feature", 'return name.startswith(CATALOG + "/") and not name.startswith(CHANGES + "/")', "return False"),
    ("change-record-without-marker-ok", 'if os.path.basename(name) == "capability-delta.md":', "if False:"),
    # Phase 4: the block for agents.
    ("agent-block-never-written", "for rel in agent_files(root):\n        result", "for rel in []:\n        result"),
    ("agent-overwrites-unbalanced", 'return "skipped %s: unbalanced markers" % rel', "updated = block + newline"),
    ("agent-ignores-config", "configured = agent_context_files(root)\n", "configured = []\n"),
    ("agent-ignores-integration", "return [AGENT_FILES.get(name, DEFAULT_AGENT_FILE) if isinstance(name, str) else DEFAULT_AGENT_FILE]", "return [DEFAULT_AGENT_FILE]"),
    ("agent-unsafe-list-allowed", "if item and safe_agent_path(item)]", "if item]"),
    ("agent-unsafe-single-allowed", "if single and safe_agent_path(single) else", "if single else"),
    ("agent-symlink-escape", "if root not in path.resolve().parents:", "if False:"),
    ("agent-listed-as-foreign", '".gitattributes", *agent_files(root))', '".gitattributes")'),
    ("agent-crlf-normalized", 'current = path.read_bytes().decode("utf-8") if path.exists() else ""', 'current = read(path) or ""'),
    ("agent-crlf-mixed", 'newline = "\\r\\n" if "\\r\\n" in current else "\\n"', 'newline = "\\n"'),
    ("agent-mdc-without-frontmatter", 'if rel.endswith(".mdc") and not updated.startswith("---"):', "if False:"),
    ("agent-rewrites-identical", "if updated == current:\n        return None", "if False:\n        return None"),
    ("agent-write-error-stops-review", 'except OSError as error:\n        return "skipped %s: %s" % (rel, error.strerror or error)', 'except ZeroDivisionError as error:\n        return "skipped %s: %s" % (rel, error.strerror or error)'),
    # Phase 4: scaffold and locate.
    ("scaffold-without-lock", 'one line of text without |")\n    with publish_lock(root):', 'one line of text without |")\n    if True:'),
    ("scaffold-ignores-journal", 'with publish_lock(root):\n        if (root / JOURNAL).exists():\n            return emit({"status": "recover-needed"}, RECOVER)\n        text = read(root / INDEX) or', 'with publish_lock(root):\n        text = read(root / INDEX) or'),
    ("scaffold-allows-pipe", '    if not covers or "|" in covers:\n        raise CapError("scaffold requires --covers', '    if not covers:\n        raise CapError("scaffold requires --covers'),
    ("scaffold-allows-any-name", '    if not capability or not CAPABILITY.match(capability):\n        raise CapError("scaffold requires --capability', '    if not capability:\n        raise CapError("scaffold requires --capability'),
    ("index-sets-any-name", '    if not capability or not CAPABILITY.match(capability):\n        raise CapError("index --capability takes a name', '    if not capability:\n        raise CapError("index --capability takes a name'),
    ("scaffold-repeats-row", 'if re.search(r"^\\| (?:\\[%s\\]\\S*|%s) \\|" % (name, name), text, re.M) or (root / CATALOG / capability).is_dir():', "if False:"),
    ("planned-row-left-behind", "text = text[:planned.start()] + text[planned.end():]", "pass"),
    ("status-hides-planned", '"planned": {name: covers for name, covers in planned if name not in capabilities},', '"planned": {},'),
    ("locate-always-resolves", 'return [{"ref": ref, "resolves": anchor_resolves(root, ref)} for ref in refs]', 'return [{"ref": ref, "resolves": True} for ref in refs]'),
    ("locate-any-name", 'if not CAPABILITY.match(capability):\n        raise CapError("invalid capability name', 'if False:\n        raise CapError("invalid capability name'),
    ("locate-origin-lost", '"origin": rule["tag"],', '"origin": None,'),
    # What the real agent runs found.
    ("review-names-no-rule", 'if set(split_links(entry["links"])) & set(changed)]', "if False]"),
    ("review-hides-other-text", '"other_text": not changed and not delta_changed,', '"other_text": False,'),
    # The mechanism underneath.
    ("anchor-symbol-not-checked", 'if name and not re.search(r"(?<!\\w)%s(?!\\w)" % re.escape(name), text):', "if False:"),
    ("anchor-not-rechecked-in-ci", 'problems.append("%s: code anchor does not resolve: %s" % (rule_id, ref))', "pass"),
    ("own-files-notice-off", "            self.check_own_files()\n", "            pass\n"),
    ("journal-ignored-by-check", "if (self.root / JOURNAL).exists():", "if False:"),
    ("recover-overwrites-edits", "    if edited:\n        return edited\n", ""),
    ("discrepancy-does-not-block", 'if row["state"] != "conforming":\n            problems.append("%s: state is', 'if False:\n            problems.append("%s: state is'),
    ("branch-conflict-off", 'elif says != entry["from"]:', "elif False:"),
    ("not-reviewed-is-fine", 'if not reviewed:\n            messages.append', 'if False:\n            messages.append'),
    ("open-tasks-are-fine", 'if tasks:\n            messages.append', 'if False:\n            messages.append'),
]


def run_mutant(name, old, new, workdir, python, target="capabilities.py", modules=None):
    copy = workdir / name
    shutil.copytree(str(EXT), str(copy))
    script = copy / "scripts" / "python" / target
    source = script.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        return "stale", "the text to replace occurs %d times" % count
    script.write_text(source.replace(old, new), encoding="utf-8")
    env = dict(os.environ, CAP_TEST_SCRIPT=str(copy / "scripts" / "python" / "capabilities.py"))
    tests = [str(ROOT / "tests" / "extensions" / "capabilities" / module) for module in modules or MODULES]
    only = ["-k", os.environ["CAP_MUTANT_TESTS"]] if os.environ.get("CAP_MUTANT_TESTS") else []
    done = subprocess.run(
        [python, "-m", "pytest", *tests, "--rootdir", str(ROOT), "-n", "8", "-x", "-q", "-p", "no:cacheprovider", "--tb=no", *only],
        cwd=str(ROOT), capture_output=True, encoding="utf-8", errors="replace", env=env,
    )
    failed = sorted(set(re.findall(r"^(?:FAILED|ERROR) \S*?::(\S+)", done.stdout, re.M)))
    shutil.rmtree(str(copy))
    if done.returncode == 0:
        return "survived", ""
    if not failed:
        return "broken", done.stdout[-400:]
    return "killed", ", ".join(failed[:3])


MUTANTS += [
    # A catalog git ignores.
    ("ignored-catalog-passes-check", 'self.hard.append("%s: %s" % (CATALOG, IGNORED_CATALOG))', "pass"),
    ("ignored-catalog-not-reported", 'touched.append("skipped %s: %s" % (CATALOG, IGNORED_CATALOG))', "pass"),
    ("ignored-catalog-counts-tracked", 'git(root, "check-ignore", "-q", CATALOG + "/index.md")', 'git(root, "check-ignore", "-q", "--no-index", CATALOG + "/index.md")'),
]

MUTANTS += [
    # refresh: what an update of the extension brings up to date, and where it writes nothing.
    ("refresh-sets-up-a-project-that-never-was", "    if not is_set_up(root):\n        return emit", "    if False:\n        return emit"),
    ("refresh-refreshes-nothing", 'return emit({"setup": ensure_setup(root), "status": "ok"})', 'return emit({"setup": [], "status": "ok"})'),
    ("refresh-says-none-for-a-set-up-project", 'return emit({"setup": ensure_setup(root), "status": "ok"})', 'return emit({"setup": ensure_setup(root), "status": "none"})'),
    ("refresh-says-ok-where-it-did-nothing", 'return emit({"setup": [], "status": "none"})', 'return emit({"setup": [], "status": "ok"})'),
    ("refresh-misses-a-block-without-its-start", "if AGENT_START in text or AGENT_END in text:", "if AGENT_START in text:"),
    ("refresh-misses-a-block-without-its-end", "if AGENT_START in text or AGENT_END in text:", "if AGENT_END in text:"),
    ("refresh-reads-out-of-the-repository", "inside = root in path.resolve().parents", "inside = True"),
    ("refresh-looks-only-at-agents-md", "    for rel in agent_files(root):\n        path = root / rel\n        inside", "    for rel in [DEFAULT_AGENT_FILE]:\n        path = root / rel\n        inside"),
    ("refresh-stops-at-a-file-that-is-not-text", '        except (OSError, UnicodeDecodeError):\n            text = ""', "        except OSError:\n            text = \"\""),
    ("refresh-not-a-command", '    if args.command == "refresh":\n        return cmd_refresh(root)\n', ""),
]

MUTANTS += [
    # bootstrap and validate: a claim of conformity needs evidence.
    ("inferred-skips-evidence", 'if row is not None and row["state"] != "unverified":', 'if row is not None and row["state"] != "unverified" and entry["op"] == "VALIDATED":'),
    ("validated-skips-evidence", 'if row is not None and row["state"] != "unverified":', 'if row is not None and row["state"] != "unverified" and entry["op"] == "INFERRED":'),
    ("discrepant-owes-nothing", 'if row is not None and row["state"] != "unverified":', 'if row is not None and row["state"] == "conforming":'),
    ("inferred-never-stale", 'fresh=entry["op"] != "VALIDATED")', 'fresh=False)'),
    ("validated-always-stale", 'fresh=entry["op"] != "VALIDATED")', 'fresh=True)'),
    # What the independent review found. Each one was a way through CI.
    ("state-given-up", 'if was and was["state"] != row["state"]:', "if False:"),
    ("state-given-up-is-only-a-note", '(self.soft if touched & anchored else self.notes.append)(message)', "self.notes.append(message)"),
    ("state-recorded-always-blocks", '(self.soft if touched & anchored else self.notes.append)(message)', "self.soft(message)"),
    ("test-file-not-anchored", 'if not code_changed and not touched & {anchor_file(ref) for ref in row["tests"]}:', "if not code_changed:"),
    ("anchors-not-rechecked", 'the fold looks at it again" % (rule_id, rule_id))\n                for ref in row["code"] + row["tests"]:', 'the fold looks at it again" % (rule_id, rule_id))\n                for ref in []:'),
    ("anchor-spelling", 'return posixpath.normpath(ref.split("::")[0])', 'return ref.split("::")[0]'),
    ("wrapped-field-skipped", "if line.strip() and (current is not None or new_capability):", "if False:"),
    ("comment-is-a-field", 're.sub(r"<!--.*?-->", "", raw, flags=re.S).splitlines()', "raw.splitlines()"),
    ("placeholder-title-matches", 'if not "".join(TITLE_SLOT.split(parts[-1])).strip():', "if False:"),
    ("template-literal-slot", r'''|\$\{[^{}]*\}|''', "|"),
]

MUTANTS += [
    # F1, the lifecycle: [designed], DESIGNED and IMPLEMENTED.
    ("designed-anywhere", "    if not is_record(source):\n        return [\"DESIGNED", "    if False:\n        return [\"DESIGNED"),
    ("design-record-mixes-operations", 'return ["a design record declares only', 'return [] and ["a design record declares only'),
    ("publish-design-takes-any-op", '        if others:\n            return emit({"status": "invalid", "errors": ["publish-design publishes', '        if False:\n            return emit({"status": "invalid", "errors": ["publish-design publishes'),
    ("publish-design-retires-built", 'if entry["op"] == "REMOVED" and rule is not None and not rule["designed"]:', "if False:"),
    ("fold-publishes-design", "if is_design(delta) or (design_capable(delta, source) and retires_designed(root, delta)):", "if False:"),
    ("designed-over-built", '    if not rule["designed"]:\n        return "the rule is %s', '    if False:\n        return "the rule is %s'),
    ("implemented-on-built-rule", 'conflicts.append(where + ": the rule is not [designed]; a spec changes an implemented rule with MODIFIED")', 'actions.append((entry, "apply"))'),
    ("implemented-applies-stale-text", 'elif rule["designed"] and rule["text"] == entry["from"]:', 'elif rule["designed"]:'),
    ("added-over-designed", 'elif rule is not None and rule["designed"] and entry["op"] in ("ADDED", "INFERRED", "VALIDATED"):', "elif False:"),
    ("spec-retires-designed", 'elif rule is not None and rule["text"] == entry["from"] and rule["designed"] and not designer:', "elif False:"),
    ("implemented-applied-while-designed", '        if rule["designed"] != (op == "DESIGNED"):\n            return False', "        pass"),
    ("base-designed-counts-as-delivered", ' and base_says["designed"] == (op == "DESIGNED")', ""),
    ("implemented-owes-no-evidence", 'elif entry["op"] in ("ADDED", "MODIFIED", "IMPLEMENTED", "REOBSERVED"):', 'elif entry["op"] in ("ADDED", "MODIFIED", "REOBSERVED"):'),
    ("retiring-designed-needs-evidence", 'if entry["op"] == "DESIGNED" or (entry["op"] == "REMOVED" and self.was_designed(entry)):', 'if entry["op"] == "DESIGNED":'),
    ("spec-retires-designed-in-check", '                if entry["op"] == "REMOVED" and not design_capable(delta, source):', "                if False:"),
    ("provenance-ignores-designed", '                if rule["designed"] != (entry["op"] == "DESIGNED"):\n                    return "origin', '                if False:\n                    return "origin'),
    ("reverse-ignores-designed", '                if after["designed"] != (entry["op"] == "DESIGNED"):\n                    continue', "                pass"),
    ("base-retired-says-now-none", 'elif says is None and retired_by and op != "REMOVED":', "elif False:"),
    # Conflict markers.
    ("markers-not-seen", "return bool(text) and bool(CONFLICT_SIDE.search(text))", "return False"),
    ("lone-equals-is-a-marker", r'CONFLICT_SIDE = re.compile(r"^(?:<{7}|>{7}|\|{7})(?: .*)?$", re.M)', r'CONFLICT_SIDE = re.compile(r"^(?:<{7}|>{7}|\|{7}|={7})(?: .*)?$", re.M)'),
    ("fold-ignores-catalog-markers", "        files = conflicted(root, rels)\n", "        files = []\n"),
    ("check-ignores-catalog-markers", "        for rel in conflicted(self.root, files):\n", "        for rel in []:\n"),
    ("check-ignores-delta-markers", "        if has_conflict(text):\n            self.hard.append", "        if False:\n            self.hard.append"),
    # review normalizes IMPLEMENTED, only before the first seal and only a slip in the copy.
    ("review-does-not-normalize", "text, normalized = normalize_implemented(root, text, source) if lock is None else (text, [])", "text, normalized = text, []"),
    ("review-normalizes-after-the-seal", "text, normalized = normalize_implemented(root, text, source) if lock is None else (text, [])", "text, normalized = normalize_implemented(root, text, source)"),
    ("normalize-takes-a-new-text", 'if entry.get("from") in (None, "(none)") or entry.get("to") not in (entry.get("from"), rule["text"]):', "if False:"),
    # The format seal and the index.
    ("newer-format-accepted", "    if found > CATALOG_FORMAT:\n", "    if False:\n"),
    ("seal-never-written", "    return with_seal(text) if designed else text\n", "    return text\n"),
    ("seal-not-required", "catalog_format(index) < CATALOG_FORMAT:", "catalog_format(index) < 0:"),
    ("index-states-unchecked", "        self.check_index_states(index)\n", "        pass\n"),
    ("legacy-row-rejected", 'if said != expected and not (not rules and said == "consolidated"):', "if said != expected:"),
    ("rebuild-keeps-duplicate-rows", "            if name in done:\n                continue\n", "            if False:\n                continue\n"),
    ("delta-block-any-rule", '        elif not rule["designed"]:\n            errors.append(', "        elif False:\n            errors.append("),
    # rebase and defer.
    ("rebase-reads-the-working-tree", 'return lambda rel: git(root, "show", "%s:%s" % (rev, rel)) if rev else None', "return lambda rel: read(root / rel)"),
    ("rebase-branch-is-always-head", "if not holds_change(root, first, source) and holds_change(root, second, source):", "if False:"),
    ("rebase-ignores-the-merge-commit", 'elif resolve_rev(root, "HEAD^2"):', "elif False:"),
    ("rebase-index-from-the-branch", '    index = base(INDEX) or template("capability-index.md")', '    index = branch(INDEX) or template("capability-index.md")'),
    ("rebase-leaves-dropped-files", "                plan[rel] = base(rel)\n", "                pass\n"),
    ("rebase-applies-an-unfolded-change", 'mine = [action for action in actions if action[0]["capability"] == capability] if folded else []', 'mine = [action for action in actions if action[0]["capability"] == capability]'),
    ("adopt-keeps-the-old-observation", 'block = re.sub(r"^- State: .*$", "- State: unverified", block, flags=re.M)', "block = block"),
    ("keep-on-a-retired-rule", 'if said is not None and entry["op"] != "REOBSERVED" and said["text"] != entry["to"]:', 'if entry["op"] != "REOBSERVED" and (said is None or said["text"] != entry["to"]):'),
    ("rebase-does-not-reseal", '                plan[source + "/" + LOCK_NAME] = dumps(relocked(lock, new_text, new_delta, source, {entry["id"] for entry in dropped}))', "                pass"),
    ("rebase-loses-other-folds", '        if others:\n            raise CapError("this branch also folded', '        if False:\n            raise CapError("this branch also folded'),
    ("defer-leaves-the-catalog", "plan, conflicts = rebased_plan(root, source, new_delta, touched, start, here, start, True)", "plan, conflicts = {}, []"),
    ("defer-rebuilds-from-the-working-tree", "            start = reader(root, point)\n", "            start = here\n"),
]

# The door to Graphify. Each one is checked with test_graph_gate.py alone.
MUTANTS += [
    # A base that fell behind its remote.
    ("stale-base-not-followed", "        self.follow_upstream()\n", ""),
    ("stale-base-kept-as-the-base", "            self.base = upstream\n", "            pass\n"),
    ("diverged-base-followed", "        if behind and not ahead:\n            remote, _, branch", "        if behind:\n            remote, _, branch"),
    ("a-base-ahead-of-its-remote-is-said-to-diverge", '        elif behind:\n            self.notes.append("%s and %s have diverged', '        else:\n            self.notes.append("%s and %s have diverged'),
    ("fetch-advised-with-no-remote", ' if branch and git(self.root, "remote", "get-url", remote) else ""', ' if branch else ""'),
    # A suite that did not load is not a test that is missing.
    ("unloaded-suite-reads-as-missing", '        return "missing" if why is None else "did not run, its suite did not load: %s" % why', '        return "missing"'),
    ("any-failed-test-of-the-file-is-its-suite", "broken = same_file(path, name) and same_file(path, file or classname or name)", "broken = same_file(path, file or classname or name)"),
    ("a-collection-error-explains-any-test", 'broken = name == module or module.endswith("." + name) or name.endswith("." + module)', "broken = True"),
    ("any-failed-step-of-the-class-is-its-suite", "broken = name in SUITE_STEPS and (", "broken = ("),
    ("a-step-that-passed-stops-the-suite", "        if passed:\n            continue\n        if path.endswith(SCRIPT_TESTS):", "        if path.endswith(SCRIPT_TESTS):"),
    ("the-reason-pytest-gives-is-lost", 'marked = [line[1:] for line in (child.text or "").splitlines() if line.startswith("E ")]', "marked = []"),
    # Tasks that come after the fold.
    ("post-merge-tasks-hold-the-fold", "    return None if boxes is None else sum(1 for rest in boxes if POST_MERGE not in rest.lower() and not FOLD_TASK.search(rest))",
     "    return None if boxes is None else sum(1 for rest in boxes if not FOLD_TASK.search(rest))"),
    ("the-task-of-the-fold-holds-the-fold", "if POST_MERGE not in rest.lower() and not FOLD_TASK.search(rest))", "if POST_MERGE not in rest.lower())"),
    ("any-task-that-says-fold-is-the-task-of-the-fold", 'FOLD_TASK = re.compile(r"speckit[.\\-]capabilities[.\\-]fold", re.I)', 'FOLD_TASK = re.compile(r"fold", re.I)'),
    ("prepare-does-not-name-the-tasks-of-the-fold", '    if own:\n        state["fold_tasks"] = own\n', ""),
    ("a-task-of-the-fold-for-after-the-merge-is-named", "if FOLD_TASK.search(rest) and POST_MERGE not in rest.lower()]", "if FOLD_TASK.search(rest)]"),
    ("a-task-of-the-fold-loses-its-id", "TASK_ID.search(rest).group(0) if TASK_ID.search(rest) else rest.strip()[:60]", "rest.strip()[:60]"),
    ("post-merge-mark-needs-its-case", "sum(1 for rest in boxes if POST_MERGE not in rest.lower() and", "sum(1 for rest in boxes if POST_MERGE not in rest and"),
    ("every-open-task-waits-for-the-merge", "    return sum(1 for rest in open_boxes(change) or [] if POST_MERGE in rest.lower())", "    return len(open_boxes(change) or [])"),
    ("prepare-does-not-say-what-waits", '    if waiting:\n        state["post_merge"] = waiting\n', ""),
    ("check-does-not-say-what-waits", '        if waiting:\n            self.notes.append("%s: %s for after the merge', '        if False:\n            self.notes.append("%s: %s for after the merge'),
    # The index: what a capability covers, and where its code starts.
    ("dead-entry-point-not-said", '            if entry not in ("", "none") and not live_entry(self.root, entry):\n                self.soft(', '            if False:\n                self.soft('),
    ("dead-entry-point-is-only-a-note", '                self.soft("index.md: the entry point of %s does not exist', '                self.notes.append("index.md: the entry point of %s does not exist'),
    ("fold-keeps-a-dead-entry-point", '        if root is not None and not live_entry(root, kept):\n            kept = "none"\n', ""),
    ("fold-replaces-a-live-entry-point", "        if root is not None and not live_entry(root, kept):", "        if root is not None:"),
    ("rebuild-keeps-a-dead-entry-point", 'kept = cells[3] if linked and len(cells) > 3 and live_entry(root, cells[3]) else "none"', 'kept = cells[3] if linked and len(cells) > 3 else "none"'),
    ("fold-does-not-say-it-replaced-an-entry-point", '    if replaced:\n        out["entry_points"] = replaced\n', ""),
    ("fold-does-not-ask-to-read-covers", '    if review:\n        out["review_covers"] = review\n', ""),
    ("covers-read-again-after-any-fold", '        if what == "apply" and entry["op"] == "REMOVED":\n            removed[entry["capability"]]', '        if what == "apply":\n            removed[entry["capability"]]'),
    ("index-sets-an-entry-point-that-is-not-there", '        if entry != "none" and not anchor_resolves(root, entry):\n            raise CapError("the entry point does not exist', '        if False:\n            raise CapError("the entry point does not exist'),
    ("index-takes-covers-with-a-pipe", '        if not covers or "|" in covers:\n            raise CapError("index takes --covers', '        if not covers:\n            raise CapError("index takes --covers'),
    ("index-takes-empty-covers", '        if not covers or "|" in covers:\n            raise CapError("index takes --covers', '        if "|" in covers:\n            raise CapError("index takes --covers'),
    ("index-set-ignores-the-journal", '            return emit({"status": "recover-needed"}, RECOVER)\n        lines = (read(root / INDEX) or "").split("\\n")', '            pass\n        lines = (read(root / INDEX) or "").split("\\n")'),
    ("overview-follows-any-covers", "new_covers != old_covers and overview_of(spec) == old_covers", "new_covers != old_covers"),
    ("overview-never-follows", "        if spec is not None and new_covers != old_covers and overview_of(spec) == old_covers:", "        if False:"),
    ("index-set-and-rebuild-at-once", '            if args.rebuild:\n                raise CapError("index takes --rebuild or --capability, not both")\n', ""),
    # REOBSERVED: the code of a rule moved, and what the rule says did not.
    ("reobserved-takes-a-text", '            for key in ("from", "to", "replaced-by"):\n                if entry.get(key):', "            for key in ():\n                if entry.get(key):"),
    ("reobserved-without-a-reason", '("capability", "reason") if entry["op"] == "REOBSERVED" else', '("capability",) if entry["op"] == "REOBSERVED" else'),
    ("any-entry-takes-a-reason", '        elif entry.get("reason"):\n            errors.append(where + ": takes no Reason', '        elif False:\n            errors.append(where + ": takes no Reason'),
    ("reobserved-has-to-link", 'if link not in allowed_links and not (entry["op"] == "REOBSERVED" and link == "none"):', "if link not in allowed_links:"),
    ("reobserved-links-to-nothing-by-itself", '            entry.setdefault("links", "none")\n', "            pass\n"),
    ("reobserved-of-a-designed-rule", '            elif rule["designed"]:\n                conflicts.append(where + ": the rule is [designed], so no code', '            elif False:\n                conflicts.append(where + ": the rule is [designed], so no code'),
    ("reobserved-owes-no-evidence", '("ADDED", "MODIFIED", "IMPLEMENTED", "REOBSERVED")', '("ADDED", "MODIFIED", "IMPLEMENTED")'),
    ("reobserved-lets-the-text-change", 'or entry["capability"] != capability or entry["op"] == "REOBSERVED":', 'or entry["capability"] != capability:'),
    ("the-base-need-not-have-the-rule", '            if base_says is None or base_says["designed"]:\n                self.hard.append("REOBSERVED %s: %s has no built rule', '            if False:\n                self.hard.append("REOBSERVED %s: %s has no built rule'),
    ("reobserved-counts-as-applied-on-a-designed-rule", '            return rule is not None and not rule["designed"]', "            return rule is not None"),
    ("the-note-does-not-say-the-way-out", '; if the rule still holds, declare REOBSERVED %s and the fold looks at it again" % (rule_id, rule_id))', '" % rule_id)'),
]

GATE_MUTANTS = [
    ("gate-leaks-the-environment", "env=graph_env()", "env=dict(os.environ, **graph_env())"),
    ("gate-backend-left-on", 'env["GRAPHIFY_BACKEND"] = "none"\n', "pass\n"),
    ("gate-query-log-left-on", 'env["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"\n', "pass\n"),
    ("gate-reads-without-updating", 'done = tool(root, ["update", "."], UPDATE_SECONDS)', 'done = (0, "", "")'),
    ("gate-reads-after-a-failed-update", "if done is None or done[0] != 0 or not (root / GRAPH).is_file():", "if False:"),
    ("gate-writes-without-the-tool", '    if find_tool() is None:\n        return None, "not-installed"\n    try:\n        wrote = ensure_ignores(root)', "    try:\n        wrote = ensure_ignores(root)"),
    ("gate-ignores-the-tool-beside-specify", 'beside = shutil.which("graphify", path=os.path.dirname(os.path.realpath(specify))) if specify else None', "beside = None"),
    ("gate-does-not-follow-the-specify-link", "os.path.dirname(os.path.realpath(specify))", "os.path.dirname(specify)"),
    ("gate-path-beats-the-shipped-tool", "return beside or shutil.which(\"graphify\")", "return shutil.which(\"graphify\") or beside"),
    ("gate-no-code-is-a-failure", 'if done is not None and done[0] != 0 and NO_CODE in done[1] + done[2]:', "if False:"),
    ("gate-any-failure-is-no-code", 'if done is not None and done[0] != 0 and NO_CODE in done[1] + done[2]:', "if done is not None and done[0] != 0:"),
    ("gate-install-always-offered", 'if reason == "not-installed":', "if True:"),
    ("gate-overwrites-the-ignore-file", "if not ignore.exists() and not ignore.is_symlink():", "if not ignore.is_symlink():"),
    ("gate-out-dir-not-ignored", '        own.write_text("*\\n", encoding="utf-8")\n', '        own.write_text("\\n", encoding="utf-8")\n'),
    ("gate-version-not-reported", 'return [] if version == PINNED else ["Graphify %s is not the validated %s" % (version or "of unknown version", PINNED)]', "return []"),
    ("gate-not-found-degrades", "if code == 4:", "if False:"),
    ("gate-ambiguous-degrades", "if code == 3:", "if False:"),
    ("gate-any-failure-accepted", "if code != 0:", "if False:"),
    ("gate-any-graph-format", 'or graph.get("schema_version") != SCHEMA or', "or"),
    ("gate-by-name-off", 'found = "by-name" if named_in_file(root, ref) else "missing"', 'found = "missing"'),
    ("gate-name-not-looked-for", 'return all(re.search(r"(?<!\\w)%s(?!\\w)" % re.escape(name), text) for name in names if name)', "return True"),
    ("gate-anchor-may-leave-the-project", "if root not in target.parents or not target.is_file():", "if not target.is_file():"),
    ("gate-repeated-name-silent", "if repeats:", "if False:"),
    ("gate-repeated-symbol-is-unique", 'return "unique" if found == 1 else "ambiguous" if found > 1 else "absent"', 'return "unique" if found else "absent"'),
    ("gate-dash-reaches-the-tool", 'if any(term.startswith("-") for term in args.terms):', "if False:"),
    ("gate-spanish-silent", "if any(ord(char) > 127 for term in terms for char in term):", "if False:"),
    ("gate-output-not-cut", '"output": stdout[:MAX_OUTPUT], "truncated"', '"output": stdout, "truncated"'),
    ("gate-writes-through-a-link", "ignore.is_symlink()", "False"),
    ("gate-out-dir-through-a-link", "out.is_symlink()", "False"),
    ("gate-write-error-escapes", "except OSError:\n        return None", "except ZeroDivisionError:\n        return None"),
    ("gate-graph-of-any-shape", 'isinstance(node.get("source_file"), str)', "True"),
    ("gate-root-not-checked", "if not root.is_dir():", "if False:"),
    ("gate-read-error-escapes", 'except OSError as error:\n        return degraded("read-failed"', 'except ZeroDivisionError as error:\n        return degraded("read-failed"'),
    ("gate-anchor-symbols-cut", 'path, *symbols = ref.split("::")', 'path, *symbols = ref.split("::")[:2]'),
    ("gate-unquoted-anchors-dropped", 'QUOTED.findall(line) or [part.strip() for part in line.split(",") if part.strip() not in ("", "none")]', "QUOTED.findall(line)"),
    ("gate-anchors-rows-not-read", '                found.setdefault(ref, (path.parent.name, "anchors"))', "                pass"),
    # touched: where the change is in the code.
    ("touched-symbol-below-holds-the-line", "at = bisect.bisect_right(starts, line) - 1", "at = bisect.bisect_right(starts, line)"),
    ("touched-new-symbols-not-listed", "            if row[1] and low <= row[0] <= high:\n                held.setdefault(row, set())", "            if False:\n                held.setdefault(row, set())"),
    ("touched-no-cap-per-file", "[:PER_FILE]", "[:]"),
    ("touched-cap-keeps-the-first", 'key=lambda s: (-s["changed"], s["line"], s["ref"]))[:PER_FILE]', 'key=lambda s: (s["line"], s["ref"]))[:PER_FILE]'),
    ("touched-catalog-is-code", "        if name.startswith(NOT_CODE):\n            continue\n        if not (root", "        if not (root"),
    ("touched-untracked-dropped", 'git_names(root, "ls-files", "--others", "--exclude-standard", "-z")', "[]"),
    ("touched-uncommitted-dropped", '"diff", "--name-only", "--no-renames", "-z", base, "--")', '"diff", "--name-only", "--no-renames", "-z", base, "HEAD", "--")'),
    ("touched-deletion-not-counted", "            changed.add(max(start, 1))", "            pass"),
    ("touched-deleted-file-not-named", "            deleted.append(name)\n", "            pass\n"),
    ("touched-config-base-ignored", "                ref = match.group(1).strip(\"\\\"'\").strip()", "                pass"),
    ("touched-dash-base-reaches-git", '    if ref.startswith("-"):\n        # git would read it', '    if False:\n        # git would read it'),
    ("touched-file-lines-go-to-a-symbol", "row = rows[at] if at >= 0 and rows[at][1] else None", "row = rows[max(at, 0)]"),
    ("touched-class-not-named", '            symbol["class"] = row[3]', "            pass"),
    ("touched-reads-an-old-graph", "    if state is None:\n        return degraded(why, base=ref", "    if False:\n        return degraded(why, base=ref"),
    ("touched-no-lines-without-the-graph", "return degraded(why, base=ref, files=plain, deleted=deleted)", "return degraded(why, base=ref)"),
    ("touched-unmodelled-files-dropped", "            other.append(item)\n", "            pass\n"),
    ("touched-package-node-is-a-symbol", ' or node.get("type") == "package"', ""),
]
# What clarify gets before its first question, checked with its own module alone.
CLARIFY_MUTANTS = [
    ("clarify-context-stops-without-a-feature", "    except (CapError, ValueError, AttributeError):\n        change = None\n", "    except ZeroDivisionError:\n        change = None\n"),
    ("clarify-context-feature-from-outside", "        feature = source_of(root, change)\n    except (CapError", "        feature = str(change)\n    except (CapError"),
    ("clarify-context-leaks-the-raw-delta", 'if key != "raw"}', 'if True}'),
    ("clarify-context-hides-delta-errors", "delta=delta, delta_errors=errors, slice=slice_of))", "delta=delta, delta_errors=[], slice=slice_of))"),
    ("clarify-context-spec-without-the-file", "    if text is not None:\n        spec = ", "    if True:\n        spec = "),
    ("clarify-context-without-the-catalog", "return emit(dict(catalog_summary(root), feature=feature", "return emit(dict({}, feature=feature"),
]
# In capabilities.py, also checked with test_graph_gate.py alone.
GATE_DOOR_MUTANTS = [
    ("graph-exit-code-lost", "str(gate), *args], check=False).returncode", "str(gate), *args], check=False).returncode and 0"),
]
# The slices: the maps, what a spec says about its slice, and the state read from the project.
# Each one is checked with test_slices.py alone.
SLICE_MODULES = ["test_slices.py"]
SLICE_MUTANTS = [
    # The shape of a map.
    ("slices-conflict-markers-read", '    if cap.has_conflict(text):\n        errors.append("merge conflict markers', '    if False:\n        errors.append("merge conflict markers'),
    ("slices-newer-map-read", "    if max(versions) > MAP_FORMAT:", "    if False:"),
    ("slices-any-heading-is-a-slice", '            if not SLICE_ID.fullmatch(slice_id):\n                errors.append("heading is not a slice', '            if False:\n                errors.append("heading is not a slice'),
    ("slices-map-comments-are-read", "    for line in strip_comments(text).splitlines():", "    for line in text.splitlines():"),
    ("slices-later-line-unchecked", '            elif line.strip():\n                errors.append("line in ## Later', '            elif False:\n                errors.append("line in ## Later'),
    ("slices-field-on-two-lines", '            if line.strip():\n                errors.append("%s: unexpected line, a field takes one line', '            if False:\n                errors.append("%s: unexpected line, a field takes one line'),
    ("slices-unknown-field-accepted", "        if key not in REQUIRED + OPTIONAL:", "        if False:"),
    ("slices-field-twice-accepted", '        elif key in current["fields"]:', "        elif False:"),
    ("slices-required-field-optional", '        if not fields.get(key):\n            errors.append("%s: field %s is missing"', '        if False:\n            errors.append("%s: field %s is missing"'),
    ("slices-title-optional", '    if not item["title"]:', "    if False:"),
    ("slices-depends-takes-anything", '    errors.extend("%s: Depends-On takes slice ids or none: %s" % (slice_id, part) for part in wrong)', "    pass"),
    ("slices-rules-takes-anything", '    errors.extend("%s: Rules takes rule ids or none: %s" % (slice_id, part) for part in wrong)', "    pass"),
    ("slices-kind-takes-anything", '        else:\n            errors.append("%s: Kind takes', '        elif False:\n            errors.append("%s: Kind takes'),
    ("slices-stories-takes-anything", '    errors.extend("%s: Stories takes story ids or none: %s" % (slice_id, part) for part in wrong)', "    pass"),
    ("slices-screens-takes-anything", '    errors.extend("%s: Screens takes screen ids or none: %s" % (slice_id, part) for part in wrong)', "    pass"),
    ("slices-stories-not-kept", '        "stories": stories,', '        "stories": [],'),
    ("slices-screens-not-kept", '        "screens": screens,', '        "screens": [],'),
    ("slices-screens-read-as-stories", '    screens, wrong = listed(fields.get("screens", "none"), SCREEN_ID)', '    screens, wrong = listed(fields.get("stories", "none"), SCREEN_ID)'),
    ("slices-clarify-forgets-the-stories", '        "stories": found[1]["stories"] if found else [],', '        "stories": [],'),
    ("slices-clarify-forgets-the-screens", '        "screens": found[1]["screens"] if found else [],', '        "screens": [],'),
    # What a map names.
    ("slices-id-reused", "            if slice_id in seen:\n", "            if False:\n"),
    ("slices-depends-on-itself", '                if dep == slice_id:\n                    hard.append("%s: %s depends on itself"', '                if False:\n                    hard.append("%s: %s depends on itself"'),
    ("slices-unknown-dependency", "                elif dep not in project.by_id:\n", "                elif False:\n"),
    ("slices-dropped-dependency", '                elif project.by_id[dep][1]["dropped"] and not item["dropped"]:', "                elif False:"),
    ("slices-forward-dependency", "                elif project.by_id[dep][0] is found and dep not in earlier:", "                elif False:"),
    ("slices-cycles-off", "    hard.extend(cycles(project))", "    pass"),
    ("slices-unknown-rule", '                if rule_id not in project.rules and rule_id not in project.retired:\n                    hard.append("%s: %s names', '                if False:\n                    hard.append("%s: %s names'),
    ("slices-retired-rule-unknown", '                if rule_id not in project.rules and rule_id not in project.retired:\n                    hard.append("%s: %s names', '                if rule_id not in project.rules:\n                    hard.append("%s: %s names'),
    ("slices-dropped-slice-checks-its-rules", '            if item["dropped"]:\n                continue\n            for rule_id in item["rules"]:', '            for rule_id in item["rules"]:'),
    ("slices-dropped-slice-keeps-its-rules", '                if not item["dropped"]:\n                    for rule_id in item["rules"]:\n                        self.owner', '                if True:\n                    for rule_id in item["rules"]:\n                        self.owner'),
    ("slices-later-unknown-rule", '            if entry["rule"] not in project.rules and entry["rule"] not in project.retired:', "            if False:"),
    ("slices-later-and-a-slice", '            if entry["rule"] in project.owner:', "            if False:"),
    ("slices-rule-in-two-slices", "        if len(owners) > 1:", "        if False:"),
    ("slices-enabler-silent", '            if item["enabler"]:', "            if False:"),
    ("slices-unassigned-everywhere", "    for rule_id in project.unassigned(touched):", "    for rule_id in project.unassigned():"),
    ("slices-later-does-not-assign", " and rule_id not in later and ", " and "),
    ("slices-built-rules-wait-for-a-slice", '            if rule["designed"] and rule_id not in self.owner', "            if rule_id not in self.owner"),
    # What a spec says about its slice.
    ("slices-declaration-reads-comments", 'raw = cap.section(strip_comments(text), "Slice")', 'raw = cap.section(text, "Slice")'),
    ("slices-missing-line-accepted", '    if not value:\n        return declared, ["## Slice names no slice', '    if value is None and False:\n        return declared, ["## Slice names no slice'),
    ("slices-placeholder-accepted", '    if value.startswith("["):', "    if False:"),
    ("slices-any-value-is-a-slice", "    elif SLICE_ID.fullmatch(value):", "    elif True:"),
    ("slices-declaration-errors-lost", '        hard.extend("%s: %s" % (spec["spec"], error) for error in spec["errors"])', "        pass"),
    ("slices-spec-names-any-slice", "        if named and named not in project.by_id:", "        if False:"),
    ("slices-spec-names-a-dropped-slice", '        elif named and project.by_id[named][1]["dropped"]:', "        elif False:"),
    ("slices-spec-builds-any-rule", "            if owners and named not in owners:", "            if False:"),
    ("slices-two-specs-one-slice", "        if len(claims) > 1:", "        if False:"),
    ("slices-catalog-is-a-spec", 'if source.startswith((cap.CATALOG + "/", MAPS + "/")) or any(', "if any("),
    ("slices-old-spec-that-builds-is-skipped", "            if declared is None and not built:\n", "            if declared is None:\n"),
    ("slices-feature-roots-ignored", '        for pattern in self.config["feature_roots"]:', '        for pattern in ["specs"]:'),
    # The state.
    ("slices-delivered-without-the-fold", "        if tasks == 0 and (folded or not entries):", "        if tasks == 0:"),
    ("slices-delivered-with-open-tasks", "        if tasks == 0 and (folded or not entries):", "        if folded or not entries:"),
    ("slices-folded-without-tasks-is-specified", '            return "delivered" if folded else "specified"', '            return "specified"'),
    ("slices-dropped-is-pending", '        if item["dropped"]:\n            return "dropped"', '        if False:\n            return "dropped"'),
    ("slices-next-ignores-dependencies", '        waiting = [dep for dep in item["depends_on"] if dep not in self.by_id or self.state(self.by_id[dep][1]) != "delivered"]', "        waiting = []"),
    ("slices-ready-with-a-spec", 'ready=state == "pending" and not waiting', "ready=not waiting"),
    ("slices-issues-off", '                if rule and rule["designed"] and rule_id not in claims[0]["changes"]:', "                if False:"),
    # show, status and the invocation.
    ("slices-show-a-dropped-slice", '    if item["dropped"]:\n        raise cap.CapError("slice %s was dropped', '    if False:\n        raise cap.CapError("slice %s was dropped'),
    ("slices-show-has-spec-is-ok", 'status = "has-spec" if view["spec"] else "blocked" if view["waiting_for"] else "ok"', 'status = "blocked" if view["waiting_for"] else "ok"'),
    ("slices-show-blocked-is-ok", 'status = "has-spec" if view["spec"] else "blocked" if view["waiting_for"] else "ok"', 'status = "has-spec" if view["spec"] else "ok"'),
    ("slices-show-exit-code-lost", 'cap.OK if status == "ok" else cap.DECISION)', "cap.OK)"),
    ("slices-show-offers-built-rules", 'if rule_id in project.rules and project.rules[rule_id]["designed"]]', "if rule_id in project.rules]"),
    ("slices-aim-drops-what-comes-in", '    if view["in"]:\n        lines.append("In: %s" % view["in"])', '    if False:\n        lines.append("In: %s" % view["in"])'),
    ("slices-aim-drops-the-stories", '    if view["stories"]:\n        lines.append("Stories of the design', '    if False:\n        lines.append("Stories of the design'),
    ("slices-aim-drops-the-screens", '    if view["screens"]:\n        lines.append("Screens of the design', '    if False:\n        lines.append("Screens of the design'),
    ("slices-aim-always-names-stories", '    if view["stories"]:\n        lines.append("Stories of the design', '    if True:\n        lines.append("Stories of the design'),
    ("slices-aim-always-names-screens", '    if view["screens"]:\n        lines.append("Screens of the design', '    if True:\n        lines.append("Screens of the design'),
    ("slices-aim-forgets-the-siblings", 'ask about it or build it: %s" % siblings,', 'ask about it or build it: %s" % "none",'),
    ("slices-aim-forgets-the-state-of-a-dependency", '", ".join("%s (%s)" % (dep["id"], dep["state"]) for dep in depends)', '", ".join(dep["id"] for dep in depends)'),
    ("slices-aim-forgets-the-rules", '("".join("\\n- %s: %s" % (rule["id"], rule["text"]) for rule in rules) or " none")', '" none"'),
    ("slices-aim-forgets-what-the-spec-writes", '        write.rstrip("\\n"),\n    ]', '        "",\n    ]'),
    ("slices-show-lists-dropped-siblings", 'if other["id"] != slice_id and not other["dropped"]]', 'if other["id"] != slice_id]'),
    ("slices-check-exit-code-lost", "cap.HARD if hard else cap.OK)", "cap.OK)"),
    ("slices-unknown-map-is-empty", '        if not maps:\n            raise cap.CapError("slice map not found', '        if False:\n            raise cap.CapError("slice map not found'),
    ("slices-newer-catalog-read", "        if problem:\n            raise cap.CapError(problem)", "        if False:\n            raise cap.CapError(problem)"),
    ("slices-show-without-an-id", '    if args.command == "show" and len(args.ids) != 1:', '    if args.command == "show" and len(args.ids) < 1:'),
    ("slices-status-takes-ids", '    if args.command != "show" and args.ids:', "    if False:"),
    ("slices-map-option-anywhere", '    if args.map is not None and args.command not in ("status", "next"):', "    if False:"),
    # next: the slice to build now.
    ("next-walks-maps-that-disagree", '    if hard:\n        return cap.emit({"status": "invalid", "hard": hard}, cap.HARD)', '    if False:\n        return cap.emit({"status": "invalid", "hard": hard}, cap.HARD)'),
    ("next-without-a-map-says-done", '    if not project.maps:\n        raise cap.CapError("no slice map under', '    if False:\n        raise cap.CapError("no slice map under'),
    ("next-unknown-map-says-done", "    if wanted and not maps:\n        raise cap.CapError", "    if False:\n        raise cap.CapError"),
    ("next-map-by-name-only", 'maps = [found for found in project.maps if wanted in (found["name"], found["map"])] if wanted else project.maps', 'maps = [found for found in project.maps if wanted == found["name"]] if wanted else project.maps'),
    ("next-picks-among-several-maps", "    if len(open_maps) > 1:", "    if False:"),
    ("next-counts-dropped-slices", 'for view in found_views if view["state"] != "dropped"]', "for view in found_views]"),
    ("next-ready-has-no-reason", 'status="ok", reason="ready",', 'status="ok", reason=None,'),
    ("next-waiting-is-done", 'reason = "waiting" if pending else "in-progress" if started else "done"', 'reason = "in-progress" if started else "done"'),
    ("next-started-is-done", 'reason = "waiting" if pending else "in-progress" if started else "done"', 'reason = "waiting" if pending else "done"'),
    ("next-blocker-without-its-state", '            return "%s (%s)" % (dep, project.state(project.by_id[dep][1]))', "            return dep"),
    ("next-ignores-the-environment", "args.map or os.environ.get(MAP_ENV) or None)", "args.map or None)"),
    ("next-environment-wins", "args.map or os.environ.get(MAP_ENV) or None)", "os.environ.get(MAP_ENV) or args.map or None)"),
    ("next-map-option-refused", '    if args.map is not None and args.command not in ("status", "next"):', '    if args.map is not None and args.command != "status":'),
    # The size of a spec.
    ("size-stories-not-counted", '"stories": len(STORY.findall(plain)),', '"stories": 1,'),
    ("size-criteria-counted-as-requirements", 'sum(1 for key in ids if key.startswith("FR-")),', 'sum(1 for key in ids if key.startswith(("FR-", "SC-"))),'),
    ("size-rules-not-counted", 'len([entry for entry in delta["entries"] if entry["op"] != "REOBSERVED"]) if delta else 0', "0"),
    ("size-counts-a-rule-observed-again", 'len([entry for entry in delta["entries"] if entry["op"] != "REOBSERVED"]) if delta else 0', 'len(delta["entries"]) if delta else 0'),
    ("size-only-open-tasks-count", 'TASK = re.compile(r"^\\s*- \\[[ xX]\\] ", re.M)', 'TASK = re.compile(r"^\\s*- \\[ \\] ", re.M)'),
    ("size-any-bullet-is-a-task", 'TASK = re.compile(r"^\\s*- \\[[ xX]\\] ", re.M)', 'TASK = re.compile(r"^\\s*- ", re.M)'),
    ("size-comments-are-counted", "    plain = strip_comments(text)\n    ids = cap.spec_sections(plain)", "    plain = text\n    ids = cap.spec_sections(plain)"),
    ("size-commented-tasks-are-counted", "len(TASK.findall(strip_comments(tasks)))", "len(TASK.findall(tasks))"),
    ("size-at-the-budget-is-over", "if held[what] is not None and held[what] > limit:", "if held[what] is not None and held[what] >= limit:"),
    ("size-config-ignored", "            limits[what] = int(value)", "            limits[what] = default"),
    ("size-zero-is-a-budget", 'elif re.fullmatch(r"[1-9]\\d*", value):', 'elif re.fullmatch(r"\\d+", value):'),
    ("size-any-text-is-a-budget", '            raise cap.CapError("slice_max_%s in %s takes a whole number above 0', '            limits[what] = default\n            continue\n            raise cap.CapError("slice_max_%s in %s takes a whole number above 0'),
    ("size-accepted-whatever-it-grows", 'settled = all("accepted" in item and item["count"] <= item["accepted"] for item in over)', 'settled = all("accepted" in item for item in over)'),
    ("size-accepted-without-a-number", 'settled = all("accepted" in item and item["count"] <= item["accepted"] for item in over)', 'settled = accepted is not None and all(item["count"] <= item.get("accepted", item["count"]) for item in over)'),
    ("size-accept-without-a-reason", '    if not reason:\n        raise cap.CapError("accept takes --reason', '    if False:\n        raise cap.CapError("accept takes --reason'),
    ("size-accept-writes-when-within", '    if size["status"] != "within":\n        written', "    if True:\n        written"),
    ("size-reason-kept-as-typed", '    reason = cap.norm(reason or "")\n    if not reason:', '    reason = (reason or "").strip()\n    if not reason:'),
    ("size-budget-file-by-hand-read", '    if not fine:\n        raise cap.CapError("%s/%s cannot be read', '    if False:\n        raise cap.CapError("%s/%s cannot be read'),
    ("size-empty-reason-read", "fine = isinstance(reason, str) and bool(reason.strip()) and all(", "fine = isinstance(reason, str) and all("),
    ("size-text-number-read", "numbers[what] is None or type(numbers[what]) is int for what in BUDGET)", "what in numbers for what in BUDGET)"),
    ("size-check-measures-delivered-specs", '        if not spec["declared"] or spec["state"] == "delivered":\n            continue', '        if not spec["declared"]:\n            continue'),
    ("size-check-measures-old-specs", '        if not spec["declared"] or spec["state"] == "delivered":\n            continue', '        if spec["state"] == "delivered":\n            continue'),
    ("size-check-drops-the-note", '        if size["status"] == "over":\n            notes.append', "        if False:\n            notes.append"),
    ("size-check-notes-what-was-accepted", '        if size["status"] == "over":\n            notes.append', '        if size["status"] != "within":\n            notes.append'),
    ("size-check-swallows-a-bad-budget", "    except cap.CapError as error:\n        return [str(error)], []", "    except cap.CapError:\n        return [], []"),
    ("size-check-swallows-a-bad-file", "        except cap.CapError as error:\n            hard.append(str(error))\n            continue", "        except cap.CapError:\n            continue"),
    ("size-line-joins-with-and-only", 'return " and ".join(part for part in (", ".join(words[:-1]), words[-1]) if part) if words else ""', 'return " and ".join(words)'),
    ("size-grown-not-named", 'if "accepted" in item and item["count"] > item["accepted"]]', "if False]"),
    ("size-clarify-lists-dropped-siblings", 'if other["id"] != declared["slice"] and not other["dropped"]] if found else []', 'if other["id"] != declared["slice"]] if found else []'),
    ("size-change-on-any-command", '    if args.change is not None and args.command not in ("measure", "accept"):', "    if False:"),
    ("size-reason-on-any-command", '    if args.reason is not None and args.command != "accept":', "    if False:"),
    # A spec found by the slice it builds, for a loop that walks a map.
    ("size-slice-unknown-accepted", '    if slice_id not in project.by_id:\n        raise cap.CapError("no slice map defines', '    if False:\n        raise cap.CapError("no slice map defines'),
    ("size-slice-two-specs-first-wins", "    if len(claims) != 1:", "    if not claims:"),
    ("size-slice-without-a-spec-crashes", "    if len(claims) != 1:", "    if len(claims) > 1:"),
    ("size-slice-ignores-the-environment", "slice_id = args.slice or (None if args.change else os.environ.get(SLICE_ENV) or None)", "slice_id = args.slice or None"),
    ("size-slice-environment-wins-over-the-option", "slice_id = args.slice or (None if args.change else os.environ.get(SLICE_ENV) or None)", "slice_id = (None if args.change else os.environ.get(SLICE_ENV) or None) or args.slice"),
    ("size-slice-environment-wins-over-a-named-spec", "slice_id = args.slice or (None if args.change else os.environ.get(SLICE_ENV) or None)", "slice_id = args.slice or os.environ.get(SLICE_ENV) or None"),
    ("size-measure-ignores-the-slice", "return cmd_measure(cap, project, args.change, slice_id)", "return cmd_measure(cap, project, args.change)"),
    ("size-accept-ignores-the-slice", "return cmd_accept(cap, project, args.change, args.reason, slice_id)", "return cmd_accept(cap, project, args.change, args.reason)"),
    ("size-slice-on-any-command", '    if args.slice is not None and args.command not in ("measure", "accept"):', "    if False:"),
    ("size-slice-with-a-named-spec", "    if args.slice is not None and args.change is not None:", "    if False:"),
    ("size-does-not-say-what-is-left-to-clarify", "    if left:\n        said +=", "    if False:\n        said +="),
    ("size-counts-a-mark-inside-a-comment", 'return strip_comments(cap.read(change / cap.DOCS[0]) or "").count("[NEEDS CLARIFICATION")',
     'return (cap.read(change / cap.DOCS[0]) or "").count("[NEEDS CLARIFICATION")'),
    ("size-says-points-for-one-point", '"1 point is" if left == 1 else "%d points are" % left', '"%d points are" % left'),
    ("size-forgets-how-many-are-left", '"accepted": accepted, "unclear": left, "summary": said}', '"accepted": accepted, "unclear": 0, "summary": said}'),
]
# In capabilities.py, also checked with test_slices.py alone.
SLICE_DOOR_MUTANTS = [
    ("clarify-context-forgets-the-slice", "delta_errors=errors, slice=slice_of))", "delta_errors=errors, slice=None))"),
    ("check-skips-the-slices", "        self.check_slices()\n", "        pass\n"),
    ("check-loses-the-slice-failures", "        self.hard.extend(hard)\n        self.notes.extend(notes)\n", "        self.notes.extend(notes)\n"),
    ("check-loses-the-slice-notes", "        self.hard.extend(hard)\n        self.notes.extend(notes)\n", "        self.hard.extend(hard)\n"),
]


COVERAGE_MODULES = ["test_coverage.py"]
COVERAGE_MUTANTS = [
    ("coverage-counts-the-forks-own-files", "        if name.startswith(NOT_PRODUCT) or posixpath", "        if posixpath"),
    ("coverage-counts-git-settings", " or posixpath.basename(name) in NOT_PRODUCT_NAMES or", " or"),
    ("coverage-counts-markdown", ' or name.lower().endswith(".md"):\n            continue\n        if any', ':\n            continue\n        if any'),
    ("coverage-ignores-coverage-ignore", "        if any(fnmatch.fnmatchcase(name, pattern) for pattern in ignore):", "        if False:"),
    ("coverage-maps-code-but-not-tests", 'for ref in row["code"] + row["tests"]:\n                owners', 'for ref in row["code"]:\n                owners'),
    ("coverage-takes-a-review-for-a-fold", 'RECORDED = ("prepared", "ready", "delivered", "no-rule-change")', 'RECORDED = ("prepared", "ready", "delivered", "no-rule-change", "reviewed")'),
    ("coverage-misses-no-rule-change", 'RECORDED = ("prepared", "ready", "delivered", "no-rule-change")', 'RECORDED = ("prepared", "ready", "delivered")'),
    ("coverage-never-says-missing", '    else:\n        status = "missing"', '    else:\n        status = "recorded"'),
    ("coverage-hides-pending-changes", '    if pending:\n        status = "unrecorded"', '    if False:\n        status = "unrecorded"'),
    ("coverage-history-never-records", "if any(cells and cells[0] == source for cells in table_rows(", "if any(cells and cells[0] == source + '!' for cells in table_rows("),
    ("coverage-lists-specs-without-rules", 'if errors or delta is None or delta["none"] or is_design(delta):', 'if errors or delta is None or is_design(delta):'),
    ("coverage-reads-the-catalog-as-a-spec", 'for name in sorted(os.listdir(root / feature_root)) if not name.startswith(("_", "."))]', 'for name in sorted(os.listdir(root / feature_root))]'),
    ("coverage-skips-record-folders", "    if (root / CHANGES).is_dir():\n        folders +=", "    if False:\n        folders +="),
    ("coverage-hides-open-tasks", '"open_tasks": open_tasks(change) if (change / "spec.md").is_file() else 0', '"open_tasks": 0'),
    ("coverage-names-a-record-after-main", ' and name not in {base.split("/")[-1] for base in bases} else "change"', ' else "change"'),
    ("coverage-drops-the-base-flag", "return cmd_coverage(root, args.base)", "return cmd_coverage(root, None)"),
    ("coverage-hides-problems", '"problems": check.hard,', '"problems": [],'),
    ("record-waits-for-tasks", 'if tasks is None and not no_tasks and (change / "spec.md").is_file():', "if tasks is None and not no_tasks:"),
    ("spec-skips-its-tasks", 'if tasks is None and not no_tasks and (change / "spec.md").is_file():', "if tasks is None and not no_tasks and False:"),
    ("feature-error-names-no-change", "\\nName the change with --change <folder>, such as a spec merged without its fold or a record under %s/.\" % (done.stderr.strip() or done.stdout.strip(), CHANGES))", "\" % (done.stderr.strip() or done.stdout.strip()))"),
]

# Part C: what check notes when work skipped its fold, the requirements review finds unlinked, and the Stop hook of the agent.
DEFENSE_MODULES = ["test_defenses.py"]
DEFENSE_MUTANTS = [
    ("defense-done-means-no-task-at-all", '        if state != "prepared" and tasks == 0:', '        if state != "prepared" and tasks == 0 and not fold_tasks(change):'),
    ("defense-done-ignores-drafts", '        if state != "prepared" and tasks == 0:', '        if state == "reviewed" and tasks == 0:'),
    ("defense-done-counts-no-tasks-md", '        if state != "prepared" and tasks == 0:', '        if state != "prepared" and not tasks:'),
    ("defense-code-ignores-coverage-ignore", "        code = product_files(self.names, coverage_ignore(self.config))", "        code = product_files(self.names, [])"),
    ("defense-code-forgets-records", "        if code and not self.states:", "        if code and not [s for s in self.states.values() if s != \"no-rule-change\"]:"),
    ("defense-code-never-noted", "        if code and not self.states:", "        if False:"),
    ("defense-merged-repeats-the-branch", '            if item["change"] in self.states:\n                continue\n            tasks = item', '            tasks = item'),
    ("defense-merged-never-noted", "        for item in unrecorded(self.root, self.config):", "        for item in []:"),
    ("defense-merged-hard-in-ci", '            self.notes.append("%s: merged without its fold', '            self.soft("%s: merged without its fold'),
    ("defense-designed-owes-code", '                if rule["designed"] or (capability, rule_id) in self.covered:', '                if (capability, rule_id) in self.covered:'),
    ("defense-no-block-is-fine", "                if row is None or not row[\"code\"]:", "                if row is not None and not row[\"code\"]:"),
    ("defense-empty-code-is-fine", "                if row is None or not row[\"code\"]:", "                if row is None:"),
    ("defense-gone-code-not-checked", "                gone = [ref for ref in row[\"code\"] if not anchor_resolves(self.root, ref)]", "                gone = []"),
    ("defense-gone-repeats-touched", "                if touched & {anchor_file(ref) for ref in row[\"code\"] + row[\"tests\"]}:\n                    continue  #", "                if False:\n                    continue  #"),
    ("review-unlinked-counts-links", '    return sorted(key for key in spec_sections(text) if key.startswith("FR-") and key not in linked)', '    return sorted(key for key in spec_sections(text) if key.startswith("FR-"))'),
    ("review-unlinked-counts-scenarios", '    return sorted(key for key in spec_sections(text) if key.startswith("FR-") and key not in linked)', '    return sorted(key for key in spec_sections(text) if key.startswith(("FR-", "US")) and key not in linked)'),
    ("review-unlinked-only-when-stamped", '    return emit({"status": "unchanged", "unlinked": unlinked_requirements(text, delta)})', '    return emit({"status": "unchanged", "unlinked": []})'),
    ("stop-ignores-the-loop-guard", '    if not isinstance(payload, dict) or payload.get("stop_hook_active"):', '    if not isinstance(payload, dict):'),
    ("stop-ignores-off", '    if mode not in STOP_MODES or mode == "off" or', '    if mode not in STOP_MODES or'),
    ("stop-warn-repeats", '    if mode == "warn" and memory is not None:\n        if read(memory) == said:', '    if mode == "warn" and memory is not None:\n        if False:'),
    ("stop-block-remembers", '    if mode == "warn" and memory is not None:', '    if memory is not None:'),
    ("stop-nags-a-spec-being-built", "        if tasks is None or tasks:\n            continue", "        if tasks is None:\n            continue"),
    ("stop-misses-missing-code", '    if report["status"] == "missing":', '    if False:'),
    ("stop-misses-finished-specs", "    for source in report[\"pending\"]:", "    for source in []:"),
    ("stop-memory-in-the-project", '    return (root / rel) if rel else None', '    return (root / "speckit-capabilities-stop") if rel else None'),
]


def main():
    wanted = set(sys.argv[1:])
    survivors = 0
    with tempfile.TemporaryDirectory(prefix="cap-mutants-") as directory:
        for name, old, new in MUTANTS:
            if wanted and name not in wanted:
                continue
            status, detail = run_mutant(name, old, new, Path(directory), sys.executable)
            if status != "killed":
                survivors += 1
            print("%-36s %-8s %s" % (name, status, detail), flush=True)
        groups = (
            (GATE_MUTANTS, "cap_graph.py", GATE_MODULES),
            (GATE_DOOR_MUTANTS, "capabilities.py", GATE_MODULES),
            (CLARIFY_MUTANTS, "capabilities.py", CLARIFY_MODULES),
            (SLICE_MUTANTS, "cap_slices.py", SLICE_MODULES),
            (SLICE_DOOR_MUTANTS, "capabilities.py", SLICE_MODULES),
            (COVERAGE_MUTANTS, "capabilities.py", COVERAGE_MODULES),
            (DEFENSE_MUTANTS, "capabilities.py", DEFENSE_MODULES),
        )
        for group, target, modules in groups:
            for name, old, new in group:
                if wanted and name not in wanted:
                    continue
                status, detail = run_mutant(name, old, new, Path(directory), sys.executable, target=target, modules=modules)
                if status != "killed":
                    survivors += 1
                print("%-36s %-8s %s" % (name, status, detail), flush=True)
    print("%d not killed" % survivors, flush=True)
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
