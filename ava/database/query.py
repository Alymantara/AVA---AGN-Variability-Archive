"""
ava.database.query — read-only access to the AVA database (``cfg.db_path``).

The SQLite database is the hub for local information; ``targets.yaml`` and
``ava.csv`` are reference copies.  This module is the default way for the
pipeline to read it.  Connections are opened read-only (``mode=ro``), so
nothing here can modify the database.

Tables used (built by ``tools/ava_crossmatch.py``)
--------------------------------------------------
agn          one row per AVA source; ``ra_deg``/``dec_deg`` = the nucleus
agn_lco      LCO / FLOYDS statistics per source (``db_*`` columns)
lco_targets  every LCO OBJECT spelling -> AVA id, with the median *requested
             pointing* (``obj_ra``/``obj_dec``) and frame counts

Positions: the AGN is always ``agn.ra_deg/dec_deg``.  The telescope may point
elsewhere (offset fields, e.g. NGC 4395: 4.4' away); those pointings are the
``lco_targets`` rows of that source.

    from ava.database import query as dbq
    t = dbq.target("NGC_4395")
    t["ra_deg"], t["dec_deg"]          # nucleus
    t["pointings"]                     # one dict per LCO OBJECT spelling
    dbq.field_radius_arcmin(t, 20.0)   # cone covering every pointing's frame
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import numpy as np
import pandas as pd

from ava.config import cfg


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Read-only connection to the AVA database."""
    path = Path(path or cfg.db_path)
    if not path.exists():
        raise FileNotFoundError(f"AVA database not found: {path} (paths.database)")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def agn_table(path: Path | None = None) -> pd.DataFrame:
    """The ``agn`` table joined with its LCO statistics (``agn_lco``)."""
    with closing(connect(path)) as con:
        return pd.read_sql(
            "SELECT a.*, l.* FROM agn a LEFT JOIN agn_lco l ON l.db_ava_id = a.id ORDER BY a.id", con
        )


def lco_names(path: Path | None = None) -> pd.DataFrame:
    """All LCO OBJECT spellings linked to an AVA source (``lco_targets``)."""
    with closing(connect(path)) as con:
        df = pd.read_sql("SELECT * FROM lco_targets WHERE ava_id IS NOT NULL", con)
    df["ava_id"] = df["ava_id"].astype(int)
    return df


def _pointings(rows: pd.DataFrame, ra: float, dec: float) -> list[dict]:
    from astropy.coordinates import SkyCoord

    out = []
    c = SkyCoord(ra, dec, unit="deg")
    for r in rows.itertuples():
        d = dict(object=r.object, n_phot=int(r.n_phot or 0), n_spec=int(r.n_spec or 0),
                 obj_ra=r.obj_ra, obj_dec=r.obj_dec, matched_by=r.matched_by, review=r.review or None)
        if pd.notna(r.obj_ra) and pd.notna(r.obj_dec):
            d["offset_arcmin"] = float(SkyCoord(r.obj_ra, r.obj_dec, unit="deg").separation(c).arcmin)
        else:
            d["offset_arcmin"] = None
        out.append(d)
    return sorted(out, key=lambda d: -d["n_phot"])


def _flag(v) -> bool | None:
    """0/1 column -> bool; NULL -> None (not set)."""
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else bool(int(v))


def _int_or_none(v) -> int | None:
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else int(v)


def targets(path: Path | None = None) -> list[dict]:
    """One dict per AVA source, with nucleus position, LCO names and pointings."""
    agn = agn_table(path)
    names = lco_names(path)
    out = []
    for a in agn.itertuples(index=False):
        if a.ra_deg in (None, "") or a.dec_deg in (None, "") or pd.isna(a.ra_deg) or pd.isna(a.dec_deg):
            continue  # no decimal coordinates yet (e.g. SDSS-RM201): not usable by the pipeline
        rows = names[names["ava_id"] == a.id]
        pts = _pointings(rows, a.ra_deg, a.dec_deg)
        out.append(dict(
            ava_id=int(a.id), name=a.name, data_id=a.data_id, simbad_name=a.simbad_name,
            ra_deg=float(a.ra_deg), dec_deg=float(a.dec_deg),
            redshift=a.redshift, ebv=a.ebv,
            lco_active=_flag(getattr(a, "lco_active", None)),
            lt_active=_flag(getattr(a, "lt_active", None)),
            agn_gaia_dr3_id=_int_or_none(getattr(a, "agn_gaia_dr3_id", None)),
            lco_names=[p["object"] for p in pts],
            pointings=pts,
            n_phot=int(sum(p["n_phot"] for p in pts)),
            n_spec=int(sum(p["n_spec"] for p in pts)),
            lco_end=getattr(a, "db_lco_end", None),
            floyds_end=getattr(a, "db_floyds_end", None),
        ))
    return out


def target(data_id: str, path: Path | None = None) -> dict | None:
    """The :func:`targets` entry for ``data_id`` (case-sensitive), or None."""
    for t in targets(path):
        if t["data_id"] == data_id:
            return t
    return None


def target_by_lco_name(obj: str, path: Path | None = None) -> dict | None:
    """Route a FITS OBJECT keyword to its AVA source (exact spelling first,
    then case/space/underscore-insensitive)."""
    norm = lambda s: str(s).upper().replace(" ", "").replace("_", "")  # noqa: E731
    ts = targets(path)
    for match in (lambda n: n == obj, lambda n: norm(n) == norm(obj)):
        for t in ts:
            if any(match(n) for n in t["lco_names"]):
                return t
    return None


def field_radius_arcmin(t: dict, camera_radius_arcmin: float, min_frames: int = 1) -> float:
    """Cone radius around the nucleus covering every pointing with frames.

    = ``camera_radius_arcmin`` + the largest offset of any LCO pointing that
    has at least ``min_frames`` photometry frames.
    """
    offs = [p["offset_arcmin"] for p in t["pointings"]
            if p["n_phot"] >= min_frames and p["offset_arcmin"] is not None]
    return float(camera_radius_arcmin + (max(offs) if offs else 0.0))
