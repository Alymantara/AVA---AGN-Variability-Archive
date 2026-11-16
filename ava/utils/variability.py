"""
Variability statistics shared by photometry and spectroscopy.

``variability(f, e)``: mean, rms, fractional variability F_var (excess variance)
with the Vaughan et al. (2003, MNRAS 345, 1271; eq. 11) uncertainty, and the
max/min flux ratio F_max/F_min (key and DB column ``rmax``; labelled F_max/F_min,
not R_max, so it is not confused with a CCF peak coefficient r_max).
Identical to ``ava.spectroscopy.lines.variability`` so the photometric and Hβ
numbers are directly comparable.
"""

from __future__ import annotations

import numpy as np


def variability(f, e) -> dict:
    """mean, rms, F_var ± err (NaN when the scatter is below the errors), R_max, median S/N."""
    f, e = np.asarray(f, float), np.asarray(e, float)
    ok = np.isfinite(f) & np.isfinite(e)
    f, e = f[ok], e[ok]
    n = len(f)
    if n < 3:
        return {"n": n}
    mean, s2 = float(f.mean()), float(f.var(ddof=1))
    err2 = float(np.mean(e ** 2))
    excess = s2 - err2
    fvar = float(np.sqrt(excess) / mean) if excess > 0 and mean > 0 else np.nan
    fvar_err = np.nan
    if np.isfinite(fvar):
        fvar_err = float(np.sqrt((np.sqrt(1 / (2 * n)) * err2 / (mean ** 2 * fvar)) ** 2
                                 + (np.sqrt(err2 / n) / mean) ** 2))
    return {"n": n, "mean": mean, "rms": float(np.sqrt(s2)), "mean_err": float(np.sqrt(err2)),
            "fvar": fvar, "fvar_err": fvar_err, "rmax": float(f.max() / f.min()) if f.min() > 0 else np.nan,
            "snr_median": float(np.median(f / e))}
