#!/usr/bin/env bash
# Rebuild the dashboard and stage it for both places it is published:
#   docs/index.html  -> GitHub Pages at geoffreybian.github.io/study
#   dashboard.html   -> the Claude artifact in insights/ARTIFACT.txt
# Mirrors ~/dev/garmin/refresh.sh, which does the same for /train.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "==> Syncing deadlines from the Canvas feed"
python3 sync_ics.py

echo
echo "==> Rebuilding dashboard"
python3 build_dashboard.py

# docs/index.html is what GitHub Pages serves; keep it in step with the build.
cp dashboard.html docs/index.html && echo "   docs/index.html updated"

# A secret in the built page would be published to a public site. Fail loudly.
if grep -qE 'feeds/calendars|CANVAS_API_TOKEN=.|geoffreybian100' docs/index.html; then
  echo "REFUSING TO PUBLISH: secret found in docs/index.html" >&2
  exit 1
fi

echo
echo "Built. To put it live:"
echo "  git -C $(pwd) add -A && git commit -m 'Refresh dashboard' && git push"
if [ -f insights/ARTIFACT.txt ]; then
  echo "  Claude version: republish to $(cat insights/ARTIFACT.txt) (reuse that URL,"
  echo "  otherwise you get a second artifact and lose the saved ticks)."
fi
