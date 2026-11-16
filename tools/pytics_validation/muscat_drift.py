"""MuSCAT vs Sinistro AGN flux over time (is the additive MuSCAT correction constant?).
Each good Sinistro epoch is compared with the MuSCAT nightly flux interpolated to its time (< 1.5 d).
Writes docs/figures/pytics/pytics_22_muscat_vs_sinistro.png"""
import sys, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, "/Users/juan/astro/AVA")
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from ava.plots import webplots as wp
ROOT = Path("/Users/juan/astro/AVA"); PHOT = ROOT / "data/test_archive/photometry/Mrk_817"; OUT = ROOT / "docs/figures/pytics"
wp._style(); plt.rcParams.update({"font.size": 9, "legend.frameon": False, "legend.fontsize": 7})
F = ["gp", "rp", "ip", "zs"]; LBL = dict(gp="g", rp="r", ip="i", zs="z")
OI = {"1m001-fa11": ("#E69F00", "o"), "1m003-fa20": ("#56B4E9", "s"), "1m006-fa07": ("#009E73", "D"),
      "1m008-fa05": ("#0072B2", "^"), "1m013-fa20": ("#D55E00", "v"), "1m014-fa20": ("#CC79A7", "P")}
lc = pd.read_parquet(PHOT / "agn_lightcurve_pytics.parquet"); lc = lc[lc.good]


def rob(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return 1.4826 * np.median(np.abs(x - np.median(x))) if len(x) else np.nan


def compare(f):
    x = lc[lc.Filter == f]; mus = x[x.scope.str.contains("-ep")].copy(); sin = x[~x.scope.str.contains("-ep")].copy()
    mus["night"] = np.floor(mus.MJD - 0.5)
    m = mus.groupby("night").agg(MJD=("MJD", "median"), F=("F_ic", "median"), see=("seeing", "median"),
                                 am=("airmass", "median"))
    t = m.MJD.values; i = np.clip(np.searchsorted(t, sin.MJD.values), 1, len(t) - 1)
    gap = np.maximum(sin.MJD.values - t[i - 1], t[i] - sin.MJD.values); w = (sin.MJD.values - t[i - 1]) / (t[i] - t[i - 1])
    sin["Fm"] = m.F.values[i - 1] + (m.F.values[i] - m.F.values[i - 1]) * w
    near = np.where(w < 0.5, i - 1, i)
    sin["see_m"] = m.see.values[near]; sin["am_m"] = m.am.values[near]
    s = sin[(gap < 1.5) & (sin.MJD > t[0]) & (sin.MJD < t[-1])].copy()
    s["d"] = s.Fm - s.F_ic; s["dpc"] = 100 * s.d / s.F_ic        # MuSCAT − Sinistro
    return s


fig, ax = plt.subplots(len(F), 3, figsize=(15, 11), gridspec_kw=dict(width_ratios=[3, 1, 1]))
rows = []
for r, f in enumerate(F):
    s = compare(f)
    for sc, h in s.groupby("scope"):
        c, mk = OI.get(sc, ("0.5", "."))
        ax[r, 0].plot(h.MJD, h.dpc, mk, color=c, ms=3, label=sc)
        ax[r, 1].plot(h.see_m, h.dpc, mk, color=c, ms=3); ax[r, 2].plot(h.seeing, h.dpc, mk, color=c, ms=3)
    # 30-day running median over all cameras
    b = (s.MJD // 30) * 30; t = s.groupby(b).agg(MJD=("MJD", "median"), d=("dpc", "median"), n=("dpc", "size"))
    t = t[t.n >= 5]; ax[r, 0].plot(t.MJD, t.d, "k-", lw=1.2, label="30-d median")
    for a in ax[r]:
        a.axhline(0, color="0.6", lw=0.6); a.set_ylim(-5, 5)
    ax[r, 0].set_ylabel(f"{LBL[f]}: MuSCAT − Sinistro (%)")
    for season, h in s.groupby(np.where(s.MJD < 59500, "2021", "2022")):
        rows.append(dict(filter=LBL[f], season=season, n=len(h), median_pct=h.dpc.median(), rob_pct=rob(h.dpc),
                         trend_pct_per_100d=100 * np.polyfit(h.MJD, h.dpc, 1)[0],
                         corr_seeing_muscat=np.corrcoef(h.see_m, h.dpc)[0, 1],
                         corr_seeing_sinistro=np.corrcoef(h.seeing, h.dpc)[0, 1]))
ax[0, 0].legend(ncol=4); ax[-1, 0].set_xlabel("MJD")
ax[-1, 1].set_xlabel("MuSCAT seeing (arcsec)"); ax[-1, 2].set_xlabel("Sinistro seeing (arcsec)")
ax[0, 0].set_title("AGN flux, MuSCAT (corrected, interpolated) − Sinistro epoch")
fig.tight_layout(); fig.savefig(OUT / "pytics_22_muscat_vs_sinistro.png", dpi=150, bbox_inches="tight")
R = pd.DataFrame(rows); pd.set_option("display.width", 200); print(R.round(2).to_string())
R.round(3).to_csv(OUT / "pytics_muscat_vs_sinistro.csv", index=False)
