"""
Per-band fractional variability of the merged (PyTICS-intercalibrated) AGN light curve.

Computed by the ``ensemble`` task right after the merged light curve is exported and
written to the AVA database:

* ``photometry_variability`` — one row per target and band (all bands, incl. Y/R/I):
  epochs, MJD span, mean flux, rms, F_var ± err, F_max/F_min (column rmax), median S/N;
* ``agn.frac_<band>`` — the legacy per-band column (u B g V r i z) in its original text
  format ("10.215%"), or "0.0" when there is no excess variance — what the website and
  older readers show as "Fractional variability".

The same step writes the recent brightness (:func:`recent_means`):

* ``photometry_recent`` — per target and band, the mean AB magnitude over the last ``nights`` *observed*
  nights (distinct UTC dates with a good epoch; default 10, ``ensemble.recent_nights``), with the number of
  epochs and the MJD range used. The mean is taken in flux and converted back to a magnitude;
* ``agn.avg_<band>`` — the legacy column (u B g V r i z) the website called "Mean mag, last 10 d".
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ava.utils.variability import variability

LEGACY_FRAC_BANDS = ("u", "B", "g", "V", "r", "i", "z")

PHOT_VAR_DDL = """
CREATE TABLE IF NOT EXISTS photometry_variability (  -- merged LCO light curve, per target and band
    data_id TEXT, filter TEXT,
    n_epochs INTEGER, mjd_first REAL, mjd_last REAL,
    mean REAL, mean_err REAL, rms REAL, fvar REAL, fvar_err REAL, rmax REAL, snr_median REAL,
    error_model TEXT, updated_utc TEXT,
    PRIMARY KEY (data_id, filter)
);
"""


def band_variability(lc: pd.DataFrame, error: str = "total", min_epochs: int = 10) -> pd.DataFrame:
    """F_var per band of the exported merged light curve (``export_merged_csv`` columns).

    error : "total" (flux_err_mJy: σ_phot ⊕ rms_t ⊕ rms_sc, conservative) or
            "random" (flux_err_random_mJy: epoch-to-epoch only).
    Bands with fewer than ``min_epochs`` good epochs are skipped.
    """
    ecol = {"total": "flux_err_mJy", "random": "flux_err_random_mJy"}[error]
    rows = []
    for band, g in lc.groupby("filter", sort=True):
        if len(g) < min_epochs:
            continue
        v = variability(g["flux_mJy"], g[ecol])
        if v.get("n", 0) < min_epochs:
            continue
        rows.append({"filter": band, "n_epochs": v["n"], "mjd_first": float(g["MJD"].min()),
                     "mjd_last": float(g["MJD"].max()), **{k: v.get(k) for k in
                     ("mean", "mean_err", "rms", "fvar", "fvar_err", "rmax", "snr_median")}})
    return pd.DataFrame(rows)


PHOT_RECENT_DDL = """
CREATE TABLE IF NOT EXISTS photometry_recent (  -- merged LCO light curve: mean over the last N observed nights
    data_id TEXT, filter TEXT,
    mag REAL, n_epochs INTEGER, n_nights INTEGER, mjd_first REAL, mjd_last REAL, updated_utc TEXT,
    PRIMARY KEY (data_id, filter)
);
"""


def recent_means(lc: pd.DataFrame, nights: int = 10) -> pd.DataFrame:
    """Per band: mean AB magnitude of the good epochs on the last ``nights`` distinct UTC dates (floor of MJD).
    Uses ``mag_AB``, or ``flux_mJy`` (AB: 3631 Jy) when the table has no magnitudes."""
    rows = []
    if "mag_AB" not in lc:
        if "flux_mJy" not in lc:
            return pd.DataFrame(rows)
        with np.errstate(divide="ignore", invalid="ignore"):
            lc = lc.assign(mag_AB=-2.5 * np.log10(lc["flux_mJy"].to_numpy(float) / 3631e3))
    for band, g in lc.groupby("filter", sort=True):
        g = g[np.isfinite(g["mag_AB"].to_numpy(float))]
        if g.empty:
            continue
        day = np.floor(g["MJD"].to_numpy(float))
        keep = np.isin(day, np.unique(day)[-nights:])
        sel = g[keep]
        flux = 10 ** (-0.4 * sel["mag_AB"].to_numpy(float))
        rows.append({"filter": band, "mag": float(-2.5 * np.log10(flux.mean())), "n_epochs": int(len(sel)),
                     "n_nights": int(np.unique(day[keep]).size), "mjd_first": float(sel["MJD"].min()),
                     "mjd_last": float(sel["MJD"].max())})
    return pd.DataFrame(rows)


def record_recent(db: Path, data_id: str, rec: pd.DataFrame) -> dict:
    """Write ``photometry_recent`` rows and the legacy ``agn.avg_<band>`` columns (bands measured only)."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(sqlite3.connect(db, timeout=60)) as con:
        con.executescript(PHOT_RECENT_DDL)
        con.execute("DELETE FROM photometry_recent WHERE data_id = ?", (data_id,))
        for r in rec.itertuples(index=False):
            con.execute("INSERT INTO photometry_recent VALUES (?,?,?,?,?,?,?,?)", (
                data_id, r.filter, r.mag, r.n_epochs, r.n_nights, r.mjd_first, r.mjd_last, now))
        cols = {r[1] for r in con.execute("PRAGMA table_info(agn)")}
        sets = {f"avg_{b}": round(float(m), 4) for b, m in zip(rec.get("filter", []), rec.get("mag", []))
                if b in LEGACY_FRAC_BANDS and f"avg_{b}" in cols}
        if sets:
            con.execute(f"UPDATE agn SET {', '.join(f'{c} = ?' for c in sets)} WHERE data_id = ?",
                        (*sets.values(), data_id))
        con.commit()
    return dict(zip(rec.get("filter", []), rec.get("mag", [])))


def legacy_frac(fvar) -> str:
    """agn.frac_<band> text format: percent with 3 decimals, "0.0" when undefined."""
    return f"{100 * float(fvar):.3f}%" if fvar is not None and np.isfinite(fvar) else "0.0"


def record_band_variability(db: Path, data_id: str, bv: pd.DataFrame, error_model: str) -> dict:
    """Write ``photometry_variability`` rows and the legacy ``agn.frac_<band>`` columns.

    Returns ``{band: fvar}``; ``agn.frac_*`` is only touched for bands that were measured.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    nan2none = lambda x: None if x is None or (isinstance(x, float) and not np.isfinite(x)) else x  # noqa: E731
    with closing(sqlite3.connect(db, timeout=60)) as con:
        con.executescript(PHOT_VAR_DDL)
        for r in bv.itertuples(index=False):
            con.execute("INSERT OR REPLACE INTO photometry_variability VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                data_id, r.filter, int(r.n_epochs), r.mjd_first, r.mjd_last, nan2none(r.mean),
                nan2none(r.mean_err), nan2none(r.rms), nan2none(r.fvar), nan2none(r.fvar_err),
                nan2none(r.rmax), nan2none(r.snr_median), error_model, now))
        cols = {r[1] for r in con.execute("PRAGMA table_info(agn)")}
        sets = {f"frac_{b}": legacy_frac(f) for b, f in zip(bv.get("filter", []), bv.get("fvar", []))
                if b in LEGACY_FRAC_BANDS and f"frac_{b}" in cols}
        if sets:
            con.execute(f"UPDATE agn SET {', '.join(f'{c} = ?' for c in sets)} WHERE data_id = ?",
                        (*sets.values(), data_id))
        con.commit()
    return {r.filter: r.fvar for r in bv.itertuples(index=False)}


def update_from_merged(db: Path, phot_dir, error: str = "total", min_epochs: int = 10,
                       error_model: str = "pytics", dry_run: bool = False,
                       recent_nights: int = 10) -> dict[str, dict]:
    """F_var of every AGN in ``db`` that has a merged light curve
    (``phot_dir(data_id)/<data_id>_LCO_merged_lightcurve.csv``) → ``photometry_variability`` +
    ``agn.frac_<band>``, and the recent means → ``photometry_recent`` + ``agn.avg_<band>``.  Keeps the main database in step with the merged light curves whichever
    database the ensemble step wrote to.  Returns ``{data_id: {band: fvar}}``."""
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)) as con:
        ids = [r[0] for r in con.execute("SELECT data_id FROM agn WHERE data_id IS NOT NULL")]
    out = {}
    for t in ids:
        csv = Path(phot_dir(t)) / f"{t}_LCO_merged_lightcurve.csv"
        if not csv.is_file():
            continue
        lc = pd.read_csv(csv, comment="#")
        qc = csv.with_name(csv.stem + "_qc" + csv.suffix)
        if error == "random" and "flux_err_random_mJy" not in lc and qc.is_file():
            # the shareable CSV keeps only total errors (Nov 2026); the random part is in the QC file
            lc = lc.merge(pd.read_csv(qc, comment="#", usecols=["frame", "flux_err_random_mJy"]), on="frame", how="left")
        rec = recent_means(lc, recent_nights)
        if not dry_run and not rec.empty:
            record_recent(db, t, rec)
        bv = band_variability(lc, error=error, min_epochs=min_epochs)
        if bv.empty:
            continue
        out[t] = (dict(zip(bv["filter"], bv["fvar"])) if dry_run
                  else record_band_variability(db, t, bv, f"{error_model}/{error}"))
    return out


def update_from_config(cfg, dry_run: bool = False) -> dict[str, dict]:
    """Pipeline entry point (publish step): settings ``ensemble.fvar_error``, ``ensemble.fvar_min_epochs``,
    ``ensemble.recent_nights``."""
    ec = cfg._raw.get("ensemble", {}) or {}
    return update_from_merged(cfg.db_path, cfg.phot_dir, str(ec.get("fvar_error", "total")),
                              int(ec.get("fvar_min_epochs", 10)), str(ec.get("error_model", "fitted")), dry_run,
                              int(ec.get("recent_nights", 10)))
