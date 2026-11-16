"""AGN STORM 2 (Mrk 817) intercalibration figures + pair test of the error bars.

    pytics_19_storm2_lightcurves.png  whole campaign, all bands, coloured by camera (PyTICS + intercal)
    pytics_20_storm2_zoom.png         zoom: per-frame ZP calibration (before) vs PyTICS + intercal (after)
    pytics_21_pair_test.png           are the error bars consistent with the scatter within pairs?
    pytics_pair_test_stats.csv

Campaign window is a parameter (default MJD 59150-59650, Nov 2020 - Feb 2022)."""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/juan/astro/AVA")
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ava.photometry import intercal as IC
from ava.plots import webplots as wp

ROOT = Path("/Users/juan/astro/AVA")
PHOT = ROOT / "data/test_archive/photometry/Mrk_817"; OUT = ROOT / "docs/figures/pytics"
T0, T1 = (float(sys.argv[1]), float(sys.argv[2])) if len(sys.argv) > 2 else (59150.0, 59650.0)
F = ["up", "B", "gp", "V", "rp", "ip", "zs"]; LBL = dict(up="u", B="B", gp="g", V="V", rp="r", ip="i", zs="z")
fd = wp.load_filter_dict(ROOT / "data/reference/filter_dict.txt")
BCOL = {r.lco: r.color for r in fd[fd.lco_flag].drop_duplicates("lco").itertuples()}
wp._style(); plt.rcParams.update({"font.size": 9, "legend.frameon": False, "legend.fontsize": 7})

# camera identity: Okabe-Ito order + marker shape as secondary encoding; MuSCAT (one camera per band) in black
OI = ["#E69F00", "#56B4E9", "#009E73", "#0072B2", "#D55E00", "#CC79A7", "#999999", "#F0E442"]
MK = ["o", "s", "D", "^", "v", "P", "X", "h"]

lc = pd.read_parquet(PHOT / "agn_lightcurve_pytics.parquet")
lc["cam"] = np.where(lc.scope.str.contains("-ep"), "2m0 MuSCAT3", lc.scope)
win = lc[(lc.MJD > T0) & (lc.MJD < T1) & lc.good]
cams = [c for c in win.cam.value_counts().index if c != "2m0 MuSCAT3"]
STY = {c: dict(color=OI[i % len(OI)], marker=MK[i % len(MK)]) for i, c in enumerate(sorted(cams))}
STY["2m0 MuSCAT3"] = dict(color="k", marker="o")

old = pd.read_parquet(PHOT / "agn_lightcurve.parquet")
old = old[(old.qc_pass == 1)].rename(columns={"mjd_mid": "MJD", "filter": "Filter"})
old["cam"] = np.where(old.camera.str.startswith("ep"), "2m0 MuSCAT3", old.tel + "-" + old.camera)
old["F"], old["Fe"] = IC.to_mjy(old["mag"], old["mag_err"])


def rob(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return 1.4826 * np.median(np.abs(x - np.median(x))) if len(x) else np.nan


def cross_cam_sigma(d, flux, ferr=None, dt=0.4):
    """robust σ (%) of the flux ratio between different cameras on the same night (< dt apart)."""
    d = d.assign(night=np.floor(d.MJD - 0.5).astype(int))
    g = d.groupby(["night", "cam"]).agg(F=(flux, "median"), MJD=("MJD", "median")).reset_index()
    r = []
    for _, h in g.groupby("night"):
        if h.cam.nunique() < 2:
            continue
        h = h.sort_values("MJD")
        for i in range(len(h) - 1):
            if h.MJD.iloc[i + 1] - h.MJD.iloc[i] < dt:
                r.append(h.F.iloc[i + 1] / h.F.iloc[i] - 1)
    return 100 * rob(r), len(r)


# ------------------------------------------------------------------ 19 whole campaign
fig, ax = plt.subplots(len(F), 1, figsize=(13, 15), sharex=True)
for a, f in zip(ax, F):
    x = win[win.Filter == f]
    for c, h in x.groupby("cam"):
        if c == "2m0 MuSCAT3":
            a.plot(h.MJD, h.F, "o", ms=2.2, mfc="none", mec="0.7", mew=0.5, zorder=1)
        a.errorbar(h.MJD, h.F_ic, h.Ferr_ic, ls="none", ms=2.2, elinewidth=0.4, zorder=2, **STY[c])
    a.text(0.005, 0.92, LBL[f], transform=a.transAxes, fontsize=12, fontweight="bold", color=BCOL[f], va="top")
    a.set_ylabel("flux (mJy)")
h = [plt.Line2D([], [], ls="none", ms=5, **STY[c]) for c in sorted(cams) + ["2m0 MuSCAT3"]]
h.append(plt.Line2D([], [], ls="none", marker="o", mfc="none", mec="0.7", ms=5))
ax[0].legend(h, sorted(cams) + ["MuSCAT3, corrected", "MuSCAT3, before additive correction"], ncol=5,
             loc="lower center", bbox_to_anchor=(0.5, 1.02), fontsize=8)
ax[-1].set_xlabel("MJD"); ax[-1].set_xlim(T0, T1)
fig.tight_layout(); fig.subplots_adjust(hspace=0.06)
fig.savefig(OUT / "pytics_19_storm2_lightcurves.png", dpi=150, bbox_inches="tight"); plt.close(fig)

# ------------------------------------------------------------------ 20 zoom: before vs after
# window: 40 days with the most nights observed by >= 2 cameras in g
g = win[win.Filter == "gp"].assign(night=lambda d: np.floor(d.MJD - 0.5))
multi = g.groupby("night").cam.nunique()
multi = multi[multi >= 2].index.to_numpy()
starts = np.arange(T0, T1 - 40, 2.0)
z0 = starts[np.argmax([((multi >= s) & (multi < s + 40)).sum() for s in starts])]; z1 = z0 + 40
fig, ax = plt.subplots(len(F), 2, figsize=(14, 15), sharex=True)
for i, f in enumerate(F):
    b = old[(old.Filter == f) & (old.MJD > z0) & (old.MJD < z1)]
    a_ = lc[(lc.Filter == f) & lc.good & (lc.MJD > z0) & (lc.MJD < z1)]
    sb, nb = cross_cam_sigma(old[(old.Filter == f) & (old.MJD > T0) & (old.MJD < T1)], "F")
    sa, na = cross_cam_sigma(win[win.Filter == f], "F_ic")
    for col, d, fl, fe, s, n in [(0, b, "F", "Fe", sb, nb), (1, a_, "F_ic", "Ferr_ic", sa, na)]:
        a = ax[i, col]
        for c, h in d.groupby("cam"):
            a.errorbar(h.MJD, h[fl], h[fe], ls="none", ms=3, elinewidth=0.5, **STY.get(c, dict(color="0.5", marker=".")))
        a.text(0.01, 0.92, LBL[f], transform=a.transAxes, fontsize=12, fontweight="bold", color=BCOL[f], va="top")
        a.text(0.99, 0.06, f"same-night camera-to-camera σ = {s:.2f} %  ({n} pairs, whole campaign)",
               transform=a.transAxes, ha="right", fontsize=7)
    lo = np.nanpercentile(np.r_[b.F, a_.F_ic], 1); hi = np.nanpercentile(np.r_[b.F, a_.F_ic], 99)
    for a in ax[i]:
        a.set_ylim(lo - 0.08 * (hi - lo), hi + 0.08 * (hi - lo))
    ax[i, 0].set_ylabel("flux (mJy)")
ax[0, 0].set_title("before: per-frame zero point (agn_lightcurve.parquet, qc_pass)")
ax[0, 1].set_title("after: PyTICS ensemble + MuSCAT additive correction (good epochs)")
for a in ax[-1]:
    a.set_xlabel("MJD"); a.set_xlim(z0, z1)
ax[0, 0].legend(h_ := [plt.Line2D([], [], ls="none", ms=5, **STY[c]) for c in sorted(cams) + ["2m0 MuSCAT3"]],
                sorted(cams) + ["2m0 MuSCAT3"], ncol=4, loc="lower left", bbox_to_anchor=(0.0, 1.12), fontsize=8)
fig.tight_layout(); fig.subplots_adjust(hspace=0.06, wspace=0.12)
fig.savefig(OUT / "pytics_20_storm2_zoom.png", dpi=150, bbox_inches="tight"); plt.close(fig)
print(f"zoom window MJD {z0:.0f}-{z1:.0f}")

# ------------------------------------------------------------------ 21 pair test
def pairs(d, max_dt):
    """consecutive good epochs of the same filter within max_dt (d); same and different camera."""
    out = []
    for f, h in d[d.good].groupby("Filter"):
        h = h.sort_values("MJD")
        t, m, cam = h.MJD.to_numpy(), h.mag_ic.to_numpy(), h.cam.to_numpy()
        er, et = h.mag_err_rand.to_numpy(), h.mag_ic_err.to_numpy()
        for j in range(1, 4):                  # up to 3 neighbours: catches interleaved cameras
            k = np.arange(len(h) - j); dt = t[k + j] - t[k]; ok = dt < max_dt
            k = k[ok]
            out.append(pd.DataFrame({"Filter": f, "dt": dt[ok], "dm": m[k + j] - m[k],
                                     "sr": np.hypot(er[k], er[k + j]), "st": np.hypot(et[k], et[k + j]),
                                     "same": cam[k] == cam[k + j], "MJD": t[k]}))
    p = pd.concat(out)
    return p[p.same | (p.dt < max_dt)]


P = pairs(lc, 1.0)
P = P.drop_duplicates(["Filter", "MJD", "dt"])
P["zr"], P["zt"] = P.dm / P.sr, P.dm / P.st
same = P[P.same & (P.dt < 1 / 24)]; diff = P[~P.same & (P.dt < 0.25)]
rows = []
for f in F:
    for lab, d, sub in [("all", same, None), ("STORM2", same, (T0, T1))]:
        x = d[d.Filter == f] if sub is None else d[(d.Filter == f) & (d.MJD > T0) & (d.MJD < T1)]
        y = diff[diff.Filter == f] if sub is None else diff[(diff.Filter == f) & (diff.MJD > T0) & (diff.MJD < T1)]
        # extra error s added in quadrature to each epoch that makes the robust σ_z = 1
        s = np.sqrt(max(rob(x.dm) ** 2 - np.median(x.sr) ** 2, 0) / 2)
        rows.append(dict(filter=LBL[f], sample=lab, same_pairs=len(x), same_sigma_z_rand=rob(x.zr),
                         same_sigma_z_tot=rob(x.zt), same_frac_gt3=float((x.zr.abs() > 3).mean()),
                         scale_rand=rob(x.zr), missing_mmag=1e3 * s if rob(x.zr) > 1 else 0.0,
                         cross_pairs=len(y), cross_sigma_z_rand=rob(y.zr), cross_sigma_z_tot=rob(y.zt),
                         med_err_rand_mmag=1e3 * np.median(x.sr) / np.sqrt(2)))
R = pd.DataFrame(rows)
R.round(3).to_csv(OUT / "pytics_pair_test_stats.csv", index=False)
pd.set_option("display.width", 250); print(R.round(2).to_string())

fig, ax = plt.subplots(2, 2, figsize=(12, 8.5)); ax = ax.ravel()
bins = np.linspace(-6, 6, 97); xg = np.linspace(-6, 6, 300)
for f in F:
    x = same[same.Filter == f]
    ax[0].hist(x.zr, bins=bins, density=True, histtype="step", color=BCOL[f], label=f"{LBL[f]} ({len(x)})")
ax[0].plot(xg, np.exp(-xg ** 2 / 2) / np.sqrt(2 * np.pi), "k--", lw=1, label="N(0, 1)")
ax[0].set_yscale("log"); ax[0].set_ylim(1e-4, 1); ax[0].legend(ncol=2)
ax[0].set_xlabel(r"$\Delta m\,/\,\sqrt{\sigma_1^2+\sigma_2^2}$  (random errors)"); ax[0].set_ylabel("density")
ax[0].set_title("AGN pairs < 1 h, same camera")
A = R[R["sample"] == "all"].reset_index(drop=True); xx = np.arange(len(F)); c = [BCOL[f] for f in F]
for dx, col, lab, kw in [(-0.3, "same_sigma_z_rand", "same camera < 1 h, random error", dict(color=c)),
                         (-0.1, "same_sigma_z_tot", "same camera < 1 h, total error", dict(color=c, alpha=0.4)),
                         (0.1, "cross_sigma_z_rand", "different camera < 6 h, random error", dict(color="0.35")),
                         (0.3, "cross_sigma_z_tot", "different camera < 6 h, total error", dict(color="0.75"))]:
    ax[1].bar(xx + dx, A[col], 0.2, label=lab, **kw)
    for i, v in enumerate(A[col]):
        ax[1].text(i + dx, v + 0.02, f"{v:.2f}", ha="center", fontsize=6, rotation=90)
ax[1].axhline(1, color="k", ls="--", lw=0.8); ax[1].set_xticks(xx); ax[1].set_xticklabels([LBL[f] for f in F])
ax[1].minorticks_off(); ax[1].tick_params(axis="x", which="both", top=False, bottom=False)
ax[1].set_ylabel("robust σ of normalised pair difference"); ax[1].legend(fontsize=7, loc="upper left", ncol=2)
ax[1].set_ylim(0, 3.0); ax[1].set_title("1 = errors right;  < 1 = too large;  > 1 = too small")
# σ_z vs Δt (same camera): flat => noise, rising => AGN variability
tb = np.logspace(np.log10(1 / 1440), 0, 13)
for f in F:
    x = P[P.same & (P.Filter == f)]
    k = pd.cut(x.dt, tb); t = x.groupby(k).agg(dt=("dt", "median"), s=("zr", rob), n=("zr", "size"))
    t = t[t.n >= 20]
    ax[2].plot(24 * t.dt, t.s, "o-", ms=3, color=BCOL[f], label=LBL[f])
ax[2].axhline(1, color="k", ls="--", lw=0.8); ax[2].set_xscale("log"); ax[2].axvline(1, color="0.6", lw=0.6)
ax[2].set_xlabel("time between the two epochs (h)"); ax[2].set_ylabel("robust σ_z (random errors)")
ax[2].set_title("same camera: flat = measurement noise, rising = AGN varies"); ax[2].legend(ncol=4)
# σ_z vs predicted error (same camera < 1 h)
for f in F:
    x = same[same.Filter == f]
    k = pd.qcut(x.sr / np.sqrt(2), 8, duplicates="drop")
    t = x.groupby(k).agg(e=("sr", "median"), s=("zr", rob))
    ax[3].plot(1e3 * t.e / np.sqrt(2), t.s, "o-", ms=3, color=BCOL[f])
ax[3].axhline(1, color="k", ls="--", lw=0.8); ax[3].set_xscale("log")
ax[3].set_xlabel("quoted random error per epoch (mmag, octiles)"); ax[3].set_ylabel("robust σ_z (random errors)")
ax[3].set_title("same camera < 1 h: does the error scale with the scatter?")
fig.tight_layout(); fig.savefig(OUT / "pytics_21_pair_test.png", dpi=150, bbox_inches="tight"); plt.close(fig)
