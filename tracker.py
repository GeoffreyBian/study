#!/usr/bin/env python3
"""Shared tracker.csv read/merge, used by both sync paths.

The two Canvas sources disagree on identifiers, which is the whole reason this
module exists. The ICS feed's UID is an *assignment override* id
(event-assignment-override-520069) while the REST API returns the *assignment*
id (2527221). Keying rows on canvas_id therefore duplicates every item. Rows are
keyed on (course, normalized title) instead; canvas_id is carried, not trusted.
"""
import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
TRACKER = ROOT / "tracker.csv"
# Canvas stores due times in UTC; he reads them in Pacific. NOT
# "America/Vancouver": that zone file (and its Canada/Pacific alias) is broken
# on this machine — it stops observing DST and reports MST for future dates,
# which silently pushed every winter deadline an hour late. America/Los_Angeles
# carries identical rules and is correct. The check below fails the import
# rather than let a bad tzdata quietly reintroduce the off-by-an-hour.
PACIFIC = ZoneInfo("America/Los_Angeles")

# What counts as closed, shared so due.py, build_dashboard.py and ticks.py
# cannot drift apart on the question.
DONE_TRACKER = {"submitted", "graded", "excused", "dropped"}
DONE_TODO = {"done", "submitted", "dropped"}

_winter = datetime(2027, 1, 24, 7, 59, tzinfo=timezone.utc).astimezone(PACIFIC)
if (_winter.month, _winter.day, _winter.hour) != (1, 23, 23):
    raise RuntimeError(
        f"timezone data is wrong: 2027-01-24T07:59Z should be Jan 23 23:59 PST, got {_winter}")

COLUMNS = ["course", "canvas_id", "title", "type", "due", "points",
           "status", "submitted_at", "score", "url", "notes"]
CLOSED = {"submitted", "graded", "excused", "dropped"}


def clean_title(raw):
    """Strip the decorations each source adds.

    ICS:  'Idea Pitch - Section 001 (APSC_V 496E E_001 2026W1) [New Venture ...]'
    API:  'Idea Pitch - Section 001'
    both -> 'Idea Pitch'
    """
    t = re.sub(r"\s*\[[^\]]*\]\s*$", "", raw).strip()
    # Only drop a trailing parenthetical that is a course/term code. A bare
    # "(Lab 1)" is part of the assignment name and must survive.
    t = re.sub(r"\s*\([^)]*\b20\d{2}[WST]\d?\b[^)]*\)\s*$", "", t).strip()
    t = re.sub(r"\s*[-–]\s*Section\s+\d+\s*$", "", t, flags=re.I).strip()
    return t


def key(course, title):
    return (course, re.sub(r"\s+", " ", clean_title(title)).lower())


def load():
    if not TRACKER.exists():
        return {}
    with TRACKER.open(newline="") as f:
        return {key(r["course"], r["title"]): r for r in csv.DictReader(f)}


def save(rows):
    with TRACKER.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in sorted(rows.values(), key=lambda r: (r.get("due") or "9999", r["title"])):
            w.writerow({c: r.get(c, "") for c in COLUMNS})


def merge(existing, incoming, owns):
    """Apply `incoming` rows, letting the caller own only `owns` fields.

    Anything outside `owns` is preserved from the local row — that is what keeps
    hand-set status ('in-progress') and notes from being clobbered by a sync.
    Returns (added, changed) titles for reporting.
    """
    added, changed = [], []
    for row in incoming:
        k = key(row["course"], row["title"])
        row = {f: v for f, v in row.items() if f in owns or f == "course"}
        row["title"] = clean_title(row["title"])
        cur = existing.get(k)
        if cur is None:
            existing[k] = {**{c: "" for c in COLUMNS}, "status": "unsubmitted", **row}
            added.append(row["title"])
        else:
            diff = [f for f, v in row.items() if (cur.get(f) or "") != (v or "")]
            if diff:
                changed.append(f"{row['title']}: {', '.join(sorted(diff))}")
            cur.update(row)
    return added, changed


def report(existing, added, changed, extra=()):
    print(f"{len(existing)} items in tracker.csv")
    if added:
        print(f"  new ({len(added)}): " + "; ".join(added))
    if changed:
        print(f"  changed ({len(changed)}): " + "; ".join(changed))
    if not added and not changed:
        print("  no changes")
    for line in extra:
        print(f"  ! {line}")
