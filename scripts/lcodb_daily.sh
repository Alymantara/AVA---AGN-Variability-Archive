#!/usr/bin/env bash
# Daily update of the LCO archive databases (lcodb daily), from any working directory.
# Schedule with cron (crontab -e), e.g. at 09:30 UTC, before the pipeline:
#   30 9 * * * AVA_PYTHON=/path/to/env/bin/python /path/to/AVA/scripts/lcodb_daily.sh
# AVA_PYTHON: the Python of the AVA environment (default: python3 on PATH).
# The databases and log go where config/lcodb_config.yaml says (db_dir); LCODB_CONFIG overrides it.
set -euo pipefail
AVA_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${AVA_PYTHON:-python3}"
cd "$AVA_ROOT"
LOG_DIR="$("$PY" -c 'from ava.lcodb.config import load_config; print(load_config().db_path("spectra").parent)')"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/daily.log"
echo "--- $(date -u '+%Y-%m-%dT%H:%M:%SZ') ---" >> "$LOG"
exec "$PY" -m ava.lcodb daily >> "$LOG" 2>&1
