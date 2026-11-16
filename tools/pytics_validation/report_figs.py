"""PyTICS report figures (docs/figures/pytics). Run after the full ensemble run."""
import sys, json, warnings, time
warnings.filterwarnings("ignore")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))   # repository root
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ava.config import cfg  # noqa: E402  (AVA_CONFIG selects the archive; AVA_TARGET the target)
from ava.pipeline.tasks.calibrate import frame_db_path  # noqa: E402
TARGET = __import__("os").environ.get("AVA_TARGET", "Mrk_817")
from ava.photometry import ensemble as E, intercal as IC, store
from ava.plots import webplots as wp

ROOT = Path(__file__).resolve().parents[2]
PHOT = cfg.phot_dir(TARGET); DB = frame_db_path()
SCR = Path(sys.argv[1]); OUT = ROOT / "docs/figures/pytics"; OUT.mkdir(parents=True, exist_ok=True)
wp._style()
plt.rcParams.update({"font.size": 10, "axes.labelsize": 10, "legend.fontsize": 8, "legend.frameon": False})
fd = wp.load_filter_dict(ROOT / "data/reference/filter_dict.txt")
COL = {r.lco: r.color for r in fd[fd.lco_flag].drop_duplicates("lco").itertuples()}
COL["Y"] = "#c0392b" if "Y" not in COL else COL["Y"]
LBL = {"up": "u", "B": "B", "gp": "g", "V": "V", "rp": "r", "ip": "i", "zs": "z", "Y": "Y"}
F = ["up", "B", "gp", "V", "rp", "ip", "zs"]
sols = {f: E.Solution.load(E.solution_dir(PHOT, f)) for f in F + ["Y"]}
lc_all = pd.read_parquet(PHOT / "agn_lightcurve_pytics.parquet")
lc = lc_all[lc_all.good]
stats = {"agn_epochs_flagged": {f: int((~g.good).sum()) for f, g in lc_all.groupby("Filter")},
         "agn_epochs": {f: int(len(g)) for f, g in lc_all.groupby("Filter")}}


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=150, bbox_inches="tight"); plt.close(fig); print("wrote", name)


def scope_colour(scopes):
    cm = plt.get_cmap("tab20")
    fa = [s for s in scopes if "-ep" not in s]
    d = {s: cm(i % 20) for i, s in enumerate(sorted(fa))}
    d.update({s: "k" for s in scopes if "-ep" in s})
    return d


# ---------------------------------------------------------------- 1 validation + timing
def fig_validation():
    fig, ax = plt.subplots(2, 2, figsize=(11, 7))
    for j, (tag, lab) in enumerate([("g2023", "g, 2023 subset (364 epochs)"), ("gfull", "g, all data (2858 epochs)")]):
        o = pd.read_parquet(SCR / f"orig_{tag}_agn.parquet")
        d = pd.read_parquet(SCR / f"{tag}.parquet"); agn = int(d.loc[d.is_agn, "star_id"].iloc[0])
        s = E.fit(d, agn_id=agn, bad_flags=0, rms_err_floor=0.0, atol=0.0)   # exact PyTICS stopping rule      # the original has no flag cut (gfull was pre-cleaned)
        a = E.apply(s, d[d.is_agn]).merge(o[["MJD", "mag", "err"]], on="MJD", suffixes=("", "_o"))
        dd = (a.mag - a.mag_o) * 1e3
        ax[0, j].plot(a.MJD, dd, ".", ms=3, color=COL["gp"])
        ax[0, j].set_title(lab); ax[0, j].set_xlabel("MJD"); ax[0, j].set_ylabel("AGN: port − original (mmag)")
        ax[0, j].set_ylim(-1, 1)
        ax[0, j].text(0.02, 0.92, f"max |Δ| = {np.abs(dd).max():.1e} mmag, Δσ ratio = {(a.mag_err / a.err).median():.4f}",
                      transform=ax[0, j].transAxes)
        stats[f"valid_{tag}_maxdiff_mmag"] = float(np.abs(dd).max())
    oe = pd.read_parquet(SCR / "orig_gfull_stars.parquet").groupby("MJD")[["DMAGT"]].first()
    k = sols["gp"].epochs.set_index("MJD").join(oe, rsuffix="_o", how="inner")
    ax[1, 0].plot(k.DMAGT_o, k.DMAGT, ".", ms=3, color=COL["gp"]); ax[1, 0].plot([-1, 1.5], [-1, 1.5], "k-", lw=0.6)
    ax[1, 0].set_xlabel("DMAGT original PyTICS (mag)"); ax[1, 0].set_ylabel("DMAGT port (mag)")
    ax[1, 0].set_title("epoch corrections, g all data")
    t = [("g 2023\noriginal", 33.2), ("g 2023\nport", 0.83), ("g all\noriginal", 433.7), ("g all\nport", 6.1),
         ("8 filters\nport", 53.1)]
    c = ["0.6", COL["gp"], "0.6", COL["gp"], "0.2"]
    b = ax[1, 1].bar(range(len(t)), [v for _, v in t], color=c)
    for i, (_, v) in enumerate(t):
        ax[1, 1].text(i, v * 1.15, f"{v:.1f} s" if v < 100 else f"{v / 60:.1f} min", ha="center", fontsize=8)
    ax[1, 1].set_yscale("log"); ax[1, 1].set_xticks(range(len(t))); ax[1, 1].set_xticklabels([n for n, _ in t])
    ax[1, 1].minorticks_off(); ax[1, 1].tick_params(axis="x", which="both", top=False, bottom=False)
    ax[1, 1].set_ylabel("wall time (s)"); ax[1, 1].set_ylim(0.3, 2000); ax[1, 1].set_title("full-fit run time")
    fig.tight_layout(); save(fig, "pytics_01_validation")


# ---------------------------------------------------------------- 2 convergence
def fig_convergence():
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    d = E.load_target(PHOT, DB, TARGET, "gp"); agn = int(d.loc[d.is_agn, "star_id"].iloc[0])
    for bf, ls, lab in [(0, "--", "all comparison measurements"), (E.BAD_FLAGS, "-", "FLAGS 4|8|16 removed")]:
        s = E.fit(d, agn_id=agn, bad_flags=bf, max_loops=200)
        h = np.array([x[0] for x in s.history])
        ax[0].semilogy(np.arange(2, len(h) + 2), h, ls, color=COL["gp"], label=f"{lab} ({len(h) + 1} loops)")
    ax[0].axhline(1e-4, color="grey", lw=0.6); ax[0].set_xlabel("loop"); ax[0].set_ylabel("max |Δp| / σ_p")
    ax[0].set_title("g: convergence (threshold 1e-4)"); ax[0].legend()
    for f in F:
        s = E.fit(E.load_target(PHOT, DB, TARGET, f), agn_id=sols[f].meta["agn_id"])
        h = np.array([x[0] for x in s.history])
        ax[1].semilogy(np.arange(2, len(h) + 2), h, color=COL[f], label=f"{LBL[f]} ({len(h) + 1})")
    ax[1].axhline(1e-4, color="grey", lw=0.6); ax[1].set_xlabel("loop"); ax[1].legend(ncol=2)
    ax[1].set_title("all filters, final settings")
    fig.tight_layout(); save(fig, "pytics_02_convergence")


# ---------------------------------------------------------------- 3 scope offsets
def fig_scopes():
    fig, ax = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    scopes = sorted(set().union(*[set(sols[f].scopes.scope) for f in F]))
    x = {s: i for i, s in enumerate(scopes)}
    for j, f in enumerate(F):
        t = sols[f].scopes
        xx = np.array([x[s] for s in t.scope]) + (j - 3) * 0.1
        ax[0].errorbar(xx, t.DMAGS, t.DMAGS_err, fmt="o", ms=4, color=COL[f], label=LBL[f])
        ax[1].plot(xx, t.rms_sc * 1e3, "o", ms=4, color=COL[f])
    ax[0].axhline(0, color="grey", lw=0.6); ax[0].set_ylabel("DMAGS (mag)"); ax[0].legend(ncol=7)
    ax[0].set_title("per telescope+camera offsets (zero-mean over all data)")
    ax[1].set_ylabel("rms_sc (mmag)"); ax[1].set_xticks(range(len(scopes))); ax[1].set_xticklabels(scopes, rotation=40, ha="right")
    ax[1].tick_params(axis="x", which="minor", bottom=False, top=False)
    fig.tight_layout(); save(fig, "pytics_03_scope_offsets")


# ---------------------------------------------------------------- 4 epochs
def fig_epochs():
    fq = store.read_frame_qc(DB, TARGET).set_index("frame")
    ep = sols["gp"].epochs.copy()
    ep["airmass"] = ep.frame.map(fq.airmass); ep["fwhm"] = ep.frame.map(fq.fwhm_arcsec); ep["zp"] = ep.frame.map(fq.zp)
    sc = scope_colour(ep.scope.unique())
    fig, ax = plt.subplots(2, 2, figsize=(11, 7))
    for s, g in ep.groupby("scope"):
        ax[0, 0].plot(g.MJD, g.DMAGT, ".", ms=2, color=sc[s], label=s)
        ax[0, 1].plot(g.airmass, g.DMAGT, ".", ms=2, color=sc[s])
        ax[1, 0].plot(g.zp, -g.DMAGT, ".", ms=2, color=sc[s])
    ax[0, 0].set_xlabel("MJD"); ax[0, 0].set_ylabel("DMAGT (mag)"); ax[0, 0].set_title("g: per-epoch correction")
    ax[0, 0].invert_yaxis(); ax[0, 0].legend(ncol=3, fontsize=6, markerscale=3)
    ax[0, 1].set_xlabel("airmass"); ax[0, 1].set_ylabel("DMAGT (mag)"); ax[0, 1].invert_yaxis()
    ax[0, 1].set_title("extinction + transparency absorbed per epoch")
    ax[1, 0].set_xlabel("per-frame GSPC zero point (mag)"); ax[1, 0].set_ylabel("−DMAGT (mag)")
    ax[1, 0].set_title("PyTICS DMAGT vs per-frame ZP")
    for f in F:
        r = sols[f].epochs.rms_t * 1e3
        ax[1, 1].hist(np.clip(r, 0.01, 200), bins=np.logspace(-2, np.log10(200), 50), histtype="step", color=COL[f], label=LBL[f])
    ax[1, 1].set_xscale("log"); ax[1, 1].set_xlabel("rms_t (mmag)"); ax[1, 1].set_ylabel("epochs"); ax[1, 1].legend(ncol=2)
    ax[1, 1].set_title("extra per-epoch scatter (0 = consistent)")
    fig.tight_layout(); save(fig, "pytics_04_epochs")


# ---------------------------------------------------------------- 5 star repeatability
def fig_star_rms():
    fq = store.read_frame_qc(DB, TARGET).set_index("frame")
    fig, ax = plt.subplots(2, 4, figsize=(14, 6.4), sharey=True)
    ax = ax.ravel(); rows = []
    for i, f in enumerate(F):
        d = E.clean_comparisons(E.load_target(PHOT, DB, TARGET, f))
        s = sols[f]; st = s.stars.set_index("star_id")
        d = d[d.star_id.isin(st.index) & d.frame.isin(set(s.epochs.frame))].copy()
        d["pf"] = d.mag_inst + d.frame.map(fq.zp)
        ep = s.epochs.set_index("frame"); sc = s.scopes.set_index("scope")
        d["pt"] = d.mag_inst - d.frame.map(ep.DMAGT) - d.scope.map(sc.DMAGS) + s.meta.get("zp", 0)

        def rob(x):
            x = x[np.isfinite(x)]; m = np.median(x); r = 1.4826 * np.median(np.abs(x - m)); return r
        g = d.groupby("star_id")
        t = pd.DataFrame({"mag": g.pt.median(), "pf": g.pf.apply(rob) * 1e3, "pt": g.pt.apply(rob) * 1e3,
                          "err": g.magerr.median() * 1e3})
        ax[i].semilogy(t.mag, t.pf, "o", ms=3, mfc="none", color="0.5", label="per-frame GSPC ZP")
        ax[i].semilogy(t.mag, t.pt, "o", ms=3, color=COL[f], label="PyTICS")
        o = np.argsort(t.mag.values); ax[i].semilogy(t.mag.values[o], t.err.values[o], "k-", lw=0.6, label="median σ_phot")
        b = t[t.mag < np.percentile(t.mag, 30)]
        ax[i].set_title(f"{LBL[f]}: bright 30%: {b.pf.median():.1f} → {b.pt.median():.1f} mmag")
        ax[i].set_xlabel(f"{LBL[f]} (AB)")
        rows.append(dict(filter=f, bright_pf=b.pf.median(), bright_pt=b.pt.median(), all_pf=t.pf.median(), all_pt=t.pt.median()))
    ax[0].set_ylabel("star robust rms (mmag)"); ax[4].set_ylabel("star robust rms (mmag)"); ax[0].legend()
    ax[7].axis("off")
    fig.tight_layout(); save(fig, "pytics_05_star_repeatability")
    stats["star_rms"] = pd.DataFrame(rows).round(2).to_dict("records")


# ---------------------------------------------------------------- 6 AGN: PyTICS vs per-frame
def fig_agn_vs_perframe():
    pf = pd.read_parquet(PHOT / "agn_lightcurve.parquet")
    pf = pf[pf.qc_pass == 1]
    m = lc.merge(pf[["frame", "mag", "mag_err"]], on="frame", suffixes=("", "_pf"))
    fig, ax = plt.subplots(2, 1, figsize=(11, 7))
    rows = []
    for f in F:
        g = m[m.Filter == f]
        dd = (g.mag - g.mag_pf) * 1e3
        ax[0].plot(g.MJD, dd - np.median(dd), ".", ms=1.5, color=COL[f], label=f"{LBL[f]} (median {np.median(dd):+.0f} mmag)")
        # intra-night repeatability: consecutive frames, same scope, < 1 h apart
        def pair_rms(col):
            x = g.sort_values("MJD"); out = []
            for _, h in x.groupby("scope"):
                t, v = h.MJD.to_numpy(), h[col].to_numpy(); k = np.diff(t) < 1 / 24
                out.append(np.diff(v)[k])
            v = np.concatenate(out); return 1.4826 * np.median(np.abs(v - np.median(v))) / np.sqrt(2) * 1e3, len(v)
        a, n = pair_rms("mag_pf"); b, _ = pair_rms("mag"); b2, _ = pair_rms("mag_ic")
        rows.append(dict(filter=f, pairs=n, per_frame=a, pytics=b, offset=float(np.median(dd)),
                         diff_rms=float(1.4826 * np.median(np.abs(dd - np.median(dd))))))
    ax[0].set_ylim(-60, 60); ax[0].set_xlabel("MJD"); ax[0].set_ylabel("PyTICS − per-frame (mmag, median removed)")
    ax[0].legend(ncol=4, markerscale=6); ax[0].set_title("AGN: ensemble vs per-frame zero point (same QC-pass frames)")
    r = pd.DataFrame(rows); x = np.arange(len(r))
    ax[1].bar(x - 0.2, r.per_frame, 0.4, color="0.6", label="per-frame GSPC ZP")
    ax[1].bar(x + 0.2, r.pytics, 0.4, color=[COL[f] for f in r["filter"]], label="PyTICS")
    for i, row in r.iterrows():
        ax[1].text(i + 0.2, row.pytics + 0.2, f"{row.pytics:.1f}", ha="center", fontsize=8)
        ax[1].text(i - 0.2, row.per_frame + 0.2, f"{row.per_frame:.1f}", ha="center", fontsize=8)
    ax[1].set_xticks(x); ax[1].set_xticklabels([LBL[f] for f in r["filter"]]); ax[1].minorticks_off()
    ax[1].tick_params(axis="x", which="both", top=False, bottom=False)
    ax[1].set_ylabel("AGN intra-hour repeatability (mmag)"); ax[1].legend()
    ax[1].set_title("consecutive frames < 1 h apart, same telescope: robust σ(Δm)/√2")
    fig.tight_layout(); save(fig, "pytics_06_agn_vs_perframe")
    stats["agn_vs_perframe"] = r.round(2).to_dict("records")


# ---------------------------------------------------------------- 7 incremental
def fig_incremental():
    S = pd.read_csv(SCR / "incr/incremental_summary.csv"); N = pd.read_csv(SCR / "incr/incremental_nightly.csv")
    fig, ax = plt.subplots(2, 2, figsize=(11, 7))
    for j, test in enumerate(["A_last60d", "B_newscope"]):
        for f in F:
            c = pd.read_parquet(SCR / f"incr/cmp_{f}_{test}.parquet")
            dd = (c.mag_up - c.mag_full) * 1e3; dd -= np.median(dd[c.new])
            ax[0, j].plot(c.MJD[c.new], dd[c.new], ".", ms=3, color=COL[f], label=LBL[f])
        ax[0, j].set_ylim(-8, 8); ax[0, j].axhline(0, color="grey", lw=0.6)
        ax[0, j].set_xlabel("MJD"); ax[0, j].set_ylabel("update − full refit (mmag, offset removed)")
        ax[0, j].set_title({"A_last60d": "A: last 60 days added night by night",
                            "B_newscope": "B: from MJD 61058 (new camera 1m006-fa11)"}[test])
    ax[0, 0].legend(ncol=4, markerscale=3)
    x = np.arange(len(F)); a = S[S.test == "A_last60d"].set_index("filter").loc[F]; b = S[S.test == "B_newscope"].set_index("filter").loc[F]
    ax[1, 0].bar(x - 0.2, a.new_scatter_mmag, 0.4, color=[COL[f] for f in F], label="A: scatter")
    ax[1, 0].bar(x + 0.2, b.new_scatter_mmag, 0.4, color=[COL[f] for f in F], alpha=0.45, label="B: scatter")
    ax[1, 0].plot(x, a.med_err_mmag, "k_", ms=18, mew=2, label="median AGN σ")
    ax[1, 0].plot(x - 0.2, np.abs(a.new_off_mmag), "kv", ms=4, label="|constant offset| A")
    ax[1, 0].set_xticks(x); ax[1, 0].set_xticklabels([LBL[f] for f in F]); ax[1, 0].minorticks_off()
    ax[1, 0].tick_params(axis="x", which="both", top=False, bottom=False)
    ax[1, 0].set_ylabel("mmag"); ax[1, 0].legend(fontsize=7); ax[1, 0].set_title("new epochs: update vs full refit")
    for f in F:
        n = N[(N["filter"] == f) & (N.test == "B_newscope")]
        ax[1, 1].plot(n.n_new, n.ms, ".", ms=4, color=COL[f], label=LBL[f])
    full = S.groupby("filter").full_fit_s.first().loc[F] * 1e3
    for f in F:
        ax[1, 1].axhline(full[f], color=COL[f], lw=0.8, ls="--")
    ax[1, 1].set_yscale("log"); ax[1, 1].set_xlabel("new frames in the update"); ax[1, 1].set_ylabel("time (ms)")
    ax[1, 1].set_title("nightly update (dots) vs full refit (dashed)"); ax[1, 1].legend(ncol=4, fontsize=7)
    fig.tight_layout(); save(fig, "pytics_07_incremental")
    stats["incremental"] = S.round(3).to_dict("records")


# ---------------------------------------------------------------- 8 absolute ZP
def fig_abszp():
    t = pd.read_parquet(PHOT / "pytics/absolute_zp_stars.parquet")
    fig, ax = plt.subplots(2, 4, figsize=(14, 6.4)); ax = ax.ravel(); rows = []
    for i, f in enumerate(F + ["Y"]):
        g = t[t["filter"] == f]; z = sols[f].meta["zp_fit"]
        ax[i].plot(g.c[g.used], g.dm[g.used], "o", ms=3, color=COL[f])
        ax[i].plot(g.c[~g.used], g.dm[~g.used], "x", ms=4, color="0.5")
        xx = np.linspace(g.c.min(), g.c.max(), 10)
        ax[i].plot(xx, z["zp"] + z["C"] * (xx - z["c0"]), "k-", lw=1)
        ax[i].axvline(z["agn_colour"], color="r", lw=0.8, ls=":")
        ax[i].set_title(f"{LBL[f]}: C = {z['C']:+.3f}±{z['C_err']:.3f}, σ = {z['scatter'] * 1e3:.0f} mmag", fontsize=9)
        ax[i].set_xlabel("GSPC g − i"); ax[i].set_ylabel(f"{LBL[f]}$_{{GSPC}}$ − m*$_{{PyTICS}}$")
        lo, hi = np.percentile(g.dm, [2, 98]); ax[i].set_ylim(lo - 0.05, hi + 0.05)
        rows.append(dict(filter=f, n=z["n"], zp=z["zp"], zp_err=z["zp_err"], C=z["C"], C_err=z["C_err"],
                         scatter=z["scatter"], chi2nu=z["chi2nu"], zp_agn=z["zp_agn"]))
    fig.suptitle(f"absolute zero point: star means vs Gaia GSPC (red: AGN colour {z['agn_colour']:.2f})", y=1.0)
    fig.tight_layout(); save(fig, "pytics_08_absolute_zp")
    stats["abs_zp"] = pd.DataFrame(rows).round(4).to_dict("records")


# ---------------------------------------------------------------- 9 per-scope colour terms
def fig_scope_colour():
    ref = pd.read_csv(PHOT / "reference_stars.csv").set_index("star_id")
    fig, ax = plt.subplots(2, 4, figsize=(14, 6.4)); ax = ax.ravel(); rows = []
    for i, f in enumerate(F):
        ss = sols[f].star_scope.copy()
        ss["c"] = ss.star_id.map(ref.lco_g - ref.lco_i)
        ss = ss[np.isfinite(ss.c) & (ss.n > 20)]
        c_agn = sols[f].meta["zp_fit"]["agn_colour"]; c0 = sols[f].meta["zp_fit"]["c0"]
        sc = scope_colour(ss.scope.unique())
        for s, g in ss.groupby("scope"):
            if len(g) < 8:
                continue
            w = 1 / (g.offset_err ** 2 + 0.003 ** 2)
            A = np.vstack([np.ones(len(g)), g.c - c0]).T
            cov = np.linalg.inv(A.T @ (A * w.values[:, None])); p = cov @ (A.T @ (w.values * g.offset.values))
            pred = p[0] + p[1] * (c_agn - c0)
            rows.append(dict(filter=f, scope=s, slope=p[1], slope_err=np.sqrt(cov[1, 1]), agn_offset=pred))
            ax[i].plot(g.c, g.offset * 1e3, ".", ms=2, color=sc[s], alpha=0.6)
            xx = np.array([ss.c.min(), ss.c.max()])
            ax[i].plot(xx, (p[0] + p[1] * (xx - c0)) * 1e3, "-", color=sc[s], lw=1.5 if "-ep" in s else 0.8,
                       label=s if "-ep" in s else None)
        ax[i].axvline(c_agn, color="r", lw=0.8, ls=":"); ax[i].set_ylim(-40, 40)
        ax[i].set_title(f"{LBL[f]}"); ax[i].set_xlabel("GSPC g − i"); ax[i].set_ylabel("star × scope offset (mmag)")
        ax[i].legend(fontsize=7)
    r = pd.DataFrame(rows)
    piv = r.pivot(index="scope", columns="filter", values="slope")[F] * 1e3
    im = ax[7].imshow(piv.values, cmap="RdBu_r", vmin=-40, vmax=40, aspect="auto")
    ax[7].set_yticks(range(len(piv))); ax[7].set_yticklabels(piv.index, fontsize=6)
    ax[7].set_xticks(range(len(F))); ax[7].set_xticklabels([LBL[f] for f in F]); ax[7].minorticks_off()
    ax[7].tick_params(which="both", top=False, right=False, bottom=False, left=False)
    fig.colorbar(im, ax=ax[7], label="relative colour slope (mmag / mag)")
    fig.suptitle("per-camera colour terms relative to the ensemble (red: AGN colour)", y=1.0)
    fig.tight_layout(); save(fig, "pytics_09_scope_colour_terms")
    r.to_csv(OUT / "pytics_scope_colour_terms.csv", index=False)
    return r


# ---------------------------------------------------------------- 10/11 intercal
def fig_intercal(ct):
    tab = pd.read_csv(PHOT / "pytics/intercal.csv")
    ref_sc = sorted(s for s in lc.scope.unique() if "-fa" in s)
    fig, ax = plt.subplots(2, 4, figsize=(14, 6.6))
    for j, f in enumerate(["gp", "rp", "ip", "zs"]):
        g = lc[lc.Filter == f]; k = [s for s in g.scope.unique() if "-ep" in s][0]
        nt = IC.nightly(g); me = nt[nt.scope == k]; ref = IC.nightly(g[g.scope.isin(ref_sc)], by=())
        fr, fre, good = IC._interp(ref, me.MJD.to_numpy(), 3.0)
        x, y = fr[good], me.F.to_numpy()[good]; xe, ye = fre[good], me.Ferr.to_numpy()[good]
        r = tab[(tab["filter"] == f) & (tab.scope == k)].iloc[0]
        ax[0, j].errorbar(x, y, ye, xe, fmt="o", ms=3, color=COL[f], elinewidth=0.5)
        xx = np.array([x.min(), x.max()])
        ax[0, j].plot(xx, xx, "k:", lw=0.8, label="1:1")
        ax[0, j].plot(xx, r.a * xx + r.b, "k-", lw=1, label=f"a={r.a:.3f}±{r.a_err:.3f}, b={r.b:+.2f}±{r.b_err:.2f}")
        ax[0, j].plot(xx, xx + r.b1, "r--", lw=1, label=f"a≡1: b={r.b1:+.3f}±{r.b1_err:.3f} mJy")
        ok = xe < np.percentile(xe, 90) * 3
        lo, hi = min(x[ok].min(), y[ok].min()), max(x[ok].max(), y[ok].max()); pad = 0.05 * (hi - lo)
        ax[0, j].set_xlim(x[ok].min() - pad, x[ok].max() + pad); ax[0, j].set_ylim(y[ok].min() - pad, y[ok].max() + pad)
        ax[0, j].set_xlabel("Sinistro (interpolated) F (mJy)"); ax[0, j].set_ylabel(f"MuSCAT {k.split('-')[1]} F (mJy)")
        ax[0, j].set_title(f"{LBL[f]}: b/F = {r.b1 / r.F_mean * 100:+.1f}%  ({r.n_pairs} nights)"); ax[0, j].legend(fontsize=7)
        # time series zoom before/after
        z = g[(g.MJD > 59280) & (g.MJD < 59680)]
        for s, h in z.groupby(z.scope.str.contains("-ep")):
            col = "k" if s else COL[f]
            ax[1, j].errorbar(h.MJD, h.F, h.Ferr, fmt="o" if not s else "s", ms=2, color=col, alpha=0.25 if s else 0.6,
                              elinewidth=0.4, label=("MuSCAT raw" if s else "Sinistro"))
            if s:
                ax[1, j].errorbar(h.MJD, h.F_ic, h.Ferr_ic, fmt="s", ms=2, color="r", elinewidth=0.4, label="MuSCAT corrected")
        lo, hi = np.percentile(z.F, [1, 99]); ax[1, j].set_ylim(lo - 0.3 * (hi - lo), hi + 0.3 * (hi - lo))
        ax[1, j].set_xlabel("MJD"); ax[1, j].set_ylabel("F (mJy)"); ax[1, j].legend(fontsize=7, markerscale=2)
    fig.suptitle("MuSCAT additive (host-light) offset: flux-flux against Sinistro on matched nights", y=1.0)
    fig.tight_layout(); save(fig, "pytics_10_muscat_intercal")

    # summary of b1 (all scopes) vs colour-term prediction
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    tab["frac"] = tab.b1 / tab.F_mean * 100; tab["frac_err"] = tab.b1_err / tab.F_mean * 100
    scopes = sorted(tab.scope.unique()); xs = {s: i for i, s in enumerate(scopes)}
    for j, f in enumerate(F):
        g = tab[tab["filter"] == f]
        ax[0].errorbar(np.array([xs[s] for s in g.scope]) + (j - 3) * 0.1, g.frac, g.frac_err, fmt="o", ms=4, color=COL[f], label=LBL[f])
    ax[0].axhline(0, color="grey", lw=0.6); ax[0].set_xticks(range(len(scopes)))
    ax[0].set_xticklabels(scopes, rotation=40, ha="right", fontsize=7); ax[0].tick_params(axis="x", which="minor", bottom=False, top=False)
    ax[0].set_ylabel("additive offset b (a≡1) / mean F  (%)"); ax[0].legend(ncol=4, fontsize=7)
    ax[0].set_title("AGN flux offset of each camera vs the Sinistro reference")
    # predicted from colour terms: Δm_k(AGN) relative to the ensemble -> flux fraction
    m = tab.merge(ct, on=["filter", "scope"])
    m["pred_pct"] = (10 ** (-0.4 * m.agn_offset) - 1) * 100      # AGN residual Δm in that camera -> flux %
    for f in F:
        h = m[(m["filter"] == f)]
        isep = h.scope.str.contains("-ep")
        ax[1].errorbar(h.pred_pct[~isep], h.frac[~isep], h.frac_err[~isep], fmt="o", ms=4, color=COL[f], label=LBL[f])
        ax[1].errorbar(h.pred_pct[isep], h.frac[isep], h.frac_err[isep], fmt="s", ms=6, mfc="none", color=COL[f])
    lim = [-3, 3]; ax[1].plot(lim, lim, "k:", lw=0.8); ax[1].set_xlim(lim)
    ax[1].set_xlabel("predicted from star × scope colour slope at AGN colour (%)"); ax[1].set_ylabel("measured b / F (%)")
    ax[1].set_title("are the Sinistro offsets colour terms? (squares: MuSCAT, off-scale ⇒ host)")
    ax[1].legend(ncol=4, fontsize=7)
    fig.tight_layout(); save(fig, "pytics_11_intercal_summary")
    ok = ~m.scope.str.contains("-ep")
    stats["intercal_colour_corr"] = float(np.corrcoef(m.pred_pct[ok], m.frac[ok])[0, 1])
    stats["intercal_muscat"] = tab[tab.scope.str.contains("-ep")][["filter", "scope", "n_pairs", "a", "a_err", "b", "b_err",
                                                                    "b1", "b1_err", "frac", "dmag_const"]].round(4).to_dict("records")
    stats["intercal_sinistro_frac_rms"] = float(tab[~tab.scope.str.contains("-ep")].frac.std())


# ---------------------------------------------------------------- 12 merged light curve
def fig_merged():
    sc_mus = lc.scope.str.contains("-ep")
    fig, ax = plt.subplots(len(F), 1, figsize=(11, 12), sharex=True)
    for a, f in zip(ax, F):
        g = lc[lc.Filter == f]
        for s, h in g.groupby(g.scope.str.contains("-ep")):
            a.errorbar(h.MJD, h.F_ic, h.Ferr_ic, fmt="o", ms=1.6, color=COL[f] if not s else "k", elinewidth=0.4,
                       alpha=0.8, label="MuSCAT (corrected)" if s else "Sinistro")
        a.set_ylabel(f"{LBL[f]} (mJy)")
        lo, hi = np.percentile(g.F_ic, [1, 99]); a.set_ylim(lo - 0.15 * (hi - lo), hi + 0.15 * (hi - lo))
    ax[2].legend(ncol=2, markerscale=3, loc="upper right"); ax[-1].set_xlabel("MJD")
    ax[0].set_title("Mrk 817 — PyTICS merged light curves (absolute AB, MuSCAT host offset removed)")
    fig.tight_layout(); fig.subplots_adjust(hspace=0); save(fig, "pytics_12_merged_lightcurves")
    merged = pd.DataFrame({"mjd_mid": lc.MJD, "filter": lc.Filter, "mag": lc.mag_ic, "mag_err": lc.mag_ic_err, "qc_pass": 1})
    # (lc holds the good epochs only)
    wp.plot_lightcurves(merged, fd, OUT / "pytics_13_webplot_merged", formats=["png"])
    wp.plot_lightcurves(merged, fd, OUT / "pytics_14_webplot_merged_last60d", recent_days=60, formats=["png"])


if __name__ == "__main__":
    t0 = time.time()
    fig_validation(); fig_convergence(); fig_scopes(); fig_epochs(); fig_star_rms(); fig_agn_vs_perframe()
    fig_incremental(); fig_abszp(); ct = fig_scope_colour(); fig_intercal(ct); fig_merged()
    stats["solutions"] = {f: {k: sols[f].meta[k] for k in ("n_stars", "n_scopes", "n_epochs", "n_rows", "loops", "converged", "seconds")}
                          for f in F + ["Y"]}
    json.dump(stats, open(OUT / "pytics_report_stats.json", "w"), indent=1, default=float)
    print("done", round(time.time() - t0), "s")
