"""Synthetic-photometry helpers for the AGN SED-correction study (tools/abscal_validation).

Passbands: data/reference/lco_filters (LCO natural: Sinistro CCD + atmosphere, X = 1) and
data/reference/ref_filters (reference systems of the GSPC anchors: SDSS u g r i z, Landolt B V).
Stars: Pickles UVKLIB from the synphot tree ($PYSYN_CDBS). AB magnitudes, photon counting.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
from astropy.io import fits
from scipy.interpolate import UnivariateSpline

ROOT = Path(__file__).resolve().parents[2]
CDBS = Path(os.environ.get("PYSYN_CDBS", ""))
C_LIGHT = 2.99792458e18
BANDS = ["u", "B", "g", "V", "r", "i", "z"]
FILTER_OF = dict(u="up", B="B", g="gp", V="V", r="rp", i="ip", z="zs")
REF_NAME = dict(u="sdss_u", B="landolt_B", g="sdss_g", V="landolt_V", r="sdss_r", i="sdss_i", z="sdss_z",
                Y="ps1_y")   # Y: passband plots only (FLOYDS does not reach it)
REF_LABEL = dict(u="SDSS u", B="Landolt B", g="SDSS g", V="Landolt V", r="SDSS r", i="SDSS i", z="SDSS z",
                 Y="PS1 y")
# rest-frame windows free of strong AGN lines (continuum spline)
LINE_FREE_REST = [(3600, 3640), (3790, 3820), (4020, 4060), (4180, 4230), (4440, 4460), (4530, 4560),
                  (5080, 5130), (5420, 5470), (5600, 5650), (6050, 6200), (6850, 6880), (7000, 7050),
                  (7400, 7700), (7950, 8100), (8350, 8450), (8800, 8840), (9000, 9200)]
LINES_REST = {"Hδ": 4102, "Hγ": 4340, "He II": 4686, "Hβ": 4861, "[O III]": 5007, "He I": 5876,
              "[O I]": 6300, "Hα": 6563, "[S II]": 6724, "[S III]": 9069, "[S III] ": 9531, "[O II]": 3727,
              "[Ne V]": 3426, "Ca II": 8542}


def load_curve(kind: str, band: str, shift: float = 0.0):
    sub, name = ("lco_filters", f"lco_{band}") if kind == "lco" else ("ref_filters", REF_NAME[band])
    w, t = np.loadtxt(ROOT / "data/reference" / sub / f"{name}.txt", unpack=True)
    return w + shift, np.clip(t, 0, None)


def span(wt, frac=0.001):
    w, t = wt
    ok = t > frac * t.max()
    return w[ok].min(), w[ok].max()


def abmag(w, fl, wt):
    """AB magnitude of f_lambda (any units: offsets cancel in differences) through photon response wt."""
    fw, ft = wt
    lo, hi = span(wt)
    if w.min() > lo or w.max() < hi:
        return np.nan
    g = np.linspace(lo, hi, 4000)
    T = np.interp(g, fw, ft)
    F = np.interp(g, w, fl)
    return -2.5 * np.log10(np.trapezoid(F * T * g, g) / np.trapezoid(T * C_LIGHT / g, g)) - 48.6


class Filters:
    def __init__(self, lco_shift: dict | None = None):
        lco_shift = lco_shift or {}
        self.shift = {b: lco_shift.get(b, 0.0) for b in BANDS}
        self.lco = {b: load_curve("lco", b, self.shift[b]) for b in BANDS}
        self.ref = {b: load_curve("ref", b) for b in BANDS}

    def mags(self, w, fl):
        out = {}
        for b in BANDS:
            out[f"lco_{b}"] = abmag(w, fl, self.lco[b])
            out[f"ref_{b}"] = abmag(w, fl, self.ref[b])
        out["gi"] = out["ref_g"] - out["ref_i"]
        return out


def pickles():
    """[(name, wave, flam)] for the Pickles UVKLIB library."""
    out = []
    for f in sorted(glob.glob(str(CDBS / "grid/pickles/dat_uvk/pickles_uk_*.fits"))):
        h = fits.open(f)
        d = h[1].data
        out.append((str(h[0].header.get("SPTYPE", Path(f).stem)), d["WAVELENGTH"].astype(float), d["FLUX"].astype(float)))
    if not out:
        raise SystemExit("Pickles library not found: set PYSYN_CDBS to the synphot data tree")
    return out


def stellar_transform(filters: Filters, lib, gi_range=(0.0, 2.7)):
    """Per band: Δ = m_ref − m_LCO = a + C (g−i) fitted over gi_range; returns {band: (a, C, rms, n)}."""
    rows = [filters.mags(w, f) for _, w, f in lib]
    gi = np.array([r["gi"] for r in rows])
    out = {}
    for b in BANDS:
        d = np.array([r[f"ref_{b}"] - r[f"lco_{b}"] for r in rows])
        k = np.isfinite(d) & np.isfinite(gi) & (gi > gi_range[0]) & (gi < gi_range[1])
        C, a = np.polyfit(gi[k], d[k], 1)
        out[b] = (a, C, float(np.std(d[k] - a - C * gi[k])), int(k.sum()))
    return out, gi, rows


# ---------------- AGN spectra ----------------

def read_floyds(path, split: float = 5300.0, overlap=(5300.0, 5600.0)):
    """Spectrum from the per-order EXTRACTED fluxes (AVA fork: fringe-corrected ``flux_optimal``; archive
    BANZAI: ``flux``), blue order (2) below ``split`` and red order (1) from ``split`` on — the products'
    convention (``spectroscopy.products.prepspec.red_min_wavelength``). The merged SPECTRUM table is not
    used: it is not fringe-corrected and mixes both orders over the whole overlap.

    Returns wave, flux, red/blue ratio in ``overlap`` (median), and a mask of red-order points."""
    d = fits.open(path)["EXTRACTED"].data
    col = "flux_optimal" if "flux_optimal" in d.columns.names else "flux"
    good = (d["mask"] == 0) & np.isfinite(d[col]) & (d[col] > 0)
    w_all = d["wavelength"].astype(float)
    red = good & (d["order"] == 1)
    blue = good & (d["order"] == 2)
    wr, fr = w_all[red], d[col][red].astype(float)
    wb, fb = w_all[blue], d[col][blue].astype(float)
    orr, ob = np.argsort(wr), np.argsort(wb)
    wr, fr, wb, fb = wr[orr], fr[orr], wb[ob], fb[ob]
    g = np.arange(overlap[0], overlap[1], 5.0)
    ratio = float(np.median(np.interp(g, wr, fr) / np.interp(g, wb, fb)))
    kb, kr = wb < split, wr >= split
    w = np.concatenate([wb[kb], wr[kr]])
    fl = np.concatenate([fb[kb], fr[kr]])
    isred = np.concatenate([np.zeros(kb.sum(), bool), np.ones(kr.sum(), bool)])
    return w, fl, ratio, isred


def continuum(w, fl, z):
    wr = w / (1 + z)
    xs, ys = [], []
    for lo, hi in LINE_FREE_REST:
        k = (wr > lo) & (wr < hi)
        if k.sum() > 3:
            xs.append(np.median(w[k]))
            ys.append(np.log(np.median(fl[k])))
    xs, ys = np.array(xs), np.array(ys)
    sp = UnivariateSpline(xs, ys, k=3, s=len(xs) * 0.002)
    c = sp(np.clip(w, xs[0], xs[-1]))
    lo, hi = w < xs[0], w > xs[-1]
    c[lo] = ys[0] + (ys[1] - ys[0]) / (xs[1] - xs[0]) * (w[lo] - xs[0])
    c[hi] = ys[-1] + (ys[-1] - ys[-2]) / (xs[-1] - xs[-2]) * (w[hi] - xs[-1])
    return np.exp(c)


_SEY = None


def extend(w, fl, z):
    """Blue: NGC 5548 Seyfert-1 template (moved to z) below the spectrum, scaled at its first 150 Å;
    red: power law fitted at 8300–10000 Å out to 11500 Å. Returns wave, flux, mask of measured points."""
    global _SEY
    if _SEY is None:
        d = fits.open(CDBS / "grid/agn/seyfert1_template.fits")[1].data
        _SEY = (d["WAVELENGTH"].astype(float) / 1.01717, d["FLUX"].astype(float))
    sw, sf = _SEY[0] * (1 + z), _SEY[1]
    k = (w > w.min() + 100) & (w < w.min() + 250)
    s = np.median(fl[k]) / np.median(np.interp(w[k], sw, sf))
    lo = (sw < w[k].min()) & (sw > 2500)
    lo &= sw < w.min()
    k2 = (w > 8300) & (w < min(w.max(), 10000))
    p = np.polyfit(np.log(w[k2]), np.log(fl[k2]), 1)
    whi = np.arange(w.max() + 2, 11500, 2.0)
    W = np.concatenate([sw[lo], w, whi])
    F = np.concatenate([s * sf[lo], fl, np.exp(np.polyval(p, np.log(whi)))])
    meas = np.concatenate([np.zeros(lo.sum(), bool), np.ones(len(w), bool), np.zeros(len(whi), bool)])
    return W, F, meas


def extrapolated_fraction(W, meas, wt):
    """Fraction of the band's response-weighted range not covered by measured points."""
    fw, ft = wt
    T = np.interp(W, fw, ft, left=0, right=0) * np.gradient(W)
    return float(np.sum(T[~meas]) / max(np.sum(T), 1e-30))
