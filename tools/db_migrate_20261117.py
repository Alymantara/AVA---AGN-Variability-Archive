#!/usr/bin/env python
"""
AVA database migration, 2026-11-17 — two target identity fixes.

1. Kaz 163 (id 79): the stored position (17:46:59.84 +68:36:36.8) is the VII Zw 742 galaxy-pair
   centre, near the northern galaxy (Z 322-13).  The AGN is the southern nucleus,
   2MASS J17465953+6836303 = Gaia DR3 1634665450507168000 (G = 16.3, DSC quasar probability 1.00;
   the northern Gaia source is classed as a galaxy).  ra/dec/ra_deg/dec_deg are set to the Gaia
   position, agn_gaia_dr3_id is filled, and a note is appended to Comments.
2. RX J2219.8+0935 (id 30): data_id ``J22198-0935`` → ``J22198+0935`` (the declination is +09:35;
   the name was already corrected on 2026-11-16).  Renamed in every ava.db table that holds a
   data_id and in the lcodb target links (frames.ava_data_id, target_link.ava_data_id).  The LCO
   OBJECT name "J22198-0935" is the observers' label and is left as it is.

Idempotent.  Dry run by default; ``--write`` backs up each database first
(``<db dir>/backups/<stem>_<stamp>_pre-migrate-20261117.db``).

    python tools/db_migrate_20261117.py                                  # dry run, cfg database + lcodb
    python tools/db_migrate_20261117.py --write
    python tools/db_migrate_20261117.py --db data/test_archive/ava.db --no-lcodb --write
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ava.config import cfg  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OLD_ID, NEW_ID = "J22198-0935", "J22198+0935"
KAZ = dict(data_id="Kaz_163", ra_deg=266.748098, dec_deg=68.608445, gaia=1634665450507168000,
           note="2026-11-17: position moved from the VII Zw 742 pair centre to the AGN (southern nucleus, "
                "2MASS J17465953+6836303 = Gaia DR3 1634665450507168000)")
#: ava.db table -> data_id column
AVA_TABLES = {"agn": "data_id", "agn_master": "data_id", "agn_literature": "data_id", "agn_derived": "data_id",
              "photometry_variability": "data_id", "line_variability": "data_id", "agn_releases": "data_id",
              "release_files": "data_id", "lco_targets": "ava_data_id"}
LCODB_TABLES = {"frames": "ava_data_id", "target_link": "ava_data_id"}


def sexagesimal(ra: float, dec: float) -> tuple[str, str]:
    from astropy.coordinates import SkyCoord

    c = SkyCoord(ra, dec, unit="deg")
    return (c.ra.to_string(unit="hourangle", sep=":", precision=2, pad=True),
            c.dec.to_string(sep=":", precision=2, alwayssign=True, pad=True))


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def plan(db: Path, tables: dict[str, str], kaz: bool) -> list[tuple[str, tuple]]:
    """[(sql, params)] still needed for ``db``; empty when already migrated."""
    out = []
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
        have = _tables(con)
        for t, col in tables.items():
            if t in have and con.execute(f'SELECT count(*) FROM "{t}" WHERE "{col}" = ?', (OLD_ID,)).fetchone()[0]:
                out.append((f'UPDATE "{t}" SET "{col}" = ? WHERE "{col}" = ?', (NEW_ID, OLD_ID)))
        if kaz and "agn" in have:
            ra, dec = sexagesimal(KAZ["ra_deg"], KAZ["dec_deg"])
            row = con.execute("SELECT ra_deg, dec_deg, agn_gaia_dr3_id FROM agn WHERE data_id = ?", (KAZ["data_id"],)).fetchone()
            if row and (abs((row[0] or 0) - KAZ["ra_deg"]) > 1e-6 or abs((row[1] or 0) - KAZ["dec_deg"]) > 1e-6 or row[2] != KAZ["gaia"]):
                out.append(("UPDATE agn SET ra = ?, dec = ?, ra_deg = ?, dec_deg = ?, agn_gaia_dr3_id = ?, "
                            "Comments = trim(COALESCE(Comments, '') || ' ' || ?) WHERE data_id = ?",
                            (ra, dec, KAZ["ra_deg"], KAZ["dec_deg"], KAZ["gaia"], KAZ["note"], KAZ["data_id"])))
    return out


def apply(db: Path, steps: list[tuple[str, tuple]]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bdir = db.parent / "backups"
    bdir.mkdir(exist_ok=True)
    backup = bdir / f"{db.stem}_{stamp}_pre-migrate-20261117{db.suffix}"
    with closing(sqlite3.connect(db, timeout=60)) as con, closing(sqlite3.connect(backup)) as b:
        con.backup(b)
        for sql, p in steps:
            con.execute(sql, p)
        con.commit()
    return backup


@click.command()
@click.option("--db", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="AVA database (default: cfg.db_path).")
@click.option("--lcodb/--no-lcodb", default=True, help="Also rename the data_id in the lcodb databases (data/lcodb).")
@click.option("--write", is_flag=True, help="Back up, then write (default: dry run).")
def main(db, lcodb, write):
    targets = [(Path(db or cfg.db_path).resolve(), AVA_TABLES, True)]
    if lcodb:
        targets += [(ROOT / "data/lcodb" / n, LCODB_TABLES, False) for n in ("photometry.sqlite", "spectra.sqlite")]
    for path, tables, kaz in targets:
        if not path.exists():
            click.echo(f"{path}: missing, skipped")
            continue
        steps = plan(path, tables, kaz)
        for sql, p in steps:
            click.echo(f"{path.name}: {sql.split(' SET')[0]}  {p if len(p) < 4 else p[:5]}")
        if not steps:
            click.echo(f"{path}: nothing to do")
        elif write:
            click.echo(f"{path}: {len(steps)} change(s) written; backup {apply(path, steps)}")
    if not write:
        click.echo("dry run: nothing written (use --write)")


if __name__ == "__main__":
    main()
