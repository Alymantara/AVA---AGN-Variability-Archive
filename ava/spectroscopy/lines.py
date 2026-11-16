"""
ava.spectroscopy.lines — Hβ region of FLOYDS spectra: Gaussian fit, [O III] calibration, variability.

Model (rest frame, blue arm = EXTRACTED order 2, ``fit_window`` default 4750–5100 Å):

* linear continuum about 4930 Å;
* [O III] λλ4959, 5007: a tied doublet (4959 = 5007 / 2.98, same shift and width), each a core Gaussian plus an
  optional blue-wing Gaussian (``oiii_wing``);
* narrow Hβ: shift and width of the [O III] core, flux free (≥ 0);
* broad Hβ: ``broad_components`` Gaussians (default 1: on same-night exposure pairs a free 2-Gaussian broad
  model trades flux with the continuum, 8-19 % pair scatter, against 0.5-4 % for one), widths ``broad_sigma`` Å.

Robust least squares (soft-L1 loss: cosmic rays / residual spikes do not drive it), weights 1/σ.  Fluxes are
analytic Gaussian integrals; errors from the Jacobian covariance scaled by the reduced χ².

[O III] calibration (a series): the narrow lines do not vary on RM time scales, so each spectrum is scaled by
``s_i = F[O III]_ref / F[O III]_i`` (``F_ref`` = median over the good spectra), which removes slit losses, clouds
and flux-calibration errors (grey factor).  Hβ and the 5100 Å continuum are reported raw and scaled.

Variability: fractional variability F_var (Rodríguez-Pascual et al. 1997) with its error (Vaughan et al. 2003),
R_max, rms, mean.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

HB, O3A, O3B = 4861.33, 4958.91, 5006.84
O3_RATIO = 2.98
S2PI = np.sqrt(2 * np.pi)


@dataclass
class FitSettings:
    fit_window: tuple = (4750.0, 5100.0)      # rest Å
    continuum_windows: tuple = ((4750.0, 4790.0), (5070.0, 5100.0))
    cont5100: tuple = (5080.0, 5120.0)
    broad_components: int = 1                 # 1 = robust fluxes (2 trades flux with the continuum)
    broad_sigma: tuple = (8.0, 80.0)          # Å  (~500–5000 km/s)
    narrow_sigma: tuple = (1.0, 15.0)         # Å  (instrument + [O III])
    max_shift: float = 20.0                   # Å, any component vs its rest wavelength
    oiii_wing: bool = True
    loss: str = "soft_l1"
    min_good_fraction: float = 0.8


def blue_arm(path, z: float, order: int = 2) -> pd.DataFrame:
    """Rest-frame blue-arm spectrum from a -1d file (EXTRACTED, fringe-corrected per order)."""
    from astropy.io import fits

    d = fits.getdata(path, "EXTRACTED")
    m = (d["order"] == order) & (d["mask"] == 0) & np.isfinite(d["flux_optimal"]) & (d["fluxerror_optimal"] > 0)
    w = np.asarray(d["wavelength"][m], float)
    o = np.argsort(w)
    return pd.DataFrame({"w": w[o] / (1 + z), "f": np.asarray(d["flux_optimal"][m], float)[o],
                         "e": np.asarray(d["fluxerror_optimal"][m], float)[o]})


def gauss(x, flux, mu, sig):
    return flux / (S2PI * sig) * np.exp(-0.5 * ((x - mu) / sig) ** 2)


def _names(s: FitSettings):
    n = ["c0", "c1", "dn", "sn", "F5007", "Fnhb"]
    if s.oiii_wing:
        n += ["Fw", "dw", "sw"]
    for k in range(s.broad_components):
        n += [f"Fb{k}", f"db{k}", f"sb{k}"]
    return n


def model(p: dict, x, s: FitSettings, part: str | None = None):
    cont = p["c0"] + p["c1"] * (x - 4930.0) / 100.0
    o3 = gauss(x, p["F5007"], O3B + p["dn"], p["sn"]) + gauss(x, p["F5007"] / O3_RATIO, O3A + p["dn"], p["sn"])
    if s.oiii_wing:
        o3 = o3 + gauss(x, p["Fw"], O3B + p["dw"], p["sw"]) + gauss(x, p["Fw"] / O3_RATIO, O3A + p["dw"], p["sw"])
    hbn = gauss(x, p["Fnhb"], HB + p["dn"], p["sn"])
    hbb = sum(gauss(x, p[f"Fb{k}"], HB + p[f"db{k}"], p[f"sb{k}"]) for k in range(s.broad_components))
    parts = {"cont": cont, "oiii": o3, "hb_narrow": hbn, "hb_broad": hbb}
    return parts[part] if part else cont + o3 + hbn + hbb


def fit_hbeta(sp: pd.DataFrame, s: FitSettings | None = None) -> dict:
    """Fit one rest-frame spectrum. Returns fluxes (same units as the spectrum × Å), errors, parameters and
    quality numbers; ``ok`` False with ``reason`` when the data cannot support the fit."""
    s = s or FitSettings()
    x = sp[(sp.w > s.fit_window[0]) & (sp.w < s.fit_window[1])]
    span = s.fit_window[1] - s.fit_window[0]
    expected = span / max(np.median(np.diff(sp.w)), 1e-3) if len(sp) > 2 else 0
    if len(x) < 30 or len(x) < s.min_good_fraction * expected:
        return {"ok": False, "reason": f"only {len(x)} good bins in the fit window"}
    w, f, e = x.w.to_numpy(), x.f.to_numpy(), x.e.to_numpy()
    cw = np.zeros(len(w), bool)
    for lo, hi in s.continuum_windows:
        cw |= (w > lo) & (w < hi)
    c1, c0 = np.polyfit((w[cw] - 4930.0) / 100.0, f[cw], 1) if cw.sum() > 5 else (0.0, np.median(f))
    resid = f - (c0 + c1 * (w - 4930.0) / 100.0)
    near = lambda lam, h: (w > lam - h) & (w < lam + h)  # noqa: E731
    dpk = w[near(O3B, s.max_shift)][np.argmax(resid[near(O3B, s.max_shift)])] - O3B if near(O3B, s.max_shift).any() else 0.0
    sn0 = 4.0
    fo3 = max(np.trapezoid(np.clip(resid[near(O3B + dpk, 3 * sn0)], 0, None), w[near(O3B + dpk, 3 * sn0)]), 1e-20)
    fhb = max(np.trapezoid(np.clip(resid[near(HB, 60)], 0, None), w[near(HB, 60)]), 1e-20)
    scale = max(abs(c0), np.median(np.abs(f)), 1e-30)
    p0 = {"c0": c0, "c1": c1, "dn": dpk, "sn": sn0, "F5007": 0.8 * fo3, "Fnhb": 0.05 * fo3}
    lo = {"c0": -np.inf, "c1": -np.inf, "dn": -s.max_shift, "sn": s.narrow_sigma[0], "F5007": 0, "Fnhb": 0}
    hi = {"c0": np.inf, "c1": np.inf, "dn": s.max_shift, "sn": s.narrow_sigma[1], "F5007": np.inf, "Fnhb": np.inf}
    if s.oiii_wing:
        p0.update(Fw=0.2 * fo3, dw=dpk - 3, sw=8.0)
        lo.update(Fw=0, dw=-s.max_shift, sw=s.narrow_sigma[0])
        hi.update(Fw=np.inf, dw=s.max_shift, sw=2.5 * s.narrow_sigma[1])
    for k in range(s.broad_components):
        frac = (0.6, 0.4, 0.2)[k] if k < 3 else 0.1
        p0.update({f"Fb{k}": frac * fhb, f"db{k}": 0.0, f"sb{k}": float(np.clip((20, 45, 70)[min(k, 2)], *s.broad_sigma))})
        lo.update({f"Fb{k}": 0, f"db{k}": -2 * s.max_shift, f"sb{k}": s.broad_sigma[0]})
        hi.update({f"Fb{k}": np.inf, f"db{k}": 2 * s.max_shift, f"sb{k}": s.broad_sigma[1]})
    names = _names(s)
    flux_like = {"c0", "c1", "F5007", "Fnhb", "Fw"} | {f"Fb{k}" for k in range(s.broad_components)}
    norm = np.array([scale if n in flux_like else 1.0 for n in names])
    x0 = np.array([p0[n] for n in names]) / norm
    lb, ub = np.array([lo[n] for n in names]) / norm, np.array([hi[n] for n in names]) / norm
    x0 = np.clip(x0, lb + 1e-9 * (np.isfinite(lb)), np.where(np.isfinite(ub), ub - 1e-9, ub))

    def res(v):
        return (model(dict(zip(names, v * norm)), w, s) - f) / e

    r = least_squares(res, x0, bounds=(lb, ub), loss=s.loss, f_scale=3.0, x_scale="jac", max_nfev=5000)
    p = dict(zip(names, r.x * norm))
    dof = max(len(w) - len(names), 1)
    chi2nu = float(np.sum(r.fun ** 2) / dof)
    try:
        J = r.jac / norm[None, :]          # d residual / d parameter (physical units)
        cov = np.linalg.pinv(J.T @ J) * max(chi2nu, 1.0)
    except np.linalg.LinAlgError:
        cov = np.full((len(names), len(names)), np.nan)
    idx = {n: i for i, n in enumerate(names)}

    def var_sum(keys):
        ii = [idx[k] for k in keys]
        return float(np.sqrt(max(cov[np.ix_(ii, ii)].sum(), 0)))

    bkeys = [f"Fb{k}" for k in range(s.broad_components)]
    okeys = ["F5007"] + (["Fw"] if s.oiii_wing else [])
    hb_b = sum(p[k] for k in bkeys)
    o3 = p["F5007"] + (p.get("Fw", 0.0))
    c5100 = sp[(sp.w > s.cont5100[0]) & (sp.w < s.cont5100[1])]
    # broad-line width: FWHM of the summed broad model on a fine grid
    g = np.linspace(HB - 200, HB + 200, 4001)
    prof = model(p, g, s, "hb_broad")
    above = g[prof >= prof.max() / 2] if prof.max() > 0 else g[:1]
    out = {"ok": bool(r.success) and hb_b > 0 and o3 > 0, "reason": "" if r.success else r.message,
           "hb_broad": hb_b, "hb_broad_err": var_sum(bkeys), "hb_narrow": p["Fnhb"], "hb_narrow_err": var_sum(["Fnhb"]),
           "oiii5007": o3, "oiii5007_err": var_sum(okeys), "oiii_shift_A": p["dn"],
           "oiii_sigma_A": p["sn"], "hb_fwhm_kms": float((above.max() - above.min()) / HB * 2.99792458e5),
           "cont5100": float(np.median(c5100.f)) if len(c5100) > 5 else np.nan,
           "cont5100_err": float(1.2533 * np.std(c5100.f) / np.sqrt(len(c5100))) if len(c5100) > 5 else np.nan,
           "chi2nu": chi2nu, "n_bins": len(w), "params": p}
    out["hb_snr"] = out["hb_broad"] / out["hb_broad_err"] if out["hb_broad_err"] > 0 else np.nan
    return out


def oiii_calibrate(t: pd.DataFrame, good: pd.Series | None = None, min_spectra: int = 3,
                   scale_limits: tuple = (0.2, 5.0)) -> tuple[pd.DataFrame, dict]:
    """Scale each spectrum to the reference [O III] 5007 flux (median over ``good`` spectra).  Adds columns
    oiii_scale(+_err), hb_broad_cal(+_err), cont5100_cal(+_err), oiii_calibrated; flags scales outside
    ``scale_limits`` as bad (``good`` False)."""
    t = t.copy()
    g = (t["ok"] if good is None else good & t["ok"]).astype(bool)
    if g.sum() < min_spectra:
        t["oiii_scale"], t["oiii_scale_err"], t["oiii_calibrated"] = 1.0, 0.0, False
        ref = np.nan
    else:
        ref = float(np.median(t.loc[g, "oiii5007"]))
        t["oiii_scale"] = ref / t["oiii5007"]
        t["oiii_scale_err"] = t["oiii_scale"] * t["oiii5007_err"] / t["oiii5007"]
        t["oiii_calibrated"] = True
    for k in ("hb_broad", "cont5100"):
        t[f"{k}_cal"] = t[k] * t["oiii_scale"]
        t[f"{k}_cal_err"] = np.abs(t[f"{k}_cal"]) * np.sqrt((t[f"{k}_err"] / t[k]) ** 2
                                                             + (t["oiii_scale_err"] / t["oiii_scale"]) ** 2)
    t["good"] = t["ok"] & t["oiii_scale"].between(*scale_limits)
    return t, {"oiii_ref": ref, "n_ref": int(g.sum())}


def nightly(t: pd.DataFrame, col: str, err: str) -> pd.DataFrame:
    """Weighted mean per night of good rows; error max(formal, scatter/√n).  Night = the ``night`` column
    (LCO DAY-OBS, site-aware) if present, else floor(MJD − 0.5)."""
    x = t[t["good"] & np.isfinite(t[col]) & (t[err] > 0)].copy()
    if "night" not in x:
        x["night"] = np.floor(x["MJD"] - 0.5).astype(int)
    rows = []
    for n, h in x.groupby("night"):
        wgt = 1 / h[err] ** 2
        m = float(np.sum(wgt * h[col]) / wgt.sum())
        e = float(np.sqrt(1 / wgt.sum()))
        if len(h) > 1:
            e = max(e, float(np.std(h[col], ddof=1) / np.sqrt(len(h))))
        rows.append({"night": n, "MJD": float(h["MJD"].mean()), col: m, err: e, "n_exp": len(h)})
    return pd.DataFrame(rows)


def variability(f, e) -> dict:
    """mean, rms, F_var ± err (excess variance; NaN when the scatter is below the errors), R_max, <σ>/mean."""
    f, e = np.asarray(f, float), np.asarray(e, float)
    ok = np.isfinite(f) & np.isfinite(e)
    f, e = f[ok], e[ok]
    n = len(f)
    if n < 3:
        return {"n": n}
    mean, s2 = float(f.mean()), float(f.var(ddof=1))
    err2 = float(np.mean(e ** 2))
    excess = s2 - err2
    fvar = float(np.sqrt(excess) / mean) if excess > 0 else np.nan
    fvar_err = np.nan
    if np.isfinite(fvar):                   # Vaughan et al. (2003) eq. 11
        fvar_err = float(np.sqrt((np.sqrt(1 / (2 * n)) * err2 / (mean ** 2 * fvar)) ** 2
                                 + (np.sqrt(err2 / n) / mean) ** 2))
    return {"n": n, "mean": mean, "rms": float(np.sqrt(s2)), "mean_err": float(np.sqrt(err2)),
            "fvar": fvar, "fvar_err": fvar_err, "rmax": float(f.max() / f.min()) if f.min() > 0 else np.nan,
            "snr_median": float(np.median(f / e))}


def integrated_hbeta(sp: pd.DataFrame, fit: dict, s: FitSettings | None = None, window=(4800.0, 4940.0)) -> float:
    """Cross-check of the broad Hβ flux: flux above the straight continuum through ``continuum_windows``,
    minus the fitted narrow lines ([O III] wings, narrow Hβ), integrated over ``window`` (rest Å)."""
    s = s or FitSettings()
    cw = np.zeros(len(sp), bool)
    for lo, hi in s.continuum_windows:
        cw |= (sp.w > lo) & (sp.w < hi)
    if cw.sum() < 5 or not fit.get("params"):
        return np.nan
    c1, c0 = np.polyfit(sp.w[cw] - 4930.0, sp.f[cw], 1)
    x = sp[(sp.w > window[0]) & (sp.w < window[1])]
    narrow = model(fit["params"], x.w.to_numpy(), s, "oiii") + model(fit["params"], x.w.to_numpy(), s, "hb_narrow")
    return float(np.trapezoid(x.f - (c0 + c1 * (x.w - 4930.0)) - narrow, x.w))
