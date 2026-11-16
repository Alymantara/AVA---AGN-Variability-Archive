#!/bin/zsh
# Daily update of the LCO archive databases.
# Schedule with cron: crontab -e
#   30 9 * * * /Users/juan/astro/AVA/scripts/lcodb_daily.sh
AVA_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY=${AVA_PYTHON:-/opt/anaconda3/envs/ava/bin/python3}
LOG="$AVA_ROOT/data/lcodb/daily.log"
mkdir -p "$AVA_ROOT/data/lcodb"
echo "--- $(date -u '+%Y-%m-%dT%H:%M:%SZ') ---" >> "$LOG"
exec "$PY" -m ava.lcodb daily >> "$LOG" 2>&1
