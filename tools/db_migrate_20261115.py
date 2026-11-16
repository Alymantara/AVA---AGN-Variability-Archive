#!/usr/bin/env python
"""
AVA database migration, 2026-11-15 — make ava.db the pipeline's source of truth.

1. Add pipeline columns to ``agn`` (if missing):
     lco_active, lt_active   INTEGER 0/1 — filled from config/targets.yaml for
                             matching data_ids (others stay NULL = not set)
     agn_gaia_dr3_id         INTEGER — written by the -o reference-catalogue step
2. Fill missing decimal coordinates (ra_deg/dec_deg empty) for four sources
   from their Gaia DR3 counterparts, checked against the source names /
   targets.yaml (see the session notes of 2026-11-15).  The sexagesimal
   ra/dec columns are rewritten to match, and a provenance note is appended
   to Comments.  SDSS-RM201, SDSS-RM562 and RX J22198-0935 are deliberately
   left unchanged.

Idempotent: re-running changes nothing.  Back up first:
    sqlite3 data/ava.db ".backup data/backups/ava_<stamp>.db"

    python tools/db_migrate_20261115.py            # dry run (prints the changes)
    python tools/db_migrate_20261115.py --apply
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import click
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ava.config import cfg  # noqa: E402

TODAY = date(2026, 11, 15).isoformat()

PIPELINE_COLUMNS = {"lco_active": "INTEGER", "lt_active": "INTEGER", "agn_gaia_dr3_id": "INTEGER"}

#: data_id -> (ra_deg, dec_deg, Gaia DR3 source_id, how it was checked)
COORD_FIXES = {
    "MCG+04-22-042": (140.929170, 22.909048, 639017573740551296,
                      "0.6\" from targets.yaml MCG_04-22-042"),
    "J21079-3754": (316.998831, -37.902523, 6774446525799214336,
                    "0.4\" from the 2MASX J21075970-3754087 name position"),
    "J21368-6438": (324.219690, -64.634388, 6402261564918955520,
                    "1.8\" from the DB sexagesimal position"),
    "PKS_0558": (89.947465, -50.447785, 4794222613840578304,
                 "3.7\" from the DB sexagesimal position"),
}


def sexagesimal(ra: float, dec: float) -> tuple[str, str]:
    from astropy.coordinates import SkyCoord

    c = SkyCoord(ra, dec, unit="deg")
    return (c.ra.to_string(unit="hourangle", sep=":", precision=2, pad=True),
            c.dec.to_string(sep=":", precision=2, alwayssign=True, pad=True))


@click.command()
@click.option("--apply", "do_apply", is_flag=True, help="Write the changes (default: dry run).")
@click.option("--db", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Database to migrate [default: paths.database].")
def main(do_apply, db):
    db = db or cfg.db_path
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    cols = {r["name"] for r in con.execute("PRAGMA table_info(agn)")}
    changes = []

    for col, typ in PIPELINE_COLUMNS.items():
        if col not in cols:
            changes.append(f"ALTER TABLE agn ADD COLUMN {col} {typ}")
            if do_apply:
                con.execute(f'ALTER TABLE agn ADD COLUMN "{col}" {typ}')

    # lco_active / lt_active from the YAML reference list (only where unset)
    with open(cfg.root / "config" / "targets.yaml") as f:
        ymap = {t["data_id"]: t for t in (yaml.safe_load(f) or {}).get("targets", [])}
    for r in con.execute("SELECT id, data_id FROM agn ORDER BY id").fetchall():
        y = ymap.get(r["data_id"])
        if y is None:
            continue
        cur = con.execute("SELECT lco_active, lt_active FROM agn WHERE id=?", (r["id"],)).fetchone() \
            if "lco_active" in cols or do_apply else None
        want = (int(bool(y.get("lco_active"))), int(bool(y.get("lt_active"))))
        if cur is None or (cur["lco_active"], cur["lt_active"]) != want:
            changes.append(f"{r['data_id']}: lco_active={want[0]} lt_active={want[1]}")
            if do_apply:
                con.execute("UPDATE agn SET lco_active=?, lt_active=? WHERE id=?", (*want, r["id"]))

    for did, (ra, dec, gid, why) in COORD_FIXES.items():
        row = con.execute("SELECT id, ra_deg, dec_deg, Comments FROM agn WHERE data_id=?", (did,)).fetchone()
        if row is None:
            changes.append(f"!! {did} not found — skipped")
            continue
        if row["ra_deg"] not in (None, "") and row["dec_deg"] not in (None, ""):
            continue  # already has coordinates: never overwrite
        ra_s, dec_s = sexagesimal(ra, dec)
        note = f"[{TODAY}] coords from Gaia DR3 {gid} ({why})"
        comments = (str(row["Comments"]).rstrip() + " | " if row["Comments"] not in (None, "") else "") + note
        changes.append(f"{did}: ra_deg/dec_deg = {ra:.6f} {dec:+.6f} ({ra_s} {dec_s}); {note}")
        if do_apply:
            con.execute("UPDATE agn SET ra_deg=?, dec_deg=?, ra=?, dec=?, Comments=?, last_update=? WHERE id=?",
                        (ra, dec, ra_s, dec_s, comments, TODAY, row["id"]))

    if do_apply:
        con.commit()
    con.close()
    print(("APPLIED" if do_apply else "DRY RUN") + f" on {db}: {len(changes)} change(s)")
    for c in changes:
        print("  " + c)


if __name__ == "__main__":
    main()
