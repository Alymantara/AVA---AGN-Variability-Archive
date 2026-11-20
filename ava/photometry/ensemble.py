"""
ava.photometry.ensemble — PyTICS ensemble intercalibration, vectorised.

A faithful, fast port of PyTICS (Vieliute et al. 2025, RASTI, doi:10.1093/rasti/rzaf021;
https://github.com/Astroberta/PyTICS, ``Filter.Corr``) with an incremental mode.

Model (per filter): every measurement of comparison star *s* at epoch *t* on scope *k*

    m_obs = m*_s + DMAGT_t + DMAGS_k
    σ_tot² = σ_phot² + rms*_s² + rms_t² + rms_sc,k²

solved by the same iterative scheme as ``Filter.Corr`` (one loop):

1. epochs (per scope): per-star scope means (inverse-variance), then for every
   epoch ``arx`` of (m - scope mean) → dmagt, rms_t (damped by ``safe`` after
   the first loop); DMAGT made zero-mean within each scope;
2. scopes: provisional star means, then ``arx`` per scope of
   (m - dmagt - m*) → dmags, rms_sc; DMAGS made zero-mean over all data;
3. stars: ``arx`` per star of (m - dmagt - dmags) → m*, rms* (damped); the
   data are shifted by dmagt + dmags;
4. the brightest star's mean is the reference (subtracted, added back at the end);
5. converged when every parameter changes by < 1e-4 of its error.

``arx`` is PyTICS' extra-variance optimal average (after K. Horne's avgrmsx),
copied below unchanged in a numba kernel that processes all groups at once.

Differences from the published PyTICS code (deliberate):
* the AGN is always excluded from the comparison stars (``Filter.Corr`` and
  ``CorrUpdate_New`` call ``Brightest_Reduced`` without ``AGN_ID``);
* epochs are keyed by frame (not by MJD), scopes by telescope + camera;
* :func:`update` — new epochs are fitted against the stored star means and
  scope offsets (one ``arx`` per epoch), instead of re-running everything.

AGN (``apply``): m_AGN = m_obs - DMAGT_t - DMAGS_k (+ ZP),
σ² = σ_phot² + rms_sc,k² + rms_t²   (as ``Filter.AGN_LC``).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit


# ---------------------------------------------------------------------------
# arx — PyTICS' avgrmsx (verbatim maths), scalar and grouped
# ---------------------------------------------------------------------------

@njit(cache=True)
def _arx(dat, sig, nloop=1000):
    """(avg, avg_err, extra_rms, extra_rms_err) — PyTICS.arx.arx without prints."""
    ng = len(dat)
    if ng == 0:
        return np.nan, np.nan, np.nan, np.nan
    e1 = 0.0
    for i in range(ng):
        e1 += sig[i]
    e1 = e1 / ng
    sum1 = 0.0
    sum2 = 0.0
    for i in range(ng):
        w = (e1 / sig[i]) ** 2
        sum1 += dat[i] * w
        sum2 += w
    avg = sum1 / sum2
    sigavg = e1 / (sum2 ** 0.5)
    w = ng / sum2
    e1 = e1 * (w ** 0.5)
    rms = e1
    sigrms = rms
    tiny = 2.0e-5
    rmin = tiny * e1
    for loop in range(nloop):
        oldavg = avg
        oldrms = rms
        s1 = 0.0
        s2 = 0.0
        sg = 0.0
        so = 0.0
        s3 = 0.0
        a = avg / e1
        r = rms / e1
        rr = r * r
        for i in range(ng):
            d = dat[i] / e1
            e = sig[i] / e1
            g = rr / (rr + e * e)
            x = g * (d - a)
            xx = x * x
            s1 += g * d
            sg += g
            so += g * g
            s2 += xx
            s3 += g * xx
        if sg <= 0.0:
            break
        a = s1 / sg
        r = (s2 ** 0.5) / (sg ** 0.5)
        r = max(rmin, r)
        siga = r / (sg ** 0.5)
        gg = 2.0 * (2.0 * s3 / s2 * sg - so) if s2 > 0 else 0.0
        sigr = r
        if gg > 0.0:
            sigr = r / (gg ** 0.5)
        avg = a * e1
        rms = r * e1
        sigavg = siga * e1
        sigrms = sigr * e1
        if s2 <= 0.0:
            rms = 0.0
            sigrms = -1.0
            break
        if loop > 1:
            safe = 0.9
            avg = oldavg * (1.0 - safe) + safe * avg
            rms = oldrms * (1.0 - safe) + safe * rms
            chiavg = (avg - oldavg) / sigavg
            chirms = (rms - oldrms) / sigrms
            if max(abs(chiavg), abs(chirms)) / tiny < 1.0:
                break
        if rms <= 0.0:
            break
    return avg, sigavg, rms, sigrms


@njit(cache=True)
def _arx_groups(dat, sig, order, starts):
    """arx for every group: rows ``order[starts[g]:starts[g+1]]``."""
    ng = len(starts) - 1
    out = np.empty((ng, 4))
    for g in range(ng):
        idx = order[starts[g]:starts[g + 1]]
        a, ae, r, re = _arx(dat[idx], sig[idx], 1000)
        out[g, 0] = a
        out[g, 1] = ae
        out[g, 2] = r
        out[g, 3] = re
    return out


def _groups(codes: np.ndarray, n: int):
    order = np.argsort(codes, kind="stable")
    counts = np.bincount(codes, minlength=n)
    starts = np.concatenate([[0], np.cumsum(counts)])
    return order, starts


def _optimal(values, errs, codes, n):
    """Inverse-variance mean and error per group (PyTICS Generic_Optimal)."""
    w = 1.0 / errs ** 2
    sw = np.bincount(codes, w, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.bincount(codes, w * values, n) / sw, 1.0 / np.sqrt(sw)


def _optimal_all(values, errs):
    w = 1.0 / errs ** 2
    return float(np.sum(w * values) / np.sum(w)), float(1.0 / np.sqrt(np.sum(w)))


# ---------------------------------------------------------------------------
# Solution
# ---------------------------------------------------------------------------

@dataclass
class Solution:
    filter: str
    stars: pd.DataFrame        # star_id, m_star, m_star_err, rms_star, rms_star_err, n, rank
    scopes: pd.DataFrame       # scope, DMAGS, DMAGS_err, rms_sc, rms_sc_err, n
    epochs: pd.DataFrame       # frame, MJD, scope, DMAGT, DMAGT_err, rms_t, rms_t_err, n_stars, fit
    meta: dict = field(default_factory=dict)
    star_scope: pd.DataFrame | None = None   # star_id, scope, offset, offset_err, n (star x camera residual)

    def save(self, folder: Path) -> None:
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        for name in ("stars", "scopes", "epochs", "star_scope"):
            if getattr(self, name) is not None:
                getattr(self, name).to_parquet(folder / f"{name}.parquet", index=False)
        (folder / "meta.json").write_text(json.dumps(self.meta, indent=1, default=str))

    @classmethod
    def load(cls, folder: Path) -> "Solution":
        folder = Path(folder)
        meta = json.loads((folder / "meta.json").read_text())
        ss = folder / "star_scope.parquet"
        return cls(meta["filter"], *(pd.read_parquet(folder / f"{n}.parquet") for n in ("stars", "scopes", "epochs")),
                   meta=meta, star_scope=pd.read_parquet(ss) if ss.exists() else None)


# ---------------------------------------------------------------------------
# Full fit
# ---------------------------------------------------------------------------

def select_stars(d: pd.DataFrame, agn_id, frac: float = 0.5, star_lim: int | None = 100,
                 bad_ids=()) -> list:
    """PyTICS ``Brightest_Reduced`` + ``Star_Lim``, with the AGN always excluded:
    stars with more than ``frac`` x the maximum number of points, brightest first."""
    s = d[(d["star_id"] != agn_id) & ~d["is_agn"] & ~d["star_id"].isin(list(bad_ids))]
    n = s.groupby("star_id").size()
    keep = n[n > frac * n.max()].index
    s = s[s["star_id"].isin(keep)]
    w = 1.0 / s["magerr"].astype(float) ** 2
    mean = (s["mag_inst"] * w).groupby(s["star_id"]).sum() / w.groupby(s["star_id"]).sum()
    ids = list(mean.sort_values().index)
    return ids[:star_lim] if star_lim else ids


_TRACE = ("dmagt", "rms_t", "DMAGT", "dmags", "rms_sc", "m_star", "rms_star", "DMAGS")


#: SExtractor FLAGS bits that remove a comparison measurement: 4 saturated,
#: 8 truncated at the image edge, 16 incomplete aperture data.
BAD_FLAGS = 4 | 8 | 16


def clean_comparisons(d: pd.DataFrame, bad_flags: int = BAD_FLAGS) -> pd.DataFrame:
    """Drop flagged comparison-star rows (the AGN rows are always kept)."""
    if not bad_flags or "sex_flags" not in d:
        return d
    return d[d["is_agn"] | ((d["sex_flags"].astype(int) & bad_flags) == 0)]


def fit(d: pd.DataFrame, *, agn_id, max_loops: int = 200, safe: float = 0.6, frac: float = 0.5,
        star_lim: int | None = 100, bad_ids=(), tiny: float = 1e-4, bad_flags: int = BAD_FLAGS,
        colours: pd.Series | None = None, rms_err_floor: float = 1e-3, atol: float = 1e-5,
        log=None) -> Solution:
    """Full PyTICS solution for one filter.

    ``d``: rows of one filter with columns frame, MJD, star_id, is_agn, mag_inst,
    magerr, scope (from :func:`ava.photometry.store.load_pytics` + a scope column).

    ``colours`` (star_id -> colour, e.g. GSPC g-i): adds a per-scope colour term
    to the model (an AVA extension; PyTICS has one offset per scope),

        m_obs = m*_s + DMAGT_t + DMAGS_k + CK_k (c_s - c0),

    fitted after the DMAGS step of every loop, weighted like DMAGS, with CK
    zero-mean over the data (a common slope is absorbed by the star means).
    Stars without a colour get c_s = c0 (no term).

    ``rms_err_floor``: in the convergence test the errors of the extra-variance
    parameters (rms_t, rms_sc, rms*) are floored at this value (mag). An rms
    sitting at 0 has a ~1e-9 error and can flip 0 <-> 0.7 mmag forever, so the
    published test never stops although nothing else moves. 0 = PyTICS exactly.
    ``atol``: also stop when the gauge-free solution (per-epoch DMAGT+DMAGS and
    m*, each up to a common shift, and CK) moves by < atol mag for 3 consecutive loops (``meta['stop'] = 'stationary'``);
    0 disables it.
    """
    t0 = time.time()
    filt = str(d["Filter"].iloc[0])
    d = clean_comparisons(d, bad_flags)
    ids = select_stars(d, agn_id, frac, star_lim, bad_ids)
    s = d[d["star_id"].isin(ids)].copy()
    y = s["mag_inst"].to_numpy(float).copy()
    e = s["magerr"].to_numpy(float)
    star_codes, star_ids = pd.factorize(s["star_id"])
    scope_codes, scope_ids = pd.factorize(s["scope"])
    ep_key = s["frame"].astype(str)
    ep_codes, ep_ids = pd.factorize(ep_key)
    nS, nK, nT = len(star_ids), len(scope_ids), len(ep_ids)
    ep_scope = np.zeros(nT, int)
    ep_scope[ep_codes] = scope_codes
    ref = int(np.where(star_ids == ids[0])[0][0])            # brightest star = reference

    # star x scope groups for the per-scope star means
    sk_codes = star_codes * nK + scope_codes
    ord_T, st_T = _groups(ep_codes, nT)
    ord_K, st_K = _groups(scope_codes, nK)
    ord_S, st_S = _groups(star_codes, nS)

    # per-scope colour terms (optional)
    use_ck = colours is not None
    star_c = np.full(nS, np.nan)
    if use_ck:
        star_c = pd.Series(np.asarray(star_ids)).map(colours).to_numpy(float)
    has_c = np.isfinite(star_c)
    c0 = float(np.median(star_c[has_c])) if has_c.any() else 0.0
    dc = np.where(has_c, star_c - c0, 0.0)[star_codes]
    use_ck = use_ck and has_c.sum() >= 5
    CK = np.zeros(nK); CK_err = np.zeros(nK); ck = np.zeros(nK)

    dmagt = np.zeros(nT); dmagt_err = np.zeros(nT); rms_t = np.zeros(nT); rms_t_err = np.zeros(nT)
    DMAGT = np.zeros(nT); DMAGT_err = np.zeros(nT)
    dmags = np.zeros(nK); dmags_err = np.zeros(nK); rms_sc = np.zeros(nK); rms_sc_err = np.zeros(nK)
    DMAGS = np.zeros(nK); DMAGS_err = np.zeros(nK)
    m = np.zeros(nS); m_err = np.zeros(nS); rms_s = np.zeros(nS); rms_s_err = np.zeros(nS)
    total = 0.0
    prev = None
    loop = 0
    converged = False
    history = []
    stop = "max_loops"
    still = 0

    def err_tot():
        return np.sqrt(e ** 2 + rms_s[star_codes] ** 2 + rms_t[ep_codes] ** 2 + rms_sc[scope_codes] ** 2)

    for loop in range(max_loops):
        # ---- 1. dmagt (per scope: star scope-means, then arx per epoch) -------------
        et = err_tot()
        sm, sme = _optimal(y, et, sk_codes, nS * nK)
        x = y - sm[sk_codes]
        sx = np.sqrt(np.maximum(et ** 2 - rms_t[ep_codes] ** 2 + sme[sk_codes] ** 2, 1e-12))
        res = _arx_groups(x, sx, ord_T, st_T)
        new = res[:, 0]
        if loop > 0:
            new = dmagt + safe * (new - dmagt)
        dmagt, dmagt_err, rms_t, rms_t_err = new, res[:, 1], res[:, 2], res[:, 3]
        # zero-mean DMAGT within each scope (row-weighted, as PyTICS)
        rowval = DMAGT[ep_codes] + dmagt[ep_codes]
        mk, mke = _optimal(rowval, dmagt_err[ep_codes], scope_codes, nK)
        dmagt = dmagt - mk[ep_scope]
        dmagt_err = np.sqrt(dmagt_err ** 2 + mke[ep_scope] ** 2)
        DMAGT_err = dmagt_err.copy()
        DMAGT = DMAGT + dmagt

        # ---- 2. dmags (provisional star means, arx per scope) -----------------------
        et = err_tot()
        mt, mte = _optimal(y, et, star_codes, nS)
        m, m_err = mt, mte
        x = y - dmagt[ep_codes] - m[star_codes]
        sx = np.sqrt(np.maximum(et ** 2 - rms_sc[scope_codes] ** 2 + dmagt_err[ep_codes] ** 2
                                + m_err[star_codes] ** 2, 1e-12))
        res = _arx_groups(x, sx, ord_K, st_K)
        dmags, dmags_err, rms_sc, rms_sc_err = res[:, 0], res[:, 1], res[:, 2], res[:, 3]
        mean, mean_err = _optimal_all(DMAGS[scope_codes] + dmags[scope_codes], dmags_err[scope_codes])
        dmags = dmags - mean
        dmags_err = np.sqrt(dmags_err ** 2 + mean_err ** 2)
        DMAGS_err = dmags_err.copy()
        DMAGS = DMAGS + dmags

        # ---- 2b. per-scope colour terms (AVA extension) -------------------------------
        if use_ck:
            x = y - dmagt[ep_codes] - dmags[scope_codes] - m[star_codes]
            w = 1.0 / np.maximum(sx ** 2 + rms_sc[scope_codes] ** 2, 1e-12)
            swx = np.bincount(scope_codes, w * dc * x, nK)
            sww = np.bincount(scope_codes, w * dc * dc, nK)
            sw1 = np.bincount(scope_codes, w * dc, nK)
            sw0 = np.bincount(scope_codes, w, nK)
            den = sww - sw1 ** 2 / np.maximum(sw0, 1e-30)            # slope with free intercept
            with np.errstate(invalid="ignore", divide="ignore"):
                ck = np.where(den > 0, (swx - sw1 * np.bincount(scope_codes, w * x, nK) / sw0) / den, 0.0)
                ck_err = np.where(den > 0, 1.0 / np.sqrt(den), 0.0)
            if loop > 0:
                ck = safe * ck                                       # damped, as dmagt / m*
            wk = np.where(ck_err > 0, sww, 0.0)
            ck = ck - (np.sum(wk * (CK + ck)) / np.sum(wk) if wk.sum() > 0 else 0.0)
            CK = CK + ck
            CK_err = ck_err
            y = y - ck[scope_codes] * dc

        # ---- 3. star means -------------------------------------------------------------
        et = err_tot()
        x = y - dmagt[ep_codes] - dmags[scope_codes]
        sx = np.sqrt(np.maximum(et ** 2 - rms_s[star_codes] ** 2 + dmagt_err[ep_codes] ** 2
                                + dmags_err[scope_codes] ** 2, 1e-12))
        res = _arx_groups(x, sx, ord_S, st_S)
        new = res[:, 0]
        if loop > 0:
            new = m + safe * (new - m)
        m, m_err, rms_s, rms_s_err = new, res[:, 1], res[:, 2], res[:, 3]
        y = y - dmagt[ep_codes] - dmags[scope_codes]

        # ---- 4. reference star -------------------------------------------------------------
        c = m[ref]
        y = y - c
        m = m - c
        total += c

        # ---- 5. convergence (PyTICS: |Δp| / σ_p < tiny for every traced parameter) ----
        cur = [(dmagt, dmagt_err), (rms_t, rms_t_err), (DMAGT, DMAGT_err), (dmags, dmags_err),
               (rms_sc, rms_sc_err), (m, m_err), (rms_s, rms_s_err), (DMAGS, DMAGS_err)]
        if use_ck:
            cur.append((CK, np.where(CK_err > 0, CK_err, np.inf)))
        if prev is not None:
            worst, worst_name, max_dmag = 0.0, "", 0.0
            for name, (v, ve), (pv, _) in zip(_TRACE + ("CK",), cur, prev):
                if name.startswith("rms"):
                    ve = np.maximum(np.abs(ve), rms_err_floor)
                with np.errstate(invalid="ignore", divide="ignore"):
                    r = np.abs(v - pv) / np.abs(ve)
                ok = np.isfinite(r)
                if ok.any() and r[ok].max() > worst:
                    worst, worst_name = float(r[ok].max()), name
                max_dmag = max(max_dmag, float(np.nanmax(np.abs(v - pv))) if len(v) else 0.0)
            history.append((worst, worst_name, max_dmag))
            if worst < tiny:
                converged, stop = True, "pytics"
                break
            # gauge-free: per-epoch total DMAGT+DMAGS and star means, each up to a common shift
            # (DMAGT of a whole scope can trade with its DMAGS, and DMAGS with the star level)
            dT = (DMAGT + DMAGS[ep_scope]) - prev_c[0]
            dm = m - prev_c[3]
            move = max(float(np.max(np.abs(dT - np.median(dT)))), float(np.max(np.abs(dm - np.median(dm)))),
                       float(np.max(np.abs(CK - prev_c[2]))))
            still = still + 1 if move < atol else 0
            if atol > 0 and still >= 3:
                converged, stop = True, "stationary"
                break
        prev = [(v.copy(), ve.copy()) for v, ve in cur]
        prev_c = (DMAGT + DMAGS[ep_scope], DMAGS.copy(), CK.copy(), m.copy())

    m = m + total
    # star x scope residual offsets (what the per-scope star means of step 1 absorb:
    # colour / pixel-scale differences between cameras) — used by update()
    y0 = s["mag_inst"].to_numpy(float)
    r = y0 - m[star_codes] - DMAGT[ep_codes] - DMAGS[scope_codes] - CK[scope_codes] * dc
    off, off_err = _optimal(r, err_tot(), sk_codes, nS * nK)
    nsk = np.bincount(sk_codes, minlength=nS * nK)
    has = nsk > 0
    star_scope = pd.DataFrame({"star_id": np.asarray(star_ids, dtype="int64")[np.arange(nS * nK)[has] // nK],
                               "scope": np.asarray(scope_ids, dtype=str)[np.arange(nS * nK)[has] % nK],
                               "offset": off[has], "offset_err": off_err[has], "n": nsk[has]})
    n_ep = np.bincount(ep_codes, minlength=nT)
    first = pd.Series(np.arange(len(s))).groupby(ep_codes).first().to_numpy()
    sol = Solution(
        filter=filt,
        stars=pd.DataFrame({"star_id": np.asarray(star_ids, dtype="int64"), "m_star": m, "m_star_err": m_err,
                            "rms_star": rms_s, "rms_star_err": rms_s_err,
                            "n": np.bincount(star_codes, minlength=nS),
                            "rank": [ids.index(i) for i in star_ids], "colour": star_c}),
        scopes=pd.DataFrame({"scope": np.asarray(scope_ids, dtype=str), "DMAGS": DMAGS, "DMAGS_err": DMAGS_err,
                             "rms_sc": rms_sc, "rms_sc_err": rms_sc_err, "CK": CK, "CK_err": CK_err,
                             "n": np.bincount(scope_codes, minlength=nK)}),
        epochs=pd.DataFrame({"frame": np.asarray(ep_ids, dtype=str), "MJD": s["MJD"].to_numpy()[first],
                             "scope": np.asarray(scope_ids, dtype=str)[ep_scope],
                             "DMAGT": DMAGT, "DMAGT_err": DMAGT_err, "rms_t": rms_t, "rms_t_err": rms_t_err,
                             "n_stars": n_ep, "fit": "full"}),
        meta=dict(filter=filt, agn_id=int(agn_id), loops=loop + 1, converged=converged, safe=safe, frac=frac,
                  bad_flags=bad_flags, colour_terms=bool(use_ck), c0=c0, rms_err_floor=rms_err_floor, stop=stop,
                  star_lim=star_lim, n_stars=nS, n_scopes=nK, n_epochs=nT, n_rows=len(s),
                  reference_star=int(star_ids[ref]), seconds=round(time.time() - t0, 3),
                  last_mjd=float(s["MJD"].max()), mode="full",
                  final_worst=history[-1] if history else None),
        star_scope=star_scope)
    sol.history = history
    if log:
        log(f"{filt}: {nS} stars, {nK} scopes, {nT} epochs, {loop + 1} loops "
            f"({'converged' if converged else 'NOT converged'}), {sol.meta['seconds']:.1f} s")
    return sol


# ---------------------------------------------------------------------------
# Incremental update
# ---------------------------------------------------------------------------

def update(sol: Solution, d: pd.DataFrame, bad_flags: int = BAD_FLAGS, refit_fraction: float = 0.1,
           refit_rms_factor: float = 2.0, log=None, refit_rms_floor: float = 0.002) -> tuple[Solution, dict]:
    """Add the epochs of ``d`` that are not in ``sol``.

    Star means, star / scope extra variances and scope offsets are kept; each new
    epoch gets DMAGT, rms_t from one ``arx`` of (m_obs - m*_s - DMAGS_k) over its
    comparison stars, σ² = σ_phot² + rms*_s² + rms_sc,k² + σ_m*².  A scope not seen
    before gets DMAGS = optimal mean of its new DMAGT (keeping DMAGT zero-mean in
    the scope) and is reported in ``info['new_scopes']``.

    ``info['needs_refit']`` lists reasons to run a full fit soon: a new scope,
    more than ``refit_fraction`` of the epochs added by updates, or new epochs
    whose median rms_t exceeds ``refit_rms_factor`` x that of the full fit.
    """
    t0 = time.time()
    d = clean_comparisons(d, bad_flags)
    known = set(sol.epochs["frame"])
    new = d[~d["frame"].astype(str).isin(known) & d["star_id"].isin(set(sol.stars["star_id"]))].copy()
    info = dict(new_epochs=0, new_scopes=[], seconds=0.0)
    if new.empty:
        return sol, info
    st = sol.stars.set_index("star_id")
    sc = sol.scopes.set_index("scope")
    new_scopes = sorted(set(new["scope"]) - set(sc.index))
    dmags = new["scope"].map(sc["DMAGS"]).fillna(0.0).to_numpy()
    rms_sc = new["scope"].map(sc["rms_sc"]).fillna(0.0).to_numpy()
    off = np.zeros(len(new)); off_err = new["star_id"].map(st["m_star_err"]).to_numpy()
    if sol.star_scope is not None:      # per-scope star means, as step 1 of the full fit
        key = pd.MultiIndex.from_arrays([new["star_id"].to_numpy(), new["scope"].astype(str).to_numpy()])
        ss = sol.star_scope.set_index(["star_id", "scope"])
        o = ss["offset"].reindex(key).to_numpy()
        oe = ss["offset_err"].reindex(key).to_numpy()
        ok = np.isfinite(o)
        off[ok] = o[ok]
        off_err = np.where(ok, oe, off_err)
    ckt = 0.0
    if sol.meta.get("colour_terms") and "CK" in sc and "colour" in st:
        dcs = (new["star_id"].map(st["colour"]) - sol.meta["c0"]).fillna(0.0).to_numpy()
        ckt = new["scope"].map(sc["CK"]).fillna(0.0).to_numpy() * dcs
    x = new["mag_inst"].to_numpy(float) - new["star_id"].map(st["m_star"]).to_numpy() - dmags - off - ckt
    sx = np.sqrt(new["magerr"].to_numpy(float) ** 2 + new["star_id"].map(st["rms_star"]).to_numpy() ** 2
                 + rms_sc ** 2 + off_err ** 2)
    codes, frames = pd.factorize(new["frame"].astype(str))
    order, starts = _groups(codes, len(frames))
    res = _arx_groups(x, sx, order, starts)
    first = pd.Series(np.arange(len(new))).groupby(codes).first().to_numpy()
    ep = pd.DataFrame({"frame": np.asarray(frames, dtype=str), "MJD": new["MJD"].to_numpy()[first],
                       "scope": new["scope"].to_numpy()[first], "DMAGT": res[:, 0], "DMAGT_err": res[:, 1],
                       "rms_t": res[:, 2], "rms_t_err": res[:, 3],
                       "n_stars": np.bincount(codes, minlength=len(frames)), "fit": "update"})
    scopes = sol.scopes.copy()
    for k in new_scopes:              # define the new scope's offset from its own epochs
        sel = ep["scope"] == k
        w = 1.0 / ep.loc[sel, "DMAGT_err"] ** 2
        off = float((ep.loc[sel, "DMAGT"] * w).sum() / w.sum())
        ep.loc[sel, "DMAGT"] -= off
        scopes = pd.concat([scopes, pd.DataFrame([{"scope": k, "DMAGS": off, "DMAGS_err": float(1 / np.sqrt(w.sum())),
                                                   "rms_sc": 0.0, "rms_sc_err": 0.0, "CK": 0.0, "CK_err": 0.0,
                                                   "n": int(sel.sum())}])],
                           ignore_index=True)
    out = Solution(sol.filter, sol.stars, scopes, pd.concat([sol.epochs, ep], ignore_index=True), star_scope=sol.star_scope,
                   meta={**sol.meta, "mode": "update", "last_mjd": float(max(sol.meta.get("last_mjd", 0), new["MJD"].max())),
                         "n_epochs": int(len(sol.epochs) + len(ep)),
                         "updates": int(sol.meta.get("updates", 0)) + 1})
    # when to schedule a full refit (the update never changes the old solution)
    n_upd = int((out.epochs["fit"] == "update").sum())
    frac_upd = n_upd / len(out.epochs)
    full_rms = float(sol.epochs.loc[sol.epochs["fit"] == "full", "rms_t"].median())
    new_rms = float(out.epochs.loc[out.epochs["fit"] == "update", "rms_t"].median())
    reasons = [r for r in sol.meta.get("needs_refit", []) if r.startswith("new scope")]
    if new_scopes:
        reasons.append("new scope " + ",".join(new_scopes))
    if frac_upd > refit_fraction:
        reasons.append(f"{frac_upd:.0%} of epochs from updates")
    if new_rms > refit_rms_factor * full_rms + refit_rms_floor:
        reasons.append(f"new-epoch rms_t {new_rms*1e3:.1f} mmag vs {full_rms*1e3:.1f}")
    out.meta["needs_refit"] = reasons
    info.update(new_epochs=len(ep), new_scopes=new_scopes, seconds=round(time.time() - t0, 4),
                needs_refit=reasons)
    if log:
        log(f"{sol.filter}: +{len(ep)} epochs in {info['seconds']*1000:.0f} ms"
            + (f"; new scopes {new_scopes}" if new_scopes else ""))
    return out, info


# ---------------------------------------------------------------------------
# Apply to the AGN (or any star)
# ---------------------------------------------------------------------------

def apply(sol: Solution, d: pd.DataFrame, zp: float = 0.0, zp_err: float = 0.0,
          max_rms_t: float = 0.05, min_stars: int = 5, colour: float | None = None) -> pd.DataFrame:
    """Calibrated light curve of the rows in ``d`` (normally the AGN rows):
    m = m_obs - DMAGT - DMAGS - CK (c_AGN - c0) + zp;  σ² = σ_phot² + rms_sc² + rms_t²
    (PyTICS AGN_LC, plus the per-scope colour term when the solution has one;
    ``colour`` defaults to ``meta['agn_colour']``, else c0 = no term).

    ``good``: the epoch's comparison stars agree (rms_t < ``max_rms_t``) and
    there are at least ``min_stars`` of them — thin cloud gradients, scattered
    light or a bad frame show up as a large rms_t (~1-4% of epochs)."""
    ep = sol.epochs.set_index("frame")
    sc = sol.scopes.set_index("scope")
    a = d[d["frame"].astype(str).isin(ep.index)].copy()
    f = a["frame"].astype(str)
    a["DMAGT"] = f.map(ep["DMAGT"]).to_numpy()
    a["rms_t"] = f.map(ep["rms_t"]).to_numpy()
    a["n_stars"] = f.map(ep["n_stars"]).to_numpy()
    a["DMAGS"] = a["scope"].map(sc["DMAGS"]).to_numpy()
    a["rms_sc"] = a["scope"].map(sc["rms_sc"]).to_numpy()
    a["CKterm"] = 0.0
    if sol.meta.get("colour_terms") and "CK" in sc:
        c = sol.meta.get("agn_colour", sol.meta["c0"]) if colour is None else colour
        a["CKterm"] = a["scope"].map(sc["CK"]).fillna(0.0).to_numpy() * (c - sol.meta["c0"])
    a["mag"] = a["mag_inst"] - a["DMAGT"] - a["DMAGS"] - a["CKterm"] + zp
    a["mag_err"] = np.sqrt(a["magerr"].astype(float) ** 2 + a["rms_sc"] ** 2 + a["rms_t"] ** 2)
    # epoch-to-epoch (random) part only: rms_sc is a per-camera systematic, common to all
    # epochs of a scope (AGN pairs < 1 h scatter as σ_phot ⊕ rms_t, not as mag_err)
    a["mag_err_rand"] = np.sqrt(a["magerr"].astype(float) ** 2 + a["rms_t"] ** 2)
    a["zp_err"] = zp_err
    a["good"] = (a["rms_t"] < max_rms_t) & (a["n_stars"] >= min_stars)
    return a


# ---------------------------------------------------------------------------
# Target driver: whole data set (full) or new frames only (update)
# ---------------------------------------------------------------------------

def load_target(phot_dir: Path, db: Path, data_id: str, filt: str, qc_only: bool = True,
                ignore_flags=None) -> pd.DataFrame:
    """PyTICS input for one filter: measurements x frame_qc, scope = telescope-camera.
    ``ignore_flags``: QC flags that do not exclude a frame (None = store.PYTICS_IGNORE_FLAGS)."""
    from ava.photometry.store import PYTICS_IGNORE_FLAGS, load_pytics

    d = load_pytics(phot_dir, db, data_id, filt=filt, qc_only=qc_only,
                    ignore_flags=PYTICS_IGNORE_FLAGS if ignore_flags is None else ignore_flags)
    d["scope"] = d["telid"].astype(str) + "-" + d["camera"].astype(str)
    return d


def solution_dir(phot_dir: Path, filt: str) -> Path:
    return Path(phot_dir) / "pytics" / filt


def _ref_scopes(scopes, prefixes):
    return [k for k in scopes if any(k.split("-", 1)[-1].startswith(p) for p in prefixes)]


def colour_term_check(lc0: pd.DataFrame, lc1: pd.DataFrame, ref_cameras=("fa",), min_gain: float = 0.05,
                      max_gap: float = 3.0, min_pairs: int = 10) -> dict:
    """Is the per-scope colour term worth it for this target and filter?

    Compares two AGN light curves of one filter (``lc0`` without, ``lc1`` with
    colour terms; output of :func:`apply` with ZP) on how well the reference
    cameras agree with each other: (a) rms of each camera's additive AGN offset
    against the others (flux-flux, a = 1, % of flux) and (b) robust σ of the flux
    ratio on nights seen by two cameras (< 0.4 d apart).  ``use`` = the mean
    relative improvement of (a) and (b) is >= ``min_gain``.  (a) needs ``min_pairs`` nights per camera
    (``ensemble.intercal_min_pairs``, as the intercalibration).  With fewer than two
    reference cameras or no usable metric the answer is ``use = False``
    (plain PyTICS)."""
    from ava.photometry import intercal as IC

    def metrics(lc):
        x = lc[lc["good"]].copy()
        scopes = _ref_scopes(sorted(x["scope"].unique()), ref_cameras)
        x = x[x["scope"].isin(scopes)]
        out = {"n_cameras": len(scopes), "offset_rms_pct": np.nan, "pair_sigma_pct": np.nan, "n_pairs": 0}
        if len(scopes) < 2:
            return out
        t = IC.intercalibrate(x, scopes, max_gap=max_gap, min_pairs=min_pairs)
        if len(t):
            out["offset_rms_pct"] = float(np.sqrt(np.mean((t["b1"] / t["F_mean"] * 100) ** 2)))
        F = IC.to_mjy(x["mag"])
        x = x.assign(F=F, night=np.floor(x["MJD"] - 0.5).astype(int))
        g = x.groupby(["night", "scope"]).agg(F=("F", "median"), MJD=("MJD", "median")).reset_index()
        r = []
        for _, h in g.groupby("night"):
            if len(h) >= 2:
                h = h.sort_values("MJD")
                dt = np.diff(h["MJD"].to_numpy()); fr = h["F"].to_numpy()
                r += list((fr[1:] / fr[:-1] - 1)[dt < 0.4])
        if len(r) >= 10:
            r = np.asarray(r) * 100
            out["pair_sigma_pct"] = float(1.4826 * np.median(np.abs(r - np.median(r))))
            out["n_pairs"] = len(r)
        return out

    m0, m1 = metrics(lc0), metrics(lc1)
    gains = [1 - m1[k] / m0[k] for k in ("offset_rms_pct", "pair_sigma_pct")
             if np.isfinite(m0[k]) and np.isfinite(m1[k]) and m0[k] > 0]
    gain = float(np.mean(gains)) if gains else float("nan")
    return {"without": m0, "with": m1, "gain": gain, "min_gain": min_gain,
            "use": bool(gains) and gain >= min_gain}


def run_target(phot_dir: Path, db: Path, data_id: str, filters, *, mode: str = "auto",
               min_epochs: int = 10, absolute: bool = True, colour_term: bool = True,
               scope_colour_terms="auto", colour_check_min_gain: float = 0.05, ref_cameras=("fa",),
               intercal_max_gap: float = 3.0, intercal_min_pairs: int = 10, colour_bands=("g", "i"),
               auto_refit: bool = True, ignore_qc_flags=None, update_kw: dict | None = None,
               apply_kw: dict | None = None, zp_kw: dict | None = None, anchor_kw: dict | None = None,
               log=print, **fit_kw) -> dict:
    """Calibrate ``data_id`` per filter and write ``agn_lightcurve_pytics.parquet``.

    mode: ``full`` refits everything; ``update`` adds new frames to the stored
    solutions; ``auto`` updates where a solution exists, otherwise fits.
    ``auto_refit``: when an update reports ``needs_refit``, run the full fit
    straight away (seconds per filter).
    ``scope_colour_terms``: ``"auto"`` (default) — after a full fit, refit with
    the per-scope colour terms and keep them only if :func:`colour_term_check`
    says the AGN agrees better between the ``ref_cameras`` (the answer differs
    between targets and filters; stored in ``meta['colour_check']`` and reused
    by updates); True / False / a list of filters forces the choice.
    ``absolute``: tie the star means to ``reference_stars.csv``
    (:func:`agn_zero_points`, colour term at the AGN colour); updates reuse the
    stored zero point (star means do not change in an update).
    ``anchor_kw``: when given (``ensemble.absolute_all_stars``), the absolute ZP uses every star in the
    frames (:func:`anchor_stars` with these settings), not only the comparison stars.
    ``colour_bands``: the star / AGN colour of every colour term (per-scope CK_k and the absolute C),
    ``(blue, red)`` reference bands (``ensemble.colour_bands``, default g - i).
    ``ignore_qc_flags``: frame_qc flags that do not keep a frame out (``ensemble.pytics_ignore_qc_flags``;
    None = the zero-point flags, :data:`ava.photometry.store.PYTICS_IGNORE_FLAGS`).
    ``fit_kw`` go to :func:`fit`, ``update_kw`` to :func:`update`, ``apply_kw`` to :func:`apply`.
    """
    from ava.photometry.calibration import FILTER_TO_BAND

    phot_dir = Path(phot_dir)
    ref_cols = tuple(f"lco_{b}" for b in colour_bands)
    band_filter = {}
    for filt, band in FILTER_TO_BAND.items():      # first (LCO) filter of each band: g -> gp, i -> ip
        band_filter.setdefault(band, filt)
    colour_filters = tuple(band_filter[b] for b in colour_bands)
    zp_kw = {**(zp_kw or {}), "colour": ref_cols}
    update_kw, apply_kw = dict(update_kw or {}), dict(apply_kw or {})
    sols, data, report = {}, {}, {}
    ref_path = phot_dir / "reference_stars.csv"
    from ava.photometry.reference import read_reference

    ref = read_reference(ref_path) if ref_path.exists() else None
    star_colours = None
    if scope_colour_terms and ref is not None:
        star_colours = (ref[ref_cols[0]] - ref[ref_cols[1]]).set_axis(ref["star_id"]).dropna()
    auto_ck = scope_colour_terms == "auto"
    forced = set(filters) if scope_colour_terms is True else (
        set() if auto_ck or not scope_colour_terms else set(scope_colour_terms))

    def full(d, agn_id, f):
        return fit(d, agn_id=agn_id, log=log, colours=star_colours if f in forced else None, **fit_kw)

    # ---- 1. fit (or update) every filter ------------------------------------------------
    for f in filters:
        d = load_target(phot_dir, db, data_id, f, ignore_flags=ignore_qc_flags)
        if d["frame"].nunique() < min_epochs:
            log(f"{f}: {d['frame'].nunique()} frames < {min_epochs}, skipped")
            continue
        agn_id = int(d.loc[d["is_agn"], "star_id"].iloc[0]) if d["is_agn"].any() else -1
        sdir = solution_dir(phot_dir, f)
        t0 = time.time()
        if mode == "full" or (mode == "auto" and not (sdir / "meta.json").exists()):
            sol, info = full(d, agn_id, f), {"mode": "full"}
        else:
            sol, info = update(Solution.load(sdir), d, log=log, **update_kw)
            info["mode"] = "update"
            if auto_refit and info.get("needs_refit"):
                log(f"{f}: full refit ({'; '.join(info['needs_refit'])})")
                sol, info["mode"] = full(d, agn_id, f), "update->full"
        sols[f], data[f] = sol, d
        report[f] = {**info, "seconds": round(time.time() - t0, 3), "n_epochs": len(sol.epochs),
                     "loops": sol.meta.get("loops"), "converged": sol.meta.get("converged")}
    # filters fully fitted in THIS run (B05: an update without new frames returns the stored solution, whose
    # meta still says mode "full"; counting it re-ran the colour check against itself)
    refitted = [f for f in sols if report[f]["mode"] in ("full", "update->full")]
    agn = {f: data[f][data[f]["is_agn"]] for f in sols}

    all_colours = (ref[ref_cols[0]] - ref[ref_cols[1]]).set_axis(ref["star_id"]).dropna() if ref is not None else None

    def anchors(sol, f):
        """Star means for the absolute ZP of ``sol`` (None: the comparison stars)."""
        if anchor_kw is None:
            return None
        return anchor_stars(sol, data[f], colours=all_colours, **anchor_kw)

    def zero_points():
        rel = {f: apply(s, agn[f], **apply_kw)["mag"].to_numpy() for f, s in sols.items()}
        stars = {f: anchors(s, f) for f, s in sols.items()} if anchor_kw is not None else None
        return agn_zero_points(sols, ref, rel, colour_term=colour_term, colour=colour_filters, zp_kw=zp_kw,
                               stars=stars)

    # ---- 2. per-scope colour terms: decide per filter from the data ------------------------
    if auto_ck and refitted and ref is not None and star_colours is not None:
        zps, fits = zero_points()
        c_agn = float(next(iter(fits.values()))["agn_colour"])
        for f in refitted:
            t0 = time.time()
            s1 = fit(data[f], agn_id=sols[f].meta["agn_id"], log=None, colours=star_colours, **fit_kw)
            z1 = absolute_zp(s1, ref, colour_term=colour_term, stars=anchors(s1, f), **zp_kw)
            zp1 = z1["zp"] + z1["C"] * (c_agn - z1["c0"])
            s1.meta["agn_colour"] = c_agn
            lc0 = apply(sols[f], agn[f], zps[f][0], **apply_kw)
            lc1 = apply(s1, agn[f], zp1, colour=c_agn, **apply_kw)
            chk = colour_term_check(lc0, lc1, ref_cameras, colour_check_min_gain, intercal_max_gap,
                                    intercal_min_pairs)
            log(f"{f}: colour terms {'ON' if chk['use'] else 'off'} (camera-consistency gain "
                f"{chk['gain']:+.0%}; offsets {chk['without']['offset_rms_pct']:.2f}->{chk['with']['offset_rms_pct']:.2f}%,"
                f" same-night {chk['without']['pair_sigma_pct']:.2f}->{chk['with']['pair_sigma_pct']:.2f}%)")
            if chk["use"]:
                sols[f] = s1
            sols[f].meta["colour_check"] = chk
            report[f]["colour_terms"] = chk["use"]
            report[f]["seconds"] = round(report[f]["seconds"] + time.time() - t0, 3)

    # ---- 3. absolute zero points ----------------------------------------------------------
    if absolute and refitted and ref is not None:
        zps, fits = zero_points()
        for f in refitted:
            z = fits[f]
            sols[f].meta.update(zp=zps[f][0], zp_err=zps[f][1], zp_fit={k: v for k, v in z.items() if k != "stars"},
                                agn_colour=float(z["agn_colour"]))
        (Path(phot_dir) / "pytics").mkdir(parents=True, exist_ok=True)   # first full fit: not created yet
        pd.concat([fits[f]["stars"].assign(filter=f) for f in fits]).to_parquet(
            Path(phot_dir) / "pytics" / "absolute_zp_stars.parquet", index=False)

    # ---- 4. AGN light curves ------------------------------------------------------------------
    lcs = []
    for f, sol in sols.items():
        sol.save(solution_dir(phot_dir, f))
        lc = apply(sol, agn[f], sol.meta.get("zp", 0.0), sol.meta.get("zp_err", 0.0), **apply_kw)
        lcs.append(lc)
        report[f].update(n_agn=len(lc), zp=sol.meta.get("zp"), zp_err=sol.meta.get("zp_err"),
                         colour_terms=bool(sol.meta.get("colour_terms")))
    write_zp_summary(phot_dir, sols)
    if lcs:
        lc = pd.concat(lcs, ignore_index=True)
        cols = ["frame", "MJD", "Filter", "telid", "camera", "scope", "mag", "mag_err", "mag_err_rand",
                "mag_inst", "magerr", "DMAGT", "DMAGS", "CKterm", "rms_t", "rms_sc", "n_stars", "good", "zp_err",
                "airmass", "seeing"]
        lc = lc[cols].sort_values(["Filter", "MJD"])
        lc.to_parquet(phot_dir / "agn_lightcurve_pytics.parquet", compression="zstd", index=False)
        lc.to_csv(phot_dir / "agn_lightcurve_pytics.csv", index=False, float_format="%.6f")
    return report


# ---------------------------------------------------------------------------
# Absolute zero point (PyTICS star means vs the GSPC reference catalogue)
# ---------------------------------------------------------------------------

ZP_SUMMARY = "absolute_zp.json"


def write_zp_summary(phot_dir: Path, sols: dict) -> dict:
    """Write ``pytics/absolute_zp.json`` from the zero points the light curve uses.

    Built from each solution's ``meta`` (``zp_fit`` + the applied ``zp``/``zp_err`` at
    the AGN colour), so it cannot disagree with ``pytics/<filter>/meta.json``.
    Filters already in the file but not in ``sols`` are kept (partial runs);
    a filter without an absolute ZP is left out.
    """
    path = Path(phot_dir) / "pytics" / ZP_SUMMARY
    out = json.loads(path.read_text()) if path.exists() else {}
    for f, s in sols.items():
        if "zp_fit" not in s.meta:
            out.pop(f, None)
            continue
        out[f] = {**s.meta["zp_fit"], "zp_agn": s.meta["zp"], "zp_agn_err": s.meta.get("zp_err"),
                  "colour_terms": bool(s.meta.get("colour_terms")), "source": f"pytics/{f}/meta.json"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, default=float))
    return out


def anchor_stars(sol: Solution, d: pd.DataFrame, *, colours: pd.Series | None = None, min_coverage: float = 0.9,
                 max_scatter: float = 0.2, trend_degree: int = 2, bad_flags: int = BAD_FLAGS) -> pd.DataFrame:
    """Star means for the absolute ZP from every star in the frames, not only the comparison stars.

    GSPC anchors exist only for G ≳ 14.2 (its SDSS / PS1 validity range), while the comparison stars are the
    brightest ``star_lim``: in dense fields they are all brighter, and in Y only bright stars pass a raw-scatter
    cut, so the ZP had 0-3 anchors (19 Nov 2026; tools/abscal_validation/anchor_sweep.py).  Here each star is put
    on the ensemble scale with the solved offsets, exactly as :func:`apply` treats the AGN:

        m = mag_inst - DMAGT(frame) - DMAGS(scope) [- CK(scope) (c - c0)]

    on the solution's epochs (``bad_flags`` measurements dropped); the star mean is the median.

    * comparison stars keep PyTICS's own ``m_star`` / ``m_star_err``;
    * other stars must be detected in ≥ ``min_coverage`` of the epochs of the best-covered star (faint stars
      seen only in good frames are biased bright) and scatter ≤ ``max_scatter`` mag (robust, per epoch);
      their means are shifted by the median (ours − PyTICS) of the well-covered comparison stars (gauge);
    * ``rms_star`` (used by :func:`absolute_zp` to reject variables) becomes the scatter in excess of the
      typical scatter of stars of the same brightness: a polynomial (``trend_degree``) in m_star fitted to
      log(scatter), iteratively clipped at +3 MAD so variables do not pull it (a running median was biased low
      at the faint end, where the window only sees brighter stars).  Photometric noise is not variability.
      ``rms_raw`` keeps the robust per-epoch scatter.

    Returns star_id, m_star, m_star_err, rms_star, rms_raw, rms_trend, n, source ("comparison" | "extra").
    """
    cols = ["star_id", "m_star", "m_star_err", "rms_star", "rms_raw", "rms_trend", "n", "source"]
    ep = sol.epochs.set_index("frame")
    sc = sol.scopes.set_index("scope")
    m = d[~d["is_agn"].astype(bool) & d["frame"].astype(str).isin(ep.index)]
    if bad_flags and "sex_flags" in m:
        m = m[(m["sex_flags"].fillna(0).astype(int) & bad_flags) == 0]
    if m.empty:
        return pd.DataFrame(columns=cols)
    fr = m["frame"].astype(str)
    mc = (m["mag_inst"].to_numpy(float) - fr.map(ep["DMAGT"]).to_numpy(float)
          - m["scope"].map(sc["DMAGS"]).to_numpy(float))
    if sol.meta.get("colour_terms") and "CK" in sc:
        ck = m["scope"].map(sc["CK"]).fillna(0.0).to_numpy(float)
        c = (m["star_id"].map(colours) if colours is not None else pd.Series(np.nan, index=m.index)).to_numpy(float)
        # a star without g-i cannot take the per-scope term (NaN: dropped) unless that scope has none
        mc = mc - np.where(ck == 0, 0.0, ck * (c - float(sol.meta.get("c0", 0.0))))
    t = pd.DataFrame({"star_id": m["star_id"].to_numpy(), "mc": mc})
    t = t[np.isfinite(t["mc"])]
    g = t.groupby("star_id")["mc"]
    med = g.median()
    s = pd.DataFrame({"m_star": med, "n": g.size()})
    s["rms_raw"] = 1.4826 * (t["mc"] - t["star_id"].map(med)).abs().groupby(t["star_id"]).median()
    s["m_star_err"] = 1.2533 * s["rms_raw"] / np.sqrt(s["n"])          # error of a median
    n_full = min_coverage * s["n"].max()
    comp = sol.stars.set_index("star_id")
    both = s.index.intersection(comp.index)
    well = both[(s.loc[both, "n"] >= n_full).to_numpy()]
    gauge = float(np.median(s.loc[well, "m_star"] - comp.loc[well, "m_star"])) if len(well) else 0.0
    s["m_star"] -= gauge
    s.loc[both, "m_star"] = comp.loc[both, "m_star"]
    s.loc[both, "m_star_err"] = comp.loc[both, "m_star_err"]
    s["source"] = "extra"
    s.loc[both, "source"] = "comparison"
    s = s[(s["source"] == "comparison") | ((s["n"] >= n_full) & (s["rms_raw"] <= max_scatter))]
    s = s.sort_values("m_star")
    s["rms_trend"] = _scatter_trend(s["m_star"].to_numpy(float), s["rms_raw"].to_numpy(float), trend_degree)
    s["rms_star"] = np.sqrt(np.clip(s["rms_raw"] ** 2 - s["rms_trend"] ** 2, 0, None))
    return s.reset_index()[cols]


def _scatter_trend(m: np.ndarray, rms: np.ndarray, degree: int = 2, n_iter: int = 5) -> np.ndarray:
    """Typical per-epoch scatter at each magnitude: poly(degree) in m fitted to log(rms), clipping stars
    more than 3 MAD above it (variables); falls back to the median for fewer than 3 (degree + 1) stars."""
    ok = np.isfinite(m) & np.isfinite(rms) & (rms > 0)
    if ok.sum() < 3 * (degree + 1):
        return np.full(len(m), float(np.median(rms[ok])) if ok.any() else np.nan)
    y = np.log(np.clip(rms, 1e-4, None))
    use = ok.copy()
    for _ in range(n_iter):
        p = np.polyfit(m[use], y[use], degree)
        r = y - np.polyval(p, m)
        mad = 1.4826 * np.median(np.abs(r[use] - np.median(r[use])))
        new = ok & (r < 3 * max(mad, 0.05))
        if (new == use).all() or new.sum() < 3 * (degree + 1):
            break
        use = new
    # beyond the fitted range keep the end values (no extrapolation of the polynomial)
    mm = np.clip(m, m[use].min(), m[use].max())
    return np.exp(np.polyval(p, mm))


def absolute_zp(sol: Solution, ref: pd.DataFrame, *, colour=("lco_g", "lco_i"), colour_term: bool = True,
                clip: float = 3.0, floor: float = 0.01, max_rms_star: float = 0.05,
                stars: pd.DataFrame | None = None) -> dict:
    """ZP (+ colour term) mapping the ensemble's star means onto the reference system:

        m_ref - m*_s = ZP + C (c_s - c0),   c = colour[0] - colour[1],  c0 = median star colour

    weighted by 1 / (σ_m*² + σ_ref² + rms*² + floor²), iteratively ``clip``-σ clipped.
    One fit per filter over ~100 stars x all epochs — far better determined than a
    per-frame ZP.  Returns ZP, C, c0, errors, n, scatter and the per-star table.
    ``stars``: the star means to use (:func:`anchor_stars`); default the comparison stars (``sol.stars``).
    """
    from ava.photometry.calibration import FILTER_TO_BAND

    band = FILTER_TO_BAND[sol.filter]
    col_b = f"lco_{band}"
    r = ref[(ref["quality_ok"].astype(bool)) & ~ref["is_agn"].astype(bool)]
    base = sol.stars if stars is None else stars
    t = base.merge(r[list(dict.fromkeys(["star_id", col_b, col_b + "_err", *colour]))], on="star_id")
    t = t[np.isfinite(t[col_b]) & np.isfinite(t[colour[0]]) & np.isfinite(t[colour[1]])
          & (t["rms_star"] < max_rms_star)].copy()
    t["dm"] = t[col_b] - t["m_star"]
    t["c"] = t[colour[0]] - t[colour[1]]
    c0 = float(np.median(t["c"])) if len(t) else 0.0
    t["sig"] = np.sqrt(t["m_star_err"] ** 2 + t[col_b + "_err"].fillna(0.05) ** 2 + t["rms_star"] ** 2 + floor ** 2)
    use = np.ones(len(t), bool)
    zp = C = zpe = Ce = np.nan
    for _ in range(10):
        if use.sum() < 3:
            break
        x, y, w = (t["c"] - c0).to_numpy()[use], t["dm"].to_numpy()[use], 1 / t["sig"].to_numpy()[use] ** 2
        if colour_term and use.sum() >= 6 and np.ptp(x) > 0.2:
            A = np.vstack([np.ones_like(x), x]).T
            cov = np.linalg.inv(A.T @ (A * w[:, None]))
            zp, C = cov @ (A.T @ (w * y))
            zpe, Ce = np.sqrt(np.diag(cov))
        else:
            zp, zpe, C, Ce = float(np.sum(w * y) / np.sum(w)), float(1 / np.sqrt(np.sum(w))), 0.0, 0.0
        res = t["dm"].to_numpy() - zp - C * (t["c"].to_numpy() - c0)
        mad = 1.4826 * np.median(np.abs(res[use] - np.median(res[use])))
        new = np.abs(res) < clip * max(mad, floor)
        if (new == use).all():
            break
        use = new
    t["res"] = t["dm"] - zp - C * (t["c"] - c0)
    t["used"] = use
    # scale errors by sqrt(chi2_nu) when > 1 (systematic star-to-star scatter)
    chi = np.sqrt(np.sum((t["res"][use] / t["sig"][use]) ** 2) / max(use.sum() - 2, 1)) if use.sum() > 2 else 1.0
    return dict(filter=sol.filter, band=band, zp=float(zp), zp_err=float(zpe * max(chi, 1)), C=float(C),
                C_err=float(Ce * max(chi, 1)), c0=c0, colour="-".join(colour), n=int(use.sum()), n_all=len(t),
                scatter=float(np.std(t["res"][use])), chi2nu=float(chi ** 2), stars=t)


def agn_zero_points(sols: dict, ref: pd.DataFrame, agn_lc: dict | None = None, colour_term: bool = True,
                    n_iter: int = 3, colour=("gp", "ip"), zp_kw: dict | None = None,
                    stars: dict | None = None) -> dict:
    """{filter: (zp_at_AGN_colour, err)} with the AGN colour from its own calibrated
    mean magnitudes (iterated; the colour term is then evaluated at the AGN's colour).
    ``stars``: {filter: star means} (:func:`anchor_stars`); missing filters use the comparison stars."""
    stars = stars or {}
    fits = {f: absolute_zp(s, ref, colour_term=colour_term, stars=stars.get(f), **(zp_kw or {}))
            for f, s in sols.items()}
    # start from the median star colour of the fits that worked (a failed fit has no stars and c0 = 0)
    usable = [z["c0"] for z in fits.values() if z["n"] > 0 and np.isfinite(z["zp"])]
    c_agn = float(np.median(usable)) if usable else float("nan")
    for _ in range(n_iter):
        if agn_lc is None or not all(k in agn_lc for k in colour):
            break
        mags = {k: float(np.nanmedian(agn_lc[k])) + fits[k]["zp"] + fits[k]["C"] * (c_agn - fits[k]["c0"])
                for k in colour}
        new = mags[colour[0]] - mags[colour[1]]
        if not np.isfinite(new):        # g or i without a zero point: keep the star-colour estimate
            break
        c_agn = new
    out = {}
    for f, z in fits.items():
        dc = c_agn - z["c0"]
        if z["C"] == 0 or not np.isfinite(dc):   # no colour term (or no AGN colour): the plain ZP
            dz, dz_err = 0.0, 0.0
        else:
            dz, dz_err = z["C"] * dc, z["C_err"] * abs(dc)
        out[f] = (z["zp"] + dz, float(np.hypot(z["zp_err"], dz_err)))
        z["agn_colour"] = c_agn
        z["zp_agn"] = out[f][0]
    return out, fits
