"""Import literature AGN properties (data/literature/agn_properties.csv) into the AVA database.

    python tools/import_literature.py                      # dry run: what would be written
    python tools/import_literature.py --write              # backup, then upsert table agn_literature
    python tools/import_literature.py --apply-to-agn       # dry run, also list changes to the agn columns
    python tools/import_literature.py --apply-to-agn --write
    python tools/import_literature.py --csv other.csv --db path/to/ava.db

``agn_literature`` mirrors the CSV (see :mod:`ava.database.literature`).  ``--apply-to-agn`` also copies
z / log M_BH / log L5100 / type into the curated agn columns shown on the website, with their citations;
afterwards run ``python tools/derive_agn_properties.py`` so agn_derived (L_bol, Eddington ratio, disc
lags) follows the new masses and luminosities.
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ava.config import cfg  # noqa: E402
from ava.database.literature import import_literature  # noqa: E402


def backup(db: Path) -> Path:
    """Online SQLite backup to <db dir>/backups/<name>_<UTC stamp>_pre-literature.db."""
    out = db.parent / "backups"
    out.mkdir(exist_ok=True)
    dst_path = out / f"{db.stem}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_pre-literature.db"
    src, dst = sqlite3.connect(f"file:{db}?mode=ro", uri=True), sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        src.close(), dst.close()
    return dst_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=str(REPO / "data/literature/agn_properties.csv"))
    ap.add_argument("--db", help="AVA database (default: cfg.db_path)")
    ap.add_argument("--apply-to-agn", action="store_true",
                    help="also update agn.redshift/logm/l_5100/AGN_type (+ citations) where the CSV has values")
    ap.add_argument("--write", action="store_true", help="back up the database, then write")
    a = ap.parse_args()
    db = Path(a.db).resolve() if a.db else Path(cfg.db_path)
    csv = Path(a.csv).resolve()

    res = import_literature(db, csv, apply_to_agn=a.apply_to_agn, write=False)
    if res["unknown"]:
        print(f"skipped (not in agn): {', '.join(res['unknown'])}")
    for u in res["agn_updates"]:
        print(f"  agn {u['data_id']:<18} {u['column']:<12} {u['old']!s:>22} -> {u['new']}")
    print(f"{res['rows']} rows for agn_literature; {len(res['agn_updates'])} agn column changes")
    if not a.write:
        print("dry run — nothing written (add --write)")
        return
    bk = backup(db)
    import_literature(db, csv, apply_to_agn=a.apply_to_agn, write=True)
    print(f"{db}: agn_literature upserted ({res['rows']} rows)"
          + (f", {len(res['agn_updates'])} agn changes" if a.apply_to_agn else "") + f"; backup {bk}")
    if a.apply_to_agn and res["agn_updates"]:
        print("next: python tools/derive_agn_properties.py")


if __name__ == "__main__":
    main()
