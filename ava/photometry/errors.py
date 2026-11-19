"""
Empirical error model for the PyTICS AGN light curve (opt-in, under verification).

PyTICS quotes, for each AGN epoch,  σ² = σ_phot² + rms_t² + rms_sc².  The AGN pair test
(docs/figures/pytics/pytics_21) shows that shape is wrong: pairs of epochs < 1 h apart on
the same camera scatter *more* than the quoted random error when it is small (good
nights: no floor) and *much less* when it is large (rms_t, the extra scatter of the
comparison stars, does not apply in full to the AGN).  This module fits, per filter and
camera family (camera-name prefix: "fa" Sinistro, "ep" MuSCAT, ...)

    σ_rand² = (k σ_phot)² + (β rms_t)² + s0²            same-camera pairs < max_dt
    σ_tot²  = σ_rand² + s_cam²                          different-camera pairs < max_dt_cross

k, β, s0 come from a Student-t likelihood of the pair differences, rescaled so the robust σ
of Δm / √(σ₁²+σ₂²) is 1; s_cam (per filter) makes the same
true for pairs from different cameras, i.e. it is the camera-to-camera / night-to-night
calibration error that same-camera pairs cannot see.  When a group has too few pairs
the filter's pooled fit is used, then the PyTICS model (k = β = 1, s0 = 0).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq, minimize

PYTICS = dict(k=1.0, beta=1.0, s0=0.0)


def rob(x) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(1.4826 * np.median(np.abs(x - np.median(x)))) if len(x) else np.nan


def family(camera) -> pd.Series:
    """camera family = the alphabetic prefix of the camera name (fa05 -> fa, ep04 -> ep)."""
    return pd.Series(camera, dtype=str).str.extract(r"^([A-Za-z]+)")[0].fillna("?").to_numpy()


def _var(th, p, t):
    return (th["k"] * p) ** 2 + (th["beta"] * t) ** 2 + th["s0"] ** 2


def pairs(lc: pd.DataFrame, max_dt: float, same: bool, mag: str = "mag") -> pd.DataFrame:
    """Pairs of good epochs (same filter) within ``max_dt`` days: consecutive epochs of one
    scope (``same=True``) or epochs of different scopes up to 3 neighbours apart."""
    x = lc[lc["good"] & np.isfinite(lc[mag].to_numpy(float))].copy()   # a filter without a ZP has NaN mags
    x["fam"] = family(x["camera"])
    out = []
    groups = x.groupby(["Filter", "scope"]) if same else x.groupby("Filter")
    for key, h in groups:
        h = h.sort_values("MJD")
        t, m = h["MJD"].to_numpy(), h[mag].to_numpy()
        sc, fam = h["scope"].to_numpy(), h["fam"].to_numpy()
        p, r = h["magerr"].to_numpy(float), h["rms_t"].to_numpy(float)
        for j in ((1,) if same else (1, 2, 3)):
            k = np.arange(len(h) - j)
            ok = (t[k + j] - t[k] < max_dt) & ((sc[k] == sc[k + j]) if same else (sc[k] != sc[k + j]))
            k = k[ok]
            out.append(pd.DataFrame({
                "Filter": h["Filter"].iloc[0], "fam1": fam[k], "fam2": fam[k + j], "scope1": sc[k], "scope2": sc[k + j],
                "MJD": t[k], "dt": t[k + j] - t[k], "dm": m[k + j] - m[k],
                "p1": p[k], "p2": p[k + j], "t1": r[k], "t2": r[k + j]}))
    cols = ["Filter", "fam1", "fam2", "scope1", "scope2", "MJD", "dt", "dm", "p1", "p2", "t1", "t2"]
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=cols)


def fit_scale(P: pd.DataFrame) -> dict:
    """one factor on the PyTICS random error (k = β, s0 = 0): robust σ_z = 1."""
    z0 = P.dm / np.sqrt(P.p1 ** 2 + P.t1 ** 2 + P.p2 ** 2 + P.t2 ** 2)
    c = rob(z0)
    return dict(k=c, beta=c, s0=0.0)


def error_range(P: pd.DataFrame) -> float:
    """p90 / p10 of the PyTICS random error of the pairs (dynamic range the 3-parameter fit needs)."""
    e = np.sqrt(P.p1 ** 2 + P.t1 ** 2 + P.p2 ** 2 + P.t2 ** 2)
    return float(np.nanpercentile(e, 90) / np.nanpercentile(e, 10))


def fit_random(P: pd.DataFrame, nu: float = 4.0) -> dict:
    """k, β, s0: Student-t (ν = 4) likelihood of the pair differences (robust to the tails,
    and far steadier than matching robust σ per error bin: on synthetic data the predicted σ
    is within ~20 % in every error quartile with 800 pairs), then one common factor so that
    the robust σ_z = 1 (the t scale is not a Gaussian σ).  k, β and s0 are partly degenerate:
    trust the resulting σ, not the individual numbers."""
    p1, p2, t1, t2, dm = (P[c].to_numpy(float) for c in ("p1", "p2", "t1", "t2", "dm"))

    def unpack(x):
        return dict(k=abs(x[0]), beta=abs(x[1]), s0=abs(x[2]))

    def nll(x):
        th = unpack(x)
        v = _var(th, p1, t1) + _var(th, p2, t2) + 1e-14
        return np.sum(0.5 * np.log(v) + (nu + 1) / 2 * np.log1p(dm ** 2 / (nu * v)))

    best = None
    for x0 in ([1.0, 1.0, 1e-3], [1.0, 0.3, 2e-3], [1.0, 0.1, 1e-3]):
        r = minimize(nll, x0, method="Nelder-Mead", options=dict(xatol=1e-7, fatol=1e-9, maxiter=6000))
        if best is None or r.fun < best.fun:
            best = r
    th = unpack(best.x)
    c = rob(dm / np.sqrt(_var(th, p1, t1) + _var(th, p2, t2)))
    return {k: v * c for k, v in th.items()}


def sigma_rand(lc: pd.DataFrame, table: pd.DataFrame) -> np.ndarray:
    """σ_rand per row of ``lc`` from the fitted table (Filter, family -> k, beta, s0)."""
    key = pd.MultiIndex.from_arrays([lc["Filter"].to_numpy(), family(lc["camera"])])
    t = table.set_index(["Filter", "family"])
    th = {c: t[c].reindex(key).astype(float).fillna(PYTICS[c]).to_numpy() for c in ("k", "beta", "s0")}
    return np.sqrt(_var(th, lc["magerr"].to_numpy(float), lc["rms_t"].to_numpy(float)))


def fit_s_cam(Pc: pd.DataFrame, sr1, sr2, s_max: float = 0.5) -> float:
    """camera-to-camera term: robust σ of Δm / √(σr₁²+σr₂²+2 s²) = 1 (0 if already ≤ 1 or not
    computable; ``s_max`` if even that is not enough, instead of a brentq error)."""
    f = lambda s: rob(Pc.dm / np.sqrt(sr1 ** 2 + sr2 ** 2 + 2 * s ** 2)) - 1.0
    if len(Pc) == 0:
        return 0.0
    f0 = f(0.0)
    if not np.isfinite(f0) or f0 <= 0:
        return 0.0
    if f(s_max) > 0:
        return float(s_max)
    return float(brentq(f, 0.0, s_max))


def fit_error_model(lc: pd.DataFrame, *, max_dt: float = 1 / 24, max_dt_cross: float = 0.25,
                    min_pairs: int = 150, min_cross_pairs: int = 30, min_error_range: float = 2.5,
                    mag: str = "mag") -> pd.DataFrame:
    """Fit the table (one row per filter x camera family, plus s_cam per filter).  A group
    whose quoted errors span less than ``min_error_range`` (p90/p10) cannot separate k, β and
    s0 (MuSCAT: 1.5-3 mmag only) and gets a single scale factor on the PyTICS error."""
    P = pairs(lc, max_dt, same=True, mag=mag)
    rows = []
    for f, Pf in P.groupby("Filter"):
        pooled = fit_random(Pf) if len(Pf) >= min_pairs else dict(PYTICS)
        src_pooled = "filter" if len(Pf) >= min_pairs else "pytics"
        for fam, Q in Pf.groupby("fam1"):
            if len(Q) < min_pairs:
                th, src = pooled, src_pooled
            elif error_range(Q) < min_error_range:
                th, src = fit_scale(Q), "scale"
            else:
                th, src = fit_random(Q), "fit"
            rows.append(dict(Filter=f, family=fam, n_pairs=len(Q), error_range=error_range(Q), source=src, **th))
    table = pd.DataFrame(rows, columns=["Filter", "family", "n_pairs", "error_range", "source", "k", "beta", "s0"])
    # camera-to-camera term from different-camera pairs, per filter
    Pc = pairs(lc, max_dt_cross, same=False, mag=mag)
    s_cam = {}
    for f, Q in Pc.groupby("Filter"):
        if len(Q) < min_cross_pairs:
            continue
        a = pd.DataFrame({"Filter": f, "camera": Q.scope1.str.split("-").str[-1], "magerr": Q.p1, "rms_t": Q.t1})
        b = pd.DataFrame({"Filter": f, "camera": Q.scope2.str.split("-").str[-1], "magerr": Q.p2, "rms_t": Q.t2})
        s_cam[f] = fit_s_cam(Q, sigma_rand(a, table), sigma_rand(b, table))
    table["s_cam"] = table["Filter"].map(s_cam).fillna(0.0)
    table["n_cross_pairs"] = table["Filter"].map(Pc.groupby("Filter").size()).fillna(0).astype(int)
    return table


def apply_error_model(lc: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """Add mag_err_model_rand (epoch-to-epoch) and mag_err_model (+ camera term) columns."""
    out = lc.copy()
    sr = sigma_rand(out, table)
    sc = out["Filter"].map(table.groupby("Filter")["s_cam"].first()).fillna(0.0).to_numpy()
    out["mag_err_model_rand"] = sr
    out["mag_err_model"] = np.sqrt(sr ** 2 + sc ** 2)
    return out
