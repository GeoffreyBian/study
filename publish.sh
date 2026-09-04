#!/usr/bin/env bash
# Sync, rebuild both dashboards, and push the public one live.
#
#   docs/index.html  -> geoffreybian.github.io/study   (public, redacted)
#   dashboard.html   -> the Claude artifact             (private, everything)
#
# Mirrors ~/dev/garmin/refresh.sh, which does the same for /train.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "==> Syncing deadlines from the Canvas feed"
python3 sync_ics.py

echo
echo "==> Rebuilding dashboards"
python3 build_dashboard.py            # full, for the artifact
python3 build_dashboard.py --public   # redacted, for GitHub Pages

echo
echo "==> Leak scan"
# Hard gate. A course without "public": true in courses.json must not reach
# docs/index.html; this aborts the push rather than publishing it.
python3 check_public.py

echo
echo "==> Publishing"
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "   not a git repo yet — skipping push"
elif ! git remote get-url origin >/dev/null 2>&1; then
  echo "   no 'origin' remote — skipping push"
elif git diff --quiet HEAD -- docs/index.html 2>/dev/null; then
  echo "   docs/index.html unchanged — nothing to push"
else
  git add -A
  git commit -q -m "Refresh dashboard $(date +%Y-%m-%d)" || true
  git push -q origin HEAD && echo "   pushed — live at https://geoffreybian.github.io/study/"
fi

if [ -f insights/ARTIFACT.txt ]; then
  echo
  echo "Claude version (has CPEN 221): republish dashboard.html to"
  echo "  $(cat insights/ARTIFACT.txt)"
  echo "Reuse that URL, or you get a second artifact and lose the saved ticks."
fi
