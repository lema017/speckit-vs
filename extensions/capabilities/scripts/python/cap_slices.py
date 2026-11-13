#!/usr/bin/env python3
"""The slices of the project: what each spec builds, in what order, and what is still to build.

A slice is one thing a person can do and check from end to end, and one spec builds one slice.
The maps live in ``specs/_slices/<name>.md``, and a spec names its slice in its ``## Slice``
section. A map says what a slice is made of, never how far it is: the state is read from the
specs, their tasks and the catalog, so it cannot go stale.

``capabilities.py slices`` loads this file and passes itself in, so the catalog, the delta and the
config are read with that script's parsers and not with copies of them. Standard library only and
Python 3.9+.

Exit codes, as in capabilities.py: 0 done, 1 ``check`` found a failure, 2 invalid input, and
3 when ``show`` needs a decision: the slice already has a spec, or it waits for another slice.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

MAPS = "specs/_slices"
MAP_FORMAT = 1
MAP_MARK = "<!-- slice-map:v%d -->" % MAP_FORMAT
MAP_LINE = re.compile(r"<!-- slice-map:v(\d+) -->")
SLICE_ID = re.compile(r"D-[a-z0-9]+(?:-[a-z0-9]+)*")
RULE_ID = re.compile(r"R-[a-z0-9-]+")
FIELD = re.compile(r"^- ([A-Za-z-]+): (.*)$")
LATER = re.compile(r"^- (R-[a-z0-9-]+): (.+)$")
ENABLER = re.compile(r"^enabler\s*[-—:]\s*(\S.*)$")
STANDALONE = re.compile(r"^standalone\s*[-—:]\s*(\S.*)$")
REQUIRED = ("intent", "verify", "depends-on", "rules")
OPTIONAL = ("in", "out", "kind", "dropped")
NOTHING = {"none", "-", "—"}


def strip_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def listed(value, pattern):
    """``none`` or ids separated by commas: (the ids, the parts that are not ids)."""
    if value.lower() in NOTHING:
        return [], []
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return [part for part in parts if pattern.fullmatch(part)], [part for part in parts if not pattern.fullmatch(part)]


def parse_map(cap, text):
    """A map as it is written. These errors are about its shape; what it names is checked against the project in problems()."""
    out = {"request": "", "slices": [], "later": [], "errors": []}
    errors = out["errors"]
    if cap.has_conflict(text):
        errors.append("merge conflict markers: resolve them by hand, a map is plain text")
        return out
    versions = [int(number) for number in MAP_LINE.findall(text)]
    if not versions:
        errors.append("not a slice map, the marker is missing: %s" % MAP_MARK)
        return out
    if max(versions) > MAP_FORMAT:
        errors.append("uses slice map format %d and this script reads up to %d: update with specify upgrade" % (max(versions), MAP_FORMAT))
        return out
    current, later = None, False
    for line in strip_comments(text).splitlines():
        if line.startswith("### "):
            slice_id, _, title = line[4:].strip().partition(" ")
            current, later = None, False
            if not SLICE_ID.fullmatch(slice_id):
                errors.append("heading is not a slice, a slice is `### D-<name> <title>`: %s" % line.strip())
                continue
            current = {"id": slice_id, "title": title.strip(), "fields": {}}
            out["slices"].append(current)
            continue
        if line.startswith("## "):
            current, later = None, line[3:].strip() == "Later"
            continue
        if later:
            match = LATER.match(line)
            if match:
                out["later"].append({"rule": match.group(1), "reason": cap.norm(match.group(2))})
            elif line.strip():
                errors.append("line in ## Later is not `- R-<id>: <reason>`: %s" % line.strip())
            continue
        if current is None:
            match = re.match(r"^Request: (.*)$", line)
            if match:
                out["request"] = cap.norm(match.group(1))
            continue
        match = FIELD.match(line)
        if not match:
            if line.strip():
                errors.append("%s: unexpected line, a field takes one line: %s" % (current["id"], line.strip()))
            continue
        key = match.group(1).lower()
        if key not in REQUIRED + OPTIONAL:
            errors.append("%s: unknown field %s" % (current["id"], match.group(1)))
        elif key in current["fields"]:
            errors.append("%s: field %s appears twice" % (current["id"], match.group(1)))
        else:
            current["fields"][key] = cap.norm(match.group(2))
    out["slices"] = [shaped(item, errors) for item in out["slices"]]
    return out


def shaped(item, errors):
    """One slice with its fields read. A slice says in ``Verify`` what a person does to check it: a layer has no such sentence."""
    slice_id, fields = item["id"], item["fields"]
    if not item["title"]:
        errors.append("%s: the heading has no title" % slice_id)
    for key in REQUIRED:
        if not fields.get(key):
            errors.append("%s: field %s is missing" % (slice_id, "-".join(part.capitalize() for part in key.split("-"))))
    depends, wrong = listed(fields.get("depends-on", "none"), SLICE_ID)
    errors.extend("%s: Depends-On takes slice ids or none: %s" % (slice_id, part) for part in wrong)
    rules, wrong = listed(fields.get("rules", "none"), RULE_ID)
    errors.extend("%s: Rules takes rule ids or none: %s" % (slice_id, part) for part in wrong)
    enabler = None
    if "kind" in fields:
        match = ENABLER.match(fields["kind"])
        if match:
            enabler = match.group(1)
        else:
            errors.append("%s: Kind takes `enabler — <why nothing smaller can be checked by a person>`" % slice_id)
    if "dropped" in fields and not fields["dropped"]:
        errors.append("%s: Dropped takes the reason" % slice_id)
    return {
        "id": slice_id,
        "title": item["title"],
        "intent": fields.get("intent", ""),
        "in": fields.get("in", ""),
        "out": fields.get("out", ""),
        "verify": fields.get("verify", ""),
        "depends_on": depends,
        "rules": rules,
        "enabler": enabler,
        "dropped": fields.get("dropped") or None,
    }


def parse_declaration(cap, text):
    """What a spec says about its slice: (declaration, errors). No declaration is a spec from before slices existed."""
    raw = cap.section(strip_comments(text), "Slice")
    if raw is None:
        return None, []
    fields = {}
    for line in raw.splitlines()[1:]:
        match = FIELD.match(line)
        if match:
            fields.setdefault(match.group(1).lower(), cap.norm(match.group(2)))
    value = fields.get("slice")
    declared = {"slice": None, "standalone": None, "out": fields.get("out", "")}
    if not value:
        return declared, ["## Slice names no slice: write `- Slice: <id>` or `- Slice: standalone — <what a person can do and check>`"]
    if value.startswith("["):
        return declared, ["## Slice still holds the placeholder of the template"]
    match = STANDALONE.match(value)
    if match:
        declared["standalone"] = match.group(1)
    elif SLICE_ID.fullmatch(value):
        declared["slice"] = value
    else:
        return declared, ["Slice takes a slice id or `standalone — <what a person can do and check>`: %s" % value]
    return declared, []


class Project:
    """The maps, the specs that name a slice and the rules of the catalog, read once."""

    def __init__(self, cap, root):
        self.cap, self.root = cap, root
        self.config = cap.load_config(root)
        self.maps = self.load_maps()
        self.rules, self.retired = self.load_rules()
        self.specs = self.load_specs()
        self.by_id = {}
        for found in self.maps:
            for item in found["slices"]:
                self.by_id.setdefault(item["id"], (found, item))
        self.claims = {}
        for spec in self.specs:
            if spec["slice"]:
                self.claims.setdefault(spec["slice"], []).append(spec)
        self.owner = {}
        for found in self.maps:
            for item in found["slices"]:
                if not item["dropped"]:
                    for rule_id in item["rules"]:
                        self.owner.setdefault(rule_id, []).append(item["id"])

    def load_maps(self):
        directory = self.root / MAPS
        maps = []
        for path in sorted(directory.glob("*.md")) if directory.is_dir() else []:
            if path.is_file():
                maps.append(dict(parse_map(self.cap, self.cap.read(path) or ""), map="%s/%s" % (MAPS, path.name), name=path.stem))
        return maps

    def load_rules(self):
        cap, rules, retired = self.cap, {}, set()
        catalog = self.root / cap.CATALOG
        for spec in sorted(catalog.glob("*/spec.md")) if catalog.is_dir() else []:
            for rule_id, rule in cap.rules_of(cap.read(spec)).items():
                rules.setdefault(rule_id, dict(rule, capability=spec.parent.name))
            retired.update(cap.retired_of(cap.read(spec.with_name("history.md"))))
        return rules, retired

    def load_specs(self):
        """Every spec under the feature roots that has a ``## Slice`` section or builds a designed rule."""
        cap, found = self.cap, {}
        for pattern in self.config["feature_roots"]:
            for base in sorted(self.root.glob(pattern)):
                for path in sorted(base.rglob("spec.md")) if base.is_dir() else []:
                    source = cap.source_of(self.root, path.parent)
                    if source.startswith((cap.CATALOG + "/", MAPS + "/")) or any(part.startswith(".") for part in source.split("/")):
                        continue
                    found[source] = path
        specs = []
        for source, path in sorted(found.items()):
            text = cap.read(path) or ""
            declared, errors = parse_declaration(cap, text)
            delta = cap.parse_delta(text, source)[0]
            entries = delta["entries"] if delta else []
            built = sorted(entry["id"] for entry in entries if entry["op"] == "IMPLEMENTED")
            if declared is None and not built:
                continue
            specs.append(dict(
                declared or {"slice": None, "standalone": None, "out": ""},
                spec=source,
                declared=declared is not None,
                errors=errors,
                built=built,
                changes=sorted(entry["id"] for entry in entries),
                state=self.spec_state(path.parent, source, entries),
            ))
        return specs

    def spec_state(self, change, source, entries):
        """How far a spec is. Delivered needs the tasks closed and, when the spec changes rules, its delta folded into the catalog."""
        cap = self.cap
        tasks = cap.open_tasks(change)
        names = sorted({entry["capability"] for entry in entries if entry.get("capability")})
        histories = [cap.read(self.root / cap.cap_rel(name, "history.md")) for name in names]
        folded = cap.was_folded(change, cap.load_lock(change), histories, source)
        if tasks is None:
            return "delivered" if folded else "specified"
        if tasks == 0 and (folded or not entries):
            return "delivered"
        return "building"

    def state(self, item):
        if item["dropped"]:
            return "dropped"
        claims = self.claims.get(item["id"])
        return claims[0]["state"] if claims else "pending"

    def view(self, item):
        """A slice with what is read from the project: its state, its spec, and what it waits for."""
        state = self.state(item)
        claims = self.claims.get(item["id"]) or []
        waiting = [dep for dep in item["depends_on"] if dep not in self.by_id or self.state(self.by_id[dep][1]) != "delivered"]
        issues = []
        if claims:
            for rule_id in item["rules"]:
                rule = self.rules.get(rule_id)
                if rule and rule["designed"] and rule_id not in claims[0]["changes"]:
                    issues.append("%s is still [designed] and %s does not build it" % (rule_id, claims[0]["spec"]))
        return dict(item, state=state, spec=claims[0]["spec"] if claims else None, waiting_for=waiting, ready=state == "pending" and not waiting, issues=issues)

    def unassigned(self, capabilities=None):
        """The [designed] rules no slice builds and no map leaves for later."""
        later = {entry["rule"] for found in self.maps for entry in found["later"]}
        return sorted(
            rule_id for rule_id, rule in self.rules.items()
            if rule["designed"] and rule_id not in self.owner and rule_id not in later and (capabilities is None or rule["capability"] in capabilities)
        )


def problems(project):
    """(hard, notes). Hard is what makes the maps and the specs disagree; a note is something a person should look at."""
    hard, notes, seen = [], [], {}
    for found in project.maps:
        hard.extend("%s: %s" % (found["map"], error) for error in found["errors"])
        earlier = set()
        for item in found["slices"]:
            slice_id = item["id"]
            if slice_id in seen:
                hard.append("%s: slice id %s is already used in %s; an id is never reused" % (found["map"], slice_id, seen[slice_id]))
                continue
            seen[slice_id] = found["map"]
            for dep in item["depends_on"]:
                if dep == slice_id:
                    hard.append("%s: %s depends on itself" % (found["map"], slice_id))
                elif dep not in project.by_id:
                    hard.append("%s: %s depends on %s, which no map defines" % (found["map"], slice_id, dep))
                elif project.by_id[dep][1]["dropped"] and not item["dropped"]:
                    hard.append("%s: %s depends on %s, which was dropped" % (found["map"], slice_id, dep))
                elif project.by_id[dep][0] is found and dep not in earlier:
                    hard.append("%s: %s depends on %s, which comes later in the map; a slice depends only on slices above it" % (found["map"], slice_id, dep))
            earlier.add(slice_id)
            if item["dropped"]:
                continue
            for rule_id in item["rules"]:
                if rule_id not in project.rules and rule_id not in project.retired:
                    hard.append("%s: %s names %s, which is not in the catalog" % (found["map"], slice_id, rule_id))
            if item["enabler"]:
                notes.append("%s: %s is an enabler, nothing a person can check on its own: %s" % (found["map"], slice_id, item["enabler"]))
        for entry in found["later"]:
            if entry["rule"] not in project.rules and entry["rule"] not in project.retired:
                hard.append("%s: ## Later names %s, which is not in the catalog" % (found["map"], entry["rule"]))
            if entry["rule"] in project.owner:
                hard.append("%s: %s is in ## Later and in %s" % (found["map"], entry["rule"], ", ".join(project.owner[entry["rule"]])))
    for rule_id, owners in sorted(project.owner.items()):
        if len(owners) > 1:
            hard.append("%s is in several slices: %s; a rule is built by one slice" % (rule_id, ", ".join(owners)))
    hard.extend(cycles(project))
    for spec in project.specs:
        hard.extend("%s: %s" % (spec["spec"], error) for error in spec["errors"])
        named = spec["slice"]
        if named and named not in project.by_id:
            hard.append("%s: names slice %s, which no map defines" % (spec["spec"], named))
        elif named and project.by_id[named][1]["dropped"]:
            hard.append("%s: names slice %s, which was dropped" % (spec["spec"], named))
        for rule_id in spec["built"]:
            owners = project.owner.get(rule_id) or []
            if owners and named not in owners:
                hard.append("%s: builds %s, which belongs to %s; name that slice in ## Slice or move the rule in the map" % (spec["spec"], rule_id, owners[0]))
    for slice_id, claims in sorted(project.claims.items()):
        if len(claims) > 1:
            hard.append("%s is named by several specs: %s; one spec builds one slice" % (slice_id, ", ".join(spec["spec"] for spec in claims)))
    for found in project.maps:
        for item in found["slices"]:
            if not item["dropped"]:
                notes.extend("%s: %s: %s; move the rule to another slice or to ## Later" % (found["map"], item["id"], issue) for issue in project.view(item)["issues"])
    touched = {project.rules[rule_id]["capability"] for rule_id in project.owner if rule_id in project.rules}
    for rule_id in project.unassigned(touched):
        notes.append("%s is [designed] and in no slice and not in ## Later" % rule_id)
    return hard, notes


def cycles(project):
    """A slice that reaches itself through its dependencies. Inside one map the order already forbids it; across maps nothing else does."""
    found, visited = [], {}

    def walk(slice_id, path):
        visited[slice_id] = "open"
        for dep in project.by_id[slice_id][1]["depends_on"]:
            if dep == slice_id or dep not in project.by_id:
                continue
            if visited.get(dep) == "open":
                found.append("dependency cycle: %s" % " > ".join(path[path.index(dep):] + [dep]))
            elif dep not in visited:
                walk(dep, path + [dep])
        visited[slice_id] = "done"

    for slice_id in sorted(project.by_id):
        if slice_id not in visited:
            walk(slice_id, [slice_id])
    return found


def implemented_blocks(cap, project, rule_ids):
    """The IMPLEMENTED blocks of the [designed] rules among ``rule_ids``, as delta-block prints them."""
    ids = [rule_id for rule_id in rule_ids if rule_id in project.rules and project.rules[rule_id]["designed"]]
    blocks = [cap.implemented_block(rule_id, project.rules[rule_id]["capability"], project.rules[rule_id]["text"]) for rule_id in ids]
    return {"ids": ids, "text": "\n\n".join(blocks) + "\n" if blocks else ""}


def cmd_status(cap, project, wanted):
    maps = project.maps
    if wanted:
        maps = [found for found in maps if wanted in (found["name"], found["map"])]
        if not maps:
            raise cap.CapError("slice map not found: %s" % wanted)
    out = []
    for found in maps:
        views = [project.view(item) for item in found["slices"]]
        ready = [view["id"] for view in views if view["ready"]]
        out.append({"map": found["map"], "name": found["name"], "request": found["request"], "slices": views, "later": found["later"], "next": ready[0] if ready else None, "errors": found["errors"]})
    hard, notes = problems(project)
    return cap.emit({
        "maps": out,
        "standalone": [{"spec": spec["spec"], "outcome": spec["standalone"], "state": spec["state"]} for spec in project.specs if spec["standalone"]],
        "unassigned_designed": project.unassigned(),
        "check": {"hard": len(hard), "notes": len(notes)},
    })


def aim(view, siblings, depends, rules, write):
    """What a run aimed at one slice builds and what it leaves to the others. The script writes it, so it reads the same whoever relays it."""
    lines = ["SLICE FOR THIS RUN", "%s — %s" % (view["id"], view["title"]), "Build exactly this: %s" % view["intent"]]
    if view["in"]:
        lines.append("In: %s" % view["in"])
    lines += [
        "A person checks it by: %s" % view["verify"],
        "Other slices own this, so do not specify it, ask about it or build it: %s" % siblings,
        "Depends on: %s" % (", ".join("%s (%s)" % (dep["id"], dep["state"]) for dep in depends) or "none"),
        "Rules to build:" + ("".join("\n- %s: %s" % (rule["id"], rule["text"]) for rule in rules) or " none"),
        "",
        "Write under ## Slice in the spec:",
        write.rstrip("\n"),
    ]
    return "\n".join(lines) + "\n"


def cmd_show(cap, project, slice_id):
    if slice_id not in project.by_id:
        raise cap.CapError("slice not found: %s" % slice_id)
    found, item = project.by_id[slice_id]
    if item["dropped"]:
        raise cap.CapError("slice %s was dropped: %s" % (slice_id, item["dropped"]))
    view = project.view(item)
    siblings = [project.view(other) for other in found["slices"] if other["id"] != slice_id and not other["dropped"]]
    out = "; ".join("%s (%s)" % (other["title"], other["id"]) for other in siblings) or "none"
    status = "has-spec" if view["spec"] else "blocked" if view["waiting_for"] else "ok"
    depends = [{"id": dep, "state": project.state(project.by_id[dep][1]) if dep in project.by_id else "unknown"} for dep in item["depends_on"]]
    rules = [dict(project.rules[rule_id], id=rule_id) for rule_id in item["rules"] if rule_id in project.rules]
    write = "- Slice: %s\n- Out: %s\n" % (slice_id, out)
    return cap.emit({
        "status": status,
        "map": found["map"],
        "request": found["request"],
        "slice": view,
        "siblings": [{"id": other["id"], "title": other["title"], "intent": other["intent"], "state": other["state"]} for other in siblings],
        "depends_on": depends,
        "rules": rules,
        "implement": implemented_blocks(cap, project, item["rules"]),
        "write": write,
        "aim": aim(view, out, depends, rules, write),
    }, cap.OK if status == "ok" else cap.DECISION)


def cmd_check(cap, project):
    hard, notes = problems(project)
    return cap.emit({"status": "invalid" if hard else "ok", "hard": hard, "notes": notes, "maps": [found["map"] for found in project.maps]}, cap.HARD if hard else cap.OK)


def report(cap, root):
    """What ``capabilities.py check`` adds to its own report."""
    return problems(Project(cap, root))


def build_parser():
    parser = argparse.ArgumentParser(prog="capabilities.py slices", description="The slices of the project")
    parser.add_argument("command", choices=["status", "show", "check"])
    parser.add_argument("ids", nargs="*", help="show: the slice")
    parser.add_argument("--root", default=".")
    parser.add_argument("--map", help="status: one map, by name or by path")
    return parser


def main(cap, argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        parser.error("--root is not a directory")
    if args.command == "show" and len(args.ids) != 1:
        parser.error("show takes one slice id")
    if args.command != "show" and args.ids:
        parser.error("%s takes no ids" % args.command)
    if args.map is not None and args.command != "status":
        parser.error("--map goes with status")
    try:
        problem = cap.format_error(cap.read(root / cap.INDEX))
        if problem:
            raise cap.CapError(problem)
        project = Project(cap, root)
        if args.command == "status":
            return cmd_status(cap, project, args.map)
        if args.command == "show":
            return cmd_show(cap, project, args.ids[0])
        return cmd_check(cap, project)
    except cap.CapError as error:
        return cap.emit({"status": "invalid", "errors": [str(error)]}, cap.INVALID)
