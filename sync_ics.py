#!/usr/bin/env python3
"""Canvas -> tracker.csv over the public ICS feed. No auth, no browser.

UBC has disabled student personal access tokens, so there is no API key to sync
with. The calendar feed needs no authentication at all and carries every dated
assignment, which is enough to drive deadlines and reminders. Fields it cannot
see (points, submission status, score) are left for ingest.py to fill.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

import tracker

ROOT = Path(__file__).parent
COURSE_MAP = ROOT / "courses.json"
OWNS = ("title", "type", "due")


def feed_url():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("CANVAS_ICS_URL="):
                return line.split("=", 1)[1].strip()
    sys.exit("set CANVAS_ICS_URL in ~/dev/school/.env "
             "(Canvas > Calendar > Calendar Feed, swap .atom for .ics)")


def unescape(v):
    return (v.replace("\\n", "\n").replace("\\,", ",")
             .replace("\\;", ";").replace("\\\\", "\\"))


def parse_events(ics):
    # RFC 5545 folds long lines by starting continuations with a space or tab.
    events, cur = [], None
    for line in re.sub(r"\r?\n[ \t]", "", ics).splitlines():
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, value = line.split(":", 1)
            name = key.split(";", 1)[0]
            cur.setdefault(name, unescape(value))
            if name == "DTSTART":
                cur["_all_day"] = "VALUE=DATE" in key
    return events


def to_iso(raw, all_day):
    """20260909T010000Z -> 2026-09-09T01:00:00Z; 20261113 -> 2026-11-13."""
    raw = raw.strip()
    if all_day or len(raw) == 8:
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    m = re.match(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z?", raw)
    return f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}Z" if m else raw


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]


def load_course_map():
    """courses.json is keyed by local slug; the sync needs canvas id -> slug.

    A multi-section course gets one tracker slug per section (cpen-221-a,
    cpen-221-b). Sections of the same course reuse assignment names, so a shared
    slug would collide them into a single row and lose a section's grading queue.
    """
    if not COURSE_MAP.exists():
        return {}
    config = json.loads(COURSE_MAP.read_text())
    out = {}
    for slug, meta in config.items():
        canvas = meta.get("canvas", {})
        for cid, section in canvas.items():
            out[str(cid)] = f"{slug}-{section.lower()}" if section and len(canvas) > 1 else slug
    return out


def label_for(due):
    """'2026-09-15T19:30:00Z' -> 'Sep 15', in his timezone, not UTC."""
    from datetime import datetime, timezone
    if "T" in due:
        dt = datetime.strptime(due, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        dt = dt.astimezone(tracker.PACIFIC)
    else:
        dt = datetime.strptime(due, "%Y-%m-%d")
    return f"{dt:%b} {dt.day}"


def disambiguate(rows):
    """Keep same-named events on the same course from collapsing into one row.

    The feed names every CPEN 416 quiz 'CPEN 416 Quiz', so ten separate dates
    hash to one key and each sync overwrites the last. Rows are keyed on
    course + title, so repeated titles get their date appended. Titles that
    appear once are left exactly as they are.
    """
    from collections import Counter
    seen = Counter(tracker.key(r["course"], r["title"]) for r in rows)
    for r in rows:
        if seen[tracker.key(r["course"], r["title"])] > 1 and r.get("due"):
            r["title"] = f'{tracker.clean_title(r["title"])} ({label_for(r["due"])})'
    return rows


def main():
    ics = urllib.request.urlopen(feed_url(), timeout=30).read().decode("utf-8")
    course_map = load_course_map()
    existing = tracker.load()
    unknown, rows = set(), []

    for ev in parse_events(ics):
        if "SUMMARY" not in ev or "DTSTART" not in ev:
            continue
        cid = re.search(r"course_(\d+)", ev.get("URL", ""))
        cid = cid.group(1) if cid else ""
        if cid in course_map:
            course = course_map[cid]
        else:
            m = re.search(r"\[([^\]]*)\]\s*$", ev["SUMMARY"])
            course = slugify(m.group(1)) if m else f"course-{cid}"
            unknown.add(f"course {cid} not in courses.json, filed as '{course}'")

        rows.append({
            "course": course,
            "title": ev["SUMMARY"],
            "type": "exam" if re.search(r"quiz|exam|midterm|final", ev["SUMMARY"], re.I)
                    else "assignment",
            "due": to_iso(ev["DTSTART"], ev.get("_all_day", False)),
        })

    rows = disambiguate(rows)

    # The API is more precise than the feed: it gives a real timestamp where an
    # all-day VEVENT gives only a date. Once ingest.py has stamped a row with a
    # canvas_id, leave its due date alone, or the two syncs overwrite each
    # other forever and neither converges.
    for row in rows:
        cur = existing.get(tracker.key(row["course"], row["title"]))
        if cur and cur.get("canvas_id"):
            row.pop("due", None)

    added, changed = tracker.merge(existing, rows, OWNS)
    tracker.save(existing)
    tracker.report(existing, added, changed, sorted(unknown))


if __name__ == "__main__":
    main()
