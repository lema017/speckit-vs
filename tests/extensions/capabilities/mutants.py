"""Prove the acceptance tests have teeth: remove each control and require a failure.

Not collected by pytest. Run it by hand from the repository root:

    .venv/bin/python tests/extensions/capabilities/mutants.py [name ...]

Each mutant is one exact replacement in a temporary copy of the extension. A
mutant that no test catches is a control nothing is really testing, so the run
exits with 1.
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
    ("scaffold-allows-pipe", 'if not covers or "|" in covers:', "if not covers:"),
    ("scaffold-allows-any-name", "if not capability or not CAPABILITY.match(capability):", "if not capability:"),
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
    done = subprocess.run(
        [python, "-m", "pytest", *tests, "--rootdir", str(ROOT), "-n", "8", "-x", "-q", "-p", "no:cacheprovider", "--tb=no"],
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
    ("anchors-not-rechecked", 'self.notes.append("%s: anchored code changed without a delta" % rule_id)\n                for ref in row["code"] + row["tests"]:', 'self.notes.append("%s: anchored code changed without a delta" % rule_id)\n                for ref in []:'),
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
    ("implemented-owes-no-evidence", 'elif entry["op"] in ("ADDED", "MODIFIED", "IMPLEMENTED"):', 'elif entry["op"] in ("ADDED", "MODIFIED"):'),
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
    ("keep-on-a-retired-rule", 'if said is not None and said["text"] != entry["to"]:', 'if said is None or said["text"] != entry["to"]:'),
    ("rebase-does-not-reseal", '                plan[source + "/" + LOCK_NAME] = dumps(relocked(lock, new_text, new_delta, source, {entry["id"] for entry in dropped}))', "                pass"),
    ("rebase-loses-other-folds", '        if others:\n            raise CapError("this branch also folded', '        if False:\n            raise CapError("this branch also folded'),
    ("defer-leaves-the-catalog", "plan, conflicts = rebased_plan(root, source, new_delta, touched, start, here, start, True)", "plan, conflicts = {}, []"),
    ("defer-rebuilds-from-the-working-tree", "            start = reader(root, point)\n", "            start = here\n"),
]

# The door to Graphify. Each one is checked with test_graph_gate.py alone.
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
    ("clarify-context-hides-delta-errors", "delta=delta, delta_errors=errors))", "delta=delta, delta_errors=[]))"),
    ("clarify-context-spec-without-the-file", "    if text is not None:\n        spec = ", "    if True:\n        spec = "),
    ("clarify-context-without-the-catalog", "return emit(dict(catalog_summary(root), feature=feature", "return emit(dict({}, feature=feature"),
]
# In capabilities.py, also checked with test_graph_gate.py alone.
GATE_DOOR_MUTANTS = [
    ("graph-exit-code-lost", "str(gate), *args], check=False).returncode", "str(gate), *args], check=False).returncode and 0"),
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
        for group, target, modules in ((GATE_MUTANTS, "cap_graph.py", GATE_MODULES), (GATE_DOOR_MUTANTS, "capabilities.py", GATE_MODULES), (CLARIFY_MUTANTS, "capabilities.py", CLARIFY_MODULES)):
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
