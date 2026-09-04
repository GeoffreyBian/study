#!/usr/bin/env python3
"""tracker.csv + todos.csv + courses.json + cache/ -> dashboard.html

Never hand-edit dashboard.html; it is regenerated every build. Edit
dashboard.template.html. The build fails loudly if a {{token}} goes unfilled.
"""
import argparse
import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tracker

ROOT = Path(__file__).parent
TEMPLATE = ROOT / "dashboard.template.html"
OUT = ROOT / "dashboard.html"
PUBLIC_OUT = ROOT / "docs" / "index.html"
LOCAL = tracker.PACIFIC
CLOSED = {"submitted", "graded", "excused", "dropped"}


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def parse_due(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        if len(raw) == 10:
            return datetime.fromisoformat(raw).replace(hour=23, minute=59, tzinfo=timezone.utc)
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:70]


def local_parts(dt):
    """Canvas stores UTC; he reads Pacific. 2026-09-09T01:00Z is Sep 8, 6pm."""
    if dt is None:
        return {"iso": "", "label": "No due date", "day": "", "time": ""}
    d = dt.astimezone(LOCAL)
    return {"iso": d.isoformat(), "label": d.strftime("%a %b %-d"),
            "day": d.strftime("%b %-d"), "time": d.strftime("%-I:%M %p").lower()}


def build(public=False, out=None):
    """public=True drops every course not flagged `"public": true` in
    courses.json. That build is served from a world-readable GitHub Pages site,
    so the flag is opt-in per course and never inferred from the role."""
    out = out or (PUBLIC_OUT if public else OUT)
    now = datetime.now(timezone.utc)
    config = json.loads((ROOT / "courses.json").read_text())
    if public:
        config = {s: m for s, m in config.items() if m.get("public") is True}
        if not config:
            raise SystemExit("no courses flagged public — refusing to build an empty public page")
    tracker = read_csv(ROOT / "tracker.csv")
    todos = read_csv(ROOT / "todos.csv")

    # tracker course slugs are per-section (cpen-221-a); group them back.
    def parent(course):
        for s in config:
            if course == s or course.startswith(s + "-"):
                return s
        return course

    tracker = [r for r in tracker if parent(r["course"]) in config]
    todos = [r for r in todos if parent(r.get("course", "")) in config]

    items = []
    for r in tracker:
        due = parse_due(r.get("due"))
        status = (r.get("status") or "").strip().lower()
        days = (due - now).days if due else None
        items.append({
            "id": slug(f"{r['course']}-{r['title']}"),
            "course": parent(r["course"]), "title": r["title"],
            "type": r.get("type", "assignment"),
            "points": r.get("points", ""), "url": r.get("url", ""),
            "status": status, "open": status not in CLOSED,
            "days": days, "overdue": bool(due and due < now and status not in CLOSED),
            **local_parts(due),
        })
    items.sort(key=lambda i: i["iso"] or "9999")

    todo_list = []
    for t in todos:
        due = parse_due(t.get("due"))
        todo_list.append({
            "id": slug(f"{t['course']}-{t['title']}"),
            "course": parent(t.get("course", "")), "title": t["title"],
            "priority": (t.get("priority") or "med").lower(),
            "notes": t.get("notes", ""),
            "days": (due - now).days if due else None,
            **local_parts(due),
        })
    todo_list.sort(key=lambda t: (t["iso"] or "9999", {"high": 0, "med": 1, "low": 2}.get(t["priority"], 1)))

    courses = []
    for s, meta in config.items():
        cache = ROOT / "cache" / f"{s}-course.json"
        cov = json.loads(cache.read_text()) if cache.exists() else {}
        mine = [i for i in items if i["course"] == s]
        nearest = next((i for i in mine if i["open"] and i["iso"]), None)

        modules = []
        for n, m in enumerate(cov.get("modules", []), 1):
            names = m.get("items", [])
            has_next = bool(nearest and any(
                slug(nearest["title"]) in slug(x) or slug(x) in slug(nearest["title"])
                for x in names))
            dated = [i for i in mine if any(slug(i["title"]) in slug(x) for x in names)]
            if m.get("reference"):
                state = "reference"
            elif has_next:
                state = "current"
            elif dated and all(not i["open"] or (i["days"] or 0) < 0 for i in dated):
                state = "done"
            elif dated and all((i["days"] or 0) > (nearest["days"] if nearest else 0) for i in dated):
                state = "ahead"
            else:
                state = "done" if not dated else "ahead"
            modules.append({"n": n, "name": m["name"], "items": names, "state": state})

        courses.append({
            "slug": s, "name": meta["name"], "code": meta["code"],
            "role": meta["role"], "term": meta.get("term", ""),
            "staff": meta.get("staff", []),
            "sections": [{"label": lbl or "—", "id": cid,
                          "students": (meta.get("students") or {}).get(cid)}
                         for cid, lbl in meta.get("canvas", {}).items()],
            "note": cov.get("note", ""),
            "weights_published": cov.get("weights_published", True),
            "groups": cov.get("assignment_groups", []),
            "modules": modules,
            "items": mine,
            "todos": [t for t in todo_list if t["course"] == s],
            "open_count": sum(1 for i in mine if i["open"]),
            "next": nearest,
        })

    payload = {
        "generated": datetime.now(LOCAL).strftime("%b %-d, %Y at %-I:%M %p"),
        "courses": courses, "items": items, "todos": todo_list,
        "overdue": [i for i in items if i["overdue"]],
        "soon": [i for i in items if i["open"] and i["days"] is not None and 0 <= i["days"] <= 7],
    }

    html = TEMPLATE.read_text().replace("{{DATA}}", json.dumps(payload))
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", html)
    if leftover:
        raise SystemExit(f"unfilled template tokens: {sorted(set(leftover))}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"wrote {out} ({len(html):,} bytes){' [public]' if public else ''}")
    print(f"  {len(courses)} courses, {len(items)} tracked items, {len(todo_list)} todos")
    for c in courses:
        cur = next((m['name'] for m in c['modules'] if m['state'] == 'current'), '—')
        print(f"  {c['code']:<18} {c['role']:<8} open={c['open_count']:<3} current: {cur}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--public", action="store_true",
                    help="build the redacted page for GitHub Pages")
    build(public=ap.parse_args().public)
