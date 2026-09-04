#!/usr/bin/env python3
"""Refuse to publish docs/index.html if it leaks anything it shouldn't.

docs/index.html goes to a world-readable GitHub Pages site. The terms to look
for are derived from courses.json and todos.csv rather than hardcoded, so adding
a course that is not flagged `"public": true` automatically extends the check
instead of quietly widening what gets published.
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
TARGET = ROOT / "docs" / "index.html"


def banned_terms():
    config = json.loads((ROOT / "courses.json").read_text())
    private = {s: m for s, m in config.items() if m.get("public") is not True}

    # Exact-substring terms: names and slugs are distinctive enough.
    words, numbers = set(), set()
    for slug, meta in private.items():
        words.update({slug, meta["name"], meta["code"]})
        words.update(meta.get("staff", []))
        # Canvas ids and enrolment counts are digits — match on word boundaries
        # so a hex colour like #A2661C can't read as the number 266.
        numbers.update(str(c) for c in meta.get("canvas", {}))
        numbers.update(str(n) for n in (meta.get("students") or {}).values())
        total = sum((meta.get("students") or {}).values())
        if total:
            numbers.add(str(total))

    for row in csv.DictReader((ROOT / "todos.csv").open(newline="")):
        if row.get("course") in private or any(
                row.get("course", "").startswith(s + "-") for s in private):
            for field in ("title", "notes"):
                if row.get(field):
                    words.add(row[field])

    # Always secret, regardless of course config.
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("CANVAS_ICS_URL="):
                words.add(line.split("=", 1)[1].strip())
                token = re.search(r"user_([A-Za-z0-9]+)", line)
                if token:
                    words.add(token.group(1))
            if line.startswith("CANVAS_API_TOKEN=") and len(line) > 20:
                words.add(line.split("=", 1)[1].strip())
    words.update({"feeds/calendars", "geoffreybian100"})
    return {w for w in words if w and len(w) > 3}, numbers


def main():
    if not TARGET.exists():
        sys.exit(f"{TARGET} does not exist — run build_dashboard.py --public first")
    html = TARGET.read_text()
    words, numbers = banned_terms()

    hits = [w for w in words if w in html]
    hits += [n for n in numbers if re.search(rf"\b{re.escape(n)}\b", html)]

    if hits:
        print("REFUSING TO PUBLISH — private content found in docs/index.html:", file=sys.stderr)
        for h in sorted(hits):
            print(f"  {h!r}", file=sys.stderr)
        sys.exit(1)
    print(f"  leak scan clean ({len(words)} terms, {len(numbers)} numbers checked)")


if __name__ == "__main__":
    main()
