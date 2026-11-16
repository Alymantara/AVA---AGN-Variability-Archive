"""Verification of the empirical AGN error model (ava.photometry.errors) on held-out data.

Splits: (1) even / odd nights (fit on one, test on the other, both ways);
        (2) time: fit on MJD < 59900, test on MJD >= 59900 (and back).
Tests:  same-camera pairs < 1 h (random error), flat in error sextiles, vs Δt;
        different-camera pairs < 6 h (total error), Sinistro-Sinistro and MuSCAT-Sinistro;
        parameter stability between the splits.
Writes docs/figures/pytics/pytics_23_error_model_verification.png + pytics_error_model_verification.csv"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/juan/astro/AVA")
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ava.photometry import errors as ER
from ava.plots import webplots as wp

ROOT = Path("/Users/juan/astro/AVA"); PHOT = ROOT / "data/test_archive/photometry/Mrk_817"; OUT = ROOT / "docs/figures/pytics"
F = ["up", "B", "gp", "V", "rp", "ip", "zs"]; LBL = dict(up="u", B="B", gp="g", V="V", rp="r", ip="i", zs="z")
fd = wp.load_filter_dict(ROOT / "data/reference/filter_dict.txt")
BCOL = {r.lco: r.color for r in fd[fd.lco_flag].drop_duplicates("lco").itertuples()}
wp._style(); plt.rcParams.update({"font.size": 9, "legend.frameon": False, "legend.fontsize": 7})
rob = ER.rob

lc = pd.read_parquet(PHOT / "agn_lightcurve_pytics.parquet")
lc = lc[lc.Filter.isin(F)]
night = np.floor(lc.MJD - 0.5)
SPLITS = {"even→odd": (night % 2 == 0, night % 2 == 1), "odd→even": (night % 2 == 1, night % 2 == 0),
          "early→late": (lc.MJD < 59900, lc.MJD >= 59900), "late→early": (lc.MJD >= 59900, lc.MJD < 59900)}


def side(P, i, table):
    d = pd.DataFrame({"Filter": P.Filter, "camera": P[f"scope{i}"].str.split("-").str[-1],
                      "magerr": P[f"p{i}"], "rms_t": P[f"t{i}"]})
    return ER.sigma_rand(d, table)


def old_err(P, i, tot):
    """PyTICS errors of each side of the pair (looked up from the light curve)."""
    key = lc.set_index(["Filter", "MJD"])
    col = "mag_ic_err" if tot else "mag_err_rand"
    t = P.MJD if i == 1 else P.MJD + P.dt
    return key[col].reindex(pd.MultiIndex.from_arrays([P.Filter, t])).to_numpy()


rows, params, octile = [], [], []
for name, (tr, te) in SPLITS.items():
    T = ER.fit_error_model(lc[tr], mag="mag_ic")
    params.append(T.assign(split=name))
    S = ER.pairs(lc[te], 1 / 24, same=True, mag="mag_ic")
    C = ER.pairs(lc[te], 0.25, same=False, mag="mag_ic")
    S["z_new"] = S.dm / np.hypot(side(S, 1, T), side(S, 2, T))
    S["z_old"] = S.dm / np.hypot(old_err(S, 1, False), old_err(S, 2, False))
    S["e_new"] = np.hypot(side(S, 1, T), side(S, 2, T)) / np.sqrt(2)
    S["e_old"] = np.hypot(old_err(S, 1, False), old_err(S, 2, False)) / np.sqrt(2)
    sc = C.Filter.map(T.groupby("Filter").s_cam.first()).fillna(0)
    C["z_new"] = C.dm / np.sqrt(side(C, 1, T) ** 2 + side(C, 2, T) ** 2 + 2 * sc ** 2)
    C["z_old"] = C.dm / np.hypot(old_err(C, 1, True), old_err(C, 2, True))
    C["mus"] = (C.fam1 == "ep") | (C.fam2 == "ep")
    for f in F:
        for fam in ["fa", "ep"]:
            s = S[(S.Filter == f) & (S.fam1 == fam)]
            if len(s) < 50:
                continue
            q_new = pd.qcut(s.e_new, 6, labels=False, duplicates="drop"); q_old = pd.qcut(s.e_old, 6, labels=False, duplicates="drop")
            rn = [rob(s.z_new[q_new == i]) for i in range(6)]; ro = [rob(s.z_old[q_old == i]) for i in range(6)]
            rows.append(dict(split=name, filter=LBL[f], test="same camera < 1 h", family=fam, n=len(s),
                             old=rob(s.z_old), new=rob(s.z_new), old_sextile_spread=np.nanmax(ro) - np.nanmin(ro),
                             new_sextile_spread=np.nanmax(rn) - np.nanmin(rn), new_frac_gt3=float((s.z_new.abs() > 3).mean())))
            if name in ("even→odd", "odd→even"):
                for i in range(6):
                    octile.append(dict(split=name, f=f, fam=fam, i=i, e_old=1e3 * s.e_old[q_old == i].median(), z_old=ro[i],
                                       e_new=1e3 * s.e_new[q_new == i].median(), z_new=rn[i]))
        for lab, c in [("Sinistro-Sinistro", C[(C.Filter == f) & ~C.mus]), ("MuSCAT-Sinistro", C[(C.Filter == f) & C.mus])]:
            if len(c) >= 20:
                rows.append(dict(split=name, filter=LBL[f], test="different camera < 6 h", family=lab, n=len(c),
                                 old=rob(c.z_old), new=rob(c.z_new), new_frac_gt3=float((c.z_new.abs() > 3).mean())))
R = pd.DataFrame(rows); Pm = pd.concat(params); O = pd.DataFrame(octile)
R.round(3).to_csv(OUT / "pytics_error_model_verification.csv", index=False)
Pm.round(5).to_csv(OUT / "pytics_error_model_params_by_split.csv", index=False)
pd.set_option("display.width", 250)
print(R.groupby(["test", "family", "filter"])[["old", "new"]].agg(["min", "max"]).round(2).to_string())
print(R[R.test == "same camera < 1 h"].groupby(["family"])[["old_sextile_spread", "new_sextile_spread"]].median().round(2))

# ------------------------------------------------------------------ figure
fig, ax = plt.subplots(2, 3, figsize=(16, 9)); ax = ax.ravel()
for f in F:
    o = O[(O.f == f) & (O.fam == "fa")].groupby("i").mean(numeric_only=True)
    ax[0].plot(o.e_old, o.z_old, "o--", ms=3, color=BCOL[f], alpha=0.45)
    ax[0].plot(o.e_new, o.z_new, "o-", ms=3, color=BCOL[f], label=LBL[f])
    o = O[(O.f == f) & (O.fam == "ep")].groupby("i").mean(numeric_only=True)
    if len(o):
        ax[1].plot(o.e_old, o.z_old, "o--", ms=3, color=BCOL[f], alpha=0.45)
        ax[1].plot(o.e_new, o.z_new, "o-", ms=3, color=BCOL[f], label=LBL[f])
for a, t in zip(ax[:2], ["Sinistro", "MuSCAT"]):
    a.axhline(1, color="k", ls="--", lw=0.8); a.set_xscale("log"); a.set_ylim(0.2, 1.8)
    a.set_xlabel("quoted random error per epoch (mmag, sextiles)"); a.set_ylabel("robust σ_z, held-out nights")
    a.set_title(f"{t}, same camera < 1 h: dashed PyTICS, solid model"); a.legend(ncol=4)
# held-out σ_z per filter, all four splits as points
x = np.arange(len(F))
for j, (test, fam, off, mk) in enumerate([("same camera < 1 h", "fa", -0.25, "o"), ("same camera < 1 h", "ep", -0.08, "s"),
                                           ("different camera < 6 h", "Sinistro-Sinistro", 0.08, "^"),
                                           ("different camera < 6 h", "MuSCAT-Sinistro", 0.25, "D")]):
    for i, f in enumerate(F):
        r = R[(R.test == test) & (R.family == fam) & (R["filter"] == LBL[f])]
        if len(r):
            ax[2].plot(np.full(len(r), i + off), r.old, mk, color="0.75", ms=4)
            ax[2].plot(np.full(len(r), i + off), r.new, mk, color=BCOL[f], ms=4)
ax[2].axhline(1, color="k", ls="--", lw=0.8); ax[2].set_xticks(x); ax[2].set_xticklabels([LBL[f] for f in F])
ax[2].minorticks_off(); ax[2].tick_params(axis="x", which="both", top=False, bottom=False); ax[2].set_ylim(0.3, 2.6)
ax[2].set_ylabel("robust σ_z on held-out data (4 splits)")
h = [plt.Line2D([], [], ls="none", marker=m, color="0.3") for m in "os^D"] + [plt.Line2D([], [], ls="none", marker="o", color="0.75")]
ax[2].legend(h, ["Sinistro same cam", "MuSCAT same cam", "Sinistro–Sinistro", "MuSCAT–Sinistro", "PyTICS errors (grey)"], ncol=2, fontsize=6)
ax[2].set_title("held-out: colour = model, grey = PyTICS")
# parameter stability
for k_, (col, lab, scale) in enumerate([("k", "k (× σ_phot)", 1), ("beta", "β (× rms_t)", 1), ("s0", "s0 (mmag)", 1e3)]):
    a = ax[3 + k_] if k_ < 2 else ax[5]
    for i, f in enumerate(F):
        for fam, off, mk in [("fa", -0.12, "o"), ("ep", 0.12, "s")]:
            p = Pm[(Pm.Filter == f) & (Pm.family == fam) & (Pm.source == "fit")]
            a.plot(np.full(len(p), i + off), scale * p[col], mk, color=BCOL[f], ms=4, alpha=0.8)
    a.set_xticks(x); a.set_xticklabels([LBL[f] for f in F]); a.minorticks_off()
    a.tick_params(axis="x", which="both", top=False, bottom=False); a.set_ylabel(lab)
    a.set_title(f"{lab}: fits on the 4 training halves (o Sinistro, □ MuSCAT)")
for i, f in enumerate(F):
    p = Pm[Pm.Filter == f].groupby("split").s_cam.first()
    ax[5].plot(np.full(len(p), i + 0.3), 1e3 * p, "_", color="k", ms=10, mew=2)
ax[5].set_title("s0 (o □) and camera term s_cam (—), mmag"); ax[5].set_ylabel("mmag")
ax[3].axhline(1, color="k", ls="--", lw=0.8); ax[4].axhline(1, color="k", ls="--", lw=0.8)
fig.tight_layout(); fig.savefig(OUT / "pytics_23_error_model_verification.png", dpi=150, bbox_inches="tight")
