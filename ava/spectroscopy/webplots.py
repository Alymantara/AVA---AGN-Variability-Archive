"""
ava.spectroscopy.webplots — website figures of the FLOYDS spectroscopy of one target.

* ``latest_spectrum``  → ``lco_latest_<target>_spec``       blue and red arm of the latest spectrum
* ``latest_hbeta_fit`` → ``lco_latest_<target>_hbeta_fit``  the Hβ-region fit of that spectrum (reference)
* ``hbeta_lightcurve`` → ``lco_latest_<target>_hbeta``      broad Hβ, 5100 Å continuum, g band if it overlaps

House style: ticks inside on all axes (minor at half length, ``ava.plots.webplots._style``), Okabe–Ito colours,
filter colours from ``filter_dict``; one figure width for all spectroscopy plots so they line up on the page.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ava.plots.webplots import serialized
from ava.spectroscopy import lines as L

WIDTH = 9.0                      # inches; every spectroscopy web figure. The website shows plots ~650 px wide, so
                                 # 9 in at 150 dpi keeps 14 pt text at ~15-16 px on screen (the page body size)
BLUE, RED, GREEN, GREY = "#0072B2", "#D55E00", "#009E73", "0.45"
INK, MUTED = "0.15", "0.45"
LINES = {"[Ne V]": 3426.0, "[O II]": 3727.4, "Hδ": 4101.7, "Hγ": 4340.5, "He II": 4685.7, "Hβ": 4861.3,
         "[O III]": 5006.8, "He I": 5875.6, "[O I]": 6300.3, "Hα": 6562.8, "[S II]": 6724.0,
         "Ca II": 8542.0}
TELLURIC = ((6865, 6935), (7160, 7340), (7590, 7700), (8130, 8360))
CREDIT = "AVA · LCO FLOYDS"


def _setup():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from ava.plots import webplots as wp

    wp._style()
    plt.rcParams.update({"font.size": 14, "axes.labelsize": 15, "axes.titlesize": 16, "legend.frameon": False,
                         "legend.fontsize": 12, "xtick.labelsize": 13, "ytick.labelsize": 13,
                         "axes.linewidth": 1.2, "savefig.facecolor": "white"})
    return plt


def _save(fig, out_base: Path, formats) -> list[str]:
    files = []
    for fmt in formats:
        f = f"{out_base}.{fmt}"
        fig.savefig(f, dpi=150, bbox_inches="tight")
        files.append(f)
    return files


def _credit(fig):
    fig.text(0.995, 0.005, f"{CREDIT} · {datetime.now(timezone.utc):%Y-%m-%d}", ha="right", va="bottom",
             fontsize=10, color=MUTED)


def _header(fig, title, subtitle, height_in):
    """Bold title and a muted subtitle line, top-left; returns the top of the axes area (figure fraction)."""
    fig.text(0.01, 1 - 0.08 / height_in, title, ha="left", va="top", fontsize=17, fontweight="bold", color=INK)
    fig.text(0.01, 1 - 0.42 / height_in, subtitle, ha="left", va="top", fontsize=12, color=MUTED)
    return 1 - 0.74 / height_in


def _ylim(f, top_pad=0.18):
    from scipy.ndimage import median_filter

    sm = median_filter(np.asarray(f, float), 5, mode="nearest")      # line peaks, not single-pixel spikes
    lo, hi = np.nanpercentile(sm, 0.5), np.nanmax(sm)
    return min(0.0, lo) - 0.03 * (hi - lo), hi + top_pad * (hi - lo)


@serialized
def latest_spectrum(arms: dict, hdr: dict, target_name: str, z: float, out_base: Path, formats=("png",),
                    red_range=(5300.0, 9050.0), unit=1e-15) -> list[str]:
    """Two panels: blue arm, red arm (``red_range`` observed Å).  Lines marked at the redshift; tellurics shaded."""
    plt = _setup()
    fig, ax = plt.subplots(2, 1, figsize=(WIDTH, 7.8))
    for a, arm, col in ((ax[0], "blue", BLUE), (ax[1], "red", RED)):
        s = arms[arm]
        if arm == "red":
            s = s[(s.w >= red_range[0]) & (s.w <= red_range[1])]
        y = s.f / unit
        a.fill_between(s.w, 0, y, color=col, alpha=0.07, lw=0, step="mid")
        a.plot(s.w, y, color=col, lw=1.4, drawstyle="steps-mid")
        a.set_xlim(s.w.min(), s.w.max())
        a.set_ylim(*_ylim(y))
        if arm == "red":
            for b0, b1 in TELLURIC:
                if b1 > s.w.min() and b0 < s.w.max():
                    a.axvspan(b0, b1, color="0.9", zorder=0, lw=0)
                    a.text((b0 + b1) / 2, 0.02, "⊕", transform=a.get_xaxis_transform(), ha="center",
                           fontsize=12, color=MUTED)
        for name, lam in LINES.items():
            lo = lam * (1 + z)
            if s.w.min() + 15 < lo < s.w.max() - 15:
                a.axvline(lo, color="0.75", lw=1.0, ls=(0, (2, 3)), zorder=0)
                a.text(lo, 0.975, name, transform=a.get_xaxis_transform(), rotation=90, ha="right", va="top",
                       fontsize=12, color=MUTED)
        a.set_ylabel(r"$F_\lambda$  ($10^{-15}$ erg s$^{-1}$ cm$^{-2}$ Å$^{-1}$)")
        a.text(0.994, 0.05 if arm == "blue" else 0.30, f"{arm} arm", transform=a.transAxes, fontsize=14, color=col,
               fontweight="bold", ha="right", va="bottom",
               bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=2), zorder=6)
    ax[1].set_xlabel("observed wavelength (Å)")
    date = str(hdr.get("DATE-OBS", ""))[:16].replace("T", " ")
    sn = (f"S/N {hdr['L1QSN2']:.0f} / {hdr['L1QSN1']:.0f}") if hdr.get("L1QSN1") else ""
    top = _header(fig, f"{target_name} — latest FLOYDS spectrum",
                  f"{date} UT · MJD {hdr.get('MJD-OBS', 0):.2f} · {str(hdr.get('SITEID', '')).upper()} · "
                  f"airmass {hdr.get('AIRMASS', 0):.2f} · {hdr.get('APERWID', 0):.0f}″ slit · {sn}",
                  fig.get_figheight())
    fig.tight_layout(rect=(0, 0.015, 1, top))
    _credit(fig)
    files = _save(fig, out_base, formats)
    plt.close(fig)
    return files


@serialized
def latest_hbeta_fit(sp: pd.DataFrame, fit: dict, settings: L.FitSettings, hdr: dict, target_name: str, z: float,
                     out_base: Path, formats=("png",), window=(4720.0, 5130.0), unit=1e-15,
                     arm: str = "blue") -> list[str]:
    """The Hβ-region fit of the latest spectrum (``arm``, rest frame): data, model components, residuals.
    No plot (``[]``) when the arm has no data in ``window`` (blue arm for z > ~0.19, B07)."""
    x = sp[(sp.w > window[0]) & (sp.w < window[1])]
    if not np.isfinite(np.asarray(x.f, float)).any():
        return []
    plt = _setup()
    fig, (a, r) = plt.subplots(2, 1, figsize=(WIDTH, 7.0), sharex=True, gridspec_kw=dict(height_ratios=[3.2, 1]))
    a.plot(x.w, x.f / unit, color=INK, lw=1.4, drawstyle="steps-mid", label=f"data ({arm} arm)", zorder=3)
    a.fill_between(x.w, (x.f - x.e) / unit, (x.f + x.e) / unit, color="0.8", lw=0, step="mid", zorder=2)
    for w0, w1 in settings.continuum_windows:
        a.axvspan(w0, w1, color="0.94", zorder=0, lw=0)
    if fit.get("params"):
        p, s = fit["params"], settings
        g = np.linspace(s.fit_window[0], s.fit_window[1], 2500)
        c = L.model(p, g, s, "cont")
        broad = L.model(p, g, s, "hb_broad")
        narrow = L.model(p, g, s, "oiii") + L.model(p, g, s, "hb_narrow")
        a.fill_between(g, c / unit, (c + broad) / unit, color=BLUE, alpha=0.18, lw=0, label="broad Hβ", zorder=1)
        a.plot(g, (c + broad) / unit, color=BLUE, lw=2.0, zorder=4)
        a.fill_between(g, c / unit, (c + narrow) / unit, color=GREEN, alpha=0.25, lw=0,
                       label="[O III] + narrow Hβ", zorder=1)
        a.plot(g, c / unit, color=GREY, lw=1.6, ls="--", label="continuum", zorder=4)
        a.plot(g, L.model(p, g, s) / unit, color=RED, lw=2.4, label="total model", zorder=5)
        mod = np.interp(x.w, g, L.model(p, g, s))
        inside = (x.w > s.fit_window[0]) & (x.w < s.fit_window[1])
        r.plot(x.w[inside], ((x.f - mod) / x.e)[inside], color=INK, lw=1.1, drawstyle="steps-mid")
        txt = (f"broad Hβ  {fit['hb_broad'] / 1e-13:.2f} ± {fit['hb_broad_err'] / 1e-13:.2f} × 10$^{{-13}}$ cgs\n"
               f"[O III] 5007  {fit['oiii5007'] / 1e-13:.2f} ± {fit['oiii5007_err'] / 1e-13:.2f} × 10$^{{-13}}$\n"
               f"FWHM(Hβ)  {fit['hb_fwhm_kms']:.0f} km s$^{{-1}}$     χ²$_ν$ = {fit['chi2nu']:.1f}")
        a.text(0.99, 0.96, txt, transform=a.transAxes, ha="right", va="top", fontsize=11.5, color=INK,
               bbox=dict(facecolor="white", edgecolor="0.85", boxstyle="round,pad=0.4"), zorder=6)
    for name, lam in (("Hβ", L.HB), ("[O III] 4959", L.O3A), ("[O III] 5007", L.O3B)):
        a.axvline(lam, color="0.75", lw=1.0, ls=(0, (2, 3)), zorder=0)
        a.text(lam, 0.03, name, transform=a.get_xaxis_transform(), rotation=90, ha="right", va="bottom",
               fontsize=12, color=MUTED)
    fmin, fmax = np.nanpercentile(x.f / unit, 1), np.nanmax(x.f / unit)
    a.set_ylim(fmin - 0.12 * (fmax - fmin), fmax + 0.45 * (fmax - fmin))   # room for the legend and the box
    a.set_ylabel(r"$F_\lambda$  ($10^{-15}$ erg s$^{-1}$ cm$^{-2}$ Å$^{-1}$)")
    a.legend(loc="upper left", ncol=1, fontsize=11)
    r.axhline(0, color=GREY, lw=1.2)
    r.set_ylim(-6, 6)
    r.set_ylabel(r"$\chi$")
    r.set_xlabel("rest wavelength (Å)")
    r.set_xlim(*window)
    top = a.secondary_xaxis("top", functions=(lambda w: w * (1 + z), lambda w: w / (1 + z)))
    top.set_xlabel("observed wavelength (Å)", fontsize=13)
    top.tick_params(direction="in", which="both")
    date = str(hdr.get("DATE-OBS", ""))[:10]
    top_ = _header(fig, f"{target_name} — Hβ fit, latest spectrum",
                   f"{date} · MJD {hdr.get('MJD-OBS', 0):.2f} · reference fit; grey = continuum windows",
                   fig.get_figheight())
    fig.tight_layout(rect=(0, 0.015, 1, top_))
    fig.subplots_adjust(hspace=0.05)
    _credit(fig)
    files = _save(fig, out_base, formats)
    plt.close(fig)
    return files


def _year_axis(ax):
    from astropy.time import Time

    lo, hi = ax.get_xlim()
    years = range(int(Time(lo, format="mjd").decimalyear), int(Time(hi, format="mjd").decimalyear) + 2)
    ticks = [(Time(f"{y}-01-01").mjd, str(y)) for y in years]
    ticks = [(m, y) for m, y in ticks if lo <= m <= hi]
    if len(ticks) < 2:          # short span: months
        t0 = Time(lo, format="mjd").datetime
        months = pd.date_range(f"{t0.year}-{t0.month:02d}-01", Time(hi, format="mjd").datetime, freq="MS")
        ticks = [(Time(m.to_pydatetime()).mjd, m.strftime("%b %Y")) for m in months]
        ticks = [(m, y) for m, y in ticks if lo <= m <= hi]
    top = ax.twiny()
    top.set_xlim(lo, hi)
    top.set_xticks([m for m, _ in ticks], [y for _, y in ticks], fontsize=12)
    top.minorticks_off()
    top.tick_params(direction="in", which="both", length=6)


@serialized
def hbeta_lightcurve(night: pd.DataFrame, meta: dict, var: dict, target_name: str, gband: pd.DataFrame,
                     out_base: Path, formats=("png",), g_colour="#008000") -> list[str]:
    """Broad Hβ ([O III]-calibrated), both [O III] lines as measured (before the calibration they set), 5100 Å
    continuum and — when its dates overlap — the g band, on one time axis."""
    plt = _setup()
    has_g = len(gband) > 0
    has_o3 = "oiii5007_int" in night and night["oiii5007_int"].notna().any()
    rows = (["g"] if has_g else []) + ["hb"] + (["oiii"] if has_o3 else []) + ["cont"]
    heights = {"g": 1.0, "hb": 1.25, "oiii": 1.05, "cont": 1.05}
    fig, ax = plt.subplots(len(rows), 1, figsize=(WIDTH, 2.1 * sum(heights[r] for r in rows) + 1.4), sharex=True,
                           gridspec_kw=dict(height_ratios=[heights[r] for r in rows]), squeeze=False)
    ax = dict(zip(rows, ax[:, 0]))

    def label(a, handle, text, colour=INK):
        leg = a.legend([handle], [text], loc="best", handletextpad=0.4, borderaxespad=0.4, fontsize=12)
        for t in leg.get_texts():
            t.set_color(colour)

    if has_g:
        a = ax["g"]
        h = a.errorbar(gband.MJD, gband.flux, gband.err, fmt="o", ms=7, color=g_colour, mec="white", mew=0.8,
                       elinewidth=1.4, capsize=0)
        a.set_ylabel("g (mJy)")
        label(a, h, "LCO g band", g_colour)
    a = ax["hb"]
    h = a.errorbar(night.MJD, night.hb / 1e-13, night.hb_err / 1e-13, fmt="o", ms=9, color=INK, mec="white",
                   mew=0.9, elinewidth=1.6, capsize=0, zorder=3)
    a.set_ylabel(r"H$\beta$ ($10^{-13}$ cgs)")
    fv = (f"F$_{{\\rm var}}$ = {100 * var['fvar']:.1f} ± {100 * var['fvar_err']:.1f} %"
          if np.isfinite(var.get("fvar", np.nan)) else "F$_{\\rm var}$ not detected")
    cal = "[O III]-calibrated" if meta.get("oiii_calibrated") else "not [O III]-calibrated"
    label(a, h, f"broad Hβ · {fv} · F$_{{\\rm max}}$/F$_{{\\rm min}}$ = {var.get('rmax', np.nan):.2f}")
    if has_o3:
        a = ax["oiii"]
        hs, ls = [], []
        for key, mult, col, mk, lab in (("oiii5007_int", 1.0, GREEN, "o", "[O III] 5007"),
                                        ("oiii4959_int", 2.98, "#CC79A7", "D", "[O III] 4959 × 2.98")):
            if key not in night or night[key].notna().sum() == 0:
                continue
            y, e = mult * night[key] / 1e-13, mult * night[f"{key}_err"] / 1e-13
            h = a.errorbar(night.MJD, y, e, fmt=mk, ms=6, color=col, mec="white", mew=0.7, elinewidth=1.2,
                           capsize=0, alpha=0.9)
            ok = np.isfinite(y)
            rms = 100 * np.nanstd(y[ok], ddof=1) / np.nanmean(y[ok]) if ok.sum() > 1 else np.nan
            hs.append(h)
            ls.append(f"{lab} (rms {rms:.1f} %)" if np.isfinite(rms) else lab)
        a.set_ylabel(r"[O III] ($10^{-13}$ cgs)")
        leg = a.legend(hs, ls, loc="best", fontsize=11, handletextpad=0.4, borderaxespad=0.4)
        leg.set_title("as measured, before the [O III] calibration", prop={"size": 10})
    a = ax["cont"]
    h = a.errorbar(night.MJD, night.cont5100 / 1e-15, night.cont5100_err / 1e-15, fmt="s", ms=7, color=BLUE,
                   mec="white", mew=0.8, elinewidth=1.4, capsize=0)
    a.set_ylabel(r"$F_{5100}$ ($10^{-15}$ cgs)")
    label(a, h, "continuum 5100 Å", BLUE)
    ax[rows[-1]].set_xlabel("MJD")
    lo, hi = night.MJD.min(), night.MJD.max()
    pad = max(4.0, 0.03 * (hi - lo))
    ax[rows[-1]].set_xlim(lo - pad, hi + pad)
    for a in ax.values():
        a.grid(axis="x", color="0.93", lw=0.8, zorder=0)
    _year_axis(ax[rows[0]])
    top_ = _header(fig, f"{target_name} — FLOYDS Hβ light curve",
                   f"{meta.get('n_spectra', 0)} spectra · {len(night)} nights · MJD {lo:.0f}–{hi:.0f}"
                   + (" · with LCO g band" if has_g else ""), fig.get_figheight())
    fig.tight_layout(rect=(0, 0.015, 1, top_ - 0.03))
    fig.subplots_adjust(hspace=0.05)
    _credit(fig)
    files = _save(fig, out_base, formats)
    plt.close(fig)
    return files


@serialized
def mean_rms_spectrum(mr: dict, target_name: str, z: float, out_base: Path, formats=("png",), unit=1e-15,
                      date_range: str = "") -> list[str]:
    """[O III]-calibrated mean spectrum and RMS spectrum (rest frame, both arms).  With one night the RMS
    panel says so instead of plotting."""
    plt = _setup()
    arms_ = [a for a in ("blue", "red") if a in mr]
    if not arms_:
        return []
    n_n = max(mr[a]["n_nights"] for a in arms_)
    has_rms = n_n > 1 and any(mr[a]["rms"] is not None for a in arms_)
    fig, (am, ar) = plt.subplots(2, 1, figsize=(WIDTH, 7.4), sharex=True, gridspec_kw=dict(height_ratios=[1.2, 1]))
    blue_max = mr["blue"]["w"].max() if "blue" in mr else -np.inf
    ymax_m = ymax_r = 0.0
    for arm, col in (("blue", BLUE), ("red", RED)):
        if arm not in mr:
            continue
        d = mr[arm]
        sel = d["w"] > blue_max if arm == "red" else np.ones(len(d["w"]), bool)   # red only beyond the blue arm
        w = d["w"][sel]
        m = d["mean"][sel] / unit
        am.fill_between(w, 0, m, color=col, alpha=0.07, lw=0, step="mid")
        am.plot(w, m, color=col, lw=1.4, drawstyle="steps-mid", label=f"{arm} arm")
        ymax_m = max(ymax_m, _ylim(m)[1])
        if has_rms and d["rms"] is not None:
            rr = d["rms"][sel] / unit
            ar.plot(w, rr, color=col, lw=1.4, drawstyle="steps-mid")
            ar.plot(w, d["noise"][sel] / unit, color=GREY, lw=1.2, ls="--",
                    label="noise level" if arm == "blue" else None)
            ymax_r = max(ymax_r, _ylim(rr)[1])
    lo = min(mr[a]["w"].min() for a in arms_)
    hi = max(mr[a]["w"].max() for a in arms_)
    ar.set_xlim(lo, hi)
    for name, lam in LINES.items():
        if lo + 20 < lam < hi - 20:
            for a in (am, ar):
                a.axvline(lam, color="0.8", lw=1.0, ls=(0, (2, 3)), zorder=0)
            am.text(lam, 0.975, name, transform=am.get_xaxis_transform(), rotation=90, ha="right", va="top",
                    fontsize=12, color=MUTED)
    am.set_ylim(0, ymax_m)
    am.set_ylabel(r"mean $F_\lambda$ ($10^{-15}$ cgs)")
    am.legend(loc="center right", fontsize=11)
    if has_rms:
        ar.set_ylim(0, max(ymax_r, 1e-30))
        ar.set_ylabel(r"RMS ($10^{-15}$ cgs)")
        ar.legend(loc="upper right", fontsize=11)
    else:
        ar.set_yticks([])
        ar.text(0.5, 0.5, f"RMS spectrum needs at least two nights ({n_n} so far)", transform=ar.transAxes,
                ha="center", va="center", fontsize=14, color=MUTED)
    ar.set_xlabel("rest wavelength (Å)")
    cal = "[O III]-calibrated" if mr.get("calibrated") else "not [O III]-calibrated (series too short)"
    top_ = _header(fig, f"{target_name} — mean and RMS spectrum",
                   f"{mr.get('n_spectra', 0)} spectr{'a' if mr.get('n_spectra', 0) != 1 else 'um'} · "
                   f"{n_n} night{'s' if n_n != 1 else ''}"
                   + (f" · {date_range}" if date_range else "") + f" · {cal}", fig.get_figheight())
    fig.tight_layout(rect=(0, 0.015, 1, top_))
    fig.subplots_adjust(hspace=0.05)
    _credit(fig)
    files = _save(fig, out_base, formats)
    plt.close(fig)
    return files
