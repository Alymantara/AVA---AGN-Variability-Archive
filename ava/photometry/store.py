"""
ava.photometry.store — where calibrated photometry lives.

* ``frame_qc`` (SQLite, the photometry database): ONE row per frame — every
  frame-level number (time, filter, camera, airmass, seeing, background, WCS,
  aperture, zero point, QC).  Nothing frame-level is repeated elsewhere.
* ``<phot_dir>/measurements.parquet``: one row per (frame, star) at the
  science aperture — all matched field stars AND the AGN (``is_agn``) — the
  PyTICS input.  Keyed by ``frame`` (archive basename) and ``star_id`` (Gaia
  DR3 source_id; -1 for an AGN without a Gaia counterpart).
* ``<phot_dir>/agn_lightcurve.parquet`` + ``.csv``: the calibrated AGN light
  curve (product; built from the two above).

:func:`load_pytics` joins measurements and frame_qc into the long table PyTICS
expects.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import numpy as np
import pandas as pd

FRAME_QC_COLUMNS = {
    "frame": "TEXT PRIMARY KEY",       # archive basename, e.g. elp1m006-fa07-20201206-0522-e91
    "data_id": "TEXT",
    "mjd_mid": "REAL",                 # mid-exposure MJD
    "day_obs": "TEXT",
    "filter": "TEXT", "camera": "TEXT", "tel": "TEXT", "site": "TEXT",
    "exptime": "REAL",
    "airmass": "REAL",                 # true airmass (the legacy files stored airmass - 1)
    "seeing_hdr": "REAL",              # header L1FWHM (arcsec)
    "saturate": "REAL",                # header SATURATE (ADU) — with the size below, all a recalibration
    "naxis1": "INTEGER", "naxis2": "INTEGER",   # needs from the image, so it can run after the image is deleted
    "fwhm_arcsec": "REAL",             # median FWHM of clean matched stars
    "background": "REAL",              # median SExtractor BACKGROUND of clean stars (ADU)
    "ellipticity": "REAL",             # median 1 - 1/ELONGATION of clean stars
    "n_detections": "INTEGER", "n_matched": "INTEGER",
    "wcs_offset_arcsec": "REAL", "wcs_repaired": "INTEGER",
    "n_apertures": "INTEGER", "aperture_index": "INTEGER", "aperture_px": "REAL", "aperture_arcsec": "REAL",
    "zp": "REAL", "zp_err": "REAL", "zp_scatter": "REAL", "zp_chi2nu": "REAL",
    "n_zp": "INTEGER", "n_zp_candidates": "INTEGER", "colour_slope": "REAL",
    "agn_matched": "INTEGER", "agn_flags": "INTEGER",
    "agn_peak": "REAL",                # AGN FLUX_MAX + BACKGROUND (ADU): QC flag agn_saturated vs saturate
    "qc_flags": "TEXT",                # comma-separated reasons; '' = clean
    "qc_pass": "INTEGER",
    "pipeline_version": "TEXT", "processed_utc": "TEXT",
}

_DDL = ("CREATE TABLE IF NOT EXISTS frame_qc (" + ", ".join(f'"{k}" {v}' for k, v in FRAME_QC_COLUMNS.items())
        + "); CREATE INDEX IF NOT EXISTS ix_frame_qc_target ON frame_qc(data_id, filter, mjd_mid);")


def _plain(v):
    if v is None or (isinstance(v, float) and not np.isfinite(v)) or v is pd.NA:
        return None
    return v.item() if hasattr(v, "item") else v


#: Frame metadata calibration takes from the image header (``process.header_meta``), all kept in ``frame_qc``.
META_COLUMNS = ("filter", "exptime", "mjd_mid", "day_obs", "airmass", "seeing_hdr", "saturate", "naxis1", "naxis2",
                "site")


def _ensure_table(con) -> None:
    """Create ``frame_qc`` if needed and add columns introduced since the table was made."""
    con.executescript(_DDL)
    have = {r[1] for r in con.execute("PRAGMA table_info(frame_qc)")}
    for c, t in FRAME_QC_COLUMNS.items():
        if c not in have:
            con.execute(f'ALTER TABLE frame_qc ADD COLUMN "{c}" {t}')


def write_frame_qc(db: Path, rows: list[dict]) -> None:
    """Upsert frame rows into ``frame_qc`` (creates the table if needed)."""
    if not rows:
        return
    cols = list(FRAME_QC_COLUMNS)
    with closing(sqlite3.connect(db, timeout=60)) as con:
        _ensure_table(con)
        con.executemany(
            f"INSERT OR REPLACE INTO frame_qc ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [tuple(_plain(r.get(c)) for c in cols) for r in rows])
        con.commit()


def frame_meta(db: Path, data_id: str) -> dict[str, dict]:
    """frame -> the image-header metadata stored in ``frame_qc`` (what ``process.header_meta`` returns), for
    recalibrating frames whose image has been deleted."""
    fq = read_frame_qc(db, data_id)
    if fq.empty:
        return {}
    for c in META_COLUMNS:
        if c not in fq:
            fq[c] = np.nan
    return {r["frame"]: {c: r[c] for c in META_COLUMNS} for r in fq.to_dict("records")}


def listing_meta(lcodb_db: Path, data_id: str, camera_defaults: dict | None = None) -> dict[str, dict]:
    """frame -> metadata from the LCO archive listing (lcodb photometry ``frames``), for catalogues whose image
    is not available (legacy catalogues).  Saturation level and image size are not in the listing: they come
    from ``camera_defaults`` (2-letter camera prefix -> {saturate, naxis1, naxis2}), else stay empty."""
    if lcodb_db is None or not Path(lcodb_db).exists():
        return {}
    with closing(sqlite3.connect(f"file:{lcodb_db}?mode=ro", uri=True)) as con:
        rows = con.execute("SELECT basename, filter, exptime, mjd_obs, day_obs, site_id, "
                           "COALESCE(airmass, airmass_calc), l1fwhm, instrument_id FROM frames "
                           "WHERE ava_data_id = ? AND rlevel = 91", (data_id,)).fetchall()
    out = {}
    for b, filt, exp, mjd, day, site, am, fwhm, inst in rows:
        if exp is None or mjd is None or not filt:
            continue
        d = (camera_defaults or {}).get(str(inst or b.split("-")[1])[:2].lower()) or {}
        out[b] = dict(filter=str(filt).replace("zs*diffuser", "zs").strip(), exptime=float(exp),
                      mjd_mid=float(mjd) + float(exp) / 86400.0 / 2.0, day_obs=str(day or "").replace("-", ""),
                      airmass=am, seeing_hdr=fwhm, saturate=d.get("saturate"), naxis1=d.get("naxis1"),
                      naxis2=d.get("naxis2"), site=site or b[:3])
    return out


def meta_complete(m: dict | None) -> bool:
    """Everything a recalibration needs from the image is stored (time, filter, saturation, image size)."""
    return bool(m) and all(m.get(c) is not None and not (isinstance(m.get(c), float) and not np.isfinite(m[c]))
                           for c in ("filter", "exptime", "mjd_mid", "saturate", "naxis1", "naxis2"))


def fill_frame_meta(db: Path, metas: dict[str, dict]) -> int:
    """Complete existing ``frame_qc`` rows with image-header values (frame -> ``process.header_meta`` dict);
    only empty fields are filled."""
    if not metas:
        return 0
    with closing(sqlite3.connect(db, timeout=60)) as con:
        _ensure_table(con)
        for frame, m in metas.items():
            con.execute("UPDATE frame_qc SET " + ", ".join(f'"{c}" = COALESCE("{c}", ?)' for c in META_COLUMNS)
                        + " WHERE frame = ?", tuple(_plain(m.get(c)) for c in META_COLUMNS) + (frame,))
        con.commit()
    return len(metas)


def read_frame_qc(db: Path, data_id: str) -> pd.DataFrame:
    if not Path(db).exists():
        return pd.DataFrame(columns=list(FRAME_QC_COLUMNS))
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        has = con.execute("SELECT name FROM sqlite_master WHERE name='frame_qc'").fetchone()
        if not has:
            return pd.DataFrame(columns=list(FRAME_QC_COLUMNS))
        return pd.read_sql("SELECT * FROM frame_qc WHERE data_id = ? ORDER BY mjd_mid", con, params=[data_id])


#: measurements.parquet schema (one row per frame x star, science aperture).
MEAS_DTYPES = {"frame": "string", "star_id": "int64", "is_agn": "bool", "mag_inst": "float32",
               "magerr": "float32", "x": "float32", "y": "float32", "sex_flags": "int16",
               "sep_arcsec": "float32", "used_in_zp": "bool"}


def update_measurements(path: Path, new: pd.DataFrame) -> int:
    """Replace the rows of the frames in ``new`` and write atomically. Returns total rows."""
    new = new[list(MEAS_DTYPES)].astype(MEAS_DTYPES)
    if Path(path).exists():
        old = pd.read_parquet(path)
        old = old[~old["frame"].isin(set(new["frame"]))]
        new = pd.concat([old, new], ignore_index=True)
    new = new.sort_values(["frame", "star_id"]).reset_index(drop=True)
    tmp = Path(path).with_suffix(".parquet.tmp")
    new.to_parquet(tmp, compression="zstd", index=False)
    tmp.replace(path)
    return len(new)


def write_agn_lightcurve(phot_dir: Path, db: Path, data_id: str) -> pd.DataFrame:
    """AGN rows of measurements.parquet + frame_qc -> agn_lightcurve.parquet / .csv."""
    meas = pd.read_parquet(Path(phot_dir) / "measurements.parquet", filters=[("is_agn", "==", True)])
    fq = read_frame_qc(db, data_id)
    lc = meas.merge(fq, on="frame", how="inner")
    lc["mag"] = lc["mag_inst"] + lc["zp"]
    lc["mag_err"] = np.hypot(lc["magerr"], lc["zp_err"])
    lc = lc[["frame", "mjd_mid", "filter", "camera", "tel", "mag", "mag_err",
             "mag_inst", "magerr", "zp", "zp_err", "qc_pass", "qc_flags"]].sort_values(["filter", "mjd_mid"])
    lc.to_parquet(Path(phot_dir) / "agn_lightcurve.parquet", compression="zstd", index=False)
    lc.to_csv(Path(phot_dir) / "agn_lightcurve.csv", index=False, float_format="%.6f")
    return lc


def load_pytics(phot_dir: Path, db: Path, data_id: str, filt: str | None = None,
                qc_only: bool = True) -> pd.DataFrame:
    """The long table PyTICS takes: one row per (frame, star) incl. the AGN.

    Columns: MJD, Filter, star_id, is_agn, mag_inst, magerr, telid, camera,
    airmass, seeing — read from measurements.parquet joined with frame_qc.
    """
    fq = read_frame_qc(db, data_id)
    if filt:
        fq = fq[fq["filter"] == filt]
    if qc_only:
        fq = fq[fq["qc_pass"] == 1]
    if fq.empty:
        # No (passing) frame in this filter, e.g. Y for most targets. pyarrow rejects an empty "in" filter
        # ("large_string vs null", host run 18 Nov 2026), so return the empty table directly.
        cols = list(MEAS_DTYPES) + ["MJD", "Filter", "telid", "camera", "airmass", "seeing"]
        return pd.DataFrame({c: pd.Series(dtype=MEAS_DTYPES.get(c, "object")) for c in cols})
    meas = pd.read_parquet(Path(phot_dir) / "measurements.parquet",
                           filters=[("frame", "in", list(fq["frame"]))] if len(fq) < 50000 else None)
    # rows written before B11 (19 Nov 2026) may hold SExtractor's 99 "no measurement" magnitude / error
    ok = np.isfinite(meas["mag_inst"]) & np.isfinite(meas["magerr"]) & (meas["mag_inst"] < 90) & (meas["magerr"] < 90)
    meas = meas[ok]
    t = meas.merge(fq[["frame", "mjd_mid", "filter", "tel", "camera", "airmass", "fwhm_arcsec"]], on="frame")
    return t.rename(columns={"mjd_mid": "MJD", "filter": "Filter", "tel": "telid",
                             "fwhm_arcsec": "seeing"}).sort_values(["MJD", "star_id"]).reset_index(drop=True)
