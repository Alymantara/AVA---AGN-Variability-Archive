"""
ava.photometry.calibration — per-frame zero point and AGN magnitude.

Replaces the maths of ``__old_pipeline__/ava_calibrate.py``.  Equations, for
one frame at the science aperture *k* (chosen per catalogue, see
:mod:`ava.photometry.apertures`):

    m_inst      = MAG_APER_k + 2.5 log10(t_exp)               (per-second instrumental mag)
    d_i         = m_ref,i - m_inst,i                          (each standard star i)
    w_i         = 1 / (σ_inst,i² + σ_ref,i² + σ_floor²)
    ZP          = Σ w_i d_i / Σ w_i        (iterated, rejecting |d_i - ZP| > κ·1.4826·MAD)
    σ_ZP        = sqrt(1 / Σ w_i) · max(1, sqrt(χ²_ν))
    m_AGN       = m_inst,AGN + ZP,          σ_AGN² = σ_inst,AGN² + σ_ZP²

The AGN and the standards are measured in the SAME aperture, so the light a
point source loses outside it (seeing-dependent) cancels.  Deliberately NOT
applied — each was a bug or a no-op in the legacy code:

* no aperture correction to the largest aperture (applied to the stars only,
  it made the AGN magnitude seeing-dependent);
* no airmass term (in-field standards share the frame's airmass; it cancels);
* no colour term on the AGN (the legacy code used Fairall 9's catalogue
  colour for every target).  Colour terms belong to the absolute-calibration
  step; here ``colour_slope`` (d vs. reference g-i) is only a QC number.

Standards: matched reference stars with ``quality_ok``, not the AGN, SExtractor
flags 0, S/N > ``min_snr``, peak below ``max_peak_frac`` of saturation, more
than ``edge_px`` from the frame edge, finite reference magnitude.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

#: LCO filter name -> reference-catalogue band (reference_stars.csv lco_<band>).
FILTER_TO_BAND = {"up": "u", "U": "u", "B": "B", "gp": "g", "V": "V", "rp": "r", "R": "R",
                  "ip": "i", "I": "I", "zs": "z", "Y": "Y"}


@dataclass
class ZPSettings:
    min_snr: float = 20.0           # standards: σ_inst < 1.0857 / min_snr
    max_peak_frac: float = 0.8      # standards: FLUX_MAX + BACKGROUND < this x SATURATE
    edge_px: float = 30.0           # standards: distance from the frame edge (photometry.pix_edge)
    sigma_floor: float = 0.01       # added in quadrature to every standard's error (mag)
    clip_kappa: float = 3.0
    min_standards: int = 5


@dataclass
class ZPResult:
    zp: float = np.nan
    zp_err: float = np.nan
    zp_scatter: float = np.nan      # robust (1.4826 MAD) scatter of d_i about ZP
    chi2_nu: float = np.nan
    n_used: int = 0
    n_candidates: int = 0
    colour_slope: float = np.nan    # d(d_i)/d(g-i): QC only
    used: np.ndarray = field(default_factory=lambda: np.zeros(0, bool))


def standard_mask(meas: pd.DataFrame, ref_mag: np.ndarray, *, saturate: float | None,
                  naxis1: float | None, naxis2: float | None, s: ZPSettings) -> np.ndarray:
    """Candidate standards among matched detections (``meas`` from catalogs.measurements
    merged with the reference columns ``quality_ok``)."""
    m = (meas["star_id"].notna().to_numpy() & ~meas["is_agn"].to_numpy()
         & meas["quality_ok"].fillna(False).to_numpy().astype(bool)
         & (meas["sex_flags"].to_numpy() == 0)
         & np.isfinite(ref_mag) & np.isfinite(meas["mag_inst"].to_numpy())
         & (meas["magerr"].to_numpy() > 0) & (meas["magerr"].to_numpy() < 1.0857 / s.min_snr))
    # a missing value (None / NaN / <= 0: header keyword absent) skips that cut; NaN used to fail every
    # comparison and so rejected every standard (B16)
    def _given(v):
        return v is not None and np.isfinite(float(v)) and float(v) > 0
    if _given(saturate):
        m &= (meas["flux_max"].to_numpy() + meas["background"].to_numpy()) < s.max_peak_frac * saturate
    if _given(naxis1) and _given(naxis2):
        x, y = meas["x"].to_numpy(), meas["y"].to_numpy()
        m &= (x > s.edge_px) & (x < naxis1 - s.edge_px) & (y > s.edge_px) & (y < naxis2 - s.edge_px)
    return m


def zero_point(d: np.ndarray, err_inst: np.ndarray, err_ref: np.ndarray, s: ZPSettings,
               colour: np.ndarray | None = None) -> ZPResult:
    """Weighted, iteratively clipped zero point from d_i = m_ref,i - m_inst,i."""
    res = ZPResult(n_candidates=int(len(d)), used=np.zeros(len(d), bool))
    if len(d) < s.min_standards:
        return res
    var = err_inst**2 + np.nan_to_num(err_ref, nan=0.0)**2 + s.sigma_floor**2
    w = 1.0 / var
    use = np.ones(len(d), bool)
    for _ in range(10):
        zp = np.sum(w[use] * d[use]) / np.sum(w[use])
        mad = 1.4826 * np.median(np.abs(d[use] - np.median(d[use])))
        new = np.abs(d - zp) <= s.clip_kappa * max(mad, 0.005)
        if new.sum() < s.min_standards or np.array_equal(new, use):
            break
        use = new
    n = int(use.sum())
    if n < s.min_standards:
        return res
    zp = float(np.sum(w[use] * d[use]) / np.sum(w[use]))
    chi2_nu = float(np.sum(w[use] * (d[use] - zp) ** 2) / max(n - 1, 1))
    res.zp = zp
    res.zp_err = float(np.sqrt(1.0 / np.sum(w[use])) * max(1.0, np.sqrt(chi2_nu)))
    res.zp_scatter = float(1.4826 * np.median(np.abs(d[use] - np.median(d[use]))))
    res.chi2_nu, res.n_used, res.used = chi2_nu, n, use
    if colour is not None:
        ok = use & np.isfinite(colour)
        if ok.sum() >= 5 and np.ptp(colour[ok]) > 0.3:
            res.colour_slope = float(np.polyfit(colour[ok], d[ok] - zp, 1, w=np.sqrt(w[ok]))[0])
    return res


def calibrate_frame(meas: pd.DataFrame, ref: pd.DataFrame, *, filt: str, exptime: float,
                    saturate: float | None = None, naxis1: float | None = None, naxis2: float | None = None,
                    settings: ZPSettings | None = None) -> tuple[pd.DataFrame, ZPResult, dict]:
    """Zero point of one frame and calibrated magnitudes of its matched detections.

    ``meas``: :func:`ava.photometry.catalogs.measurements` output (``mag``/``magerr`` at
    the science aperture).  Returns (meas with mag_inst / is_standard / used_in_zp,
    ZPResult, AGN dict {mag, mag_err, mag_inst, magerr_inst} or {}).
    """
    s = settings or ZPSettings()
    band = FILTER_TO_BAND.get(filt)
    m = meas.copy()
    m["mag_inst"] = m["mag"] + 2.5 * np.log10(exptime)
    cols = ["star_id", "quality_ok"] + ([f"lco_{band}", f"lco_{band}_err"] if band else []) + ["lco_g", "lco_i"]
    m = m.merge(ref[[c for c in dict.fromkeys(cols) if c in ref]], on="star_id", how="left")
    m["is_standard"] = False
    m["used_in_zp"] = False
    if band is None or f"lco_{band}" not in m:   # no reference magnitudes in this band (R / I with the APASS
        return m, ZPResult(), {}                   # fallback catalogue): no zero point, not a KeyError (B15)
    ref_mag = m[f"lco_{band}"].to_numpy(float)
    cand = standard_mask(m, ref_mag, saturate=saturate, naxis1=naxis1, naxis2=naxis2, s=s)
    m.loc[cand, "is_standard"] = True
    d = ref_mag[cand] - m["mag_inst"].to_numpy()[cand]
    colour = None
    if "lco_g" in m and "lco_i" in m:
        colour = (m["lco_g"] - m["lco_i"]).to_numpy(float)[cand]
    zp = zero_point(d, m["magerr"].to_numpy()[cand], m[f"lco_{band}_err"].to_numpy(float)[cand], s, colour)
    idx = np.flatnonzero(cand)
    m.loc[m.index[idx[zp.used]], "used_in_zp"] = True
    agn = {}
    a = m[m["is_agn"]]
    if len(a) and np.isfinite(zp.zp):
        r = a.iloc[0]
        agn = dict(mag_inst=float(r["mag_inst"]), magerr_inst=float(r["magerr"]),
                   mag=float(r["mag_inst"] + zp.zp), mag_err=float(np.hypot(r["magerr"], zp.zp_err)),
                   sex_flags=int(r["sex_flags"]),
                   # peak counts (FLUX_MAX + BACKGROUND, ADU): frame QC flags near-saturated AGN
                   peak=float(r["flux_max"] + r["background"]) if {"flux_max", "background"} <= set(r.index) else np.nan)
    return m.drop(columns=[c for c in m.columns if c.startswith("lco_")]), zp, agn
