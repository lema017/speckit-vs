#!/usr/bin/env python3
"""Mutants of the studio script: each one breaks a single check, and the tests must notice.

    .venv/bin/python tests/extensions/studio/mutants.py [name ...]

A mutant is (name, text to find once in studio.py, what to put in its place). The script is copied
with its extension, changed, and the tests run against the copy. "killed" is what every line should
say; "survived" means no test noticed, and "stale" means the text is no longer in the script.
Not collected by pytest.
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
EXT = ROOT / "extensions" / "studio"
TESTS = ROOT / "tests" / "extensions" / "studio"

MUTANTS = [
    # Reading the files.
    ("mark-not-needed", 'if not mark:\n            raise StudioError("%s has no', 'if False:\n            raise StudioError("%s has no'),
    ("newer-format-read", "if int(mark.group(1)) > FORMAT:", "if False:"),
    ("product-any-first-line", 'if not items or items[0]["level"] != 1 or not items[0]["title"].startswith("Product:") or not items[0]["title"][8:].strip():', "if not items:"),
    ("product-level-not-checked", 'if not items or items[0]["level"] != 1 or not items[0]["title"].startswith("Product:")', 'if not items or not items[0]["title"].startswith("Product:")'),
    ("product-empty-name", ' or not items[0]["title"][8:].strip():', ":"),
    ("comment-is-read", 'text = COMMENT.sub(lambda found: "\\n" * found.group(0).count("\\n"), text)', "pass"),
    ("comment-shifts-lines", 'text = COMMENT.sub(lambda found: "\\n" * found.group(0).count("\\n"), text)', 'text = COMMENT.sub("", text)'),
    ("fence-is-read", "heading = None if fenced else HEADING.match(raw)", "heading = HEADING.match(raw)"),
    ("field-twice-kept-quiet", 'current["twice"].append(key)', "pass"),
    ("unknown-field-accepted", "if key not in required and key not in optional:", "if False:"),
    ("missing-field-accepted", 'if not item["fields"].get(key, "").strip():', "if False:"),
    ("bad-id-accepted", "for part in wrong:", "for part in ():"),
    ("defined-twice-accepted", "        if key in store:", "        if False:"),
    ("none-is-an-id", "if not value or value.split(\" \")[0].lower() in NOTHING:", "if not value:"),
    ("link-is-read", "return path.read_text(encoding=\"utf-8\") if path.is_file() and not path.is_symlink() else None", "return path.read_text(encoding=\"utf-8\") if path.is_file() else None"),
    ("link-is-written", "    if path.is_symlink():\n        raise StudioError", "    if False:\n        raise StudioError"),
    # Each kind of file.
    ("actor-any-heading", 'if not key or not title:\n                self.bad("actors.md"', 'if False:\n                self.bad("actors.md"'),
    ("area-any-heading", 'if not key or not title:\n                        self.bad("navigation.md", item["line"], "an area is', 'if False:\n                        self.bad("navigation.md", item["line"], "an area is'),
    ("flow-any-heading", 'if not key or not title:\n                        self.bad("navigation.md", item["line"], "a flow is', 'if False:\n                        self.bad("navigation.md", item["line"], "a flow is'),
    ("flow-step-any-text", '                        else:\n                            self.bad("navigation.md", item["line"], "Steps: %s is not', '                        elif False:\n                            self.bad("navigation.md", item["line"], "Steps: %s is not'),
    ("flow-state-forgotten", 'steps.append([step.group(1), step.group(2) or "normal"])', 'steps.append([step.group(1), "normal"])'),
    ("story-any-heading", 'if not key or not title:\n                self.bad("story-map.md"', 'if False:\n                self.bad("story-map.md"'),
    ("story-interface-ignored", '"no_interface": fields.get("Interface", "").strip().lower().startswith("none"),', '"no_interface": False,'),
    ("screen-any-first-line", 'if not key or not title:\n                self.bad(name, 1, "the first line is `# SCR-<name> <title>`")', 'if False:\n                self.bad(name, 1, "the first line is `# SCR-<name> <title>`")'),
    ("screen-file-name-free", 'if path.name != key + ".md":', "if False:"),
    ("screen-state-any-text", "                if not re.fullmatch(SLUG, state):", "                if False:"),
    ("screen-normal-not-needed", 'if states and "normal" not in states:', "if False:"),
    ("screen-page-any-name", "if page and not re.fullmatch(PAGE, page):", "if False:"),
    ("screen-session-any-word", 'if session not in ("none", "required"):', "if False:"),
    ("screen-section-not-needed", 'if wanted not in sections or not (sections[wanted]["lines"] or sections[wanted]["fields"]):', "if False:"),
    ("screen-element-any-text", '                else:\n                    self.bad(name, number, \'an element is', '                elif False:\n                    self.bad(name, number, \'an element is'),
    ("screen-state-described-freely", "                if state not in states:\n                    self.bad(name, sections[\"States\"][\"line\"]", "                if False:\n                    self.bad(name, sections[\"States\"][\"line\"]"),
    ("screen-session-lost", '"session": session == "required",', '"session": False,'),
    ("screen-entry-lost", '"entry": fields.get("Entry", "").strip().lower() == "yes",', '"entry": True,'),
    ("screen-anyone-is-an-actor", '"seen_by": [] if seen.lower() == "anyone" else', '"seen_by": [] if False else'),
    ("capability-any-heading", "if not re.fullmatch(SLUG, section[\"title\"]):", "if False:"),
    ("rule-any-heading", '                if not key:\n                    self.bad("capability-drafts.md"', '                if False:\n                    self.bad("capability-drafts.md"'),
    ("questions-any-group", 'if scope != "define" and not re.fullmatch(r"map %s" % SLUG, scope):', "if False:"),
    ("question-any-heading", 'if not key or not text:\n                    self.bad("decisions.md"', 'if False:\n                    self.bad("decisions.md"'),
    ("question-any-status", 'if status not in ("asked", "decided", "open"):', "if False:"),
    ("decided-without-answer", 'if status == "decided" and not fields.get("Answer", "").strip():', "if False:"),
    ("open-without-owner", 'if status == "open" and not fields.get("Owner", "").strip():', "if False:"),
    ("question-twice", '                if key in seen:\n                    self.bad("decisions.md"', '                if False:\n                    self.bad("decisions.md"'),
    ("theme-any-first-line", 'if not items or items[0]["level"] != 1:\n            self.bad("look-and-feel.md"', 'if False:\n            self.bad("look-and-feel.md"'),
    ("theme-any-radius", 'if not re.fullmatch(r"[0-9]{1,3}px", theme[key]):', "if False:"),
    ("radius-of-any-length", 'if not re.fullmatch(r"[0-9]{1,3}px", theme[key]):', 'if not re.fullmatch(r"[0-9]+px", theme[key]):'),
    ("radius-of-two-digits-only", 'if not re.fullmatch(r"[0-9]{1,3}px", theme[key]):', 'if not re.fullmatch(r"[0-9]{1,2}px", theme[key]):'),
    ("theme-mode-not-needed", '            if section is None:\n                self.bad(name, head["line"], "the section %s is missing" % mode)', '            if section is None:\n                pass'),
    ("theme-any-color", "                if value and not HEX.match(value):", "                if False:"),
    ("theme-complete-anyway", "                complete = complete and bool(HEX.match(value))", "                pass"),
    # The catalog.
    ("catalog-changes-are-capabilities", '        if spec.parent.name.startswith("_"):\n            continue', '        if False:\n            continue'),
    ("catalog-designed-is-built", '"state": "designed" if rule.group(2) else "implemented"', '"state": "implemented"'),
    ("catalog-built-is-designed", '"state": "designed" if rule.group(2) else "implemented"', '"state": "designed"'),
    # The check.
    ("spec-file-names-allowed", '    for name in ("spec.md", "capability-delta.md"):', "    for name in ():"),
    ("requirement-lines-allowed", 'if re.search(r"^\\s*- \\*\\*FR-\\d+\\*\\*", read(path) or "", re.M):', "if False:"),
    ("unknown-area-accepted", "        if area and area not in product.areas:\n            hard.append", "        if False:\n            hard.append"),
    ("story-unknown-actor-accepted", "            if actor not in product.actors:\n                hard.append(\"%s: %s names the actor", "            if False:\n                hard.append(\"%s: %s names the actor"),
    ("story-without-screen-accepted", 'if not story["no_interface"] and not any(story["id"] in screen["stories"] for screen in product.screens.values()):', "if False:"),
    ("screen-unknown-actor-accepted", "            if actor not in product.actors:\n                hard.append(\"%s: Seen-By names", "            if False:\n                hard.append(\"%s: Seen-By names"),
    ("screen-unknown-story-accepted", "            if story not in product.stories:", "            if False:"),
    ("element-unknown-screen-accepted", '            if element["to"] and target is None:', "            if False:"),
    ("element-unknown-state-accepted", '            elif target and element["state"] and element["state"] not in target["states"]:', "            elif False:"),
    ("state-without-description-accepted", '            if state != "normal" and state not in screen["described"]:', "            if False:"),
    ("shared-page-accepted", '            if screen["file"] in files:', "            if False:"),
    ("unknown-rule-accepted", "        if rule not in product.rules and rule not in catalog:", "        if False:"),
    ("uncited-draft-accepted", '        if rule["id"] not in cited:', "        if False:"),
    ("draft-rewrites-the-catalog", '        if known and known["text"] != rule["text"]:', "        if False:"),
    ("draft-in-catalog-not-noted", "        elif known:\n            notes.append", "        elif False:\n            notes.append"),
    ("flow-of-one-step", '        if len(flow["steps"]) < 2:', "        if False:"),
    ("flow-unknown-screen-accepted", "            if screen not in product.screens:\n                hard.append(\"%s: %s passes through %s, which is not a screen\"", "            if False:\n                hard.append(\"%s: %s passes through %s, which is not a screen\""),
    ("flow-unknown-state-accepted", '            elif state not in product.screens[screen]["states"]:', "            elif False:"),
    # The pages.
    ("page-of-another-screen", '        if page.screen != screen["id"]:', "        if False:"),
    ("page-of-another-area", '        if page.area != screen["area"]:', "        if False:"),
    ("page-loads-what-it-likes", "            if wanted not in page.assets:", "            if False:"),
    ("page-leaves-the-mockup", '            if kind == "outside":', "            if False:"),
    ("scripts-may-leave-the-mockup", "        for link in page.links + page.assets:", "        for link in page.links:"),
    ("protocol-relative-is-inside", 'if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", link) or link.startswith("//"):', 'if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", link):'),
    ("link-to-no-page-accepted", '            elif kind == "page" and target not in files:', "            elif False:"),
    ("query-is-part-of-the-page", '    page = link.split("?", 1)[0].split("#", 1)[0]', "    page = link"),
    ("goto-is-not-a-link", '        if at.get("data-goto"):\n            self.links.append(at["data-goto"])', '        if at.get("data-goto"):\n            pass'),
    ("unknown-ref-accepted", "            if ref not in product.stories and ref not in product.rules and ref not in catalog:", "            if False:"),
    ("unknown-page-state-accepted", '            if state not in screen["states"]:\n                hard.append("%s: data-state uses', '            if False:\n                hard.append("%s: data-state uses'),
    ("screen-rule-not-shown-accepted", "            if rule not in page.refs:", "            if False:"),
    ("entry-not-needed", "        if not entries:", "        if False:"),
    ("unreachable-accepted", "            if entries and key not in reached:", "            if False:"),
    ("dead-end-accepted", "            if not links[key] and len(product.screens) > 1:", "            if False:"),
    ("one-screen-is-a-dead-end", "            if not links[key] and len(product.screens) > 1:", "            if not links[key]:"),
    ("flow-is-no-way", "                if one in links and other != one:\n                    links[one].add(other)", "                if one in links and other != one:\n                    pass"),
    ("no-pages-still-needs-entry", "    if pages:\n        # A flow is also", "    if True:\n        # A flow is also"),
    ("lang-not-noted", "        if not page.lang:", "        if False:"),
    ("h1-not-noted", "        if page.h1 != 1:", "        if False:"),
    ("label-not-noted", "            if not label and (not ident or ident not in page.labels):", "            if False:"),
    ("aria-label-not-a-label", "            if not label and (not ident or ident not in page.labels):", "            if not ident or ident not in page.labels:"),
    ("alt-not-noted", '        elif tag == "img" and "alt" not in at:', "        elif False:"),
    ("button-not-noted", '            if not self._button["text"].strip() and not self._button["label"]:', "            if False:"),
    ("own-styles-not-noted", '        if re.search(r"#[0-9a-fA-F]{3,8}\\b|\\brgba?\\(|\\bhsla?\\(|font-family", page.styles()):', "        if False:"),
    ("style-attribute-not-read", '        if at.get("style"):\n            self._style.append(at["style"])', '        if at.get("style"):\n            pass'),
    ("style-element-not-read", "        if self._in_style:\n            self._style.append(data)", "        if self._in_style:\n            pass"),
    ("contrast-not-noted", "                if ratio < least:", "                if False:"),
    ("contrast-light-only", '        for mode in ("Light", "Dark"):\n            for front, back, least in CONTRAST:', '        for mode in ("Light",):\n            for front, back, least in CONTRAST:'),
    # How far the design is.
    ("asked-does-not-hold-define", 'define = {"state": "done" if not missing and not waiting else "active"', 'define = {"state": "done" if not missing else "active"'),
    ("missing-does-not-hold-define", 'define = {"state": "done" if not missing and not waiting else "active"', 'define = {"state": "done" if not waiting else "active"'),
    ("incomplete-theme-counts", '("look-and-feel.md", bool(product.theme and product.theme.get("complete")))', '("look-and-feel.md", bool(product.theme))'),
    ("decisions-of-every-conversation", 'sum(1 for question in product.questions if question["scope"] == "define" and question["status"] == "decided")', 'sum(1 for question in product.questions if question["status"] == "decided")'),
    ("asked-of-another-area-holds", '        pending = [question for question in asked if question["scope"] == scope]', "        pending = list(asked)"),
    ("story-without-screen-is-mapped", 'mapped = "done" if stories and screens and not orphan and not pending else "active"', 'mapped = "done" if stories and screens and not pending else "active"'),
    ("asked-does-not-hold-the-map", 'mapped = "done" if stories and screens and not orphan and not pending else "active"', 'mapped = "done" if stories and screens and not orphan else "active"'),
    ("half-drawn-is-drawn", 'mock = "pending" if not drawn else "done" if len(drawn) == len(screens) else "active"', 'mock = "pending" if not drawn else "done"'),
    ("nothing-drawn-is-active", 'mock = "pending" if not drawn else "done" if len(drawn) == len(screens) else "active"', 'mock = "done" if len(drawn) == len(screens) else "active"'),
    ("map-before-mockup", "        if undrawn:\n            left =", "        if undrawn and not unmapped:\n            left ="),
    ("open-lists-every-question", 'for question in product.questions if question["status"] == "open"],\n        "check"', 'for question in product.questions],\n        "check"'),
    ("draft-outranks-the-catalog", 'return catalog[rule]["state"] if rule in catalog else "draft" if rule in product.rules else "unknown"', 'return "draft" if rule in product.rules else catalog[rule]["state"] if rule in catalog else "unknown"'),
    ("one-screen-left-is-many", '"has" if left == 1 else "have"', '"have"'),
    ("the-only-screen-is-counted", '"its screen has" if undrawn["screens"] == 1 else ', ""),
    # The files of the mockup.
    ("script-can-be-closed", '.replace("</", "<\\\\/")', ""),
    ("title-not-escaped", "product.language, escape(name), jump, escape(name), link)", "product.language, name, jump, escape(name), link)"),
    ("font-not-used", 'return SYSTEM_FONT if look["font"].lower() == "system" else "%s, %s" % (look["font"], SYSTEM_FONT)', "return SYSTEM_FONT"),
    ("incomplete-theme-written", '    if product.theme and product.theme.get("complete"):\n        write(target / "theme.css"', '    if product.theme:\n        write(target / "theme.css"'),
    ("screen-without-page-listed", 'for screen in product.screens.values() if screen["file"]},\n               "flujos"', 'for screen in product.screens.values()},\n               "flujos"'),
    ("session-on-every-screen", '**({"sesion": True} if screen["session"] else {}))', '**{"sesion": True})'),
    ("index-skips-the-entry", '    first = entry or next((screen for screen in product.screens.values() if screen["file"]), None)', '    first = next((screen for screen in product.screens.values() if screen["file"]), None)'),
    ("example-not-shown", '"nota": draft["example"] if draft else ""}', '"nota": ""}'),
    # Starting a design.
    ("scaffold-without-a-name", "        if not name or not name.strip():\n            raise StudioError", "        if False:\n            raise StudioError"),
    ("scaffold-rewrites-the-product", '    if read(product / "product.md") is None:', "    if True:"),
    ("scaffold-drops-the-ignore-lines", "    missing = [line for line in GENERATED if line not in have]", "    missing = [line for line in GENERATED]\n    have = []"),
    ("scaffold-keeps-an-old-kit", '        if read(product / "mockup" / "_studio" / kit_file) != source:', '        if read(product / "mockup" / "_studio" / kit_file) is None:'),
    ("options-on-any-command", '        if value is not None and args.command != "scaffold":', "        if False:"),
    # What came with the first delivery: the device, the looks to choose from, the steps, opening and pictures.
    ("device-any-word", "        if self.device not in DEVICES:", "        if False:"),
    ("device-lost", '"idioma": product.language, "dispositivo": product.device,\n', '"idioma": product.language, "dispositivo": "desktop",\n'),
    ("scaffold-forgets-the-device", "        if device:\n            lines.append", "        if False:\n            lines.append"),
    ("font-any-text", '        if not re.fullmatch(FONT, theme["font"]):', "        if False:"),
    ("direction-any-heading", '            if not key or not title:\n                self.bad("directions.md"', '            if False:\n                self.bad("directions.md"'),
    ("direction-why-not-needed", 'fields = self.fields("directions.md", item, ("Why",), ("Font", "Radius", "Radius-Control"))', 'fields = self.fields("directions.md", item, (), ("Why", "Font", "Radius", "Radius-Control"))'),
    ("sample-item-without-its-second-part", 'entry + [""] * (2 - len(entry))', "entry"),
    ("pending-link-not-noted", "        if page.pending:\n            notes.append", "        if False:\n            notes.append"),
    ("bare-hash-is-pending", '            if kind == "placeholder" and link.strip() not in ("", "#"):', '            if kind == "placeholder":'),
    ("set-state-not-checked", '        if at.get("data-set-state"):\n            self.states.append(at["data-set-state"].strip())', '        if at.get("data-set-state"):\n            pass'),
    ("direction-contrast-not-checked", 'looks += [("%s, direction %s" % (rel("directions.md", look["line"]), key), look) for key, look in sorted(product.directions.items())]', "looks += []"),
    ("incomplete-look-checked", '        if not look.get("complete"):\n            continue', '        if False:\n            continue'),
    ("half-drawn-area-is-drawn", '"drawn" if mapped == "done" and mock == "done" else "in-design"', '"drawn" if mapped == "done" else "in-design"'),
    ("links-pending-not-counted", '"links_pending": sum(len(pages[key].pending) for key in drawn),', '"links_pending": 0,'),
    ("area-decisions-count-every-question", '"decisions": sum(1 for question in product.questions if question["scope"] == scope and question["status"] == "decided"),',
     '"decisions": sum(1 for question in product.questions if question["scope"] == scope),'),
    ("define-fact-not-started", '    if len(missing) == len(words) and not define["decisions"] and not waiting:', "    if False:"),
    ("define-fact-hides-waiting", '    if waiting:\n        fact += ", %d waiting" % len(waiting)', '    if False:\n        fact += ", %d waiting" % len(waiting)'),
    ("define-fact-hides-missing", "    elif missing:\n        fact +=", "    elif False:\n        fact +="),
    ("map-step-never-pending", '"state": "pending" if not started else "done" if len(described) == len(areas) else "active"', '"state": "done" if len(described) == len(areas) else "active"'),
    ("map-step-done-early", '"state": "pending" if not started else "done" if len(described) == len(areas) else "active"', '"state": "pending" if not started else "done" if described else "active"'),
    ("map-fact-without-areas", '"fact": "%d of %s" % (len(described), count(len(areas), "area")) if areas else "No areas yet"', '"fact": "%d of %s" % (len(described), count(len(areas), "area"))'),
    ("mockup-step-ignores-problems", '"state": "pending" if not pages else "attention" if hard else "done"', '"state": "pending" if not pages else "done"'),
    ("mockup-step-done-early", '"done" if len(pages) == len(product.screens) else "active",\n         "fact"', '"done",\n         "fact"'),
    ("mockup-step-marked-before-it-is-drawn", '"state": "pending" if not pages else "attention" if hard else "done"', '"state": "attention" if hard else "pending" if not pages else "done"'),
    ("mockup-fact-without-screens", ' if product.screens else "No screens yet")', ")"),
    ("mockup-fact-counts-problems-before-it-is-drawn", 'if pages and hard else "")},', 'if hard else "")},'),
    ("asked-about-the-product-not-listed", "    if waiting:\n        attention.append", "    if False:\n        attention.append"),
    ("asked-about-an-area-not-listed", '        if area["asked"]:\n            attention.append', '        if False:\n            attention.append'),
    ("open-not-listed", '        if question["status"] == "open":\n            attention.append', '        if False:\n            attention.append'),
    ("check-not-listed", "    if hard:\n        attention.append", "    if False:\n        attention.append"),
    ("pending-not-listed", '        if area["links_pending"]:\n            attention.append', '        if False:\n            attention.append'),
    ("every-problem-shown", '"details": hard[:5]})', '"details": hard})'),
    ("one-is-many", '"" if number == 1 else "s"', '"s"'),
    ("total-decisions-count-every-question", '"decisions": sum(1 for question in product.questions if question["status"] == "decided")},', '"decisions": len(product.questions)},'),
    ("look-of-an-incomplete-theme", '"look": product.theme["direction"] if product.theme and product.theme.get("complete") else ""', '"look": product.theme["direction"] if product.theme else ""'),
    ("every-document-listed", "[name for name in DOCUMENTS if read(product.dir / name) is not None]", "list(DOCUMENTS)"),
    ("mockup-there-before-it-is-built", '"mockup": bool(pages) and read(product.dir / "mockup" / "index.html") is not None,', '"mockup": bool(pages),'),
    ("idea-takes-headings", '        if line.startswith("#") or (not line and not found):', "        if not line and not found:"),
    ("idea-runs-on", "        if not line:\n            break", "        if not line:\n            continue"),
    ("idea-reads-comments", '    for line in COMMENT.sub("", text).splitlines():\n        line = line.strip()', "    for line in text.splitlines():\n        line = line.strip()"),
    ("entry-is-any-screen", 'if screen["entry"] and screen["file"]), "")}', 'if screen["file"]), "")}'),
    ("incomplete-direction-shown", 'complete = [look for _, look in sorted(product.directions.items()) if look["complete"]]', "complete = [look for _, look in sorted(product.directions.items())]"),
    ("no-direction-is-fine", "    if not complete:\n        raise StudioError", "    if False:\n        raise StudioError"),
    ("chosen-lost", '"elegida": look["id"] == chosen,', '"elegida": False,'),
    ("directions-brings-no-kit", '    write(target / "kit.css", kit_css)\n', "    pass\n"),
    ("sample-lost", '"muestra": product.sample, "direcciones"', '"muestra": {}, "direcciones"'),
    ("dark-has-the-shadow-of-light", '"oscuro": dict(look["Dark"], shadow=SHADOW["Dark"])', '"oscuro": dict(look["Dark"], shadow=SHADOW["Light"])'),
    ("pick-takes-an-incomplete-direction", '    if not look["complete"]:\n        raise StudioError("direction %s is not complete', '    if False:\n        raise StudioError("direction %s is not complete'),
    ("pick-forgets-the-font", '"- Font: %s" % look["font"]', '"- Font: system"'),
    ("pick-forgets-dark", '    for mode in ("Light", "Dark"):\n        lines += ["## %s" % mode', '    for mode in ("Light",):\n        lines += ["## %s" % mode'),
    ("pick-reports-the-old-look", '            answer["written"] = [PRODUCT + "/" + pick(product, args.letter)]\n            product = Product(root)', '            answer["written"] = [PRODUCT + "/" + pick(product, args.letter)]'),
    ("pick-any-letter", '    if args.command == "pick" and not re.fullmatch(LETTER, args.letter or ""):', "    if False:"),
    ("open-with-no-pages", "        if not drawn(product):\n            raise NothingYet(\"no screen has a page yet: speckit.studio.mockup draws them\")\n        build(product, kit)\n        path", "        build(product, kit)\n        path"),
    ("open-does-not-build", '        build(product, kit)\n        path = product.dir / "mockup" / "index.html"', '        path = product.dir / "mockup" / "index.html"'),
    ("open-ignores-no-browser", "    if browser and can_open():", "    if can_open():"),
    ("open-ignores-where-it-runs", "    if browser and can_open():", "    if browser:"),
    ("ci-opens-a-browser", "for name in NO_BROWSER_ENV + (\"CI\",))", "for name in NO_BROWSER_ENV)"),
    ("the-switch-is-ignored", "for name in NO_BROWSER_ENV + (\"CI\",))", "for name in (\"CI\",))"),
    ("zero-means-yes", 'not in ("", "0", "false") for name in NO_BROWSER_ENV', 'not in ("",) for name in NO_BROWSER_ENV'),
    ("ssh-opens-a-browser", '    if env.get("SSH_CONNECTION") or env.get("SSH_CLIENT") or env.get("SSH_TTY"):\n        return False', '    if False:\n        return False'),
    ("ssh-client-opens-a-browser", 'env.get("SSH_CONNECTION") or env.get("SSH_CLIENT") or env.get("SSH_TTY")', 'env.get("SSH_CONNECTION") or env.get("SSH_TTY")'),
    ("no-display-opens-a-browser", '    if platform.startswith("linux") and not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):\n        return False', '    if False:\n        return False'),
    ("wayland-is-no-display", 'not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))', 'not env.get("DISPLAY")'),
    ("a-missing-browser-is-replaced", "    if named:\n        return named if os.path.isfile(named) else None", "    if named and os.path.isfile(named):\n        return named"),
    ("older-picture-kept", "    if target.is_symlink() or target.exists():\n        target.unlink()", "    if False:\n        target.unlink()"),
    ("profile-left-behind", "        shutil.rmtree(profile, ignore_errors=True)", "        pass"),
    ("empty-picture-counts", "    return target.is_file() and target.stat().st_size > 0", "    return target.is_file()"),
    ("shots-without-a-browser-go-on", '    if browser is None:\n        raise NothingYet("no Chrome', '    if False:\n        raise NothingYet("no Chrome'),
    ("shots-of-an-unknown-area", "        if area and area not in product.areas:\n            raise StudioError", "        if False:\n            raise StudioError"),
    ("shots-of-every-area", "        screens = drawn(product, area)", "        screens = drawn(product)"),
    ("shots-do-not-build", "        build(product, kit)\n        for screen in screens:", "        for screen in screens:"),
    ("shots-of-every-state-always", '(screen["states"] if states else ["normal"])', 'screen["states"]'),
    ("shots-without-a-session", '(1 if screen["session"] else 0)', "0"),
    ("shots-as-the-first-person", 'who = next((actor for actor in screen["seen_by"] if actor in product.actors), next(iter(product.actors), ""))', 'who = next(iter(product.actors), "")'),
    ("shots-in-one-size", '"size": DEVICES[product.device]})', '"size": DEVICES["desktop"]})'),
    ("shots-with-the-bar", 'query = "?captura=1&modo=claro&sesion=%d"', 'query = "?modo=claro&sesion=%d"'),
    ("no-picture-is-fine", '            if not answer["shots"]:\n                raise NothingYet', '            if False:\n                raise NothingYet'),
    ("failed-pictures-pass-as-taken", "(taken if done else failed).append(shot)", "taken.append(shot)"),
    ("a-screen-without-a-page-is-drawn", 'if screen["file"] and read(product.dir / "mockup" / screen["file"]) is not None and (area is None', 'if screen["file"] and (area is None'),
    # What a page shows against what its screen names.
    ("named-element-not-looked-for", '            if element["kind"] in NAMED and not page.shows(element["label"]):', "            if False:"),
    ("every-element-looked-for-by-name", '            if element["kind"] in NAMED and not page.shows(element["label"]):', '            if not page.shows(element["label"]):'),
    ("picture-not-noted", '        if page.pictures and not any(element["kind"] == "image" for element in screen["elements"]):', "        if False:"),
    ("picture-noted-though-named", '        if page.pictures and not any(element["kind"] == "image" for element in screen["elements"]):', "        if page.pictures:"),
    ("an-img-is-no-picture", '        if tag == "img" or any(name == "ph" or name.startswith("ph-") for name in (at.get("class") or "").split()):',
     '        if any(name == "ph" or name.startswith("ph-") for name in (at.get("class") or "").split()):'),
    ("a-placeholder-is-no-picture", '        if tag == "img" or any(name == "ph" or name.startswith("ph-") for name in (at.get("class") or "").split()):', '        if tag == "img":'),
    ("a-small-placeholder-is-no-picture", 'name == "ph" or name.startswith("ph-")', 'name == "ph"'),
    ("text-of-a-script-is-on-the-page", "        if not self._hidden:\n            self._words.append(data)", "        if True:\n            self._words.append(data)"),
    ("what-an-attribute-says-is-not-read", '        self._words.extend(at[key] for key in ("aria-label", "placeholder", "alt", "value", "title") if at.get(key))', "        pass"),
    ("a-name-in-other-letters-is-missed", 'return " ".join(label.split()).lower() in " ".join(" ".join(self._words).split()).lower()', 'return " ".join(label.split()) in " ".join(" ".join(self._words).split())'),
    ("a-name-with-other-spacing-is-missed", 'return " ".join(label.split()).lower() in " ".join(" ".join(self._words).split()).lower()', 'return label.lower() in " ".join(" ".join(self._words).split()).lower()'),
    ("new-options-on-any-command", "        if value is not None and args.command not in commands:", "        if False:"),
]


def run_mutant(name, old, new, workdir):
    copy = workdir / name
    shutil.copytree(str(EXT), str(copy), ignore=shutil.ignore_patterns("__pycache__"))
    script = copy / "scripts" / "python" / "studio.py"
    source = script.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        return "stale", "the text to replace occurs %d times" % count
    script.write_text(source.replace(old, new), encoding="utf-8")
    env = dict(os.environ, STUDIO_TEST_SCRIPT=str(script), SPECKIT_STUDIO_NO_BROWSER="1")
    done = subprocess.run([sys.executable, "-m", "pytest", str(TESTS / "test_studio.py"), "--rootdir", str(ROOT), "-x", "-q", "-p", "no:cacheprovider",
                           "-p", "no:xdist", "--tb=no"], cwd=str(ROOT), capture_output=True, encoding="utf-8", errors="replace", env=env)
    failed = sorted(set(re.findall(r"^(?:FAILED|ERROR) \S*?::(\S+)", done.stdout, re.M)))
    shutil.rmtree(str(copy), ignore_errors=True)
    if done.returncode == 0:
        return "survived", ""
    return ("killed", ", ".join(failed[:2])) if failed else ("broken", done.stdout[-300:])


def main():
    from concurrent.futures import ThreadPoolExecutor

    wanted = set(sys.argv[1:])
    names = [name for name, _, _ in MUTANTS]
    unknown = wanted - set(names)
    twice = sorted({name for name in names if names.count(name) > 1})
    if unknown or twice:
        print("unknown mutants: %s; named twice: %s" % (", ".join(sorted(unknown)) or "none", ", ".join(twice) or "none"))
        return 2
    chosen = [mutant for mutant in MUTANTS if not wanted or mutant[0] in wanted]
    left = 0
    with tempfile.TemporaryDirectory(prefix="studio-mutants-") as directory:
        # Each mutant runs the tests one by one, and several mutants run at once.
        with ThreadPoolExecutor(max_workers=int(os.environ.get("STUDIO_MUTANT_JOBS", "6"))) as pool:
            results = pool.map(lambda mutant: run_mutant(mutant[0], mutant[1], mutant[2], Path(directory)), chosen)
            for (name, _, _), (status, detail) in zip(chosen, results):
                left += status != "killed"
                print("%-46s %-9s %s" % (name, status, detail[:150]), flush=True)
    print("%d of %d not killed" % (left, len(chosen)), flush=True)
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
