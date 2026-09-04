#!/usr/bin/env python3
"""What's due, from tracker.csv. No network — run this before answering anything
about deadlines rather than eyeballing the CSV."""
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tracker as _t

TRACKER = Path(__file__).parent / "tracker.csv"
DONE = {"submitted", "graded", "excused", "dropped"}


def parse_due(raw):
    """Canvas hands back ISO 8601 (2026-09-14T23:59:00Z). Bare dates mean end of day."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        if len(raw) == 10:
            return datetime.fromisoformat(raw).replace(hour=23, minute=59, tzinfo=timezone.utc)
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def load():
    if not TRACKER.exists():
        sys.exit(f"no tracker at {TRACKER} — sync from Canvas first")
    with TRACKER.open(newline="") as f:
        return list(csv.DictReader(f))


def _positive(raw):
    try:
        return float(raw) > 0
    except (TypeError, ValueError):
        return False


def human(delta):
    days = delta.days
    if days < 0:
        return f"{-days}d overdue"
    if days == 0:
        hours = delta.seconds // 3600
        return f"in {hours}h" if hours else "due now"
    return f"in {days}d"


def main():
    horizon = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=horizon)

    overdue, upcoming, undated = [], [], []
    for row in load():
        if row.get("status", "").strip().lower() in DONE:
            continue
        due = parse_due(row.get("due"))
        if due is None:
            undated.append(row)
        elif due < now:
            overdue.append((due, row))
        elif due <= cutoff:
            upcoming.append((due, row))

    def show(label, items):
        if not items:
            return
        print(f"\n{label}")
        for due, row in sorted(items, key=lambda pair: pair[0]):
            when = due.astimezone(_t.PACIFIC).strftime("%a %b %d %H:%M")
            pts = f" [{row['points']}pt]" if _positive(row.get("points")) else ""
            print(f"  {when}  ({human(due - now):>11})  {row['course']}: {row['title']}"
                  f"  <{row.get('type','')}>{pts}")

    show("OVERDUE", overdue)
    show(f"NEXT {horizon} DAYS", upcoming)
    if undated:
        print("\nNO DUE DATE")
        for row in undated:
            print(f"  {row['course']}: {row['title']}  <{row.get('type','')}>")
    if not (overdue or upcoming or undated):
        print(f"Nothing open in the next {horizon} days.")


if __name__ == "__main__":
    main()
