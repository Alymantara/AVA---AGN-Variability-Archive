#!/usr/bin/env python
"""Figures for the point-to-point (pair) test of every AGN, from pair_scatter_all.py / pair_scatter_stars.py
outputs (+ the held-out error-model table of the analysis).

    python tools/pytics_validation/pair_scatter_figs.py --work <work> --out docs/figures/pytics_errors
"""
from pathlib import Path

import click
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

ORDER = ["u", "B", "g", "V", "r", "i", "z", "Y"]
BCOL = dict(u="#6250d6", B="#2a78d6", g="#1baf7a", V="#008300", r="#eb6834", i="#e34948", z="#e87ba4", Y="#eda100")
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"text.usetex": False, "font.size": 8.5, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "lines.linewidth": 1.6,
                     "legend.frameon": False, "xtick.direction": "out", "ytick.direction": "out",
                     "xtick.top": False, "ytick.right": False})


def rob(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return 1.4826 * np.median(np.abs(x - np.median(x))) if len(x) else np.nan


def save(fig, out, name):
    for ext in ("pdf", "png"):
        fig.savefig(out / f"{name}.{ext}", dpi=170, bbox_inches="tight")
    plt.close(fig)


def binned(x, z, edges, minn=30):
    b = pd.cut(x, edges)
    g = pd.DataFrame({"b": b, "z": z}).groupby("b", observed=True)
    r = g.z.agg([("n", "size"), ("sig", rob), ("f3", lambda v: np.mean(np.abs(v) > 3))])
    r = r[r.n >= minn]
    r["mid"] = [iv.mid for iv in r.index]
    return r


@click.command()
@click.option("--work", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--out", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--bright", default=-12.0, show_default=True, help="instrumental mag: brighter = 'bright'")
def main(work, out, bright):
    out.mkdir(parents=True, exist_ok=True)
    S = pd.read_parquet(work / "pairs_same.parquet")
    X = pd.read_parquet(work / "pairs_cross.parquet")
    ST = pd.read_parquet(work / "pairs_stars.parquet")
    H = pd.read_csv(work / "heldout_model.csv") if (work / "heldout_model.csv").exists() else None

    # ---- 1. distributions -------------------------------------------------------------------
    fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.0))
    x = np.linspace(-8, 8, 400)
    bins = np.linspace(-8, 8, 81)
    for ax, (data, lab) in zip(axs, [(S, f"AGN, {len(S):,} back-to-back pairs"), (ST, f"comparison stars, {len(ST)/1e6:.1f} M pairs")]):
        for col, c, name in [("z_phot", C2, "photometric error"), ("z_rand", C1, "PyTICS random error")] + \
                            ([("z_model", C3, "fitted error model")] if "z_model" in data else []):
            z = data[col].to_numpy(float)
            z = z[np.isfinite(z)]
            ax.hist(np.clip(z, -7.99, 7.99), bins=bins, density=True, histtype="step", color=c, lw=1.5,
                    label=f"{name} (σ_rob {rob(z):.2f}, |z|>3 {100 * np.mean(np.abs(z) > 3):.1f} %)")
        ax.plot(x, stats.norm.pdf(x), color=INK, lw=1, ls="--", label="N(0, 1) (|z|>3: 0.27 %)")
        ax.set_yscale("log"); ax.set_ylim(1e-5, 30); ax.set_xlim(-8, 8)
        ax.set_xlabel(r"z = $\Delta m\,/\,\sqrt{\sigma_1^2+\sigma_2^2}$"); ax.set_title(lab, loc="left", fontsize=9)
        ax.legend(fontsize=6.3, loc="upper left", handlelength=1.5, borderaxespad=0.2)
    axs[0].set_ylabel("density")
    fig.suptitle("Pairs of epochs < 1 h apart on the same camera: normalised differences", x=0.02, ha="left", fontsize=10)
    fig.tight_layout()
    save(fig, out, "pair_01_distributions")

    # ---- 2. Q-Q per band ---------------------------------------------------------------------
    fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.3), sharey=True)
    q = np.linspace(0.0005, 0.9995, 400)
    gq = stats.norm.ppf(q)
    for ax, col, title in [(axs[0], "z_rand", "PyTICS random error"), (axs[1], "z_model", "fitted error model")]:
        for b in ORDER:
            z = S.loc[S.band == b, col].to_numpy(float)
            z = z[np.isfinite(z)]
            if len(z) < 200:
                continue
            ax.plot(gq, np.quantile(z, q), color=BCOL[b], lw=1.3, label=b)
        ax.plot([-4, 4], [-4, 4], color=INK, lw=1, ls="--")
        ax.set_xlim(-3.6, 3.6); ax.set_ylim(-8, 8)
        ax.set_xlabel("Gaussian quantile"); ax.set_title(f"AGN pairs, {title}", loc="left", fontsize=9)
    axs[0].set_ylabel("quantile of z"); axs[0].legend(ncol=4, fontsize=7, loc="upper left")
    fig.tight_layout()
    save(fig, out, "pair_02_qq")

    # ---- 3. shape: sigma_z vs predicted error and vs rms_t, AGN and stars --------------------
    fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.1))
    e_edges = np.r_[0.002, 0.003, 0.004, 0.005, 0.006, 0.008, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.07, 0.1]
    for data, lab, c, mk in [(S, "AGN, PyTICS random", C1, "o"), (ST, "stars, PyTICS random", C2, "s")]:
        r = binned(data.e_rand / np.sqrt(2), data.z_rand, e_edges)
        axs[0].plot(r.mid * 1e3, r.sig, marker=mk, ms=4, color=c, label=lab)
    r = binned(S.e_model / np.sqrt(2), S.z_model, e_edges)
    axs[0].plot(r.mid * 1e3, r.sig, marker="^", ms=4, color=C3, label="AGN, fitted model")
    r = binned(ST.e_phot / np.sqrt(2), ST.z_phot, e_edges)
    axs[0].plot(r.mid * 1e3, r.sig, marker="s", ms=4, color=C2, ls=":", label="stars, photometric only")
    axs[0].axhline(1, color=INK2, lw=0.8)
    axs[0].set_xscale("log"); axs[0].set_xlabel("quoted error per epoch (mmag)"); axs[0].set_ylabel("robust σ of z")
    axs[0].legend(fontsize=6.5); axs[0].set_title("Error bars vs observed scatter", loc="left", fontsize=9)
    t_edges = np.r_[0, 0.001, 0.002, 0.003, 0.004, 0.006, 0.008, 0.012, 0.02, 0.03, 0.05, 0.1]
    for data, lab, c, mk in [(S, "AGN", C1, "o"), (ST, "stars", C2, "s")]:
        r = binned(data.rms_t, data.z_rand, t_edges)
        axs[1].plot(r.mid * 1e3, r.sig, marker=mk, ms=4, color=c, label=lab)
    axs[1].axhline(1, color=INK2, lw=0.8)
    axs[1].set_xscale("log"); axs[1].set_xlabel("rms_t, comparison-star scatter of the epoch (mmag)")
    axs[1].legend(fontsize=7); axs[1].set_title("rms_t is over-counted", loc="left", fontsize=9)
    fig.tight_layout()
    save(fig, out, "pair_03_shape")

    # ---- 4. brightness on the detector -----------------------------------------------------
    fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.0))
    m_edges = np.r_[-14, -13, -12.5, -12, -11.5, -11, -10.5, -10, -9, -8, -7, -6, -4]
    for data, lab, c, mk in [(S, "AGN", C1, "o"), (ST, "comparison stars", C2, "s")]:
        if "mag_inst" not in data:
            continue
        r = binned(data.mag_inst, data.z_rand, m_edges)
        axs[0].plot(r.mid, r.sig, marker=mk, ms=4, color=c, label=lab)
        axs[1].plot(r.mid, 100 * r.f3, marker=mk, ms=4, color=c, label=lab)
    for ax in axs:
        ax.axvline(bright, color=INK2, lw=0.8, ls=":"); ax.invert_xaxis()
        ax.set_xlabel("instrumental magnitude (brighter →)")
    axs[0].axhline(1, color=INK2, lw=0.8); axs[0].set_ylabel("robust σ of z (PyTICS random)")
    axs[1].axhline(0.27, color=INK2, lw=0.8); axs[1].set_ylabel("% of pairs with |z| > 3"); axs[1].set_yscale("log")
    axs[0].legend(fontsize=7); axs[0].set_title("Bright sources: errors too small, heavy tails", loc="left", fontsize=9)
    fig.tight_layout()
    save(fig, out, "pair_04_brightness")

    # ---- 5. per AGN ----------------------------------------------------------------------
    g = S.groupby("target").agg(n=("z_rand", "size"), rand=("z_rand", rob), model=("z_model", rob),
                                f3=("z_rand", lambda v: 100 * np.mean(np.abs(v) > 3)))
    g = g[g.n >= 100].sort_values("rand")
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    xx = np.arange(len(g))
    ax.plot(xx, g.rand, "o", ms=5, color=C1, label="PyTICS random error")
    ax.plot(xx, g.model, "^", ms=5, color=C3, label="fitted error model")
    ax.axhline(1, color=INK2, lw=0.8)
    ax.set_xticks(xx, [t.replace("_", " ") for t in g.index], rotation=70, ha="right", fontsize=6.5)
    ax.set_ylabel("robust σ of z (all bands)"); ax.legend(fontsize=7, loc="upper left")
    ax.set_title(f"Back-to-back consistency per AGN ({len(g)} AGN with ≥ 100 pairs)", loc="left", fontsize=9)
    fig.tight_layout()
    save(fig, out, "pair_05_per_agn")

    # ---- 6. cameras and cross-camera -----------------------------------------------------
    fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.0))
    fams = [f for f in ["fa", "fl", "ep", "kb", "fs"] if (S.fam == f).sum() > 100]
    names = dict(fa="Sinistro fa", fl="Sinistro fl", ep="MuSCAT", kb="SBIG", fs="Spectral")
    for k, f in enumerate(fams):
        zz = S.loc[S.fam == f, "z_rand"]
        axs[0].bar(k - 0.18, rob(zz), width=0.34, color=C1, label="robust σ" if k == 0 else None)
        axs[0].bar(k + 0.18, 100 * np.mean(np.abs(zz) > 3) / 10, width=0.34, color=C2, label="% |z|>3 ÷ 10" if k == 0 else None)
    axs[0].axhline(1, color=INK2, lw=0.8)
    axs[0].set_xticks(range(len(fams)), [names[f] for f in fams], fontsize=7)
    axs[0].legend(fontsize=7); axs[0].set_title("Back-to-back, by camera", loc="left", fontsize=9)
    X["dt_h"] = X.dt_d * 24
    r = binned(X.dt_h, X.z_total, np.r_[0, 0.5, 1, 2, 3, 4, 6], minn=50)
    axs[1].plot(r.mid, r.sig, "o-", ms=5, color=C1, label="different cameras, total error")
    r2 = binned(S.dt_min / 60, S.z_rand, np.r_[0, 0.1, 0.25, 0.5, 1], minn=50)
    axs[1].plot(r2.mid, r2.sig, "s-", ms=4, color=C3, label="same camera, random error")
    axs[1].axhline(1, color=INK2, lw=0.8)
    axs[1].set_xlabel("time between the two epochs (h)"); axs[1].set_ylabel("robust σ of z")
    axs[1].legend(fontsize=7); axs[1].set_title("Same night: calibration + AGN variability", loc="left", fontsize=9)
    fig.tight_layout()
    save(fig, out, "pair_06_cameras")
    # ---- 7. the error model: floor (s0), photometric scale (k), rms_t fraction (beta) -------------------
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ava.photometry import errors as ER
    fa = S[(S.fam.isin(["fa", "fl"])) & (S.mag_inst > -11)].copy()          # Sinistro, below the bright regime
    fa["p"] = fa.e_phot / np.sqrt(2)
    P = pd.DataFrame({"p1": fa.p, "p2": fa.p, "t1": fa.rms_t, "t2": fa.rms_t, "dm": fa.dm})
    th = ER.fit_random(P)
    fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.3))
    low = fa[fa.rms_t < 0.001]
    pe = np.r_[0.0015, 0.002, 0.0025, 0.003, 0.004, 0.005, 0.006, 0.008, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05]
    r = pd.DataFrame({"b": pd.cut(low.p, pe), "dm": low.dm}).groupby("b", observed=True).dm.agg([("n", "size"), ("s", rob)])
    r = r[r.n >= 40]
    mid = np.array([iv.mid for iv in r.index])
    axs[0].plot(mid * 1e3, r.s / np.sqrt(2) * 1e3, "o", ms=5, color=INK, label="observed (pairs, rms_t < 1 mmag)")
    xx = np.geomspace(1.2e-3, 0.06, 100)
    axs[0].plot(xx * 1e3, xx * 1e3, color=C2, lw=1.4, ls="--", label="PyTICS: σ_phot (rms_t ≈ 0)")
    axs[0].plot(xx * 1e3, np.sqrt((th["k"] * xx) ** 2 + th["s0"] ** 2) * 1e3, color=C3, lw=2,
                label=f"model: √((k σ_phot)² + s0²), k = {th['k']:.2f}")
    axs[0].axhline(th["s0"] * 1e3, color=C1, lw=1.2, ls=":")
    axs[0].annotate(f"floor s0 = {th['s0'] * 1e3:.1f} mmag", (1.3, th["s0"] * 1e3), xytext=(0, 5),
                    textcoords="offset points", color=C1, fontsize=7.5)
    axs[0].set_xscale("log"); axs[0].set_yscale("log")
    axs[0].set_xlabel("SExtractor error σ_phot per epoch (mmag)"); axs[0].set_ylabel("per-epoch scatter (mmag)")
    axs[0].legend(fontsize=6.8, loc="upper left"); axs[0].set_title("Photometric scale and floor", loc="left", fontsize=9)
    mid_p = fa[(fa.p > 0.004) & (fa.p < 0.008)]
    te = np.r_[0, 0.001, 0.002, 0.003, 0.004, 0.006, 0.008, 0.012, 0.02, 0.03, 0.05]
    r = pd.DataFrame({"b": pd.cut(mid_p.rms_t, te), "dm": mid_p.dm}).groupby("b", observed=True).dm.agg([("n", "size"), ("s", rob)])
    r = r[r.n >= 40]
    mid = np.array([iv.mid for iv in r.index])
    p0 = float(mid_p.p.median())
    axs[1].plot(mid * 1e3, r.s / np.sqrt(2) * 1e3, "o", ms=5, color=INK, label=f"observed (σ_phot ≈ {p0 * 1e3:.1f} mmag)")
    tt = np.linspace(0, 0.05, 100)
    axs[1].plot(tt * 1e3, np.sqrt(p0 ** 2 + tt ** 2) * 1e3, color=C2, lw=1.4, ls="--", label="PyTICS: √(σ_phot² + rms_t²)")
    axs[1].plot(tt * 1e3, np.sqrt((th["k"] * p0) ** 2 + (th["beta"] * tt) ** 2 + th["s0"] ** 2) * 1e3, color=C3, lw=2,
                label=f"model: + (β rms_t)², β = {th['beta']:.2f}")
    axs[1].set_xlabel("rms_t of the epoch (mmag)"); axs[1].set_ylabel("per-epoch scatter (mmag)")
    axs[1].legend(fontsize=6.8, loc="upper left"); axs[1].set_title("Only a fraction of rms_t applies", loc="left", fontsize=9)
    fig.suptitle("Error model σ² = (k σ_phot)² + (β rms_t)² + s0², fitted to Sinistro back-to-back AGN pairs (all AGN)",
                 x=0.02, ha="left", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    save(fig, out, "pair_07_error_model")
    pd.Series(th).to_csv(out / "pair_07_error_model_params.csv")

    # ---- 8. peak counts / saturation (Mrk 817; needs peak_pairs.parquet from the legacy-catalogue test) -------
    pp = work / "peak_pairs.parquet"
    if pp.exists():
        K = pd.read_parquet(pp)
        K["zm"] = K.dm / np.sqrt((th["k"] * K.p1) ** 2 + (th["beta"] * K.t1) ** 2 + th["s0"] ** 2
                                 + (th["k"] * K.p2) ** 2 + (th["beta"] * K.t2) ** 2 + th["s0"] ** 2)
        edges = np.r_[0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.0))
        for fam, mk, name in [("fa", "o", "Sinistro"), ("ep", "s", "MuSCAT")]:
            x = K[K.fam == fam]
            for col, c, lab in [("z", C1, "PyTICS random"), ("zm", C3, "fitted model")]:
                r = binned(x.frac, x[col], edges, minn=30)
                axs[0].plot(r.mid, r.sig, marker=mk, ms=4, color=c, ls="-" if fam == "fa" else ":", label=f"{name}, {lab}")
                if fam == "fa":     # MuSCAT: too few bright pairs for tail fractions (zeros)
                    axs[1].plot(r.mid, 100 * r.f3, marker=mk, ms=4, color=c, label=f"{name}, {lab}")
        for ax in axs:
            ax.axvline(0.8, color=INK2, lw=0.8, ls="--")
            ax.set_xlabel("peak counts / saturation level")
        axs[0].axhline(1, color=INK2, lw=0.8); axs[0].set_ylabel("robust σ of z")
        axs[1].axhline(0.27, color=INK2, lw=0.8); axs[1].set_ylabel("% of pairs with |z| > 3"); axs[1].set_yscale("log")
        axs[0].legend(fontsize=6.3, loc="lower left")
        axs[0].set_title("Star pairs vs peak counts (Mrk 817)", loc="left", fontsize=9)
        axs[1].text(0.78, 0.04, "AGN cut 0.8", transform=axs[1].get_xaxis_transform(), fontsize=7, color=INK2,
                    ha="right", va="bottom")
        axs[1].set_title("Sinistro: tails", loc="left", fontsize=9)
        fig.tight_layout()
        save(fig, out, "pair_08_peak")
    # ---- 9. Sinistro: the floor, and the model works ---------------------------------------------------
    SS = ST[ST.fam.isin(["fa", "fl"])].copy()
    SS["p"] = SS.e_phot / np.sqrt(2)
    SS["dm"] = SS.z_phot * SS.e_phot
    SA = S[S.fam.isin(["fa", "fl"])].copy()
    SA["p"] = SA.e_phot / np.sqrt(2)
    fig, axs = plt.subplots(1, 2, figsize=(7.6, 3.4))
    pe = np.geomspace(3e-4, 0.05, 20)
    for data, lab, c, mk, tmax in [(SS, "comparison stars (rms_t < 1.5 mmag)", C2, "s", 0.0015),
                                   (SA, "AGN (rms_t < 1.5 mmag)", C1, "o", 0.0015)]:
        q = data[data.rms_t < tmax]
        r = pd.DataFrame({"b": pd.cut(q.p, pe), "dm": q.dm, "p": q.p}).groupby("b", observed=True).agg(
            n=("dm", "size"), obs=("dm", lambda v: rob(v) / np.sqrt(2)), p=("p", "median"))
        r = r[r.n >= 50]
        axs[0].plot(r.p * 1e3, r.obs * 1e3, marker=mk, ms=4, ls="none", color=c, label=lab)
    xx = np.geomspace(3e-4, 0.05, 200)
    axs[0].plot(xx * 1e3, xx * 1e3, color=INK2, lw=1, ls="--", label="photometric error alone")
    axs[0].plot(xx * 1e3, np.sqrt((th["k"] * xx) ** 2 + th["s0"] ** 2) * 1e3, color=C3, lw=2,
                label=f"model: k = {th['k']:.2f}, floor s0 = {th['s0'] * 1e3:.1f} mmag")
    axs[0].axhline(th["s0"] * 1e3, color=C3, lw=1, ls=":")
    axs[0].set_xscale("log"); axs[0].set_yscale("log")
    axs[0].set_xlabel("photometric error per epoch (mmag)"); axs[0].set_ylabel("observed scatter per epoch (mmag)")
    axs[0].legend(fontsize=6.3, loc="upper left"); axs[0].set_title("Sinistro: a floor of ~1 mmag", loc="left", fontsize=9)
    # right: z with the model errors, Sinistro, below the bright regime
    SS["zm"] = SS.dm / np.sqrt(2 * ((th["k"] * SS.p) ** 2 + (th["beta"] * SS.rms_t) ** 2 + th["s0"] ** 2))
    bins = np.linspace(-6, 6, 61)
    xg = np.linspace(-6, 6, 300)
    for z, lab, c in [(SA.loc[SA.mag_inst > -11, "z_model"], "AGN", C1), (SS.loc[SS.mag_inst > -11, "zm"], "comparison stars", C2)]:
        z = z[np.isfinite(z)]
        axs[1].hist(np.clip(z, -5.99, 5.99), bins=bins, density=True, histtype="step", color=c, lw=1.5,
                    label=f"{lab}: σ_rob {rob(z):.2f}, |z|>3 {100 * np.mean(np.abs(z) > 3):.1f} %")
    axs[1].plot(xg, stats.norm.pdf(xg), color=INK, lw=1, ls="--", label="N(0, 1): |z|>3 0.27 %")
    axs[1].set_yscale("log"); axs[1].set_ylim(1e-5, 30); axs[1].set_xlim(-6, 6)
    axs[1].set_xlabel(r"z = $\Delta m\,/\,\sqrt{\sigma_1^2+\sigma_2^2}$, model errors")
    axs[1].legend(fontsize=6.3, loc="upper left")
    axs[1].set_title("Sinistro, instrumental mag > -11", loc="left", fontsize=9)
    fig.tight_layout()
    save(fig, out, "pair_09_sinistro_floor")

    # ---- 10. is the floor epoch dependent? bright Sinistro stars in quiet frames, s0 per condition -------
    import sqlite3
    from scipy.optimize import brentq

    from ava.config import cfg
    Bq = SS[(SS.rms_t < 0.0015) & (SS.p < 0.002)].copy()
    dbp = cfg.archive_root / "frame_qc.sqlite"
    if "frame" in Bq and dbp.exists():
        qc = pd.read_sql("select frame, fwhm_arcsec, airmass, exptime from frame_qc",
                         sqlite3.connect(f"file:{dbp}?mode=ro", uri=True))
        Bq = Bq.merge(qc, on="frame", how="left")
    Bq["year"] = pd.to_datetime(Bq.MJD - 40587, unit="D").dt.year if "MJD" in Bq else np.nan

    def s0_of(g):
        if len(g) < 500:
            return np.nan
        f = lambda v: rob(g.dm / np.sqrt(2 * ((th["k"] * g.p) ** 2 + v ** 2))) - 1  # noqa: E731
        return 0.0 if f(0) <= 0 else brentq(f, 0, 0.02)

    panels = [("exptime", np.r_[0, 15, 30, 45, 60, 120, 300], "exposure time (s)"),
              ("airmass", np.r_[1, 1.1, 1.2, 1.3, 1.45, 1.6, 2], "airmass"),
              ("fwhm_arcsec", np.r_[0, 1.5, 2, 2.5, 3, 4], "seeing FWHM (arcsec)"),
              ("year", None, "year")]
    fig, axs = plt.subplots(1, 4, figsize=(7.8, 2.6), sharey=True)
    for ax, (col, edges, lab) in zip(axs, panels):
        if col not in Bq or Bq[col].notna().sum() < 1000:
            ax.set_visible(False); continue
        key = Bq[col] if edges is None else pd.cut(Bq[col], edges)
        r = [((k.mid if hasattr(k, "mid") else k), s0_of(g), len(g)) for k, g in Bq.groupby(key, observed=True)]
        r = [x for x in r if np.isfinite(x[1])]
        ax.plot([x[0] for x in r], [1e3 * x[1] for x in r], "o-", ms=4, color=C1)
        ax.axhline(th["s0"] * 1e3, color=C3, lw=1, ls=":")
        ax.set_xlabel(lab, fontsize=8); ax.tick_params(labelsize=7)
        if col == "year":
            from matplotlib.ticker import MaxNLocator
            ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=4))
    axs[0].set_ylabel("floor s0 (mmag)")
    axs[0].text(0.03, 0.04, "dotted: constant s0 of the model", transform=axs[0].transAxes, fontsize=6.5, color=C3)
    fig.suptitle("The floor follows the conditions (bright Sinistro stars, quiet frames)", x=0.02, ha="left", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    save(fig, out, "pair_10_floor_conditions")
    print("figures in", out)


if __name__ == "__main__":
    main()
