#!/usr/bin/env python
"""
Independent check of a target's absolute (AB) calibration, with manual figures.

Compares the PyTICS-calibrated comparison stars with photometry AVA never uses:

  * SDSS DR16 PSF magnitudes (VizieR V/154): u g r i z; B and V via the
    Jordi et al. (2006) stellar transformations (good to ~0.02-0.03 mag);
  * Pan-STARRS1 DR2 mean PSF y (MAST) for LCO Y.

and checks the calibration chain internally: the zero point applied to the AGN
light curve vs ``pytics/<f>/meta.json`` and ``pytics/absolute_zp.json``, the
per-frame ZPs in ``frame_qc`` vs the ensemble, the camera-to-camera agreement,
MuSCAT vs Sinistro AGN fluxes before/after intercal, and the mJy conversion.

Outputs (``--out-dir``, default ``docs/figures/abscal``):
  abscal_01_stars.{pdf,png}      calibrated - external vs g-i, per filter
  abscal_02_summary.{pdf,png}    offset at the AGN colour, AVA and GSPC
  abscal_03_cameras.{pdf,png}    per-camera offsets
  abscal_04_frame_zp.{pdf,png}   per-frame ZP - ensemble ZP
  abscal_05_muscat.{pdf,png}     MuSCAT - Sinistro AGN, raw and after intercal
  abscal_<target>.csv            numbers behind the figures
  abscal_<target>.tex            \\input{} from docs/ (figures + table)

External catalogues are cached in the photometry dir (``external_sdss16.csv``,
``external_ps1dr2.csv``); ``--refresh`` downloads them again.  Needs pandas with
a working pyarrow (e.g. ``/opt/anaconda3/envs/stenv/bin/python``); no numba.

    python tools/check_absolute_calibration.py --phot-dir data/test_archive/photometry/Mrk_817
"""

from __future__ import annotations

import json
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import click
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FILTERS = ["up", "B", "gp", "V", "rp", "ip", "zs", "Y"]
BAND = dict(up="u", B="B", gp="g", V="V", rp="r", ip="i", zs="z", Y="Y")
TRUTH = dict(up="SDSS u", B="SDSS→B", gp="SDSS g", V="SDSS→V", rp="SDSS r", ip="SDSS i", zs="SDSS z", Y="PS1 y")
TRUTH_TEX = dict(up="SDSS $u$", B="SDSS$\\to B$", gp="SDSS $g$", V="SDSS$\\to V$", rp="SDSS $r$",
                 ip="SDSS $i$", zs="SDSS $z$", Y="PS1 $y$")
SDSS_AB = dict(u=-0.04, g=0.0, r=0.0, i=0.0, z=0.02)        # u_AB = u - 0.04, z_AB = z + 0.02
SDSS_BRIGHT = dict(u=13.0, g=14.0, r=14.0, i=14.0, z=12.5)   # saturation, conservative
VEGA_TO_AB = dict(B=-0.09, V=0.02)
C_AVA, C_GSPC, C_AGN, C_RAW = "#1f4e79", "#2e8b57", "#c0392b", "#e69f00"


# ---------------------------------------------------------------------------
# External catalogues
# ---------------------------------------------------------------------------

def fetch_sdss(ra, dec, radius_arcmin, path: Path, servers) -> pd.DataFrame:
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    from ava.photometry.reference import vizier_query

    cols = (["RA_ICRS", "DE_ICRS", "mode", "class", "clean"]
            + [f"{b}pmag" for b in "ugriz"] + [f"e_{b}pmag" for b in "ugriz"])
    t, _ = vizier_query(servers, SkyCoord(ra, dec, unit="deg"), radius_arcmin * u.arcmin,
                        "V/154/sdss16", columns=cols)
    df = t.to_pandas()
    df.to_csv(path, index=False)
    return df


def fetch_ps1(ra, dec, radius_arcmin, path: Path) -> pd.DataFrame:
    cols = ["objID", "raMean", "decMean", "nDetections", "qualityFlag", "iMeanPSFMag", "iMeanKronMag",
            "yMeanPSFMag", "yMeanPSFMagErr"]
    q = urllib.parse.urlencode({"ra": ra, "dec": dec, "radius": radius_arcmin / 60.0, "nDetections.gt": 4,
                                "columns": "[" + ",".join(cols) + "]", "pagesize": 50000})
    url = "https://catalogs.mast.stsci.edu/api/v0.1/panstarrs/dr2/mean.csv?" + q
    with urllib.request.urlopen(url, timeout=300) as r:
        path.write_bytes(r.read())
    return pd.read_csv(path)


def truth_table(phot: Path, ref: pd.DataFrame, target: dict, refresh: bool, servers) -> pd.DataFrame:
    """External AB magnitudes for every reference star (NaN where unmatched/unusable)."""
    from astropy.coordinates import SkyCoord

    ra, dec, rad = target["ra_deg"], target["dec_deg"], float(ref["agn_sep_arcsec"].max() / 60 + 0.5)
    sp, pp = phot / "external_sdss16.csv", phot / "external_ps1dr2.csv"
    sd = fetch_sdss(ra, dec, rad, sp, servers) if refresh or not sp.exists() else pd.read_csv(sp)
    ps = fetch_ps1(ra, dec, rad, pp) if refresh or not pp.exists() else pd.read_csv(pp)

    sd = sd[(sd["mode"] == 1) & (sd["class"] == 6) & (sd["clean"] == 1)]
    t = pd.DataFrame({"ra": sd["RA_ICRS"].to_numpy(), "dec": sd["DE_ICRS"].to_numpy()})
    for b, off in SDSS_AB.items():
        m, e = sd[f"{b}pmag"].to_numpy(), sd[f"e_{b}pmag"].to_numpy()
        t[f"t_{b}"] = np.where((m > SDSS_BRIGHT[b]) & (e < 0.05), m + off, np.nan)
    gr = t["t_g"] - t["t_r"]                     # Jordi+06 (stars, Vega) -> AB
    t["t_B"] = t["t_g"] + 0.313 * gr + 0.219 + VEGA_TO_AB["B"]
    t["t_V"] = t["t_g"] - 0.565 * gr - 0.016 + VEGA_TO_AB["V"]
    t["ext_gi"] = t["t_g"] - t["t_i"]

    ps = ps.replace(-999.0, np.nan)
    ps = ps[ps["iMeanPSFMag"] - ps["iMeanKronMag"] < 0.05]       # point sources
    y = np.where((ps["yMeanPSFMag"] > 13.0) & (ps["yMeanPSFMagErr"] < 0.05), ps["yMeanPSFMag"], np.nan)

    r = ref[~ref["is_agn"].astype(bool)].copy()
    cr = SkyCoord(r["ra"].to_numpy(), r["dec"].to_numpy(), unit="deg")
    i_s, d_s, _ = cr.match_to_catalog_sky(SkyCoord(t["ra"].to_numpy(), t["dec"].to_numpy(), unit="deg"))
    i_p, d_p, _ = cr.match_to_catalog_sky(SkyCoord(ps["raMean"].to_numpy(), ps["decMean"].to_numpy(), unit="deg"))
    for c in [c for c in t.columns if c.startswith("t_") or c == "ext_gi"]:
        r[c] = np.where(d_s.arcsec < 1.0, t[c].to_numpy()[i_s], np.nan)
    r["t_Y"] = np.where(d_p.arcsec < 1.0, y[i_p], np.nan)
    r["gi_ext"] = r["ext_gi"].fillna(r["lco_g"] - r["lco_i"])   # independent colour where possible
    return r


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def rstats(d):
    d = np.asarray(d, float)
    d = d[np.isfinite(d)]
    if len(d) < 3:
        return np.nan, np.nan, len(d)
    m = float(np.median(d))
    return m, float(1.4826 * np.median(np.abs(d - m))), len(d)


def offset_at(x, y, x0, rng, n_boot=500):
    """Clipped linear fit y(x); value at x0 with bootstrap error, and the slope."""
    x, y = np.asarray(x, float) - x0, np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 6:
        return np.nan, np.nan, np.nan, len(x)
    keep = np.ones(len(x), bool)
    for _ in range(5):
        p = np.polyfit(x[keep], y[keep], 1)
        r = y - np.polyval(p, x)
        s = 1.4826 * np.median(np.abs(r[keep]))
        keep = np.abs(r) < 3 * max(s, 0.005)
    xb, yb = x[keep], y[keep]
    bs = [np.polyfit(xb[i], yb[i], 1)[1] for i in (rng.integers(0, len(xb), len(xb)) for _ in range(n_boot))]
    return float(p[1]), float(np.std(bs)), float(p[0]), int(keep.sum())


def load_solutions(phot: Path):
    meta = {f: json.loads((phot / "pytics" / f / "meta.json").read_text()) for f in FILTERS
            if (phot / "pytics" / f / "meta.json").exists()}
    return meta


def analyse(phot: Path, qc_db: Path, X: pd.DataFrame, meta: dict):
    rng = np.random.default_rng(1)
    lc = pd.read_parquet(phot / "agn_lightcurve_pytics.parquet")
    summ = json.loads((phot / "pytics" / "absolute_zp.json").read_text()) \
        if (phot / "pytics" / "absolute_zp.json").exists() else {}
    qc = pd.read_sql("select frame, zp from frame_qc", sqlite3.connect(qc_db))
    meas = pd.read_parquet(phot / "measurements.parquet",
                           columns=["frame", "star_id", "is_agn", "mag_inst", "sex_flags"])
    meas = meas[~meas["is_agn"] & ((meas["sex_flags"] & 28) == 0)]

    rows, stars, cams, fzp = [], [], [], []
    for f, m in meta.items():
        b, z = BAND[f], m["zp_fit"]
        c_agn = float(m.get("agn_colour", z.get("agn_colour")))
        st = pd.read_parquet(phot / "pytics" / f / "stars.parquet").merge(X, on="star_id")
        st = st[st["rms_star"] < 0.05].copy()
        st["cal"] = st["m_star"] + z["zp"] + z["C"] * (st["gi_ext"] - z["c0"])
        st["d"] = st["cal"] - st[f"t_{b}"]
        st["d_gspc"] = st[f"lco_{b}"] - st[f"t_{b}"]
        st["filter"] = f
        stars.append(st)
        med, sd, n = rstats(st["d"])
        off, off_e, slope, n_fit = offset_at(st["gi_ext"], st["d"], c_agn, rng)
        goff, goff_e, _, _ = offset_at(st["gi_ext"], st["d_gspc"], c_agn, rng)

        # zero point applied to the AGN light curve
        a = lc[lc["Filter"] == f]
        applied = float(np.median(a["mag"] - a["mag_inst"] + a["DMAGT"] + a["DMAGS"] + a["CKterm"]))

        # per camera, from the raw measurements
        ep = pd.read_parquet(phot / "pytics" / f / "epochs.parquet")[["frame", "scope", "DMAGT"]]
        sc = pd.read_parquet(phot / "pytics" / f / "scopes.parquet").set_index("scope")
        mm = meas.merge(ep, on="frame").merge(X[["star_id", f"t_{b}", "gi_ext"]], on="star_id")
        ck = mm["scope"].map(sc["CK"]).fillna(0.0) if (m.get("colour_terms") and "CK" in sc) else 0.0
        mm["cal"] = (mm["mag_inst"] - mm["DMAGT"] - mm["scope"].map(sc["DMAGS"]) - ck * (mm["gi_ext"] - m["c0"])
                     + z["zp"] + z["C"] * (mm["gi_ext"] - z["c0"]))
        per = mm.groupby(["scope", "star_id"]).agg(cal=("cal", "median"), t=(f"t_{b}", "first"), n=("cal", "size"))
        per = per[per["n"] >= 5]
        per["d"] = per["cal"] - per["t"]
        for scope, g in per.groupby("scope"):
            cm, cs, cn = rstats(g["d"])
            if cn >= 5:
                cams.append(dict(filter=f, scope=scope, offset=cm, sd=cs, n_star=cn, n_frames=int((ep.scope == scope).sum())))
        cam_rms = float(np.std([c["offset"] for c in cams if c["filter"] == f])) \
            if sum(c["filter"] == f for c in cams) > 1 else np.nan

        # per-frame ZP (frame_qc) vs ensemble frame ZP at the star c0
        e = ep.merge(qc, on="frame")
        dz = (e["zp"] - (z["zp"] - e["DMAGT"] - e["scope"].map(sc["DMAGS"]))).dropna()
        fzp.append(pd.DataFrame({"filter": f, "dzp": dz.to_numpy()}))
        fm, fs, fn = rstats(dz)

        rows.append(dict(filter=f, truth=TRUTH[f], n_stars=n, median=med, sd=sd,
                         offset_agn=off, offset_agn_err=off_e, slope=slope, n_fit=n_fit,
                         gspc_offset_agn=goff, gspc_offset_agn_err=goff_e, agn_colour=c_agn,
                         zp_applied=applied, zp_meta=m["zp"], zp_err=m.get("zp_err"),
                         zp_summary=summ.get(f, {}).get("zp_agn", np.nan),
                         n_cameras=sum(c["filter"] == f for c in cams), camera_rms=cam_rms,
                         frame_zp_median=fm, frame_zp_sd=fs, n_frames=fn, n_epochs=len(ep),
                         colour_terms=bool(m.get("colour_terms"))))

    # MuSCAT vs Sinistro, same night
    g = lc[lc["good"]].copy() if "good" in lc else lc.copy()
    g["night"] = np.floor(g["MJD"] - 0.5)
    g["cam"] = g["camera"].str[:2]
    mus = []
    for f, gf in g.groupby("Filter"):
        n = gf.groupby(["night", "cam"])[["mag", "mag_ic"]].median().unstack("cam")
        if ("mag", "ep") in n and ("mag", "fa") in n:
            raw = (n["mag"]["ep"] - n["mag"]["fa"]).dropna()
            ic = (n["mag_ic"]["ep"] - n["mag_ic"]["fa"]).dropna()
            mus.append(pd.DataFrame({"filter": f, "night": raw.index, "raw": raw.to_numpy(),
                                     "intercal": ic.reindex(raw.index).to_numpy()}))
    mus = pd.concat(mus, ignore_index=True) if mus else pd.DataFrame(columns=["filter", "raw", "intercal"])

    # mJy conversion of the shareable product
    prod = sorted(phot.glob("*_LCO_merged_lightcurve.csv"))
    mjy = np.nan
    if prod:
        p = pd.read_csv(prod[0], usecols=["flux_mJy", "mag_AB"], comment="#")
        mjy = float(np.median(p["flux_mJy"] / (3631e3 * 10 ** (-0.4 * p["mag_AB"]))))
    return (pd.DataFrame(rows), pd.concat(stars, ignore_index=True), pd.DataFrame(cams),
            pd.concat(fzp, ignore_index=True), mus, mjy)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"text.usetex": False, "font.size": 9, "axes.titlesize": 9})
    return plt


def save(fig, out: Path, name: str):
    for ext in ("pdf", "png"):
        fig.savefig(out / f"{name}.{ext}", dpi=150, bbox_inches="tight")


def fig_stars(plt, res, stars, out, name):
    fig, axs = plt.subplots(2, 4, figsize=(13, 6.2), sharex=True, sharey=True)
    for ax, (_, r) in zip(axs.flat, res.iterrows()):
        s = stars[stars["filter"] == r["filter"]]
        ax.axhspan(-0.01, 0.01, color="0.88", zorder=0)
        ax.axhline(0, color="0.5", lw=0.8)
        ax.scatter(s["gi_ext"], s["d"], s=11, color=C_AVA, alpha=0.85, lw=0)
        ax.axvline(r["agn_colour"], color=C_AGN, ls="--", lw=1)
        if np.isfinite(r["slope"]):
            x = np.linspace(s["gi_ext"].min(), s["gi_ext"].max(), 10)
            ax.plot(x, r["offset_agn"] + r["slope"] * (x - r["agn_colour"]), color=C_AGN, lw=1)
        ax.set_title(f"{r['filter']} − {r['truth']}:  median {r['median']:+.3f}, σ {r['sd']:.3f}, n = {r['n_stars']}",
                     loc="left")
    axs[0, 0].set_ylim(-0.15, 0.15)
    axs[0, 0].text(0.02, 0.92, "AGN g−i", color=C_AGN, transform=axs[0, 0].transAxes, fontsize=8)
    for a in axs[1]:
        a.set_xlabel("g − i  (SDSS; GSPC where no SDSS)")
    for a in axs[:, 0]:
        a.set_ylabel("calibrated − external [mag]")
    fig.tight_layout()
    save(fig, out, name)
    plt.close(fig)


def fig_summary(plt, res, out, name):
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    x = np.arange(len(res))
    ax.axhspan(-0.01, 0.01, color="0.88", zorder=0)
    ax.axhline(0, color="0.5", lw=0.8)
    ax.errorbar(x - 0.12, res["offset_agn"], res["offset_agn_err"], fmt="o", color=C_AVA, capsize=3,
                label="AVA (PyTICS + absolute ZP)")
    ax.errorbar(x + 0.12, res["gspc_offset_agn"], res["gspc_offset_agn_err"], fmt="s", mfc="none",
                color=C_GSPC, capsize=3, label="GSPC reference catalogue")
    ax.set_xticks(x, [f"{f}\n({t})" for f, t in zip(res["filter"], res["truth"])], fontsize=8)
    ax.set_ylabel("offset at AGN colour [mag]\n(minus external)")
    lim = np.nanmax(np.abs(np.r_[res["offset_agn"] + res["offset_agn_err"], 0.03])) * 1.4
    ax.set_ylim(-lim, lim)
    ax.legend(fontsize=8, loc="lower left", frameon=False)
    fig.tight_layout()
    save(fig, out, name)
    plt.close(fig)


def fig_cameras(plt, res, cams, out, name):
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ax.axhspan(-0.01, 0.01, color="0.88", zorder=0)
    ax.axhline(0, color="0.5", lw=0.8)
    for i, f in enumerate(res["filter"]):
        c = cams[cams["filter"] == f]
        if not len(c):
            continue
        jit = np.linspace(-0.25, 0.25, len(c)) if len(c) > 1 else np.zeros(1)
        col = np.where(c["scope"].str.contains("-ep"), C_RAW, np.where(c["scope"].str.startswith("2m"), C_GSPC, C_AVA))
        ax.scatter(i + jit, c["offset"], c=col, s=18, zorder=3)
    ax.set_xticks(range(len(res)), res["filter"])
    ax.set_ylabel("camera offset vs external [mag]")
    kinds = (("1 m Sinistro", C_AVA, ~cams["scope"].str.startswith("2m")),
             ("2 m Spectral", C_GSPC, cams["scope"].str.startswith("2m") & ~cams["scope"].str.contains("-ep")),
             ("2 m MuSCAT", C_RAW, cams["scope"].str.contains("-ep")))
    for lab, col, present in kinds:
        if present.any():
            ax.scatter([], [], c=col, s=18, label=lab)
    ax.legend(fontsize=8, frameon=False, ncol=3, loc="lower left")
    ax.set_ylim(-0.05, 0.05)
    fig.tight_layout()
    save(fig, out, name)
    plt.close(fig)


def fig_frame_zp(plt, res, fzp, out, name):
    fig, axs = plt.subplots(1, len(res), figsize=(13, 2.6), sharey=False)
    for ax, (_, r) in zip(np.atleast_1d(axs), res.iterrows()):
        d = fzp.loc[fzp["filter"] == r["filter"], "dzp"]
        ax.hist(d.clip(-0.06, 0.06), bins=np.linspace(-0.06, 0.06, 41), color=C_AVA)
        ax.axvline(0, color="0.5", lw=0.8)
        ax.set_title(f"{r['filter']}: {r['frame_zp_median']:+.3f} ± {r['frame_zp_sd']:.3f}\n(n = {r['n_frames']})",
                     fontsize=8)
        ax.set_yticks([])
        ax.set_xlabel("ΔZP [mag]")
    fig.tight_layout()
    save(fig, out, name)
    plt.close(fig)


def fig_muscat(plt, mus, out, name):
    fs = list(dict.fromkeys(mus["filter"]))
    fig, axs = plt.subplots(1, max(len(fs), 1), figsize=(3.0 * max(len(fs), 1), 2.8), sharey=True)
    for ax, f in zip(np.atleast_1d(axs), fs):
        m = mus[mus["filter"] == f]
        bins = np.linspace(-0.05, 0.18, 47)
        ax.hist(m["raw"].clip(bins[0], bins[-1]), bins=bins, color=C_RAW, alpha=0.75,
                label=f"raw {np.median(m['raw']):+.3f}")
        ax.hist(m["intercal"].clip(bins[0], bins[-1]), bins=bins, histtype="step", color=C_AVA, lw=1.6,
                label=f"intercal {np.median(m['intercal']):+.3f}")
        ax.axvline(0, color="0.5", lw=0.8)
        ax.set_title(f"{f}  ({len(m)} nights)")
        ax.set_xlabel("MuSCAT − Sinistro [mag]")
        ax.legend(fontsize=7, frameon=False, loc="upper center")
    np.atleast_1d(axs)[0].set_ylabel("nights")
    fig.tight_layout()
    save(fig, out, name)
    plt.close(fig)


# ---------------------------------------------------------------------------
# LaTeX
# ---------------------------------------------------------------------------

def write_tex(path: Path, rel: str, name: str, res: pd.DataFrame, mus: pd.DataFrame, mjy: float, tag: str):
    def f3(v):
        return "--" if not np.isfinite(v) else f"${v:+.3f}$"

    rows = "\n".join(
        f"  {r['filter']} & {TRUTH_TEX[r['filter']]} & {r['n_stars']} & {f3(r['median'])} & {r['sd']:.3f} & "
        f"{f3(r['offset_agn'])}\\,$\\pm${r['offset_agn_err']:.3f} & {f3(r['gspc_offset_agn'])} & "
        f"{r['camera_rms']:.3f} & {r['zp_applied']:.3f} \\\\"
        .replace("nan", "--")
        for _, r in res.iterrows())
    good = res[res["filter"].isin(["up", "gp", "rp", "ip", "zs"])]
    bv = res[res["filter"].isin(["B", "V"])]
    mus_txt = ""
    if len(mus):
        mm = mus.groupby("filter")[["raw", "intercal"]].median()
        mus_txt = (f"MuSCAT measures the AGN ${mm['raw'].min():.2f}$--${mm['raw'].max():.2f}$\\,mag fainter than "
                   f"Sinistro on the same nights (8.9$''$ vs 10.5$''$ aperture: less host light); "
                   f"after the intercal correction the difference is $\\le{mm['intercal'].abs().max():.3f}$\\,mag "
                   f"(Fig.~\\ref{{fig:{tag}-muscat}}). ")
    y = res[res["filter"] == "Y"]
    y_txt = (f"$Y$ has only {int(y['n_epochs'].iat[0])} epochs and a {y['sd'].iat[0]:.2f}\\,mag star-to-star "
             "scatter against PS1 and is not yet usable. ") if len(y) else ""
    tex = rf"""% Generated by tools/check_absolute_calibration.py on {datetime.now(timezone.utc):%Y-%m-%d} -- do not edit by hand.
% \input{{{rel}/abscal_{tag}}} from docs/ (needs graphicx, booktabs).
\paragraph{{Independent check of the absolute calibration ({name}).}}
The PyTICS-calibrated comparison stars were compared with photometry that AVA never
uses: SDSS DR16 PSF magnitudes ($u\,g\,r\,i\,z$; $B$, $V$ through the Jordi et al.\ 2006
stellar transformations, themselves good to $\sim$0.02--0.03\,mag) and Pan-STARRS1 DR2
$y$ (Table~\ref{{tab:{tag}}}, Figs.~\ref{{fig:{tag}-stars}}--\ref{{fig:{tag}-summary}}).
Evaluated at the AGN colour ($g-i={res['agn_colour'].iat[0]:.2f}$), $u\,g\,r\,i\,z$ agree with SDSS to
$\le{good['offset_agn'].abs().max():.3f}$\,mag and $B$, $V$ to ${bv['offset_agn'].min():+.3f}$--${bv['offset_agn'].max():+.3f}$\,mag,
within the transformation uncertainty; the GSPC catalogue itself shows the same $B$, $V$
offset. Individual cameras agree to {good['camera_rms'].min():.3f}--{good['camera_rms'].max():.3f}\,mag rms
(Fig.~\ref{{fig:{tag}-cameras}}), and the per-frame zero points of the \texttt{{frame\_qc}} path
agree with the ensemble to $\le{res['frame_zp_median'].abs().max():.3f}$\,mag (Fig.~\ref{{fig:{tag}-framezp}}).
{mus_txt}{y_txt}The published fluxes use $f_\nu = 3631\,\mathrm{{Jy}}\times10^{{-0.4\,m_{{\rm AB}}}}$
(checked: ratio {mjy:.5f}). The comparison is limited by SDSS's own AB accuracy
($\sim$0.01--0.02\,mag, more in $u$) and tests point sources only; the AGN additionally
depends on the aperture host fraction and on emission lines within the filters.

\begin{{table}}[htbp]
  \centering\small
  \caption{{{name}: calibrated comparison stars minus external photometry (AB, mag).
  Median and robust $\sigma$ over stars; ``at AGN'' is a clipped linear fit in $g-i$ evaluated at
  the AGN colour (bootstrap error); GSPC is the reference catalogue against the same truth;
  camera rms is the scatter of per-camera offsets; ZP is the zero point applied to the AGN.}}
  \label{{tab:{tag}}}
  \begin{{tabular}}{{llrrrrrrr}}
  \toprule
  Filter & External & $N$ & Median & $\sigma$ & At AGN & GSPC & Camera rms & ZP \\
  \midrule
{rows}
  \bottomrule
  \end{{tabular}}
\end{{table}}

\begin{{figure}}[htbp]
  \centering
  \includegraphics[width=\textwidth]{{{rel}/abscal_01_stars.pdf}}
  \caption{{{name}: PyTICS-calibrated comparison stars minus SDSS DR16 ($B$, $V$ via
  Jordi et al.\ 2006) and PS1 DR2 $y$, against $g-i$. Red line: clipped linear fit; dashed:
  AGN colour; grey band: $\pm0.01$\,mag.}}
  \label{{fig:{tag}-stars}}
\end{{figure}}

\begin{{figure}}[htbp]
  \centering
  \includegraphics[width=0.75\textwidth]{{{rel}/abscal_02_summary.pdf}}
  \caption{{{name}: offset from the external photometry at the AGN colour, for the AVA
  calibration (filled) and for the GSPC reference catalogue (open).}}
  \label{{fig:{tag}-summary}}
\end{{figure}}

\begin{{figure}}[htbp]
  \centering
  \includegraphics[width=0.75\textwidth]{{{rel}/abscal_03_cameras.pdf}}
  \caption{{{name}: per-camera offset from the external photometry (median over stars of
  each star's median calibrated magnitude in that camera).}}
  \label{{fig:{tag}-cameras}}
\end{{figure}}

\begin{{figure}}[htbp]
  \centering
  \includegraphics[width=\textwidth]{{{rel}/abscal_04_frame_zp.pdf}}
  \caption{{{name}: per-frame zero point from \texttt{{frame\_qc}} minus the ensemble
  zero point of the same frame (median $\pm$ robust $\sigma$). The secondary peak in $r$ and
  $i$ is MuSCAT (few ZP stars in its small field); Sinistro frames sit at a constant offset.
  The AGN light curve uses the ensemble zero point only.}}
  \label{{fig:{tag}-framezp}}
\end{{figure}}

\begin{{figure}}[htbp]
  \centering
  \includegraphics[width=\textwidth]{{{rel}/abscal_05_muscat.pdf}}
  \caption{{{name}: AGN, MuSCAT minus Sinistro on the same night, before (filled) and
  after (open) the additive intercal correction.}}
  \label{{fig:{tag}-muscat}}
\end{{figure}}
"""
    path.write_text(tex)


# ---------------------------------------------------------------------------

@click.command()
@click.option("--phot-dir", type=click.Path(file_okay=False, path_type=Path),
              default=ROOT / "data/test_archive/photometry/Mrk_817", show_default=True)
@click.option("--qc-db", type=click.Path(dir_okay=False, path_type=Path),
              default=ROOT / "data/test_archive/frame_qc.sqlite", show_default=True)
@click.option("--out-dir", type=click.Path(file_okay=False, path_type=Path),
              default=ROOT / "docs/figures/abscal", show_default=True)
@click.option("--refresh", is_flag=True, help="Download SDSS / PS1 again.")
def main(phot_dir, qc_db, out_dir, refresh):
    target = yaml.safe_load((phot_dir / "target.yaml").read_text())
    tag = target["data_id"].lower().replace("_", "").replace("+", "p")
    ref = pd.read_csv(phot_dir / "reference_stars.csv")
    X = truth_table(phot_dir, ref, target, refresh, ["vizier.cfa.harvard.edu", "vizier.cds.unistra.fr"])
    meta = load_solutions(phot_dir)
    res, stars, cams, fzp, mus, mjy = analyse(phot_dir, qc_db, X, meta)

    out_dir.mkdir(parents=True, exist_ok=True)
    plt = _plt()
    fig_stars(plt, res, stars, out_dir, "abscal_01_stars")
    fig_summary(plt, res, out_dir, "abscal_02_summary")
    fig_cameras(plt, res, cams, out_dir, "abscal_03_cameras")
    fig_frame_zp(plt, res, fzp, out_dir, "abscal_04_frame_zp")
    fig_muscat(plt, mus, out_dir, "abscal_05_muscat")
    res.to_csv(out_dir / f"abscal_{tag}.csv", index=False, float_format="%.5f")
    rel = out_dir.resolve().relative_to((ROOT / "docs").resolve()).as_posix() \
        if (ROOT / "docs").resolve() in out_dir.resolve().parents else str(out_dir)
    write_tex(out_dir / f"abscal_{tag}.tex", rel, target["name"], res, mus, mjy, tag)

    pd.set_option("display.width", 200)
    click.echo(res[["filter", "truth", "n_stars", "median", "sd", "offset_agn", "offset_agn_err",
                    "gspc_offset_agn", "camera_rms", "frame_zp_median", "zp_applied", "zp_meta",
                    "zp_summary"]].round(4).to_string(index=False))
    bad = res[(res["zp_applied"] - res["zp_meta"]).abs() > 1e-4]
    stale = res[(res["zp_summary"] - res["zp_applied"]).abs() > 1e-4]
    click.echo(f"ZP applied == meta.json: {'yes' if bad.empty else 'NO ' + ','.join(bad['filter'])}; "
               f"absolute_zp.json: {'consistent' if stale.empty else 'STALE ' + ','.join(stale['filter'])}; "
               f"mJy ratio {mjy:.5f}")
    click.echo(f"Wrote {out_dir}/abscal_0[1-5]_*.{{pdf,png}}, abscal_{tag}.csv, abscal_{tag}.tex")


if __name__ == "__main__":
    main()
