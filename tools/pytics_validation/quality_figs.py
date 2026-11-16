"""PyTICS quality figures (docs/figures/pytics/pytics_16..18) from the stored Mrk 817 solution."""
import sys, json, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))   # repository root
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ava.config import cfg  # noqa: E402  (AVA_CONFIG selects the archive; AVA_TARGET the target)
from ava.pipeline.tasks.calibrate import frame_db_path  # noqa: E402
TARGET = __import__("os").environ.get("AVA_TARGET", "Mrk_817")
from ava.photometry import ensemble as E, store
from ava.plots import webplots as wp

ROOT = Path(__file__).resolve().parents[2]
PHOT = cfg.phot_dir(TARGET); DB = frame_db_path()
OUT = ROOT / "docs/figures/pytics"
F = ["up", "B", "gp", "V", "rp", "ip", "zs"]; LBL = dict(up="u", B="B", gp="g", V="V", rp="r", ip="i", zs="z")
fd = wp.load_filter_dict(ROOT / "data/reference/filter_dict.txt")
COL = {r.lco: r.color for r in fd[fd.lco_flag].drop_duplicates("lco").itertuples()}
wp._style(); plt.rcParams.update({"font.size": 10, "legend.frameon": False, "legend.fontsize": 8})
fq = store.read_frame_qc(DB, TARGET).set_index("frame")
lc = pd.read_parquet(PHOT / "agn_lightcurve_pytics.parquet")
stats = {}


def rob(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return 1.4826 * np.median(np.abs(x - np.median(x))) if len(x) else np.nan


def residuals(f):
    sol = E.Solution.load(E.solution_dir(PHOT, f))
    st, sc, ep = sol.stars.set_index("star_id"), sol.scopes.set_index("scope"), sol.epochs.set_index("frame")
    d = E.clean_comparisons(E.load_target(PHOT, DB, TARGET, f))
    d = d[d.star_id.isin(st.index) & d.frame.isin(ep.index)].copy()
    dc = (d.star_id.map(st["colour"]) - sol.meta.get("c0", 0)).fillna(0) if sol.meta.get("colour_terms") else 0.0
    ck = d.scope.map(sc["CK"]).fillna(0) if "CK" in sc else 0.0
    d["model"] = d.star_id.map(st.m_star) + d.frame.map(ep.DMAGT) + d.scope.map(sc.DMAGS) + ck * dc
    d["res"] = d.mag_inst - d.model
    d["sig"] = np.sqrt(d.magerr ** 2 + d.star_id.map(st.rms_star) ** 2 + d.frame.map(ep.rms_t) ** 2
                       + d.scope.map(sc.rms_sc) ** 2)
    d["z"] = d.res / d.sig
    d["good"] = d.frame.map(ep.rms_t) < 0.05
    ref = pd.read_csv(PHOT / "reference_stars.csv").set_index("star_id")
    d["colour"] = d.star_id.map(ref.lco_g - ref.lco_i)
    d["airmass"] = d.frame.map(fq.airmass); d["fwhm"] = d.frame.map(fq.fwhm_arcsec)
    return sol, d


# ---------------------------------------------------------------- 16 error model
fig, ax = plt.subplots(2, 2, figsize=(12, 8))
bins = np.linspace(-6, 6, 121); xg = np.linspace(-6, 6, 300)
rows = []
for f in F:
    sol, d = residuals(f)
    g = d[d.good]
    ax[0, 0].hist(g.z, bins=bins, density=True, histtype="step", color=COL[f], label=f"{LBL[f]}: σ_z = {rob(g.z):.2f}")
    # normalised residual vs magnitude
    mb = pd.qcut(g.groupby("star_id").model.median().reindex(g.star_id).values, 8, duplicates="drop")
    t = g.groupby(mb).agg(m=("mag_inst", "median"), s=("z", rob))
    ax[0, 1].plot(t.m, t.s, "o-", ms=4, color=COL[f])
    # AGN pairs < 1 h, same scope, both good: Δm / sqrt(σ1²+σ2²)
    a = lc[(lc.Filter == f) & lc.good].sort_values("MJD")
    zz, zr = [], []
    for _, h in a.groupby("scope"):
        t_, m_, e_, er_ = h.MJD.to_numpy(), h.mag.to_numpy(), h.mag_err.to_numpy(), h.mag_err_rand.to_numpy()
        k = np.diff(t_) < 1 / 24
        zz.append((np.diff(m_) / np.hypot(e_[1:], e_[:-1]))[k])
        zr.append((np.diff(m_) / np.hypot(er_[1:], er_[:-1]))[k])
    zz, zr = np.concatenate(zz), np.concatenate(zr)
    rows.append(dict(filter=f, star_sigma_z=rob(g.z), star_frac_gt5=float((g.z.abs() > 5).mean()),
                     agn_pair_sigma_z=rob(zz), agn_pair_sigma_z_random=rob(zr), agn_pairs=len(zz), agn_med_err_mmag=1e3 * a.mag_err.median()))
r = pd.DataFrame(rows)
ax[0, 0].plot(xg, np.exp(-xg ** 2 / 2) / np.sqrt(2 * np.pi), "k--", lw=1, label="N(0,1)")
ax[0, 0].set_yscale("log"); ax[0, 0].set_ylim(1e-4, 1); ax[0, 0].set_xlabel("comparison-star residual / σ_tot")
ax[0, 0].set_ylabel("density"); ax[0, 0].legend(ncol=2); ax[0, 0].set_title("normalised residuals (good epochs)")
ax[0, 1].axhline(1, color="k", ls="--", lw=0.8); ax[0, 1].set_xlabel("star instrumental mag (octile medians)")
ax[0, 1].set_ylabel("robust σ of residual / σ_tot"); ax[0, 1].set_title("error model vs brightness")
x = np.arange(len(F))
ax[1, 0].bar(x - 0.27, r.star_sigma_z, 0.27, color="0.6", label="comparison stars (σ_tot)")
ax[1, 0].bar(x, r.agn_pair_sigma_z, 0.27, color=[COL[f] for f in F], alpha=0.45, label="AGN pairs < 1 h, mag_err")
ax[1, 0].bar(x + 0.27, r.agn_pair_sigma_z_random, 0.27, color=[COL[f] for f in F], label="AGN pairs < 1 h, mag_err_rand")
ax[1, 0].axhline(1, color="k", ls="--", lw=0.8)
for i, row in r.iterrows():
    for dx, v in [(-0.27, row.star_sigma_z), (0, row.agn_pair_sigma_z), (0.27, row.agn_pair_sigma_z_random)]:
        ax[1, 0].text(i + dx, v + 0.02, f"{v:.2f}", ha="center", fontsize=6)
ax[1, 0].set_xticks(x); ax[1, 0].set_xticklabels([LBL[f] for f in F]); ax[1, 0].minorticks_off()
ax[1, 0].tick_params(axis="x", which="both", top=False, bottom=False)
ax[1, 0].set_ylabel("robust σ of normalised differences"); ax[1, 0].legend(fontsize=7, loc="lower right")
ax[1, 0].set_title("are the quoted errors right? (1 = yes; < 1 = conservative)")
ax[1, 1].bar(x, 100 * r.star_frac_gt5, color=[COL[f] for f in F])
ax[1, 1].set_xticks(x); ax[1, 1].set_xticklabels([LBL[f] for f in F]); ax[1, 1].minorticks_off()
ax[1, 1].tick_params(axis="x", which="both", top=False, bottom=False)
ax[1, 1].set_ylabel("% comparison measurements with |z| > 5"); ax[1, 1].set_title("outliers (Gaussian: 6e-5 %)")
fig.tight_layout(); fig.savefig(OUT / "pytics_16_error_model.png", dpi=150, bbox_inches="tight"); plt.close(fig)
stats["error_model"] = r.round(3).to_dict("records")
print(r.round(3).to_string())

# ---------------------------------------------------------------- 17 residual systematics
fig, ax = plt.subplots(2, 3, figsize=(15, 8)); ax = ax.ravel()
trend = []
for f in F:
    sol, d = residuals(f)
    g = d[d.good]
    for i, (col, lab) in enumerate([("airmass", "airmass"), ("fwhm", "FWHM (arcsec)"), ("colour", "star GSPC g − i"),
                                    ("x", "detector x (px, scaled)"), ("y", "detector y (px, scaled)"), ("MJD", "MJD")]):
        v = g[col].astype(float)
        if col in ("x", "y"):   # scale per camera so MuSCAT / Sinistro share an axis
            v = g.groupby("scope")[col].transform(lambda s: (s - s.min()) / (s.max() - s.min() + 1e-9))
        ok = np.isfinite(v)
        b = pd.qcut(v[ok], 12, duplicates="drop")
        t = pd.DataFrame({"v": v[ok], "r": g.res[ok]}).groupby(b).agg(v=("v", "median"), r=("r", "median"))
        ax[i].plot(t.v, 1e3 * t.r, "o-", ms=3, color=COL[f], label=LBL[f])
        ax[i].set_xlabel(lab)
        trend.append(dict(filter=f, quantity=col, range_mmag=1e3 * float(t.r.max() - t.r.min())))
for a in ax:
    a.axhline(0, color="grey", lw=0.6); a.set_ylabel("median residual (mmag)"); a.set_ylim(-6, 6)
ax[0].legend(ncol=4); fig.suptitle("comparison-star residuals vs observing conditions (good epochs, 12 quantile bins)", y=1.0)
fig.tight_layout(); fig.savefig(OUT / "pytics_17_residual_systematics.png", dpi=150, bbox_inches="tight"); plt.close(fig)
tr = pd.DataFrame(trend).pivot(index="filter", columns="quantity", values="range_mmag").loc[F]
stats["residual_trend_range_mmag"] = tr.round(2).to_dict()
print(tr.round(2).to_string())

# ---------------------------------------------------------------- 18 epoch quality timeline
fig, ax = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
summ = []
for f in F:
    sol = E.Solution.load(E.solution_dir(PHOT, f)); e = sol.epochs.sort_values("MJD")
    ax[0].plot(e.MJD, np.clip(1e3 * e.rms_t, 0.05, 500), ".", ms=2, color=COL[f], label=LBL[f])
    ax[1].plot(e.MJD, e.n_stars, ".", ms=2, color=COL[f])
    m = np.floor((e.MJD - e.MJD.min()) / 30.4)
    gf = (e.rms_t < 0.05).groupby(m).mean()
    ax[2].plot(e.MJD.groupby(m).median(), 100 * gf, "-", lw=1, color=COL[f])
    a = lc[lc.Filter == f]
    summ.append(dict(filter=f, epochs=len(e), good_pct=100 * float((e.rms_t < 0.05).mean()),
                     median_rms_t_mmag=1e3 * float(e.rms_t.median()), p90_rms_t_mmag=1e3 * float(e.rms_t.quantile(0.9)),
                     median_n_stars=float(e.n_stars.median()), agn_median_err_mmag=1e3 * float(a.mag_err[a.good].median()),
                     loops=sol.meta["loops"], stop=sol.meta.get("stop")))
ax[0].axhline(50, color="r", lw=0.8, ls="--"); ax[0].set_yscale("log"); ax[0].set_ylabel("rms_t (mmag)")
ax[0].legend(ncol=7, markerscale=4); ax[0].set_title("per-epoch extra scatter (red: good-epoch limit 50 mmag)")
ax[1].set_ylabel("comparison stars per epoch"); ax[1].axhline(5, color="r", lw=0.8, ls="--")
ax[2].set_ylabel("good epochs per month (%)"); ax[2].set_xlabel("MJD"); ax[2].set_ylim(50, 101)
fig.tight_layout(); fig.subplots_adjust(hspace=0.08)
fig.savefig(OUT / "pytics_18_epoch_quality.png", dpi=150, bbox_inches="tight"); plt.close(fig)
s = pd.DataFrame(summ); stats["epoch_quality"] = s.round(2).to_dict("records"); print(s.round(2).to_string())
json.dump(stats, open(OUT / "pytics_quality_stats.json", "w"), indent=1, default=float)
