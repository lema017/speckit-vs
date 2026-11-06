"""Spec Kit progress hook: what a harness runs by itself, with no model and no tokens.

It runs after every tool call of a session, so it imports almost nothing and usually stops after
comparing a few file dates. Only when something changed does it load the engine and draw the page.

The dispatcher, .specify/events.py, runs this file inside its own process. Nothing here may raise
or print: a problem with the page must never reach the harness.
"""

import os
import sys

_CALL_MARK = b"progress."
_SOURCES = ("tasks.md", "progress.jsonl", "spec.md", "plan.md")
_SAFE_NAME_CHARS = "._-"


def current_spec(root):
    """The folder of the current spec, as far as a quick look can tell. None when there is none."""
    raw = os.environ.get("SPECIFY_FEATURE_DIRECTORY", "")
    if not raw:
        try:
            with open(os.path.join(root, ".specify", "feature.json"), encoding="utf-8") as stream:
                text = stream.read(64 * 1024)
        except (OSError, ValueError):
            text = ""
        if text:
            import json

            try:
                stored = json.loads(text)
            except ValueError:
                stored = None
            value = stored.get("feature_directory") if isinstance(stored, dict) else None
            raw = value if isinstance(value, str) else ""
    if not raw and os.environ.get("SPECIFY_FEATURE"):
        raw = os.path.join("specs", os.environ["SPECIFY_FEATURE"])
    if not raw:
        return None
    path = raw if os.path.isabs(raw) else os.path.join(root, raw)
    return path if os.path.isdir(path) else None


def page_name(folder):
    """The name the engine gives this spec's page, without the regular expression it uses for it."""
    name = ""
    for char in os.path.basename(os.path.normpath(folder)):
        safe = (char.isascii() and char.isalnum()) or char in _SAFE_NAME_CHARS
        if safe:
            name += char
        elif not name.endswith("_"):
            name += "_"
    return (name.strip("._") or "spec") + ".html"


def is_stale(root):
    """True when the page is older than what it shows. The same date counts as older."""
    folder = current_spec(root)
    if folder is None:
        return False
    try:
        drawn = os.stat(os.path.join(root, ".specify", "progress", page_name(folder))).st_mtime_ns
    except OSError:
        return True
    for name in _SOURCES:
        try:
            if os.stat(os.path.join(folder, name)).st_mtime_ns >= drawn:
                return True
        except OSError:
            pass
    return False


def load_engine():
    import importlib.util

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine.py")
    sys.dont_write_bytecode = True  # Bytecode next to the engine would show up in the project's Git.
    spec = importlib.util.spec_from_file_location("speckit_progress_engine", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(harness, event, raw, root):
    """Return one line for the model's context, or nothing. raw is the harness's message, in bytes."""
    if sys.version_info < (3, 9):
        return ""
    mentions_a_call = event == "post_tool_use" and _CALL_MARK in raw
    if event != "session_start" and not mentions_a_call and not is_stale(root):
        return ""
    return load_engine().run_hook(root, harness, event, raw)
