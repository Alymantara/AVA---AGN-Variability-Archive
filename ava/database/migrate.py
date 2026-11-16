"""
One-time migration: import the existing ava.sqlite from the FLOYDS/AVA
folder into the new AVA database schema.

Usage:
    python -m ava.database.migrate --source /path/to/floyds/AVA/ava.sqlite
"""

import argparse
import sqlite3
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def migrate_from_legacy(source_path: str, dest_path: str):
    """
    Copy AGN, agn_lco, and lco_targets rows from the legacy DB
    into the new AVA DB.
    """
    src = sqlite3.connect(source_path)
    src.row_factory = sqlite3.Row

    # Import here to avoid circular imports at module level
    from ava.database.models import init_db, AGN, AGNLCOStats, LCOTarget
    from sqlalchemy.orm import Session

    engine = init_db(dest_path)

    with Session(engine) as session:
        # --- AGN / agn_master ---
        cur = src.execute("SELECT * FROM agn_master ORDER BY id")
        rows = cur.fetchall()
        log.info(f"Migrating {len(rows)} AGN rows...")

        for row in rows:
            r = dict(row)
            agn = AGN(
                id=r["id"], name=r["name"], data_id=r.get("data_id"),
                simbad_name=r.get("simbad_name"),
                ava=r.get("ava", 0), public=r.get("public", 0),
                ra=r.get("ra"), dec=r.get("dec"),
                ra_deg=r.get("ra_deg"), dec_deg=r.get("dec_deg"),
                Vmag=r.get("Vmag"), AGN_type=r.get("AGN_type"),
                redshift=r.get("redshift"), red_cite=r.get("red_cite"),
                ebv=r.get("ebv"), logl=r.get("logl"),
                l_5100=r.get("l_5100"), logm=r.get("logm"),
                ledd=r.get("ledd"),
                cite_name=r.get("cite_name"), cite_url=r.get("cite_url"),
                bentz_id=r.get("bentz_id"), PI=r.get("PI"),
                Comments=r.get("Comments"), last_update=r.get("last_update"),
            )
            session.merge(agn)

        # --- agn_lco ---
        cur = src.execute("SELECT * FROM agn_lco")
        rows = cur.fetchall()
        log.info(f"Migrating {len(rows)} agn_lco rows...")
        for row in rows:
            r = dict(row)
            stats = AGNLCOStats(**{k: v for k, v in r.items()
                                   if hasattr(AGNLCOStats, k)})
            session.merge(stats)

        # --- lco_targets ---
        cur = src.execute("SELECT * FROM lco_targets")
        rows = cur.fetchall()
        log.info(f"Migrating {len(rows)} lco_targets rows...")
        for i, row in enumerate(rows):
            r = dict(row)
            t = LCOTarget(id=i+1, **{k: v for k, v in r.items()
                                      if hasattr(LCOTarget, k) and k != "id"})
            session.merge(t)

        session.commit()

    src.close()
    log.info("Migration complete.")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Migrate legacy ava.sqlite to new schema")
    p.add_argument("--source", required=True, help="Path to legacy ava.sqlite")
    p.add_argument("--dest", default=None,
                   help="Destination DB path (default: from ava_config.yaml)")
    args = p.parse_args()

    if args.dest is None:
        from ava.config import cfg
        dest = str(cfg.db_path)
    else:
        dest = args.dest

    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    migrate_from_legacy(args.source, dest)


if __name__ == "__main__":
    main()
