#!/usr/bin/env bash
# Daily update of the LCO archive databases (lcodb daily), from any working directory.
# Scheduled by scripts/make_crontab.py (01:00 UTC, before the pipeline), through scripts/cron_job.sh.
# AVA_PYTHON: the Python of the AVA environment (default: python3 on PATH).
# The databases go where the lcodb config says (db_dir): LCODB_CONFIG, else data/config/lcodb_config.yaml, else
# config/lcodb_config.yaml. The output is appended to <db_dir>/daily.log AND printed, so the cron wrapper's
# <logs>/lcodb_daily.log has it too.
set -euo pipefail
AVA_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${AVA_PYTHON:-python3}"
cd "$AVA_ROOT"
LOG_DIR="$("$PY" -c 'from ava.lcodb.config import load_config; print(load_config().db_path("spectra").parent)')"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/daily.log"
echo "--- $(date -u '+%Y-%m-%dT%H:%M:%SZ') ---" | tee -a "$LOG"
"$PY" -m ava.lcodb daily 2>&1 | tee -a "$LOG"      # pipefail: the exit code is lcodb's, not tee's
