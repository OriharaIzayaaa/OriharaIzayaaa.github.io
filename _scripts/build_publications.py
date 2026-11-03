#!/usr/bin/env python3
"""Turn the .bib files in _bibliography into Markdown lists for the website.

references.bib (Zotero export) gives _includes/publications.md and preprints.md.
A preprint is hidden when a published article has the same short title (or, if
there is no short title, the same title).

activities.bib (edited by hand) gives talks.md, posters.md, data.md and
awards.md. Talks and posters are limited to the last CONFERENCE_YEARS calendar
years, counted from the build date. Only the Python standard library is needed.
"""
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIB_FILE = ROOT / "_bibliography" / "references.bib"
ACTIVITIES_FILE = ROOT / "_bibliography" / "activities.bib"
OUTPUT_DIR = ROOT / "_includes"
HIGHLIGHT_AUTHOR = ("Anders", "Gerrit")  # (family name, given name) shown in bold
PUBLISHED_TYPES = {"article", "inproceedings", "incollection", "inbook", "book"}
PREPRINT_TYPES = {"online", "unpublished", "misc", "report"}
CONFERENCE_YEARS = 4
MONTHS = ("January February March April May June July August September "
          "October November December").split()


def read_braced(text, start):
    """Return the text inside the braces opening at start, and the end index."""
    depth, i = 0, start
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
        i += 1
    raise ValueError(f"Unbalanced braces near: {text[start:start + 60]!r}")


def parse_bib(text):
    entries = []
    for match in re.finditer(r"^\s*@(\w+)\s*(?=\{)", text, re.M):
        kind = match.group(1).lower()
        if kind in {"comment", "preamble", "string"}:
            continue
        body, _ = read_braced(text, match.end())
        key, _, rest = body.partition(",")
        fields, i = {}, 0
        while True:
            field = re.compile(r"\s*,?\s*([\w-]+)\s*=\s*").match(rest, i)
            if not field:
                break
            i = field.end()
            if i < len(rest) and rest[i] == "{":
                value, i = read_braced(rest, i)
            else:
                bare = re.compile(r'"[^"]*"|[^,\s]+').match(rest, i)
                value, i = bare.group(0).strip('"'), bare.end()
            fields[field.group(1).lower()] = value
        entries.append({"type": kind, "key": key.strip(), **fields})
    return entries


def clean(value):
    """Remove BibTeX braces and escapes, and make text safe for Markdown."""
    value = value.replace(r"\textasciitilde", "~")
    value = re.sub(r"\\([&%_$#{}])", r"\1", value)
    value = value.replace("{", "").replace("}", "").replace("--", "–")
    value = re.sub(r"\s+", " ", value).strip()
    return re.sub(r"([\\*_\[\]|<>`])", r"\\\1", value)


def plain_key(value):
    return re.sub(r"\W+", " ", value.replace("{", "").replace("}", "")).strip().casefold()


def initials(given):
    parts = []
    for name in given.split():
        hyphenated = [piece[0].upper() + "." for piece in name.split("-") if piece]
        parts.append("-".join(hyphenated))
    return " ".join(parts)


def format_authors(raw):
    authors = []
    for person in re.split(r"\s+and\s+", raw):
        family, _, given = person.partition(",")
        family, given = family.strip(), given.strip()
        text = clean(f"{family}, {initials(given)}" if given else family)
        if (family, given) == HIGHLIGHT_AUTHOR:
            text = f"**{text}**"
        authors.append(text)
    if len(authors) == 1:
        return authors[0]
    return ", ".join(authors[:-1]) + ", & " + authors[-1]


def link(entry):
    if entry.get("doi"):
        return f"https://doi.org/{entry['doi']}"
    return entry.get("url", "")


def venue(entry):
    if entry["type"] in PREPRINT_TYPES:
        return clean(entry.get("eprinttype") or "Preprint")
    name = clean(entry.get("journaltitle") or entry.get("booktitle") or entry.get("publisher", ""))
    text = f"*{name}*" if name else ""
    if entry.get("volume"):
        text += f", *{clean(entry['volume'])}*"
        if entry.get("number"):
            text += f"({clean(entry['number'])})"
    if entry.get("pages"):
        text += f", {clean(entry['pages'])}"
    return text


def format_entry(entry):
    year = entry.get("date", "n.d.")[:4]
    title = clean(entry.get("title", "Untitled"))
    target = link(entry)
    title_text = f"[{title}]({target})" if target else title
    return f"- {format_authors(entry.get('author', ''))} ({year}). {title_text}. {venue(entry)}.\n"


def event_date(value):
    """Format 2025-07-30/2025-08-02 as: 2025, July 30–August 2."""
    start, _, end = value.partition("/")
    year, month, day = start.split("-")
    text = f"{year}, {MONTHS[int(month) - 1]} {int(day)}"
    if end:
        _, end_month, end_day = end.split("-")
        if end_month != month:
            text += f"–{MONTHS[int(end_month) - 1]} {int(end_day)}"
        else:
            text += f"–{int(end_day)}"
    return text


def format_activity(entry):
    title = clean(entry.get("title", "Untitled"))
    target = link(entry)
    title_text = f"[{title}]({target})" if target else title
    when = event_date(entry["eventdate"]) if entry.get("eventdate") else entry.get("date", "n.d.")[:4]
    parts = [title_text] + [clean(entry[f]) for f in ("symposium", "eventtitle", "venue") if entry.get(f)]
    details = " ".join(part if part[-1] in ".?!" else part + "." for part in parts)
    return f"- {format_authors(entry.get('author', ''))} ({when}). {details}\n"


def build_activities(this_year):
    entries = parse_bib(ACTIVITIES_FILE.read_text(encoding="utf-8"))
    first_year = this_year - CONFERENCE_YEARS + 1
    sections = {"talk": "talks.md", "poster": "posters.md", "dataset": "data.md", "award": "awards.md"}
    start = lambda e: e.get("eventdate") or e.get("date", "")
    unknown = [e["key"] for e in entries if e["type"] not in sections]
    for kind, name in sections.items():
        items = [e for e in entries if e["type"] == kind]
        if kind in {"talk", "poster"}:
            items = [e for e in items if int(start(e)[:4]) >= first_year]
        lines = [format_activity(e) for e in sorted(items, key=start, reverse=True)]
        (OUTPUT_DIR / name).write_text("".join(lines), encoding="utf-8")
        print(f"{name}: {len(items)}")
    if unknown:
        print("Skipped (unknown entry type): " + ", ".join(unknown))


def main():
    entries = parse_bib(BIB_FILE.read_text(encoding="utf-8"))
    if not entries:
        sys.exit(f"No entries found in {BIB_FILE}")
    published = [e for e in entries if e["type"] in PUBLISHED_TYPES]
    preprints = [e for e in entries if e["type"] in PREPRINT_TYPES]
    other = [e["key"] for e in entries if e["type"] not in PUBLISHED_TYPES | PREPRINT_TYPES]

    name_of = lambda e: plain_key(e.get("shorttitle") or e.get("title", ""))
    published_names = {name_of(e) for e in published}
    hidden = [e for e in preprints if name_of(e) in published_names]
    visible = [e for e in preprints if name_of(e) not in published_names]

    newest_first = lambda e: e.get("date", "")
    OUTPUT_DIR.mkdir(exist_ok=True)
    for name, items in (("publications.md", published), ("preprints.md", visible)):
        lines = [format_entry(e) for e in sorted(items, key=newest_first, reverse=True)]
        (OUTPUT_DIR / name).write_text("".join(lines), encoding="utf-8")

    print(f"Publications: {len(published)}")
    print(f"Preprints shown: {len(visible)}")
    print("Preprints hidden: " + (", ".join(e["key"] for e in hidden) or "none"))
    if other:
        print("Skipped (unknown entry type): " + ", ".join(other))
    build_activities(date.today().year)


if __name__ == "__main__":
    main()
