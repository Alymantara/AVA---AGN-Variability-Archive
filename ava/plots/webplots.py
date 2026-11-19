"""
ava.plots.webplots — the AVA website plots (port of ``__old_pipeline__/ava_webplot.py``).

Same figures as the legacy script, drawn from the new products
(``frame_qc``, ``measurements.parquet``, ``agn_lightcurve``):

* :func:`plot_lightcurves` — one panel per filter, flux in mJy (AB), colours
  and wavelengths from ``filter_dict.txt``; spectroscopic epochs as red ticks;
  title "Last Photo | Last Spec"; calendar years (or months, for short windows)
  on the top axis.  ``recent_days`` gives the "last 60 days" version and
  ``last_season`` the last observing season; ``label`` prefixes the title
  (e.g. "Merged by PyTICS").  (legacy ``lco_latest_<obj>`` / ``_last6``; new ``_season``)
* :func:`plot_swift` — Swift/UVOT + XRT light curves (legacy ``_swift``).
* :func:`plot_diagnostics` — per filter: seeing, airmass, zero point
  (transparency) vs MJD, per site (legacy ``_<filter>_sky``).
* :func:`plot_standards_rms` — magnitude vs RMS of every field star per filter,
  the AGN as a diamond (legacy ``_stan``).

Only frames passing QC are plotted (legacy: flag==0, dist<3.5", n_std>=3).
Flux: f[mJy] = 1000 * 10**(-0.4 (m_AB - 8.90)),  σ_f = f σ_m / 1.0857.
"""

from __future__ import annotations

import functools
import threading
from pathlib import Path

import numpy as np
import pandas as pd

AB_JY = 8.90           # m_AB = -2.5 log10(f / 1 Jy) + 8.90

PLOT_LOCK = threading.RLock()


def serialized(fn):
    """Draw one figure at a time, with its style changes kept local to it.

    Matplotlib is not thread-safe (pyplot state, ``rcParams``, the mathtext parser) and the pipeline runs targets
    in a thread pool (``pipeline.n_cores``): concurrent figures fail with random mathtext ``ParseException`` errors, and
    one module's ``rcParams`` (the bigger spectroscopy fonts) would leak into another's figure.  Every website plot
    function holds ``PLOT_LOCK`` for the whole figure inside ``plt.rc_context()``, on the Agg backend (the macOS GUI
    backend refuses to create figures off the main thread).
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        with PLOT_LOCK, plt.rc_context():
            return fn(*args, **kwargs)
    return wrapper


def load_filter_dict(path: Path) -> pd.DataFrame:
    """filter_dict.txt: Filter, wave (Å), color (hex or name), lco, lco_flag, ..."""
    d = pd.read_csv(path)
    d["lco_flag"] = d["lco_flag"].astype(str).str.lower().eq("true")
    return d


def lco_filters(fd: pd.DataFrame, present) -> pd.DataFrame:
    """Rows to plot for LCO photometry: lco_flag True and the filter present, in wavelength order."""
    return fd[fd["lco_flag"] & fd["lco"].isin(set(present))].drop_duplicates("lco").sort_values("wave")


def mag_to_mjy(mag, err):
    f = 1000.0 * 10 ** (-0.4 * (np.asarray(mag, float) - AB_JY))
    return f, f * np.asarray(err, float) / 1.0857


def _mad(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return 1.4826 * np.median(np.abs(x - np.median(x))) if len(x) else np.nan


def _iso(mjd):
    from astropy.time import Time

    return Time(mjd, format="mjd").iso[:10] if mjd is not None and np.isfinite(mjd) else "None"


def _style():
    import matplotlib.pyplot as plt

    major, minor = 6.0, 3.0            # minor ticks are half the length of major ticks
    plt.rcParams.update({
        "font.family": "sans-serif", "axes.spines.top": True, "axes.spines.right": True,
        # ticks inside the plot, on all four axes, with minor ticks visible
        "xtick.direction": "in", "ytick.direction": "in",
        "xtick.top": True, "xtick.bottom": True, "ytick.left": True, "ytick.right": True,
        "xtick.minor.visible": True, "ytick.minor.visible": True,
        "xtick.major.size": major, "ytick.major.size": major,
        "xtick.minor.size": minor, "ytick.minor.size": minor,
        "xtick.major.width": 1.0, "ytick.major.width": 1.0,
        "xtick.minor.width": 0.8, "ytick.minor.width": 0.8,
    })


def _save(fig, out_base: Path, formats) -> list[str]:
    out = []
    for fmt in formats:
        p = Path(f"{out_base}.{fmt}")
        fig.savefig(p, dpi=150)
        out.append(str(p))
    return out


def last_season_start(mjd, gap_days: float = 60.0) -> float:
    """MJD of the first observation after the last gap longer than ``gap_days``."""
    t = np.sort(np.asarray(mjd, float))
    t = t[np.isfinite(t)]
    if len(t) == 0:
        return np.nan
    gaps = np.flatnonzero(np.diff(t) > gap_days)
    return float(t[gaps[-1] + 1]) if len(gaps) else float(t[0])


def _mjd_to_year(mjd):
    return 2000.0 + (np.asarray(mjd, float) - 51544.5) / 365.25


def _year_to_mjd(year):
    return 51544.5 + (np.asarray(year, float) - 2000.0) * 365.25


def _year_axis(ax, x0: float, x1: float):
    """Calendar axis on top of ``ax``: years for long windows, months for short ones."""
    from datetime import datetime

    from astropy.time import Time
    from matplotlib.ticker import FixedLocator, NullLocator

    ax.tick_params(axis="x", which="both", top=False)          # the calendar axis takes the top edge
    top = ax.secondary_xaxis("top", functions=(_mjd_to_year, _year_to_mjd))
    top.tick_params(axis="x", which="both", direction="in", labelsize=10)
    span_yr = (x1 - x0) / 365.25
    if span_yr > 1.5:
        y0, y1 = int(np.floor(_mjd_to_year(x0))), int(np.ceil(_mjd_to_year(x1)))
        ticks = [Time(datetime(y, 1, 1)).mjd for y in range(y0, y1 + 1)]
        top.xaxis.set_major_locator(FixedLocator(_mjd_to_year(ticks)))
        top.set_xticklabels([str(y) for y in range(y0, y1 + 1)])
        top.xaxis.set_minor_locator(FixedLocator(_mjd_to_year(
            [Time(datetime(y, m, 1)).mjd for y in range(y0, y1 + 1) for m in (4, 7, 10)])))
    else:
        step = 1 if span_yr < 0.8 else 2
        d0, d1 = Time(x0, format="mjd").datetime, Time(x1, format="mjd").datetime
        months, y, m = [], d0.year, d0.month
        while (y, m) <= (d1.year, d1.month):
            months.append(datetime(y, m, 1))
            m += 1
            if m > 12:
                y, m = y + 1, 1
        # only months inside the window, so the first label (with its year) is visible
        major = [d for d in months if (d.month - 1) % step == 0 and x0 <= Time(d).mjd <= x1]
        top.xaxis.set_major_locator(FixedLocator(_mjd_to_year([Time(d).mjd for d in major])))
        top.set_xticklabels([d.strftime("%b %Y") if (i == 0 or d.month == 1) else d.strftime("%b")
                             for i, d in enumerate(major)])
        top.xaxis.set_minor_locator(NullLocator())
    return top


@serialized
def plot_lightcurves(lc: pd.DataFrame, fd: pd.DataFrame, out_base: Path, *, spec_mjd=(), last_spec_mjd=None,
                     recent_days: float | None = None, last_season: bool = False, season_gap_days: float = 60.0,
                     label: str | None = None, formats=("png",)) -> list[str]:
    """Legacy ``lco_latest_<obj>`` plot.

    ``recent_days``: the last-N-days version; ``last_season``: from the start of the last
    observing season (after the last gap > ``season_gap_days``); ``label``: prefix for the
    title (e.g. "Merged by PyTICS").  The first panel carries the spectroscopic epochs as
    red ticks and a calendar axis on top.

    ``lc``: agn_lightcurve (mjd_mid, filter, mag, mag_err, qc_pass)."""
    import matplotlib.pyplot as plt

    _style()
    lc = lc[lc["qc_pass"] == 1].sort_values("mjd_mid")
    rows = lco_filters(fd, lc["filter"].unique())
    n = max(len(rows), 1)
    xmin, xmax = lc["mjd_mid"].min(), lc["mjd_mid"].max()
    if last_season:
        x0 = last_season_start(lc["mjd_mid"], season_gap_days)
    else:
        x0 = xmax - recent_days if recent_days else xmin
    fig, axs = plt.subplots(nrows=n, ncols=1, figsize=(10, 2 * max(n, 2)), sharex=True, squeeze=False)
    axs = axs[:, 0]
    for i, (ax, r) in enumerate(zip(axs, rows.itertuples())):
        g = lc[lc["filter"] == r.lco]
        f, fe = mag_to_mjy(g["mag"], g["mag_err"])
        ax.errorbar(g["mjd_mid"], f, yerr=fe, ls="None", capsize=0, marker="o", markersize=4, color=r.color)
        ax.axhline(0, ls="--", color="grey", alpha=0.5)
        ax.set_ylabel(f"{r.Filter}\n({int(r.wave)}" + r"$\AA$)", fontsize=12)
        ax.yaxis.set_tick_params(labelsize=12)
        win = (g["mjd_mid"] >= x0).to_numpy()
        fy = f[win] if win.sum() > 0 else f
        if len(fy):
            lo, hi = np.percentile(fy, 4), np.percentile(fy, 96)
            ax.set_ylim(lo - 0.5 * (hi - lo), hi + 0.5 * (hi - lo))
        if i == 0:
            y0, y1 = ax.get_ylim()
            for t in spec_mjd:
                if x0 - 5 <= t <= xmax + 5:
                    ax.plot([t, t], [y0 + 0.9 * (y1 - y0), y1], color="r", lw=1)
            ax.set_ylim(y0, y1)
            if last_season:
                last = f"Last season: {_iso(x0)} to {_iso(xmax)}"
            elif recent_days:
                last = f"Last {recent_days:.0f} days from: {_iso(xmax)}"
            else:
                last = f"Last Photo: {_iso(xmax)}"
            head = f"{label} | Flux in mJy" if label else "Flux in mJy"
            ax.set_title(f"{head} | {last} | Last Spec: {_iso(last_spec_mjd)}", pad=22)
            _year_axis(ax, x0 - 5.0, xmax + 5.0)
    axs[-1].set_xlim(x0 - 5.0, xmax + 5.0)
    axs[-1].set_xlabel("MJD")
    fig.tight_layout()
    fig.subplots_adjust(wspace=0, hspace=0)
    out = _save(fig, out_base, formats)
    plt.close(fig)
    return out


@serialized
def plot_swift(swift: pd.DataFrame, fd: pd.DataFrame, out_base: Path, *, spec_mjd=(), formats=("png",)) -> list[str]:
    """Legacy ``_swift`` plot.  ``swift``: one target's rows of the Swift DB (Band, MJD, Flux, Error);
    UVOT fluxes in erg/s/cm²/Å are converted to mJy at the band wavelength; X-ray bands
    (HX, SX, FX) are plotted as given (count rate)."""
    import matplotlib.pyplot as plt

    _style()
    rows = fd[fd["Filter"].isin(set(swift["Band"]))].drop_duplicates("Filter").sort_values("wave")
    n = max(len(rows), 1)
    fig, axs = plt.subplots(nrows=n, ncols=1, figsize=(10, 2 * max(n, 2)), sharex=True, squeeze=False)
    axs = axs[:, 0]
    for i, (ax, r) in enumerate(zip(axs, rows.itertuples())):
        g = swift[swift["Band"] == r.Filter]
        if r.Filter in ("HX", "SX", "FX"):
            f, fe = g["Flux"].to_numpy(), g["Error"].to_numpy()
        else:
            k = (float(r.wave) ** 2) / 2.9979e18 / 1e-23 * 1000.0   # f_lambda -> mJy
            f, fe = g["Flux"].to_numpy() * k, g["Error"].to_numpy() * k
        ax.errorbar(g["MJD"], f, yerr=fe, ls="None", capsize=0, marker="o", markersize=4, color=r.color)
        ax.set_ylabel(f"{r.Filter}\n({int(r.wave)}" + r"$\AA$)", fontsize=12)
        if len(f):
            ax.set_ylim(np.nanmedian(f) - 7 * _mad(f), np.nanmedian(f) + 7 * _mad(f))
        if i == 0:
            ax.set_title(f"Flux units in mJy, X-rays in count rate\n| Last observed: {_iso(swift['MJD'].max())}")
            y0, y1 = ax.get_ylim()
            for t in spec_mjd:
                ax.plot([t, t], [y0 + 0.9 * (y1 - y0), y1], color="k", lw=1)
            ax.set_ylim(y0, y1)
    axs[-1].set_xlim(swift["MJD"].min() - 5, swift["MJD"].max() + 5)
    axs[-1].set_xlabel("MJD")
    fig.tight_layout()
    fig.subplots_adjust(wspace=0, hspace=0)
    out = _save(fig, out_base, formats)
    plt.close(fig)
    return out


@serialized
def plot_diagnostics(fq: pd.DataFrame, fd: pd.DataFrame, out_base: Path, formats=("png",)) -> list[str]:
    """Legacy ``_<filter>_sky`` plots: seeing, airmass, zero point vs MJD per site, one figure per filter.
    ``fq``: frame_qc rows (QC-passing frames are used, as in the legacy script)."""
    import matplotlib.pyplot as plt

    _style()
    fq = fq[fq["qc_pass"] == 1]
    out = []
    for r in lco_filters(fd, fq["filter"].unique()).itertuples():
        g = fq[fq["filter"] == r.lco]
        fig = plt.figure(figsize=(10, 10))
        axs = [fig.add_subplot(311), fig.add_subplot(312), fig.add_subplot(313)]
        for site, s in g.groupby("site"):
            for ax, col in zip(axs, ("fwhm_arcsec", "airmass", "zp")):
                ax.plot(s["mjd_mid"], s[col], ls="None", alpha=0.6, marker="o", label=site)
        axs[0].set_ylabel("Seeing / arcsec")
        axs[1].set_ylabel("Airmass")
        axs[2].set_ylabel("Zeropoint (Transparency)")
        axs[2].invert_yaxis()
        for ax in axs:
            ax.yaxis.set_tick_params(labelsize=12)
        axs[0].set_xticklabels([])
        axs[1].set_xticklabels([])
        axs[2].set_xlabel("MJD")
        axs[0].set_title(f"{r.Filter} ({int(r.wave)} Å)")
        axs[0].legend(ncol=max(g["site"].nunique(), 1), loc=9)
        plt.tight_layout(h_pad=0)
        out += _save(fig, Path(f"{out_base}_{r.lco}_sky"), formats)
        plt.close(fig)
    return out


@serialized
def plot_standards_rms(meas: pd.DataFrame, fq: pd.DataFrame, fd: pd.DataFrame, out_base: Path, *,
                       last_epochs: int = 500, formats=("png",)) -> list[str]:
    """Legacy ``_stan`` plot: calibrated magnitude vs RMS for every star with > 10 epochs
    (last ``last_epochs`` QC-passing epochs), the AGN as a diamond in its filter colour."""
    import matplotlib.pyplot as plt

    _style()
    fq = fq[fq["qc_pass"] == 1][["frame", "filter", "mjd_mid", "zp"]]
    m = meas.merge(fq, on="frame")
    m["mag"] = m["mag_inst"] + m["zp"]
    rows = lco_filters(fd, m["filter"].unique())
    n = len(rows)
    fig, axs = plt.subplots(nrows=int(np.ceil(n / 2)), ncols=2, figsize=(10, 2 * max(n, 2)), squeeze=False)
    for ax, r in zip(axs.reshape(-1), rows.itertuples()):
        g = m[m["filter"] == r.lco].sort_values("mjd_mid")
        stats = g.groupby("star_id").agg(
            n=("mag", "size"), med=("mag", lambda x: np.nanmedian(x.to_numpy()[-last_epochs:])),
            rms=("mag", lambda x: _mad(x.to_numpy()[-last_epochs:])), agn=("is_agn", "max"))
        stats = stats[stats["n"] > 10]
        if stats.empty:                 # e.g. a filter with only a handful of epochs
            ax.set_visible(False)
            continue
        s = stats[~stats["agn"]]
        ax.plot(s["med"], s["rms"], "o", ls="None", ms=2, alpha=0.5, color="k")
        a = stats[stats["agn"]]
        if len(a):
            ax.plot(a["med"], a["rms"], marker="d", ms=9, ls="None", color=r.color, label=r.lco)
            ax.legend(fontsize=18)
        ax.set_title(f"Magnitude, Filter: {r.lco}")
        ax.set_ylim(0.001, 1.0)
        ax.set_xlim(7.5, 22.0)
        ax.set_yscale("log")
        ax.set_ylabel("RMS")
    for ax in axs.reshape(-1)[n:]:
        ax.set_visible(False)
    fig.tight_layout()
    out = _save(fig, out_base, formats)
    plt.close(fig)
    return out
