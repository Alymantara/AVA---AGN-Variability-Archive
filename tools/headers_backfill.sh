#!/bin/zsh
# Fetch all pending headers, politely: when the archive throttles us (HTTP 429 with a long Retry-After)
# Usage: DB=spectra tools/headers_backfill.sh   (default DB=spectra; photometry headers are off in config.yaml)
# `lcodb headers` stops cleanly; we wait and resume until nothing is pending, then run airmass + matching.
cd "$(dirname "$0")/.."
pending() { sqlite3 db/spectra.sqlite "select count(*) from frames where header_status=0 and rlevel in (0,91)";
            [[ ${DB:-spectra} == spectra ]] || sqlite3 db/photometry.sqlite "select count(*) from frames where header_status=0 and is_best=1"; }
while true; do
  python3 -m lcodb headers --db ${DB:-spectra}
  left=$(pending | paste -sd+ - | bc)
  echo "$(date '+%F %T') pending headers: $left"
  [[ $left -eq 0 ]] && break
  sleep 1800
done
python3 -m lcodb airmass && python3 -m lcodb match && echo ALL_DONE
