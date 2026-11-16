"""
Spectroscopy initialise task — create one target's FLOYDS folders and record what exists for it.

The spectroscopic counterpart of :mod:`ava.pipeline.tasks.initialise` (legacy: the folder part
of ``__old_pipeline__/ava_floyds_sort.py``).  Idempotent: never deletes or overwrites.

Folders (``<spec_root>`` = ``paths.spectra_root``, ``<spec_raw>`` = ``paths.spectra_raw``):

  ======================================  ===============================================
  ``<spec_raw>/<target>/``                 raw science + arcs + lamp flats (``YYYYMMDD/``)
  ``<spec_raw>/standards/``                raw standards + their arcs / flats (shared)
  ``<spec_root>/<target>/``                spectroscopy products of the target
  ``<spec_root>/<target>/archive/``        archive BANZAI -1d/-2d (comparison)
  ``<spec_root>/<target>/reduced/``        our reduction (banzai-floyds, improved fork)
  ``<spec_root>/<target>/plots/``          figures
  ``<spec_root>/standards/archive/``       archive -1d/-2d of the standards
  ======================================  ===============================================

Writes ``<spec_root>/<target>/target.yaml`` once (target entry + a FLOYDS summary from the
lcodb spectra DB: science spectra per site and slit, nights, first/last night, standards used).
Returns ``{"target", "name", "created", "existing", "floyds": summary}``.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import yaml
from prefect import get_run_logger, task

from ava.config import cfg

TARGET_META = "target.yaml"


def spec_dirs(target: str) -> list:
    raw_root = cfg.spec_raw(target).parent
    return [raw_root / target, raw_root / "standards", cfg.spec_dir(target), cfg.spec_dir(target) / "archive",
            cfg.spec_dir(target) / "reduced", cfg.spec_dir(target) / "plots", cfg.spec_root / "standards" / "archive"]


def floyds_summary(db, ava_id: int) -> dict:
    """What the lcodb spectra DB holds for this target (offline)."""
    if db is None:
        return {"spectra_db": None}
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
        q = ("SELECT site_id, instrument_id, aperwid, COUNT(*), COUNT(DISTINCT day_obs), MIN(day_obs), MAX(day_obs) "
             "FROM frames WHERE ava_id=? AND rlevel=0 AND obstype='SPECTRUM' AND COALESCE(is_standard,0)=0 "
             "GROUP BY 1,2,3 ORDER BY 1,2,3")
        rows = con.execute(q, (int(ava_id),)).fetchall()
        std = con.execute("SELECT std_object, std_choice, COUNT(*) FROM spectrum_standards WHERE ava_id=? "
                          "GROUP BY 1,2 ORDER BY 3 DESC", (int(ava_id),)).fetchall()
        miss = con.execute("SELECT SUM(arc_id IS NULL), SUM(flat_id IS NULL) FROM spectrum_calibs c JOIN frames f "
                           "ON f.id=c.spec_id WHERE f.ava_id=? AND COALESCE(f.is_standard,0)=0", (int(ava_id),)).fetchone()
    return {
        "spectra_db": str(db),
        "by_unit": [dict(site=r[0], instrument=r[1], slit_arcsec=r[2], spectra=r[3], nights=r[4], first=r[5], last=r[6])
                    for r in rows],
        "spectra": sum(r[3] for r in rows), "nights": sum(r[4] for r in rows),
        "standards": [dict(object=r[0], choice=r[1], spectra=r[2]) for r in std],
        "without_arc": int(miss[0] or 0), "without_flat": int(miss[1] or 0),
    }


@task(name="spec-initialise", tags=["spectroscopy", "filesystem"])
def spec_initialise(target: str) -> dict:
    """Create the FLOYDS folders of ``target`` and summarise its spectra (idempotent)."""
    from ava.pipeline.tasks.download import lcodb_path

    logger = get_run_logger()
    entry = cfg.target_by_data_id(target)
    if entry is None:
        raise ValueError(f"{target!r} is not a known data_id")
    created, existing = [], []
    for d in spec_dirs(target):
        (existing if d.is_dir() else created).append(str(d))
        d.mkdir(parents=True, exist_ok=True)
    summary = floyds_summary(lcodb_path("spec"), int(entry["ava_id"]))
    meta = cfg.spec_dir(target) / TARGET_META
    if meta.exists():
        existing.append(str(meta))
    else:
        record = {**entry, "floyds": summary,
                  "initialised_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "config": str(cfg._path)}
        record = json.loads(json.dumps(record, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
        meta.write_text(yaml.safe_dump(record, sort_keys=False))
        created.append(str(meta))
    if summary.get("spectra_db") is None:
        logger.warning("%s: no lcodb spectra DB — FLOYDS summary skipped", target)
    else:
        logger.info("%s: %d FLOYDS spectra on %d nights %s; standards %s; %d without arc, %d without flat",
                    target, summary["spectra"], summary["nights"],
                    [(u["site"], u["slit_arcsec"], u["spectra"]) for u in summary["by_unit"]],
                    [(s["object"], s["spectra"]) for s in summary["standards"][:4]],
                    summary["without_arc"], summary["without_flat"])
    logger.info("Spectroscopy initialised %s (%s): %d created, %d already present",
                target, entry["name"], len(created), len(existing))
    return {"target": target, "name": entry["name"], "created": created, "existing": existing, "floyds": summary}
