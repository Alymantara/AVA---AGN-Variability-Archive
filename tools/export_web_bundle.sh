#!/usr/bin/env bash
# Export a standalone copy of the AVA website for an Apache + PHP (>= 8.1, pdo_sqlite) host.
#
# The copy serves only the published snapshot: web/ (minus _legacy/) plus web/data/ as left by the last
# `publish_web.py` run. It needs no pipeline code, no ava package, no config YAML and no LCO access.
# All site links are relative, so the folder works at a domain root or under any sub-path (e.g. /ava/).
#
#   tools/export_web_bundle.sh [OUT_DIR]          # default OUT_DIR: ~/ava_web_bundle
#   AVA_BUNDLE_TAR=1 tools/export_web_bundle.sh   # also write OUT_DIR.tar.gz
#   AVA_BUNDLE_STAGING=0 tools/export_web_bundle.sh   # no STAGING badge (default: on, for the test copy)
#
# Rerun after each publish: rsync --delete makes OUT_DIR an exact mirror (stale files are removed).
# Upload/refresh instructions: docs/guides/personal_site_bundle.md

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
WEB="$REPO/web"
OUT="${1:-$HOME/ava_web_bundle}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd -P)"

case "$OUT/" in
  "$(cd "$REPO" && pwd -P)"/*) rmdir "$OUT" 2>/dev/null || true
    echo "error: OUT_DIR must be outside the repository ($REPO)" >&2; exit 1 ;;
esac
# rsync --delete mirrors web/ into OUT: refuse a non-empty folder that is not an earlier bundle.
if [[ -n "$(ls -A "$OUT")" && ! -f "$OUT/BUNDLE_INFO.txt" ]]; then
  echo "error: $OUT is not empty and is not an AVA bundle; choose a new or empty folder" >&2; exit 1
fi
for f in ava.db filter_dict.txt site.json; do
  [[ -f "$WEB/data/$f" ]] || { echo "error: $WEB/data/$f missing; run the web publish step first" >&2; exit 1; }
done

# Staging copies leave out the large 1-d FLOYDS spectra (served by the main site only; includes/plots.php:
# AVA_STAGING_MAIN_ONLY marks them "on the main AVA site only").
STAGING_EXCLUDES=()
if [[ "${AVA_BUNDLE_STAGING:-1}" == "1" ]]; then
  STAGING_EXCLUDES=(--exclude 'data/downloads/*/*_FLOYDS_1d.zip')
fi

rsync -a --delete \
  ${STAGING_EXCLUDES[@]+"${STAGING_EXCLUDES[@]}"} \
  --exclude '_legacy/' \
  --exclude '.DS_Store' \
  --exclude '.gitignore' \
  --exclude '*.tmp' \
  --exclude 'BUNDLE_INFO.txt' \
  --exclude 'STAGING' \
  "$WEB/" "$OUT/"

# Bundle-only: make index.php the folder index (the main site leaves this to the server config).
cat > "$OUT/.htaccess" <<'EOF'
# AVA website bundle (tools/export_web_bundle.sh). Per-folder rules live in includes/, data/, data/releases/.
DirectoryIndex index.php
EOF

{
  echo "AVA website bundle"
  echo "exported: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo "commit:   $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "ava.db:   $(date -u -r "$WEB/data/ava.db" '+%Y-%m-%d %H:%M UTC' 2>/dev/null || stat -c %y "$WEB/data/ava.db")"
} > "$OUT/BUNDLE_INFO.txt"

# Staging marker: includes/config.php then shows a STAGING badge and asks search engines not to index the copy.
if [[ "${AVA_BUNDLE_STAGING:-1}" == "1" ]]; then
  echo "commit $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown), exported $(date -u '+%Y-%m-%d %H:%M UTC')" \
    > "$OUT/STAGING"
  rm -f "$OUT"/data/downloads/*/*_FLOYDS_1d.zip     # left by an earlier non-staging export (rsync keeps excluded files)
else
  rm -f "$OUT/STAGING"
fi

# Keep the build note and the marker out of the public site.
cat >> "$OUT/.htaccess" <<'EOF'
<FilesMatch "^(BUNDLE_INFO\.txt|STAGING)$">
  Require all denied
</FilesMatch>
EOF

if [[ "${AVA_BUNDLE_TAR:-0}" == "1" ]]; then
  tar -czf "$OUT.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")"
  echo "wrote $OUT.tar.gz"
fi

echo "bundle: $OUT ($(du -sh "$OUT" | cut -f1))"
cat "$OUT/BUNDLE_INFO.txt"
