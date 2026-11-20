"""Figures for the QC-gate / linearity report (20 Nov 2026)."""
import sqlite3
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

LIN, ESO, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)
plt.rcdefaults()
plt.rcParams["text.usetex"] = False
C1, C2, GREY, INK = "#2a78d6", "#eb6834", "#9a9a94", "#3b3b38"
plt.rcParams.update({"axes.edgecolor": GREY, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
                     "axes.spines.top": False, "axes.spines.right": False, "font.size": 10})

# ---- 1. linearity ------------------------------------------------------------------------------
B = pd.read_csv(LIN / "lin_corrected.csv")
N = pd.read_csv(LIN / "linearity_bins.csv")
fig, ax = plt.subplots(figsize=(7.2, 4.2))
ax.axhspan(-1, 1, color="#ecebe6", zorder=0, lw=0)
ax.axhline(0, color=GREY, lw=0.8)
ax.axvline(0.8, color=GREY, lw=1, ls="--")
ax.text(0.805, 4.3, "agn_saturated cut (0.8)", fontsize=8, color=INK, va="top")
n = N[(N.fam == "fa") & (N.mid <= 1.0)]
ax.plot(n.mid, 1e3 * n.med, color=GREY, lw=1.5, ls=":", marker="o", ms=4, mfc="white",
        label="Sinistro, binned by measured peak (selection bias)")
for fam, col, lab, dx in (("fa", C1, "Sinistro (fa)", -0.006), ("ep", C2, "MuSCAT (ep)", 0.006)):
    s = B[(B.fam == fam) & (B.mid <= 1.0) & (B.n >= 20)]
    ax.errorbar(s.mid + dx, 1e3 * s.med, yerr=1e3 * s.err, color=col, lw=2, marker="o", ms=6, capsize=0,
                mec="white", mew=1.5, label=f"{lab}, predicted peak, frame-corrected")
ax.set_xlim(0, 1.02)
ax.set_ylim(-8.5, 4.5)
ax.set_xlabel("star peak counts / saturation level")
ax.set_ylabel("magnitude residual (mmag; + = fainter)")
ax.set_title("Mrk 817 comparison stars: no non-linearity up to saturation", loc="left", fontsize=11)
ax.legend(frameon=False, fontsize=8, loc="lower left")
fig.text(0.01, 0.005, "Residual = star's ensemble-calibrated mag minus its median; grey band ±1 mmag. FLAGS 4|8|16 "
         "excluded; magerr < 0.01.", fontsize=7, color=INK)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(OUT / "sinistro_linearity_mrk817.png", dpi=160)

# ---- 2. ESO 511-30 frames reaching PyTICS: old gate vs new ------------------------------------
fq = pd.read_sql("select * from frame_qc", sqlite3.connect(ESO / "frame_qc_ESO_511-30.sqlite"))
ign = {"no_zp", "zp_scatter", "zp_offset"}
flags = fq.qc_flags.fillna("").str.split(",").apply(lambda s: {x for x in s if x})
deblend_only = fq.agn_flags.fillna(0).astype(int).map(lambda v: (v & 28) == 0)
# new flag set: agn_flagged only for 4|8|16
newf = [({x for x in s if x != "agn_flagged"} | ({"agn_flagged"} if not d else set())) for s, d in zip(flags, deblend_only)]
new_ok = pd.Series([not (s - ign) for s in newf], index=fq.index)
order = ["up", "B", "gp", "V", "rp", "ip", "zs"]
tab = pd.DataFrame({"n": fq.groupby("filter").size(), "old": fq.groupby("filter").qc_pass.sum(),
                    "new": new_ok.groupby(fq["filter"]).sum()}).loc[order]
fig, ax = plt.subplots(figsize=(7.2, 3.8))
x = np.arange(len(order))
w = 0.38
ax.bar(x - w / 2 - 0.01, tab.old, w, color=C2, label=f"current gate (qc_pass): {tab.old.sum()/tab.n.sum():.0%} kept")
ax.bar(x + w / 2 + 0.01, tab.new, w, color=C1, label=f"new gate: {tab.new.sum()/tab.n.sum():.0%} kept")
ax.plot(np.r_[x - 0.45, x + 0.45].reshape(2, -1), np.vstack([tab.n, tab.n]), color=INK, lw=1)
for i, (o, nw, t) in enumerate(zip(tab.old, tab.new, tab.n)):
    ax.text(i - w / 2, o + 15, f"{o/t:.0%}", ha="center", fontsize=7, color=INK)
    ax.text(i + w / 2, nw + 15, f"{nw/t:.0%}", ha="center", fontsize=7, color=INK)
ax.set_xticks(x, order)
ax.set_ylabel("frames into PyTICS")
ax.set_ylim(0, 1550)
ax.set_title("ESO 511-30: frames reaching PyTICS (black line = all frames)", loc="left", fontsize=11)
ax.legend(frameon=False, fontsize=8, loc="upper left", ncol=2)
fig.tight_layout()
fig.savefig(OUT / "eso511_pytics_gate.png", dpi=160)
tab.to_csv(OUT / "eso511_pytics_gate.csv")

# ---- 3. ESO 511-30: deblended (FLAGS 2) vs clean frames of the same night -------------------------
lc = pd.read_csv(ESO / "agn_lightcurve.csv").merge(fq[["frame", "agn_flags", "day_obs", "site", "agn_peak", "saturate"]],
                                                  on="frame")
fig, axs = plt.subplots(1, 2, figsize=(7.2, 3.4), gridspec_kw=dict(width_ratios=[1.3, 1]))
ax = axs[0]
cols = {"gp": "#1baf7a", "rp": C2, "ip": C1}
for k, (f, col) in enumerate(cols.items()):
    d = lc[lc["filter"] == f]
    diffs = []
    for _, g in d.groupby(["day_obs", "site"]):
        a, b = g[g.agn_flags == 2], g[g.agn_flags == 0]
        if len(a) and len(b):
            diffs.append(1e3 * (a.mag.median() - b.mag.median()))
    diffs = np.array(diffs)
    yy = np.full(len(diffs), k) + np.random.default_rng(k).uniform(-0.18, 0.18, len(diffs))
    ax.scatter(diffs, yy, s=14, color=col, alpha=0.7, lw=0)
    ax.plot([np.median(diffs)] * 2, [k - 0.3, k + 0.3], color=INK, lw=2)
    ax.text(28, k + 0.28, f"N={len(diffs)}, median {np.median(diffs):+.1f}", va="center", fontsize=7, color=INK)
ax.axvline(0, color=GREY, lw=0.8)
ax.set_yticks(range(3), list(cols))
ax.set_xlim(-32, 62)
ax.set_xlabel("FLAGS 2 minus clean, same night (mmag)")
ax.set_title("FLAGS 2 does not bias the AGN", loc="left", fontsize=10)
ax = axs[1]
fr = (fq.agn_peak / fq.saturate).dropna()
ax.hist(fr, bins=np.linspace(0, 1, 51), color=C1)
ax.axvline(0.8, color=GREY, ls="--", lw=1)
ax.set_xlabel("AGN peak / saturation")
ax.set_ylabel("frames")
ax.set_title("ESO 511-30 nucleus: far below saturation", loc="left", fontsize=10)
fig.tight_layout()
fig.savefig(OUT / "eso511_deblend_and_peak.png", dpi=160)
print(tab)
