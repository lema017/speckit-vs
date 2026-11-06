"""The checks behind ``specify progress doctor``: is the progress view really working here?"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

from ..events import PROGRESS_HOOK_PREFIX
from ..integrations import INTEGRATION_REGISTRY
from ._engine import load_engine

OK = "ok"
WARN = "warn"
FAIL = "fail"
PROTOCOL_MARK = " done T"
WRAPPERS = {
    "sh": ("bash", ("progress.sh", "run-step.sh")),
    "ps": ("powershell", ("progress.ps1", "run-step.ps1")),
    "py": ("python", ("progress.py", "run_step.py")),
}
ENGINE_FILES = ("engine.py", "hook.py", "page.html", "index.html")
UPGRADE = "Run: specify integration upgrade"
SHARED_MANIFEST = "speckit"  # Spec Kit's own files, not an integration.


class Check(NamedTuple):
    level: str
    subject: str
    detail: str


def _script_type(root: Path) -> str | None:
    try:
        data = json.loads((root / ".specify" / "init-options.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    script = data.get("script") if isinstance(data, dict) else None
    return script if script in WRAPPERS else None


def check_files(root: Path) -> list[Check]:
    scripts = root / ".specify" / "scripts"
    missing = [name for name in ENGINE_FILES if not (scripts / "progress" / name).is_file()]
    if missing:
        return [Check(FAIL, "Engine", "Missing %s. %s" % (", ".join(missing), UPGRADE))]
    checks = [Check(OK, "Engine", "Installed in .specify/scripts/progress")]
    script = _script_type(root)
    if script is None:
        return checks
    folder, names = WRAPPERS[script]
    missing = [name for name in names if not (scripts / folder / name).is_file()]
    if missing:
        checks.append(Check(FAIL, "Wrappers", "Missing %s. %s" % (", ".join(missing), UPGRADE)))
    else:
        checks.append(Check(OK, "Wrappers", "Installed for %s" % folder))
    return checks


def _python_works(candidate: list[str]) -> bool:
    if shutil.which(candidate[0]) is None:
        return False
    probe = "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
    try:
        return subprocess.run([*candidate, "-c", probe], capture_output=True, timeout=20, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def check_python() -> list[Check]:
    for candidate in (["python3"], ["python"], ["py", "-3"]):
        if _python_works(candidate):
            return [Check(OK, "Python", "%s is 3.9 or newer" % " ".join(candidate))]
    if shutil.which("specify"):
        return [Check(WARN, "Python", "No Python 3.9 or newer on PATH. The wrappers fall back to the specify command, and native events do not run.")]
    return [Check(FAIL, "Python", "No Python 3.9 or newer on PATH and no specify command. The page cannot be drawn.")]


def check_spec(root: Path) -> list[Check]:
    engine = load_engine()
    feature = engine.current_feature_dir(root)
    if feature is None:
        return [Check(OK, "Current spec", "None yet")]
    checks = [Check(OK, "Current spec", feature.name)]
    log = feature / engine.LOG_NAME
    if log.is_symlink():
        return [*checks, Check(FAIL, "Log", "%s is a symbolic link, so nothing is written to it." % log)]
    if log.exists():
        _, bad, truncated = engine.read_events(log)
        if bad:
            checks.append(Check(WARN, "Log", "%d lines could not be understood. The page lists this too." % bad))
        if truncated:
            checks.append(Check(WARN, "Log", "It is over the size limit, so only its first part is read."))
        attributes = feature / engine.ATTRIBUTES_NAME
        if not attributes.is_file() or engine.LOG_NAME not in attributes.read_text(encoding="utf-8", errors="replace"):
            checks.append(Check(WARN, "Log", "No merge=union line in %s, so two branches can conflict over the log." % attributes))
    if not os.access(feature, os.W_OK):
        checks.append(Check(FAIL, "Spec folder", "%s cannot be written." % feature))
    return checks


def _implement_file(root: Path, key: str) -> Path | None:
    """The file holding this integration's /speckit.implement, from what it installed."""
    path = root / ".specify" / "integrations" / ("%s.manifest.json" % key)
    try:
        files = json.loads(path.read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError, AttributeError):
        return None
    for name in files:
        if "speckit-implement" in name or "speckit.implement" in name:
            return root / name
    return None


def _events_installed(root: Path, integration, key: str) -> bool:
    target = root / (".opencode/plugin/speckit-events.ts" if key == "opencode" else integration.events_config_file)
    try:
        return PROGRESS_HOOK_PREFIX + key in target.read_text(encoding="utf-8")
    except OSError:
        return False


def check_integration(root: Path, key: str) -> list[Check]:
    integration = INTEGRATION_REGISTRY.get(key)
    if integration is None:
        return [Check(WARN, key, "Not known to this version of Spec Kit.")]
    checks = []
    implement = _implement_file(root, key)
    if implement is not None:
        try:
            has_protocol = PROTOCOL_MARK in implement.read_text(encoding="utf-8")
        except OSError:
            has_protocol = False
        if not has_protocol:
            checks.append(Check(WARN, key, "Its implement command has no progress calls, perhaps because of a preset. The page still follows the boxes in tasks.md, but cannot say who did what."))
    if not integration.supports_events():
        checks.append(Check(OK, key, "No native events, so the page updates when a command calls it. Run specify progress watch for a live page."))
    elif not _events_installed(root, integration, key):
        checks.append(Check(WARN, key, "Native events are off, so the page updates only when a command calls it. Without --events false: specify integration upgrade %s" % key))
    elif key == "codex":
        checks.append(Check(WARN, key, "Native events are installed. Codex runs them only after you approve them with /hooks."))
    else:
        checks.append(Check(OK, key, "Native events are installed"))
    return checks


def check_browser(root: Path) -> list[Check]:
    engine = load_engine()
    if engine.browser_is_off(root):
        return [Check(OK, "Browser", "Pages stay closed until you open them. Turn it on with: specify progress browser on")]
    if not engine.can_open_browser():
        return [Check(OK, "Browser", "No browser can open from here, for example over SSH or in CI.")]
    return [Check(OK, "Browser", "A spec's page opens by itself the first time it is drawn.")]


def installed_integrations(root: Path) -> list[str]:
    suffix = ".manifest.json"
    folder = root / ".specify" / "integrations"
    keys = (path.name[: -len(suffix)] for path in folder.glob("*" + suffix))
    return sorted(key for key in keys if key != SHARED_MANIFEST)


def run_checks(root: Path) -> list[Check]:
    checks = [*check_files(root), *check_python(), *check_spec(root)]
    for key in installed_integrations(root):
        checks.extend(check_integration(root, key))
    return [*checks, *check_browser(root)]
