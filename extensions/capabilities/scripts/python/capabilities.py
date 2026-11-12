#!/usr/bin/env python3
"""Mechanics of the capability catalog: delta, fold publication and integration check.

Standard library only and Python 3.9+, so any ``python3`` can run it, in CI too.

Exit codes, the same for every subcommand:
  0  done
  1  ``check`` found a failure (``check`` reports project problems only with this code)
  2  invalid input or bad invocation
  3  a decision is needed, or the operation is blocked
  4  a fold was interrupted and needs recovery
  5  another process is publishing
"""
import argparse
import contextlib
import fnmatch
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

OK, HARD, INVALID, DECISION, RECOVER, BUSY = 0, 1, 2, 3, 4, 5

CATALOG = "specs/_capabilities"
IGNORED_CATALOG = "git ignores it, so it stays on this machine and CI has nothing to check. Remove that rule from .gitignore"
CHANGES = CATALOG + "/_changes"
INDEX = CATALOG + "/index.md"
STATE_DIR = ".specify/capabilities"
JOURNAL = STATE_DIR + "/journal"
STAGING = STATE_DIR + "/staging"
PUBLISH_LOCK = STATE_DIR + "/publish.lock"
EXTENSION_DIR = ".specify/extensions/capabilities"
CONFIG = EXTENSION_DIR + "/capabilities-config.yml"
LOCK_NAME = "capability-delta.lock.json"
DOCS = ("spec.md", "capability-delta.md")
TEMPLATES = Path(__file__).resolve().parents[2] / "templates"

MARK = "<!-- capability-delta:v1 -->"
# The catalog format this script reads and writes. 2 adds the [designed] mark, written with the seal below.
CATALOG_FORMAT = 2
FORMAT_SEAL = "<!-- capability-catalog: %d -->" % CATALOG_FORMAT
FORMAT_LINE = re.compile(r"<!-- capability-catalog: (\d+) -->")
RULE = re.compile(r"^- \*\*(R-[a-z0-9-]+)\*\*( \[(?:inferred|designed)\])?: (.*?)(?: \(([^()]*/[^()]*)\))?\s*$")
ENTRY = re.compile(r"^### (ADDED|MODIFIED|REMOVED|INFERRED|VALIDATED|DESIGNED|IMPLEMENTED) (R-[a-z0-9-]+)\s*$")
# What a design record may declare, besides NEW-CAPABILITY. Only a record under _changes/ declares DESIGNED.
DESIGN_OPS = {"DESIGNED", "REMOVED"}
# Git's conflict markers. ======= alone is not one: Markdown underlines a heading with it, and git never writes it alone.
CONFLICT_SIDE = re.compile(r"^(?:<{7}|>{7}|\|{7})(?: .*)?$", re.M)
BLOCK = re.compile(r"^### (R-[a-z0-9-]+)\s*$")
BLOCK_FIELD = re.compile(r"^- (Observed|State|Code|Tests|Change): (.*)$")
FR_LINE = re.compile(r"^\s*- \*\*FR-\d+\*\*", re.M)
CAPABILITY = re.compile(r"^[a-z][a-z0-9-]*$")
RECORD = re.compile(r"^\d{8}-[a-z0-9][a-z0-9-]*$")
FIELDS = {"capability", "from", "to", "links", "replaced-by"}
STATES = {"conforming", "discrepant", "unverified"}
CATALOG_SECTIONS = {"Overview", "Rules", "Related Capabilities"}
FORBIDDEN_NAMES = {"plan.md", "tasks.md", "README.md"}
REPORT_SKEW_SECONDS = 300
SCRIPT_TESTS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
TITLE_SLOT = re.compile(r"%[a-zA-Z#]|\$\{[^{}]*\}|\$[A-Za-z_][\w.]*|\{[^{}]*\}")
DEFAULTS = {"feature_roots": "specs", "allow_manual_evidence": "false", "allow_partial_features": "false", "base_branch": ""}
GITIGNORE_LINE = ".specify/capabilities/"
GITATTRIBUTES_LINES = (
    "specs/_capabilities/index.md merge=union",
    "specs/_capabilities/*/history.md merge=union",
)
AGENT_CONTEXT_CONFIG = ".specify/extensions/agent-context/agent-context-config.yml"
INIT_OPTIONS = ".specify/init-options.json"
AGENT_START = "<!-- SPECKIT CAPABILITIES START -->"
AGENT_END = "<!-- SPECKIT CAPABILITIES END -->"
DEFAULT_AGENT_FILE = "AGENTS.md"
# The agent-context extension's map, without the entries that use the default. A test keeps them aligned.
AGENT_FILES = {
    "alquimia": "ALQUIMIA.md",
    "auggie": ".augment/rules/specify-rules.md",
    "claude": "CLAUDE.md",
    "cline": ".clinerules/specify-rules.md",
    "codebuddy": "CODEBUDDY.md",
    "copilot": ".github/copilot-instructions.md",
    "cursor-agent": ".cursor/rules/specify-rules.mdc",
    "firebender": ".firebender/rules/specify-rules.mdc",
    "gemini": "GEMINI.md",
    "junie": ".junie/AGENTS.md",
    "kilocode": ".kilocode/rules/specify-rules.md",
    "lingma": ".lingma/rules/specify-rules.md",
    "qodercli": "QODER.md",
    "qwen": "QWEN.md",
    "shai": "SHAI.md",
    "tabnine": "TABNINE.md",
    "trae": ".trae/rules/project_rules.md",
    "windsurf": ".windsurf/rules/specify-rules.md",
    "zcode": "ZCODE.md",
}


class CapError(Exception):
    """Invalid input: reported as JSON with exit code 2."""


class Busy(Exception):
    """Another process holds the publish lock."""


# ---------------------------------------------------------------- basics


def norm(text):
    return " ".join(text.split())


def sha(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


def read(path):
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None


def write_file(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def sync_dir(path):
    if os.name == "posix":
        descriptor = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def git(root, *args):
    done = subprocess.run(["git", *args], cwd=str(root), capture_output=True, encoding="utf-8", errors="replace")
    return done.stdout if done.returncode == 0 else None


def git_names(root, *args):
    return [name for name in (git(root, *args) or "").split("\0") if name]


def emit(obj, code=OK):
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))
    return code


def dumps(obj):
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def template(name, **values):
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{%s}" % key, value)
    return text


def section(text, title):
    match = re.search(r"^## " + re.escape(title) + r".*$", text, re.M)
    if not match:
        return None
    following = re.search(r"^## ", text[match.end():], re.M)
    return text[match.start():(match.end() + following.start()) if following else len(text)]


def has_conflict(text):
    return bool(text) and bool(CONFLICT_SIDE.search(text))


def conflicted(root, rels):
    """The files among ``rels`` that still hold git's conflict markers."""
    return sorted(rel for rel in set(rels) if has_conflict(read(root / rel)))


def conflict_message(files, source=None):
    change = source or "<feature>"
    return "merge conflict markers in %s; the catalog is never resolved by hand: run capabilities.py rebase --change %s" % (", ".join(files), change)


def catalog_format(text):
    found = [int(number) for number in FORMAT_LINE.findall(text or "")]
    return max(found) if found else 1


def format_error(text, where="specs/_capabilities/index.md"):
    found = catalog_format(text)
    if found > CATALOG_FORMAT:
        return "%s uses catalog format %d and this script reads up to %d: update with specify upgrade" % (where, found, CATALOG_FORMAT)
    return None


def with_seal(text):
    """The seal goes under the title once the catalog holds a [designed] rule. A script that predates it ignores the comment."""
    if FORMAT_LINE.search(text):
        return text
    head, _, rest = text.partition("\n")
    if not head.startswith("# "):
        return FORMAT_SEAL + "\n\n" + text
    return head + "\n\n" + FORMAT_SEAL + "\n" + rest


def load_config(root):
    config = dict(DEFAULTS)
    for line in (read(root / CONFIG) or "").splitlines():
        match = re.match(r"^([a-z_]+):\s*(.*?)\s*(?:#.*)?$", line)
        if match:
            config[match.group(1)] = match.group(2).strip("\"'")
    config["allow_manual_evidence"] = config["allow_manual_evidence"].lower() == "true"
    config["allow_partial_features"] = config["allow_partial_features"].lower() == "true"
    config["feature_roots"] = [r.strip().strip("/") for r in config["feature_roots"].split(",") if r.strip()]
    config["base_branch"] = config["base_branch"].strip()
    return config


def safe_agent_path(value):
    return "\\" not in value and not value.startswith("/") and not re.match(r"^[A-Za-z]:", value) and ".." not in value.split("/")


def agent_context_files(root):
    """``context_files``, else ``context_file``, from the agent-context config, without unsafe paths. No YAML parser: standard library only."""
    listed, single, inside = [], "", False
    for line in (read(root / AGENT_CONTEXT_CONFIG) or "").splitlines():
        line = re.sub(r"(^|\s)#.*$", "", line).rstrip()
        match = re.match(r"^(context_files?):\s*(.*)$", line)
        if match:
            value = match.group(2).strip()
            inside = match.group(1) == "context_files" and not value
            if match.group(1) == "context_file":
                single = value.strip("\"'")
            elif value.startswith("["):
                listed = [item.strip().strip("\"'") for item in value.strip("[]").split(",")]
            continue
        item = re.match(r"^\s*-\s+(.*)$", line)
        if inside and item:
            listed.append(item.group(1).strip().strip("\"'"))
        elif line.strip():
            inside = False
    return [item for item in listed if item and safe_agent_path(item)] or ([single] if single and safe_agent_path(single) else [])


def agent_files(root):
    """The file the project configured, else the one of its integration, else AGENTS.md."""
    configured = agent_context_files(root)
    if configured:
        return configured
    try:
        options = json.loads(read(root / INIT_OPTIONS) or "{}")
    except ValueError:
        options = {}
    name = (options.get("integration") or options.get("ai")) if isinstance(options, dict) else None
    return [AGENT_FILES.get(name, DEFAULT_AGENT_FILE) if isinstance(name, str) else DEFAULT_AGENT_FILE]


def upsert_agent_block(root, rel):
    """Add or refresh the block and leave the rest of the file byte for byte. Returns what to report, or None."""
    path = root / rel
    if root not in path.resolve().parents:
        return "skipped %s: it points outside the repository" % rel
    try:
        current = path.read_bytes().decode("utf-8") if path.exists() else ""
    except (OSError, UnicodeDecodeError):
        return "skipped %s: it cannot be read as UTF-8" % rel
    newline = "\r\n" if "\r\n" in current else "\n"
    block = template("capability-agent-rule.md").strip("\n").replace("\n", newline)
    starts, ends = current.count(AGENT_START), current.count(AGENT_END)
    if starts == 0 and ends == 0:
        head = current if not current or current.endswith("\n") else current + newline
        updated = head + (newline if head.strip() else "") + block + newline
    elif starts == 1 and ends == 1 and current.index(AGENT_START) < current.index(AGENT_END):
        updated = current[:current.index(AGENT_START)] + block + current[current.index(AGENT_END) + len(AGENT_END):]
    else:
        return "skipped %s: unbalanced markers" % rel
    if rel.endswith(".mdc") and not updated.startswith("---"):
        updated = "---\nalwaysApply: true\n---\n\n" + updated
    if updated == current:
        return None
    try:
        write_file(path, updated)
    except OSError as error:
        return "skipped %s: %s" % (rel, error.strerror or error)
    return rel


def catalog_is_ignored(root):
    """A catalog git ignores stays on one machine, and CI would pass with nothing to check."""
    return git(root, "check-ignore", "-q", CATALOG + "/index.md") is not None


def ensure_setup(root):
    """Idempotent project setup: appends lines and keeps the agent block current. Never rewrites anything else."""
    touched = []
    for name, wanted in ((".gitignore", (GITIGNORE_LINE,)), (".gitattributes", GITATTRIBUTES_LINES)):
        path = root / name
        current = read(path) or ""
        missing = [line for line in wanted if line not in current.splitlines()]
        if missing:
            prefix = current if not current or current.endswith("\n") else current + "\n"
            write_file(path, prefix + "\n".join(missing) + "\n")
            touched.append(name)
    for rel in agent_files(root):
        result = upsert_agent_block(root, rel)
        if result:
            touched.append(result)
    if catalog_is_ignored(root):
        touched.append("skipped %s: %s" % (CATALOG, IGNORED_CATALOG))
    return touched


@contextlib.contextmanager
def publish_lock(root):
    """Kernel lock, so it dies with its process. Non-blocking: a second writer gets Busy."""
    path = root / PUBLISH_LOCK
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    locked = False
    try:
        try:
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            locked = True
        except OSError:
            raise Busy()
        yield
    finally:
        if locked and fcntl is None:
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        os.close(descriptor)


# ---------------------------------------------------------------- change documents


def change_doc(change):
    fallback = None
    for name in DOCS:
        path = change / name
        text = read(path)
        if text is not None:
            if MARK in text:
                return path
            fallback = fallback or path
    return fallback or change / DOCS[0]


def source_of(root, change):
    rel = os.path.relpath(str(change.resolve()), str(root.resolve())).replace(os.sep, "/")
    if rel == ".." or rel.startswith("../"):
        raise CapError("change directory is outside the repository: %s" % change)
    return rel


def resolve_change(root, given):
    """Ask Spec Kit for the feature path instead of reimplementing the resolution."""
    if given:
        return root / given[0]
    options = json.loads(read(root / ".specify/init-options.json") or "{}")
    commands = {
        "sh": ["bash", ".specify/scripts/bash/check-prerequisites.sh", "--json", "--paths-only"],
        "ps": ["pwsh", "-NoProfile", "-File", ".specify/scripts/powershell/check-prerequisites.ps1", "-Json", "-PathsOnly"],
        "py": [sys.executable, ".specify/scripts/python/check_prerequisites.py", "--json", "--paths-only"],
    }
    command = commands.get(options.get("script", "sh"), commands["sh"])
    try:
        done = subprocess.run(command, cwd=str(root), capture_output=True, encoding="utf-8", errors="replace")
    except OSError as error:
        raise CapError("cannot resolve the feature directory: %s" % error)
    if done.returncode != 0:
        raise CapError("cannot resolve the feature directory: %s" % (done.stderr.strip() or done.stdout.strip()))
    for line in reversed(done.stdout.splitlines()):
        with contextlib.suppress(ValueError):
            feature = json.loads(line).get("FEATURE_DIR")
            if feature:
                return Path(feature)
    raise CapError("check-prerequisites did not report FEATURE_DIR")


def spec_sections(text):
    out, story, in_scenarios = {}, None, False
    for line in text.splitlines():
        match = re.match(r"^- \*\*((?:FR|SC)-\d+)\*\*:(.*)$", line)
        if match:
            out[match.group(1)] = sha(norm(match.group(2)))
        match = re.match(r"^### User Story (\d+)", line)
        if match:
            story, in_scenarios = match.group(1), False
        if "Acceptance Scenarios" in line:
            in_scenarios = True
        match = re.match(r"^\s*(\d+)\. (.*)$", line)
        if match and story and in_scenarios:
            out["US%s/AC%s" % (story, match.group(1))] = sha(norm(match.group(2)))
    return out


def split_links(value):
    return [link for link in re.split(r"\s*,\s*", value or "") if link]


def parse_delta(text, source=None):
    """With ``source``, also where the delta lives: only a record under _changes/ declares DESIGNED."""
    if text.count(MARK) > 1 or len(re.findall(r"^## Capability Delta", text, re.M)) > 1:
        return None, ["delta section appears more than once"]
    raw = section(text, "Capability Delta")
    if raw is None:
        return None, ["delta section missing"]
    if MARK not in raw:
        return None, ["delta marker missing"]
    delta = {"raw": raw, "none": None, "entries": [], "new": {}}
    errors, current, new_capability = [], None, None
    for line in re.sub(r"<!--.*?-->", "", raw, flags=re.S).splitlines():
        match = ENTRY.match(line)
        if match:
            current, new_capability = {"op": match.group(1), "id": match.group(2)}, None
            delta["entries"].append(current)
            continue
        match = re.match(r"^### NEW-CAPABILITY (\S+)\s*$", line)
        if match:
            current, new_capability = None, match.group(1)
            delta["new"][new_capability] = ""
            if not CAPABILITY.match(new_capability):
                errors.append("NEW-CAPABILITY %s: invalid name" % new_capability)
            continue
        if line.startswith("### "):
            current, new_capability = None, None
            errors.append("unrecognized block: %s" % line.strip())
            continue
        match = re.match(r"^Capabilities: none\s*[-—]\s*(.+)$", line)
        if match:
            delta["none"] = match.group(1)
            continue
        match = re.match(r"^- ([A-Za-z-]+): (.*)$", line)
        if not match:
            if line.strip() and (current is not None or new_capability):
                errors.append("unexpected line, a field takes one line: %s" % line.strip())
            continue
        key, value = match.group(1).lower(), norm(match.group(2))
        if current is not None:
            if key in FIELDS:
                current[key] = value
            else:
                errors.append("%s %s: unknown field %s" % (current["op"], current["id"], match.group(1)))
        elif new_capability and key == "covers":
            delta["new"][new_capability] = value
    errors.extend(delta_errors(delta, set(spec_sections(text))))
    if source is not None:
        errors.extend(placement_errors(delta, source))
    return delta, errors


def is_record(source):
    return source.startswith(CHANGES + "/")


def design_capable(delta, source):
    """A record that only designs or retires: the one place a [designed] rule may be retired."""
    return is_record(source) and bool(delta["entries"]) and all(entry["op"] in DESIGN_OPS for entry in delta["entries"])


def is_design(delta):
    return any(entry["op"] == "DESIGNED" for entry in delta["entries"])


def placement_errors(delta, source):
    if not is_design(delta):
        return []
    if not is_record(source):
        return ["DESIGNED %s: only a design record under %s/ declares DESIGNED; a spec builds a [designed] rule with IMPLEMENTED" % (entry["id"], CHANGES) for entry in delta["entries"] if entry["op"] == "DESIGNED"]
    others = sorted({entry["op"] for entry in delta["entries"]} - DESIGN_OPS)
    if others:
        return ["a design record declares only NEW-CAPABILITY, DESIGNED and REMOVED of [designed] rules, not %s; declare them in a spec" % ", ".join(others)]
    return []


def delta_errors(delta, known):
    errors = []
    if not delta["entries"] and not delta["none"]:
        errors.append("delta is empty")
    if delta["entries"] and delta["none"]:
        errors.append("delta declares rules and 'Capabilities: none' at once")
    seen = set()
    allowed_links = known or {"none"}
    for entry in delta["entries"]:
        where = "%s %s" % (entry["op"], entry["id"])
        if entry["id"] in seen:
            errors.append(where + ": repeated rule")
        seen.add(entry["id"])
        for key in ("capability", "from", "to", "links"):
            if not entry.get(key):
                errors.append("%s: missing %s" % (where, key))
        if entry.get("capability") and not CAPABILITY.match(entry["capability"]):
            errors.append("%s: invalid capability name %s" % (where, entry["capability"]))
        if entry["op"] in ("ADDED", "INFERRED") and entry.get("from") != "(none)":
            errors.append(where + ": From must be (none)")
        if entry["op"] == "REMOVED":
            if entry.get("to") != "(none)":
                errors.append(where + ": To must be (none)")
            if not entry.get("replaced-by"):
                errors.append(where + ": missing Replaced-By (a rule id, or none)")
        if entry["op"] == "MODIFIED" and entry.get("from") == entry.get("to"):
            errors.append(where + ": From equals To")
        if entry["op"] == "VALIDATED" and entry.get("from") != entry.get("to"):
            errors.append(where + ": From must equal To")
        if entry["op"] == "IMPLEMENTED":
            if entry.get("from") == "(none)":
                errors.append(where + ": From is the text of the [designed] rule; a new rule is ADDED")
            elif entry.get("from") != entry.get("to"):
                errors.append(where + ": From must equal To; a spec that changes the text of a [designed] rule declares MODIFIED")
        if entry["op"] == "DESIGNED":
            if entry.get("to") == "(none)":
                errors.append(where + ": To cannot be (none); a design record retires a [designed] rule with REMOVED")
            elif entry.get("from") == entry.get("to"):
                errors.append(where + ": From equals To")
        for link in split_links(entry.get("links")):
            if link not in allowed_links:
                errors.append("%s: link %s not found in the change" % (where, link))
    used = {entry.get("capability") for entry in delta["entries"]}
    for capability, covers in delta["new"].items():
        if not covers:
            errors.append("NEW-CAPABILITY %s: missing Covers" % capability)
        if capability not in used:
            errors.append("NEW-CAPABILITY %s: no rule uses it" % capability)
    return errors


def capabilities_of(delta):
    return sorted({entry["capability"] for entry in delta["entries"]})


# ---------------------------------------------------------------- catalog documents


def parse_rules(text):
    rules, errors = {}, []
    raw = section(text or "", "Rules")
    if raw is None:
        return rules, ["missing ## Rules section"] if text is not None else []
    for line in raw.splitlines()[1:]:
        if not line.strip():
            continue
        match = RULE.match(line)
        if not match:
            errors.append("line in ## Rules is not a rule: %r" % line.strip()[:80])
        elif match.group(1) in rules:
            errors.append("duplicate rule id %s" % match.group(1))
        else:
            mark = (match.group(2) or "").strip()
            rules[match.group(1)] = {"text": norm(match.group(3)), "tag": match.group(4), "inferred": mark == "[inferred]", "designed": mark == "[designed]"}
    return rules, errors


def rules_of(text):
    return parse_rules(text)[0]


def capability_state(rules, retired):
    """2.1 of the plan. A capability left without rules is retired; one still marked consolidated is accepted as legacy."""
    if not rules:
        return "retired"
    designed = sum(1 for rule in rules.values() if rule["designed"])
    if designed == len(rules):
        return "designed"
    return "partial" if designed else "consolidated"


def catalog_errors(text):
    errors = list(parse_rules(text)[1])
    for match in re.finditer(r"^## (.+?)\s*$", text, re.M):
        if match.group(1) not in CATALOG_SECTIONS:
            errors.append("section %r is not allowed: behaviour belongs in ## Rules" % match.group(1))
    outside = text.replace(section(text, "Rules") or "", "")
    for match in re.finditer(r"^\s*- \*\*(R-[a-z0-9-]+)\*\*", outside, re.M):
        errors.append("rule %s sits outside ## Rules" % match.group(1))
    return errors


INDEX_ROW = re.compile(r"^\| \[([a-z0-9-]+)\]\(([^)]*)\) \|")


def index_row_cells(line):
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def index_row(name, covers, state, entry_point):
    return "| [%s](%s/spec.md) | %s | %s | %s |" % (name, name, covers, state, entry_point)


def table_rows(text, title):
    rows = []
    for line in (section(text or "", title) or "").splitlines():
        line = line.strip()
        if not line.startswith("|") or re.match(r"^\|[\s:|-]+\|$", line):
            continue
        cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line.strip("|"))]
        if cells[0] not in ("Change", "Rule"):
            rows.append(cells)
    return rows


def retired_of(text):
    out = {}
    for cells in table_rows(text, "Retired Rules"):
        if len(cells) >= 3:
            out[cells[0]] = {"text": cells[1], "by": cells[2], "replacement": cells[3] if len(cells) > 3 else "none"}
    return out


def blocks(text, title):
    out, current = {}, None
    for line in (section(text or "", title) or "").splitlines():
        match = BLOCK.match(line)
        if match:
            current = out.setdefault(match.group(1), {"observed": "", "state": "", "code": [], "tests": [], "manual": None, "change": ""})
            continue
        match = BLOCK_FIELD.match(line)
        if not match or current is None:
            continue
        key, value = match.group(1).lower(), match.group(2).strip()
        if key == "tests" and value.startswith("manual:"):
            current["manual"] = value[len("manual:"):].strip() or "no reason given"
        elif key in ("code", "tests"):
            quoted = re.findall(r"`([^`]+)`", value)
            current[key] = quoted or [ref.strip() for ref in value.split(",") if ref.strip() not in ("", "none")]
        else:
            current[key] = value
    return out


def rule_status(text):
    return blocks(text, "Rule Status")


def retirement_evidence(text):
    return blocks(text, "Retirement Evidence")


def anchor_file(ref):
    return posixpath.normpath(ref.split("::")[0])


def anchor_resolves(root, ref):
    """The file exists and each symbol of the reference appears in it as a word. Not a parse."""
    path = root / anchor_file(ref)
    if not path.is_file():
        return False
    text = path.read_bytes().decode("utf-8", "replace")
    for part in ref.split("::")[1:]:
        name = part.split("[")[0].strip(".()")
        if name and not re.search(r"(?<!\w)%s(?!\w)" % re.escape(name), text):
            return False
    return True


def file_digest(root, rel):
    path = root / rel
    return sha(path.read_bytes().replace(b"\r\n", b"\n")) if path.is_file() else "missing"


def anchors_of(root, row):
    return {anchor_file(ref): file_digest(root, anchor_file(ref)) for ref in row["code"] + row["tests"]}


def cap_rel(capability, name):
    return "%s/%s/%s" % (CATALOG, capability, name)


def open_tasks(change):
    text = read(change / "tasks.md")
    return None if text is None else len(re.findall(r"^\s*- \[ \]", text, re.M))


def lock_path(change):
    return change / LOCK_NAME


def load_lock(change):
    text = read(lock_path(change))
    return json.loads(text) if text else None


def stamp(text, delta, source, fold=None):
    data = {
        "schema": 1,
        "source": source,
        "delta_sha": sha(delta["raw"]),
        "spec_sha": sha(text.replace(delta["raw"], "")),
        "sections": spec_sections(text),
    }
    if fold:
        data["fold"] = fold
    return data


def classify(root, delta, source, get=None):
    """Each entry against the catalog: apply, done, or a conflict. ``get`` reads a catalog file; by default, the working tree."""
    get = get or (lambda rel: read(root / rel))
    actions, conflicts = [], []
    designer = design_capable(delta, source)
    for entry in delta["entries"]:
        spec = get(cap_rel(entry["capability"], "spec.md"))
        rule = rules_of(spec).get(entry["id"])
        retired = retired_of(get(cap_rel(entry["capability"], "history.md")))
        where = "%s %s" % (entry["op"], entry["id"])
        gone = rule is None and entry["id"] in retired
        if spec is None and entry["capability"] not in delta["new"]:
            conflicts.append("%s: capability %s does not exist; declare NEW-CAPABILITY" % (where, entry["capability"]))
        elif entry["op"] == "DESIGNED":
            conflict = designed_conflict(entry, rule, gone, retired, source)
            if conflict:
                conflicts.append(where + ": " + conflict)
            else:
                actions.append((entry, "done" if rule is not None and rule["text"] == entry["to"] else "apply"))
        elif entry["op"] == "IMPLEMENTED":
            if rule is None:
                conflicts.append(where + (": retired by %s" % retired[entry["id"]]["by"] if gone else ": rule not found"))
            elif rule["designed"] and rule["text"] == entry["from"]:
                actions.append((entry, "apply"))
            elif rule["designed"]:
                conflicts.append("%s: catalog says %r, delta expects %r; if the base changed the rule, run rebase" % (where, rule["text"], entry["from"]))
            elif rule["text"] == entry["to"] and rule["tag"] == source and not rule["inferred"]:
                actions.append((entry, "done"))
            else:
                conflicts.append(where + ": the rule is not [designed]; a spec changes an implemented rule with MODIFIED")
        elif rule is not None and rule["designed"] and entry["op"] in ("ADDED", "INFERRED", "VALIDATED"):
            conflicts.append(where + ": the rule is [designed]; a spec builds it with IMPLEMENTED")
        elif entry["op"] in ("ADDED", "INFERRED"):
            if rule is None and entry["id"] in retired:
                conflicts.append(where + ": retired ids are not reused")
            elif rule is None:
                actions.append((entry, "apply"))
            elif rule["text"] == entry["to"]:
                actions.append((entry, "done"))
            else:
                conflicts.append("%s: already exists with %r" % (where, rule["text"]))
        elif entry["op"] == "MODIFIED":
            if rule is None:
                conflicts.append(where + (": retired by %s" % retired[entry["id"]]["by"] if gone else ": rule not found"))
            elif rule["text"] == entry["to"] and not rule["designed"]:
                actions.append((entry, "done"))
            elif rule["text"] == entry["from"]:
                actions.append((entry, "apply"))
            else:
                conflicts.append("%s: catalog says %r, delta expects %r" % (where, rule["text"], entry["from"]))
        elif entry["op"] == "VALIDATED":
            if rule is None or rule["text"] != entry["to"]:
                conflicts.append(where + ": catalog text does not match")
            elif rule["inferred"]:
                actions.append((entry, "apply"))
            elif rule["tag"] == source:
                actions.append((entry, "done"))
            else:
                conflicts.append(where + ": rule is not inferred")
        else:
            if rule is None and retired.get(entry["id"], {}).get("by") == source:
                actions.append((entry, "done"))
            elif rule is not None and rule["text"] == entry["from"] and rule["designed"] and not designer:
                conflicts.append(where + ": a [designed] rule is retired only by a design record; to leave it out of this spec, run capabilities.py defer")
            elif rule is not None and rule["text"] == entry["from"] and not rule["designed"] and is_design(delta):
                conflicts.append(where + ": a design record retires only [designed] rules; retire an implemented rule with a change that brings evidence")
            elif rule is not None and rule["text"] == entry["from"]:
                actions.append((entry, "apply"))
            else:
                conflicts.append(where + ": catalog state does not match From")
    return actions, conflicts


def designed_conflict(entry, rule, gone, retired, source):
    """What stops a DESIGNED entry, or None. A new rule needs a free id; a redesign needs the current [designed] text."""
    if entry["from"] == "(none)":
        if gone:
            return "retired ids are not reused"
        if rule is None or (rule["designed"] and rule["text"] == entry["to"] and rule["tag"] == source):
            return None
        return "already exists with %r" % rule["text"]
    if rule is None:
        return "retired by %s" % retired[entry["id"]]["by"] if gone else "rule not found"
    if not rule["designed"]:
        return "the rule is %s; a spec changes it with MODIFIED" % ("[inferred]" if rule["inferred"] else "implemented")
    if rule["text"] in (entry["from"], entry["to"]):
        return None
    return "catalog says %r, delta expects %r" % (rule["text"], entry["from"])


# ---------------------------------------------------------------- scope and digests


def paths_in(text):
    return set(re.findall(r"[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+\.[A-Za-z0-9]+", text or ""))


def scope_of(root, change, rows):
    found = paths_in(read(change / "tasks.md")) | paths_in(read(change / "plan.md"))
    for row in rows:
        found |= {anchor_file(ref) for ref in row["code"] + row["tests"]}
    source = source_of(root, change)
    return sorted(p for p in found if (root / p).is_file() and not p.startswith(CATALOG) and not p.startswith(source))


def delta_rows(delta, implementation_of):
    rows = []
    for entry in delta["entries"]:
        text = implementation_of(entry["capability"])
        if entry["op"] == "REMOVED":
            row = retirement_evidence(text).get(entry["id"])
        else:
            row = rule_status(text).get(entry["id"])
        if row:
            rows.append(row)
    return rows


def foreign_of(root, change, scope):
    source = source_of(root, change)
    skip = (CATALOG, source, ".specify", ".gitignore", ".gitattributes", *agent_files(root))
    names = [item[3:] for item in git_names(root, "status", "--porcelain", "-z", "--no-renames")]
    return sorted(n for n in names if n not in scope and not n.startswith(skip))


def input_digest(root, change, delta, scope):
    digest = hashlib.sha256()
    digest.update(delta["raw"].encode("utf-8"))
    for name in ("plan.md", "research.md"):
        digest.update((read(change / name) or "").encode("utf-8"))
    for rel in scope:
        digest.update(rel.encode("utf-8"))
        digest.update(file_digest(root, rel).encode("utf-8"))
    return digest.hexdigest()[:16]


def base_token(root, change, delta, scope):
    """What apply must find unchanged: everything the draft was written against."""
    source = source_of(root, change)
    rels = {INDEX, source + "/" + LOCK_NAME, source + "/" + change_doc(change).name, *scope}
    for capability in capabilities_of(delta):
        rels.update(cap_rel(capability, name) for name in ("spec.md", "implementation.md", "history.md"))
    digest = hashlib.sha256()
    for rel in sorted(rels):
        digest.update(("%s=%s\n" % (rel, file_digest(root, rel))).encode("utf-8"))
    return digest.hexdigest()[:16]


# ---------------------------------------------------------------- fold


def merge_conflict(root, change, text, delta=None):
    """The change document, then the catalog files of its delta, with git's conflict markers. None when clean."""
    source = source_of(root, change)
    if has_conflict(text):
        files = [source_of(root, change_doc(change))]
    elif delta is not None:
        rels = [INDEX] + [cap_rel(capability, name) for capability in capabilities_of(delta) for name in ("spec.md", "implementation.md", "history.md")]
        files = conflicted(root, rels)
    else:
        files = []
    if not files:
        return None
    return {"status": "merge-conflict", "files": files, "reason": conflict_message(files, source)}


def retires_designed(root, delta):
    for entry in delta["entries"]:
        if entry["op"] == "REMOVED":
            rule = rules_of(read(root / cap_rel(entry["capability"], "spec.md"))).get(entry["id"])
            if rule is not None and rule["designed"]:
                return True
    return False


def prepare_state(root, change, no_tasks=False):
    """Validate every precondition. Writes nothing."""
    if (root / JOURNAL).exists():
        return {"status": "recover-needed"}, None, RECOVER
    source = source_of(root, change)
    text = read(change_doc(change))
    if text is None:
        raise CapError("no spec.md or capability-delta.md in %s" % source)
    blocked = merge_conflict(root, change, text)
    if blocked:
        return blocked, None, DECISION
    delta, errors = parse_delta(text, source)
    if errors:
        return {"status": "invalid", "errors": errors}, None, INVALID
    if delta["none"]:
        return {"status": "no-rule-change", "source": source}, None, OK
    blocked = merge_conflict(root, change, text, delta)
    if blocked:
        return blocked, None, DECISION
    if is_design(delta) or (design_capable(delta, source) and retires_designed(root, delta)):
        return {"status": "invalid", "errors": ["%s designs or retires [designed] rules: publish it with capabilities.py publish-design --change %s" % (source, source)]}, None, INVALID
    tasks = open_tasks(change)
    if tasks is None and not no_tasks:
        return {"status": "blocked", "reason": "no tasks.md; pass --no-tasks for a change outside specify"}, None, DECISION
    if tasks:
        return {"status": "blocked", "reason": "%d open tasks" % tasks}, None, DECISION
    lock = load_lock(change)
    current = stamp(text, delta, source)
    if lock is None or lock["delta_sha"] != current["delta_sha"] or lock["spec_sha"] != current["spec_sha"]:
        return {"status": "needs-review"}, None, DECISION
    actions, conflicts = classify(root, delta, source)
    if conflicts:
        return {"status": "conflict", "conflicts": conflicts}, None, DECISION
    rows = delta_rows(delta, lambda capability: read(root / cap_rel(capability, "implementation.md")))
    scope = scope_of(root, change, rows)
    digest = input_digest(root, change, delta, scope)
    state = {
        "source": source,
        "scope": scope,
        "foreign": foreign_of(root, change, scope),
        "input_digest": digest,
        "token": base_token(root, change, delta, scope),
    }
    finished = all(action[1] == "done" for action in actions)
    state["status"] = "unchanged" if finished and (lock.get("fold") or {}).get("input_digest") == digest else "ready"
    return state, (delta, text, actions), OK


def public(state):
    return {key: value for key, value in state.items() if key != "token"}


def cmd_prepare(root, change, no_tasks):
    state, context, code = prepare_state(root, change, no_tasks)
    if code or state["status"] != "ready":
        return emit(public(state), code)
    delta = context[0]
    staging = "%s/%s-%s" % (STAGING, sha(state["source"]), uuid.uuid4().hex[:8])
    state["setup"] = ensure_setup(root)
    for capability in capabilities_of(delta):
        current = read(root / cap_rel(capability, "implementation.md"))
        write_file(root / staging / capability / "implementation.md", current or template("capability-implementation.md", capability=capability))
    write_file(root / staging / "manifest.json", dumps({"source": state["source"], "token": state["token"]}))
    state["staging"] = staging
    state["capabilities"] = capabilities_of(delta)
    return emit(public(state))


def replace_delta(text, raw):
    old = section(text, "Capability Delta")
    start = text.index(old)
    return text[:start] + raw + text[start + len(old):]


def delta_set(text, rule_id, op=None, fields=None):
    """Rewrite one entry of the delta in place: its operation, or some of its fields. Every other line stays."""
    raw = section(text, "Capability Delta")
    out, inside = [], False
    for line in raw.split("\n"):
        match = ENTRY.match(line)
        if line.startswith("#"):
            inside = bool(match) and match.group(2) == rule_id
            if inside and op:
                line = "### %s %s" % (op, rule_id)
        elif inside:
            field = re.match(r"^- ([A-Za-z-]+): (.*)$", line)
            if field and field.group(1) in (fields or {}):
                line = "- %s: %s" % (field.group(1), fields[field.group(1)])
        out.append(line)
    return replace_delta(text, "\n".join(out))


def delta_drop(text, rule_ids, reason):
    """Take entries out of the delta, and the NEW-CAPABILITY blocks nothing uses then. With nothing left, the delta says why."""
    raw = section(text, "Capability Delta")
    tail = raw[len(raw.rstrip("\n")):]
    entries = [entry for entry in parse_delta(text)[0]["entries"] if entry["id"] not in rule_ids]
    if not entries:
        head = raw[:raw.index(MARK) + len(MARK)]
        return replace_delta(text, "%s\n\nCapabilities: none — %s%s" % (head, reason, tail))
    used = {entry["capability"] for entry in entries}
    out, skipping = [], False
    for line in raw.split("\n"):
        if line.startswith("#"):
            match, new = ENTRY.match(line), re.match(r"^### NEW-CAPABILITY (\S+)\s*$", line)
            skipping = bool(match and match.group(2) in rule_ids) or bool(new and new.group(1) not in used)
        if not skipping:
            out.append(line)
    return replace_delta(text, "\n".join(out).rstrip("\n") + tail)


def normalize_implemented(root, text, source):
    """IMPLEMENTED does not change a rule, so its From and To are the catalog's text, whatever the model copied."""
    delta = parse_delta(text)[0]
    changes = []
    for entry in (delta or {}).get("entries", []):
        if entry["op"] != "IMPLEMENTED" or not CAPABILITY.match(entry.get("capability") or ""):
            continue
        rule = rules_of(read(root / cap_rel(entry["capability"], "spec.md"))).get(entry["id"])
        if rule is None or not (rule["designed"] or (rule["tag"] == source and not rule["inferred"])):
            continue
        if entry.get("from") == rule["text"] and entry.get("to") == rule["text"]:
            continue
        # A slip in the copy, not a new text: both copies alike, or only From off. A To of its own is a change, and declares MODIFIED.
        if entry.get("from") in (None, "(none)") or entry.get("to") not in (entry.get("from"), rule["text"]):
            continue
        changes.append({"rule": entry["id"], "from": entry.get("from"), "to": entry.get("to"), "catalog": rule["text"]})
        text = delta_set(text, entry["id"], fields={"From": rule["text"], "To": rule["text"]})
    return text, changes


def cmd_review(root, change, accept):
    if (root / JOURNAL).exists():
        return emit({"status": "recover-needed"}, RECOVER)
    source = source_of(root, change)
    doc = change_doc(change)
    text = read(doc)
    if text is None:
        raise CapError("no spec.md or capability-delta.md in %s" % source)
    blocked = merge_conflict(root, change, text)
    if blocked:
        return emit(blocked, DECISION)
    lock = load_lock(change)
    # Only before the first seal: later, a text that differs from the catalog means the base changed the rule.
    text, normalized = normalize_implemented(root, text, source) if lock is None else (text, [])
    delta, errors = parse_delta(text, source)
    if errors:
        return emit({"status": "invalid", "errors": errors}, INVALID)
    blocked = merge_conflict(root, change, text, delta)
    if blocked:
        return emit(blocked, DECISION)
    conflicts = classify(root, delta, source)[1]
    if conflicts:
        return emit({"status": "conflict", "conflicts": conflicts}, DECISION)
    current = stamp(text, delta, source)
    if lock is None or accept:
        data = dict(current)
        if lock and lock.get("fold"):
            data["fold"] = lock["fold"]
        setup = ensure_setup(root)
        with publish_lock(root):
            if normalized:
                write_file(doc, text)
            write_file(lock_path(change), dumps(data))
        out = {"status": "stamped", "setup": setup}
        if normalized:
            out["normalized"] = normalized
        return emit(out)
    changed = sorted(k for k in set(current["sections"]) | set(lock["sections"]) if current["sections"].get(k) != lock["sections"].get(k))
    delta_changed = current["delta_sha"] != lock["delta_sha"]
    if changed or delta_changed or current["spec_sha"] != lock["spec_sha"]:
        linked = {link for entry in delta["entries"] for link in split_links(entry["links"])}
        rules = [entry["id"] for entry in delta["entries"] if set(split_links(entry["links"])) & set(changed)]
        return emit({
            "status": "changed",
            "sections": changed,
            "linked": sorted(linked & set(changed)),
            "rules": sorted(rules),
            "delta_changed": delta_changed,
            "other_text": not changed and not delta_changed,
        }, DECISION)
    return emit({"status": "unchanged"})


def cmd_ensure(root, change):
    source = source_of(root, change)
    doc = change_doc(change)
    text = read(doc)
    if text is None:
        raise CapError("no spec.md or capability-delta.md in %s" % source)
    if section(text, "Capability Delta") is not None:
        return emit({"status": "present", "written": False})
    write_file(doc, text.rstrip("\n") + "\n\n## Capability Delta *(mandatory)*\n\n" + MARK + "\n")
    return emit({"status": "inserted", "written": True})


def rewrite_spec(text, capability, overview, actions, source):
    if text is None:
        text = template("capability-spec.md", capability=capability, overview=overview or "")
    rules = rules_of(text)
    for entry, what in actions:
        if what != "apply" or entry["capability"] != capability:
            continue
        if entry["op"] == "REMOVED":
            rules.pop(entry["id"], None)
        else:
            rules[entry["id"]] = {"text": entry["to"], "tag": source, "inferred": entry["op"] == "INFERRED", "designed": entry["op"] == "DESIGNED"}
    lines = []
    for rule_id in sorted(rules):
        rule = rules[rule_id]
        tag = " (%s)" % rule["tag"] if rule["tag"] else ""
        mark = " [inferred]" if rule["inferred"] else " [designed]" if rule["designed"] else ""
        lines.append("- **%s**%s: %s%s" % (rule_id, mark, rule["text"], tag))
    return text.replace(section(text, "Rules"), "## Rules\n\n" + "\n\n".join(lines) + ("\n\n" if lines else "\n"))


def changes_cell(entries):
    return "; ".join("%s %s" % (entry["op"], entry["id"]) for entry in entries)


def rewrite_history(text, capability, actions, source):
    if text is None:
        text = template("capability-history.md", capability=capability)
    entries = [entry for entry, _ in actions if entry["capability"] == capability]
    row = "| %s | %s |" % (source, changes_cell(entries))
    changes = section(text, "Changes")
    pattern = re.compile(r"^\| %s \|.*$" % re.escape(source), re.M)
    if pattern.search(changes):
        updated = pattern.sub(lambda _: row, changes)
    else:
        updated = changes.rstrip("\n") + "\n" + row + "\n\n"
    text = text.replace(changes, updated)
    for entry, what in actions:
        if what == "apply" and entry["capability"] == capability and entry["op"] == "REMOVED":
            retired = section(text, "Retired Rules")
            line = "| %s | %s | %s | %s |" % (entry["id"], entry["from"].replace("|", "\\|"), source, entry["replaced-by"])
            text = text.replace(retired, retired.rstrip("\n") + "\n" + line + "\n")
    return text


def rewrite_index(text, delta, statuses, specs=None, histories=None, capabilities=None):
    """One row for each capability of the delta, with its state recalculated (2.1).

    A row keeps its entry point; one that has none takes the first code anchor. ``specs`` and
    ``histories`` are the texts being published. A catalog with a [designed] rule gets the format seal.
    """
    if text is None:
        text = template("capability-index.md")
    specs, histories = specs or {}, histories or {}
    designed = False
    for capability in capabilities if capabilities is not None else capabilities_of(delta):
        rules = rules_of(specs.get(capability))
        designed = designed or any(rule["designed"] for rule in rules.values())
        state = capability_state(rules, retired_of(histories.get(capability))) if capability in specs else "consolidated"
        codes = [ref for row in statuses.get(capability, {}).values() for ref in row["code"]]
        lines = text.split("\n")
        hits = [number for number, line in enumerate(lines) if re.match(r"^\| \[%s\]\(" % re.escape(capability), line)]
        if not hits:
            planned = re.search(r"^\| %s \| [^|]* \| planned \|.*\n?" % re.escape(capability), text, re.M)
            if planned:
                text = text[:planned.start()] + text[planned.end():]
            entry_point = "`%s`" % codes[0] if codes else "none"
            text = text.rstrip("\n") + "\n" + index_row(capability, delta["new"].get(capability, ""), state, entry_point) + "\n"
            continue
        cells = index_row_cells(lines[hits[0]])
        covers = cells[1] if len(cells) > 1 and cells[1] else delta["new"].get(capability, "")
        kept = cells[3] if len(cells) > 3 else "none"
        entry_point = kept if kept not in ("", "none") else ("`%s`" % codes[0] if codes else "none")
        lines[hits[0]] = index_row(capability, covers, state, entry_point)
        for number in reversed(hits[1:]):
            del lines[number]
        text = "\n".join(lines)
    return with_seal(text) if designed else text


def draft_errors(root, delta, drafts, source):
    """Everything wrong with the model's drafts, before anything is published."""
    errors = []
    statuses = {capability: rule_status(text) for capability, text in drafts.items()}
    retirements = {capability: retirement_evidence(text) for capability, text in drafts.items()}
    declared = {entry["id"] for entry in delta["entries"] if entry["op"] != "REMOVED"}
    catalog = root / CATALOG
    known = set(declared)
    if catalog.is_dir():
        for spec in catalog.glob("*/spec.md"):
            known |= set(rules_of(read(spec)))

    def check_anchors(row):
        for ref in row["code"] + row["tests"]:
            if not anchor_resolves(root, ref):
                errors.append("anchor does not exist: %s" % ref)

    for entry in delta["entries"]:
        capability, rule_id = entry["capability"], entry["id"]
        if entry["op"] == "VALIDATED":
            continue
        if entry["op"] == "REMOVED":
            if rule_id in statuses[capability]:
                errors.append("Rule Status still has a block for retired rule %s" % rule_id)
            replacement = entry["replaced-by"]
            if replacement != "none":
                if replacement not in known - {rule_id}:
                    errors.append("%s: replacement %s does not exist" % (rule_id, replacement))
                continue
            row = retirements[capability].get(rule_id)
            if row is None:
                errors.append("%s: retired without replacement needs a Retirement Evidence block" % rule_id)
                continue
            if row["change"] != source:
                errors.append("%s: Retirement Evidence must name Change: %s" % (rule_id, source))
        else:
            row = statuses[capability].get(rule_id)
            if row is None:
                errors.append("no Rule Status block for %s" % rule_id)
                continue
        if row["state"] not in STATES:
            errors.append("invalid state for %s: %r" % (rule_id, row["state"]))
        check_anchors(row)
    return errors


def fold_anchors(root, delta, statuses, retirements, all_rows):
    anchors = {}
    for entry in delta["entries"]:
        rule_id = entry["id"]
        if entry["op"] == "VALIDATED":
            continue
        if entry["op"] != "REMOVED":
            anchors[rule_id] = anchors_of(root, statuses[entry["capability"]][rule_id])
        elif entry["replaced-by"] != "none":
            row = all_rows.get(entry["replaced-by"])
            if row:
                anchors[entry["replaced-by"]] = anchors_of(root, row)
        else:
            anchors[rule_id] = anchors_of(root, retirements[entry["capability"]][rule_id])
    return anchors


def cmd_apply(root, change, staged, no_tasks):
    staged = root / staged
    manifest_text = read(staged / "manifest.json")
    if manifest_text is None:
        return emit({"status": "needs-prepare", "reason": "no prepared draft at %s; run prepare" % staged}, DECISION)
    manifest = json.loads(manifest_text)
    with publish_lock(root):
        state, context, code = prepare_state(root, change, no_tasks)
        if code or state["status"] == "no-rule-change":
            return emit(public(state), code)
        if state["token"] != manifest.get("token") or state["source"] != manifest.get("source"):
            return emit({"status": "base-changed", "reason": "catalog or inputs changed after prepare; run prepare again"}, DECISION)
        if state["status"] == "unchanged":
            return emit({"status": "unchanged", "written": []})
        delta, text, actions = context
        source = state["source"]
        drafts = {}
        for capability in capabilities_of(delta):
            draft = read(staged / capability / "implementation.md")
            if draft is None:
                return emit({"status": "invalid-staging", "errors": ["staged implementation missing for " + capability]}, INVALID)
            drafts[capability] = draft
        errors = draft_errors(root, delta, drafts, source)
        if errors:
            return emit({"status": "invalid-staging", "errors": errors}, INVALID)
        statuses = {capability: rule_status(draft) for capability, draft in drafts.items()}
        retirements = {capability: retirement_evidence(draft) for capability, draft in drafts.items()}
        all_rows = {rule_id: row for rows in statuses.values() for rule_id, row in rows.items()}
        for implementation in (root / CATALOG).glob("*/implementation.md"):
            if implementation.parent.name not in statuses:
                all_rows.update(rule_status(read(implementation)))
        plan = {}
        for capability in capabilities_of(delta):
            plan[cap_rel(capability, "implementation.md")] = drafts[capability]
            plan[cap_rel(capability, "spec.md")] = rewrite_spec(read(root / cap_rel(capability, "spec.md")), capability, delta["new"].get(capability), actions, source)
            plan[cap_rel(capability, "history.md")] = rewrite_history(read(root / cap_rel(capability, "history.md")), capability, actions, source)
        specs = {capability: plan[cap_rel(capability, "spec.md")] for capability in capabilities_of(delta)}
        histories = {capability: plan[cap_rel(capability, "history.md")] for capability in capabilities_of(delta)}
        plan[INDEX] = rewrite_index(read(root / INDEX), delta, statuses, specs, histories)
        scope = scope_of(root, change, delta_rows(delta, drafts.get))
        fold = {"input_digest": input_digest(root, change, delta, scope), "anchors": fold_anchors(root, delta, statuses, retirements, all_rows)}
        plan[source + "/" + LOCK_NAME] = dumps(stamp(text, delta, source, fold))
        written = publish(root, plan, source_of(root, staged))
        return emit({"status": "published", "written": written, "foreign_ignored": state["foreign"]})


def publish(root, plan, staging):
    """Journal first, then replace each file, then drop the journal. The rename is the commit point.

    A file planned as None is removed: rebase drops a capability the base never had.
    """
    targets = {}
    for rel, new in plan.items():
        old = read(root / rel)
        if old != new:
            targets[rel] = {"old": sha(old) if old is not None else None, "new": sha(new) if new is not None else None}
    if not targets:
        shutil.rmtree(str(root / staging), ignore_errors=True)
        return []
    journal, pending = root / JOURNAL, root / (JOURNAL + ".tmp")
    shutil.rmtree(str(pending), ignore_errors=True)
    (pending / "blobs").mkdir(parents=True, exist_ok=True)
    for rel in targets:
        if plan[rel] is not None:
            write_file(pending / "blobs" / sha(rel), plan[rel])
    write_file(pending / "targets.json", dumps({"targets": targets, "staging": staging}))
    sync_dir(pending / "blobs")
    sync_dir(pending)
    if os.environ.get("CAP_CRASH_AFTER") == "before-journal":
        os._exit(9)
    os.replace(str(pending), str(journal))
    sync_dir(journal.parent)
    roll_forward(root)
    return sorted(targets)


def roll_forward(root):
    journal = root / JOURNAL
    record = json.loads((journal / "targets.json").read_text(encoding="utf-8"))
    targets = record["targets"]
    edited = []
    for rel, target in targets.items():
        current = read(root / rel)
        if (sha(current) if current is not None else None) not in (target["old"], target["new"]):
            edited.append(rel)
    if edited:
        return edited
    limit = os.environ.get("CAP_CRASH_AFTER")
    done = 0
    for rel in sorted(targets):
        current = read(root / rel)
        if targets[rel]["new"] is None and current is None:
            continue
        if current is not None and sha(current) == targets[rel]["new"]:
            continue
        if limit not in (None, "end") and done == int(limit):
            os._exit(9)
        destination = root / rel
        if targets[rel]["new"] is None:
            os.remove(str(destination))
            with contextlib.suppress(OSError):
                destination.parent.rmdir()
            sync_dir(destination.parent if destination.parent.is_dir() else destination.parent.parent)
            done += 1
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".captmp")
        shutil.copyfile(str(journal / "blobs" / sha(rel)), str(temporary))
        # Writable on purpose: Windows refuses fsync on a read-only descriptor.
        with open(str(temporary), "r+b") as handle:
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(destination))
        sync_dir(destination.parent)
        done += 1
    if limit == "end":
        os._exit(9)
    shutil.rmtree(str(journal))
    sync_dir(journal.parent)
    shutil.rmtree(str(root / record["staging"]), ignore_errors=True)
    return []


def cmd_recover(root):
    if not (root / STATE_DIR).is_dir():
        return emit({"status": "clean"})
    with publish_lock(root):
        if not (root / JOURNAL).exists():
            return emit({"status": "clean"})
        edited = roll_forward(root)
        if edited:
            return emit({"status": "manual", "edited_since": edited}, RECOVER)
        return emit({"status": "recovered"})


def cmd_status(root, capability):
    if capability:
        spec = read(root / cap_rel(capability, "spec.md"))
        if spec is None:
            raise CapError("capability not found: %s" % capability)
        implementation = read(root / cap_rel(capability, "implementation.md"))
        history = read(root / cap_rel(capability, "history.md"))
        rules = rules_of(spec)
        return emit({
            "capability": capability,
            "state": capability_state(rules, retired_of(history)),
            "rules": rules,
            "rule_status": rule_status(implementation),
            "history": history or "",
        })
    return emit(catalog_summary(root))


def catalog_summary(root):
    rows = re.findall(r"^\| \[([a-z0-9-]+)\][^|]*\| ([^|]*) \|", read(root / INDEX) or "", re.M)
    capabilities = {}
    for name, covers in rows:
        statuses = rule_status(read(root / cap_rel(name, "implementation.md")))
        rules = rules_of(read(root / cap_rel(name, "spec.md")))
        capabilities[name] = {
            "covers": covers,
            "state": capability_state(rules, retired_of(read(root / cap_rel(name, "history.md")))),
            "rules": len(rules),
            "inferred": sorted(rule_id for rule_id, rule in rules.items() if rule["inferred"]),
            # Approved and not built yet: not current behaviour, so no code to look for.
            "designed": sorted(rule_id for rule_id, rule in rules.items() if rule["designed"]),
            "not_conforming": sorted(rule_id for rule_id, row in statuses.items() if row["state"] != "conforming"),
        }
    planned = re.findall(r"^\| ([a-z][a-z0-9-]*) \| ([^|]*) \| planned \|", read(root / INDEX) or "", re.M)
    return {
        "catalog": (root / INDEX).is_file(),
        "capabilities": capabilities,
        "planned": {name: covers for name, covers in planned if name not in capabilities},
        "journal_pending": (root / JOURNAL).exists(),
    }


def cmd_clarify_context(root, given):
    """Read-only. The feature, its parsed delta and every capability, before the first question of clarify.

    Ends well without a feature: clarify runs its own check right after this and reports it.
    """
    feature, spec, delta, errors = None, None, None, []
    try:
        change = resolve_change(root, given)
        feature = source_of(root, change)
    except (CapError, ValueError, AttributeError):
        change = None
    text = read(change / DOCS[0]) if change is not None else None
    if text is not None:
        spec = "%s/%s" % (feature, DOCS[0])
        delta, errors = parse_delta(text)
    if delta is not None:
        delta = {key: value for key, value in delta.items() if key != "raw"}
    return emit(dict(catalog_summary(root), feature=feature, spec=spec, delta=delta, delta_errors=errors))


def cmd_locate(root, capability):
    """Read-only. For one capability, each rule with its origin, code and tests, and whether those anchors still resolve."""
    if not capability:
        return cmd_status(root, None)
    if not CAPABILITY.match(capability):
        raise CapError("invalid capability name: %s" % capability)
    spec = read(root / cap_rel(capability, "spec.md"))
    if spec is None:
        raise CapError("capability not found: %s" % capability)
    statuses = rule_status(read(root / cap_rel(capability, "implementation.md")))
    history = read(root / cap_rel(capability, "history.md"))

    def anchors(refs):
        return [{"ref": ref, "resolves": anchor_resolves(root, ref)} for ref in refs]

    rules = []
    for rule_id, rule in sorted(rules_of(spec).items()):
        row = statuses.get(rule_id) or {}
        rules.append({
            "id": rule_id,
            "text": rule["text"],
            "inferred": rule["inferred"],
            "origin": rule["tag"],
            "state": row.get("state"),
            "observed": row.get("observed"),
            "code": anchors(row.get("code", [])),
            "tests": anchors(row.get("tests", [])),
            "manual": row.get("manual"),
        })
    changes = [{"change": cells[0], "what": " | ".join(cells[1:])} for cells in table_rows(history, "Changes")]
    state = capability_state(rules_of(spec), retired_of(history))
    # Approved and not built: listed apart, so a reader never takes them for current behaviour.
    designed = sorted(rule_id for rule_id, rule in rules_of(spec).items() if rule["designed"])
    return emit({"capability": capability, "state": state, "designed": designed, "rules": rules, "changes": changes, "retired": retired_of(history)})


def cmd_scaffold(root, capability, covers):
    """List a capability nobody has consolidated yet. It holds no rules until a record adds them."""
    if not capability or not CAPABILITY.match(capability):
        raise CapError("scaffold requires --capability matching %s" % CAPABILITY.pattern)
    covers = norm(covers or "")
    if not covers or "|" in covers:
        raise CapError("scaffold requires --covers: one line of text without |")
    with publish_lock(root):
        if (root / JOURNAL).exists():
            return emit({"status": "recover-needed"}, RECOVER)
        text = read(root / INDEX) or template("capability-index.md")
        name = re.escape(capability)
        if re.search(r"^\| (?:\[%s\]\S*|%s) \|" % (name, name), text, re.M) or (root / CATALOG / capability).is_dir():
            return emit({"status": "unchanged", "capability": capability})
        setup = ensure_setup(root)
        write_file(root / INDEX, text.rstrip("\n") + "\n| %s | %s | planned | none |\n" % (capability, covers))
    return emit({"status": "planned", "capability": capability, "setup": setup})


# ---------------------------------------------------------------- lifecycle: design, rebase and defer


def find_rule(root, rule_id):
    """The capability that holds a rule, and the rule; (None, None) when no capability has it."""
    catalog = root / CATALOG
    for spec in sorted(catalog.glob("*/spec.md")) if catalog.is_dir() else []:
        rule = rules_of(read(spec)).get(rule_id)
        if rule is not None:
            return spec.parent.name, rule
    return None, None


def cmd_delta_block(root, ids):
    """The IMPLEMENTED blocks of [designed] rules, with the catalog's text, for a spec to copy."""
    if not ids:
        raise CapError("delta-block requires --implement and the ids of [designed] rules")
    found, errors = [], []
    for rule_id in ids:
        capability, rule = find_rule(root, rule_id)
        if rule is None:
            errors.append("%s: not found in the catalog" % rule_id)
        elif not rule["designed"]:
            errors.append("%s: the rule is not [designed]; a spec changes an implemented rule with MODIFIED" % rule_id)
        else:
            block = "### IMPLEMENTED %s\n- Capability: %s\n- From: %s\n- To: %s\n- Links: FR-###" % (rule_id, capability, rule["text"], rule["text"])
            found.append({"rule": rule_id, "capability": capability, "block": block})
    if errors:
        return emit({"status": "invalid", "errors": errors}, INVALID)
    return emit({
        "status": "ok",
        "blocks": found,
        "text": "\n\n".join(item["block"] for item in found) + "\n",
        "links": "replace FR-### with the requirements and acceptance criteria of the spec that build each rule",
    })


def cmd_publish_design(root, change):
    """review, prepare --no-tasks and apply of a design record, as one operation under the lock. Repeating it changes nothing."""
    source = source_of(root, change)
    if not is_record(source):
        raise CapError("publish-design takes a design record under %s/, not %s" % (CHANGES, source))
    with publish_lock(root):
        if (root / JOURNAL).exists():
            return emit({"status": "recover-needed"}, RECOVER)
        text = read(change_doc(change))
        if text is None:
            raise CapError("no spec.md or capability-delta.md in %s" % source)
        blocked = merge_conflict(root, change, text)
        if blocked:
            return emit(blocked, DECISION)
        delta, errors = parse_delta(text, source)
        if errors:
            return emit({"status": "invalid", "errors": errors}, INVALID)
        if delta["none"]:
            return emit({"status": "no-rule-change", "source": source})
        others = sorted({entry["op"] for entry in delta["entries"]} - DESIGN_OPS)
        if others:
            return emit({"status": "invalid", "errors": ["publish-design publishes NEW-CAPABILITY, DESIGNED and REMOVED of [designed] rules, not %s; fold publishes the rest" % ", ".join(others)]}, INVALID)
        built = []
        for entry in delta["entries"]:
            rule = rules_of(read(root / cap_rel(entry["capability"], "spec.md"))).get(entry["id"])
            if entry["op"] == "REMOVED" and rule is not None and not rule["designed"]:
                built.append("REMOVED %s: the rule is built; retire it with a change that brings evidence, through fold" % entry["id"])
        if built:
            return emit({"status": "invalid", "errors": built}, INVALID)
        blocked = merge_conflict(root, change, text, delta)
        if blocked:
            return emit(blocked, DECISION)
        actions, conflicts = classify(root, delta, source)
        if conflicts:
            return emit({"status": "conflict", "conflicts": conflicts}, DECISION)
        plan, specs, histories, statuses = {}, {}, {}, {}
        for capability in capabilities_of(delta):
            implementation = read(root / cap_rel(capability, "implementation.md"))
            # No code yet, so no block: the file starts empty and fold fills it.
            plan[cap_rel(capability, "implementation.md")] = implementation if implementation is not None else template("capability-implementation.md", capability=capability)
            specs[capability] = plan[cap_rel(capability, "spec.md")] = rewrite_spec(read(root / cap_rel(capability, "spec.md")), capability, delta["new"].get(capability), actions, source)
            histories[capability] = plan[cap_rel(capability, "history.md")] = rewrite_history(read(root / cap_rel(capability, "history.md")), capability, actions, source)
            statuses[capability] = rule_status(plan[cap_rel(capability, "implementation.md")])
        plan[INDEX] = rewrite_index(read(root / INDEX), delta, statuses, specs, histories)
        plan[source + "/" + LOCK_NAME] = dumps(stamp(text, delta, source))
        setup = ensure_setup(root)
        written = publish(root, plan, "%s/%s-design" % (STAGING, sha(source)))
        return emit({"status": "published" if written else "unchanged", "written": written, "setup": setup})


def raw_blocks(text, title):
    """The ### blocks of a section as written, by rule id, in their order."""
    out, current = {}, None
    for line in (section(text or "", title) or "").split("\n")[1:]:
        match = BLOCK.match(line)
        if match:
            current = match.group(1)
            out[current] = [line]
        elif current is not None:
            out[current].append(line)
    return {rule_id: "\n".join(lines).rstrip("\n") for rule_id, lines in out.items()}


def replace_section(text, title, body):
    """Swap a ## section, heading included, keeping the blank line before the next one."""
    old = section(text, title)
    if old is None:
        return text.rstrip("\n") + "\n\n" + body.rstrip("\n") + "\n"
    start = text.index(old)
    tail = "\n\n" if start + len(old) < len(text) else "\n"
    return text[:start] + body.rstrip("\n") + tail + text[start + len(old):]


def with_blocks(text, title, found):
    return replace_section(text, title, "## %s\n\n%s" % (title, "\n\n".join(found.values())) if found else "## " + title)


def paragraphs(text, title):
    body = (section(text or "", title) or "").split("\n", 1)
    return [part.strip("\n") for part in re.split(r"\n\s*\n", body[1] if len(body) > 1 else "") if part.strip()]


def table_parts(text, title):
    """The heading and column lines of a table section, and its rows, as written."""
    raw = section(text or "", title)
    if raw is None:
        return None, []
    lines = raw.rstrip("\n").split("\n")
    pipes = [number for number, line in enumerate(lines) if line.startswith("|")]
    end = pipes[1] + 1 if len(pipes) > 1 and re.match(r"^\|[\s:|-]+\|$", lines[pipes[1]].strip()) else len(lines)
    return lines[:end], [line for line in lines[end:] if line.startswith("|")]


def merged_implementation(capability, base, branch, ancestor, actions, source, unverified):
    """The base's implementation.md plus what the branch wrote for this change's rules.

    Its Rule Status and Retirement Evidence blocks, the Decisions rows that name it, and the Approach
    paragraphs and Anchors rows the branch added since the common ancestor. Prose is added whole: it does not mix.
    """
    text = base if base is not None else template("capability-implementation.md", capability=capability)
    entries = {entry["id"]: entry for entry, _ in actions}
    theirs, gone = raw_blocks(branch, "Rule Status"), raw_blocks(branch, "Retirement Evidence")
    status, retirements = raw_blocks(text, "Rule Status"), raw_blocks(text, "Retirement Evidence")
    for rule_id, entry in entries.items():
        if entry["op"] == "REMOVED":
            status.pop(rule_id, None)
            if rule_id in gone:
                retirements[rule_id] = gone[rule_id]
        elif rule_id in theirs:
            block = theirs[rule_id]
            if rule_id in unverified:
                # The code was observed against the old text: fold observes it again.
                block = re.sub(r"^- State: .*$", "- State: unverified", block, flags=re.M)
            status[rule_id] = block
    text = with_blocks(with_blocks(text, "Rule Status", status), "Retirement Evidence", retirements)
    mine = paragraphs(text, "Approach")
    seen = {norm(part) for part in mine + paragraphs(ancestor, "Approach")}
    added = [part for part in paragraphs(branch, "Approach") if norm(part) not in seen]
    if added:
        text = replace_section(text, "Approach", "## Approach\n\n" + "\n\n".join(mine + added))
    head, rows = table_parts(text, "Decisions")
    have = {norm(row) for row in rows}
    extra = [row for row in table_parts(branch, "Decisions")[1] if index_row_cells(row)[-1] == source and norm(row) not in have]
    if head is not None and extra:
        text = replace_section(text, "Decisions", "\n".join(head + rows + extra))
    head, rows = table_parts(text, "Anchors")
    known = {index_row_cells(row)[0] for row in rows + table_parts(ancestor, "Anchors")[1]}
    extra = [row for row in table_parts(branch, "Anchors")[1] if index_row_cells(row)[0] not in known]
    if head is not None and extra:
        text = replace_section(text, "Anchors", "\n".join(head + rows + extra))
    return text


def index_lines(text):
    """(name, line) of each capability row, linked or planned."""
    out = []
    for line in (text or "").split("\n"):
        match = re.match(r"^\| (?:\[([a-z0-9-]+)\]\([^)]*\)|([a-z][a-z0-9-]*)) \|", line)
        if match:
            out.append((match.group(1) or match.group(2), line))
    return out


def rebased_plan(root, source, delta, touched, base, branch, ancestor, folded, unverified=()):
    """The catalog of the capabilities ``touched`` and ``delta`` name, as the base plus ``delta``.

    ``base``, ``branch`` and ``ancestor`` read a catalog path at each side. A change never folded
    adds nothing yet: fold applies it later. A capability that ends up with nothing of the change gets
    the base's files, or none when the base never had it. Returns the plan and any classification conflicts.
    """
    actions, conflicts = classify(root, delta, source, base)
    if conflicts:
        return None, conflicts
    plan, statuses, specs, histories, live = {}, {}, {}, {}, []
    capabilities = sorted(set(touched) | set(capabilities_of(delta)))
    for capability in capabilities:
        rels = {name: cap_rel(capability, name) for name in ("spec.md", "implementation.md", "history.md")}
        mine = [action for action in actions if action[0]["capability"] == capability] if folded else []
        if not mine:
            for rel in rels.values():
                plan[rel] = base(rel)
            continue
        live.append(capability)
        specs[capability] = plan[rels["spec.md"]] = rewrite_spec(base(rels["spec.md"]), capability, delta["new"].get(capability), mine, source)
        histories[capability] = plan[rels["history.md"]] = rewrite_history(base(rels["history.md"]), capability, mine, source)
        implementation = merged_implementation(capability, base(rels["implementation.md"]), branch(rels["implementation.md"]), ancestor(rels["implementation.md"]), mine, source, unverified)
        plan[rels["implementation.md"]] = implementation
        statuses[capability] = rule_status(implementation)
    index = base(INDEX) or template("capability-index.md")
    present = {name for name, _ in index_lines(index)} | {name for name, _ in index_lines(ancestor(INDEX))}
    # Rows the branch added for capabilities of other changes stay; the rows of this one come from the base.
    for name, line in index_lines(branch(INDEX)):
        if name not in present and name not in capabilities:
            index = index.rstrip("\n") + "\n" + line + "\n"
            present.add(name)
    plan[INDEX] = rewrite_index(index, delta, statuses, specs, histories, live)
    return plan, []


def resolve_rev(root, ref):
    found = git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
    return found.strip() if found else None


def base_ref(root, onto):
    ref = onto or load_config(root)["base_branch"] or "main"
    rev = resolve_rev(root, ref)
    if rev is None:
        raise CapError("base not found: %s; pass --onto <ref> or set base_branch in %s" % (ref, CONFIG))
    return ref, rev


def holds_change(root, rev, source):
    return any(MARK in (git(root, "show", "%s:%s/%s" % (rev, source, name)) or "") for name in DOCS)


def rebase_sides(root, source, onto):
    """(branch, base) as commits. The two sides of a merge in progress or just committed; else HEAD and the base.

    Of the two sides, the branch is the one that holds the change, so either merge direction works. Never
    the working tree, which may hold conflict markers.
    """
    merging = resolve_rev(root, "MERGE_HEAD")
    if merging:
        first, second = resolve_rev(root, "HEAD"), merging
    elif resolve_rev(root, "HEAD^2"):
        first, second = resolve_rev(root, "HEAD^1"), resolve_rev(root, "HEAD^2")
    else:
        head = resolve_rev(root, "HEAD")
        if head is None:
            raise CapError("rebase needs a git repository with at least one commit")
        return head, base_ref(root, onto)[1]
    if not holds_change(root, first, source) and holds_change(root, second, source):
        first, second = second, first
    if not holds_change(root, first, source):
        raise CapError("neither side of the merge holds %s; commit the change on its branch first" % source)
    return first, base_ref(root, onto)[1] if onto else second


def reader(root, rev):
    return lambda rel: git(root, "show", "%s:%s" % (rev, rel)) if rev else None


def was_folded(change, lock, histories, source):
    """A change is in its branch's catalog once fold published it: its history row, or a fold in its lock."""
    if (lock or {}).get("fold"):
        return True
    return any(cells[0] == source for text in histories for cells in table_rows(text, "Changes"))


def other_folds(source, capabilities, base, branch, ancestor):
    """Changes the branch folded into the same capabilities, besides this one. Rebuilding one change would lose them."""
    found = set()
    for capability in capabilities:
        rel = cap_rel(capability, "history.md")
        known = {cells[0] for text in (base(rel), ancestor(rel)) for cells in table_rows(text, "Changes")}
        found |= {cells[0] for cells in table_rows(branch(rel), "Changes") if cells[0] not in known and cells[0] != source}
    return sorted(found)


def relocked(lock, text, delta, source, dropped):
    """The lock for a delta rebase or defer rewrote: the same seal, and fold's observations of the rules that stay."""
    data = stamp(text, delta, source)
    fold = dict((lock or {}).get("fold") or {})
    if fold and not delta["none"]:
        fold["anchors"] = {rule_id: files for rule_id, files in (fold.get("anchors") or {}).items() if rule_id not in dropped}
        data["fold"] = fold
    return data


def drop_reason(entries, how):
    links = sorted({link for entry in entries for link in split_links(entry["links"]) if link != "none"})
    reason = "%s left this change (%s)" % (", ".join(entry["id"] for entry in entries), how)
    return reason + ("; %s out of scope" % ", ".join(links) if links else "")


def cmd_rebase(root, change, onto, adopt, keep, drop, reason):
    """3.3 of the plan: the catalog of a branch after merging its base, as the base plus this change's delta."""
    source = source_of(root, change)
    doc = change_doc(change)
    text = read(doc)
    if text is None:
        raise CapError("no spec.md or capability-delta.md in %s" % source)
    if has_conflict(text):
        raise CapError("%s has merge conflict markers; resolve them in the spec, then run rebase" % source_of(root, doc))
    delta, errors = parse_delta(text, source)
    if errors:
        return emit({"status": "invalid", "errors": errors}, INVALID)
    if delta["none"]:
        return emit({"status": "no-rule-change", "source": source})
    choices = {}
    for choice, ids in (("adopt", adopt), ("keep", keep), ("drop", drop)):
        for rule_id in ids or []:
            if choices.setdefault(rule_id, choice) != choice:
                raise CapError("%s: choose one of --adopt, --keep and --drop" % rule_id)
    entries = {entry["id"]: entry for entry in delta["entries"]}
    unknown = sorted(set(choices) - set(entries))
    if unknown:
        raise CapError("not in the delta of %s: %s" % (source, ", ".join(unknown)))
    branch_rev, base_rev = rebase_sides(root, source, onto)
    ancestor_rev = (git(root, "merge-base", branch_rev, base_rev) or "").strip() or None
    base, branch, ancestor = reader(root, base_rev), reader(root, branch_rev), reader(root, ancestor_rev)
    with publish_lock(root):
        if (root / JOURNAL).exists():
            return emit({"status": "recover-needed"}, RECOVER)
        pending, resolved, notes, dropped, unverified = [], [], [], [], set()
        new_text = text
        for entry in delta["entries"]:
            rule_id, choice = entry["id"], choices.get(entry["id"])
            conflict = classify(root, dict(delta, entries=[entry]), source, base)[1]
            if not conflict:
                if choice in ("adopt", "keep"):
                    raise CapError("%s does not conflict with the base; only --drop takes it out" % rule_id)
                if choice == "drop":
                    dropped.append(entry)
                continue
            said = rules_of(base(cap_rel(entry["capability"], "spec.md"))).get(rule_id)
            retired = retired_of(base(cap_rel(entry["capability"], "history.md"))).get(rule_id) if said is None else None
            options = []
            if said is not None and said["designed"] and entry["op"] != "REMOVED":
                options.append("adopt")
            if said is not None and said["text"] != entry["to"]:
                options.append("keep")
            options.append("drop")
            if choice is None:
                pending.append({
                    "rule": rule_id, "op": entry["op"], "capability": entry["capability"], "conflict": conflict[0],
                    "spec": entry["to"], "base": said["text"] if said else None, "base_designed": bool(said and said["designed"]),
                    "retired_by": retired["by"] if retired else None, "choices": options,
                })
                continue
            if choice not in options:
                if retired:
                    why = "the base retired the rule (retired by %s) and retired ids are not reused; --drop it, and add a new rule with ADDED if the spec still needs one" % retired["by"]
                elif choice == "adopt":
                    why = "the base's rule is not [designed], so there is no design to adopt; --keep or --drop"
                else:
                    why = "the base already says the spec's text; --adopt"
                raise CapError("--%s %s: %s" % (choice, rule_id, why))
            resolved.append({"rule": rule_id, "choice": choice})
            links = ", ".join(split_links(entry["links"]))
            if choice == "adopt":
                new_text = delta_set(new_text, rule_id, op="IMPLEMENTED", fields={"From": said["text"], "To": said["text"]})
                unverified.add(rule_id)
                notes.append("%s: the spec now builds the base's text; its block stays unverified until fold observes the code again" % rule_id)
                if links and links != "none":
                    notes.append("%s: %s of %s still say the old text; update them" % (rule_id, links, source))
            elif choice == "keep":
                fields = {"From": said["text"]}
                new_text = delta_set(new_text, rule_id, op="MODIFIED" if entry["op"] != "REMOVED" else None, fields=fields)
                notes.append("%s: the spec changes the base's text %r to %r; that is a business decision for the PO" % (rule_id, said["text"], entry["to"]))
            else:
                dropped.append(entry)
        if pending:
            return emit({
                "status": "decision",
                "source": source,
                "conflicts": pending,
                "next": "choose for each rule: capabilities.py rebase --change %s --adopt <id> | --keep <id> | --drop <id>" % source,
            }, DECISION)
        for entry in dropped:
            code = rule_status(branch(cap_rel(entry["capability"], "implementation.md"))).get(entry["id"], {}).get("code") or []
            notes.append("%s left the delta%s%s" % (
                entry["id"],
                "; %s linked it: mark them out of scope" % entry["links"] if entry["links"] != "none" else "",
                "; the code that built it has no rule now: %s" % ", ".join(code) if code else "",
            ))
        if dropped:
            new_text = delta_drop(new_text, {entry["id"] for entry in dropped}, reason or drop_reason(dropped, "rebase --drop"))
        new_delta, errors = parse_delta(new_text, source)
        if errors:
            raise CapError("the rebased delta is not valid: %s" % "; ".join(errors))
        touched = capabilities_of(delta)
        lock = load_lock(change)
        folded = was_folded(change, lock, [branch(cap_rel(capability, "history.md")) for capability in touched], source)
        others = other_folds(source, touched, base, branch, ancestor) if folded else []
        if others:
            raise CapError("this branch also folded %s into the same capabilities; rebase rebuilds one change and would lose them" % ", ".join(others))
        plan, conflicts = rebased_plan(root, source, new_delta, touched, base, branch, ancestor, folded, unverified)
        if conflicts:
            return emit({"status": "conflict", "conflicts": conflicts}, DECISION)
        changed = new_text != text
        if changed:
            plan[source_of(root, doc)] = new_text
            if lock is not None:
                plan[source + "/" + LOCK_NAME] = dumps(relocked(lock, new_text, new_delta, source, {entry["id"] for entry in dropped}))
        written = publish(root, plan, "%s/%s-rebase" % (STAGING, sha(source)))
        steps = ["git add specs/_capabilities %s and finish the merge" % source]
        if unverified:
            steps.append("run fold so it observes %s again" % ", ".join(sorted(unverified)))
        return emit({
            "status": "rebased",
            "source": source,
            "branch": branch_rev,
            "base": base_rev,
            "folded": folded,
            "written": written,
            "delta_changed": changed,
            "stamped": changed and lock is not None,
            "resolved": resolved,
            "notes": notes,
            "next": "; ".join(steps),
        })


def cmd_defer(root, change, ids, onto, reason):
    """7.9 of the plan: leave rules out of a spec's delta. A [designed] rule goes back to designed."""
    if not ids:
        raise CapError("defer takes the ids of the rules to leave out: defer --change <spec> R-x")
    source = source_of(root, change)
    doc = change_doc(change)
    text = read(doc)
    if text is None:
        raise CapError("no spec.md or capability-delta.md in %s" % source)
    blocked = merge_conflict(root, change, text)
    if blocked:
        return emit(blocked, DECISION)
    delta, errors = parse_delta(text, source)
    if errors:
        return emit({"status": "invalid", "errors": errors}, INVALID)
    if design_capable(delta, source):
        raise CapError("defer leaves rules out of a spec; a design record changes with another design record")
    entries = {entry["id"]: entry for entry in delta["entries"]}
    unknown = sorted(set(ids) - set(entries))
    if unknown:
        raise CapError("not in the delta of %s: %s" % (source, ", ".join(unknown)))
    blocked = merge_conflict(root, change, text, delta)
    if blocked:
        return emit(blocked, DECISION)
    deferred = [entries[rule_id] for rule_id in sorted(set(ids))]
    with publish_lock(root):
        if (root / JOURNAL).exists():
            return emit({"status": "recover-needed"}, RECOVER)
        new_text = delta_drop(text, set(ids), reason or drop_reason(deferred, "defer"))
        new_delta, errors = parse_delta(new_text, source)
        if errors:
            raise CapError("the delta left after defer is not valid: %s" % "; ".join(errors))
        touched = capabilities_of(delta)
        lock = load_lock(change)
        here = lambda rel: read(root / rel)
        folded = was_folded(change, lock, [here(cap_rel(capability, "history.md")) for capability in touched], source)
        plan = {}
        if folded:
            # The catalog of this branch is its base point plus the delta: rebuild it with the delta that is left.
            ref = base_ref(root, onto)[0]
            point = (git(root, "merge-base", "HEAD", ref) or "").strip()
            if not point:
                raise CapError("no merge base with %s; pass --onto <ref>" % ref)
            start = reader(root, point)
            plan, conflicts = rebased_plan(root, source, new_delta, touched, start, here, start, True)
            if conflicts:
                return emit({"status": "conflict", "conflicts": conflicts, "reason": "the base changed these rules; run capabilities.py rebase --change %s first" % source}, DECISION)
        plan[source_of(root, doc)] = new_text
        if lock is not None:
            plan[source + "/" + LOCK_NAME] = dumps(relocked(lock, new_text, new_delta, source, set(ids)))
        written = publish(root, plan, "%s/%s-defer" % (STAGING, sha(source)))
    designed = [entry["id"] for entry in deferred if rules_of(read(root / cap_rel(entry["capability"], "spec.md"))).get(entry["id"], {}).get("designed")]
    return emit({
        "status": "deferred",
        "source": source,
        "rules": [entry["id"] for entry in deferred],
        "links": {entry["id"]: split_links(entry["links"]) for entry in deferred},
        "designed": designed,
        "folded": folded,
        "written": written,
        "stamped": lock is not None,
        "next": "mark the requirements in links out of scope in %s, then run review" % source_of(root, doc),
    })


def overview_of(text):
    for line in (section(text or "", "Overview") or "").split("\n")[1:]:
        if line.strip():
            return norm(line).replace("|", "\\|")
    return ""


def cmd_index(root, rebuild):
    """index --rebuild: the index from the capability directories, one row each, with its state recalculated."""
    if not rebuild:
        raise CapError("index takes --rebuild")
    with publish_lock(root):
        if (root / JOURNAL).exists():
            return emit({"status": "recover-needed"}, RECOVER)
        catalog = root / CATALOG
        names = sorted(p.name for p in catalog.iterdir() if p.is_dir() and p.name != "_changes" and not p.name.startswith(".") and (p / "spec.md").is_file()) if catalog.is_dir() else []
        text = read(root / INDEX) or template("capability-index.md")
        lines = [line for line in text.split("\n") if not CONFLICT_SIDE.match(line) and line != "======="]
        rows, out, done, designed, states = {}, [], set(), False, {}
        for name, line in index_lines("\n".join(lines)):
            rows.setdefault(name, line)

        def row_for(name):
            spec = read(catalog / name / "spec.md")
            rules = rules_of(spec)
            states[name] = capability_state(rules, retired_of(read(catalog / name / "history.md")))
            cells = index_row_cells(rows[name]) if name in rows else []
            linked = bool(cells) and cells[0].startswith("[")
            covers = cells[1] if len(cells) > 1 and cells[1] else overview_of(spec)
            kept = cells[3] if linked and len(cells) > 3 else "none"
            codes = [ref for row in rule_status(read(catalog / name / "implementation.md")).values() for ref in row["code"]]
            entry_point = kept if kept not in ("", "none") else ("`%s`" % codes[0] if codes else "none")
            return index_row(name, covers, states[name], entry_point), any(rule["designed"] for rule in rules.values())

        last = None
        for line in lines:
            match = index_lines(line)
            if not match:
                out.append(line)
                continue
            name = match[0][0]
            if name in done:
                continue
            done.add(name)
            if name in names:
                line, marked = row_for(name)
                designed = designed or marked
            elif not re.match(r"^\| %s \| [^|]* \| planned \|" % re.escape(name), line):
                continue
            out.append(line)
            last = len(out)
        missing = [name for name in names if name not in done]
        added = []
        for name in missing:
            line, marked = row_for(name)
            designed = designed or marked
            added.append(line)
        if added:
            if last is None:
                out = ("\n".join(out).rstrip("\n") + "\n" + "\n".join(added)).split("\n")
            else:
                out[last:last] = added
        new = "\n".join(out)
        new = new.rstrip("\n") + "\n"
        if designed:
            new = with_seal(new)
        written = publish(root, {INDEX: new}, "%s/index-rebuild" % STAGING)
    return emit({"status": "rebuilt" if written else "unchanged", "written": written, "capabilities": states})


# ---------------------------------------------------------------- test evidence


def junit_cases(path):
    cases = []
    for case in ET.parse(str(path)).getroot().iter("testcase"):
        passed = not any(child.tag in ("failure", "error", "skipped") for child in case)
        cases.append((case.get("name") or "", case.get("classname") or "", passed, case.get("file") or ""))
    return cases


def title_matches(title, name):
    """A title as the file writes it (``at %d minutes``, ``at {0} minutes``) matches each of its variants."""
    if title == name:
        return True
    pieces = TITLE_SLOT.split(title)
    return len(pieces) > 1 and re.fullmatch(".+".join(re.escape(piece) for piece in pieces), name) is not None


def same_file(ref_path, path):
    """Either may be relative to a subdirectory: a runner's root is not always the repository's."""
    return bool(path) and (ref_path == path or ref_path.endswith("/" + path) or path.endswith("/" + ref_path))


def script_test_hits(parts, cases):
    """``path::[describe::]title``. Jest names the file in ``file``, Vitest in ``classname``. No file, no match."""
    title = " ".join(" ".join(parts[1:]).split())
    return [case for case in cases if same_file(parts[0], case[3] or case[1]) and title_matches(title, " ".join(case[0].replace(" > ", " ").split()))]


def class_test_hits(parts, cases):
    """``path::[Class::]name``: pytest, and JUnit, which writes ``$`` for a nested class and ``()``, ``(long)[1]`` after a method."""
    expected = ".".join([re.sub(r"\.[^./]+$", "", parts[0]).replace("/", ".")] + parts[1:-1])
    name = parts[-1]
    hits = []
    for case in cases:
        classname = case[1].replace("$", ".")
        same_class = classname == expected or classname.endswith("." + expected) or expected.endswith("." + classname)
        if same_class and (case[0].startswith((name + "[", name + "(")) or title_matches(name, case[0])):
            hits.append(case)
    return hits


def test_result(ref, cases):
    """Every variant of a test must pass; skipped is not passed."""
    parts = ref.split("::")
    if not "".join(TITLE_SLOT.split(parts[-1])).strip():
        return "missing"
    hits = (script_test_hits if parts[0].endswith(SCRIPT_TESTS) else class_test_hits)(parts, cases)
    if not hits:
        return "missing"
    return "passed" if all(case[2] for case in hits) else "failed"


def report_moment(value):
    """None if it names no zone: Gradle and Jest write UTC there, older pytest local time, and nothing says which."""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment.timestamp() if moment.tzinfo else None


# ---------------------------------------------------------------- check


def naming_errors(root):
    catalog = root / CATALOG
    if not catalog.is_dir():
        return []
    errors = []
    for child in sorted(catalog.iterdir()):
        name = child.name
        if name.startswith("."):
            continue
        if child.is_file():
            if name != "index.md":
                errors.append("%s/%s: only index.md may sit at the catalog root" % (CATALOG, name))
        elif name == "_changes":
            for record in sorted(child.iterdir()):
                if not record.name.startswith(".") and not (record.is_dir() and RECORD.match(record.name)):
                    errors.append("%s/%s: records must be directories named YYYYMMDD-slug" % (CHANGES, record.name))
        elif not CAPABILITY.match(name):
            errors.append("%s/%s: capability directories must match %s" % (CATALOG, name, CAPABILITY.pattern))
    for path in catalog.rglob("*"):
        if path.is_file() and path.name in FORBIDDEN_NAMES:
            errors.append("%s: this file name is not allowed under the catalog" % source_of(root, path))
    return errors


def under_root(name, roots):
    parts = name.split("/")
    for root in roots:
        pattern = root.split("/")
        if len(parts) > len(pattern) and all(fnmatch.fnmatchcase(parts[i], pattern[i]) for i in range(len(pattern))):
            return True
    return False


def in_catalog(name):
    return name.startswith(CATALOG + "/") and not name.startswith(CHANGES + "/")


def not_a_change(name):
    return in_catalog(name) or (name.startswith(".specify/") and not name.startswith(".specify/bugs/"))


class Check:
    def __init__(self, root, mode, base, report, combined):
        self.root, self.mode, self.base, self.report, self.combined = root, mode, base, report, combined
        self.config = load_config(root)
        self.hard, self.notes, self.states, self.revalidated = [], [], {}, []
        self.merge_base = None
        self.cases = None
        self.names = []
        self.entries_by_source = {}
        self.covered = set()
        self.capabilities = []
        self.head_rules = {}
        self.head_status = {}

    def soft(self, message):
        (self.hard if self.mode == "ci" else self.notes).append(message)

    def show(self, rev, rel):
        return git(self.root, "show", "%s:%s" % (rev, rel))

    def resolve_base(self):
        if not self.base:
            return
        if git(self.root, "rev-parse", "--verify", "--quiet", self.base + "^{commit}") is None:
            raise CapError("base not found: %s" % self.base)
        merge_base = git(self.root, "merge-base", self.base, "HEAD")
        if merge_base is None:
            raise CapError("no merge base with %s; CI must fetch the whole history (fetch-depth: 0)" % self.base)
        self.merge_base = merge_base.strip()

    def report_files(self):
        """Each ``--report`` is a file or a directory: Surefire and Gradle write one XML per class."""
        files = []
        for value in self.report:
            path = self.root / value
            if path.is_dir():
                found = sorted(item for item in path.rglob("*.xml") if item.is_file())
                if not found:
                    raise CapError("no XML test report in %s" % value)
                files.extend(found)
            elif path.is_file():
                files.append(path)
            else:
                raise CapError("test report not found: %s" % value)
        return files

    def written_at(self, tree, path):
        """The oldest suite that names its zone. Without one, when the file was written."""
        moments = []
        for suite in tree.iter("testsuite"):
            value = suite.get("timestamp")
            if not value:
                continue
            try:
                moment = report_moment(value)
            except ValueError:
                self.notes.append("test report timestamp not understood: %r" % value)
                continue
            if moment is not None:
                moments.append(moment)
        return min(moments) if moments else path.stat().st_mtime

    def load_report(self):
        if not self.report:
            return
        cases, rejected = [], []
        head_time = int((git(self.root, "log", "-1", "--format=%ct", "HEAD") or "0").strip() or 0)
        for path in self.report_files():
            name = os.path.relpath(str(path), str(self.root))
            try:
                cases.extend(junit_cases(path))
                tree = ET.parse(str(path)).getroot()
            except ET.ParseError as error:
                raise CapError("test report is not valid XML: %s: %s" % (name, error))
            if git(self.root, "ls-files", "--error-unmatch", "--", str(path)) is not None:
                rejected.append("test report %s is tracked by git; evidence must come from this run" % name)
            elif self.written_at(tree, path) < head_time - REPORT_SKEW_SECONDS:
                rejected.append("test report %s is older than the evaluated commit" % name)
        for message in rejected:
            self.soft(message)
        if not rejected:
            self.cases = cases

    def discover(self):
        self.names = sorted(set(git_names(self.root, "diff", "--name-only", "--no-renames", "-z", self.merge_base)) | set(git_names(self.root, "ls-files", "--others", "--exclude-standard", "-z")))
        found, seen = {}, set()
        for name in self.names:
            if not_a_change(name):
                continue
            directory = Path(name).parent
            while str(directory) != "." and str(directory) not in seen:
                seen.add(str(directory))
                text = read(change_doc(self.root / directory))
                if text and MARK in text:
                    found[str(directory)] = self.root / directory
                    break
                directory = directory.parent
        for name in self.names:
            if os.path.basename(name) in DOCS and not not_a_change(name):
                self.check_doc_presence(name)
        return list(found.values())

    def check_doc_presence(self, name):
        text = read(self.root / name)
        before = self.show(self.merge_base, name)
        if before is not None:
            if MARK in before and (text is None or MARK not in text):
                self.hard.append("%s: a registered capability delta was removed (document deleted, renamed or marker gone)" % name)
            return
        if text is None or MARK in text:
            return
        if os.path.basename(name) == "capability-delta.md":
            self.hard.append("%s: change record without a capability delta" % name)
        elif under_root(name, self.config["feature_roots"]):
            self.hard.append("%s: new feature spec without a capability delta" % name)
        elif FR_LINE.search(text):
            self.hard.append("%s: looks like a feature spec (FR-### requirements) outside feature_roots and has no capability delta; add its root to feature_roots in %s and declare the delta" % (name, CONFIG))

    def delivered(self, source, doc_rel, text, change):
        """True when the merge base already holds this change. Its delta is then a sealed record."""
        if not self.merge_base:
            return False
        before = self.show(self.merge_base, doc_rel)
        if not before or MARK not in before:
            return False
        delta_before = parse_delta(before)[0]
        if delta_before is None:
            return False
        sealed = bool(delta_before["none"])
        for capability in capabilities_of(delta_before):
            history = self.show(self.merge_base, cap_rel(capability, "history.md"))
            if any(cells[0] == source for cells in table_rows(history, "Changes")):
                sealed = True
        if not sealed:
            return False
        now = section(text, "Capability Delta") or ""
        if norm(now) != norm(delta_before["raw"]):
            self.hard.append("%s: the delta of a delivered change was edited; it is the record that backs the rule, declare a new change instead" % source)
        lock_rel = source + "/" + LOCK_NAME
        if self.show(self.merge_base, lock_rel) != read(self.root / lock_rel):
            self.hard.append("%s: the lock of a delivered change was changed or removed; restore it with git checkout %s -- %s, and declare a new change to change a rule" % (source, self.base, lock_rel))
        if norm(text) != norm(before):
            self.notes.append("%s: record already delivered on %s was edited in this change" % (source, self.base))
        return True

    def tests_problems(self, rule_id, row):
        if row["manual"]:
            if self.config["allow_manual_evidence"]:
                self.notes.append("%s: manual evidence accepted: %s" % (rule_id, row["manual"]))
                return []
            return ["%s: manual evidence is not allowed (%s); set allow_manual_evidence to accept it" % (rule_id, row["manual"])]
        if not row["tests"]:
            return ["%s: no mapped test" % rule_id]
        if self.cases is None:
            return ["%s: no test report for this revision" % rule_id]
        results = [(ref, test_result(ref, self.cases)) for ref in row["tests"]]
        return ["%s: mapped test %s %s" % (rule_id, ref, result) for ref, result in results if result != "passed"]

    def freshness_problems(self, rule_id, row, lock, test_problems):
        stored = ((lock or {}).get("fold") or {}).get("anchors", {}).get(rule_id) or {}
        current = anchors_of(self.root, row)
        if stored == current:
            return []
        files = sorted(path for path in set(stored) | set(current) if stored.get(path) != current.get(path))
        changed = ", ".join(files)
        if not self.combined:
            return ["%s: observation is stale, anchored file changed after fold: %s" % (rule_id, changed)]
        if row["manual"]:
            return ["%s: anchored file changed after fold (%s) and manual evidence cannot revalidate it" % (rule_id, changed)]
        if test_problems:
            return ["%s: anchored file changed after fold (%s) and the observation could not be revalidated in this commit" % (rule_id, changed)]
        self.revalidated.append({"rule": rule_id, "files": files, "tests": row["tests"]})
        return []

    def rule_evidence(self, rule_id, row, lock, fresh=True):
        problems = []
        if row["state"] != "conforming":
            problems.append("%s: state is %s (%s)" % (rule_id, row["state"], row["observed"]))
        if not row["code"]:
            problems.append("%s: no code anchor" % rule_id)
        for ref in row["code"]:
            if not anchor_resolves(self.root, ref):
                problems.append("%s: code anchor does not resolve: %s" % (rule_id, ref))
        tests = self.tests_problems(rule_id, row)
        return problems + tests + (self.freshness_problems(rule_id, row, lock, tests) if fresh else [])

    def retirement_problems(self, entry, source, lock):
        rule_id, replacement = entry["id"], entry["replaced-by"]
        if replacement != "none":
            for capability, rules in self.head_rules.items():
                if replacement in rules:
                    row = self.head_status[capability].get(replacement)
                    if row is None:
                        return ["%s: replacement %s has no Rule Status block" % (rule_id, replacement)]
                    return ["%s: replacement %s" % (rule_id, problem) for problem in self.rule_evidence(replacement, row, lock)]
            return ["%s: replacement %s does not exist in the catalog" % (rule_id, replacement)]
        row = retirement_evidence(read(self.root / cap_rel(entry["capability"], "implementation.md"))).get(rule_id)
        if row is None:
            return ["%s: retired without replacement and no Retirement Evidence block" % rule_id]
        problems = []
        if row["change"] != source:
            problems.append("%s: Retirement Evidence names %r instead of %s" % (rule_id, row["change"], source))
        if row["state"] == "discrepant":
            problems.append("%s: retired, but the behaviour is still present (%s)" % (rule_id, row["observed"]))
        elif row["state"] != "conforming":
            problems.append("%s: retirement state is %s" % (rule_id, row["state"]))
        tests = self.tests_problems(rule_id, row)
        if not row["manual"] and not row["tests"]:
            tests = ["%s: retired without replacement needs at least one passing absence test" % rule_id]
        return problems + tests + self.freshness_problems(rule_id, row, lock, tests)

    def base_comparison(self, entry, source):
        """E2: the rule at the direct base against what this change started from."""
        if not self.base:
            return None
        capability, rule_id, op = entry["capability"], entry["id"], entry["op"]
        base_says = rules_of(self.show(self.base, cap_rel(capability, "spec.md"))).get(rule_id)
        # A [designed] rule on the base is approved, not built: only a DESIGNED entry finds it delivered there.
        already = base_says is not None and op != "REMOVED" and base_says["text"] == entry["to"] and base_says["designed"] == (op == "DESIGNED")
        where = "%s %s" % (op, rule_id)
        retired_by = None if base_says is not None else retired_of(self.show(self.base, cap_rel(capability, "history.md"))).get(rule_id, {}).get("by")
        if op in ("ADDED", "INFERRED") or (op == "DESIGNED" and entry["from"] == "(none)"):
            if base_says is not None and not already:
                self.hard.append("%s: already exists on %s as %r" % (where, self.base, base_says["text"]))
            if base_says is None and rule_id in retired_of(self.show(self.base, cap_rel(capability, "history.md"))):
                self.hard.append(where + ": retired ids are not reused")
        elif op == "VALIDATED":
            if base_says is None or base_says["text"] != entry["to"]:
                self.hard.append("%s: %s does not hold this text" % (where, self.base))
        else:
            says = base_says["text"] if base_says else None
            if already:
                self.notes.append("%s: %s already delivered on %s with the same text" % (source, rule_id, self.base))
            elif says is None and retired_by and op != "REMOVED":
                self.hard.append("%s: branch started from %r but %s retired the rule (retired by %s); run capabilities.py rebase --change %s" % (where, entry["from"], self.base, retired_by, source))
            elif says != entry["from"]:
                self.hard.append("%s: branch started from %r but %s now says %r; this change proposes %r" % (where, entry["from"], self.base, says, entry["to"]))
        return already

    def was_designed(self, entry):
        """Whether the rule a REMOVED retires was [designed]: in the catalog still, at the merge base, or by a DESIGNED of this branch."""
        rule_id, rel = entry["id"], cap_rel(entry["capability"], "spec.md")
        now = self.head_rules.get(entry["capability"], {}).get(rule_id)
        if now is not None:
            return now["designed"]
        if self.merge_base:
            before = rules_of(self.show(self.merge_base, rel)).get(rule_id)
            if before is not None:
                return before["designed"]
        return any(other["op"] == "DESIGNED" and other["id"] == rule_id for entries in self.entries_by_source.values() for other in entries)

    def entry_applied(self, entry, source, already):
        capability, rule_id, op = entry["capability"], entry["id"], entry["op"]
        rule = self.head_rules.get(capability, {}).get(rule_id)
        if op == "REMOVED":
            retired = retired_of(read(self.root / cap_rel(capability, "history.md")))
            return rule is None and retired.get(rule_id, {}).get("by") == source
        if rule is None or rule["text"] != entry["to"]:
            return False
        if rule["inferred"] != (op == "INFERRED"):
            return False
        # An IMPLEMENTED is applied once the mark is gone and the spec is the origin, never while the rule is still [designed].
        if rule["designed"] != (op == "DESIGNED"):
            return False
        return rule["tag"] == source or bool(already)

    def eval_change(self, change):
        source = source_of(self.root, change)
        doc = change_doc(change)
        text = read(doc)
        if text is None:
            self.hard.append("%s: no spec.md or capability-delta.md" % source)
            self.states[source] = "invalid"
            return
        if has_conflict(text):
            self.hard.append("%s: %s" % (source, conflict_message([source_of(self.root, doc)], source)))
            self.states[source] = "invalid"
            return
        if self.delivered(source, source_of(self.root, doc), text, change):
            self.states[source] = "delivered"
            return
        delta, errors = parse_delta(text, source)
        if errors:
            self.hard.extend("%s: %s" % (source, error) for error in errors)
            self.states[source] = "invalid"
            return
        if delta["none"]:
            self.states[source] = "no-rule-change"
            return
        self.entries_by_source[source] = delta["entries"]
        self.covered.update((entry["capability"], entry["id"]) for entry in delta["entries"])
        lock = load_lock(change)
        current = stamp(text, delta, source)
        reviewed = lock is not None and lock["delta_sha"] == current["delta_sha"] and lock["spec_sha"] == current["spec_sha"]
        tasks = open_tasks(change)
        applied = []
        for entry in delta["entries"]:
            already = self.base_comparison(entry, source)
            applied.append((entry, self.entry_applied(entry, source, already)))
        if tasks and self.config["allow_partial_features"] and reviewed and not any(done for _, done in applied):
            self.notes.append("%s: integrated in parts, %d open tasks and catalog not folded yet" % (source, tasks))
            self.states[source] = "partial"
            return
        messages = []
        if not reviewed:
            messages.append("%s: delta not reviewed for this spec (hook skipped or spec edited later)" % source)
        if tasks:
            messages.append("%s: %d open tasks" % (source, tasks))
        elif tasks is None and not is_design(delta):
            self.notes.append("%s: no tasks.md; readiness rests on the delta and test evidence" % source)
        for entry, done in applied:
            if not done:
                now = self.head_rules.get(entry["capability"], {}).get(entry["id"])
                if now is not None and now["designed"] and entry["op"] != "DESIGNED" and now["text"] == entry["to"]:
                    messages.append("%s %s: the rule is still [designed] in the catalog; fold publishes it with its code and tests" % (entry["op"], entry["id"]))
                    continue
                messages.append("%s %s: catalog says %r, delta requires %r" % (entry["op"], entry["id"], now["text"] if now else "(absent)", entry["to"]))
        state = "reviewed" if reviewed else "drafted"
        if reviewed and all(done for _, done in applied):
            state = "prepared"
        problems = []
        for entry in delta["entries"]:
            if entry["op"] == "DESIGNED" or (entry["op"] == "REMOVED" and self.was_designed(entry)):
                # Approved, not built: a design record brings no evidence, and retiring an unbuilt rule needs none.
                if entry["op"] == "REMOVED" and not design_capable(delta, source):
                    problems.append("REMOVED %s: a [designed] rule is retired only by a design record; to leave it out of this spec, run capabilities.py defer" % entry["id"])
                continue
            if entry["op"] == "REMOVED":
                problems.extend(self.retirement_problems(entry, source, lock))
            elif entry["op"] in ("ADDED", "MODIFIED", "IMPLEMENTED"):
                row = self.head_status.get(entry["capability"], {}).get(entry["id"])
                if row is None:
                    problems.append("%s: no Rule Status block" % entry["id"])
                else:
                    problems.extend(self.rule_evidence(entry["id"], row, lock))
            else:
                # INFERRED and VALIDATED owe nothing while unverified. A claim needs evidence, and discrepant blocks. A validation stamps no anchors.
                row = self.head_status.get(entry["capability"], {}).get(entry["id"])
                if row is not None and row["state"] != "unverified":
                    problems.extend(self.rule_evidence(entry["id"], row, lock, fresh=entry["op"] != "VALIDATED"))
        if self.mode == "ci":
            self.hard.extend(messages)
            self.hard.extend("%s: %s" % (source, problem) for problem in problems)
            if state == "prepared" and not messages and not problems:
                state = "ready"
        else:
            self.notes.extend(messages)
            self.notes.extend("%s: %s" % (source, problem) for problem in problems)
        self.states[source] = state

    def load_catalog(self):
        catalog = self.root / CATALOG
        names = sorted(p.name for p in catalog.iterdir() if p.is_dir() and p.name != "_changes" and not p.name.startswith(".")) if catalog.is_dir() else []
        self.capabilities = names
        for name in names:
            text = read(catalog / name / "spec.md")
            self.head_rules[name] = rules_of(text)
            self.head_status[name] = rule_status(read(catalog / name / "implementation.md"))

    def check_catalog_shape(self):
        if catalog_is_ignored(self.root):
            self.hard.append("%s: %s" % (CATALOG, IGNORED_CATALOG))
        self.hard.extend(naming_errors(self.root))
        owners = {}
        for name in self.capabilities:
            text = read(self.root / cap_rel(name, "spec.md"))
            if text is None:
                self.hard.append("%s: capability without spec.md" % name)
                continue
            self.hard.extend("%s: %s" % (cap_rel(name, "spec.md"), error) for error in catalog_errors(text))
            retired = retired_of(read(self.root / cap_rel(name, "history.md")))
            for rule_id in self.head_rules[name]:
                owners.setdefault(rule_id, []).append(name)
                if rule_id in retired:
                    self.hard.append("%s: retired ids are not reused" % rule_id)
        for rule_id, names in sorted(owners.items()):
            if len(names) > 1:
                self.hard.append("%s: rule id used by several capabilities: %s" % (rule_id, ", ".join(names)))
        index = read(self.root / INDEX) or ""
        rows = re.findall(r"^\| \[([a-z0-9-]+)\]", index, re.M)
        for name in sorted({row for row in rows if rows.count(row) > 1}):
            self.hard.append("index.md: duplicated capability %s; after a merge, run capabilities.py rebase --change <feature>, or index --rebuild" % name)
        for name in self.capabilities:
            if name not in rows and self.head_rules[name]:
                self.hard.append("index.md: capability %s has rules and no row" % name)
        for name in sorted(set(rows) - set(self.capabilities)):
            self.hard.append("index.md: capability %s has a row and no directory" % name)
        self.check_index_states(index)
        if any(rule["designed"] for rules in self.head_rules.values() for rule in rules.values()) and catalog_format(index) < CATALOG_FORMAT:
            self.hard.append("index.md: the catalog holds [designed] rules but not the format seal %s; run capabilities.py index --rebuild" % FORMAT_SEAL)
        catalog = self.root / CATALOG
        files = [source_of(self.root, path) for path in sorted(catalog.rglob("*.md")) if path.is_file()] if catalog.is_dir() else []
        for rel in conflicted(self.root, files):
            self.hard.append("%s: %s" % (rel, conflict_message([rel])))

    def check_index_states(self, index):
        """Each row says what its rules make it (2.1). A row left without rules and still consolidated is legacy, and stays."""
        for line in index.splitlines():
            match = INDEX_ROW.match(line)
            if not match or match.group(1) not in self.head_rules:
                continue
            name, cells = match.group(1), index_row_cells(line)
            said = cells[2] if len(cells) > 2 else ""
            rules = self.head_rules[name]
            expected = capability_state(rules, retired_of(read(self.root / cap_rel(name, "history.md"))))
            if said != expected and not (not rules and said == "consolidated"):
                self.hard.append("index.md: %s says %s but its rules make it %s; run capabilities.py index --rebuild" % (name, said or "nothing", expected))

    def check_provenance(self):
        """Every rule must be backed by the delta its tag points to."""
        for capability, rules in self.head_rules.items():
            for rule_id, rule in sorted(rules.items()):
                problem = self.provenance_problem(capability, rule_id, rule)
                if problem:
                    self.soft("%s (%s): %s" % (rule_id, capability, problem))

    def provenance_problem(self, capability, rule_id, rule):
        if not rule["tag"]:
            return "rule has no origin tag"
        try:
            source_of(self.root, self.root / rule["tag"])
        except CapError:
            return "origin %s is outside the repository" % rule["tag"]
        text = read(change_doc(self.root / rule["tag"]))
        if text is None:
            return "origin %s does not exist" % rule["tag"]
        delta = parse_delta(text)[0]
        for entry in (delta or {}).get("entries", []):
            if entry["id"] == rule_id and entry["op"] != "REMOVED" and entry.get("capability") == capability:
                if entry.get("to") != rule["text"]:
                    return "origin %s sets %r but the catalog says %r" % (rule["tag"], entry.get("to"), rule["text"])
                if rule["inferred"] != (entry["op"] == "INFERRED"):
                    return "origin %s does not match the [inferred] mark" % rule["tag"]
                if rule["designed"] != (entry["op"] == "DESIGNED"):
                    return "origin %s does not match the [designed] mark: only a DESIGNED entry sets it, and every other one clears it" % rule["tag"]
                return None
        return "origin %s does not establish this rule" % rule["tag"]

    def authorized(self, capability, rule_id, before, after):
        for source, entries in self.entries_by_source.items():
            for entry in entries:
                if entry["id"] != rule_id or entry["capability"] != capability:
                    continue
                if after is None:
                    if entry["op"] == "REMOVED":
                        return True
                    continue
                if entry["to"] != after["text"] or after["tag"] != source:
                    continue
                if after["designed"] != (entry["op"] == "DESIGNED"):
                    continue
                if entry["op"] == "DESIGNED" and (before is None or before["designed"]):
                    return True
                if before is not None and before["designed"] and entry["op"] == "IMPLEMENTED" and before["text"] == after["text"] and not after["inferred"]:
                    return True
                if before is None and entry["op"] in ("ADDED", "INFERRED") and after["inferred"] == (entry["op"] == "INFERRED"):
                    return True
                if before is not None and entry["op"] == "MODIFIED" and not after["inferred"]:
                    return True
                if before is not None and entry["op"] == "VALIDATED" and before["inferred"] and not after["inferred"] and before["text"] == after["text"]:
                    return True
        return False

    def capabilities_at_merge_base(self):
        listed = git_names(self.root, "ls-tree", "-d", "-z", "--name-only", self.merge_base, CATALOG + "/")
        return [path.split("/")[-1] for path in listed if not path.endswith("/_changes")]

    def check_reverse(self):
        """Every change to an approved rule must be authorized by a delta of this change."""
        for capability in sorted(set(self.capabilities) | set(self.capabilities_at_merge_base())):
            old = rules_of(self.show(self.merge_base, cap_rel(capability, "spec.md")))
            new = self.head_rules.get(capability, {})
            for rule_id in sorted(set(old) | set(new)):
                before, after = old.get(rule_id), new.get(rule_id)
                if before == after or self.authorized(capability, rule_id, before, after):
                    continue
                if after is None:
                    detail = "removed (it said %r)" % before["text"]
                elif before is None:
                    detail = "added as %r" % after["text"]
                else:
                    detail = "%s said %r with origin %s, now says %r with origin %s" % (self.base, before["text"], before["tag"], after["text"], after["tag"])
                self.hard.append("%s (%s): catalog rule changed without an authorizing delta in this change: %s" % (rule_id, capability, detail))

    def check_history(self):
        """history.md is append-only against the merge base, and new rows must match a delta."""
        for capability in sorted(set(self.capabilities) | set(self.capabilities_at_merge_base())):
            rel = cap_rel(capability, "history.md")
            old_text, new_text = self.show(self.merge_base, rel), read(self.root / rel)
            if new_text is None:
                if old_text is not None:
                    self.hard.append("%s: history was removed" % rel)
                continue
            for title in ("Changes", "Retired Rules"):
                old_rows, new_rows = table_rows(old_text, title), table_rows(new_text, title)
                for row in old_rows:
                    if row not in new_rows:
                        self.hard.append("%s: row removed or edited in %s: %s" % (rel, title, " | ".join(row)))
            for row in table_rows(new_text, "Changes"):
                if row not in table_rows(old_text, "Changes"):
                    self.check_new_change_row(rel, capability, row)
            for row in table_rows(new_text, "Retired Rules"):
                if row not in table_rows(old_text, "Retired Rules"):
                    self.check_new_retired_row(rel, capability, row)

    def check_new_change_row(self, rel, capability, row):
        entries = [entry for entry in self.entries_by_source.get(row[0], []) if entry["capability"] == capability]
        if not entries or len(row) < 2 or row[1] != changes_cell(entries):
            self.hard.append("%s: new row does not match a delta in this change: %s" % (rel, " | ".join(row)))

    def check_new_retired_row(self, rel, capability, row):
        if len(row) >= 4:
            for entry in self.entries_by_source.get(row[2], []):
                if entry["op"] == "REMOVED" and entry["id"] == row[0] and entry["capability"] == capability and entry["from"] == row[1] and entry["replaced-by"] == row[3]:
                    return
        self.hard.append("%s: new retired row does not match a delta in this change: %s" % (rel, " | ".join(row)))

    def check_rule_status_changes(self):
        """Rule Status may change without a delta, but a claim of conformity needs evidence and a state cannot be given up while its code moves."""
        touched = {posixpath.normpath(name) for name in self.names}
        for capability in self.capabilities:
            old = rule_status(self.show(self.merge_base, cap_rel(capability, "implementation.md")))
            new = self.head_status[capability]
            for rule_id, row in sorted(new.items()):
                if (capability, rule_id) in self.covered or old.get(rule_id) == row:
                    continue
                was = old.get(rule_id)
                if row["state"] != "conforming":
                    if was and was["state"] != row["state"]:
                        message = "%s (%s): state went from %s to %s with no delta in this change" % (rule_id, capability, was["state"], row["state"])
                        anchored = {anchor_file(ref) for ref in was["code"] + was["tests"] + row["code"] + row["tests"]}
                        (self.soft if touched & anchored else self.notes.append)(message)
                    continue
                for problem in self.tests_problems(rule_id, row):
                    self.soft("%s (Rule Status changed to conforming): %s" % (capability, problem))
                for ref in row["code"] + row["tests"]:
                    if not anchor_resolves(self.root, ref):
                        self.soft("%s: anchor does not exist: %s" % (rule_id, ref))
            for rule_id in sorted(set(old) - set(new)):
                if rule_id in self.head_rules[capability]:
                    self.soft("%s (%s): Rule Status block removed while the rule is still in force" % (rule_id, capability))

    def check_anchored_code(self):
        """A file anchored to a rule changed: its anchors must still exist and its tests must pass, even without a delta."""
        touched = {posixpath.normpath(name) for name in self.names}
        for capability in self.capabilities:
            for rule_id, row in sorted(self.head_status[capability].items()):
                if (capability, rule_id) in self.covered:
                    continue
                code_changed = touched & {anchor_file(ref) for ref in row["code"]}
                if not code_changed and not touched & {anchor_file(ref) for ref in row["tests"]}:
                    continue
                if code_changed:
                    self.notes.append("%s: anchored code changed without a delta" % rule_id)
                for ref in row["code"] + row["tests"]:
                    if not anchor_resolves(self.root, ref):
                        self.soft("%s: anchor does not exist: %s" % (rule_id, ref))
                if not row["tests"]:
                    continue
                for problem in self.tests_problems(rule_id, row):
                    self.soft("anchored code changed: %s" % problem)

    def check_own_files(self):
        """CI runs the copy in this revision, so a PR can weaken its own check. Say so."""
        changed = [name for name in self.names if name.startswith(EXTENSION_DIR + "/")]
        if changed:
            self.notes.append("this change edits the extension that evaluates it, and CI runs this copy; review it: %s" % ", ".join(changed))

    def run(self, explicit):
        self.resolve_base()
        if self.base:
            problem = format_error(self.show(self.base, INDEX), "%s:%s" % (self.base, INDEX))
            if problem:
                raise CapError(problem)
        if (self.root / JOURNAL).exists():
            return emit({"mode": self.mode, "hard": ["fold interrupted or in progress: run recover"], "notes": [], "states": {}, "revalidated": []}, HARD)
        self.load_report()
        self.load_catalog()
        targets = list(explicit)
        if self.merge_base:
            targets += self.discover()
        unique = {path.resolve(): path for path in targets}
        for change in unique.values():
            self.eval_change(change)
        self.check_catalog_shape()
        self.check_provenance()
        if self.merge_base:
            self.check_reverse()
            self.check_history()
            self.check_rule_status_changes()
            self.check_anchored_code()
            self.check_own_files()
        result = {"mode": self.mode, "hard": self.hard, "notes": self.notes, "states": self.states, "revalidated": self.revalidated}
        return emit(result, HARD if self.hard else OK)


def build_parser():
    parser = argparse.ArgumentParser(description="Capability catalog mechanics")
    parser.add_argument("command", choices=["status", "locate", "clarify-context", "scaffold", "ensure", "review", "prepare", "apply", "recover", "check", "publish-design", "delta-block", "rebase", "defer", "index"])
    parser.add_argument("ids", nargs="*", help="defer: the rules to leave out of the delta")
    parser.add_argument("--root", default=".")
    parser.add_argument("--change", action="append", default=[])
    parser.add_argument("--capability")
    parser.add_argument("--covers", help="scaffold: what the capability covers, in one line")
    parser.add_argument("--staged")
    parser.add_argument("--accept", action="store_true")
    parser.add_argument("--no-tasks", action="store_true")
    parser.add_argument("--mode", choices=["dev", "ci"], default="dev")
    parser.add_argument("--base")
    parser.add_argument("--report", action="extend", nargs="+", help="check: JUnit XML files or directories that hold them")
    parser.add_argument("--combined", action="store_true", help="evaluate a merge queue commit: changed anchors must be revalidated by this commit's tests")
    parser.add_argument("--implement", action="extend", nargs="+", default=[], help="delta-block: the [designed] rules a spec builds")
    parser.add_argument("--onto", help="rebase, defer: the base branch, instead of base_branch from the config")
    parser.add_argument("--adopt", action="extend", nargs="+", default=[], help="rebase: the spec builds the base's text of these rules")
    parser.add_argument("--keep", action="extend", nargs="+", default=[], help="rebase: the spec keeps its text of these rules, as MODIFIED")
    parser.add_argument("--drop", action="extend", nargs="+", default=[], help="rebase: these rules leave the delta")
    parser.add_argument("--reason", help="rebase, defer: why, when no rule is left in the delta")
    parser.add_argument("--rebuild", action="store_true", help="index: regenerate the index from the capability directories")
    return parser


def dispatch(args, root):
    problem = format_error(read(root / INDEX))
    if problem:
        raise CapError(problem)
    if args.ids and args.command != "defer":
        raise CapError("%s takes no rule ids; only defer does" % args.command)
    if args.command == "status":
        return cmd_status(root, args.capability)
    if args.command == "locate":
        return cmd_locate(root, args.capability)
    if args.command == "clarify-context":
        return cmd_clarify_context(root, args.change)
    if args.command == "scaffold":
        return cmd_scaffold(root, args.capability, args.covers)
    if args.command == "recover":
        return cmd_recover(root)
    if args.command == "check":
        if args.mode == "ci" and not args.base:
            raise CapError("--mode ci requires --base")
        if args.combined and args.mode != "ci":
            raise CapError("--combined requires --mode ci")
        return Check(root, args.mode, args.base, args.report, args.combined).run([root / change for change in args.change])
    if args.command == "delta-block":
        return cmd_delta_block(root, args.implement)
    if args.command == "index":
        return cmd_index(root, args.rebuild)
    if args.command == "publish-design":
        if not args.change:
            raise CapError("publish-design requires --change, the design record")
        return cmd_publish_design(root, root / args.change[0])
    change = resolve_change(root, args.change)
    if args.command == "rebase":
        return cmd_rebase(root, change, args.onto, args.adopt, args.keep, args.drop, args.reason)
    if args.command == "defer":
        return cmd_defer(root, change, args.ids, args.onto, args.reason)
    if args.command == "ensure":
        return cmd_ensure(root, change)
    if args.command == "review":
        return cmd_review(root, change, args.accept)
    if args.command == "prepare":
        return cmd_prepare(root, change, args.no_tasks)
    if not args.staged:
        raise CapError("apply requires --staged, the directory prepare reported")
    return cmd_apply(root, change, args.staged, args.no_tasks)


def run_graph(args):
    """The graph has its own door. check and the fold subcommands do not use it: the fold command runs it."""
    gate = Path(__file__).resolve().with_name("cap_graph.py")
    return subprocess.run([sys.executable, "-I", "-S", str(gate), *args], check=False).returncode


def main():
    if sys.argv[1:2] == ["graph"]:
        return run_graph(sys.argv[2:])
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # Intermixed, so the rule ids of defer may come after the options: defer --change specs/001-x R-a R-b.
    args = build_parser().parse_intermixed_args()
    root = Path(args.root).resolve()
    try:
        return dispatch(args, root)
    except CapError as error:
        return emit({"status": "invalid", "errors": [str(error)]}, INVALID)
    except Busy:
        return emit({"status": "busy", "reason": "another process is publishing; try again when it finishes"}, BUSY)


if __name__ == "__main__":
    sys.exit(main())
