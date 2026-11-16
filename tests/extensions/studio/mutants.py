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
    ("draft-outranks-the-catalog", 'return known["state"] if known else "draft" if draft else "unknown"', 'return "draft" if draft else known["state"] if known else "unknown"'),
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
    ("example-not-shown", '"nota": draft["example"] if draft else examples.get(rule, "")}', '"nota": examples.get(rule, "")}'),
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
    ("half-drawn-area-is-drawn", '"in-design" if mapped != "done" or mock != "done" else', '"in-design" if mapped != "done" else'),
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
    ("pick-reports-the-old-look", '            answer["written"] = [PRODUCT + "/" + pick(product, args.words[0])]\n            product = Product(root)',
     '            answer["written"] = [PRODUCT + "/" + pick(product, args.words[0])]'),
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
    ("answer-in-the-code-page-of-the-console", '        sys.stdout.reconfigure(encoding="utf-8")', "        pass"),
    ("new-options-on-any-command", "        if value is not None and args.command not in commands:", "        if False:"),
    # Comments: what the file holds.
    ("comment-any-heading", '            if not re.fullmatch(REMARK, key):\n                self.bad(COMMENTS, item["line"], "a comment is', '            if False:\n                self.bad(COMMENTS, item["line"], "a comment is'),
    ("comment-any-status", "            if status not in COMMENT_STATES:", "            if False:"),
    ("comment-screen-any-text", '            if not re.fullmatch(SCREEN, fields.get("Screen", "").strip()):', "            if False:"),
    ("comment-with-no-words-read", '            if not text:\n                self.bad(COMMENTS', '            if False:\n                self.bad(COMMENTS'),
    ("declined-without-a-reason-read", '            if status == "declined" and not fields.get("Note", "").strip():', "            if False:"),
    ("comment-defined-twice", '            if key in seen:\n                self.bad(COMMENTS, item["line"], "comment %s is defined twice" % key)',
     '            if False:\n                self.bad(COMMENTS, item["line"], "comment %s is defined twice" % key)'),
    # Comments: what a person typed is cut to what a field takes.
    ("control-characters-kept", "if char.isprintable())", "if True)"),
    ("a-field-keeps-its-line-breaks", '"".join(char for char in " ".join(str(value if value is not None else "").split()) if', '"".join(char for char in str(value if value is not None else "") if'),
    ("a-field-opens-a-comment-of-markdown", '    return text.replace("<!--", "<! --")[:limit].strip()', "    return text[:limit].strip()"),
    ("a-field-of-any-length", '    return text.replace("<!--", "<! --")[:limit].strip()', '    return text.replace("<!--", "<! --").strip()'),
    ("words-of-any-length", '    return "\\n".join(lines).strip("\\n")[:limit].rstrip()', '    return "\\n".join(lines).strip("\\n").rstrip()'),
    ("state-of-a-comment-any-text", '"state": state if re.fullmatch(SLUG, state) else "normal"', '"state": state or "normal"'),
    ("person-of-a-comment-any-text", '"person": person if re.fullmatch(ACTOR, person) else ""', '"person": person'),
    ("path-of-a-comment-any-text", '"path": path if re.fullmatch(r"[a-z0-9:()> -]*", path) else ""', '"path": path'),
    ("refs-of-a-comment-any-text", 'if re.fullmatch("%s|%s" % (STORY, RULE), part)]\n    return {"screen": screen', 'if part]\n    return {"screen": screen'),
    ("date-of-a-comment-any-text", '"date": date if re.fullmatch(r"\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}", date) else stamp', '"date": date or stamp'),
    ("comment-on-an-unknown-screen", '    if screen not in product.screens:\n        return None, "%s is not a screen of the product"', '    if False:\n        return None, "%s is not a screen of the product"'),
    ("comment-that-says-nothing", '    if not text:\n        return None, "the comment on %s says nothing" % screen', '    if False:\n        return None, "the comment on %s says nothing" % screen'),
    ("comment-that-is-no-object", '    if not isinstance(entry, dict):\n        return None, "a comment is an object', '    if False:\n        return None, "a comment is an object'),
    ("comment-kept-twice", '        if key in known:\n            skipped.append("the comment on %s is already kept', '        if False:\n            skipped.append("the comment on %s is already kept'),
    ("comment-taken-back-counts-as-kept", 'for comment in comments if comment["status"] != "withdrawn"}', "for comment in comments}"),
    ("number-of-a-comment-used-twice", '    number = max([int(comment["id"][2:]) for comment in comments] or [0])', "    number = len(comments)"),
    ("unreadable-comments-rewritten", '    if wrong:\n        raise StudioError("%s cannot be read as it is written', '    if False:\n        raise StudioError("%s cannot be read as it is written'),
    ("resolve-an-unknown-comment", "    if not keys or unknown:", "    if not keys:"),
    ("declined-without-a-reason", '    if state == "declined" and not note:\n        raise StudioError("a declined comment says why: --note")', '    if False:\n        raise StudioError("a declined comment says why: --note")'),
    ("note-kept-as-typed", "    note = one_line(note, 400)", "    note = note"),
    ("resolve-changes-every-comment", '    changed = [comment for comment in comments if comment["id"] in keys]', "    changed = comments"),
    ("a-pasted-quote-hides-the-next-comment", '    text = re.sub(r"(?m)^\\s*>.*$", lambda line: line.group(0).replace("<!--", "<! --"), text)', "    pass"),
    ("comments-lists-the-ones-gone-through", 'for comment in product.comments if args.all or comment["status"] == "open"]', "for comment in product.comments]"),
    ("all-lists-only-the-ones-that-wait", 'for comment in product.comments if args.all or comment["status"] == "open"]', 'for comment in product.comments if comment["status"] == "open"]'),
    ("comment-on-a-gone-screen-not-noted", '        if comment["status"] == "open" and comment["screen"] not in product.screens:', "        if False:"),
    ("closed-comment-on-a-gone-screen-noted", '        if comment["status"] == "open" and comment["screen"] not in product.screens:', '        if comment["screen"] not in product.screens:'),
    # Comments in the status.
    ("open-question-not-warned", "    if undecided:\n        warnings.append", "    if False:\n        warnings.append"),
    ("open-question-of-another-area-warned", 'if question["scope"] == "map " + area and question["status"] == "open"]', 'if question["status"] == "open"]'),
    ("asked-question-warned-as-open", 'if question["scope"] == "map " + area and question["status"] == "open"]', 'if question["scope"] == "map " + area]'),
    ("one-open-question-are", '"is" if len(undecided) == 1 else "are"', '"are"'),
    ("last-approver-not-said", '        "last_by": last_approver(product.root),', '        "last_by": None,'),
    ("last-approver-is-the-first", "    return max(found)[3] if found else None", "    return min(found)[3] if found else None"),
    ("last-approver-by-the-name-of-the-folder", "found.append((match.group(2), len(path.parent.name), path.parent.name, one_line(match.group(1))))", "found.append((path.parent.name, len(path.parent.name), path.parent.name, one_line(match.group(1))))"),
    ("last-approver-as-it-was-typed", "found.append((match.group(2), len(path.parent.name), path.parent.name, one_line(match.group(1))))", "found.append((match.group(2), len(path.parent.name), path.parent.name, match.group(1)))"),
    ("last-approver-reads-every-line", "                found.append((match.group(2), len(path.parent.name), path.parent.name, one_line(match.group(1))))\n                break", "                found.append((match.group(2), len(path.parent.name), path.parent.name, one_line(match.group(1))))"),
    ("comments-do-not-come-next", '        elif waiting_all:\n            step = {"command": "speckit.studio.iterate"', '        elif False:\n            step = {"command": "speckit.studio.iterate"'),
    ("iterate-step-never-needs-attention", '"state": "attention" if waiting_all else "done" if reviewed else "pending", "fact": fact})', '"state": "done" if reviewed else "pending", "fact": fact})'),
    ("iterate-step-done-with-nothing-gone-through", '"state": "attention" if waiting_all else "done" if reviewed else "pending", "fact": fact})', '"state": "attention" if waiting_all else "done", "fact": fact})'),
    ("comments-not-in-attention", '    if waiting_all:\n        attention.append({"kind": "comments"', '    if False:\n        attention.append({"kind": "comments"'),
    ("area-counts-comments-gone-through", 'waiting_comments = sum(1 for comment in said if comment["status"] == "open")', "waiting_comments = len(said)"),
    ("area-counts-comments-of-other-areas", 'said = [comment for comment in product.comments if comment["screen"] in product.screens and product.screens[comment["screen"]]["area"] == area["id"]]',
     "said = list(product.comments)"),
    ("comments-gone-through-do-not-settle-an-area", 'settled = (approve == "done" and mock == "done") or len(said) > waiting_comments', 'settled = approve == "done" and mock == "done"'),
    ("approval-does-not-settle-an-area", 'settled = (approve == "done" and mock == "done") or len(said) > waiting_comments', "settled = len(said) > waiting_comments"),
    # How far the approval of a rule and of an area is.
    ("changed-draft-of-an-approved-rule-is-not-a-change", '    if known and draft and known["state"] == "designed" and draft["text"] != known["text"]:\n        return "proposed"', '    if False:\n        return "proposed"'),
    ("draft-proposes-a-change-to-a-built-rule", 'if known and draft and known["state"] == "designed" and draft["text"] != known["text"]:', 'if known and draft and draft["text"] != known["text"]:'),
    ("a-draft-left-behind-is-fine", "    if any(rule in product.rules and rule in catalog for rule in rules):\n        return \"attention\"", "    if False:\n        return \"attention\""),
    ("approved-when-some-rules-are-drafts", '    return "done" if approved == len(states) else "active" if approved else "pending"', '    return "done" if approved else "pending"'),
    ("half-approved-is-not-started", '    return "done" if approved == len(states) else "active" if approved else "pending"', '    return "done" if approved == len(states) else "pending"'),
    ("area-with-no-rule-approved-before-it-is-drawn", 'unready = mapped == "pending" or (not rules and (mapped != "done" or mock != "done"))', 'unready = mapped == "pending"'),
    ("approved-area-is-still-drawn", '"approved" if approve == "done" else "drawn",', '"drawn",'),
    ("changed-rule-does-not-come-next", '        elif changed:\n            step = {"command": "speckit.studio.approve", "args": changed["id"]', '        elif False:\n            step = {"command": "speckit.studio.approve", "args": changed["id"]'),
    ("area-to-approve-does-not-come-next", "        elif unapproved:", "        elif False:"),
    ("slices-do-not-come-next", '        elif designed:\n            step = {"command": "speckit.capabilities.slice"', '        elif False:\n            step = {"command": "speckit.capabilities.slice"'),
    ("approve-step-never-needs-attention", '"state": "attention" if any(area["steps"]["approve"] == "attention" for area in areas)\n                           else "done" if', '"state": "done" if'),
    ("approval-that-waits-not-in-attention", '        if area["steps"]["approve"] == "attention":\n            proposed = area["rules"].get("proposed", 0)', '        if False:\n            proposed = area["rules"].get("proposed", 0)'),
    # What a draft may say of a rule the catalog has.
    ("rule-moved-to-another-capability", '        if known and known["capability"] != rule["capability"]:\n            hard.append', '        if False:\n            hard.append'),
    ("built-rule-rewritten-by-a-draft", '        elif known and known["text"] != rule["text"] and known["state"] != "designed":\n            hard.append', '        elif False:\n            hard.append'),
    ("change-to-an-approved-rule-refused", '        elif known and known["text"] != rule["text"] and known["state"] != "designed":', '        elif known and known["text"] != rule["text"]:'),
    # The mockup and the approved rules.
    ("approved-rule-loses-its-example", '"nota": draft["example"] if draft else examples.get(rule, "")}', '"nota": draft["example"] if draft else ""}'),
    ("proposed-rule-hides-what-was-approved", '            if state == "proposed":\n                rules[rule]["antes"] = known["text"]', '            if False:\n                rules[rule]["antes"] = known["text"]'),
    ("examples-read-outside-their-section", '                inside = line.strip() == "## Examples"', "                inside = True"),
    ("examples-of-the-first-approval-win", '    for path in sorted(base.glob("*/" + RECORD)) if base.is_dir() else []:\n        inside = False', '    for path in sorted(base.glob("*/" + RECORD), reverse=True) if base.is_dir() else []:\n        inside = False'),
    # Approving.
    ("approve-an-area-that-is-not-there", '    if area not in product.areas:\n        raise StudioError("the area %s is not in navigation.md; the areas are', '    if False:\n        raise StudioError("the area %s is not in navigation.md; the areas are'),
    ("approve-without-the-catalog", "    if read(product.root / CAPABILITIES_SCRIPT) is None:\n        blockers.append", "    if False:\n        blockers.append"),
    ("approve-over-what-the-check-finds", '    if hard:\n        blockers.append("the check finds', '    if False:\n        blockers.append("the check finds'),
    ("approve-over-a-question-that-waits", "    if asked:\n        blockers.append", "    if False:\n        blockers.append"),
    ("a-question-of-another-area-blocks", 'if question["scope"] == "map " + area and question["status"] == "asked"]', 'if question["status"] == "asked"]'),
    ("comments-that-wait-not-warned", "    if waiting:\n        warnings.append", "    if False:\n        warnings.append"),
    ("screens-not-drawn-not-warned", "    if undrawn:\n        warnings.append", "    if False:\n        warnings.append"),
    ("rule-already-approved-published-again", '        if known and known["text"] == draft["text"]:\n            leftover.append(key)\n            continue', '        if False:\n            leftover.append(key)\n            continue'),
    ("rule-of-another-area-approved", 'owners = [owner for owner in list(product.stories.values()) + list(product.screens.values()) if owner["area"] == area]',
     "owners = [owner for owner in list(product.stories.values()) + list(product.screens.values())]"),
    ("also-in-names-the-area-itself", 'if key in owner["rules"] and owner["area"] != area)', 'if key in owner["rules"])'),
    ("capability-always-new", '"new": read(product.root / CATALOG / draft["capability"] / "spec.md") is None, "rules": []})', '"new": True, "rules": []})'),
    ("change-published-as-a-new-rule", '"from": known["text"] if known else None,', '"from": None,'),
    ("nothing-to-approve-is-ready", '"status": "blocked" if blockers else "ready" if groups or leftover else "nothing",', '"status": "blocked" if blockers else "ready",'),
    ("drafts-left-behind-are-nothing", '"status": "blocked" if blockers else "ready" if groups or leftover else "nothing",', '"status": "blocked" if blockers else "ready" if groups else "nothing",'),
    ("a-blocked-approval-goes-on", '    if plan["status"] != "ready":\n        return plan', '    if plan["status"] == "nothing":\n        return plan'),
    ("approve-for-nobody", '    if not who:\n        raise StudioError("say who approves', '    if False:\n        raise StudioError("say who approves'),
    ("the-owner-wins-over-who-approves", "    who = one_line(by) or one_line(product.owner)", "    who = one_line(product.owner) or one_line(by)"),
    ("drafts-stay-after-approval", '    write(drafts, without_rules(read(drafts) or "", set(published)))', "    pass"),
    ("drafts-left-behind-stay", '    published = [rule["id"] for group in plan["capabilities"] for rule in group["rules"]] + plan["leftover"]',
     '    published = [rule["id"] for group in plan["capabilities"] for rule in group["rules"]]'),
    ("record-without-who-approved", '"Approved by: %s on %s" % (who, day.isoformat())', '"Approved"'),
    ("record-without-examples", '    lines += ["- %s: %s" % (rule["id"], rule["example"]) for group in plan["capabilities"] for rule in group["rules"]]', "    pass"),
    ("new-capability-not-declared", '        if group["new"]:\n            lines += ["", "### NEW-CAPABILITY %s"', '        if False:\n            lines += ["", "### NEW-CAPABILITY %s"'),
    ("published-record-rewritten", '        if not folder.exists() or not published or read(folder / RECORD) == text:', "        if True:"),
    ("unpublished-record-left-aside", '        if not folder.exists() or not published or read(folder / RECORD) == text:', '        if not folder.exists() or read(folder / RECORD) == text:'),
    ("same-record-gets-another-place", '        if not folder.exists() or not published or read(folder / RECORD) == text:', "        if not folder.exists() or not published:"),
    ("what-the-catalog-answers-is-not-read", '    if done.returncode != 0 or not isinstance(answer, dict) or answer.get("status") not in ("published", "unchanged"):', "    if False:"),
    ("catalog-exit-code-not-read", '    if done.returncode != 0 or not isinstance(answer, dict) or answer.get("status") not in ("published", "unchanged"):',
     '    if not isinstance(answer, dict) or answer.get("status") not in ("published", "unchanged"):'),
    ("catalog-answer-not-read", '    if done.returncode != 0 or not isinstance(answer, dict) or answer.get("status") not in ("published", "unchanged"):', "    if done.returncode != 0:"),
    ("capability-with-no-rule-stays-in-the-drafts", '        if below and all(child["line"] in gone for child in below):', "        if False:"),
    ("every-rule-leaves-the-drafts", 'if item["level"] == 3 and split_title(item["title"], RULE)[0] in rules:', 'if item["level"] == 3:'),
    ("dry-run-approves", 'plan = approval(product, args.words[0]) if args.dry_run else approve(product, args.words[0], args.by)', "plan = approve(product, args.words[0], args.by)"),
    ("blocked-approval-exits-fine", 'HARD if plan["status"] == "blocked" else WAIT if plan["status"] == "nothing" else OK)', 'WAIT if plan["status"] == "nothing" else OK)'),
    ("nothing-to-approve-exits-fine", 'HARD if plan["status"] == "blocked" else WAIT if plan["status"] == "nothing" else OK)', 'HARD if plan["status"] == "blocked" else OK)'),
    # The server of the mockup.
    ("server-answers-to-any-name", 'return (self.headers.get("Host", "") in ("127.0.0.1:%d" % port, "localhost:%d" % port)\n', "return (True\n"),
    ("server-answers-to-any-origin", 'and (origin is None or origin in ("http://127.0.0.1:%d" % port, "http://localhost:%d" % port)))', "and True)"),
    ("pages-shown-to-another-site", '            if not self.local():\n                return self.say(403, {"error": "this server answers only to its own address"})',
     '            if False:\n                return self.say(403, {"error": "this server answers only to its own address"})'),
    ("comments-read-without-the-session", '                if not self.trusted():\n                    return self.say(403, {"error": "only a page of the mockup reads the comments"})',
     '                if False:\n                    return self.say(403, {"error": "only a page of the mockup reads the comments"})'),
    ("comments-written-without-the-session", "            if not self.local() or not self.trusted():", "            if not self.local():"),
    ("comments-written-from-another-site", "            if not self.local() or not self.trusted():", "            if not self.trusted():"),
    ("any-session-is-trusted", '            return hmac.compare_digest(self.headers.get(SESSION_HEADER, "").encode("utf-8"), session.encode("utf-8"))', '            return bool(self.headers.get(SESSION_HEADER, ""))'),
    ("a-form-is-taken-for-a-comment", '            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":', "            if False:"),
    ("a-long-body-is-taken", "            if length > COMMENT_BODY:", "            if False:"),
    ("hidden-files-served", 'inside = not any(part.startswith(".") or "\\\\" in part or ":" in part for part in parts) and mockup.resolve() in target.resolve().parents', "inside = mockup.resolve() in target.resolve().parents"),
    ("files-outside-the-mockup-served", 'inside = not any(part.startswith(".") or "\\\\" in part or ":" in part for part in parts) and mockup.resolve() in target.resolve().parents',
     'inside = not any(part.startswith(".") or "\\\\" in part or ":" in part for part in parts)'),
    ("links-followed", "not target.is_symlink() and target.is_file()\n                body = ", "target.is_file()\n                body = "),
    ("pages-do-not-know-the-session", '                body = re.sub(br"<head[^>]*>", lambda head: head.group(0) + mark, body, count=1, flags=re.I)', "                pass"),
    ("the-hour-of-the-page-is-kept", "dict(body, date=None) if isinstance(body, dict) else body", "body"),
    ("a-comment-gone-through-is-taken-back", 'if not any(comment["id"] == taken.group(1) and comment["status"] == "open" for comment in product.comments):', 'if not any(comment["id"] == taken.group(1) for comment in product.comments):'),
    ("written-anywhere-under-the-api", '            if path != "/_api/comments" and not taken:\n                return self.say(404', '            if False:\n                return self.say(404'),
    ("server-never-stops-by-itself", "        while not server.stop and time.monotonic() - server.touched < idle:", "        while not server.stop:"),
    ("stop-is-not-heard", "        while not server.stop and time.monotonic() - server.touched < idle:", "        while time.monotonic() - server.touched < idle:"),
    ("a-slow-start-counts-as-time-without-a-request", "        server.touched = time.monotonic()\n        while not server.stop", "        while not server.stop"),
    ("state-file-left-behind", '            if (json.loads(read(place) or "{}") or {}).get("session") == session:\n                place.unlink()', '            if False:\n                place.unlink()'),
    ("anyone-reads-the-session", "os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)", "os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)"),
    ("serve-does-not-build", "            build(product, kit)\n            return serve(root", "            return serve(root"),
    ("serve-with-nothing-drawn", '        if args.command == "serve":\n            if not drawn(product):', '        if args.command == "serve":\n            if False:'),
    ("server-of-another-project-trusted", '    return state if answer and answer.get("root") == root_key(root) else None', "    return state if answer else None"),
    ("state-file-of-any-shape", '    if not isinstance(state, dict) or not isinstance(state.get("port"), int) or not isinstance(state.get("session"), str):\n        return None', '    if not isinstance(state, dict):\n        return None'),
    ("server-started-though-not-asked", '        if page != "directions" and can_serve():', '        if page != "directions":'),
    ("the-looks-are-served", '        if page != "directions" and can_serve():', "        if can_serve():"),
    ("a-running-server-is-ignored", "state = server_state(product.root) or start_server(product.root)", "state = start_server(product.root)"),
    ("no-server-is-not-heard", '    return env.get(NO_SERVER_ENV, "").strip().lower() in ("", "0", "false")', "    return True"),
    ("comments-always-said-to-be-in-the-project", 'answer["comments"] = "project" if answer["served"] else "browser"', 'answer["comments"] = "project"'),
    ("stop-opens-the-mockup", '        if args.command == "open" and args.stop:\n            answer["stopped"] = stop_server(root)\n            return emit(answer)', '        if False:\n            answer["stopped"] = stop_server(root)\n            return emit(answer)'),
    # The command line of comments and approval.
    ("approve-takes-any-words", '    if args.command == "approve" and (len(args.words) != 1 or not re.fullmatch(SLUG, args.words[0])):\n        parser.error', '    if False:\n        parser.error'),
    ("pick-takes-any-words", '    if args.command == "pick" and (len(args.words) != 1 or not re.fullmatch(LETTER, args.words[0])):\n        parser.error', '    if False:\n        parser.error'),
    ("comments-takes-any-action", '        if action not in (None, "add", "resolve") or (action != "resolve" and len(args.words) > 1):\n            parser.error', '        if False:\n            parser.error'),
    ("resolve-without-what-became-of-them", '        if action == "resolve" and (len(args.words) < 2 or not all(re.fullmatch(REMARK, word) for word in args.words[1:]) or not args.outcome):\n            parser.error',
     '        if False:\n            parser.error'),
    ("as-goes-with-any-action", '        if action != "resolve" and (args.outcome or args.note is not None):\n            parser.error', '        if False:\n            parser.error'),
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
