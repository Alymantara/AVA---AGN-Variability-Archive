"""
ava.photometry.intercal — flux-flux intercalibration between telescopes / cameras.

PyTICS makes the comparison STARS agree between scopes (DMAGS, per-epoch
DMAGT).  The AGN can still disagree because it is extended: a camera with a
smaller aperture in arcsec (MuSCAT 8.9" vs Sinistro 10.5") or a different PSF
captures a different fraction of the host galaxy, i.e. an ADDITIVE flux offset
that a magnitude shift cannot remove (a constant Δmag would scale the variable
part too).  Per filter and scope

    F_scope(t) = a · F_ref(t) + b          (flux, mJy)

against the reference light curve (all other scopes of the reference camera
family, nightly means, linearly interpolated to the scope's nights when the
gap is short).  ``b`` is the host-flux difference; ``a`` = 1 if the stars fixed
the scale.  Correction: F' = (F - b) / a, errors scaled by 1/a.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

AB_MJY = 16.4          # m_AB = 16.4  <->  1 mJy (3631 Jy zero point)


def to_mjy(mag, err=None):
    f = 10 ** (-0.4 * (np.asarray(mag, float) - AB_MJY))
    return (f, f * np.asarray(err, float) * np.log(10) / 2.5) if err is not None else f


def to_mag(f, ferr=None):
    m = AB_MJY - 2.5 * np.log10(np.asarray(f, float))
    return (m, 2.5 / np.log(10) * np.asarray(ferr, float) / np.asarray(f, float)) if ferr is not None else m


def nightly(lc: pd.DataFrame, by=("scope",)) -> pd.DataFrame:
    """Inverse-variance nightly means in flux; columns MJD, F, Ferr, n (+ by)."""
    x = lc.copy()
    x["F"], x["Ferr"] = to_mjy(x["mag"], x["mag_err"])
    x["night"] = np.floor(x["MJD"] - 0.5).astype(int)
    x["w"] = 1 / x["Ferr"] ** 2
    x["wt"], x["wf"] = x["w"] * x["MJD"], x["w"] * x["F"]
    g = x.groupby([*by, "night"])[["w", "wt", "wf"]].sum()
    out = pd.DataFrame({"MJD": g["wt"] / g["w"], "F": g["wf"] / g["w"], "Ferr": 1 / np.sqrt(g["w"]),
                        "n": x.groupby([*by, "night"]).size()}).reset_index()
    return out


def _interp(ref: pd.DataFrame, t: np.ndarray, max_gap: float):
    """Reference flux at times t (linear between nightly means, gap < max_gap)."""
    r = ref.sort_values("MJD")
    tm, F, E = r["MJD"].to_numpy(), r["F"].to_numpy(), r["Ferr"].to_numpy()
    j = np.searchsorted(tm, t)
    ok = (j > 0) & (j < len(tm))
    j = np.clip(j, 1, len(tm) - 1)
    t0, t1 = tm[j - 1], tm[j]
    gap_ok = ok & ((t1 - t0) < max_gap)
    near = np.minimum(np.abs(t - t0), np.abs(t1 - t))
    w = np.where(t1 > t0, (t - t0) / np.where(t1 > t0, t1 - t0, 1), 0)
    f = (1 - w) * F[j - 1] + w * F[j]
    e = np.sqrt(((1 - w) * E[j - 1]) ** 2 + (w * E[j]) ** 2)
    good = gap_ok | (near < 0.3)
    return f, e, good


def fit_linear(x, xe, y, ye, clip=4.0, n_iter=10):
    """y = a x + b with errors on both (effective-variance weights), clipped.
    Returns a, a_err, b, b_err, chi2nu, mask."""
    use = np.isfinite(x) & np.isfinite(y)
    a, b = 1.0, 0.0
    for _ in range(n_iter):
        w = 1 / (ye ** 2 + a ** 2 * xe ** 2)
        A = np.vstack([x, np.ones_like(x)]).T
        cov = np.linalg.inv(A[use].T @ (A[use] * w[use, None]))
        a, b = cov @ (A[use].T @ (w[use] * y[use]))
        r = (y - a * x - b) * np.sqrt(1 / (ye ** 2 + a ** 2 * xe ** 2))
        chi = np.sum(r[use] ** 2) / max(use.sum() - 2, 1)
        s = 1.4826 * np.median(np.abs(r[use]))
        new = np.isfinite(r) & (np.abs(r) < clip * max(s, 1.0))
        if (new == use).all():
            break
        use = new
    ae, be = np.sqrt(np.diag(cov)) * np.sqrt(max(chi, 1.0))
    return float(a), float(ae), float(b), float(be), float(chi), use


def intercalibrate(lc: pd.DataFrame, ref_scopes, scopes=None, max_gap: float = 3.0, min_pairs: int = 10) -> pd.DataFrame:
    """Flux-flux fit of every scope (per filter) against the reference scopes."""
    rows = []
    if "good" in lc:
        lc = lc[lc["good"]]
    for f, lf in lc.groupby("Filter"):
        nt = nightly(lf)
        for k in (scopes or sorted(lf["scope"].unique())):
            ref = nightly(lf[lf["scope"].isin(ref_scopes) & (lf["scope"] != k)], by=())
            me = nt[nt["scope"] == k]
            if len(me) < min_pairs or len(ref) < min_pairs:
                continue
            fr, fre, good = _interp(ref, me["MJD"].to_numpy(), max_gap)
            if good.sum() < min_pairs:
                continue
            x, xe = fr[good], fre[good]
            y, ye = me["F"].to_numpy()[good], me["Ferr"].to_numpy()[good]
            a, ae, b, be, chi, use = fit_linear(x, xe, y, ye)
            # pure additive (a = 1: the stars fixed the scale): y = x + b1
            w1 = 1 / (ye ** 2 + xe ** 2)
            b1 = float(np.sum(w1[use] * (y - x)[use]) / np.sum(w1[use]))
            chi1 = float(np.sum(w1[use] * ((y - x)[use] - b1) ** 2) / max(use.sum() - 1, 1))
            b1e = float(np.sqrt(max(chi1, 1.0) / np.sum(w1[use])))
            # magnitude-only alternative: y = c x  (a constant Δmag)
            c = np.sum(x * y / ye ** 2) / np.sum(x * x / ye ** 2)
            rows.append(dict(filter=f, scope=k, n_pairs=int(good.sum()), n_used=int(use.sum()), a=a, a_err=ae,
                             b=b, b_err=be, chi2nu=chi, b1=b1, b1_err=b1e, chi2nu_b1=chi1,
                             dmag_const=float(-2.5 * np.log10(c)),
                             F_mean=float(np.mean(y)), b_frac=float(b / np.mean(y)),
                             rms_before=float(np.std((y - x)[use])), rms_after=float(np.std((y - a * x - b)[use])),
                             rms_const=float(np.std((y - c * x)[use])),
                             rms_b1=float(np.std((y - x - b1)[use]))))
    return pd.DataFrame(rows)


def seasons(mjd, gap_days: float = 60.0) -> np.ndarray:
    """Observing-season index: a new season starts after a gap > ``gap_days`` in ``mjd``."""
    t = np.asarray(mjd, float)
    order = np.argsort(t)
    s = np.empty(len(t), int)
    s[order] = np.concatenate([[0], np.cumsum(np.diff(t[order]) > gap_days)]) if len(t) else []
    return s


def intercalibrate_by_season(lc: pd.DataFrame, ref_scopes, scopes, season_col: str = "season",
                             max_gap: float = 3.0, min_pairs: int = 10) -> pd.DataFrame:
    """``intercalibrate`` of ``scopes`` vs ``ref_scopes`` in each season separately; seasons
    with fewer than ``min_pairs`` pairs get no row (the all-data fit applies there)."""
    rows = []
    for s, h in lc.groupby(season_col):
        t = intercalibrate(h, ref_scopes, scopes=scopes, max_gap=max_gap, min_pairs=min_pairs)
        if len(t):
            rows.append(t.assign(season=int(s), MJD_min=h["MJD"].min(), MJD_max=h["MJD"].max()))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def apply_intercal(lc: pd.DataFrame, table: pd.DataFrame, scopes=None, min_sigma: float = 3.0,
                   additive_only: bool = True) -> pd.DataFrame:
    """F' = (F - b)/a for the listed scopes (default: those whose offset is
    > min_sigma significant).  ``additive_only``: use the a = 1 fit (b1) —
    the comparison stars already fixed the flux scale.  Adds F, Ferr, F_ic,
    Ferr_ic, mag_ic, mag_ic_err, ic_a, ic_b.  Rows of ``table`` with a ``season`` (>= 0)
    apply only to the rows of ``lc`` in that season and are applied after the all-data rows
    (season -1 / NaN), which therefore remain for seasons without their own fit."""
    out = lc.copy()
    if "season" in table:
        table = table.assign(_s=table["season"].fillna(-1)).sort_values("_s", kind="stable")
    out["F"], out["Ferr"] = to_mjy(out["mag"], out["mag_err"])
    out["F_ic"], out["Ferr_ic"] = out["F"], out["Ferr"]
    out["ic_a"], out["ic_b"] = 1.0, 0.0
    for _, r in table.iterrows():
        if scopes is not None and r["scope"] not in scopes:
            continue
        a, b, be = (1.0, r["b1"], r["b1_err"]) if additive_only else (r["a"], r["b"], r["b_err"])
        if scopes is None and abs(b) < min_sigma * be and (additive_only or abs(a - 1) < min_sigma * r["a_err"]):
            continue
        sel = (out["Filter"] == r["filter"]) & (out["scope"] == r["scope"])
        if "season" in r and pd.notna(r["season"]) and r["season"] >= 0:
            sel &= out["season"] == r["season"]
        out.loc[sel, "F_ic"] = (out.loc[sel, "F"] - b) / a
        out.loc[sel, "Ferr_ic"] = out.loc[sel, "Ferr"] / a
        out.loc[sel, "ic_a"], out.loc[sel, "ic_b"] = a, b
    out["mag_ic"], out["mag_ic_err"] = to_mag(out["F_ic"], out["Ferr_ic"])
    return out
