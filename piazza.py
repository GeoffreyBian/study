#!/usr/bin/env python3
"""Piazza resource ingest — the local half of `piazza_fetch.js`.

The browser snippet drops one zip into ~/Downloads holding every new resource
plus a manifest. This unpacks it into courses/<slug>/, extracts slide text, and
records what has been seen so the next run only fetches what is new.

    python3 piazza.py --known cpen-411     # ids to paste into the snippet
    python3 piazza.py cpen-411             # ingest what the snippet downloaded
    python3 piazza.py cpen-411 --index     # rebuild INDEX.md only

State lives in cache/piazza-<slug>.json. Nothing here talks to Piazza; it never
needs the browser.
"""
import argparse
import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import slidetext

ROOT = Path(__file__).resolve().parent
DOWNLOADS = Path.home() / "Downloads"
COURSES = ROOT / "courses"
CACHE = ROOT / "cache"

# Where each resources-page section lands, and whether its date is a lecture
# date (Piazza's own column heading) or a due date.
SECTIONS = {
    "Lecture Notes": ("lectures", "lecture"),
    "Assignments": ("assignments", "due"),
    "General Resources": ("resources", None),
    "Tutorials": ("tutorials", "lecture"),
    "Exams": ("resources", None),
}
DEFAULT_SECTION = ("resources", None)


def state_path(slug):
    return CACHE / f"piazza-{slug}.json"


def load_state(slug):
    p = state_path(slug)
    return json.loads(p.read_text()) if p.exists() else {"slug": slug, "items": {}}


def save_state(slug, state):
    CACHE.mkdir(exist_ok=True)
    state_path(slug).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def slugify(s):
    s = re.sub(r"\.(pptx|pdf|docx|zip)$", "", s, flags=re.I)
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return re.sub(r"-+", "-", s) or "untitled"


def parse_date(s):
    """'Sep 21, 2026' -> '2026-09-21'. Piazza is inconsistent, so fail soft."""
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return ""


# Aamodt posts each deck twice, and the pdf row's link text is just "... pdf"
# or "_pdf". On its own that slugifies to "pdf" and every one of them collides.
# The manifest is in page order, so the row above it is the deck it belongs to.
COMPANION = re.compile(r"^[.\s_]*pdf$", re.I)


def resolve_titles(items):
    prev = None
    for item in items:
        if COMPANION.match(item["title"]) and prev:
            item["title"] = f"{prev} (pdf)"
        else:
            prev = item["title"]


def ingest(slug, keep_bundle=False):
    bundle = DOWNLOADS / f"piazza__{slug}__bundle.zip"
    if not bundle.exists():
        sys.exit(f"no bundle at {bundle} — run piazza_fetch.js in the browser first")
    zf = zipfile.ZipFile(bundle)
    manifest = json.loads(zf.read("manifest.json"))
    state = load_state(slug)
    course_dir = COURSES / slug
    if not course_dir.exists():
        sys.exit(f"{course_dir} does not exist — add the course to courses.json first")

    added, skipped = [], []
    names = set(zf.namelist())
    resolve_titles(manifest["items"])
    for item in manifest["items"]:
        if item["file"] not in names:
            skipped.append((item["title"], "not in bundle"))
            continue
        folder, date_kind = SECTIONS.get(item.get("section", ""), DEFAULT_SECTION)
        date = parse_date(item.get("date", ""))
        ext = item["file"].rsplit(".", 1)[-1]
        # Lecture material is filed by the date it was taught, which is what
        # makes "what did we cover last class" answerable from the filenames.
        stem = f"{date}-{slugify(item['title'])}" if (date and date_kind == "lecture") else slugify(item["title"])
        dest_dir = course_dir / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{stem}.{ext}"
        if dest.exists():
            dest = dest_dir / f"{stem}-{item['rid'][-6:]}.{ext}"
        dest.write_bytes(zf.read(item["file"]))

        text_rel = ""
        if ext in ("pptx", "pdf"):
            try:
                text = slidetext.extract(dest)
                dest.with_suffix(".txt").write_text(text)
                text_rel = str(dest.with_suffix(".txt").relative_to(ROOT))
            except Exception as e:  # a pdf without pypdf, a malformed zip
                skipped.append((item["title"], f"filed, no text: {e}"))

        state["items"][item["rid"]] = {
            "title": item["title"],
            "section": item.get("section", ""),
            "date": date,
            "date_kind": date_kind,
            "path": str(dest.relative_to(ROOT)),
            "text": text_rel,
            "bytes": item.get("bytes"),
            "fetched": manifest.get("fetched", ""),
        }
        added.append(item["title"])

    save_state(slug, state)
    zf.close()
    if not keep_bundle:
        bundle.unlink()
    write_index(slug, state)
    for t in added:
        print(f"  + {t}")
    for t, why in skipped:
        print(f"  ! {t}: {why}")
    print(f"{len(added)} filed, {len(state['items'])} known for {slug}")


def write_index(slug, state=None):
    state = state or load_state(slug)
    items = sorted(
        state["items"].values(),
        key=lambda i: (i.get("date") or "0000", i["title"]),
        reverse=True,
    )
    lines = [f"# {slug} — Piazza resources", ""]
    for section in ("Lecture Notes", "Assignments", "Tutorials", "General Resources"):
        rows = [i for i in items if i.get("section") == section]
        if not rows:
            continue
        lines += [f"## {section}", ""]
        for i in rows:
            date = i.get("date") or "?"
            label = "taught" if i.get("date_kind") == "lecture" else ("due" if i.get("date_kind") == "due" else "")
            text = f" · [text]({Path(i['text']).name})" if i.get("text") else ""
            lines.append(f"- **{date}** {label} — [{i['title']}]({Path(i['path']).name}){text}")
        lines.append("")
    other = [i for i in items if i.get("section") not in
             ("Lecture Notes", "Assignments", "Tutorials", "General Resources")]
    if other:
        lines += ["## Other", ""] + [f"- {i['title']}" for i in other] + [""]
    out = COURSES / slug / "PIAZZA.md"
    out.write_text("\n".join(lines))
    print(f"wrote {out.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--known", action="store_true", help="print the KNOWN array for piazza_fetch.js")
    ap.add_argument("--index", action="store_true", help="rebuild PIAZZA.md from state only")
    ap.add_argument("--keep-bundle", action="store_true", help="do not delete the zip after ingest")
    a = ap.parse_args()
    if a.known:
        print(json.dumps(sorted(load_state(a.slug)["items"])))
    elif a.index:
        write_index(a.slug)
    else:
        ingest(a.slug, a.keep_bundle)


if __name__ == "__main__":
    main()
