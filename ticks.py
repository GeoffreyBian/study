#!/usr/bin/env python3
"""Fold dashboard ticks back into the CSVs, so a checked box stays checked.

The board is served from two places. As a Claude artifact it has a real
database and ticks are readable server-side; as a static page on GitHub Pages
there is no backend and a tick only reaches that browser's localStorage. Either
way the tick is invisible to `due.py`, the briefing and every other browser
until it lands in the CSVs — which is what this does.

    ./ticks.py --ids a,b,c          # mark these dashboard ids done
    ./ticks.py --json ticks.json    # {"<id>": true, ...} as the page stores it
    ./ticks.py --list               # show what is currently marked done
    ./ticks.py --ids x --undo       # put one back

`tracker.py` preserves hand-set status across a Canvas sync, so a tick applied
here survives the next refresh rather than being clobbered by it.
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
TRACKER = ROOT / "tracker.csv"
TODOS = ROOT / "todos.csv"
ARCHIVE = ROOT / "todos_done.csv"

# What each file calls "done". tracker.csv mirrors Canvas vocabulary; todos.csv
# is ours. due.py treats the tracker set as closed and skips those rows.
TRACKER_DONE = "submitted"
TODO_DONE = "done"


def slug(s):
    """Must match build_dashboard.slug exactly, or no id will ever line up."""
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:70]


def read(path):
    if not path.exists():
        return [], []
    with path.open(newline="") as f:
        r = csv.DictReader(f)
        return list(r), list(r.fieldnames or [])


def write(path, rows, cols):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in cols})


def row_id(row):
    return slug(f"{row.get('course', '')}-{row.get('title', '')}")


def apply(ids, undo=False):
    hit, miss = [], set(ids)
    for path, done_val, open_val in ((TRACKER, TRACKER_DONE, "unsubmitted"),
                                     (TODOS, TODO_DONE, "open")):
        rows, cols = read(path)
        if not rows:
            continue
        changed = 0
        for row in rows:
            rid = row_id(row)
            if rid not in miss and rid not in ids:
                continue
            want = open_val if undo else done_val
            if row.get("status", "") != want:
                row["status"] = want
                changed += 1
            hit.append((path.name, rid, row.get("title", "")[:58]))
            miss.discard(rid)
        if changed:
            write(path, rows, cols)
            print(f"{path.name}: {changed} row(s) -> "
                  f"{open_val if undo else done_val}")
    for rid in sorted(miss):
        print(f"  no row matches id: {rid}", file=sys.stderr)
    return hit, miss


def retire():
    """Move finished todos out of the working list into todos_done.csv.

    A todo is a thing to do next, so a completed one is clutter on the board
    rather than a record. Tracker rows are left alone: those mirror Canvas and
    the closed ones still carry points and a grade worth keeping in place.
    """
    rows, cols = read(TODOS)
    if not rows:
        return 0
    done = [r for r in rows
            if (r.get("status") or "").strip().lower() in
            {"done", "submitted", "dropped"}]
    if not done:
        print("todos.csv: nothing to retire")
        return 0
    keep = [r for r in rows if r not in done]

    old, acols = read(ARCHIVE)
    acols = acols or cols + ["retired"]
    if "retired" not in acols:
        acols = acols + ["retired"]
    stamp = datetime.now().date().isoformat()
    for r in done:
        r["retired"] = stamp
    write(ARCHIVE, old + done, acols)
    write(TODOS, keep, cols)
    print(f"todos.csv: retired {len(done)} -> {ARCHIVE.name}, {len(keep)} still open")
    for r in done:
        print(f"    {(r.get('title') or '')[:64]}")
    return len(done)


def show():
    for path, done_val in ((TRACKER, TRACKER_DONE), (TODOS, TODO_DONE)):
        rows, _ = read(path)
        marked = [r for r in rows
                  if (r.get("status") or "").strip().lower()
                  in {"submitted", "graded", "excused", "dropped", "done"}]
        print(f"\n{path.name}: {len(marked)} of {len(rows)} marked done")
        for r in marked:
            print(f"  [{r.get('status'):<10}] {r.get('course',''):<20} "
                  f"{(r.get('title') or '')[:56]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", help="comma-separated dashboard ids")
    ap.add_argument("--json", help="a file of {id: bool} as the page stores it")
    ap.add_argument("--undo", action="store_true", help="reopen instead of closing")
    ap.add_argument("--list", action="store_true", help="show what is marked done")
    ap.add_argument("--retire", action="store_true",
                    help="move finished todos into todos_done.csv")
    a = ap.parse_args()

    if a.list:
        show()
        return

    if a.retire and not (a.ids or a.json):
        retire()
        return

    ids = set()
    if a.ids:
        ids |= {i.strip() for i in a.ids.split(",") if i.strip()}
    if a.json:
        blob = json.loads(Path(a.json).read_text())
        ids |= {k for k, v in blob.items() if v} if not a.undo else set(blob)
    if not ids:
        sys.exit("give --ids or --json (or --list)")

    hit, miss = apply(ids, a.undo)
    print(f"\nmatched {len(hit)}, unmatched {len(miss)}")
    if a.retire:
        print()
        retire()
    if hit:
        print("Rebuild and republish so the page ships with these already done:")
        print("  ~/dev/school/publish.sh")


if __name__ == "__main__":
    main()
