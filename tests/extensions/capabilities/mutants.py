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
]

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
    ("old-report-accepted", "if moment < head_time - REPORT_SKEW_SECONDS:", "if False:"),
    ("tracked-report-accepted", 'if git(self.root, "ls-files", "--error-unmatch", "--", str(path)) is not None:', "if False:"),
    ("skipped-counts-as-passed", 'child.tag in ("failure", "error", "skipped")', 'child.tag in ("failure", "error")'),
    ("one-variant-is-enough", 'return "passed" if all(case[2] for case in hits) else "failed"', 'return "passed" if any(case[2] for case in hits) else "failed"'),
    ("any-module-matches", 'and (case[1] == expected or case[1].endswith("." + expected))', ""),
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


def run_mutant(name, old, new, workdir, python):
    copy = workdir / name
    shutil.copytree(str(EXT), str(copy))
    script = copy / "scripts" / "python" / "capabilities.py"
    source = script.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        return "stale", "the text to replace occurs %d times" % count
    script.write_text(source.replace(old, new), encoding="utf-8")
    env = dict(os.environ, CAP_TEST_SCRIPT=str(script))
    tests = [str(ROOT / "tests" / "extensions" / "capabilities" / module) for module in MODULES]
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
    print("%d not killed" % survivors, flush=True)
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
