# study

Term dashboard for UBC coursework, built from Canvas.

Live: **https://geoffreybian.github.io/study/**

UBC disables student Canvas API tokens, so this pulls from two token-free
sources instead:

- **`sync_ics.py`** — the Canvas calendar feed, which needs no authentication
  and carries every dated assignment. No browser, cron-safe. The default path.
- **`ingest.py`** — Canvas's REST API answers normally to a logged-in browser
  session, which fills in points, submission status and scores.

`build_dashboard.py` renders `tracker.csv` + `todos.csv` + `courses.json` into
the page: an overview with the next deadlines and a to-do list, plus a page per
course showing what's currently being covered.

## Two builds

`build_dashboard.py --public` drops every course not flagged `"public": true`
in `courses.json`, and `check_public.py` refuses to publish if anything from a
private course reaches `docs/index.html`. Only the redacted build is committed;
the full one stays local.

```
./publish.sh          # sync, rebuild both, leak-scan, push
```

## Setup

```bash
cp courses.example.json courses.json     # your courses, Canvas ids, roles
echo 'CANVAS_ICS_URL=<your feed>' > .env  # Canvas > Calendar > Calendar Feed
python3 sync_ics.py && python3 due.py
```

The feed URL is a bearer secret — anyone holding it can read your whole
calendar. It stays in `.env`, which is gitignored.

## Notes

Two things that bite:

- Canvas due times are UTC. `America/Vancouver` tzdata is broken on some
  machines (it stops observing DST and reports MST), which pushes winter
  deadlines an hour late; `tracker.PACIFIC` pins `America/Los_Angeles` and
  asserts a known winter timestamp at import.
- The calendar feed's UID is an *assignment override* id while the REST API
  returns the *assignment* id, so rows key on course plus normalized title, not
  on the Canvas id.
