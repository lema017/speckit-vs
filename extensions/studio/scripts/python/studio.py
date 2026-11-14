#!/usr/bin/env python3
"""Product Studio: the design of a product, kept as files, and the mockup built from them.

    studio.py scaffold --name NAME [--owner WHO] [--language es] [--device phone]
    studio.py status
    studio.py check
    studio.py build
    studio.py directions            the page that shows the looks of directions.md side by side
    studio.py pick LETTER           make one direction the look of the product
    studio.py open [--page directions] [--no-browser]
    studio.py shots [--area AREA] [--page directions] [--states]

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
BROWSER_ENV = "SPECKIT_STUDIO_BROWSER"
SHOT_SECONDS = 60
# Wide and tall enough for three looks side by side, each with its two sample screens.
DIRECTIONS_SIZE = (1440, 1560)
# What the person can open and read, in the order the design is made.
DOCUMENTS = ("vision.md", "actors.md", "navigation.md", "story-map.md", "capability-drafts.md", "decisions.md", "look-and-feel.md")

ACTOR = r"ACT-[a-z0-9]+(?:-[a-z0-9]+)*"
STORY = r"ST-[0-9]+"
SCREEN = r"SCR-[a-z0-9]+(?:-[a-z0-9]+)*"
FLOW = r"FL-[0-9]+"
RULE = r"R-[a-z0-9]+(?:-[a-z0-9]+)*"
SLUG = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
QUESTION = r"Q-[0-9]+"
LETTER = r"[A-Z]"
FONT = r"[A-Za-z0-9 ,'\"_-]{1,120}"
PAGE = r"[a-z0-9][a-z0-9-]*\.html"
HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\Z")

HEADING = re.compile(r"^(#{1,3}) (.+?)\s*$")
FIELD = re.compile(r"^- ([A-Za-z][A-Za-z-]*): ?(.*?)\s*$")
ELEMENT = re.compile(r'^- ([a-z][a-z-]*) "(.+?)"(?: -> (%s)(?:/(%s))?)?(?:: (.+))?$' % (SCREEN, SLUG))
COMMENT = re.compile(r"<!--.*?-->", re.S)
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
        if known and known["text"] != rule["text"]:
            hard.append("%s: %s is in the catalog with another text; a draft does not rewrite an approved rule" % (where, rule["id"]))
        elif known:
            notes.append("%s: %s is already in the catalog with this text; the draft can go" % (where, rule["id"]))

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
    """A rule the catalog has is past its draft, whatever capability-drafts.md still holds."""
    return catalog[rule]["state"] if rule in catalog else "draft" if rule in product.rules else "unknown"


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
        rules = sorted({rule for owner in stories + screens for rule in owner["rules"]})
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
        areas.append({
            "id": area["id"], "title": area["title"], "covers": area["covers"], "stories": len(stories), "screens": len(screens), "pages": len(drawn),
            "rules": counts, "asked": len(pending),
            "open": sum(1 for question in product.questions if question["scope"] == scope and question["status"] == "open"),
            "decisions": sum(1 for question in product.questions if question["scope"] == scope and question["status"] == "decided"),
            "links_pending": sum(len(pages[key].pending) for key in drawn),
            "steps": {"map": mapped, "mockup": mock},
            "state": "not-started" if mapped == "pending" else "drawn" if mapped == "done" and mock == "done" else "in-design",
        })
    if define["state"] != "done":
        step = {"command": "speckit.studio.define", "args": "", "why": "The product still lacks: %s." % ", ".join(missing) if missing
                else "%d questions of the first conversation wait for an answer." % len(waiting)}
    else:
        unmapped = next((area for area in areas if area["steps"]["map"] != "done"), None)
        undrawn = next((area for area in areas if area["steps"]["map"] == "done" and area["steps"]["mockup"] != "done"), None)
        if undrawn:
            left = undrawn["screens"] - undrawn["pages"]
            step = {"command": "speckit.studio.mockup", "args": "", "why": "%s is described and %s no page yet." % (
                undrawn["title"], "its screen has" if undrawn["screens"] == 1 else "%d of its %d screens %s" % (left, undrawn["screens"], "has" if left == 1 else "have"))}
        elif unmapped:
            step = {"command": "speckit.studio.map", "args": unmapped["id"], "why": "%s is %s." % (
                unmapped["title"], "not described yet" if unmapped["steps"]["map"] == "pending" else "half described")}
        else:
            step = {"command": "speckit.studio.mockup", "args": "", "why": "Every area is drawn. Open the mockup and say what to change."}

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
    attention = []
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
        "define": define, "areas": areas, "steps": steps, "attention": attention,
        "totals": {"areas": len(areas), "not_started": sum(1 for area in areas if area["state"] == "not-started"),
                   "in_design": sum(1 for area in areas if area["state"] == "in-design"), "drawn": sum(1 for area in areas if area["state"] == "drawn"),
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
    rules = {}
    for rule in sorted({rule for owner in list(product.stories.values()) + list(product.screens.values()) for rule in owner["rules"]} | set(product.rules)):
        draft, known = product.rules.get(rule), catalog.get(rule)
        if draft or known:
            rules[rule] = {"capacidad": (draft or known)["capability"], "texto": (draft or known)["text"], "estado": rule_state(product, catalog, rule),
                           "nota": draft["example"] if draft else ""}
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


def show(product, kit, page=None, browser=True):
    """Writes what is to be seen and opens it. Returns (its link, whether a browser opened it)."""
    if page == "directions":
        path = product.dir / directions(product, kit)
    else:
        if not drawn(product):
            raise NothingYet("no screen has a page yet: speckit.studio.mockup draws them")
        build(product, kit)
        path = product.dir / "mockup" / "index.html"
    link = path.resolve().as_uri()
    opened = False
    if browser and can_open():
        import webbrowser
        try:
            opened = bool(webbrowser.open(link))
        except webbrowser.Error:
            opened = False
    return link, opened


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

    parser = argparse.ArgumentParser(prog="studio.py", description="The design of a product and its mockup", allow_abbrev=False)
    parser.add_argument("command", choices=["scaffold", "status", "check", "build", "directions", "pick", "open", "shots"])
    parser.add_argument("letter", nargs="?", help="pick: the letter of the direction")
    parser.add_argument("--root", default=".")
    parser.add_argument("--name", help="scaffold: how the product is called")
    parser.add_argument("--owner", help="scaffold: who approves the design")
    parser.add_argument("--language", help="scaffold: the language of the product, such as es or en")
    parser.add_argument("--device", choices=sorted(DEVICES), help="scaffold: where the product is used most")
    parser.add_argument("--page", choices=["directions"], help="open, shots: the page of the directions instead of the mockup")
    parser.add_argument("--area", help="shots: only the screens of this area")
    parser.add_argument("--states", action="store_true", help="shots: every state of each screen, not only the normal one")
    parser.add_argument("--no-browser", action="store_true", help="open: write the page and print its link, without opening it")
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
                                  (args.no_browser or None, "--no-browser", ("open",)), (args.letter, "a letter", ("pick",))):
        if value is not None and args.command not in commands:
            parser.error("%s goes with %s" % (name, " or ".join(commands)))
    if args.command == "pick" and not re.fullmatch(LETTER, args.letter or ""):
        parser.error("pick takes the letter of a direction, such as A")
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
        answer = {"status": "ok"}
        if args.command == "build":
            answer["written"] = [PRODUCT + "/" + name for name in build(product, kit)]
        elif args.command == "directions":
            answer["page"] = PRODUCT + "/" + directions(product, kit)
            answer["link"] = (root / answer["page"]).as_uri()
            answer["directions"] = [{"id": key, "name": look["name"], "complete": look["complete"]} for key, look in sorted(product.directions.items())]
        elif args.command == "pick":
            answer["written"] = [PRODUCT + "/" + pick(product, args.letter)]
            product = Product(root)
        elif args.command == "open":
            answer["link"], answer["opened"] = show(product, kit, args.page, not args.no_browser)
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
