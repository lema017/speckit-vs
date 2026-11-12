#!/usr/bin/env python3
"""The only door to Graphify, the code graph this fork installs with specify: where code is and what a change affects.

It never decides what a requirement is. Graphify arrives as a dependency of specify, so it lives
beside the real specify and may not be on PATH. It is never installed from here. Standard library
only, so any Python 3 can run it.

Only ``update``, ``explain``, ``affected`` and ``query`` reach the tool: never ``extract``,
``install``, ``watch``, hooks or ``--strict``. It runs without LLM keys in its environment.
``touched`` and ``anchors`` read the graph that ``update`` writes.

Exit codes: 0 done, 2 invalid input, 6 Graphify cannot answer, and ``reason`` says why:
``not-installed`` needs specify reinstalled, ``no-code`` is a project with nothing to graph yet,
``update-failed`` and ``read-failed`` are failures of the tool. The last three continue with the
anchors and ``rg``.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path

OK, INVALID, UNAVAILABLE = 0, 2, 6
PINNED = "0.9.102"
INSTALL = "uv tool install specify-cli --force --from git+https://github.com/lema017/speckit-vs.git"
NO_CODE = "No code files found"
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
ANCHORS = re.compile(r"^## Anchors[ \t]*$(.*?)(?=^## |\Z)", re.M | re.S)
ANCHOR_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.M)
FILE_REF = re.compile(r"^[A-Za-z0-9_.\-/]+\.[A-Za-z0-9]+(?:::|$)")
CONFIG = ".specify/extensions/capabilities/capabilities-config.yml"
BASE_LINE = re.compile(r"^base_branch:\s*(.*?)\s*(?:#.*)?$")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.M)
LOCATION = re.compile(r"^L(\d+)$")
# The catalog, the features and the tools' own files are never code of the change.
NOT_CODE = ("specs/", ".specify/", "graphify-out/", ".graphifyignore")
PER_FILE = 15


def emit(obj, code=OK):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return code


def degraded(reason, **extra):
    report = {"status": "degraded", "reason": reason, "fallback": "use the anchors and rg"}
    if reason == "not-installed":
        report["install"] = INSTALL
    return emit(dict(report, **extra), UNAVAILABLE)


def find_tool():
    """Beside the real specify first: it is the version this fork ships, and it is not on PATH. Then PATH."""
    specify = shutil.which("specify")
    beside = shutil.which("graphify", path=os.path.dirname(os.path.realpath(specify))) if specify else None
    return beside or shutil.which("graphify")


def graph_env():
    env = {key: os.environ[key] for key in KEPT_ENV if key in os.environ}
    env["GRAPHIFY_BACKEND"] = "none"
    env["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"
    return env


def tool(root, args, seconds):
    """(returncode, stdout, stderr), or None if it could not run or did not finish."""
    path = find_tool()
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
    """``query`` does not say when the graph is old, so every read updates it first. Returns (what to report, None) or (None, why not)."""
    if find_tool() is None:
        return None, "not-installed"
    try:
        wrote = ensure_ignores(root)
    except OSError:
        return None, "update-failed"
    done = tool(root, ["update", "."], UPDATE_SECONDS)
    if done is not None and done[0] != 0 and NO_CODE in done[1] + done[2]:
        return None, "no-code"
    if done is None or done[0] != 0 or not (root / GRAPH).is_file():
        return None, "update-failed"
    return {"wrote": wrote, "warnings": version_warnings(version_of(root))}, None


def load_graph(root):
    """(nodes, links), or None if the graph is not the shape this script was validated with."""
    try:
        data = json.loads((root / GRAPH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    graph = data.get("graph") if isinstance(data, dict) else None
    nodes = data.get("nodes") if isinstance(data, dict) else None
    if not isinstance(graph, dict) or graph.get("schema_version") != SCHEMA or not isinstance(nodes, list):
        return None
    if not all(isinstance(node, dict) for node in nodes):
        return None
    links = data.get("links")
    return nodes, [link for link in links if isinstance(link, dict)] if isinstance(links, list) else []


def index_of(nodes):
    index = {}
    for node in nodes:
        if isinstance(node.get("source_file"), str) and isinstance(node.get("label"), str) and node["source_file"] and node["label"]:
            index.setdefault((node["source_file"], node["label"]), []).append(node)
    return index


def load_index(root):
    """{(file, label): [node]}, or None if the graph is not the shape this script was validated with."""
    loaded = load_graph(root)
    return None if loaded is None else index_of(loaded[0])


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
    """{ref: (capability, where)}: the Code of each rule, then the rows of ## Anchors that name a file."""
    pattern = "%s/implementation.md" % (capability or "*")
    found = {}
    for path in sorted((root / CATALOG).glob(pattern)):
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in CODE_LINE.findall(text):
            for ref in QUOTED.findall(line) or [part.strip() for part in line.split(",") if part.strip() not in ("", "none")]:
                found.setdefault(ref, (path.parent.name, "code"))
        section = ANCHORS.search(text)
        for ref in ANCHOR_ROW.findall(section.group(1)) if section else ():
            if FILE_REF.match(ref):
                found.setdefault(ref, (path.parent.name, "anchors"))
    return found


def git(root, *args):
    """stdout, or None if git failed. Git is not the tool: it keeps its environment."""
    try:
        done = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=str(root), capture_output=True, encoding="utf-8", errors="replace", timeout=READ_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def git_names(root, *args):
    return [name for name in (git(root, *args) or "").split("\0") if name]


def base_of(root, onto):
    """(ref, merge base). The ref is --onto, else base_branch in the config, else main, as capabilities.py reads them."""
    ref = onto
    if ref is None:
        try:
            text = (root / CONFIG).read_text(encoding="utf-8")
        except OSError:
            text = ""
        for line in text.splitlines():
            match = BASE_LINE.match(line)
            if match:
                ref = match.group(1).strip("\"'").strip()
        ref = ref or "main"
    if ref.startswith("-"):
        # git would read it as an option: merge-base --fork-point prints a commit.
        return ref, None
    return ref, (git(root, "merge-base", "HEAD", ref) or "").strip() or None


def hunks(text):
    """(changed lines, added ranges) of one file's diff without context. A deletion counts as the line above it."""
    changed, added = set(), []
    for match in HUNK.finditer(text):
        start, count = int(match.group(1)), int(match.group(2) or "1")
        if count:
            changed.update(range(start, start + count))
            added.append((start, start + count - 1))
        else:
            changed.add(max(start, 1))
    return changed, added


def changes(root, base):
    """({file: (changed, added)}, deleted): the merge base against the working tree, so what is committed and what is not; untracked files whole."""
    found, deleted = {}, []
    for name in git_names(root, "diff", "--name-only", "--no-renames", "-z", base, "--"):
        if name.startswith(NOT_CODE):
            continue
        if not (root / name).is_file():
            deleted.append(name)
            continue
        changed, added = hunks(git(root, "diff", "-U0", "--no-renames", "--no-color", "--no-ext-diff", base, "--", name) or "")
        if changed:
            found[name] = (changed, added)
    for name in git_names(root, "ls-files", "--others", "--exclude-standard", "-z"):
        path = root / name
        if name.startswith(NOT_CODE) or path.is_symlink() or not path.is_file():
            continue
        try:
            count = len(path.read_bytes().decode("utf-8", "replace").splitlines())
        except OSError:
            continue
        if count:
            found[name] = (set(range(1, count + 1)), [(1, count)])
    return found, deleted


def ranges_of(lines):
    """[3, 4, 5, 9] -> ["3-5", "9"]."""
    spans = []
    for line in sorted(lines):
        if spans and line == spans[-1][1] + 1:
            spans[-1][1] = line
        else:
            spans.append([line, line])
    return ["%d" % low if low == high else "%d-%d" % (low, high) for low, high in spans]


def symbols_of(nodes, links):
    """{file: [(line, symbol, label, class)]}, sorted so that the last one starting at or before a line holds it.

    ``symbol`` is False for the node of the file itself. ``class`` is the owner of a method, from the graph."""
    labels = {node["id"]: node.get("label") for node in nodes if isinstance(node.get("id"), str)}
    owner = {}
    for link in links:
        source, target = link.get("source"), link.get("target")
        if link.get("relation") == "method" and isinstance(source, str) and isinstance(target, str) and isinstance(labels.get(source), str):
            owner.setdefault(target, labels[source])
    found = {}
    for node in nodes:
        path, label, where, ident = node.get("source_file"), node.get("label"), node.get("source_location"), node.get("id")
        match = LOCATION.match(where) if isinstance(where, str) else None
        if not (isinstance(path, str) and isinstance(label, str) and path and label and match) or node.get("type") == "package":
            continue
        found.setdefault(path, []).append((int(match.group(1)), label != posixpath.basename(path), label, owner.get(ident) if isinstance(ident, str) else None))
    for rows in found.values():
        rows.sort(key=lambda row: (row[0], row[1], row[2]))
    return found


def ref_of(path, row):
    if row is None or not row[1]:
        return path
    label = row[2]
    return "%s::%s" % (path, label[:-2] if label.endswith("()") and not label.startswith(".") else label)


def touched_in(index, path, rows, changed, added):
    """The symbol that holds each changed line, and every symbol that starts inside added lines. An approximation: the graph gives where a symbol starts, not where it ends."""
    starts = [row[0] for row in rows]
    held = {}
    for line in changed:
        at = bisect.bisect_right(starts, line) - 1
        row = rows[at] if at >= 0 and rows[at][1] else None
        held.setdefault(row, set()).add(line)
    for low, high in added:
        for row in rows:
            if row[1] and low <= row[0] <= high:
                held.setdefault(row, set())
    symbols = []
    for row, lines in held.items():
        ref = ref_of(path, row)
        symbol = {"ref": ref, "line": row[0] if row else 1, "changed": len(lines), "found": resolve(index, ref)}
        if row and row[3]:
            symbol["class"] = row[3]
        symbols.append(symbol)
    kept = sorted(symbols, key=lambda s: (-s["changed"], s["line"], s["ref"]))[:PER_FILE]
    return sorted(kept, key=lambda s: (s["line"], s["ref"])), len(symbols) - len(kept)


def cmd_touched(root, onto):
    """Where the change is in the code: the candidates for Code and for ## Anchors. Which rule a symbol serves is for whoever reads the code."""
    ref, base = base_of(root, onto)
    if base is None:
        return emit({"status": "invalid", "errors": ["no merge base with %s; pass --onto <ref> or set base_branch in %s" % (ref, CONFIG)]}, INVALID)
    found, deleted = changes(root, base)
    plain = [{"file": path, "lines": ranges_of(found[path][0])} for path in sorted(found)]
    state, why = refresh(root)
    if state is None:
        return degraded(why, base=ref, files=plain, deleted=deleted)
    loaded = load_graph(root)
    if loaded is None:
        return degraded("read-failed", detail="graph format not recognised", base=ref, files=plain, deleted=deleted)
    index, symbols = index_of(loaded[0]), symbols_of(*loaded)
    files, other = [], []
    for item in plain:
        rows = symbols.get(item["file"])
        if not rows:
            other.append(item)
            continue
        listed, omitted = touched_in(index, item["file"], rows, *found[item["file"]])
        files.append(dict(item, symbols=listed, omitted=omitted))
    return emit(dict({"status": "ok", "base": ref, "files": files, "other": other, "deleted": deleted}, **state))


def cmd_status(root):
    if find_tool() is None:
        return emit({"status": "degraded", "available": False, "fallback": "use the anchors and rg", "install": INSTALL, "pinned": PINNED})
    version = version_of(root)
    return emit({"status": "ok", "available": True, "version": version, "pinned": PINNED, "graph": (root / GRAPH).is_file(), "warnings": version_warnings(version)})


def cmd_update(root):
    state, why = refresh(root)
    if state is None:
        return degraded(why)
    return emit(dict({"status": "ok", "graph": GRAPH}, **state))


def cmd_read(root, args, terms, depth, show_all):
    state, why = refresh(root)
    if state is None:
        return degraded(why)
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
    state, _ = refresh(root)
    if state is None:
        warnings.append("no graph: an anchor counts if its file exists and contains the name")
    else:
        warnings += state["warnings"]
        index = load_index(root)
        if index is None:
            warnings.append("graph format not recognised: an anchor counts if its file exists and contains the name")
    rows = []
    for ref, (name, where) in anchors.items():
        found = resolve(index, ref) if index is not None else "absent"
        if found == "absent":
            found = "by-name" if named_in_file(root, ref) else "missing"
        rows.append({"capability": name, "ref": ref, "found": found, "in": where})
    return emit({"status": "ok" if index is not None else "degraded", "anchors": rows, "missing": [row["ref"] for row in rows if row["found"] == "missing"], "warnings": warnings})


def build_parser():
    parser = argparse.ArgumentParser(description="The only door to Graphify")
    parser.add_argument("command", choices=["status", "update", "explain", "affected", "query", "anchors", "touched"])
    parser.add_argument("terms", nargs="*", help="explain, affected: one anchor or name. query: technical English words")
    parser.add_argument("--root", default=".")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--all", action="store_true", help="explain: every connection")
    parser.add_argument("--capability")
    parser.add_argument("--onto", help="touched: the base branch, instead of base_branch from the config")
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
    if args.command in ("status", "update", "anchors", "touched") and args.terms:
        parser.error("%s takes no terms" % args.command)
    if args.onto is not None and (args.command != "touched" or not args.onto or args.onto.startswith("-")):
        parser.error("--onto takes a branch, and only with touched")
    try:
        if args.command == "status":
            return cmd_status(root)
        if args.command == "update":
            return cmd_update(root)
        if args.command == "anchors":
            return cmd_anchors(root, args.capability)
        if args.command == "touched":
            return cmd_touched(root, args.onto)
        return cmd_read(root, args.command, args.terms, args.depth, args.all)
    except OSError as error:
        return degraded("read-failed", detail=str(error))


if __name__ == "__main__":
    sys.exit(main())
