"""
Per-band fractional variability of the merged (PyTICS-intercalibrated) AGN light curve.

Computed by the ``ensemble`` task right after the merged light curve is exported and
written to the AVA database:

* ``photometry_variability`` — one row per target and band (all bands, incl. Y/R/I):
  epochs, MJD span, mean flux, rms, F_var ± err, F_max/F_min (column rmax), median S/N;
* ``agn.frac_<band>`` — the legacy per-band column (u B g V r i z) in its original text
  format ("10.215%"), or "0.0" when there is no excess variance — what the website and
  older readers show as "Fractional variability".
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
