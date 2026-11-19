#!/usr/bin/env python
"""Export the calibration study for the website (web/calibration.php).

Reads the outputs of agn_sed_corrections.py (and optionally abscal_ps1_apass.py) and writes one compact JSON
file to ``web.calibration_src`` (default data/products/calibration/calibration.json); ``tools/publish_web.py``
(pipeline -w) copies it to ``<web.data_dir>/calibration/calibration.json``.

    PYSYN_CDBS=... python tools/abscal_validation/export_web.py --sed <work> [--ext <work>/ext]
        [--trends <work>/trends] [--out FILE]

Contents: per-target, per-band corrections (true − AVA in the reference system, line part, line fractions,
flux factors, natural-system shift), thinned median spectra with continuum, LCO and reference passbands, a
redshift scan of each spectrum, the star-based accuracy (when --ext is given) and the per-star residuals of
the test field (when --trends is given).
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import synlib as S  # noqa: E402
from ava.config import cfg  # noqa: E402

MAIN = ["B", "g", "V", "r", "i"]
FILTER_OF = S.FILTER_OF


def r3(x, nd=4):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def thin_curve(wt, frac=0.01, n=160):
    w, t = wt
    lo, hi = S.span(wt, frac)
    g = np.linspace(lo - 50, hi + 50, n)
    tt = np.interp(g, w, t, left=0, right=0) / t.max()
    return [[round(float(a), 1), round(float(b), 4)] for a, b in zip(g, tt)]


def passband_entry(lco, ref, b):
    return dict(lco=thin_curve(lco), ref=thin_curve(ref), ref_name=S.REF_LABEL[b],
                lco_half=[round(float(x)) for x in S.span(lco, 0.5)], ref_half=[round(float(x)) for x in S.span(ref, 0.5)])


TREND_BANDS = [("up", "u"), ("B", "B"), ("gp", "g"), ("V", "V"), ("rp", "r"), ("ip", "i"), ("zs", "z")]


def star_residuals(trends: Path, target: str) -> dict:
    """Per comparison star: Gaia GSPC magnitude and GSPC − AVA (abscal_trends.py trends_star_means.csv), by band."""
    s = pd.read_csv(trends / "trends_star_means.csv")
    ref = pd.read_csv(cfg.phot_dir(target) / "reference_stars.csv")
    out = {"target": target}
    for f, b in TREND_BANDS:
        q = s[s["filter"] == f].merge(ref[["star_id", f"lco_{b}"]], on="star_id", how="inner")
        q = q[np.isfinite(q[f"lco_{b}"]) & np.isfinite(q["res"])].sort_values(f"lco_{b}")
        if len(q):
            out[b] = dict(mag=[round(float(v), 3) for v in q[f"lco_{b}"]],
                          res=[round(float(v), 4) for v in q["res"]],
                          used=[bool(v) for v in q["used"]])
    return out


@click.command()
@click.option("--sed", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--ext", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--trends", type=click.Path(file_okay=False, path_type=Path), default=None,
              help="abscal_trends.py output: per-star residuals for the stars chart")
@click.option("--trends-target", default="Mrk_817", show_default=True)
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--bin", "binw", default=8.0, show_default=True, help="spectrum bin width (Å)")
def main(sed, ext, trends, trends_target, out, binw):
    web = cfg._raw.get("web", {}) or {}
    out = out or cfg._resolve(web.get("calibration_src") or "data/products/calibration/calibration.json")
    summ = pd.read_csv(sed / "sed_corr_summary.csv")
    ep = pd.read_csv(sed / "sed_corr_epochs.csv")
    tr = pd.read_csv(sed / "sed_corr_transform.csv")
    trn = tr[tr.variant == "nominal"].set_index("band")
    npz = np.load(sed / "sed_corr_mean_spectra.npz")
    F = S.Filters()

    targets = []
    spectra = {}
    zs = np.round(np.arange(0.0, 0.2001, 0.0025), 4)
    zscan = {}
    for t, g in summ.groupby("target", sort=False):
        ty = yaml.safe_load((cfg.spec_root / t / "target.yaml").read_text())
        e = ep[(ep.target == t) & (ep.reduction == "ava")]
        rec = dict(data_id=t, name=ty.get("name", t), ava_id=ty.get("ava_id"), z=r3(g["z"].iloc[0], 5),
                   n_spectra=int(len(e)), n_nights=int(e["basename"].str.split("-").str[2].nunique()),
                   mjd=[r3(e["MJD"].min(), 1), r3(e["MJD"].max(), 1)], bands={})
        for _, r in g.iterrows():
            err = float(np.hypot(r["sys_total"], r["dref_sd"]))
            rec["bands"][r["band"]] = dict(
                dref=r3(r["dref"]), err=r3(err), dline=r3(r["dline"]), sd=r3(r["dref_sd"]),
                linefrac_lco=r3(r["linefrac_lco"], 3), linefrac_ref=r3(r["linefrac_ref"], 3),
                flux_factor=r3(r["flux_corr_ref"]), dnat=r3(r["dnat"]),
                reliable=bool(r["band"] in MAIN))
        targets.append(rec)
        # thinned median spectrum (normalised at 5100 Å rest) and continuum
        w, f = npz[f"{t}__wave"], npz[f"{t}__flux"]
        c = npz[f"{t}__cont"]
        k = np.isfinite(f) & np.isfinite(c)
        w, f, c = w[k], f[k], c[k]
        edges = np.arange(w.min(), w.max() + binw, binw)
        idx = np.digitize(w, edges)
        ww, ff, cc = [], [], []
        for i in np.unique(idx):
            m = idx == i
            if m.sum() >= 2:
                ww.append(w[m].mean()); ff.append(np.median(f[m])); cc.append(np.median(c[m]))
        spectra[t] = dict(wave=[round(float(x), 1) for x in ww], flux=[round(float(x), 4) for x in ff],
                          cont=[round(float(x), 4) for x in cc])
        # redshift scan of this spectrum
        z0 = float(npz[f"{t}__z"])
        wr = w / (1 + z0)
        res = {b: [] for b in MAIN}
        for z in zs:
            Wx, Fx, _ = S.extend(wr * (1 + z), f, z)
            m = F.mags(Wx, Fx)
            for b in MAIN:
                res[b].append(r3((m[f"ref_{b}"] - m[f"lco_{b}"] - trn.loc[b, "a"] - trn.loc[b, "C"] * m["gi"]), 4))
        zscan[t] = res

    passbands = {b: passband_entry(F.lco[b], F.ref[b], b) for b in S.BANDS}
    passbands["Y"] = passband_entry(S.load_curve("lco", "Y"), S.load_curve("ref", "Y"), "Y")   # plots only

    stars = None
    if ext is not None and (ext / "ps1_apass_offsets.csv").exists():
        o = pd.read_csv(ext / "ps1_apass_offsets.csv")
        g = o[o["who"] == "GSPC"].set_index(["filter", "cat"])["offset_mmag"]
        stars = {}
        for f, b in [("up", "u"), ("gp", "g"), ("rp", "r"), ("ip", "i"), ("zs", "z")]:
            row = {}
            for cat in ("sdss", "ps1"):
                q = o[(o["who"] == "AVA") & (o["filter"] == f) & (o["cat"] == cat)]
                if len(q):
                    v = float(q["offset_mmag"].iloc[0])
                    if cat == "ps1":
                        v -= float(g.get((f, "ps1"), 0.0))
                    row[cat] = [r3(v / 1e3), r3(float(q["err_mmag"].iloc[0]) / 1e3)]
            stars[b] = row

    doc = dict(generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
               bands=MAIN, all_bands=S.BANDS, targets=targets, spectra=spectra, passbands=passbands,
               redshift_scan=dict(z=[float(z) for z in zs], curves=zscan), stars=stars,
               star_residuals=star_residuals(trends, trends_target) if trends is not None else None,
               transform={b: dict(a=r3(trn.loc[b, "a"]), C=r3(trn.loc[b, "C"]), C_emp=r3(trn.loc[b, "C_emp"]))
                          for b in S.BANDS},
               notes=dict(spectra="FLOYDS 6\" slit, fringe-corrected per-order fluxes (EXTRACTED), blue below "
                                  f"{cfg.spectroscopy.products.prepspec.red_min_wavelength:.0f} Å, red above"))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":"), allow_nan=False))
    tmp.replace(out)
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} kB): {len(targets)} targets")


if __name__ == "__main__":
    main()
