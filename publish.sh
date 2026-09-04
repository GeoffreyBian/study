#!/usr/bin/env bash
# Sync Canvas, rebuild the term board, and publish it everywhere it lives.
#
#   geoffreybian.github.io/study   encrypted blob + page in the website repo
#   Claude artifact                the same board, inline, for reading back ticks
#
# Mirrors ~/dev/stocks/scripts/publish_web_dashboard.py, which does the same
# for /portfolio.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
PY=./.venv/bin/python
[ -x "$PY" ] || PY=python3

# --no-web is the shared flag across all three dashboards (garmin's refresh.sh
# and stocks' refresh_all.py take the same one). publish_web.py spells it
# --no-push, so translate rather than making the caller remember which is which.
WEB=1
ARGS=()
for a in "$@"; do
  case "$a" in
    --no-web|--no-push) WEB=0 ;;
    *) ARGS+=("$a") ;;
  esac
done

echo "==> Syncing deadlines from the Canvas feed"
$PY sync_ics.py

echo
echo "==> Rebuilding the board"
$PY build_dashboard.py

echo
echo "==> Encrypting and publishing to the website"
if [ "$WEB" = "1" ]; then
  $PY publish_web.py ${ARGS+"${ARGS[@]}"}
else
  $PY publish_web.py --no-push ${ARGS+"${ARGS[@]}"}
fi

# The generated page only changes when the template does, so committing it is
# usually a no-op. The course data never lands here — it is in the blob.
# --porcelain, not `git diff`: study.html may be untracked, which `git diff`
# reports as no change.
if [ "$WEB" = "1" ] && [ -n "$(git -C ../website status --porcelain -- study.html)" ]; then
  echo "   study.html changed — committing to the website repo"
  git -C ../website add study.html
  git -C ../website commit -q -m "Update /study dashboard page"
  git -C ../website push -q && echo "   pushed"
fi

echo
echo "==> Code repo"
if [ "$WEB" = "0" ]; then
  echo "   --no-web: not pushing"
elif git diff --quiet HEAD 2>/dev/null && git diff --cached --quiet 2>/dev/null; then
  echo "   no code changes"
else
  git add -A
  git commit -q -m "Refresh $(date +%Y-%m-%d)" || true
  git push -q origin HEAD 2>/dev/null && echo "   pushed" || echo "   nothing to push"
fi

if [ -f insights/ARTIFACT.txt ]; then
  echo
  echo "Claude artifact: republish dashboard.html to"
  echo "  $(cat insights/ARTIFACT.txt)"
  echo "Reuse that URL, or you get a second artifact and lose the saved ticks."
fi
