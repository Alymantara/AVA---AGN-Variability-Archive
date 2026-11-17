#!/usr/bin/env bash
# Commit and push the LCO usage snapshot log (data/lco_usage/snapshots.csv) to GitHub, so the history of the
# charged totals is kept in the repository (production VM, daily cron; deployment_guide.md §7.5).
#
# Only that one file is ever staged. Needs push access from the VM (a deploy key with write access).
#
#   0 7 * * *  /opt/ava/AVA/scripts/push_lco_snapshots.sh >> /srv/ava/logs/lco_snapshots_push.log 2>&1
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
FILE="data/lco_usage/snapshots.csv"
cd "$REPO"
echo "--- $(date -u +%Y-%m-%dT%H:%M:%SZ) push_lco_snapshots"

if [ -z "$(git status --porcelain -- "$FILE")" ]; then
    echo "no new snapshots"
    exit 0
fi
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git add -- "$FILE"
git commit -q -m "LCO usage snapshots up to $(tail -n 1 "$FILE" | cut -d, -f1)" -- "$FILE"
git pull -q --rebase --autostash origin "$BRANCH"
git push -q origin "$BRANCH"
echo "pushed $(git rev-parse --short HEAD) to origin/$BRANCH"
