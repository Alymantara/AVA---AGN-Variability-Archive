#!/usr/bin/env python
"""
Worked example of the ``apass_model`` reference catalogue (SED fit diagnostics).

For one target this

1. loads the production (GSPC) ``reference_stars.csv`` + ``_meta.yaml``;
2. loads, or builds once and caches, the ``apass_model`` catalogue for the same
   field (``reference_stars_apass_model.csv`` + ``_meta.yaml`` next to it) with
   :func:`ava.photometry.reference.build_apass_model_catalog` and the settings
   in ``photometry.reference`` — the GSPC files only hold the final LCO
   magnitudes, not the APASS photometry or the fit;
3. plots the SED fit of a few representative stars (cool, solar, hottest, bad fit):
   APASS B g V r i, the best-fit model, the synthetic LCO magnitudes and the
   GSPC values of the same Gaia source;
4. plots a summary: fit_redchi, Teff (fit vs Gaia GSP-Phot), u before/after the
   GSPC anchor, and model - GSPC in every band;
5. writes ``docs/figures/reference_sed_example.pdf`` (page 1 = stars,
   page 2 = summary) and a ``.tex`` snippet to ``\\input{}`` from ``docs/``.

The model "SED" is the atmosphere grid's band-averaged f_lambda (the
spectra behind ``ava_atmo_models.csv`` are not stored with AVA), so the model is
drawn at the filter wavelengths only.

    python tools/reference_sed_example.py                 # Fairall 9
    python tools/reference_sed_example.py --target Mrk_817 --refresh
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ava.config import cfg  # noqa: E402
from ava.photometry import reference as ref  # noqa: E402

GSPC_CAT, GSPC_META = "reference_stars.csv", "reference_stars_meta.yaml"
APM_CAT, APM_META = "reference_stars_apass_model.csv", "reference_stars_apass_model_meta.yaml"
FIG_DIR = ROOT / "docs" / "figures"
STEM = "reference_sed_example"
SDSS_U_AB = -0.04   # u_AB = u_SDSS - 0.04 (as in anchor_u)

# One colour per role, fixed across both pages.
C_APASS, C_MODEL, C_LCO, C_GSPC, C_RAW = "#1f4e79", "#7f7f7f", "#c0392b", "#2e8b57", "#e69f00"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def phot_dir(target: str) -> Path:
    """Production photometry dir if present, else the local test archive."""
    d = cfg.phot_dir(target)
    if (d / GSPC_CAT).exists():
        return d
    local = ROOT / "data" / "test_archive" / "photometry" / target
    if (local / GSPC_CAT).exists():
        return local
    raise FileNotFoundError(f"No {GSPC_CAT} for {target!r} in {d} or {local}")


def _plain(obj):
    return json.loads(json.dumps(obj, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def build_apass_model(target: str, out_dir: Path) -> None:
    """Run the fallback builder once with the pipeline's settings and cache it."""
    from ava.database.query import field_radius_arcmin

    entry = cfg.target_by_data_id(target)
    if entry is None:
        raise ValueError(f"{target!r} is not a known data_id")
    rc = cfg.photometry.reference
    agn_ra, agn_dec = cfg.agn_position(entry)
    radius = float(rc.radius_arcmin)
    if entry.get("pointings"):
        radius = field_radius_arcmin(entry, radius)
        centre = (agn_ra, agn_dec)
    else:
        centre = (entry["ra_deg"], entry["dec_deg"])
    stars, meta = ref.build_apass_model_catalog(
        *centre, agn_ra=agn_ra, agn_dec=agn_dec,
        apass_source=rc.apass_source, radius_arcmin=radius,
        grid_path=cfg._resolve(rc.atmosphere_grid), filters_dir=cfg._resolve(rc.lco_filters),
        apass_url=rc.apass_url, vizier_server=list(rc.vizier_servers),
        use_gaia=bool(rc.gaia), dust_scale_height_pc=float(rc.dust_scale_height_pc),
        min_parallax_snr=float(rc.min_parallax_snr), gaia_match_arcsec=float(rc.gaia_match_arcsec),
        n_draws=int(rc.n_draws), seed=int(rc.random_seed),
        u_anchor=bool(rc.get("u_anchor", True)),
        u_anchor_min_stars=int(rc.get("u_anchor_min_stars", 10)),
    )
    meta.update(target=target, built_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                note="cached by tools/reference_sed_example.py (diagnostics only)")
    stars.to_csv(out_dir / APM_CAT, index=False)
    (out_dir / APM_META).write_text(yaml.safe_dump(_plain(meta), sort_keys=False))


def load(target: str, refresh: bool):
    d = phot_dir(target)
    if refresh or not (d / APM_CAT).exists():
        click.echo(f"Building apass_model catalogue for {target} (VizieR + IRSA queries) ...")
        build_apass_model(target, d)
    gspc = pd.read_csv(d / GSPC_CAT)
    gmeta = yaml.safe_load((d / GSPC_META).read_text())
    apm = pd.read_csv(d / APM_CAT)
    ameta = yaml.safe_load((d / APM_META).read_text())
    # GSPC catalogue values (already mapped to LCO bands, AB) by Gaia source_id.
    g = gspc[["star_id", "quality_ok"] + [f"lco_{b}" for b in ref.LCO_BANDS]
             + [f"lco_{b}_err" for b in ref.LCO_BANDS]]
    g = g.rename(columns={c: c.replace("lco_", "gspcref_") for c in g.columns if c.startswith("lco_")}
                 | {"quality_ok": "gspcref_quality_ok"})
    apm = apm.merge(g, on="star_id", how="left")
    return d, apm, ameta, gmeta


# ---------------------------------------------------------------------------
# Model reconstruction
# ---------------------------------------------------------------------------

def model_mags(star, grid, w, system, bands):
    """AB mags of the best-fit reddened model (fit_norm, fit_teff, ebv)."""
    red = ref.unred(w, np.ones_like(w), -float(star["ebv"]))
    f_lam = 10 ** star["fit_norm"] * grid(star["fit_teff"], system, bands) * red
    return -2.5 * np.log10(f_lam * w**2 / ref.C_ANGSTROM_S) - 48.6


def pick_stars(apm: pd.DataFrame, grid) -> list[tuple[str, pd.Series]]:
    ok = apm["fit_ok"].astype(bool) & ~apm["is_agn"].astype(bool)
    s = apm[ok & apm["gspcref_g"].notna()]
    inside = s["fit_teff"].between(grid.temp[0] * 1.01, grid.temp[-1] * 0.99)
    good = s[inside & (s["fit_redchi"] <= s["fit_redchi"].median())]
    picks, used = [], set()

    def take(label, row):
        if row is not None and row.name not in used:
            used.add(row.name)
            picks.append((label, row))

    take("cool", good.loc[good["fit_teff"].idxmin()] if len(good) else None)
    take("solar-type", good.loc[(good["fit_teff"] - 5800).abs().idxmin()] if len(good) else None)
    take("hottest", good.loc[good["fit_teff"].idxmax()] if len(good) else None)
    take("bad fit", s.loc[s["fit_redchi"].idxmax()] if len(s) else None)
    return picks


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def plot_star(ax, rax, label, star, grid, pivots):
    w_fit = np.array([ref.FIT_WAVE[b] for b in ref.FIT_BANDS])
    w_lco = np.array([pivots[b] for b in ref.LCO_BANDS])

    ap = np.array([star[f"apass_{b}"] + ref.VEGA_TO_AB[b] for b in ref.FIT_BANDS])
    ap_e = np.array([star[f"apass_{b}_err"] for b in ref.FIT_BANDS])
    m_fit = model_mags(star, grid, w_fit, "aavso", ref.FIT_BANDS)
    m_lco = model_mags(star, grid, w_lco, "lco", ref.LCO_BANDS)
    lco = np.array([star[f"lco_{b}"] for b in ref.LCO_BANDS])
    lco_e = np.array([star[f"lco_{b}_err"] for b in ref.LCO_BANDS])
    gs = np.array([star.get(f"gspcref_{b}", np.nan) for b in ref.LCO_BANDS])
    gs_e = np.array([star.get(f"gspcref_{b}_err", np.nan) for b in ref.LCO_BANDS])

    ax.plot(w_lco, m_lco, "-", color=C_MODEL, lw=1, zorder=1, label="model (through LCO filters)")
    ax.plot(w_fit, m_fit, "D", ms=4, color=C_MODEL, zorder=2, label="model (APASS bands)")
    ax.errorbar(w_fit, ap, ap_e, fmt="o", color=C_APASS, ms=5, capsize=2, zorder=4, label="APASS (AB)")
    ax.errorbar(w_lco, lco, lco_e, fmt="o", mfc="none", mec=C_LCO, ecolor=C_LCO, ms=8, capsize=2,
                zorder=3, label="synthetic LCO")
    if np.isfinite(star.get("lco_u_model", np.nan)) and abs(star["lco_u_model"] - star["lco_u"]) > 1e-3:
        ax.plot(pivots["u"], star["lco_u_model"], "s", mfc="none", mec=C_RAW, ms=8, zorder=3,
                label="LCO u before anchor")
    ax.errorbar(w_lco, gs, gs_e, fmt="x", color=C_GSPC, ms=7, mew=1.6, zorder=5, label="GSPC")
    for b, x in zip(ref.LCO_BANDS, w_lco):
        ax.annotate(b, (x, 0), xycoords=("data", "axes fraction"), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=7, color="0.4")
    ax.invert_yaxis()
    ax.set_ylabel("AB mag")
    gt = star.get("gaia_teff", np.nan)
    gtxt = f", GSP-Phot {gt:.0f} K" if np.isfinite(gt) else ""
    ax.set_title(f"{label}: Gaia DR3 {int(star['star_id'])}\n"
                 f"Teff = {star['fit_teff']:.0f} ± {star['fit_teff_err']:.0f} K{gtxt}, "
                 f"E(B-V) = {star['ebv']:.3f}, " + r"$\chi^2_\nu$" + f" = {star['fit_redchi']:.2f}",
                 fontsize=8, loc="left")

    rax.axhline(0, color="0.6", lw=0.8)
    rax.errorbar(w_fit, ap - m_fit, ap_e, fmt="o", color=C_APASS, ms=4, capsize=2)
    rax.plot(w_lco, lco - gs, "x", color=C_GSPC, ms=6, mew=1.4)
    rax.set_ylabel(r"$\Delta$ mag", fontsize=8)
    rax.set_xlabel(r"$\lambda$ [Å]")
    lim = np.nanmax(np.abs(np.r_[ap - m_fit, lco - gs, 0.1])) * 1.3
    rax.set_ylim(-lim, lim)


def page_stars(pdf, target_name, picks, grid, pivots):
    import matplotlib.pyplot as plt

    n = len(picks)
    ncol = 2
    nrow = int(np.ceil(n / ncol))
    fig = plt.figure(figsize=(11, 4.2 * nrow))
    outer = fig.add_gridspec(nrow, ncol, hspace=0.42, wspace=0.22)
    for i, (label, star) in enumerate(picks):
        inner = outer[i // ncol, i % ncol].subgridspec(2, 1, height_ratios=[3, 1], hspace=0.05)
        ax = fig.add_subplot(inner[0])
        rax = fig.add_subplot(inner[1], sharex=ax)
        plot_star(ax, rax, label, star, grid, pivots)
        plt.setp(ax.get_xticklabels(), visible=False)
        if i == 0:
            h, lab = ax.get_legend_handles_labels()
    fig.legend(h, lab, loc="upper center", ncol=6, fontsize=8, frameon=False,
               bbox_to_anchor=(0.5, 0.995))
    fig.suptitle(f"{target_name}: apass_model SED fits "
                 "(residuals: APASS − model, synthetic LCO − GSPC)", y=1.025, fontsize=11)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def page_summary(pdf, target_name, apm, ameta, picks):
    import matplotlib.pyplot as plt

    ok = apm["fit_ok"].astype(bool) & ~apm["is_agn"].astype(bool)
    f = apm[ok]
    fig, axs = plt.subplots(2, 2, figsize=(11, 8.5))
    out = {}

    # (a) reduced chi^2
    ax = axs[0, 0]
    rc = f["fit_redchi"].to_numpy()
    bins = np.logspace(np.log10(max(rc.min(), 1e-3)), np.log10(rc.max()), 30)
    ax.hist(rc, bins=bins, color=C_APASS, alpha=0.8)
    ax.set_xscale("log")
    med = np.median(rc)
    ax.axvline(med, color="k", ls="--", lw=1, label=f"median {med:.2f}")
    for label, s in picks:
        ax.axvline(s["fit_redchi"], color=C_LCO, lw=0.8, alpha=0.7)
        ax.text(s["fit_redchi"], ax.get_ylim()[1] * 0.95, label, rotation=90, va="top",
                ha="right", fontsize=7, color=C_LCO)
    ax.set_xlabel(r"fit_redchi ($\chi^2_\nu$, 3 dof)")
    ax.set_ylabel("stars")
    ax.legend(fontsize=8)
    ax.set_title(f"(a) fit quality: {len(f)} stars fitted", fontsize=9, loc="left")
    out["redchi_median"] = med

    # (b) Teff
    ax = axs[0, 1]
    lo, hi = np.nanpercentile(np.r_[f["fit_teff"], f["gaia_teff"].dropna()], [0.5, 99.5])
    tb = np.arange(np.floor(lo / 250) * 250, np.ceil(hi / 250) * 250 + 1, 125)
    ax.hist(f["fit_teff"].clip(tb[0], tb[-1]), bins=tb, color=C_APASS, alpha=0.8, label="SED fit")
    gt = f["gaia_teff"].dropna()
    if len(gt):
        ax.hist(gt.clip(tb[0], tb[-1]), bins=tb, histtype="step", color=C_GSPC, lw=1.5,
                label="Gaia GSP-Phot")
        both = f[["fit_teff", "gaia_teff"]].dropna()
        d = both["fit_teff"] - both["gaia_teff"]
        out["teff_vs_gaia_median"] = float(np.median(d))
        out["teff_vs_gaia_n"] = int(len(d))
        ax.text(0.97, 0.75, f"fit − GSP-Phot: median {np.median(d):+.0f} K\n(n = {len(d)})",
                transform=ax.transAxes, ha="right", fontsize=8)
    ax.set_xlabel(r"$T_{\rm eff}$ [K] (clipped to plot range)")
    ax.set_ylabel("stars")
    ax.legend(fontsize=8)
    ax.set_title("(b) temperature distribution", fontsize=9, loc="left")

    # (c) u before / after anchor vs GSPC SDSS u (AB), stars used by anchor_u
    ax = axs[1, 0]
    use = (f["gspc_u_sdss_flag"] == 1) & f["gspc_u_sdss"].notna() & ~(f["gaia_ruwe"] > 1.4)
    u = f[use]
    u_ref = u["gspc_u_sdss"] + SDSS_U_AB
    ua = ameta.get("u_anchor", {})
    d_raw, d_anc = u["lco_u_model"] - u_ref, u["lco_u"] - u_ref
    ax.scatter(u_ref, d_raw, s=14, color=C_RAW, label=f"model (median {np.median(d_raw):+.3f})")
    ax.scatter(u_ref, d_anc, s=14, facecolor="none", edgecolor=C_LCO,
               label=f"anchored (median {np.median(d_anc):+.3f})")
    ax.axhline(0, color="0.5", lw=0.8)
    title = "(c) u band vs GSPC SDSS u (AB)"
    if ua.get("applied"):
        title += (f": offset {ua['offset_mag']:+.3f} ± {ua['offset_err_mag']:.3f}, "
                  f"scatter {ua['scatter_mag']:.3f}, n = {ua['n_stars']}")
    else:
        title += f": anchor NOT applied (n = {ua.get('n_stars', 0)})"
    ax.set_title(title, fontsize=9, loc="left")
    ax.set_xlabel("GSPC u (AB)")
    ax.set_ylabel("LCO u − GSPC u [mag]")
    ax.set_ylim(-1, 1)
    ax.legend(fontsize=8)
    out["u_n"] = int(use.sum())

    # (d) model - GSPC catalogue, every band
    ax = axs[1, 1]
    q = f[f["gspcref_quality_ok"].eq(True)]
    data, labels, stats = [], [], {}
    for b in ref.LCO_BANDS:
        d = (q[f"lco_{b}"] - q[f"gspcref_{b}"]).dropna().to_numpy()
        if b == "u":
            d0 = (q["lco_u_model"] - q["gspcref_u"]).dropna().to_numpy()
            if len(d0):
                data.append(d0)
                labels.append("u\n(raw)")
        if len(d):
            data.append(d)
            labels.append(b)
            m = float(np.median(d))
            stats[b] = (m, float(1.4826 * np.median(np.abs(d - m))), len(d))
    ax.boxplot(data, showfliers=False, medianprops=dict(color=C_LCO))
    ax.set_xticks(range(1, len(labels) + 1), labels)
    ax.axhline(0, color="0.5", lw=0.8)
    ax.set_ylabel("apass_model − GSPC catalogue [mag]")
    ax.set_title("(d) per-band agreement (GSPC quality_ok stars)", fontsize=9, loc="left")
    out["band_stats"] = stats

    fig.suptitle(f"{target_name}: apass_model reference catalogue summary", fontsize=11)
    fig.tight_layout()
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# LaTeX
# ---------------------------------------------------------------------------

def write_tex(path, target_name, ameta, gmeta, picks, s):
    ua = ameta.get("u_anchor", {})
    pdf = f"figures/{STEM}.pdf"
    bands = ", ".join(f"{b}~${m:+.3f}$" for b, (m, _, _) in s["band_stats"].items())
    if ua.get("applied"):
        utxt = (f"The raw model $u$ is ${ua['offset_mag']:+.3f}\\pm{ua['offset_err_mag']:.3f}$\\,mag "
                f"away from GSPC SDSS $u$ (AB; {ua['n_stars']} stars, robust scatter "
                f"{ua['scatter_mag']:.3f}\\,mag) and is shifted by that offset.")
    else:
        utxt = (f"Only {ua.get('n_stars', 0)} usable GSPC $u$ stars, so $u$ was not anchored "
                "and \\texttt{lco\\_u} is the raw model prediction.")
    names = ", ".join(f"{lab}" for lab, _ in picks)
    tex = rf"""% Generated by tools/reference_sed_example.py on {datetime.now(timezone.utc):%Y-%m-%d} -- do not edit by hand.
% \input{{figures/{STEM}}} from docs/ (needs graphicx).
\paragraph{{Worked example: {target_name}.}}
The \texttt{{apass\_model}} fallback (Sec.~\ref{{sec:apass_model}}) was run on the
{target_name} field ({ameta.get('apass_release', 'APASS')}, {ameta['n_fitted']} of
{ameta['n_stars']} stars fitted, $E(B-V)_{{\rm SF11}}={ameta['ebv_sf11_los']:.3f}$) and
compared with the production GSPC catalogue ({gmeta['n_quality_ok']} quality stars).
Figure~\ref{{fig:refsed-stars}} shows the fit for representative stars ({names});
Fig.~\ref{{fig:refsed-summary}} summarises the field. The median reduced $\chi^2$
is {s['redchi_median']:.2f}. {utxt} Median apass\_model $-$ GSPC offsets per LCO band:
{bands}\,mag.

\begin{{figure}}[htbp]
  \centering
  \includegraphics[page=1,width=\textwidth]{{{pdf}}}
  \caption{{SED fits of representative {target_name} field stars by the
  \texttt{{apass\_model}} method. Filled circles: APASS $B\,g\,V\,r\,i$ (AB);
  grey diamonds and line: best-fit reddened BT-Settl/NextGen model, band-averaged
  through the APASS (nominal) and LCO filters; open red circles: synthetic LCO
  magnitudes (\texttt{{lco\_*}}); orange square: $u$ before the GSPC anchor;
  green crosses: the Gaia DR3 GSPC catalogue value for the same source.
  Lower panels: APASS $-$ model and synthetic LCO $-$ GSPC.}}
  \label{{fig:refsed-stars}}
\end{{figure}}

\begin{{figure}}[htbp]
  \centering
  \includegraphics[page=2,width=\textwidth]{{{pdf}}}
  \caption{{{target_name} \texttt{{apass\_model}} summary. (a) Reduced $\chi^2$ of
  the two-parameter fit to five bands; (b) fitted $T_{{\rm eff}}$ against Gaia
  GSP-Phot; (c) LCO $u$ minus GSPC SDSS $u$ (AB) before (filled) and after (open)
  the per-field anchor, for the stars \texttt{{anchor\_u}} uses; (d) per-band
  difference from the GSPC catalogue (box: interquartile range).}}
  \label{{fig:refsed-summary}}
\end{{figure}}
"""
    path.write_text(tex)


# ---------------------------------------------------------------------------

@click.command()
@click.option("--target", default="fairall_9", show_default=True, help="data_id of the target.")
@click.option("--refresh", is_flag=True, help="Rebuild the cached apass_model catalogue.")
@click.option("--out-dir", type=click.Path(file_okay=False, path_type=Path), default=FIG_DIR,
              show_default=True)
def main(target, refresh, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_pdf import PdfPages

    d, apm, ameta, gmeta = load(target, refresh)
    entry = cfg.target_by_data_id(target) or {}
    name = entry.get("name", target)
    rc = cfg.photometry.reference
    grid = ref.AtmosphereGrid.load(cfg._resolve(rc.atmosphere_grid))
    fdir = Path(cfg._resolve(rc.lco_filters))
    pivots = {b: ref.pivot_wavelength(fdir / f"lco_{b}.txt") for b in ref.LCO_BANDS}

    picks = pick_stars(apm, grid)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{STEM}.pdf"
    with PdfPages(pdf_path) as pdf:
        page_stars(pdf, name, picks, grid, pivots)
        s = page_summary(pdf, name, apm, ameta, picks)
    write_tex(out_dir / f"{STEM}.tex", name, ameta, gmeta, picks, s)

    click.echo(f"Catalogues: {d}")
    for label, st in picks:
        click.echo(f"  {label:10s} {int(st['star_id'])}  Teff {st['fit_teff']:7.0f} K  "
                   f"redchi {st['fit_redchi']:8.2f}")
    click.echo(f"u anchor: {ameta.get('u_anchor')}")
    for b, (m, sc, n) in s["band_stats"].items():
        click.echo(f"  {b}: model - GSPC {m:+.3f} (scatter {sc:.3f}, n={n})")
    click.echo(f"Wrote {pdf_path} and {pdf_path.with_suffix('.tex')}")


if __name__ == "__main__":
    main()
