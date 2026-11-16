"""Register a data release (files already made) in the AVA database, so the website links to it.

    python tools/register_release.py DR1                         # dry run: lists AGN and files per kind
    python tools/register_release.py DR1 --write                 # backup, then write the release tables
    python tools/register_release.py DR1 --write --withhold NGC_4151   # registered, but not linked (flag 0)

Reads ``<releases.dir>/DR1/release.yaml`` and every file under ``<releases.dir>/DR1/<data_id>/``; the layout and
the tables are described in :mod:`ava.database.releases`.  Re-run after the release files change.  The site shows
the links once ``release_date`` (release.yaml) has passed and the website is published (``-w``).
"""
import argparse
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ava.config import cfg  # noqa: E402
from ava.database import releases as R  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("release", help="release folder name, e.g. DR1")
    ap.add_argument("--write", action="store_true", help="back up the database, then write")
    ap.add_argument("--withhold", nargs="*", default=[], metavar="DATA_ID",
                    help="register these AGN with available = 0 (not linked on the site)")
    a = ap.parse_args()
    db, root = Path(cfg.db_path), R.releases_dir(cfg)
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        known = {r[0] for r in con.execute("SELECT data_id FROM agn WHERE data_id IS NOT NULL")}
    s = R.scan(root, a.release, known)
    m = s.meta
    print(f"{a.release}: {m['title'] or '(no title)'} · data {m['date_start']} → {m['date_end']} · "
          f"public {'from ' + m['release_date'] if m['release_date'] else 'NOT YET (release_date unset)'}"
          f"{' (public now)' if R.is_public(m['release_date']) else ''}")
    print(f"folder: {root / a.release}")
    for d in s.data_ids:
        fs = [f for f in s.files if f["data_id"] == d]
        kinds = ", ".join(f"{k} {n}" for k, n in sorted(Counter(f["kind"] for f in fs).items()))
        flag = "withheld" if d in a.withhold else "available"
        print(f"  {d:18s} {len(fs):4d} files {sum(f['bytes'] for f in fs) / 1e6:9.2f} MB  [{kinds}]  {flag}")
    if s.unknown:
        print(f"  ignored (not an AGN data_id): {s.unknown}")
    if not s.files:
        raise SystemExit("no files found: nothing to register")
    if not a.write:
        print("\n(dry run: nothing written; add --write)")
        return
    backup = db.parent / "backups" / f"ava_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_before_{a.release}.db"
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)
    print(f"backup: {backup}")
    out = R.register(db, s, set(a.withhold))
    print(f"registered {out['release']}: {out['agn']} AGN, {out['files']} files, {out['bytes'] / 1e6:.1f} MB"
          + (f"; withheld {out['withheld']}" if out["withheld"] else ""))


if __name__ == "__main__":
    main()
