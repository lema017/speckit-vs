#!/usr/bin/env python3
"""The only door to Graphify, an optional code graph: where code is and what a change affects.

It never decides what a requirement is, and nothing else in the extension needs it. Graphify is
never installed from here. Standard library only, so any Python 3 can run it.

Only ``update``, ``explain``, ``affected`` and ``query`` reach the tool: never ``extract``,
``install``, ``watch``, hooks or ``--strict``. It runs without LLM keys in its environment.

Exit codes: 0 done, 2 invalid input, 6 Graphify cannot answer: use the anchors and ``rg``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

OK, INVALID, UNAVAILABLE = 0, 2, 6
PINNED = "0.9.102"
INSTALL = "uv tool install graphifyy==%s" % PINNED
GRAPH = "graphify-out/graph.json"
SCHEMA = 1
CATALOG = "specs/_capabilities"
UPDATE_SECONDS = 600
READ_SECONDS = 60
MAX_OUTPUT = 20000
IGNORED = (
    "tests/", "test/", "src/test/", "*.test.*", "*.spec.*", "docs/", "specs/", ".github/", ".claude/", ".specify/", ".devcontainer/",
    "target/", "build/", "dist/", "node_modules/", ".venv/", "graphify-out/", "*.md", "*.json",
)
KEPT_ENV = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "LC_CTYPE", "APPDATA", "LOCALAPPDATA")
CODE_LINE = re.compile(r"^- Code: (.*)$", re.M)
QUOTED = re.compile(r"`([^`]+)`")


def emit(obj, code=OK):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return code


def degraded(reason, **extra):
    return emit(dict({"status": "degraded", "reason": reason, "fallback": "use the anchors and rg", "install": INSTALL}, **extra), UNAVAILABLE)


def no_graph():
    return degraded("update-failed" if shutil.which("graphify") else "not-installed")


def graph_env():
    env = {key: os.environ[key] for key in KEPT_ENV if key in os.environ}
    env["GRAPHIFY_BACKEND"] = "none"
    env["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"
    return env


def tool(root, args, seconds):
    """(returncode, stdout, stderr), or None if it could not run or did not finish."""
    path = shutil.which("graphify")
    if path is None:
        return None
    try:
        done = subprocess.run([path, *args], cwd=str(root), env=graph_env(), capture_output=True, encoding="utf-8", errors="replace", timeout=seconds, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.returncode, done.stdout or "", done.stderr or ""


def version_of(root):
    done = tool(root, ["--version"], READ_SECONDS)
    match = re.search(r"\d+\.\d+\.\d+", done[1]) if done else None
    return match.group(0) if match else None


def version_warnings(version):
    return [] if version == PINNED else ["Graphify %s is not the validated %s" % (version or "of unknown version", PINNED)]


def ensure_ignores(root):
    """Never overwrites a choice of the project, and changes no tracked file: an agent can ask a question without leaving a diff."""
    wrote = []
    ignore = root / ".graphifyignore"
    if not ignore.exists() and not ignore.is_symlink():
        ignore.write_text("\n".join(IGNORED) + "\n", encoding="utf-8")
        wrote.append(".graphifyignore")
    out = root / "graphify-out"
    own = out / ".gitignore"
    if not out.is_symlink() and not own.exists() and not own.is_symlink():
        out.mkdir(exist_ok=True)
        own.write_text("*\n", encoding="utf-8")
        wrote.append("graphify-out/.gitignore")
    return wrote


def refresh(root):
    """``query`` does not say when the graph is old, so every read updates it first. Returns what to report, or None on failure."""
    if shutil.which("graphify") is None:
        return None
    try:
        wrote = ensure_ignores(root)
    except OSError:
        return None
    done = tool(root, ["update", "."], UPDATE_SECONDS)
    if done is None or done[0] != 0 or not (root / GRAPH).is_file():
        return None
    return {"wrote": wrote, "warnings": version_warnings(version_of(root))}


def load_index(root):
    """{(file, label): [node]}, or None if the graph is not the shape this script was validated with."""
    try:
        data = json.loads((root / GRAPH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    graph = data.get("graph") if isinstance(data, dict) else None
    nodes = data.get("nodes") if isinstance(data, dict) else None
    if not isinstance(graph, dict) or graph.get("schema_version") != SCHEMA or not isinstance(nodes, list):
        return None
    index = {}
    for node in nodes:
        if not isinstance(node, dict):
            return None
        if isinstance(node.get("source_file"), str) and isinstance(node.get("label"), str) and node["source_file"] and node["label"]:
            index.setdefault((node["source_file"], node["label"]), []).append(node)
    return index


def labels_of(symbol):
    return [symbol] if symbol.startswith(".") else [symbol, symbol + "()"]


def resolve(index, ref):
    path, _, symbol = ref.partition("::")
    if not symbol:
        return "unique" if any(key[0] == path for key in index) else "absent"
    found = sum(len(index.get((path, label), [])) for label in labels_of(symbol))
    return "unique" if found == 1 else "ambiguous" if found > 1 else "absent"


def named_in_file(root, ref):
    """Not a parse: the file exists and each symbol appears in it as a word, as anchor_resolves in capabilities.py reads it."""
    path, *symbols = ref.split("::")
    target = (root / path).resolve()
    if root not in target.parents or not target.is_file():
        return False
    text = target.read_bytes().decode("utf-8", "replace")
    names = [symbol.split("[")[0].strip(".()") for symbol in symbols]
    return all(re.search(r"(?<!\w)%s(?!\w)" % re.escape(name), text) for name in names if name)


def repeated_name(root, term):
    """In the spike every false caller came from a method whose name repeats across the code."""
    index = load_index(root)
    symbol = term.partition("::")[2] or term
    if index is None or not symbol:
        return None
    count = sum(len(nodes) for (_, label), nodes in index.items() if label in labels_of(symbol))
    return count if count > 1 else None


def code_anchors(root, capability):
    pattern = "%s/implementation.md" % (capability or "*")
    found = {}
    for path in sorted((root / CATALOG).glob(pattern)):
        for line in CODE_LINE.findall(path.read_text(encoding="utf-8", errors="replace")):
            for ref in QUOTED.findall(line) or [part.strip() for part in line.split(",") if part.strip() not in ("", "none")]:
                found.setdefault(ref, path.parent.name)
    return found


def cmd_status(root):
    if shutil.which("graphify") is None:
        return emit({"status": "degraded", "available": False, "fallback": "use the anchors and rg", "install": INSTALL, "pinned": PINNED})
    version = version_of(root)
    return emit({"status": "ok", "available": True, "version": version, "pinned": PINNED, "graph": (root / GRAPH).is_file(), "warnings": version_warnings(version)})


def cmd_update(root):
    state = refresh(root)
    if state is None:
        return no_graph()
    return emit(dict({"status": "ok", "graph": GRAPH}, **state))


def cmd_read(root, args, terms, depth, show_all):
    state = refresh(root)
    if state is None:
        return no_graph()
    warnings = state["warnings"]
    if args == "query":
        if any(ord(char) > 127 for term in terms for char in term):
            warnings.append("query works with technical English words: in Spanish it found 1 of 12 in the spike")
        call = ["query", " ".join(terms)]
    else:
        call = [args, terms[0]]
        if args == "explain" and show_all:
            call.append("--all")
        if args == "affected":
            call += ["--depth", str(depth)]
            repeats = repeated_name(root, terms[0])
            if repeats:
                warnings.append("%d nodes share this name: confirm the callers in the code" % repeats)
    done = tool(root, call, READ_SECONDS)
    if done is None:
        return degraded("read-failed")
    code, stdout, stderr = done
    if code == 4:
        return emit({"status": "not-found", "term": terms[0], "fallback": "use the anchors and rg", "warnings": warnings})
    if code == 3:
        return emit({"status": "ambiguous", "term": terms[0], "output": stdout[:MAX_OUTPUT], "warnings": warnings})
    if code != 0:
        return degraded("read-failed", detail=(stderr or stdout)[-400:])
    return emit({"status": "ok", "output": stdout[:MAX_OUTPUT], "truncated": len(stdout) > MAX_OUTPUT, "warnings": warnings})


def cmd_anchors(root, capability):
    """Whether the code anchors of the catalog still exist. Works with or without the tool, and says which."""
    anchors = code_anchors(root, capability)
    warnings, index = [], None
    state = refresh(root)
    if state is None:
        warnings.append("no graph: an anchor counts if its file exists and contains the name")
    else:
        warnings += state["warnings"]
        index = load_index(root)
        if index is None:
            warnings.append("graph format not recognised: an anchor counts if its file exists and contains the name")
    rows = []
    for ref, name in anchors.items():
        found = resolve(index, ref) if index is not None else "absent"
        if found == "absent":
            found = "by-name" if named_in_file(root, ref) else "missing"
        rows.append({"capability": name, "ref": ref, "found": found})
    return emit({"status": "ok" if index is not None else "degraded", "anchors": rows, "missing": [row["ref"] for row in rows if row["found"] == "missing"], "warnings": warnings})


def build_parser():
    parser = argparse.ArgumentParser(description="The only door to Graphify")
    parser.add_argument("command", choices=["status", "update", "explain", "affected", "query", "anchors"])
    parser.add_argument("terms", nargs="*", help="explain, affected: one anchor or name. query: technical English words")
    parser.add_argument("--root", default=".")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--all", action="store_true", help="explain: every connection")
    parser.add_argument("--capability")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not root.is_dir():
        parser.error("--root is not a directory")
    if args.capability and not re.fullmatch(r"[a-z][a-z0-9-]*", args.capability):
        parser.error("invalid capability name")
    if any(term.startswith("-") for term in args.terms):
        parser.error("a term cannot start with a dash")
    if args.command in ("explain", "affected") and len(args.terms) != 1:
        parser.error("%s takes one anchor or name" % args.command)
    if args.command == "query" and not args.terms:
        parser.error("query takes technical English words")
    if args.command in ("status", "update", "anchors") and args.terms:
        parser.error("%s takes no terms" % args.command)
    try:
        if args.command == "status":
            return cmd_status(root)
        if args.command == "update":
            return cmd_update(root)
        if args.command == "anchors":
            return cmd_anchors(root, args.capability)
        return cmd_read(root, args.command, args.terms, args.depth, args.all)
    except OSError as error:
        return degraded("read-failed", detail=str(error))


if __name__ == "__main__":
    sys.exit(main())
