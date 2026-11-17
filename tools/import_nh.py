"""Add the Galactic HI column density N_H (HI4PI) to the AVA catalogue: column ``agn.nh`` in cm^-2.

Values come from the HEASARC nH tool (w3nh), map ``h1_nh_HI4PI.fits`` (HI4PI Collaboration 2016,
A&A 594, A116), weighted average within 0.1 deg of the AGN position — what the original AVA
website showed next to E(B-V). Only rows with no value yet are queried (one request per AGN): a one-off
backfill; new AGN get N_H when they are added (tools/add_ava_targets.py).

    python tools/import_nh.py                     # dry run: print the values, write nothing
    python tools/import_nh.py --apply             # add/fill agn.nh in cfg.db_path (backup first)
    python tools/import_nh.py --apply --db data/test_archive/ava.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ava.config import cfg  # noqa: E402
from ava.photometry.reference import field_nh_hi4pi as hi4pi_nh  # noqa: E402


def backup(db: Path) -> Path:
    out = db.parent / "backups"
    out.mkdir(exist_ok=True)
    dst = out / f"{db.stem}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_pre-nh.db"
    with closing(sqlite3.connect(db)) as src, closing(sqlite3.connect(dst)) as d:
        src.backup(d)
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", help="AVA database (default: cfg.db_path)")
    ap.add_argument("--apply", action="store_true", help="write agn.nh (default: dry run)")
    ap.add_argument("--all", action="store_true", help="re-query rows that already have a value")
    a = ap.parse_args()
    db = Path(a.db).resolve() if a.db else cfg.db_path
    with closing(sqlite3.connect(db)) as con:
        has = "nh" in {r[1] for r in con.execute("PRAGMA table_info(agn)")}
        where = "" if (a.all or not has) else "AND nh IS NULL"
        rows = con.execute(f"SELECT id, data_id, ra_deg, dec_deg FROM agn WHERE ra_deg IS NOT NULL {where} ORDER BY id").fetchall()
    vals = []
    for i, d, ra, dec in rows:
        try:
            nh = hi4pi_nh(float(ra), float(dec))
        except requests.RequestException as e:
            print(f"  {d}: request failed ({type(e).__name__})")
            nh = None
        print(f"  {d:22s} {nh:.3e}" if nh else f"  {d:22s} —")
        vals.append((nh, i))
        time.sleep(0.5)
    n = sum(v is not None for v, _ in vals)
    if not a.apply:
        print(f"[dry-run] {n} of {len(rows)} AGN with N_H; nothing written to {db}")
        return
    bk = backup(db)
    with closing(sqlite3.connect(db)) as con:
        if not has:
            con.execute("ALTER TABLE agn ADD COLUMN nh REAL")
        con.executemany("UPDATE agn SET nh = ? WHERE id = ? AND ? IS NOT NULL", [(v, i, v) for v, i in vals])
        con.commit()
    print(f"{n} of {len(rows)} AGN: agn.nh written to {db} (backup {bk})")


if __name__ == "__main__":
    main()
