#!/usr/bin/env python3
"""Product Studio: the design of a product, kept as files, and the mockup built from them.

    studio.py scaffold --name NAME [--owner WHO] [--language es] [--device phone]
    studio.py status
    studio.py check
    studio.py build
    studio.py directions            the page that shows the looks of directions.md side by side
    studio.py pick LETTER           make one direction the look of the product
    studio.py open [--page directions] [--no-browser] [--stop]
    studio.py shots [--area AREA] [--page directions] [--states]
    studio.py comments [--all]                              what the person said on the mockup
    studio.py comments add                                  keep the comments the mockup copied, read from stdin
    studio.py comments resolve C-1 [C-2 ...] --as applied|declined|open [--note WHY]
    studio.py approve AREA [--by WHO] [--dry-run]           publish the draft rules of an area as approved
    studio.py serve [--port N] [--idle SECONDS]             serve the mockup to this machine and keep its comments

Everything a person decides in the design conversation is a Markdown file under specs/_product/.
This script decides nothing. It reads those files, says whether they agree with each other and with
the pages of the mockup, and writes the files of the mockup that nobody edits by hand.

Standard library only, and it runs on Python 3.9. The answer is JSON on stdout.
Exit codes: 0 fine, 1 the check found something to fix, 2 the call or a file cannot be used,
3 there is nothing to show yet, or no browser to show it with.
"""

import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

OK, HARD, INVALID, WAIT = 0, 1, 2, 3
PRODUCT = "specs/_product"
CATALOG = "specs/_capabilities"
FORMAT = 1
MARK = re.compile(r"<!-- studio-product:v(\d+) -->")
GENERATED = ("mockup/_studio/", "mockup/index.html", "mockup/_shots/")
KIT_FILES = ("kit.css", "runtime.js")
DIRECTIONS_PAGE = "directions.html"
DATA_PLACEHOLDER = "/*DATA*/null"
# Where a product is used most, and the size of the window its pictures are taken in. A browser window is never
# narrower than about 500 px, so the picture of a phone is the phone frame of the mockup in a window that holds it.
DEVICES = {"desktop": (1280, 800), "phone": (500, 1000)}
# Either one set to anything but 0 or false: this script opens no browser.
NO_BROWSER_ENV = ("SPECKIT_STUDIO_NO_BROWSER", "SPECKIT_PROGRESS_NO_BROWSER")
# Set to anything but 0 or false: `open` starts no server, and opens the mockup from the disk.
NO_SERVER_ENV = "SPECKIT_STUDIO_NO_SERVER"
BROWSER_ENV = "SPECKIT_STUDIO_BROWSER"
SHOT_SECONDS = 60
# Wide and tall enough for three looks side by side, each with its two sample screens.
DIRECTIONS_SIZE = (1440, 1560)
# What the person can open and read, in the order the design is made.
DOCUMENTS = ("vision.md", "actors.md", "navigation.md", "story-map.md", "capability-drafts.md", "decisions.md", "look-and-feel.md", "comments.md")
COMMENTS = "comments.md"
# What became of a comment: it waits, it was applied, it was not (its note says why), or the person took it back.
COMMENT_STATES = ("open", "applied", "declined", "withdrawn")
# A comment is what a person typed in a page: each part is cut to what its field takes before it is kept.
COMMENT_FIELD, COMMENT_TEXT, COMMENT_BODY = 200, 2000, 16 * 1024
# Where the catalog keeps a design record, and the script that publishes one.
CHANGES = CATALOG + "/_changes"
RECORD = "capability-delta.md"
CAPABILITIES_SCRIPT = ".specify/extensions/capabilities/scripts/python/capabilities.py"
# The server of the mockup: the header a page of its own sends, how long it waits for a request before it stops,
# and the ports it tries first. A project gets the same port every time, so its link stays the same.
SESSION_HEADER = "X-Studio-Session"
SERVER_IDLE = 6 * 60 * 60
SERVER_PORTS = (47000, 1000)
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml",
         ".webp": "image/webp", ".ico": "image/x-icon", ".woff2": "font/woff2"}

ACTOR = r"ACT-[a-z0-9]+(?:-[a-z0-9]+)*"
STORY = r"ST-[0-9]+"
SCREEN = r"SCR-[a-z0-9]+(?:-[a-z0-9]+)*"
FLOW = r"FL-[0-9]+"
RULE = r"R-[a-z0-9]+(?:-[a-z0-9]+)*"
SLUG = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
QUESTION = r"Q-[0-9]+"
REMARK = r"C-[0-9]+"
LETTER = r"[A-Z]"
FONT = r"[A-Za-z0-9 ,'\"_-]{1,120}"
PAGE = r"[a-z0-9][a-z0-9-]*\.html"
HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\Z")

HEADING = re.compile(r"^(#{1,3}) (.+?)\s*$")
FIELD = re.compile(r"^- ([A-Za-z][A-Za-z-]*): ?(.*?)\s*$")
ELEMENT = re.compile(r'^- ([a-z][a-z-]*) "(.+?)"(?: -> (%s)(?:/(%s))?)?(?:: (.+))?$' % (SCREEN, SLUG))
COMMENT = re.compile(r"<!--.*?-->", re.S)
EXAMPLE = re.compile(r"^- (%s): (.+?)\s*$" % RULE)
PASTED = re.compile(r"^C-[0-9]+: (%s)(?:\s|$)" % SCREEN)
APPROVED_BY = re.compile(r"^Approved by: (.+) on (\d{4}-\d{2}-\d{2})\s*$")
CATALOG_RULE = re.compile(r"^- \*\*(%s)\*\*( \[designed\])?: (.*?)(?: \([^()]*\))?\s*$" % RULE, re.M)
NOTHING = ("none", "-")
# The kinds of element a person presses or fills in: the page shows each one under the label its screen gives it.
NAMED = ("button", "link", "field", "tab")

TOKENS = ("bg", "surface", "text", "muted", "border", "field-border", "primary", "primary-hover", "on-primary",
          "link", "danger", "danger-bg", "success", "success-bg", "ring")
# What has to be readable on what, and how much: text needs 4.5, the edge of a control and the focus ring need 3.
CONTRAST = (("text", "bg", 4.5), ("text", "surface", 4.5), ("muted", "bg", 4.5), ("muted", "surface", 4.5), ("link", "bg", 4.5),
            ("link", "surface", 4.5), ("on-primary", "primary", 4.5), ("danger", "danger-bg", 4.5), ("success", "success-bg", 4.5),
            ("field-border", "surface", 3.0), ("ring", "bg", 3.0), ("ring", "surface", 3.0))
SYSTEM_FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
SHADOW = {"Light": "0 1px 2px rgb(16 24 40 / 6%), 0 12px 32px rgb(16 24 40 / 8%)", "Dark": "none"}


class StudioError(Exception):
    """The call cannot go on: a file that is not there, or one written in a format this script does not read."""


class NothingYet(StudioError):
    """There is nothing to show yet, or nothing to show it with. Not a mistake of anyone."""


def emit(data, code=OK):
    sys.stdout.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")
    return code


def read(path):
    try:
        return path.read_text(encoding="utf-8") if path.is_file() and not path.is_symlink() else None
    except (OSError, UnicodeDecodeError):
        return None


def write(path, text):
    """Writes the whole file or nothing, and never through a link."""
    if path.is_symlink():
        raise StudioError("%s is a link: studio does not write through links" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(path.name + ".tmp")
    scratch.write_text(text, encoding="utf-8")
    os.replace(str(scratch), str(path))


def listed(value, pattern):
    """The ids of a `- Key: a, b` line, and what in it is not an id. `none` is an empty list."""
    value = (value or "").strip()
    if not value or value.split(" ")[0].lower() in NOTHING:
        return [], []
    parts = [part.strip() for part in value.split(",") if part.strip()]
    good = [part for part in parts if re.fullmatch(pattern, part)]
    return good, [part for part in parts if part not in good]


# --------------------------------------------------------------------------- reading the Markdown of the product

def outline(text):
    """The headings of a document, in order, each with what sits right under it: its `- Key: value` lines and its other lines.
    A comment keeps its line breaks, so the line numbers are the ones of the file."""
    items, current, fenced = [], None, False
    text = COMMENT.sub(lambda found: "\n" * found.group(0).count("\n"), text)
    for number, raw in enumerate(text.splitlines(), 1):
        if raw.lstrip().startswith("```"):
            fenced = not fenced
        heading = None if fenced else HEADING.match(raw)
        if heading:
            current = {"level": len(heading.group(1)), "title": heading.group(2), "line": number, "fields": {}, "twice": [], "lines": []}
            items.append(current)
        elif current is not None and raw.strip():
            field = None if fenced else FIELD.match(raw)
            if field:
                key = field.group(1)
                if key in current["fields"]:
                    current["twice"].append(key)
                current["fields"][key] = field.group(2)
            else:
                current["lines"].append((number, raw.rstrip()))
    return items


def under(items, index):
    """The headings below one heading: every deeper heading up to the next one of its level or above."""
    level, found = items[index]["level"], []
    for item in items[index + 1:]:
        if item["level"] <= level:
            break
        found.append(item)
    return found


def first_paragraph(text, limit=600):
    """The first lines of running text of a document: what it says before its first blank line, headings aside."""
    found = []
    for line in COMMENT.sub("", text).splitlines():
        line = line.strip()
        if line.startswith("#") or (not line and not found):
            continue
        if not line:
            break
        found.append(line)
    return " ".join(found)[:limit]


def count(number, noun):
    return "%d %s%s" % (number, noun, "" if number == 1 else "s")


def one_line(value, limit=COMMENT_FIELD):
    """What a person typed, as one line a field can hold: no line break, no control character, nothing that opens
    a comment of Markdown, and no longer than the field takes."""
    text = "".join(char for char in " ".join(str(value if value is not None else "").split()) if char.isprintable())
    return text.replace("<!--", "<! --")[:limit].strip()


def many_lines(value, limit=COMMENT_TEXT):
    """What a person typed, line by line, without the empty lines around it."""
    lines = [one_line(line, limit) for line in str(value if value is not None else "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip("\n")[:limit].rstrip()


def quoted(item):
    """The lines a block quotes with `> `: what a comment says."""
    lines = [line.strip()[1:] for _, line in item["lines"] if line.strip().startswith(">")]
    return "\n".join(line[1:] if line.startswith(" ") else line for line in lines).strip("\n")


def split_title(title, pattern):
    """`ID The rest` -> (id, the rest), or (None, title) when it does not start with an id of that kind."""
    head, _, rest = title.partition(" ")
    return (head, rest.strip()) if re.fullmatch(pattern, head) else (None, title)


class Product:
    """What specs/_product/ says, with every problem found while reading it."""

    def __init__(self, root):
        self.root, self.dir = root, root / PRODUCT
        self.hard, self.notes = [], []
        self.name = self.owner = None
        self.language = "en"
        self.device = "desktop"
        self.vision = False
        self.idea = ""
        self.actors, self.areas, self.flows, self.stories, self.screens = {}, {}, {}, {}, {}
        self.capabilities, self.rules, self.questions = {}, {}, []
        self.comments = []
        self.theme = None
        self.directions, self.sample = {}, {}
        self.exists = read(self.dir / "product.md") is not None
        if self.exists:
            self.load()

    # -- helpers

    def rel(self, name, line=None):
        return "%s/%s%s" % (PRODUCT, name, ":%d" % line if line else "")

    def bad(self, name, line, message):
        self.hard.append("%s: %s" % (self.rel(name, line), message))

    def fields(self, name, item, required, optional=()):
        """The fields of a block, checked against what that kind of block takes."""
        for key in item["twice"]:
            self.bad(name, item["line"], "%s is written twice" % key)
        for key in item["fields"]:
            if key not in required and key not in optional:
                self.bad(name, item["line"], "%s is not a field here; the fields are %s" % (key, ", ".join(required + tuple(optional))))
        for key in required:
            if not item["fields"].get(key, "").strip():
                self.bad(name, item["line"], "%s is missing" % key)
        return item["fields"]

    def ids(self, name, item, key, pattern):
        good, wrong = listed(item["fields"].get(key), pattern)
        for part in wrong:
            self.bad(name, item["line"], "%s: %s is not written as an id" % (key, part))
        return good

    def keep(self, store, key, value, name, line, what):
        if key in store:
            self.bad(name, line, "%s %s is defined twice" % (what, key))
        else:
            store[key] = value

    # -- the files

    def load(self):
        self.load_product()
        vision = (read(self.dir / "vision.md") or "").strip()
        self.vision = bool(vision)
        self.idea = first_paragraph(vision)
        self.load_actors()
        self.load_navigation()
        self.load_stories()
        self.load_screens()
        self.load_drafts()
        self.load_decisions()
        self.load_comments()
        self.load_theme()
        self.load_directions()

    def load_product(self):
        text = read(self.dir / "product.md")
        mark = MARK.search(text)
        if not mark:
            raise StudioError("%s has no <!-- studio-product:v%d --> line: `scaffold` writes it" % (self.rel("product.md"), FORMAT))
        if int(mark.group(1)) > FORMAT:
            raise StudioError("%s is in a newer format than this script reads: update with `specify upgrade`" % self.rel("product.md"))
        items = outline(text)
        if not items or items[0]["level"] != 1 or not items[0]["title"].startswith("Product:") or not items[0]["title"][8:].strip():
            self.bad("product.md", 1, "the first line is `# Product: <name>`")
            return
        self.name = items[0]["title"][8:].strip()
        fields = self.fields("product.md", items[0], (), ("Owner", "Language", "Device"))
        self.owner = fields.get("Owner") or None
        self.language = (fields.get("Language") or "en").strip().lower()
        self.device = (fields.get("Device") or "desktop").strip().lower()
        if self.device not in DEVICES:
            self.bad("product.md", items[0]["line"], "Device is %s" % " or ".join(sorted(DEVICES)))
            self.device = "desktop"

    def load_actors(self):
        for item in outline(read(self.dir / "actors.md") or ""):
            if item["level"] != 3:
                continue
            key, title = split_title(item["title"], ACTOR)
            if not key or not title:
                self.bad("actors.md", item["line"], "an actor is `### ACT-<name> <how the person is called>`")
                continue
            fields = self.fields("actors.md", item, ("Role", "About"), ("Email",))
            self.keep(self.actors, key, {"id": key, "name": title, "role": fields.get("Role", ""), "about": fields.get("About", ""),
                                         "email": fields.get("Email", "")}, "actors.md", item["line"], "actor")

    def load_navigation(self):
        items = outline(read(self.dir / "navigation.md") or "")
        for index, section in enumerate(items):
            if section["level"] != 2:
                continue
            for item in under(items, index):
                if section["title"] == "Areas":
                    key, title = split_title(item["title"], SLUG)
                    if not key or not title:
                        self.bad("navigation.md", item["line"], "an area is `### <name> <title>`, with a name in lowercase and hyphens")
                        continue
                    fields = self.fields("navigation.md", item, ("Covers",))
                    self.keep(self.areas, key, {"id": key, "title": title, "covers": fields.get("Covers", "")}, "navigation.md", item["line"], "area")
                elif section["title"] == "Flows":
                    key, title = split_title(item["title"], FLOW)
                    if not key or not title:
                        self.bad("navigation.md", item["line"], "a flow is `### FL-<number> <title>`")
                        continue
                    fields = self.fields("navigation.md", item, ("Steps",), ("Area",))
                    steps = []
                    for part in [part.strip() for part in fields.get("Steps", "").split(">") if part.strip()]:
                        step = re.fullmatch(r"(%s)(?:/(%s))?" % (SCREEN, SLUG), part)
                        if step:
                            steps.append([step.group(1), step.group(2) or "normal"])
                        else:
                            self.bad("navigation.md", item["line"], "Steps: %s is not `SCR-<name>` or `SCR-<name>/<state>`" % part)
                    self.keep(self.flows, key, {"id": key, "title": title, "area": fields.get("Area") or None, "steps": steps, "line": item["line"]},
                              "navigation.md", item["line"], "flow")

    def load_stories(self):
        for item in outline(read(self.dir / "story-map.md") or ""):
            if item["level"] != 3:
                continue
            key, title = split_title(item["title"], STORY)
            if not key or not title:
                self.bad("story-map.md", item["line"], "a story is `### ST-<number> <title>`")
                continue
            fields = self.fields("story-map.md", item, ("Area", "Actor", "Story", "Criteria"), ("Rules", "Interface"))
            self.keep(self.stories, key, {
                "id": key, "title": title, "area": fields.get("Area", "").strip(), "actors": self.ids("story-map.md", item, "Actor", ACTOR),
                "story": fields.get("Story", ""), "criteria": fields.get("Criteria", ""), "rules": self.ids("story-map.md", item, "Rules", RULE),
                "no_interface": fields.get("Interface", "").strip().lower().startswith("none"), "line": item["line"],
            }, "story-map.md", item["line"], "story")

    def load_screens(self):
        folder = self.dir / "screens"
        for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
            name = "screens/" + path.name
            items = outline(read(path) or "")
            key, title = split_title(items[0]["title"], SCREEN) if items and items[0]["level"] == 1 else (None, "")
            if not key or not title:
                self.bad(name, 1, "the first line is `# SCR-<name> <title>`")
                continue
            if path.name != key + ".md":
                self.bad(name, 1, "the file of %s is called %s.md" % (key, key))
            fields = self.fields(name, items[0], ("Area", "File", "States"), ("Layout", "Seen-By", "Session", "Stories", "Rules", "Entry"))
            states = [part.strip() for part in fields.get("States", "").split(",") if part.strip()]
            for state in states:
                if not re.fullmatch(SLUG, state):
                    self.bad(name, items[0]["line"], "States: %s is not a state name, in lowercase and hyphens" % state)
            if states and "normal" not in states:
                self.bad(name, items[0]["line"], "States must include normal")
            page = fields.get("File", "").strip()
            if page and not re.fullmatch(PAGE, page):
                self.bad(name, items[0]["line"], "File: %s is not a page name such as entrar.html" % page)
            session = (fields.get("Session") or "none").strip().lower()
            if session not in ("none", "required"):
                self.bad(name, items[0]["line"], "Session is none or required")
            seen = fields.get("Seen-By", "anyone").strip()
            sections = {item["title"]: item for item in items[1:] if item["level"] == 2}
            for wanted in ("Purpose", "Elements"):
                if wanted not in sections or not (sections[wanted]["lines"] or sections[wanted]["fields"]):
                    self.bad(name, items[0]["line"], "the section ## %s is missing or empty" % wanted)
            elements = []
            for number, line in sections.get("Elements", {"lines": []})["lines"]:
                found = ELEMENT.match(line.strip())
                if found:
                    elements.append({"kind": found.group(1), "label": found.group(2), "to": found.group(3), "state": found.group(4), "note": found.group(5), "line": number})
                else:
                    self.bad(name, number, 'an element is `- <kind> "<label>"`, with ` -> SCR-<name>` when it leads to a screen')
            described = sections.get("States", {"fields": {}})["fields"]
            for state in described:
                if state not in states:
                    self.bad(name, sections["States"]["line"], "## States describes %s, which is not in States" % state)
            self.keep(self.screens, key, {
                "id": key, "title": title, "area": fields.get("Area", "").strip(), "file": page, "layout": (fields.get("Layout") or "app").strip(),
                "session": session == "required", "states": states, "seen_by": [] if seen.lower() == "anyone" else self.ids(name, items[0], "Seen-By", ACTOR),
                "stories": self.ids(name, items[0], "Stories", STORY), "rules": self.ids(name, items[0], "Rules", RULE),
                "entry": fields.get("Entry", "").strip().lower() == "yes", "elements": elements, "described": sorted(described), "source": name,
            }, name, 1, "screen")

    def load_drafts(self):
        items = outline(read(self.dir / "capability-drafts.md") or "")
        for index, section in enumerate(items):
            if section["level"] != 2:
                continue
            if not re.fullmatch(SLUG, section["title"]):
                self.bad("capability-drafts.md", section["line"], "a capability is `## <name>`, in lowercase and hyphens")
                continue
            fields = self.fields("capability-drafts.md", section, ("Covers",))
            self.keep(self.capabilities, section["title"], {"id": section["title"], "covers": fields.get("Covers", ""), "rules": []},
                      "capability-drafts.md", section["line"], "capability")
            for item in under(items, index):
                key, _ = split_title(item["title"], RULE)
                if not key:
                    self.bad("capability-drafts.md", item["line"], "a rule is `### R-<name>`, in lowercase and hyphens")
                    continue
                fields = self.fields("capability-drafts.md", item, ("Text", "Example"), ("Owner",))
                self.keep(self.rules, key, {"id": key, "capability": section["title"], "text": fields.get("Text", ""), "example": fields.get("Example", ""),
                                            "line": item["line"]}, "capability-drafts.md", item["line"], "rule")
                self.capabilities[section["title"]]["rules"].append(key)

    def load_decisions(self):
        items = outline(read(self.dir / "decisions.md") or "")
        seen = set()
        for index, section in enumerate(items):
            if section["level"] != 2:
                continue
            scope = section["title"].strip()
            if scope != "define" and not re.fullmatch(r"map %s" % SLUG, scope):
                self.bad("decisions.md", section["line"], "a group of questions is `## define` or `## map <area>`")
                continue
            for item in under(items, index):
                key, text = split_title(item["title"], QUESTION)
                if not key or not text:
                    self.bad("decisions.md", item["line"], "a question is `### Q-<number> <the question>`")
                    continue
                fields = self.fields("decisions.md", item, ("Status",), ("Round", "Options", "Recommended", "Answer", "Owner", "Why", "Business"))
                status = fields.get("Status", "").strip().lower()
                if status not in ("asked", "decided", "open"):
                    self.bad("decisions.md", item["line"], "Status is asked, decided or open")
                if status == "decided" and not fields.get("Answer", "").strip():
                    self.bad("decisions.md", item["line"], "a decided question says its Answer")
                if status == "open" and not fields.get("Owner", "").strip():
                    self.bad("decisions.md", item["line"], "an open question says its Owner: who decides it")
                if key in seen:
                    self.bad("decisions.md", item["line"], "question %s is defined twice" % key)
                seen.add(key)
                self.questions.append({"id": key, "scope": scope, "question": text, "status": status, "answer": fields.get("Answer", ""),
                                       "owner": fields.get("Owner", ""), "business": fields.get("Business", "").strip().lower() == "yes"})

    def load_comments(self):
        """What the person said on the mockup: `## C-<number>`, where it was said, what became of it, and the words, quoted."""
        seen = set()
        for item in outline(read(self.dir / COMMENTS) or ""):
            if item["level"] != 2:
                continue
            key = item["title"].strip()
            if not re.fullmatch(REMARK, key):
                self.bad(COMMENTS, item["line"], "a comment is `## C-<number>`")
                continue
            fields = self.fields(COMMENTS, item, ("Screen", "Status"), ("State", "Person", "Element", "Path", "Refs", "Date", "Note"))
            status, text = fields.get("Status", "").strip().lower(), quoted(item)
            if status not in COMMENT_STATES:
                self.bad(COMMENTS, item["line"], "Status is %s" % ", ".join(COMMENT_STATES[:-1]) + " or " + COMMENT_STATES[-1])
            if not re.fullmatch(SCREEN, fields.get("Screen", "").strip()):
                self.bad(COMMENTS, item["line"], "Screen is the id of the screen the comment was made on, such as SCR-login")
            if not text:
                self.bad(COMMENTS, item["line"], "a comment says what to change, in lines that start with `> `")
            if status == "declined" and not fields.get("Note", "").strip():
                self.bad(COMMENTS, item["line"], "a declined comment says why in its Note")
            if key in seen:
                self.bad(COMMENTS, item["line"], "comment %s is defined twice" % key)
            seen.add(key)
            self.comments.append({
                "id": key, "screen": fields.get("Screen", "").strip(), "state": fields.get("State", "").strip() or "normal",
                "person": fields.get("Person", "").strip(), "element": fields.get("Element", "").strip(), "path": fields.get("Path", "").strip(),
                "refs": self.ids(COMMENTS, item, "Refs", "%s|%s" % (STORY, RULE)), "date": fields.get("Date", "").strip(),
                "status": status, "note": fields.get("Note", "").strip(), "text": text,
            })

    def look(self, name, head, modes):
        """One look: the font and the radii its heading gives, and the colors of its Light and Dark sections."""
        fields = head["fields"]
        theme = {"font": (fields.get("Font") or "system").strip(), "radius": (fields.get("Radius") or "12px").strip(),
                 "radius_control": (fields.get("Radius-Control") or "8px").strip(), "Light": {}, "Dark": {}}
        if not re.fullmatch(FONT, theme["font"]):
            self.bad(name, head["line"], "Font is `system` or the names of fonts, with commas between them")
            theme["font"] = "system"
        for key in ("radius", "radius_control"):
            if not re.fullmatch(r"[0-9]{1,3}px", theme[key]):
                self.bad(name, head["line"], "a radius is a number of px, such as 12px")
        complete = True
        for mode in ("Light", "Dark"):
            section = modes.get(mode)
            if section is None:
                self.bad(name, head["line"], "the section %s is missing" % mode)
                complete = False
                continue
            fields = self.fields(name, section, TOKENS)
            for token in TOKENS:
                value = fields.get(token, "").strip()
                if value and not HEX.match(value):
                    self.bad(name, section["line"], "%s: %s is not a color written as #rgb or #rrggbb" % (token, value))
                complete = complete and bool(HEX.match(value))
                theme[mode][token] = value
        theme["complete"] = complete
        return theme

    def load_theme(self):
        text = read(self.dir / "look-and-feel.md")
        if text is None:
            return
        items = outline(text)
        if not items or items[0]["level"] != 1:
            self.bad("look-and-feel.md", 1, "the first line is `# Look and feel`")
            return
        fields = self.fields("look-and-feel.md", items[0], ("Direction",), ("Font", "Radius", "Radius-Control"))
        self.theme = self.look("look-and-feel.md", items[0], {item["title"]: item for item in items[1:] if item["level"] == 2})
        self.theme["direction"] = fields.get("Direction", "")

    def load_directions(self):
        """The looks the person chooses from: `## <letter> <name>`, each with its `### Light` and `### Dark`."""
        items = outline(read(self.dir / "directions.md") or "")
        if items and items[0]["level"] == 1:
            # What the two sample screens say, in the words of the product. Without it they say something plain.
            fields = self.fields("directions.md", items[0], (), ("Sample-Title", "Sample-Items", "Sample-Action"))
            entries = [[part.strip() for part in entry.split("|", 1)] for entry in fields.get("Sample-Items", "").split(";") if entry.strip()]
            self.sample = {"titulo": fields.get("Sample-Title", ""), "accion": fields.get("Sample-Action", ""),
                           "entradas": [entry + [""] * (2 - len(entry)) for entry in entries]}
        for index, item in enumerate(items):
            if item["level"] != 2:
                continue
            key, title = split_title(item["title"], LETTER)
            if not key or not title:
                self.bad("directions.md", item["line"], "a direction is `## <letter> <name>`, such as `## A Warm and plain`")
                continue
            fields = self.fields("directions.md", item, ("Why",), ("Font", "Radius", "Radius-Control"))
            look = self.look("directions.md", item, {child["title"]: child for child in under(items, index) if child["level"] == 3})
            look.update({"id": key, "name": title, "why": fields.get("Why", ""), "line": item["line"]})
            self.keep(self.directions, key, look, "directions.md", item["line"], "direction")


# --------------------------------------------------------------------------- the catalog and the pages

def catalog_rules(root):
    """The rules the catalog of capabilities already has: id -> (capability, text, designed or implemented)."""
    found, base = {}, root / CATALOG
    for spec in sorted(base.glob("*/spec.md")) if base.is_dir() else []:
        if spec.parent.name.startswith("_"):
            continue
        for rule in CATALOG_RULE.finditer(read(spec) or ""):
            found.setdefault(rule.group(1), {"capability": spec.parent.name, "text": rule.group(3).strip(), "state": "designed" if rule.group(2) else "implemented"})
    return found


class Page(HTMLParser):
    """What a page of the mockup holds that the check needs: where it leads, what it cites, and how it is written."""

    def __init__(self, text):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.lang = self.screen = self.area = None
        self.links, self.refs, self.states, self.assets, self.problems = [], [], [], [], []
        self.pending = []
        self.pictures = 0
        self._words, self._hidden = [], 0
        self.h1 = 0
        self.labels, self.inputs = set(), []
        self._button = self._in_style = None
        self._style = []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        at = dict(attrs)
        if tag in ("script", "style"):
            self._hidden += 1
        # What a person can read of an element that has no text of its own.
        self._words.extend(at[key] for key in ("aria-label", "placeholder", "alt", "value", "title") if at.get(key))
        if tag == "img" or any(name == "ph" or name.startswith("ph-") for name in (at.get("class") or "").split()):
            self.pictures += 1
        if tag == "html":
            self.lang = at.get("lang")
        elif tag == "body":
            self.screen, self.area = at.get("data-screen"), at.get("data-area")
        elif tag == "h1":
            self.h1 += 1
        elif tag == "label" and at.get("for"):
            self.labels.add(at["for"])
        elif tag in ("input", "select", "textarea") and at.get("type") not in ("hidden", "submit", "button"):
            self.inputs.append((at.get("id"), at.get("aria-label") or at.get("aria-labelledby")))
        elif tag == "img" and "alt" not in at:
            self.problems.append("an image has no alt text")
        elif tag == "button":
            self._button = {"text": "", "label": at.get("aria-label")}
        elif tag == "style":
            self._in_style = True
        if tag == "a" and at.get("href"):
            self.links.append(at["href"])
        if at.get("data-goto"):
            self.links.append(at["data-goto"])
        if at.get("data-ref"):
            self.refs.extend(at["data-ref"].split())
        if at.get("data-state"):
            self.states.extend(at["data-state"].split())
        if at.get("data-set-state"):
            self.states.append(at["data-set-state"].strip())
        if tag in ("script", "img", "iframe", "source", "video", "audio") and at.get("src"):
            self.assets.append(at["src"])
        if tag == "link" and at.get("href"):
            self.assets.append(at["href"])
        if at.get("style"):
            self._style.append(at["style"])

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._hidden -= 1
        if tag == "button" and self._button is not None:
            if not self._button["text"].strip() and not self._button["label"]:
                self.problems.append("a button has no text and no aria-label")
            self._button = None
        elif tag == "style":
            self._in_style = None

    def handle_data(self, data):
        if not self._hidden:
            self._words.append(data)
        if self._button is not None:
            self._button["text"] += data
        if self._in_style:
            self._style.append(data)

    def styles(self):
        return "\n".join(self._style)

    def shows(self, label):
        """Whether the page says these words somewhere a person reads, whatever the case and the spacing."""
        return " ".join(label.split()).lower() in " ".join(" ".join(self._words).split()).lower()


def target_of(link):
    """(kind, page) of a link: a page of the mockup, a placeholder (#...), or something outside it."""
    link = link.strip()
    if link.startswith("#") or not link:
        return "placeholder", None
    if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", link) or link.startswith("//"):
        return "outside", None
    page = link.split("?", 1)[0].split("#", 1)[0]
    return ("page", page) if re.fullmatch(PAGE, page) else ("other", page)


def luminance(color):
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(part * 2 for part in color)
    parts = [int(color[at:at + 2], 16) / 255.0 for at in (0, 2, 4)]
    parts = [part / 12.92 if part <= 0.03928 else ((part + 0.055) / 1.055) ** 2.4 for part in parts]
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]


def contrast(one, other):
    high, low = sorted((luminance(one), luminance(other)), reverse=True)
    return (high + 0.05) / (low + 0.05)


# --------------------------------------------------------------------------- the check

def problems(product):
    """(what must be fixed, what is worth knowing). The first list is what `check` fails on."""
    hard, notes = list(product.hard), list(product.notes)
    rel = product.rel
    catalog = catalog_rules(product.root)
    pages = {}
    mockup = product.dir / "mockup"

    for name in ("spec.md", "capability-delta.md"):
        for path in sorted(product.dir.rglob(name)):
            hard.append("%s: the product keeps no file with that name; it is the name of a spec's file" % path.relative_to(product.root).as_posix())
    for path in sorted(product.dir.glob("*.md")) + sorted((product.dir / "screens").glob("*.md")):
        if re.search(r"^\s*- \*\*FR-\d+\*\*", read(path) or "", re.M):
            hard.append("%s: a requirement line (FR-###) belongs in a spec, not in the product" % path.relative_to(product.root).as_posix())

    def area_known(area, where):
        if area and area not in product.areas:
            hard.append("%s: the area %s is not in navigation.md" % (where, area))

    for story in product.stories.values():
        where = rel("story-map.md", story["line"])
        area_known(story["area"], where)
        for actor in story["actors"]:
            if actor not in product.actors:
                hard.append("%s: %s names the actor %s, which is not in actors.md" % (where, story["id"], actor))
        if not story["no_interface"] and not any(story["id"] in screen["stories"] for screen in product.screens.values()):
            hard.append("%s: %s has no screen; a screen names it in Stories, or the story says `- Interface: none - <why>`" % (where, story["id"]))

    files = {}
    for screen in product.screens.values():
        where = rel(screen["source"])
        area_known(screen["area"], where)
        for actor in screen["seen_by"]:
            if actor not in product.actors:
                hard.append("%s: Seen-By names %s, which is not in actors.md" % (where, actor))
        for story in screen["stories"]:
            if story not in product.stories:
                hard.append("%s: Stories names %s, which is not in story-map.md" % (where, story))
        for element in screen["elements"]:
            target = product.screens.get(element["to"]) if element["to"] else None
            if element["to"] and target is None:
                hard.append("%s: \"%s\" leads to %s, which is not a screen" % (rel(screen["source"], element["line"]), element["label"], element["to"]))
            elif target and element["state"] and element["state"] not in target["states"]:
                hard.append("%s: \"%s\" leads to %s/%s, and %s has no such state" % (rel(screen["source"], element["line"]), element["label"], element["to"], element["state"], element["to"]))
        for state in screen["states"]:
            if state != "normal" and state not in screen["described"]:
                hard.append("%s: ## States does not say what the state %s shows" % (where, state))
        if screen["file"]:
            if screen["file"] in files:
                hard.append("%s: %s is also the page of %s" % (where, screen["file"], files[screen["file"]]))
            files[screen["file"]] = screen["id"]

    cited = {}
    for owner in list(product.stories.values()) + list(product.screens.values()):
        for rule in owner["rules"]:
            cited.setdefault(rule, []).append(owner["id"])
    for rule, owners in sorted(cited.items()):
        if rule not in product.rules and rule not in catalog:
            hard.append("%s: %s cites %s, which is not in capability-drafts.md nor in the catalog" % (PRODUCT, ", ".join(owners), rule))
    for rule in product.rules.values():
        where = rel("capability-drafts.md", rule["line"])
        if rule["id"] not in cited:
            hard.append("%s: no story and no screen cites %s" % (where, rule["id"]))
        known = catalog.get(rule["id"])
        if known and known["capability"] != rule["capability"]:
            hard.append("%s: %s belongs to the capability %s in the catalog, and to %s here" % (where, rule["id"], known["capability"], rule["capability"]))
        elif known and known["text"] != rule["text"] and known["state"] != "designed":
            hard.append("%s: %s is built, and the draft gives it another text; a built rule changes with a spec, not with a draft" % (where, rule["id"]))
        elif known and known["text"] != rule["text"]:
            notes.append("%s: %s is approved with another text; this draft is a change that waits for speckit.studio.approve" % (where, rule["id"]))
        elif known:
            notes.append("%s: %s is already in the catalog with this text; speckit.studio.approve takes the draft away" % (where, rule["id"]))
    for comment in product.comments:
        if comment["status"] == "open" and comment["screen"] not in product.screens:
            notes.append("%s: %s was made on %s, which is not a screen any more" % (rel(COMMENTS), comment["id"], comment["screen"]))

    for flow in product.flows.values():
        where = rel("navigation.md", flow["line"])
        if len(flow["steps"]) < 2:
            hard.append("%s: %s needs at least two steps" % (where, flow["id"]))
        for screen, state in flow["steps"]:
            if screen not in product.screens:
                hard.append("%s: %s passes through %s, which is not a screen" % (where, flow["id"], screen))
            elif state not in product.screens[screen]["states"]:
                hard.append("%s: %s passes through %s/%s, and %s has no such state" % (where, flow["id"], screen, state, screen))

    # The pages of the mockup, once there is at least one.
    links = {}
    for screen in product.screens.values():
        path = mockup / screen["file"] if screen["file"] else None
        text = read(path) if path else None
        if text is None:
            continue
        where = "%s/mockup/%s" % (PRODUCT, screen["file"])
        page = pages[screen["id"]] = Page(text)
        if page.screen != screen["id"]:
            hard.append("%s: <body data-screen> says %s and this is the page of %s" % (where, page.screen or "nothing", screen["id"]))
        if page.area != screen["area"]:
            hard.append("%s: <body data-area> says %s and %s is in the area %s" % (where, page.area or "nothing", screen["id"], screen["area"]))
        for wanted in ("_studio/theme.css", "_studio/kit.css", "_studio/product.js", "_studio/screens.js", "_studio/runtime.js"):
            if wanted not in page.assets:
                hard.append("%s: the page does not load %s" % (where, wanted))
        links[screen["id"]] = set()
        for link in page.links + page.assets:
            kind, target = target_of(link)
            if kind == "placeholder" and link.strip() not in ("", "#"):
                page.pending.append(link.strip())
            if kind == "outside":
                hard.append("%s: %s leaves the mockup; nothing in it loads from or leads to another site" % (where, link))
            elif kind == "page" and target not in files:
                hard.append("%s: %s is not the page of any screen" % (where, link))
            elif kind == "page" and files[target] != screen["id"]:
                links[screen["id"]].add(files[target])
        for ref in page.refs:
            if ref not in product.stories and ref not in product.rules and ref not in catalog:
                hard.append("%s: data-ref cites %s, which is not a story nor a rule" % (where, ref))
        for state in page.states:
            if state not in screen["states"]:
                hard.append("%s: data-state uses %s, which is not a state of %s" % (where, state, screen["id"]))
        for rule in screen["rules"]:
            if rule not in page.refs:
                hard.append("%s: no element cites %s with data-ref, and %s says the screen applies it" % (where, rule, rel(screen["source"])))
        # How the page is written: worth fixing, and never a reason to stop.
        if not page.lang:
            notes.append("%s: <html> has no lang" % where)
        if page.h1 != 1:
            notes.append("%s: the page has %d h1 headings; it takes one" % (where, page.h1))
        for ident, label in page.inputs:
            if not label and (not ident or ident not in page.labels):
                notes.append("%s: a field has no label" % where)
        notes.extend("%s: %s" % (where, problem) for problem in page.problems)
        if page.pending:
            notes.append("%s: %d links lead to something that is not designed yet: %s" % (where, len(page.pending), ", ".join(sorted(set(page.pending)))))
        # The mockup is built from what is written: what a person presses or fills in is on the page under its name.
        for element in screen["elements"]:
            if element["kind"] in NAMED and not page.shows(element["label"]):
                notes.append("%s: %s names the %s \"%s\" and the page does not show it" % (where, rel(screen["source"]), element["kind"], element["label"]))
        if page.pictures and not any(element["kind"] == "image" for element in screen["elements"]):
            notes.append("%s: the page shows a picture and %s names no image" % (where, rel(screen["source"])))
        if re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|font-family", page.styles()):
            notes.append("%s: the page sets its own colors or fonts; a page uses the classes of the kit and the variables of the theme" % where)

    if pages:
        # A flow is also a way from one screen to the next: some steps happen with no link to click, such as being locked out.
        for flow in product.flows.values():
            for (one, _), (other, _) in zip(flow["steps"], flow["steps"][1:]):
                if one in links and other != one:
                    links[one].add(other)
        entries = [key for key, screen in product.screens.items() if screen["entry"]]
        if not entries:
            hard.append("%s: no screen says `- Entry: yes`; one screen at least is where a person starts" % PRODUCT)
        reached, frontier = set(entries), list(entries)
        while frontier:
            for target in links.get(frontier.pop(), ()):
                if target not in reached:
                    reached.add(target)
                    frontier.append(target)
        for key in sorted(pages):
            where = "%s/mockup/%s" % (PRODUCT, product.screens[key]["file"])
            if entries and key not in reached:
                hard.append("%s: nothing leads to %s from a screen where a person starts" % (where, key))
            if not links[key] and len(product.screens) > 1:
                hard.append("%s: %s leads to no other screen" % (where, key))

    looks = [(rel("look-and-feel.md"), product.theme)] if product.theme else []
    looks += [("%s, direction %s" % (rel("directions.md", look["line"]), key), look) for key, look in sorted(product.directions.items())]
    for where, look in looks:
        if not look.get("complete"):
            continue
        for mode in ("Light", "Dark"):
            for front, back, least in CONTRAST:
                ratio = contrast(look[mode][front], look[mode][back])
                if ratio < least:
                    notes.append("%s: %s, %s on %s has a contrast of %.1f and needs %.1f" % (where, mode, front, back, ratio, least))
    return hard, notes, pages


# --------------------------------------------------------------------------- how far the design is

def rule_state(product, catalog, rule):
    """A rule the catalog has is past its draft. An approved rule whose draft says something else has a change proposed:
    the catalog keeps its text until the person approves the new one."""
    known, draft = catalog.get(rule), product.rules.get(rule)
    if known and draft and known["state"] == "designed" and draft["text"] != known["text"]:
        return "proposed"
    return known["state"] if known else "draft" if draft else "unknown"


def area_rules(product, area):
    """The rules the stories and the screens of an area cite, in order."""
    owners = [owner for owner in list(product.stories.values()) + list(product.screens.values()) if owner["area"] == area]
    return sorted({rule for owner in owners for rule in owner["rules"]})


def approval_state(product, catalog, rules):
    """How far the approval of some rules is: nothing to approve counts as done, a change or a draft left behind needs the person."""
    states = [rule_state(product, catalog, rule) for rule in rules]
    # A rule that is in the catalog and still in the drafts: its text changed, or its approval was cut short.
    if any(rule in product.rules and rule in catalog for rule in rules):
        return "attention"
    approved = sum(1 for state in states if state not in ("draft", "unknown"))
    return "done" if approved == len(states) else "active" if approved else "pending"


def status(product):
    """How far the design is, read from its files: the steps, each area, what waits for the person and what comes next."""
    if not product.exists:
        return {"status": "none", "next": {"command": "speckit.studio.define", "args": "", "why": "The product has no design yet."}}
    hard, notes, pages = problems(product)
    catalog = catalog_rules(product.root)
    asked = [question for question in product.questions if question["status"] == "asked"]
    missing = [name for name, there in (("vision.md", product.vision), ("actors.md", bool(product.actors)), ("navigation.md", bool(product.areas)),
                                        ("look-and-feel.md", bool(product.theme and product.theme.get("complete")))) if not there]
    waiting = [question for question in asked if question["scope"] == "define"]
    define = {"state": "done" if not missing and not waiting else "active", "missing": missing,
              "decisions": sum(1 for question in product.questions if question["scope"] == "define" and question["status"] == "decided"),
              "asked": len(waiting)}
    areas = []
    for area in product.areas.values():
        stories = [story for story in product.stories.values() if story["area"] == area["id"]]
        screens = [screen for screen in product.screens.values() if screen["area"] == area["id"]]
        rules = area_rules(product, area["id"])
        counts = {}
        for rule in rules:
            state = rule_state(product, catalog, rule)
            counts[state] = counts.get(state, 0) + 1
        scope = "map " + area["id"]
        pending = [question for question in asked if question["scope"] == scope]
        orphan = [story["id"] for story in stories if not story["no_interface"] and not any(story["id"] in screen["stories"] for screen in screens)]
        drawn = [screen["id"] for screen in screens if screen["id"] in pages]
        if not stories and not screens:
            mapped = "pending"
        else:
            mapped = "done" if stories and screens and not orphan and not pending else "active"
        mock = "pending" if not drawn else "done" if len(drawn) == len(screens) else "active"
        said = [comment for comment in product.comments if comment["screen"] in product.screens and product.screens[comment["screen"]]["area"] == area["id"]]
        waiting_comments = sum(1 for comment in said if comment["status"] == "open")
        # An area with no rule has nothing to approve: it counts as approved once it is described and drawn.
        unready = mapped == "pending" or (not rules and (mapped != "done" or mock != "done"))
        approve = "pending" if unready else approval_state(product, catalog, rules)
        # Nothing asks for a round of changes once the area is approved, or once its comments were gone through.
        settled = (approve == "done" and mock == "done") or len(said) > waiting_comments
        iterate = "attention" if waiting_comments else "done" if settled else "pending"
        areas.append({
            "id": area["id"], "title": area["title"], "covers": area["covers"], "stories": len(stories), "screens": len(screens), "pages": len(drawn),
            "rules": counts, "asked": len(pending),
            "open": sum(1 for question in product.questions if question["scope"] == scope and question["status"] == "open"),
            "decisions": sum(1 for question in product.questions if question["scope"] == scope and question["status"] == "decided"),
            "links_pending": sum(len(pages[key].pending) for key in drawn),
            "comments": waiting_comments,
            "approved": sum(number for state, number in counts.items() if state not in ("draft", "unknown")),
            "steps": {"map": mapped, "mockup": mock, "iterate": iterate, "approve": approve},
            "state": "not-started" if mapped == "pending" else "in-design" if mapped != "done" or mock != "done" else "approved" if approve == "done" else "drawn",
        })
    remarks = {state: sum(1 for comment in product.comments if comment["status"] == state) for state in COMMENT_STATES}
    waiting_all = remarks["open"]
    if define["state"] != "done":
        step = {"command": "speckit.studio.define", "args": "", "why": "The product still lacks: %s." % ", ".join(missing) if missing
                else "%d questions of the first conversation wait for an answer." % len(waiting)}
    else:
        unmapped = next((area for area in areas if area["steps"]["map"] != "done"), None)
        undrawn = next((area for area in areas if area["steps"]["map"] == "done" and area["steps"]["mockup"] != "done"), None)
        changed = next((area for area in areas if area["steps"]["approve"] == "attention"), None)
        unapproved = next((area for area in areas if area["state"] == "drawn"), None)
        designed = sorted({catalog[rule]["capability"] for owner in list(product.stories.values()) + list(product.screens.values())
                           for rule in owner["rules"] if rule in catalog and catalog[rule]["state"] == "designed"})
        if undrawn:
            left = undrawn["screens"] - undrawn["pages"]
            step = {"command": "speckit.studio.mockup", "args": "", "why": "%s is described and %s no page yet." % (
                undrawn["title"], "its screen has" if undrawn["screens"] == 1 else "%d of its %d screens %s" % (left, undrawn["screens"], "has" if left == 1 else "have"))}
        elif waiting_all:
            step = {"command": "speckit.studio.iterate", "args": "", "why": "%s on the mockup %s to be applied." % (
                count(waiting_all, "comment"), "waits" if waiting_all == 1 else "wait")}
        elif changed:
            step = {"command": "speckit.studio.approve", "args": changed["id"], "why": "A rule of %s changed after it was approved, or its approval was cut short." % changed["title"]}
        elif unapproved:
            step = {"command": "speckit.studio.approve", "args": unapproved["id"],
                    "why": "%s is drawn. Approve its rules when the mockup is right, or say what to change first." % unapproved["title"]}
        elif unmapped:
            step = {"command": "speckit.studio.map", "args": unmapped["id"], "why": "%s is %s." % (
                unmapped["title"], "not described yet" if unmapped["steps"]["map"] == "pending" else "half described")}
        elif designed:
            step = {"command": "speckit.capabilities.slice", "args": designed[0], "why": "Every area is approved. Cut the rules of %s into slices, and build one spec per slice." % designed[0]}
        else:
            step = {"command": "speckit.studio.iterate", "args": "", "why": "Every area is approved. To change something, say it."}

    # The steps a person runs, in order, each with what its files prove.
    words = {"vision.md": "the idea", "actors.md": "the people", "navigation.md": "the areas", "look-and-feel.md": "the look"}
    fact = count(define["decisions"], "decision")
    if waiting:
        fact += ", %d waiting" % len(waiting)
    if len(missing) == len(words) and not define["decisions"] and not waiting:
        fact = "Not started"
    elif missing:
        fact += ", missing %s" % ", ".join(words[name] for name in missing)
    described = [area for area in areas if area["steps"]["map"] == "done"]
    started = [area for area in areas if area["steps"]["map"] != "pending"]
    steps = [
        {"name": "define", "command": "speckit.studio.define", "state": define["state"], "fact": fact},
        {"name": "map", "command": "speckit.studio.map", "state": "pending" if not started else "done" if len(described) == len(areas) else "active",
         "fact": "%d of %s" % (len(described), count(len(areas), "area")) if areas else "No areas yet"},
        {"name": "mockup", "command": "speckit.studio.mockup",
         "state": "pending" if not pages else "attention" if hard else "done" if len(pages) == len(product.screens) else "active",
         "fact": ("%d of %s" % (len(pages), count(len(product.screens), "screen")) if product.screens else "No screens yet")
                 + (", %s" % count(len(hard), "problem") if pages and hard else "")},
    ]
    reviewed = remarks["applied"] + remarks["declined"]
    if waiting_all:
        fact = "%s open" % count(waiting_all, "comment") + (", %d applied" % remarks["applied"] if remarks["applied"] else "")
    elif reviewed:
        fact = "%s applied" % count(remarks["applied"], "comment") + (", %d not" % remarks["declined"] if remarks["declined"] else "")
    else:
        fact = "No comments yet"
    steps.append({"name": "iterate", "command": "speckit.studio.iterate", "state": "attention" if waiting_all else "done" if reviewed else "pending", "fact": fact})
    approved = [area for area in areas if area["state"] == "approved"]
    touched = [area for area in areas if area["steps"]["approve"] in ("active", "attention")]
    steps.append({"name": "approve", "command": "speckit.studio.approve",
                  "state": "attention" if any(area["steps"]["approve"] == "attention" for area in areas)
                           else "done" if areas and len(approved) == len(areas) else "active" if approved or touched else "pending",
                  "fact": "%d of %s" % (len(approved), count(len(areas), "area")) if areas else "No areas yet"})
    attention = []
    if waiting_all:
        attention.append({"kind": "comments", "text": "%s on the mockup %s to be applied." % (count(waiting_all, "comment"), "waits" if waiting_all == 1 else "wait")})
    for area in areas:
        if area["steps"]["approve"] == "attention":
            proposed = area["rules"].get("proposed", 0)
            attention.append({"kind": "approve", "area": area["id"],
                              "text": "%s of %s changed after %s approved: %s for approval." % (
                                  count(proposed, "rule"), area["title"], "it was" if proposed == 1 else "they were", "it waits" if proposed == 1 else "they wait")
                              if proposed else "The approval of %s was cut short: run it again." % area["title"]})
    if waiting:
        attention.append({"kind": "asked", "text": "%s about the product %s for an answer." % (count(len(waiting), "question"), "waits" if len(waiting) == 1 else "wait")})
    for area in areas:
        if area["asked"]:
            attention.append({"kind": "asked", "area": area["id"],
                              "text": "%s about %s %s for an answer." % (count(area["asked"], "question"), area["title"], "waits" if area["asked"] == 1 else "wait")})
    for question in product.questions:
        if question["status"] == "open":
            attention.append({"kind": "open", "text": "Open, %s decides: %s" % (question["owner"], question["question"])})
    if hard:
        attention.append({"kind": "check", "text": "The check found %s in the design." % count(len(hard), "problem"), "details": hard[:5]})
    for area in areas:
        if area["links_pending"]:
            attention.append({"kind": "pending", "area": area["id"],
                              "text": "%s in %s %s to something that is not designed yet." % (count(area["links_pending"], "link"), area["title"],
                                                                                              "leads" if area["links_pending"] == 1 else "lead")})
    return {
        "status": "ok", "product": product.name, "owner": product.owner, "language": product.language, "device": product.device,
        "define": define, "areas": areas, "steps": steps, "attention": attention, "comments": remarks,
        "totals": {"areas": len(areas), "not_started": sum(1 for area in areas if area["state"] == "not-started"),
                   "in_design": sum(1 for area in areas if area["state"] == "in-design"), "drawn": sum(1 for area in areas if area["state"] == "drawn"),
                   "approved": len(approved),
                   "screens": len(product.screens), "pages": len(pages), "rules": len(product.rules),
                   "decisions": sum(1 for question in product.questions if question["status"] == "decided")},
        "summary": {"idea": product.idea, "people": [{"name": actor["name"], "role": actor["role"], "about": actor["about"]} for actor in product.actors.values()],
                    "look": product.theme["direction"] if product.theme and product.theme.get("complete") else ""},
        "documents": [name for name in DOCUMENTS if read(product.dir / name) is not None],
        "mockup": bool(pages) and read(product.dir / "mockup" / "index.html") is not None,
        "open": [{"id": question["id"], "scope": question["scope"], "question": question["question"], "owner": question["owner"]}
                 for question in product.questions if question["status"] == "open"],
        "check": {"hard": len(hard), "notes": len(notes)}, "next": step,
    }


# --------------------------------------------------------------------------- the files of the mockup nobody edits

def as_json(data):
    """JSON that cannot close the <script> it sits in, whatever a name or a rule says."""
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True).replace("</", "<\\/")


def as_script(name, data):
    return "window.%s = %s;\n" % (name, as_json(data))


def font_of(look):
    return SYSTEM_FONT if look["font"].lower() == "system" else "%s, %s" % (look["font"], SYSTEM_FONT)


def theme_css(theme):
    def block(mode, indent):
        lines = ["%s--%s: %s;" % (indent, token, theme[mode][token]) for token in TOKENS]
        lines.append("%s--shadow: %s;" % (indent, SHADOW[mode]))
        lines.append("%scolor-scheme: %s;" % (indent, mode.lower()))
        return "\n".join(lines)
    font = font_of(theme)
    return ("/* Generated by studio from look-and-feel.md. Edit that file, not this one. */\n"
            ":root {\n%s\n  --radius: %s;\n  --radius-control: %s;\n  --font: %s;\n}\n\n"
            "@media (prefers-color-scheme: dark) {\n  :root:not([data-theme=\"light\"]) {\n%s\n  }\n}\n\n"
            ":root[data-theme=\"dark\"] {\n%s\n}\n") % (block("Light", "  "), theme["radius"], theme["radius_control"], font, block("Dark", "    "), block("Dark", "  "))


def index_html(product):
    entry = next((screen for screen in product.screens.values() if screen["entry"] and screen["file"]), None)
    first = entry or next((screen for screen in product.screens.values() if screen["file"]), None)
    jump = "<script>location.replace(%s + location.search);</script>" % json.dumps(first["file"]) if first else ""
    name = product.name or "Product"
    link = '<a class="btn btn-primary" href="%s">%s</a>' % (first["file"], first["title"]) if first else ""
    return ("<!doctype html>\n<html lang=\"%s\">\n<head>\n  <meta charset=\"utf-8\">\n  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "  <title>%s</title>\n  <link rel=\"stylesheet\" href=\"_studio/theme.css\">\n  <link rel=\"stylesheet\" href=\"_studio/kit.css\">\n  %s\n</head>\n"
            "<body>\n  <div class=\"app\"><div class=\"auth\"><main class=\"card\"><h1>%s</h1>%s</main></div></div>\n</body>\n</html>\n") % (
                product.language, escape(name), jump, escape(name), link)


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build(product, kit):
    """Writes what the mockup needs and nobody edits: the kit, the theme, the list of screens and the data of the product."""
    catalog = catalog_rules(product.root)
    target = product.dir / "mockup" / "_studio"
    written = []
    for name in KIT_FILES:
        source = read(kit / name)
        if source is None:
            raise StudioError("the kit of studio is not where it should be: %s" % (kit / name))
        write(target / name, source)
        written.append("mockup/_studio/" + name)
    if product.theme and product.theme.get("complete"):
        write(target / "theme.css", theme_css(product.theme))
        written.append("mockup/_studio/theme.css")
    screens = {"areas": {area["id"]: area["title"] for area in product.areas.values()},
               "pantallas": {screen["id"]: dict({"archivo": screen["file"], "titulo": screen["title"], "area": screen["area"], "estados": screen["states"]},
                                                **({"sesion": True} if screen["session"] else {})) for screen in product.screens.values() if screen["file"]},
               "flujos": {flow["id"]: {"titulo": flow["title"], "pasos": flow["steps"]} for flow in product.flows.values()},
               "entrada": next((screen["id"] for screen in product.screens.values() if screen["entry"] and screen["file"]), "")}
    write(target / "screens.js", "/* Generated by studio from navigation.md and screens/. */\n" + as_script("STUDIO_SCREENS", screens))
    written.append("mockup/_studio/screens.js")
    rules, examples = {}, record_examples(product.root)
    for rule in sorted({rule for owner in list(product.stories.values()) + list(product.screens.values()) for rule in owner["rules"]} | set(product.rules)):
        draft, known = product.rules.get(rule), catalog.get(rule)
        if draft or known:
            # A draft says what the person wants now: the mockup shows it, and what was approved before when that is something else.
            state = rule_state(product, catalog, rule)
            rules[rule] = {"capacidad": (draft or known)["capability"], "texto": (draft or known)["text"], "estado": state,
                           "nota": draft["example"] if draft else examples.get(rule, "")}
            if state == "proposed":
                rules[rule]["antes"] = known["text"]
    data = {"producto": product.name, "idioma": product.language, "dispositivo": product.device,
            "personas": [{"id": actor["id"], "nombre": actor["name"], "rol": actor["role"], "descripcion": actor["about"], "correo": actor["email"]}
                         for actor in product.actors.values()],
            "historias": {story["id"]: story["story"] for story in product.stories.values()}, "reglas": rules}
    write(target / "product.js", "/* Generated by studio from the product and the catalog of capabilities. */\n" + as_script("STUDIO_DATA", data))
    written.append("mockup/_studio/product.js")
    write(product.dir / "mockup" / "index.html", index_html(product))
    written.append("mockup/index.html")
    return written


def directions(product, kit):
    """Writes the page that shows every complete direction side by side, on the same two sample screens."""
    complete = [look for _, look in sorted(product.directions.items()) if look["complete"]]
    if not complete:
        raise StudioError("%s/directions.md has no complete direction: each one is `## <letter> <name>` with its Light and Dark colors" % PRODUCT)
    template, kit_css = read(kit / DIRECTIONS_PAGE), read(kit / "kit.css")
    if template is None or kit_css is None or DATA_PLACEHOLDER not in template:
        raise StudioError("the kit of studio is not where it should be: %s" % (kit / DIRECTIONS_PAGE))
    chosen = re.match(r"%s\b" % LETTER, product.theme["direction"]) if product.theme else None
    chosen = chosen.group(0) if chosen else ""
    data = {"producto": product.name, "idioma": product.language, "dispositivo": product.device, "muestra": product.sample, "direcciones": [
        {"id": look["id"], "nombre": look["name"], "porque": look["why"], "elegida": look["id"] == chosen, "fuente": font_of(look),
         "radio": look["radius"], "radioControl": look["radius_control"],
         "claro": dict(look["Light"], shadow=SHADOW["Light"]), "oscuro": dict(look["Dark"], shadow=SHADOW["Dark"])} for look in complete]}
    target = product.dir / "mockup" / "_studio"
    write(target / "kit.css", kit_css)
    write(target / DIRECTIONS_PAGE, template.replace(DATA_PLACEHOLDER, as_json(data), 1))
    return "mockup/_studio/" + DIRECTIONS_PAGE


def pick(product, letter):
    """Makes one direction the look of the product: look-and-feel.md says what that direction says."""
    look = product.directions.get(letter)
    if look is None:
        raise StudioError("%s/directions.md has no direction %s; it has %s" % (PRODUCT, letter, ", ".join(sorted(product.directions)) or "none"))
    if not look["complete"]:
        raise StudioError("direction %s is not complete: it needs every color of Light and of Dark" % letter)
    lines = ["# Look and feel", "", "- Direction: %s %s" % (letter, look["name"]), "- Font: %s" % look["font"], "- Radius: %s" % look["radius"],
             "- Radius-Control: %s" % look["radius_control"], ""]
    for mode in ("Light", "Dark"):
        lines += ["## %s" % mode, ""] + ["- %s: %s" % (token, look[mode][token]) for token in TOKENS] + [""]
    write(product.dir / "look-and-feel.md", "\n".join(lines))
    return "look-and-feel.md"


def drawn(product, area=None):
    """The screens that have a page, in the order of their files."""
    return [screen for screen in product.screens.values()
            if screen["file"] and read(product.dir / "mockup" / screen["file"]) is not None and (area is None or screen["area"] == area)]


def can_open(env=None, platform=None):
    """False where a browser would open and the person could not see it, or was told not to open."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if any(env.get(name, "").strip().lower() not in ("", "0", "false") for name in NO_BROWSER_ENV + ("CI",)):
        return False
    if env.get("SSH_CONNECTION") or env.get("SSH_CLIENT") or env.get("SSH_TTY"):
        return False
    if platform.startswith("linux") and not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        return False
    return True


def can_serve(env=None):
    """False where the person asked for no server: the mockup then opens from the disk, and its comments stay in the browser."""
    env = os.environ if env is None else env
    return env.get(NO_SERVER_ENV, "").strip().lower() in ("", "0", "false")


def show(product, kit, page=None, browser=True):
    """Writes what is to be seen and opens it. Returns (its link, whether a browser opened it, whether a server of this project serves it).
    The mockup is served where a browser can open it: a comment made in a page that is served is kept in the project."""
    if page == "directions":
        path = product.dir / directions(product, kit)
    else:
        if not drawn(product):
            raise NothingYet("no screen has a page yet: speckit.studio.mockup draws them")
        build(product, kit)
        path = product.dir / "mockup" / "index.html"
    link, opened, served = path.resolve().as_uri(), False, False
    if browser and can_open():
        if page != "directions" and can_serve():
            state = server_state(product.root) or start_server(product.root)
            if state:
                link, served = "http://127.0.0.1:%d/index.html" % state["port"], True
        import webbrowser
        try:
            opened = bool(webbrowser.open(link))
        except webbrowser.Error:
            opened = False
    return link, opened, served


def find_browser(env=None):
    """A browser that can take a picture of a page without a window: Chrome, Chromium, Edge or Brave."""
    env = os.environ if env is None else env
    named = env.get(BROWSER_ENV, "").strip()
    if named:
        return named if os.path.isfile(named) else None
    candidates = []
    if sys.platform == "darwin":
        candidates = ["/Applications/%s.app/Contents/MacOS/%s" % (app, app) for app in ("Google Chrome", "Chromium", "Microsoft Edge", "Brave Browser")]
    elif os.name == "nt":
        for base in (env.get("PROGRAMFILES"), env.get("PROGRAMFILES(X86)"), env.get("LOCALAPPDATA")):
            if base:
                candidates += [os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                               os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")]
    for path in candidates:
        if os.path.isfile(path):
            return path
    import shutil
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def shoot(browser, link, target, size):
    """One picture of one page. The browser runs with a profile of its own, so it never touches the person's."""
    import shutil
    import subprocess
    import tempfile
    if target.is_symlink() or target.exists():
        target.unlink()
    profile = tempfile.mkdtemp(prefix="studio-shot-")
    command = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "--disable-extensions",
               "--user-data-dir=" + profile, "--window-size=%d,%d" % size, "--virtual-time-budget=2000", "--screenshot=" + str(target), link]
    try:
        subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=SHOT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return target.is_file() and target.stat().st_size > 0


def shots(product, kit, area=None, page=None, states=False):
    """Pictures of the screens that have a page, in light colors and as the person who sees each one. Returns (taken, failed)."""
    browser = find_browser()
    if browser is None:
        raise NothingYet("no Chrome, Chromium or Edge was found to take the pictures; %s can name one" % BROWSER_ENV)
    folder = product.dir / "mockup" / "_shots"
    wanted = []
    if page == "directions":
        path = product.dir / directions(product, kit)
        wanted.append({"name": "directions", "title": "Directions", "link": path.resolve().as_uri() + "?modo=claro", "size": DIRECTIONS_SIZE})
    else:
        if area and area not in product.areas:
            raise StudioError("the area %s is not in navigation.md" % area)
        screens = drawn(product, area)
        if not screens:
            raise NothingYet("no screen has a page yet: speckit.studio.mockup draws them")
        build(product, kit)
        for screen in screens:
            who = next((actor for actor in screen["seen_by"] if actor in product.actors), next(iter(product.actors), ""))
            for state in (screen["states"] if states else ["normal"]):
                query = "?captura=1&modo=claro&sesion=%d" % (1 if screen["session"] else 0)
                query += "&persona=" + who if who else ""
                query += "" if state == "normal" else "&estado=" + state
                wanted.append({"name": screen["id"] + ("" if state == "normal" else "." + state), "screen": screen["id"], "state": state,
                               "title": screen["title"], "link": (product.dir / "mockup" / screen["file"]).resolve().as_uri() + query,
                               "size": DEVICES[product.device]})
    folder.mkdir(parents=True, exist_ok=True)
    taken, failed = [], []
    for shot in wanted:
        target = folder / (shot["name"] + ".png")
        done = shoot(browser, shot.pop("link"), target, shot.pop("size"))
        shot["file"] = "%s/mockup/_shots/%s" % (PRODUCT, target.name)
        (taken if done else failed).append(shot)
    return taken, failed


# --------------------------------------------------------------------------- what the person says on the mockup

def render_comments(comments):
    """comments.md as this script writes it: one block per comment, its fields, and its words quoted."""
    lines = ["# Comments", "", "<!-- What the person said on the mockup. The mockup adds a comment and `comments resolve` says what became of it: never by hand. -->", ""]
    for comment in comments:
        lines.append("## %s" % comment["id"])
        for key, name in (("screen", "Screen"), ("state", "State"), ("person", "Person"), ("element", "Element"), ("path", "Path"),
                          ("refs", "Refs"), ("date", "Date"), ("status", "Status"), ("note", "Note")):
            value = ", ".join(comment[key]) if key == "refs" else comment[key]
            if value:
                lines.append("- %s: %s" % (name, value))
        lines += [""] + ["> " + line if line else ">" for line in comment["text"].split("\n")] + [""]
    return "\n".join(lines)


def readable_comments(product):
    """The comments, once the file that keeps them can be read whole: this script rewrites it, and would drop what it cannot read."""
    wrong = [problem for problem in product.hard if problem.startswith(product.rel(COMMENTS))]
    if wrong:
        raise StudioError("%s cannot be read as it is written: %s" % (product.rel(COMMENTS), "; ".join(wrong)))
    return [dict(comment) for comment in product.comments]


def clean_comment(product, entry, stamp):
    """(a comment as it is kept, None) or (None, why not). Whatever a comment says is data: each part is cut to what its field takes."""
    if not isinstance(entry, dict):
        return None, "a comment is an object with its screen and its text"
    screen, text = one_line(entry.get("screen")), many_lines(entry.get("text"))
    if screen not in product.screens:
        return None, "%s is not a screen of the product" % (screen or "nothing")
    if not text:
        return None, "the comment on %s says nothing" % screen
    state, person, path, date = one_line(entry.get("state")), one_line(entry.get("person")), one_line(entry.get("path"), 400), one_line(entry.get("date"))
    refs = [part for part in re.split(r"[\s,]+", one_line(entry.get("refs"))) if re.fullmatch("%s|%s" % (STORY, RULE), part)]
    return {"screen": screen, "state": state if re.fullmatch(SLUG, state) else "normal", "person": person if re.fullmatch(ACTOR, person) else "",
            "element": one_line(entry.get("element")), "path": path if re.fullmatch(r"[a-z0-9:()> -]*", path) else "", "refs": refs,
            "date": date if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", date) else stamp, "status": "open", "note": "", "text": text}, None


def now_stamp():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def add_comments(product, entries, stamp=None):
    """Keeps new comments, each under the next number: a number is never used twice. Returns (the ones kept, why each other was not).
    A comment already kept, with the same screen, element, words and date, is not kept again, unless the person took it back."""
    comments = readable_comments(product)
    known = {(comment["screen"], comment["element"], comment["text"], comment["date"]) for comment in comments if comment["status"] != "withdrawn"}
    number = max([int(comment["id"][2:]) for comment in comments] or [0])
    added, skipped = [], []
    for entry in entries:
        comment, why = clean_comment(product, entry, stamp or now_stamp())
        if comment is None:
            skipped.append(why)
            continue
        key = (comment["screen"], comment["element"], comment["text"], comment["date"])
        if key in known:
            skipped.append("the comment on %s is already kept: %s" % (comment["screen"], comment["text"].split("\n")[0][:60]))
            continue
        number += 1
        comment["id"] = "C-%03d" % number
        known.add(key)
        comments.append(comment)
        added.append(comment)
    if added:
        write(product.dir / COMMENTS, render_comments(comments))
    return added, skipped


def resolve_comments(product, keys, state, note=""):
    """Says what became of some comments. Returns them as they are now."""
    comments = readable_comments(product)
    unknown = sorted(set(keys) - {comment["id"] for comment in comments})
    if not keys or unknown:
        raise StudioError("no comment %s in %s" % (", ".join(unknown), product.rel(COMMENTS)) if unknown else "say which comments, such as C-001")
    note = one_line(note, 400)
    if state == "declined" and not note:
        raise StudioError("a declined comment says why: --note")
    changed = [comment for comment in comments if comment["id"] in keys]
    for comment in changed:
        comment["status"], comment["note"] = state, note
    write(product.dir / COMMENTS, render_comments(comments))
    return changed


def pasted_comments(text):
    """The comments in the Markdown the mockup copies: `## C-001: SCR-login (Entrar)`, its fields and its quoted words."""
    # A quoted line is what a person typed: it must not open a comment of Markdown that would hide what follows.
    text = re.sub(r"(?m)^\s*>.*$", lambda line: line.group(0).replace("<!--", "<! --"), text)
    found = []
    for item in outline(text):
        match = PASTED.match(item["title"]) if item["level"] == 2 else None
        if match:
            fields = item["fields"]
            found.append({"screen": match.group(1), "state": fields.get("State"), "person": fields.get("Person"), "element": fields.get("Element"),
                          "refs": fields.get("References"), "date": fields.get("Date"), "text": quoted(item)})
    return found


# --------------------------------------------------------------------------- approving the rules of an area

def record_examples(root):
    """The example each approved rule was approved with: the design records keep them under `## Examples`."""
    found, base = {}, root / CHANGES
    for path in sorted(base.glob("*/" + RECORD)) if base.is_dir() else []:
        inside = False
        for line in (read(path) or "").splitlines():
            if line.startswith("## "):
                inside = line.strip() == "## Examples"
            elif inside and EXAMPLE.match(line):
                found[EXAMPLE.match(line).group(1)] = EXAMPLE.match(line).group(2)
    return found


def last_approver(root):
    """Who approved rules the last time, from the design records. The person is asked whether it is them again: it is never taken for granted."""
    found, base = [], root / CHANGES
    for path in sorted(base.glob("*/" + RECORD)) if base.is_dir() else []:
        for line in (read(path) or "").splitlines():
            match = APPROVED_BY.match(line)
            if match:
                found.append((match.group(2), len(path.parent.name), path.parent.name, one_line(match.group(1))))
                break
    return max(found)[3] if found else None


def approval(product, area):
    """What approving an area publishes, and what stands in the way. Reads, and writes nothing."""
    if area not in product.areas:
        raise StudioError("the area %s is not in navigation.md; the areas are %s" % (area, ", ".join(sorted(product.areas)) or "none"))
    hard, _, pages = problems(product)
    catalog = catalog_rules(product.root)
    screens = [screen for screen in product.screens.values() if screen["area"] == area]
    stories = [story for story in product.stories.values() if story["area"] == area]
    capabilities, leftover, approved, blockers = {}, [], [], []
    for key in area_rules(product, area):
        draft, known = product.rules.get(key), catalog.get(key)
        if draft is None:
            if known:
                approved.append(key)
            continue
        if known and known["text"] == draft["text"]:
            leftover.append(key)
            continue
        elsewhere = sorted(owner["id"] for owner in list(product.stories.values()) + list(product.screens.values())
                           if key in owner["rules"] and owner["area"] != area)
        group = capabilities.setdefault(draft["capability"], {
            "id": draft["capability"], "covers": product.capabilities[draft["capability"]]["covers"],
            "new": read(product.root / CATALOG / draft["capability"] / "spec.md") is None, "rules": []})
        group["rules"].append({"id": key, "text": draft["text"], "example": draft["example"], "from": known["text"] if known else None, "also_in": elsewhere})
    if read(product.root / CAPABILITIES_SCRIPT) is None:
        blockers.append("approving needs the capabilities extension, which keeps the approved rules: specify extension add capabilities")
    if hard:
        blockers.append("the check finds %s in the design: fix %s first, `check` lists them" % (count(len(hard), "problem"), "it" if len(hard) == 1 else "them"))
    asked = [question["id"] for question in product.questions if question["scope"] == "map " + area and question["status"] == "asked"]
    if asked:
        blockers.append("%s about the area %s for an answer: %s" % (count(len(asked), "question"), "waits" if len(asked) == 1 else "wait", ", ".join(asked)))
    warnings = []
    waiting = [comment["id"] for comment in product.comments if comment["status"] == "open" and comment["screen"] in {screen["id"] for screen in screens}]
    if waiting:
        warnings.append("%s on its screens %s to be applied: %s" % (count(len(waiting), "comment"), "waits" if len(waiting) == 1 else "wait", ", ".join(waiting)))
    undecided = [question["id"] for question in product.questions if question["scope"] == "map " + area and question["status"] == "open"]
    if undecided:
        warnings.append("%s about the area %s still open: %s" % (count(len(undecided), "question"), "is" if len(undecided) == 1 else "are", ", ".join(undecided)))
    undrawn = [screen["id"] for screen in screens if screen["id"] not in pages]
    if undrawn:
        warnings.append("%s no page in the mockup yet: %s" % ("1 screen has" if len(undrawn) == 1 else "%d screens have" % len(undrawn), ", ".join(undrawn)))
    groups = [capabilities[key] for key in sorted(capabilities)]
    return {
        "area": area, "title": product.areas[area]["title"], "covers": product.areas[area]["covers"], "owner": product.owner,
        "last_by": last_approver(product.root),
        "stories": [{"id": story["id"], "title": story["title"]} for story in stories],
        "screens": [{"id": screen["id"], "title": screen["title"]} for screen in screens],
        "capabilities": groups, "rules": sum(len(group["rules"]) for group in groups), "leftover": leftover, "approved": approved,
        "blockers": blockers, "warnings": warnings,
        "status": "blocked" if blockers else "ready" if groups or leftover else "nothing",
    }


def record_text(plan, who, day):
    """The design record of an approval: who approved and when, the example of each rule, and the delta the catalog publishes."""
    lines = ["# Design: %s" % plan["title"], "", "Approved by: %s on %s" % (who, day.isoformat()), "", "## Examples", ""]
    lines += ["- %s: %s" % (rule["id"], rule["example"]) for group in plan["capabilities"] for rule in group["rules"]]
    lines += ["", "## Capability Delta", "<!-- capability-delta:v1 -->"]
    for group in plan["capabilities"]:
        if group["new"]:
            lines += ["", "### NEW-CAPABILITY %s" % group["id"], "- Covers: %s" % group["covers"]]
        for rule in group["rules"]:
            lines += ["", "### DESIGNED %s" % rule["id"], "- Capability: %s" % group["id"], "- From: %s" % (rule["from"] or "(none)"),
                      "- To: %s" % rule["text"], "- Links: none"]
    return "\n".join(lines) + "\n"


def record_place(root, area, text, day):
    """Where the record of today's approval of an area goes: the same place when it is the same record or one that was never published,
    and a new one beside it otherwise. A published record is never rewritten."""
    for number in range(1, 100):
        name = "%s/%s-design-%s%s" % (CHANGES, day.strftime("%Y%m%d"), area, "" if number == 1 else "-%d" % number)
        folder = root / name
        if folder.is_symlink():
            continue
        published = any(path.name.endswith(".lock.json") for path in folder.iterdir()) if folder.is_dir() else False
        if not folder.exists() or not published or read(folder / RECORD) == text:
            return name
    raise StudioError("too many design records for %s today" % area)


def publish_design(root, record):
    """Has the catalog publish a design record. Publishing the same record twice changes nothing."""
    import subprocess
    try:
        done = subprocess.run([sys.executable, str(root / CAPABILITIES_SCRIPT), "publish-design", "--root", str(root), "--change", record],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise StudioError("the catalog could not publish %s: %s" % (record, error))
    try:
        answer = json.loads(done.stdout.decode("utf-8"))
    except ValueError:
        answer = {}
    if done.returncode != 0 or not isinstance(answer, dict) or answer.get("status") not in ("published", "unchanged"):
        said = answer if isinstance(answer, dict) else {}
        details = said.get("errors") or said.get("conflicts") or [said.get("status") or done.stderr.decode("utf-8", "replace").strip()[-400:] or "it said nothing"]
        raise StudioError("the catalog did not publish %s: %s" % (record, "; ".join(str(detail) for detail in details)))
    return answer


def without_rules(text, rules):
    """capability-drafts.md without those rules, and without a capability left with none."""
    lines, items = text.split("\n"), outline(text)
    gone = set()
    for index, item in enumerate(items):
        end = items[index + 1]["line"] - 1 if index + 1 < len(items) else len(lines)
        if item["level"] == 3 and split_title(item["title"], RULE)[0] in rules:
            gone.update(range(item["line"], end + 1))
    for index, item in enumerate(items):
        if item["level"] != 2:
            continue
        below = under(items, index)
        if below and all(child["line"] in gone for child in below):
            end = next((other["line"] - 1 for other in items[index + 1:] if other["level"] <= 2), len(lines))
            gone.update(range(item["line"], end + 1))
    kept = [line for number, line in enumerate(lines, 1) if number not in gone]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).rstrip("\n") + "\n"


def approve(product, area, by=None, day=None):
    """Publishes the draft rules of an area as approved, with who approved and when, and takes them out of the drafts.
    It can be run again: cut short after publishing, the second run only takes the drafts away."""
    import datetime
    plan = approval(product, area)
    if plan["status"] != "ready":
        return plan
    who = one_line(by) or one_line(product.owner)
    if not who:
        raise StudioError("say who approves: --by, or `- Owner:` in %s" % product.rel("product.md"))
    plan["by"] = who
    if plan["capabilities"]:
        day = day or datetime.date.today()
        text = record_text(plan, who, day)
        plan["record"] = record_place(product.root, area, text, day)
        write(product.root / plan["record"] / RECORD, text)
        plan["published"] = publish_design(product.root, plan["record"])["status"]
    published = [rule["id"] for group in plan["capabilities"] for rule in group["rules"]] + plan["leftover"]
    drafts = product.dir / "capability-drafts.md"
    write(drafts, without_rules(read(drafts) or "", set(published)))
    plan["status"], plan["approved_now"] = "approved", published
    return plan


# --------------------------------------------------------------------------- the server of the mockup

def root_key(root):
    import hashlib
    return hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]


def server_file(root):
    """Where the running server of a project says its port and its session: outside the project, so it is never committed."""
    import tempfile
    return Path(tempfile.gettempdir()) / ("speckit-studio-%s.json" % root_key(root))


def ask(port, method, path, session=None, body=None, timeout=3):
    """One call to a server of studio on this machine. None when nobody answers as one."""
    import urllib.request
    request = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), method=method,
                                     data=None if body is None else json.dumps(body).encode("utf-8"))
    if session:
        request.add_header(SESSION_HEADER, session)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        # No proxy: this never leaves the machine.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
            answer = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except (OSError, ValueError):
        return None
    return answer if isinstance(answer, dict) else None


def server_state(root):
    """The server of this project's mockup, when one answers: its port and its session. None otherwise."""
    try:
        state = json.loads(read(server_file(root)) or "")
    except ValueError:
        return None
    if not isinstance(state, dict) or not isinstance(state.get("port"), int) or not isinstance(state.get("session"), str):
        return None
    answer = ask(state["port"], "GET", "/_api/ping")
    return state if answer and answer.get("root") == root_key(root) else None


def start_server(root, wait=15.0):
    """Starts the server of this project's mockup on its own, so it outlives this command. None when it cannot."""
    import subprocess
    import time
    options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        options["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS and CREATE_NEW_PROCESS_GROUP: no console, no Ctrl+C of ours.
    else:
        options["start_new_session"] = True
    try:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "serve", "--root", str(root)], **options)
    except OSError:
        return None
    until = time.monotonic() + wait
    while time.monotonic() < until:
        time.sleep(0.1)
        state = server_state(root)
        if state:
            return state
    return None


def stop_server(root):
    """Tells the server of this project's mockup to stop. False when none was running."""
    state = server_state(root)
    return bool(state and ask(state["port"], "POST", "/_api/stop", state["session"], {}))


def public(comment):
    return {key: comment[key] for key in ("id", "screen", "state", "person", "element", "path", "refs", "date", "status", "note", "text")}


def make_server(root, port=None):
    """A server that shows the mockup of one project to this machine only, and keeps the comments made in it.
    Returns (the server, its session). The session is a word only the pages it serves know: without it nothing is written."""
    import hmac
    import secrets
    import time
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import unquote

    mockup = root / PRODUCT / "mockup"
    session, key = secrets.token_urlsafe(24), root_key(root)
    mark = ('<meta name="studio-session" content="%s">' % session).encode("ascii")

    class Server(HTTPServer):
        # On Windows this option would let another program take the port while this one listens.
        allow_reuse_address = os.name != "nt"
        stop = False
        touched = time.monotonic()

    class Handler(BaseHTTPRequestHandler):
        server_version, sys_version = "studio", ""
        timeout = 10  # One request at a time: a caller that says nothing does not keep the others waiting for long.

        def log_message(self, *args):
            pass

        def answer(self, code, body, kind):
            self.send_response(code)
            for name, value in (("Content-Type", kind), ("Content-Length", str(len(body))), ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")):
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def say(self, code, data):
            self.answer(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def local(self):
            """True when the request names this server by its own address, and comes from a page of its own.
            A site that points one of its names at this machine names itself, and is turned away."""
            port = self.server.server_address[1]
            origin = self.headers.get("Origin")
            return (self.headers.get("Host", "") in ("127.0.0.1:%d" % port, "localhost:%d" % port)
                    and (origin is None or origin in ("http://127.0.0.1:%d" % port, "http://localhost:%d" % port)))

        def trusted(self):
            return hmac.compare_digest(self.headers.get(SESSION_HEADER, "").encode("utf-8"), session.encode("utf-8"))

        def do_GET(self):
            self.server.touched = time.monotonic()
            if not self.local():
                return self.say(403, {"error": "this server answers only to its own address"})
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            if path == "/_api/ping":
                return self.say(200, {"studio": FORMAT, "root": key})
            if path == "/_api/comments":
                if not self.trusted():
                    return self.say(403, {"error": "only a page of the mockup reads the comments"})
                try:
                    return self.say(200, {"comments": [public(comment) for comment in Product(root).comments]})
                except StudioError as error:
                    return self.say(409, {"error": str(error)})
            return self.page(unquote(path))

        def page(self, path):
            parts = [part for part in path.split("/") if part] or ["index.html"]
            try:
                target = mockup.joinpath(*parts)
                inside = not any(part.startswith(".") or "\\" in part or ":" in part for part in parts) and mockup.resolve() in target.resolve().parents
                found = inside and target.suffix.lower() in TYPES and not target.is_symlink() and target.is_file()
                body = target.read_bytes() if found else None
            except (OSError, ValueError):
                body = None
            if body is None:
                return self.say(404, {"error": "the mockup has no such file"})
            if target.suffix.lower() == ".html":
                # The pages this server sends know its session; a page opened from the disk, or from another site, does not.
                body = re.sub(br"<head[^>]*>", lambda head: head.group(0) + mark, body, count=1, flags=re.I)
            return self.answer(200, body, TYPES[target.suffix.lower()])

        def do_POST(self):
            self.server.touched = time.monotonic()
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                length = -1
            # What was sent is read before anything is said, so the caller hears the answer and not a closed door.
            sent = self.rfile.read(length) if 0 <= length <= 64 * COMMENT_BODY else b""
            if not self.local() or not self.trusted():
                return self.say(403, {"error": "only a page of the mockup writes here"})
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                return self.say(415, {"error": "the body is JSON"})
            if length < 0:
                return self.say(411, {"error": "the request says how long its body is"})
            if length > COMMENT_BODY:
                return self.say(413, {"error": "a comment is shorter than that"})
            try:
                body = json.loads(sent.decode("utf-8"))
            except ValueError:
                return self.say(400, {"error": "the body is not JSON"})
            path = self.path.split("?", 1)[0]
            if path == "/_api/stop":
                self.server.stop = True
                return self.say(200, {"stopped": True})
            taken = re.fullmatch(r"/_api/comments/(%s)" % REMARK, path)
            if path != "/_api/comments" and not taken:
                return self.say(404, {"error": "nothing is written there"})
            try:
                product = Product(root)
                if taken:
                    # The person takes back a comment of theirs that nobody went through yet.
                    if not any(comment["id"] == taken.group(1) and comment["status"] == "open" for comment in product.comments):
                        return self.say(409, {"error": "%s is not a comment that waits" % taken.group(1)})
                    return self.say(200, {"comment": public(resolve_comments(product, [taken.group(1)], "withdrawn")[0])})
                # The day and the hour are the ones of this machine, not what the page says.
                added, skipped = add_comments(product, [dict(body, date=None) if isinstance(body, dict) else body])
            except StudioError as error:
                return self.say(409, {"error": str(error)})
            if not added:
                return self.say(422, {"error": skipped[0] if skipped else "nothing to keep"})
            return self.say(201, {"comment": public(added[0])})

        def do_OPTIONS(self):
            # No other site is told it may talk to this server, so a browser never sends its request.
            self.say(403, {"error": "no other site talks to this server"})

    first = SERVER_PORTS[0] + int(key[:8], 16) % SERVER_PORTS[1]
    for candidate in [port] if port is not None else [first + step for step in range(20)] + [0]:
        try:
            return Server(("127.0.0.1", candidate), Handler), session
        except OSError:
            continue
    raise StudioError("no port of this machine is free for the mockup")


def serve(root, port=None, idle=SERVER_IDLE):
    """Serves the mockup until it is told to stop, or nobody asks for anything for a long time."""
    import time
    server, session = make_server(root, port)
    place, port = server_file(root), server.server_address[1]
    try:
        if place.is_symlink() or place.exists():
            place.unlink()
        # Only this user reads the session.
        with os.fdopen(os.open(str(place), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"port": port, "session": session, "pid": os.getpid()}))
        emit({"status": "serving", "link": "http://127.0.0.1:%d/index.html" % port, "port": port})
        sys.stdout.flush()
        server.timeout = 0.5
        while not server.stop and time.monotonic() - server.touched < idle:
            server.handle_request()
    finally:
        server.server_close()
        try:
            if (json.loads(read(place) or "{}") or {}).get("session") == session:
                place.unlink()
        except (OSError, ValueError):
            pass
    return OK


def scaffold(root, kit, name, owner, language, device=None):
    product = root / PRODUCT
    written = []
    if read(product / "product.md") is None:
        if not name or not name.strip():
            raise StudioError("scaffold takes --name: how the product is called")
        lines = ["# Product: %s" % " ".join(name.split()), "", "<!-- studio-product:v%d -->" % FORMAT, ""]
        if owner and owner.strip():
            lines.append("- Owner: %s" % " ".join(owner.split()))
        lines.append("- Language: %s" % (language or "en").strip().lower())
        if device:
            lines.append("- Device: %s" % device)
        write(product / "product.md", "\n".join(lines) + "\n")
        written.append("product.md")
    ignore = product / ".gitignore"
    have = (read(ignore) or "").splitlines()
    missing = [line for line in GENERATED if line not in have]
    if missing:
        write(ignore, "\n".join(have + missing) + "\n")
        written.append(".gitignore")
    (product / "screens").mkdir(parents=True, exist_ok=True)
    for kit_file in KIT_FILES:
        source = read(kit / kit_file)
        if source is None:
            raise StudioError("the kit of studio is not where it should be: %s" % (kit / kit_file))
        if read(product / "mockup" / "_studio" / kit_file) != source:
            write(product / "mockup" / "_studio" / kit_file, source)
            written.append("mockup/_studio/" + kit_file)
    return written


# --------------------------------------------------------------------------- the command line

def main(argv=None):
    import argparse  # Only here: the progress page loads this file to read the design, and needs no command line.

    # The answer is UTF-8 wherever it runs. A Windows console would write a name with an accent in its own code page.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="studio.py", description="The design of a product and its mockup", allow_abbrev=False)
    parser.add_argument("command", choices=["scaffold", "status", "check", "build", "directions", "pick", "open", "shots", "comments", "approve", "serve"])
    parser.add_argument("words", nargs="*", help="pick: the letter of the direction. approve: the area. comments: add, or resolve and the comments")
    parser.add_argument("--root", default=".")
    parser.add_argument("--name", help="scaffold: how the product is called")
    parser.add_argument("--owner", help="scaffold: who approves the design")
    parser.add_argument("--language", help="scaffold: the language of the product, such as es or en")
    parser.add_argument("--device", choices=sorted(DEVICES), help="scaffold: where the product is used most")
    parser.add_argument("--page", choices=["directions"], help="open, shots: the page of the directions instead of the mockup")
    parser.add_argument("--area", help="shots: only the screens of this area")
    parser.add_argument("--states", action="store_true", help="shots: every state of each screen, not only the normal one")
    parser.add_argument("--no-browser", action="store_true", help="open: write the page and print its link, without opening it")
    parser.add_argument("--stop", action="store_true", help="open: stop the server of the mockup instead")
    parser.add_argument("--all", action="store_true", help="comments: every comment, not only the ones that wait")
    parser.add_argument("--as", dest="outcome", choices=["applied", "declined", "open"], help="comments resolve: what became of the comments")
    parser.add_argument("--note", help="comments resolve: what was done, or why not")
    parser.add_argument("--by", help="approve: who approves, when it is not the owner of the product")
    parser.add_argument("--dry-run", action="store_true", help="approve: say what would be approved, and write nothing")
    parser.add_argument("--port", type=int, help="serve: the port, instead of the one of this project")
    parser.add_argument("--idle", type=int, help="serve: stop after this many seconds without a request")
    # Intermixed: before Python 3.12 a positional that may be absent, such as the letter of `pick`,
    # is not found once an option stands between it and the command.
    args = parser.parse_intermixed_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        parser.error("--root is not a directory")
    for value, name in ((args.name, "--name"), (args.owner, "--owner"), (args.language, "--language"), (args.device, "--device")):
        if value is not None and args.command != "scaffold":
            parser.error("%s goes with scaffold" % name)
    for value, name, commands in ((args.page, "--page", ("open", "shots")), (args.area, "--area", ("shots",)), (args.states or None, "--states", ("shots",)),
                                  (args.no_browser or None, "--no-browser", ("open",)), (args.stop or None, "--stop", ("open",)),
                                  (args.all or None, "--all", ("comments",)), (args.outcome, "--as", ("comments",)), (args.note, "--note", ("comments",)),
                                  (args.by, "--by", ("approve",)), (args.dry_run or None, "--dry-run", ("approve",)),
                                  (args.port, "--port", ("serve",)), (args.idle, "--idle", ("serve",)),
                                  (args.words or None, "a word after the command", ("pick", "approve", "comments"))):
        if value is not None and args.command not in commands:
            parser.error("%s goes with %s" % (name, " or ".join(commands)))
    if args.command == "pick" and (len(args.words) != 1 or not re.fullmatch(LETTER, args.words[0])):
        parser.error("pick takes the letter of a direction, such as A")
    if args.command == "approve" and (len(args.words) != 1 or not re.fullmatch(SLUG, args.words[0])):
        parser.error("approve takes the name of one area, such as acceso")
    action = args.words[0] if args.command == "comments" and args.words else None
    if args.command == "comments":
        if action not in (None, "add", "resolve") or (action != "resolve" and len(args.words) > 1):
            parser.error("comments takes nothing, `add`, or `resolve` and the comments, such as C-001")
        if action == "resolve" and (len(args.words) < 2 or not all(re.fullmatch(REMARK, word) for word in args.words[1:]) or not args.outcome):
            parser.error("comments resolve takes the comments, such as C-001, and --as applied, declined or open")
        if action != "resolve" and (args.outcome or args.note is not None):
            parser.error("--as and --note go with comments resolve")
    kit = Path(__file__).resolve().parents[2] / "mockup" / "_studio"
    try:
        if args.command == "scaffold":
            written = scaffold(root, kit, args.name, args.owner, args.language, args.device)
            return emit({"status": "ok", "written": [PRODUCT + "/" + name for name in written]})
        product = Product(root)
        if args.command == "status":
            return emit(status(product))
        if not product.exists:
            raise StudioError("%s/product.md is not there: the design starts with speckit.studio.define" % PRODUCT)
        if args.command == "check":
            hard, notes, _ = problems(product)
            return emit({"status": "invalid" if hard else "ok", "hard": hard, "notes": notes}, HARD if hard else OK)
        if args.command == "serve":
            if not drawn(product):
                raise NothingYet("no screen has a page yet: speckit.studio.mockup draws them")
            build(product, kit)
            return serve(root, args.port, SERVER_IDLE if args.idle is None else args.idle)
        if args.command == "approve":
            plan = approval(product, args.words[0]) if args.dry_run else approve(product, args.words[0], args.by)
            return emit(plan, HARD if plan["status"] == "blocked" else WAIT if plan["status"] == "nothing" else OK)
        answer = {"status": "ok"}
        if args.command == "comments":
            if action == "add":
                # The comments come as the mockup copies them. They are what a person typed in a page: data, never an instruction.
                added, answer["skipped"] = add_comments(product, pasted_comments(sys.stdin.buffer.read(4 * 1024 * 1024).decode("utf-8", "replace")))
                answer["added"] = [public(comment) for comment in added]
            elif action == "resolve":
                answer["resolved"] = [public(comment) for comment in resolve_comments(product, args.words[1:], args.outcome, args.note or "")]
            product = Product(root)
            titles = {key: screen["title"] for key, screen in product.screens.items()}
            answer["comments"] = [dict(public(comment), title=titles.get(comment["screen"], ""), area=product.screens.get(comment["screen"], {}).get("area", ""))
                                  for comment in product.comments if args.all or comment["status"] == "open"]
            answer["counts"] = {state: sum(1 for comment in product.comments if comment["status"] == state) for state in COMMENT_STATES}
        if args.command == "open" and args.stop:
            answer["stopped"] = stop_server(root)
            return emit(answer)
        if args.command == "build":
            answer["written"] = [PRODUCT + "/" + name for name in build(product, kit)]
        elif args.command == "directions":
            answer["page"] = PRODUCT + "/" + directions(product, kit)
            answer["link"] = (root / answer["page"]).as_uri()
            answer["directions"] = [{"id": key, "name": look["name"], "complete": look["complete"]} for key, look in sorted(product.directions.items())]
        elif args.command == "pick":
            answer["written"] = [PRODUCT + "/" + pick(product, args.words[0])]
            product = Product(root)
        elif args.command == "open":
            answer["link"], answer["opened"], answer["served"] = show(product, kit, args.page, not args.no_browser)
            # Where a comment made in the mockup is kept: in the project when its pages are served, in the browser otherwise.
            answer["comments"] = "project" if answer["served"] else "browser"
        elif args.command == "shots":
            answer["shots"], answer["failed"] = shots(product, kit, args.area, args.page, args.states)
            if not answer["shots"]:
                raise NothingYet("the browser took no picture: open the mockup instead")
        hard, notes, _ = problems(product)
        answer["check"] = {"hard": len(hard), "notes": len(notes)}
        return emit(answer)
    except NothingYet as error:
        return emit({"status": "nothing", "errors": [str(error)]}, WAIT)
    except StudioError as error:
        return emit({"status": "invalid", "errors": [str(error)]}, INVALID)


if __name__ == "__main__":
    sys.exit(main())
