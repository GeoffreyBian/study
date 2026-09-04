# School

Coursework, synced from Canvas (UBC). Driven by the `school` skill.

UBC has **disabled student Canvas API tokens**, so there is no API key here.
Two token-free paths replace it:

1. **ICS calendar feed** (`sync_ics.py`) — a permanent, unauthenticated URL that
   carries every dated assignment. No browser needed, works from cron.
2. **Browser-session API** (`ingest.py`) — Canvas's REST API answers normally to
   a logged-in browser session, so the Chrome tools can pull points, submission
   status, scores, rubrics and files. Needs Chrome open and signed in.

```
school/
  .env                 # CANVAS_ICS_URL (secret, gitignored, chmod 600)
  courses.json         # canvas course id -> local slug
  tracker.py           # shared tracker.csv load/merge
  sync_ics.py          # feed  -> tracker.csv
  ingest.py            # browser JSON dump -> tracker.csv
  due.py               # what's due / overdue
  tracker.csv          # every assignment/exam across courses
  cache/               # browser JSON dumps (gitignored)
  courses/<slug>/
    course.md          # canvas id, instructors, grading breakdown, how it's graded
    syllabus.md
    assignments/<slug>/
    notes/  materials/  exams/
```

Both syncs are idempotent and converge — running either repeatedly reports
"no changes".

Add a course: create `courses/<slug>/`, add its Canvas id to `courses.json`,
re-run `sync_ics.py`.
