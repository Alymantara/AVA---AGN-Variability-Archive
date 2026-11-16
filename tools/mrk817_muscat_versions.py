#!/usr/bin/env python
"""
Two versions of the merged AGN light curve, differing only in the MuSCAT additive correction:

  single      one MuSCAT offset per filter for the whole data set (the pipeline default,
              ``ensemble.intercal_per_season: false``) — reproduces the production light curve
  per_season  one MuSCAT offset per filter and observing season (``intercal_per_season: true``;
              seasons split at gaps > ``intercal_season_gap_days``)

Both use the pipeline's own functions (ava.photometry.intercal) on the stored PyTICS light curve
``agn_lightcurve_pytics.parquet``; nothing in the photometry directory is overwritten.

Writes to ``<phot>/muscat_versions/`` (or ``--out``):
  <target>_LCO_merged_lightcurve_muscat_single.csv       shareable format (good epochs, mJy + AB)
  <target>_LCO_merged_lightcurve_muscat_per_season.csv
  muscat_offsets.csv                                     fitted offsets b (mJy) for both versions
  lc_full_single.png / lc_full_per_season.png            whole data span, all bands
  lc_storm2_single.png / lc_storm2_per_season.png        AGN STORM 2 (MJD 59150-59650)
  muscat_offset_diagnostic.png                           how the offsets are measured, and residuals

Needs pandas + pyarrow + numba (the ava photometry modules), e.g. the pipeline venv.

    python tools/mrk817_muscat_versions.py --phot-dir data/test_archive/photometry/Mrk_817
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import click
import numpy as np
import pandas as pd
import yaml

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ava.photometry import intercal as IC  # noqa: E402

BANDS = ["up", "B", "gp", "V", "rp", "ip", "zs"]          # Y has ~10 epochs: in the CSVs, not plotted
LBL = dict(up="u", B="B", gp="g", V="V", rp="r", ip="i", zs="z", Y="Y")
FILTER_NAMES = {"up": "u", "B": "B", "gp": "g", "V": "V", "rp": "r", "ip": "i", "zs": "z", "Y": "Y"}
STORM2 = (59150.0, 59650.0)
# no greys: grey open circles are the uncorrected MuSCAT points
OI = ["#E69F00", "#56B4E9", "#009E73", "#0072B2", "#D55E00", "#CC79A7", "#7B3294", "#F0E442",
      "#8C564B", "#17BECF", "#BCBD22", "#E7298A", "#1B9E77"]
MK = ["o", "s", "D", "^", "v", "P", "X", "h", "<", ">", "p", "*", "d"]
SEASON_COL = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]


def cfg_value(key, default):
    try:
        c = yaml.safe_load((ROOT / "config/ava_config.yaml").read_text())
        return c.get("ensemble", {}).get(key, default)
    except Exception:  # noqa: BLE001
        return default


def matches(scope, prefixes):
    cam = scope.split("-", 1)[-1]
    return any(cam.startswith(p) for p in prefixes)


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

def build(lc: pd.DataFrame, per_season: bool, ref_prefix, fix_prefix, max_gap, min_pairs, gap_days):
    base = lc.drop(columns=[c for c in ("F", "Ferr", "F_ic", "Ferr_ic", "ic_a", "ic_b", "mag_ic", "mag_ic_err")
                            if c in lc])
    base["season"] = IC.seasons(base["MJD"], gap_days)
    scopes = sorted(base["scope"].unique())
    ref = [s for s in scopes if matches(s, ref_prefix)]
    fix = [s for s in scopes if matches(s, fix_prefix)]
    table = IC.intercalibrate(base, ref, max_gap=max_gap, min_pairs=min_pairs).assign(season=-1)
    if per_season:
        ts = IC.intercalibrate_by_season(base, ref, fix, max_gap=max_gap, min_pairs=min_pairs)
        table = pd.concat([table, ts], ignore_index=True)
    out = IC.apply_intercal(base, table, scopes=fix, additive_only=True)
    t = table[table["scope"].isin(fix)].copy()
    t["version"] = "per_season" if per_season else "single"
    return out, t, ref, fix


def export(lc: pd.DataFrame, path: Path, target: str) -> pd.DataFrame:
    """Same columns and errors as the pipeline's shareable CSV (export_merged_csv, error_model=pytics)."""
    g = lc[lc["good"]].copy()
    f_rand = g["F_ic"] * g["mag_err_rand"] * np.log(10) / 2.5 / g["ic_a"]
    out = pd.DataFrame({
        "target": target, "MJD": g["MJD"].round(6), "filter": g["Filter"].map(FILTER_NAMES).fillna(g["Filter"]),
        "telescope": g["telid"], "camera": g["camera"],
        "flux_mJy": g["F_ic"], "flux_err_mJy": g["Ferr_ic"], "flux_err_random_mJy": f_rand,
        "mag_AB": g["mag_ic"], "mag_AB_err": g["mag_ic_err"], "mag_AB_err_random": g["mag_err_rand"],
        "muscat_offset_mJy": g["ic_b"], "season": g["season"],
        "frame": g["frame"]}).sort_values(["filter", "MJD"])
    out.to_csv(path, index=False, float_format="%.5f")
    return out


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def plt_setup():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"text.usetex": False, "font.size": 9, "legend.frameon": False, "legend.fontsize": 7,
                         "xtick.direction": "in", "ytick.direction": "in"})
    return plt


def cam_styles(lc):
    cams = sorted(c for c in lc["cam"].unique() if c != "MuSCAT3")
    sty = {c: dict(color=OI[i % len(OI)], marker=MK[i % len(MK)]) for i, c in enumerate(cams)}
    sty["MuSCAT3"] = dict(color="k", marker="o")
    return cams, sty


def rob(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return 1.4826 * np.median(np.abs(x - np.median(x))) if len(x) else np.nan


def cross_cam_sigma(d, dt=0.4):
    """Robust σ (%) of the flux ratio MuSCAT/Sinistro on the same night (< dt apart)."""
    d = d.assign(night=np.floor(d["MJD"] - 0.5).astype(int), kind=np.where(d["cam"] == "MuSCAT3", "ep", "fa"))
    g = d.groupby(["night", "kind"]).agg(F=("F_ic", "median"), MJD=("MJD", "median")).unstack("kind").dropna()
    if not len(g):
        return np.nan, 0
    ok = (g[("MJD", "ep")] - g[("MJD", "fa")]).abs() < dt
    r = (g[("F", "ep")] / g[("F", "fa")] - 1)[ok]
    return 100 * rob(r), int(ok.sum())


def plot_lc(plt, lc, path, title, t0=None, t1=None, show_raw=True):
    d = lc[lc["good"]]
    if t0 is not None:
        d = d[(d["MJD"] > t0) & (d["MJD"] < t1)]
    cams, sty = cam_styles(lc)
    fig, ax = plt.subplots(len(BANDS), 1, figsize=(13, 2.05 * len(BANDS) + 1), sharex=True)
    for a, f in zip(ax, BANDS):
        x = d[d["Filter"] == f]
        for c, h in x.groupby("cam"):
            if c == "MuSCAT3" and show_raw:
                a.plot(h["MJD"], h["F"], "o", ms=2, mfc="none", mec="0.75", mew=0.5, zorder=1)
            a.errorbar(h["MJD"], h["F_ic"], h["Ferr_ic"], ls="none", ms=2.2, elinewidth=0.4, zorder=2, **sty[c])
        a.text(0.005, 0.9, LBL[f], transform=a.transAxes, fontsize=12, fontweight="bold", va="top")
        if (x["cam"] == "MuSCAT3").any():
            s, n = cross_cam_sigma(x)
            a.text(0.995, 0.06, f"MuSCAT vs Sinistro, same night: σ = {s:.2f} % ({n} nights)",
                   transform=a.transAxes, ha="right", fontsize=7)
        if len(x):
            lo, hi = np.nanpercentile(x["F_ic"], [0.5, 99.5])
            a.set_ylim(lo - 0.12 * (hi - lo), hi + 0.12 * (hi - lo))
        a.set_ylabel("flux (mJy)")
    present = [c for c in cams if c in set(d["cam"])] + (["MuSCAT3"] if (d["cam"] == "MuSCAT3").any() else [])
    hnd = [plt.Line2D([], [], ls="none", ms=5, **sty[c]) for c in present]
    lab = [c if c != "MuSCAT3" else "MuSCAT3, corrected" for c in present]
    if show_raw and "MuSCAT3" in present:
        hnd.append(plt.Line2D([], [], ls="none", marker="o", mfc="none", mec="0.75", ms=5))
        lab.append("MuSCAT3, before correction")
    ax[0].legend(hnd, lab, ncol=7, loc="lower center", bbox_to_anchor=(0.5, 1.02), fontsize=7)
    ax[0].set_title(title, pad=38, fontsize=10)
    ax[-1].set_xlabel("MJD")
    if t0 is not None:
        ax[-1].set_xlim(t0, t1)
    fig.tight_layout()
    fig.subplots_adjust(hspace=0.06)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_diagnostic(plt, lc, tables, ref, fix, path, max_gap, title):
    """Row 1: MuSCAT vs interpolated Sinistro flux per night, coloured by season, with the
    single offset and the per-season offsets.  Row 2: MuSCAT - Sinistro vs time, raw, with
    the offsets drawn as steps.  Row 3: residual after each version, vs time."""
    fs = [f for f in BANDS if any(lc.loc[lc["Filter"] == f, "scope"].isin(fix))]
    fig, ax = plt.subplots(3, len(fs), figsize=(3.6 * len(fs), 9.6), squeeze=False)
    tab = pd.concat(tables, ignore_index=True)
    from astropy.time import Time
    rng = lc.groupby("season")["MJD"].agg(["min", "max"])
    slabel = {int(s): f"{Time(r['min'], format='mjd').datetime:%b %Y}–{Time(r['max'], format='mjd').datetime:%b %Y}"
              for s, r in rng.iterrows()}
    for j, f in enumerate(fs):
        g = lc[(lc["Filter"] == f) & lc["good"]]
        k = [s for s in g["scope"].unique() if s in fix][0]
        raw = g.assign(mag=g["mag"])                       # PyTICS mags before the additive term
        nt = IC.nightly(raw)
        me = nt[nt["scope"] == k].copy()
        refn = IC.nightly(raw[raw["scope"].isin(ref)], by=())
        fr, fre, good = IC._interp(refn, me["MJD"].to_numpy(), max_gap)
        me = me.assign(x=fr, xe=fre)[good]
        me["season"] = np.searchsorted(np.sort(lc.groupby("season")["MJD"].min().to_numpy()),
                                       me["MJD"].to_numpy(), "right") - 1
        single = tab[(tab["filter"] == f) & (tab["scope"] == k) & (tab["version"] == "single")].iloc[0]
        per = tab[(tab["filter"] == f) & (tab["scope"] == k) & (tab["version"] == "per_season")
                  & (tab["season"] >= 0)]

        # --- flux-flux
        a = ax[0, j]
        for s, h in me.groupby("season"):
            a.errorbar(h["x"], h["F"], h["Ferr"], h["xe"], fmt="o", ms=3, elinewidth=0.4,
                       color=SEASON_COL[s % len(SEASON_COL)], label=f"{slabel[s]}: {len(h)} nights")
        xx = np.array([me["x"].min(), me["x"].max()])
        a.plot(xx, xx, ":", color="0.4", lw=0.8, label="1:1")
        a.plot(xx, xx + single["b1"], "k-", lw=1.2, label=f"single: b = {single['b1']:+.3f} ± {single['b1_err']:.3f}")
        for _, r in per.iterrows():
            a.plot(xx, xx + r["b1"], "--", lw=1.1, color=SEASON_COL[int(r["season"]) % len(SEASON_COL)],
                   label=f"{slabel[int(r['season'])]}: b = {r['b1']:+.3f} ± {r['b1_err']:.3f}")
        a.set_xlabel("Sinistro, interpolated to the MuSCAT night (mJy)")
        a.set_ylabel(f"MuSCAT {k.split('-')[1]} (mJy)")
        a.set_title(f"{LBL[f]}: MuSCAT = Sinistro + b", fontsize=9)
        a.legend(fontsize=6, loc="upper left")

        # --- difference vs time, offsets as steps
        a = ax[1, j]
        d = me["F"] - me["x"]
        for s, h in me.assign(d=d).groupby("season"):
            a.errorbar(h["MJD"], h["d"], np.hypot(h["Ferr"], h["xe"]), fmt="o", ms=2.5, elinewidth=0.4,
                       color=SEASON_COL[s % len(SEASON_COL)])
        a.axhline(single["b1"], color="k", lw=1.2, label="single offset")
        for _, r in per.iterrows():
            a.hlines(r["b1"], r["MJD_min"], r["MJD_max"], colors=SEASON_COL[int(r["season"]) % len(SEASON_COL)],
                     linestyles="--", lw=1.4, label=slabel[int(r["season"])])
        a.set_xlabel("MJD")
        a.set_ylabel("MuSCAT − Sinistro (mJy)")
        lo, hi = np.nanpercentile(d, [2, 98])
        a.set_ylim(lo - 0.4 * (hi - lo), hi + 0.4 * (hi - lo))
        a.legend(fontsize=6, loc="best")

        # --- residual after each version
        a = ax[2, j]
        sb = me["season"].map(per.set_index("season")["b1"]).fillna(single["b1"])
        for lab, b, col, mk in (("single", single["b1"], "k", "o"), ("per season", sb, "#D55E00", "s")):
            r = d - b
            a.plot(me["MJD"], 100 * r / me["x"], mk, ms=2.5, color=col, alpha=0.8,
                   label=f"{lab}: robust σ = {100 * rob(r / me['x']):.2f} %")
        a.axhline(0, color="0.5", lw=0.8)
        a.set_xlabel("MJD")
        a.set_ylabel("residual (% of flux)")
        a.set_ylim(-4, 4)
        a.legend(fontsize=6, loc="lower left")
    fig.suptitle(title, y=1.0)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------

@click.command()
@click.option("--phot-dir", type=click.Path(file_okay=False, path_type=Path),
              default=ROOT / "data/test_archive/photometry/Mrk_817", show_default=True)
@click.option("--out", type=click.Path(file_okay=False, path_type=Path), default=None,
              help="Output folder (default <phot-dir>/muscat_versions).")
def main(phot_dir, out):
    out = out or phot_dir / "muscat_versions"
    out.mkdir(parents=True, exist_ok=True)
    target = yaml.safe_load((phot_dir / "target.yaml").read_text())
    tid, name = target["data_id"], target["name"]
    ref_prefix = tuple(cfg_value("intercal_reference_cameras", ["fa"]))
    fix_prefix = tuple(cfg_value("intercal_correct_cameras", ["ep"]))
    max_gap = float(cfg_value("intercal_max_gap_days", 3.0))
    min_pairs = int(cfg_value("intercal_min_pairs", 10))
    gap_days = float(cfg_value("intercal_season_gap_days", 60.0))

    prod = pd.read_parquet(phot_dir / "agn_lightcurve_pytics.parquet")
    one, t1, ref, fix = build(prod, False, ref_prefix, fix_prefix, max_gap, min_pairs, gap_days)
    per, t2, _, _ = build(prod, True, ref_prefix, fix_prefix, max_gap, min_pairs, gap_days)

    # the single-offset version must be the production light curve
    chk = one.merge(prod[["frame", "mag_ic"]], on="frame", suffixes=("", "_prod"))
    dmax = float((chk["mag_ic"] - chk["mag_ic_prod"]).abs().max())
    click.echo(f"single version vs production mag_ic: max |Δ| = {dmax:.2e} mag over {len(chk)} rows")
    if dmax > 1e-6:
        raise SystemExit("single-offset version does not reproduce the production light curve")

    for v in (one, per):
        v["cam"] = np.where(v["scope"].isin(fix), "MuSCAT3", v["scope"])

    e1 = export(one, out / f"{tid}_LCO_merged_lightcurve_muscat_single.csv", tid)
    e2 = export(per, out / f"{tid}_LCO_merged_lightcurve_muscat_per_season.csv", tid)
    tabs = pd.concat([t1, t2], ignore_index=True)
    cols = ["version", "filter", "scope", "season", "MJD_min", "MJD_max", "n_pairs", "n_used", "b1", "b1_err",
            "F_mean", "rms_before", "rms_b1"]
    tabs[[c for c in cols if c in tabs]].to_csv(out / "muscat_offsets.csv", index=False, float_format="%.5f")

    plt = plt_setup()
    span = f"MJD {prod['MJD'].min():.0f}–{prod['MJD'].max():.0f}"
    plot_lc(plt, one, out / "lc_full_single.png", f"{name}, all data ({span}) — MuSCAT: one offset per filter")
    plot_lc(plt, per, out / "lc_full_per_season.png", f"{name}, all data ({span}) — MuSCAT: one offset per filter and season")
    plot_lc(plt, one, out / "lc_storm2_single.png", f"{name}, AGN STORM 2 — MuSCAT: one offset per filter", *STORM2)
    plot_lc(plt, per, out / "lc_storm2_per_season.png", f"{name}, AGN STORM 2 — MuSCAT: one offset per filter and season",
            *STORM2)
    plot_diagnostic(plt, per, [t1, t2], ref, fix, out / "muscat_offset_diagnostic.png", max_gap,
                    f"{name}: MuSCAT additive offset, single vs per season (nightly means, good epochs)")

    seasons = per.groupby("season")["MJD"].agg(["min", "max", "size"])
    click.echo("seasons (all cameras):\n" + seasons.round(1).to_string())
    click.echo(tabs[[c for c in ("version", "filter", "season", "n_pairs", "b1", "b1_err", "rms_b1") if c in tabs]]
               .round(4).to_string(index=False))
    click.echo(f"rows: single {len(e1)}, per-season {len(e2)}; changed MuSCAT rows: "
               f"{int((np.abs(e1['flux_mJy'].to_numpy() - e2['flux_mJy'].to_numpy()) > 1e-6).sum())}")
    click.echo(f"wrote {out}")


if __name__ == "__main__":
    main()
