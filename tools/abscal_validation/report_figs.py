#!/usr/bin/env python
"""Figures for docs/reports/abscal/ from agn_sed_corrections.py / sed_photometry_check.py outputs.

    PYSYN_CDBS=... python tools/abscal_validation/report_figs.py --sed <work> --out docs/reports/abscal/figures
"""
import sys
from pathlib import Path

import click
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import synlib as S  # noqa: E402

BAND_COL = dict(u="#6250d6", B="#2a78d6", g="#1baf7a", V="#008300", r="#eb6834", i="#e34948", z="#e87ba4")
TGT_COL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6", "#008300", "#e34948"]
INK, INK2, GRID, SHADE = "#0b0b0b", "#52514e", "#e4e3df", "#f0efec"
plt.rcParams.update({"text.usetex": False, "font.size": 8.5, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "lines.linewidth": 1.6,
                     "legend.frameon": False, "xtick.direction": "out", "ytick.direction": "out",
                     "xtick.top": False, "ytick.right": False})
NICE = {"Mrk_817": "Mrk 817", "NGC_4151": "NGC 4151", "fairall_9": "Fairall 9"}
MAIN = ["B", "g", "V", "r", "i"]


def nice(t):
    return NICE.get(t, t.replace("_", " "))


def save(fig, out, name):
    for ext in ("pdf", "png"):
        fig.savefig(out / f"{name}.{ext}", dpi=170, bbox_inches="tight")
    plt.close(fig)


def mean_spec(npz, t):
    g = npz[f"{t}__wave"]; f = npz[f"{t}__flux"]; c = npz[f"{t}__cont"]
    k = np.isfinite(f) & np.isfinite(c)
    return g[k], f[k], c[k], npz[f"{t}__p16"][k], npz[f"{t}__p84"][k], float(npz[f"{t}__z"])


def label_lines(ax, w, f, z, ymax):
    for name, lam in S.LINES_REST.items():
        x = lam * (1 + z)
        if w.min() < x < w.max():
            y = np.interp(x, w, f)
            if y > 0.25 * ymax or name.strip() in ("Hα", "Hβ", "[O III]"):
                ax.annotate(name.strip(), (x, min(y, ymax * 0.98)), xytext=(0, 3), textcoords="offset points",
                            ha="center", va="bottom", fontsize=6.5, color=INK2)


# ------------------------------------------------------------------ filters only
def fig_filters(F, out):
    fig, axs = plt.subplots(7, 1, figsize=(7.2, 8.6), sharex=False)
    for ax, b in zip(axs, S.BANDS):
        lw, lt = F.lco[b]; rw, rt = F.ref[b]
        lo, hi = min(S.span(F.lco[b], 0.02)[0], S.span(F.ref[b], 0.02)[0]) - 150, max(S.span(F.lco[b], 0.02)[1], S.span(F.ref[b], 0.02)[1]) + 150
        ax.plot(lw, lt / lt.max(), color=BAND_COL[b], label=f"LCO {b}{'′' if b in 'ugriz' else ''}")
        ax.plot(rw, rt / rt.max(), color=INK, ls="--", lw=1.2, label=S.REF_LABEL[b])
        g = np.linspace(lo, hi, 2000)
        d = np.interp(g, lw, lt / lt.max(), left=0, right=0) - np.interp(g, rw, rt / rt.max(), left=0, right=0)
        ax.fill_between(g, 0, d, where=d > 0, color=BAND_COL[b], alpha=0.18, lw=0)
        ax.fill_between(g, 0, d, where=d < 0, color=INK2, alpha=0.18, lw=0)
        ax.set_xlim(lo, hi); ax.set_ylim(-0.6, 1.12); ax.set_yticks([0, 0.5, 1])
        ax.legend(loc="lower right", fontsize=7, ncol=2)
        h1 = S.span(F.lco[b], 0.5); h2 = S.span(F.ref[b], 0.5)
        ax.text(0.01, 0.92, f"half-power LCO {h1[0]:.0f}–{h1[1]:.0f} Å; ref {h2[0]:.0f}–{h2[1]:.0f} Å",
                transform=ax.transAxes, fontsize=7, color=INK2, va="top")
    axs[-1].set_xlabel("wavelength (Å)")
    axs[3].set_ylabel("normalised throughput   (shaded: LCO − reference)")
    fig.suptitle("LCO natural passbands vs the reference systems of the Gaia anchors", x=0.02, ha="left", fontsize=10)
    fig.tight_layout()
    save(fig, out, "fig01_filters")


# ------------------------------------------------------------------ per-target spectrum + all filters
def fig_target_overview(F, npz, t, summ, out, n):
    w, f, c, p16, p84, z = mean_spec(npz, t)
    norm = np.median(f[(w / (1 + z) > 5080) & (w / (1 + z) < 5130)])
    fig, (ax, axb) = plt.subplots(2, 1, figsize=(7.4, 5.0), height_ratios=[3, 1.1], sharex=True)
    ax.fill_between(w, p16 / norm, p84 / norm, color=INK2, alpha=0.18, lw=0, label="16–84 % of epochs")
    ax.plot(w, f / norm, color=INK, lw=0.7, label=f"median spectrum ({n} spectra)")
    ax.plot(w, c / norm, color=INK2, lw=0.9, ls=":", label="continuum fit (line-free windows)")
    ymax = np.nanpercentile(f / norm, 99.7) * 1.15
    ax.set_ylim(0, ymax); label_lines(ax, w, f / norm, z, ymax)
    ax.axvspan(4900, 5600, color=SHADE, zorder=0); ax.text(5250, ymax * 0.04, "order overlap", ha="center", fontsize=6.5, color=INK2)
    ax.set_ylabel("F$_\\lambda$ / F$_\\lambda$(5100 Å rest)")
    ax.legend(loc="upper right", fontsize=7)
    for b in S.BANDS:
        lw_, lt = F.lco[b]; rw, rt = F.ref[b]
        axb.plot(lw_, lt / lt.max(), color=BAND_COL[b], lw=1.2)
        axb.plot(rw, rt / rt.max(), color=BAND_COL[b], lw=1.0, ls="--")
        x = np.average(lw_, weights=lt)
        r = summ[(summ.target == t) & (summ.band == b)]
        txt = f"{b}\n{r['dref'].iloc[0] * 1e3:+.0f}" if len(r) else b
        axb.text(x, 1.08, txt, ha="center", va="bottom", fontsize=7, color=INK)
    axb.set_ylim(0, 1.6); axb.set_yticks([0, 1]); axb.set_ylabel("T (norm.)")
    axb.set_xlabel("observed wavelength (Å)   — solid: LCO; dashed: reference (SDSS / Landolt)")
    axb.set_xlim(3000, 10300)
    ax.set_title(f"{nice(t)} (z = {z:.4f}): FLOYDS spectrum and passbands; numbers: true − AVA (mmag)",
                 loc="left", fontsize=9.5)
    fig.tight_layout(h_pad=0.4)
    save(fig, out, f"fig_{t}_overview")


# ------------------------------------------------------------------ per-target band zooms
def fig_target_bands(F, npz, t, summ, out):
    w, f, c, p16, p84, z = mean_spec(npz, t)
    fig, axs = plt.subplots(2, 4, figsize=(7.6, 4.6))
    axs = axs.ravel()
    for ax, b in zip(axs, S.BANDS):
        lw_, lt = F.lco[b]; rw, rt = F.ref[b]
        lo, hi = min(S.span(F.lco[b], 0.02)[0], S.span(F.ref[b], 0.02)[0]) - 150, max(S.span(F.lco[b], 0.02)[1], S.span(F.ref[b], 0.02)[1]) + 150
        k = (w > lo) & (w < hi)
        sc = np.nanmax(f[k]) if k.any() else 1
        if k.any():
            ax.plot(w[k], f[k] / sc, color=INK, lw=0.7)
            ax.plot(w[k], c[k] / sc, color=INK2, lw=0.8, ls=":")
        ax.plot(lw_, lt / lt.max(), color=BAND_COL[b], lw=1.3)
        ax.plot(rw, rt / rt.max(), color=BAND_COL[b], lw=1.0, ls="--")
        g = np.linspace(lo, hi, 1500)
        d = np.interp(g, lw_, lt / lt.max(), left=0, right=0) - np.interp(g, rw, rt / rt.max(), left=0, right=0)
        ax.fill_between(g, 0, np.abs(d), color=BAND_COL[b], alpha=0.15, lw=0)
        if w.min() > lo:
            ax.axvspan(lo, w.min(), color=SHADE, zorder=0)
        if w.max() < hi:
            ax.axvspan(w.max(), hi, color=SHADE, zorder=0)
        r = summ[(summ.target == t) & (summ.band == b)].iloc[0]
        ax.set_title(f"{b}: {r['dref'] * 1e3:+.0f} ± {r['sys_total'] * 1e3:.0f} mmag\n"
                     f"lines {r['linefrac_lco'] * 100:.0f} % LCO, {r['linefrac_ref'] * 100:.0f} % ref", fontsize=7.5, loc="left")
        ax.set_xlim(lo, hi); ax.set_ylim(0, 1.12); ax.set_yticks([])
        ax.tick_params(labelsize=6.5)
    axs[-1].axis("off")
    axs[-1].text(0, 0.9, f"{nice(t)}\nsolid: LCO passband\ndashed: reference passband\nshaded colour: |difference|\n"
                 "black: median spectrum\ndotted: continuum fit\ngrey band: extrapolated\n(u: Seyfert-1 template;\n z: power law)\n\n"
                 "title: true − AVA ± syst.", fontsize=7, va="top", color=INK)
    fig.tight_layout(w_pad=0.6)
    save(fig, out, f"fig_{t}_bands")


# ------------------------------------------------------------------ per-target epochs
def fig_target_epochs(ep, t, out):
    g = ep[(ep.target == t) & (ep.reduction == "ava")].copy()
    g["state"] = np.log10(g["cont5100"] / g["oiii5007"])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 2.9), sharey=True)
    for b in MAIN:
        y = g[f"dref_{b}_nominal"] * 1e3
        a1.plot(g["MJD"], y, "o", ms=4, color=BAND_COL[b], label=b)
        a2.plot(g["state"], y, "o", ms=4, color=BAND_COL[b])
        k = np.isfinite(g["state"]) & np.isfinite(y)
        if k.sum() > 5 and np.ptp(g.loc[k, "state"]) > 0.03:
            p = np.polyfit(g.loc[k, "state"], y[k], 1)
            xs = np.linspace(g.loc[k, "state"].min(), g.loc[k, "state"].max(), 10)
            a2.plot(xs, np.polyval(p, xs), color=BAND_COL[b], lw=1)
    a1.set_xlabel("MJD"); a1.set_ylabel("true − AVA (mmag)")
    a2.set_xlabel("log$_{10}$ [F$_{5100}$ / F([O III])]  (AGN state)")
    a1.legend(ncol=5, fontsize=7, loc="best")
    a1.set_title(f"{nice(t)}: per-spectrum correction", loc="left", fontsize=9)
    fig.tight_layout()
    save(fig, out, f"fig_{t}_epochs")


# ------------------------------------------------------------------ summary across targets
def fig_summary(summ, out):
    tg = list(summ.target.unique())
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.6, 3.2), width_ratios=[2.2, 1])
    x = np.arange(len(MAIN))
    for k, t in enumerate(tg):
        s = summ[summ.target == t].set_index("band").reindex(MAIN)
        xx = x + (k - (len(tg) - 1) / 2) * 0.2
        a1.errorbar(xx, s["dref"] * 1e3, yerr=np.hypot(s["sys_total"], s["dref_sd"]) * 1e3, fmt="o", ms=6,
                    color=TGT_COL[k], label=nice(t), capsize=0, lw=1.4)
        a2.plot(xx, s["dnat"] * 1e3, "o", ms=6, color=TGT_COL[k])
    a1.axhspan(-5, 5, color=GRID, lw=0, zorder=0); a1.axhline(0, color=INK2, lw=0.7)
    a1.set_xticks(x, MAIN); a1.set_ylabel("true − AVA (mmag)")
    a1.set_title("Reference-system (SDSS/Landolt) correction", loc="left", fontsize=9)
    a1.legend(fontsize=7, loc="upper left")
    a2.axhline(0, color=INK2, lw=0.7); a2.set_xticks(x, MAIN)
    a2.set_ylabel("LCO natural − AVA (mmag)")
    a2.set_title("Natural-system shift", loc="left", fontsize=9)
    fig.tight_layout()
    save(fig, out, "fig02_summary")


# ------------------------------------------------------------------ redshift scan with each template
def fig_redshift(npz, targets, F, tr, out):
    zs = np.round(np.arange(0.0, 0.2001, 0.0025), 4)
    fig, axs = plt.subplots(1, len(MAIN), figsize=(7.8, 2.8), sharey=False)
    for k, t in enumerate(targets):
        w, f, c, _, _, z0 = mean_spec(npz, t)
        wr = w / (1 + z0)
        res = {b: [] for b in MAIN}
        for z in zs:
            W, Fx, _ = S.extend(wr * (1 + z), f, z)
            m = F.mags(W, Fx)
            for b in MAIN:
                a, C = tr.loc[b, "a"], tr.loc[b, "C"]
                res[b].append((m[f"ref_{b}"] - m[f"lco_{b}"] - a - C * m["gi"]) * 1e3)
        for ax, b in zip(axs, MAIN):
            ax.plot(zs, res[b], color=TGT_COL[k], lw=1.3, label=nice(t) + " spectrum")
            ax.axvline(z0, color=TGT_COL[k], lw=0.6, ls=":")
    for ax, b in zip(axs, MAIN):
        ax.axhline(0, color=INK2, lw=0.6); ax.set_title(b, loc="left", fontsize=9); ax.set_xlabel("z")
        ax.tick_params(labelsize=7)
    axs[0].set_ylabel("true − AVA (mmag)")
    axs[0].legend(fontsize=6.5, loc="upper left", bbox_to_anchor=(0, -0.28), ncol=3)
    fig.suptitle("Each spectrum moved in redshift (AGN colour from the moved spectrum; dotted: true z)",
                 x=0.02, ha="left", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    save(fig, out, "fig03_redshift")


# ------------------------------------------------------------------ colour-term tuning
def fig_tuning(sed, out):
    g = pd.read_csv(sed / "sed_corr_tuning_grid.csv")
    tr = pd.read_csv(sed / "sed_corr_transform.csv")
    nom = tr[tr.variant == "nominal"].set_index("band")
    fig, axs = plt.subplots(1, 6, figsize=(7.8, 2.4), sharex=True)
    for ax, b in zip(axs, ["B", "g", "V", "r", "i", "z"]):
        ax.plot(g["shift_A"], g[f"C_{b}"], color=BAND_COL[b])
        ce, cee = nom.loc[b, "C_emp"], nom.loc[b, "C_emp_err"]
        ax.axhspan(ce - cee, ce + cee, color=GRID, lw=0); ax.axhline(ce, color=INK, lw=0.8)
        sh = tr[(tr.variant == "tuned")].set_index("band").loc[b, "shift_A"]
        ax.axvline(sh, color=INK2, ls=":", lw=0.8)
        ax.set_title(f"{b}: {sh:+.0f} Å", loc="left", fontsize=8); ax.tick_params(labelsize=6.5)
        ax.set_xlabel("LCO shift (Å)", fontsize=7)
    axs[0].set_ylabel("stellar colour term C")
    fig.suptitle("Synthetic C vs LCO-curve shift; black line ± grey: empirical C (Mrk 817 field)", x=0.02, ha="left", fontsize=9)
    fig.tight_layout()
    save(fig, out, "fig04_tuning")


# ------------------------------------------------------------------ photometry vs spectra colours
def fig_phot_check(sed, out):
    p = sed / "sed_photometry_check.csv"
    if not p.exists():
        return
    r = pd.read_csv(p)
    s = r.groupby("colour")[["obs", "pred_ava", "true_ref"]].median()
    order = [c for c in ["B-g", "g-V", "V-r", "g-r", "r-i", "i-z"] if c in s.index]
    s = s.loc[order]
    x = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(5.4, 2.9))
    ax.plot(x - 0.15, (s["pred_ava"] - s["obs"]) * 1e3, "o", ms=7, color=TGT_COL[0], label="predicted AVA − observed AVA")
    ax.plot(x + 0.15, (s["true_ref"] - s["obs"]) * 1e3, "s", ms=7, color=TGT_COL[1], label="true SDSS/Landolt − observed AVA")
    ax.axhline(0, color=INK2, lw=0.7)
    for xi, c in zip(x, order):
        if c in ("V-r", "g-r"):
            ax.axvspan(xi - 0.4, xi + 0.4, color=SHADE, zorder=0)
    ax.set_xticks(x, order); ax.set_ylabel("colour difference (mmag)")
    ax.legend(fontsize=7, loc="lower left")
    ax.set_title("Mrk 817, 13 Aug 2026: colours from spectra vs same-night photometry", loc="left", fontsize=9)
    ax.text(0.99, 0.97, "shaded: g or V paired with r\n(blue vs red part of the spectrum)", transform=ax.transAxes, ha="right", va="top", fontsize=6.5, color=INK2)
    fig.tight_layout()
    save(fig, out, "fig05_photometry_check")


# ------------------------------------------------------------------ stars vs independent catalogues
def fig_stars(ext, out):
    e = pd.read_csv(ext / "ps1_apass_offsets.csv")
    g = e[e["who"] == "GSPC"].set_index(["filter", "cat"])["offset_mmag"]
    e = e[(e["who"] == "AVA") & e["cat"].isin(["sdss", "ps1"])]
    order = ["up", "gp", "rp", "ip", "zs"]
    fig, ax = plt.subplots(figsize=(5.0, 3.0))
    for k, (cat, c, lab) in enumerate([("sdss", TGT_COL[0], "AVA − SDSS DR16"), ("ps1", TGT_COL[1], "AVA − PS1 − (GSPC − PS1)")]):
        s = e[e["cat"] == cat].set_index("filter").reindex(order)
        y = s["offset_mmag"].copy()
        if cat == "ps1":
            y = y - g.xs("ps1", level="cat").reindex(order)
        ax.errorbar(np.arange(len(order)) + (k - 0.5) * 0.18, y, yerr=s["err_mmag"], fmt="o", ms=7, color=c,
                    capsize=0, lw=1.5, label=lab)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_xticks(range(len(order)), ["u", "g", "r", "i", "z"]); ax.set_ylabel("offset at AGN g−i (mmag)")
    ax.legend(fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    ax.set_title("Mrk 817 field stars: AVA vs independent catalogues", loc="left", fontsize=9)
    save(fig, out, "fig06_stars")


@click.command()
@click.option("--ext", type=click.Path(file_okay=False, path_type=Path), default=None,
              help="abscal_ps1_apass.py output folder (star comparison figure)")
@click.option("--sed", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--out", type=click.Path(file_okay=False, path_type=Path), required=True)
def main(ext, sed, out):
    out.mkdir(parents=True, exist_ok=True)
    F = S.Filters()
    npz = np.load(sed / "sed_corr_mean_spectra.npz")
    ep = pd.read_csv(sed / "sed_corr_epochs.csv")
    summ = pd.read_csv(sed / "sed_corr_summary.csv")
    tr = pd.read_csv(sed / "sed_corr_transform.csv")
    tr = tr[tr.variant == "nominal"].set_index("band")
    targets = list(summ.target.unique())
    fig_filters(F, out)
    fig_summary(summ, out)
    fig_redshift(npz, targets, F, tr, out)
    fig_tuning(sed, out)
    fig_phot_check(sed, out)
    for t in targets:
        n = int(((ep.target == t) & (ep.reduction == "ava")).sum())
        fig_target_overview(F, npz, t, summ, out, n)
        fig_target_bands(F, npz, t, summ, out)
        fig_target_epochs(ep, t, out)
    if ext:
        fig_stars(ext, out)
    print("figures in", out)


if __name__ == "__main__":
    main()
