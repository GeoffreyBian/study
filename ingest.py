#!/usr/bin/env python3
"""Merge a browser-pulled Canvas assignments dump into tracker.csv.

UBC blocks personal access tokens, but the REST API answers normally to a
logged-in browser session. The skill's browser snippet writes
cache/<course>-assignments.json; this merges it in. Adds what the ICS feed
cannot see: points, submission state, score, and undated assignments.

    python3 ingest.py cache/new-venture-design-assignments.json
"""
import json
import sys
from pathlib import Path

import tracker

OWNS = ("canvas_id", "title", "due", "points", "status", "submitted_at", "score", "url")
# Canvas submission workflow_state -> tracker status. 'unsubmitted' is left
# alone so a locally-set 'in-progress' is not reset on every sync.
STATE = {"graded": "graded", "submitted": "submitted", "pending_review": "submitted",
         "unsubmitted": None}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    payload = json.loads(path.read_text())
    course = payload["course"]
    existing = tracker.load()

    rows = []
    for a in payload["assignments"]:
        sub = a.get("submission") or {}
        row = {
            "course": course,
            "canvas_id": str(a["id"]),
            "title": a["name"],
            "due": (a.get("due_at") or ""),
            "points": "" if a.get("points_possible") is None else str(a["points_possible"]),
            "url": a.get("html_url", ""),
            "submitted_at": sub.get("submitted_at") or "",
            "score": "" if sub.get("score") is None else str(sub["score"]),
        }
        mapped = STATE.get(sub.get("workflow_state"))
        if mapped:
            row["status"] = mapped
        rows.append(row)

    added, changed = tracker.merge(existing, rows, OWNS)
    tracker.save(existing)
    tracker.report(existing, added, changed)


if __name__ == "__main__":
    main()
