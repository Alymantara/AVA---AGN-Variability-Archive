#!/usr/bin/env bash
# Run one scheduled AVA job and record how it ended.
#
#   scripts/cron_job.sh NAME LOG_DIR -- command [args...]
#
# The command's output goes to LOG_DIR/NAME.log, between "=== <UTC> start" and "=== <UTC> end: exit N" lines, and
# one line per run is appended to LOG_DIR/cron_runs.tsv:  name <TAB> start <TAB> end <TAB> exit code.
# scripts/daily_check.py reads that file to tell whether every job ran on time and succeeded. Lines written by
# scripts/make_crontab.py use this wrapper. If `flock` is available, a job that is still running is not started a
# second time (the skipped run is recorded with exit code 75).
set -uo pipefail

if [ $# -lt 4 ] || [ "$3" != "--" ]; then
    echo "usage: $0 NAME LOG_DIR -- command [args...]" >&2
    exit 64
fi
name=$1
logdir=$2
shift 3
mkdir -p "$logdir"
log="$logdir/$name.log"
runs="$logdir/cron_runs.tsv"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

start=$(now)
echo "=== $start start: $*" >> "$log"
if command -v flock >/dev/null 2>&1; then
    exec 9>"$logdir/.$name.lock"
    if ! flock -n 9; then
        end=$(now)
        echo "=== $end end: exit 75 (previous run still going; skipped)" >> "$log"
        printf '%s\t%s\t%s\t%s\n' "$name" "$start" "$end" 75 >> "$runs"
        exit 75
    fi
fi
"$@" >> "$log" 2>&1
rc=$?
end=$(now)
echo "=== $end end: exit $rc" >> "$log"
printf '%s\t%s\t%s\t%s\n' "$name" "$start" "$end" "$rc" >> "$runs"
exit $rc
