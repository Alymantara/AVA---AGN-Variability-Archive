"""Before / after the per-camera colour terms (CK_k) in the ensemble. Usage:
    compare_colour_terms.py <before_dir>   (copy of <phot>/pytics + agn_lightcurve_pytics.parquet before)
Writes docs/figures/pytics/pytics_15_colour_terms_effect.png and pytics_colour_terms_stats.json."""
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
from ava.photometry import ensemble as E, intercal as IC
from ava.plots import webplots as wp

ROOT = Path(__file__).resolve().parents[2]
PHOT = cfg.phot_dir(TARGET); DB = frame_db_path()
BEF = Path(sys.argv[1]); OUT = ROOT / "docs/figures/pytics"
F = ["up", "B", "gp", "V", "rp", "ip", "zs"]; LBL = dict(up="u", B="B", gp="g", V="V", rp="r", ip="i", zs="z")
fd = wp.load_filter_dict(ROOT / "data/reference/filter_dict.txt")
COL = {r.lco: r.color for r in fd[fd.lco_flag].drop_duplicates("lco").itertuples()}
wp._style(); plt.rcParams.update({"font.size": 10, "legend.frameon": False})
ref = pd.read_csv(PHOT / "reference_stars.csv")
colours = (ref.lco_g - ref.lco_i).set_axis(ref.star_id).dropna()
st = {}


def rob(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return 1.4826 * np.median(np.abs(x - np.median(x))) if len(x) else np.nan


def star_resid(sol, d):
    """per-star robust rms of the calibrated comparison-star magnitudes (all cameras)."""
    s = sol.stars.set_index("star_id"); ep = sol.epochs.set_index("frame"); sc = sol.scopes.set_index("scope")
    x = E.clean_comparisons(d); x = x[x.star_id.isin(s.index) & x.frame.isin(ep.index)].copy()
    v = x.mag_inst - x.frame.map(ep.DMAGT) - x.scope.map(sc.DMAGS)
    if sol.meta.get("colour_terms"):
        dc = (x.star_id.map(s.colour) - sol.meta["c0"]).fillna(0)
        v = v - x.scope.map(sc.CK).fillna(0) * dc
    x["v"] = v
    g = x.groupby("star_id")
    return pd.DataFrame({"mag": g.v.median(), "rms": g.v.apply(rob)})


def same_night_pairs(lc):
    """AGN: nights observed by two different Sinistro cameras (< 0.4 d apart):
    robust σ of the flux ratio − 1 (%), i.e. the camera-to-camera calibration noise."""
    x = lc[lc.good & ~lc.scope.str.contains("-ep")]
    nt = IC.nightly(x.assign(mag=x["mag"], mag_err=x["mag_err"]))
    out = []
    for f in F:
        pass
    return nt


before_rows, after_rows, rep = [], [], []
fig, ax = plt.subplots(2, 3, figsize=(15, 8))
lc_b = pd.read_parquet(BEF / "agn_lightcurve_pytics.parquet"); lc_a = pd.read_parquet(PHOT / "agn_lightcurve_pytics.parquet")
for f in F:
    d = E.load_target(PHOT, DB, TARGET, f)
    sb = E.Solution.load(BEF / "pytics" / f); sa = E.Solution.load(E.solution_dir(PHOT, f))
    rb, ra = star_resid(sb, d), star_resid(sa, d)
    j = rb.join(ra, rsuffix="_a").dropna()
    br = j[j.mag < np.percentile(j.mag, 30)]
    # same-night cross-camera AGN pairs
    def pairs(lc):
        x = lc[(lc.Filter == f) & lc.good & ~lc.scope.str.contains("-ep")].copy()
        x["F"], x["Fe"] = IC.to_mjy(x["mag"], x["mag_err"])
        x["night"] = np.floor(x.MJD - 0.5).astype(int)
        g = x.groupby(["night", "scope"]).agg(F=("F", "median"), MJD=("MJD", "median")).reset_index()
        r = []
        for _, h in g.groupby("night"):
            if h.scope.nunique() >= 2:
                h = h.sort_values("MJD")
                for i in range(len(h) - 1):
                    if abs(h.MJD.iloc[i + 1] - h.MJD.iloc[i]) < 0.4:
                        r.append(h.F.iloc[i + 1] / h.F.iloc[i] - 1)
        return np.array(r) * 100
    pb, pa = pairs(lc_b), pairs(lc_a)
    # intercal: Sinistro offsets
    tb = pd.read_csv(BEF / "pytics" / "intercal.csv"); ta = pd.read_csv(PHOT / "pytics" / "intercal.csv")
    tb, ta = [t[(t["filter"] == f) & ~t.scope.str.contains("-ep")] for t in (tb, ta)]
    fb, fa = (tb.b1 / tb.F_mean * 100), (ta.b1 / ta.F_mean * 100)
    # absolute zp
    zb, za = sb.meta["zp_fit"], sa.meta["zp_fit"]
    rep.append(dict(filter=f, star_rms_bright_before=1e3 * br.rms.median(), star_rms_bright_after=1e3 * br.rms_a.median(),
                    star_rms_all_before=1e3 * j.rms.median(), star_rms_all_after=1e3 * j.rms_a.median(),
                    pairs=len(pa), pair_rms_before=rob(pb), pair_rms_after=rob(pa),
                    sinistro_offset_rms_before=float(np.sqrt(np.mean(fb ** 2))), sinistro_offset_rms_after=float(np.sqrt(np.mean(fa ** 2))),
                    zp_scatter_before=1e3 * zb["scatter"], zp_scatter_after=1e3 * za["scatter"],
                    zp_before=zb["zp_agn"], zp_after=za["zp_agn"],
                    agn_mean_shift_mmag=1e3 * float(np.median(lc_a[lc_a.Filter == f].set_index("frame").mag
                                                              - lc_b[lc_b.Filter == f].set_index("frame").mag)),
                    loops_before=sb.meta["loops"], loops_after=sa.meta["loops"]))
    ax[0, 0].plot(j.mag, 1e3 * (j.rms_a - j.rms), "o", ms=3, color=COL[f], label=LBL[f])
r = pd.DataFrame(rep)
ax[0, 0].axhline(0, color="grey", lw=0.6); ax[0, 0].set_xlabel("star instrumental mag"); ax[0, 0].set_ylim(-8, 4)
ax[0, 0].set_ylabel("Δ star rms, after − before (mmag)"); ax[0, 0].legend(ncol=4, fontsize=8)
ax[0, 0].set_title("comparison stars across all cameras")
x = np.arange(len(F)); c = [COL[f] for f in F]
for a, (b_, a_, t, u) in zip([ax[0, 1], ax[0, 2], ax[1, 0], ax[1, 1]],
                             [("star_rms_bright_before", "star_rms_bright_after", "bright 30% stars: robust rms", "mmag"),
                              ("pair_rms_before", "pair_rms_after", "AGN, same night, two Sinistro cameras", "robust σ of flux ratio (%)"),
                              ("sinistro_offset_rms_before", "sinistro_offset_rms_after", "AGN offset of each Sinistro camera vs the rest", "rms of b/F (%)"),
                              ("zp_scatter_before", "zp_scatter_after", "absolute ZP: star scatter vs GSPC", "mmag")]):
    a.bar(x - 0.2, r[b_], 0.4, color="0.65", label="before (one offset per camera)")
    a.bar(x + 0.2, r[a_], 0.4, color=c, label="after (+ colour term per camera)")
    for i in range(len(F)):
        a.text(i - 0.2, r[b_][i], f"{r[b_][i]:.2f}" if r[b_][i] < 10 else f"{r[b_][i]:.1f}", ha="center", va="bottom", fontsize=7)
        a.text(i + 0.2, r[a_][i], f"{r[a_][i]:.2f}" if r[a_][i] < 10 else f"{r[a_][i]:.1f}", ha="center", va="bottom", fontsize=7)
    a.set_xticks(x); a.set_xticklabels([LBL[f] for f in F]); a.minorticks_off()
    a.tick_params(axis="x", which="both", top=False, bottom=False); a.set_title(t); a.set_ylabel(u)
ax[0, 1].legend(fontsize=7)
# CK per scope heat map
ck = pd.concat([E.Solution.load(E.solution_dir(PHOT, f)).scopes.assign(filter=f) for f in F])
piv = ck.pivot(index="scope", columns="filter", values="CK")[F] * 1e3
im = ax[1, 2].imshow(piv.values, cmap="RdBu_r", vmin=-40, vmax=40, aspect="auto")
for (i, k), v in np.ndenumerate(piv.values):
    if np.isfinite(v):
        ax[1, 2].text(k, i, f"{v:+.0f}", ha="center", va="center", fontsize=6)
ax[1, 2].set_yticks(range(len(piv))); ax[1, 2].set_yticklabels(piv.index, fontsize=7)
ax[1, 2].set_xticks(range(len(F))); ax[1, 2].set_xticklabels([LBL[f] for f in F]); ax[1, 2].minorticks_off()
ax[1, 2].tick_params(which="both", top=False, right=False, bottom=False, left=False)
fig.colorbar(im, ax=ax[1, 2], label="CK (mmag per mag of g−i)"); ax[1, 2].set_title("fitted per-camera colour terms")
fig.tight_layout(); fig.savefig(OUT / "pytics_15_colour_terms_effect.png", dpi=150, bbox_inches="tight")
r.round(3).to_csv(OUT / "pytics_colour_terms_effect.csv", index=False)
pd.set_option("display.width", 250); print(r.round(2).to_string())
