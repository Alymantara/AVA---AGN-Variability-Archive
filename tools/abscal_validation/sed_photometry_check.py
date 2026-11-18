#!/usr/bin/env python
"""Empirical check: AVA AGN colours vs colours synthesised from same-night FLOYDS spectra.

For each spectrum with AVA photometry within ±--window days (PyTICS light curve, good epochs, all cameras
after intercal is NOT applied: Sinistro 'fa'/'fl' only, the reference cameras), compare adjacent-band colours:
  observed AVA            (median mag per band in the window)
  predicted AVA           m_LCO(spectrum) + a + C c_AGN   → what AVA should report if the model is right
  true reference system   m_ref(spectrum)
A grey slit loss cancels in colours; host light does not (6" slit x extraction vs the 10.5" aperture).

    PYSYN_CDBS=... python tools/abscal_validation/sed_photometry_check.py --sed <work from agn_sed_corrections> --out <work>
"""
import sys
from pathlib import Path

import click
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import synlib as S  # noqa: E402
from ava.config import cfg  # noqa: E402

PAIRS = [("B", "g"), ("g", "V"), ("V", "r"), ("g", "r"), ("r", "i"), ("i", "z")]


@click.command()
@click.option("--sed", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--out", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--window", default=1.0, show_default=True, help="days")
def main(sed, out, window):
    ep = pd.read_csv(sed / "sed_corr_epochs.csv")
    tr = pd.read_csv(sed / "sed_corr_transform.csv")
    tr = tr[tr.variant == "nominal"].set_index("band")
    F = S.Filters()
    rows = []
    for t, g in ep[ep.reduction == "ava"].groupby("target"):
        lcp = cfg.phot_root / t / "agn_lightcurve_pytics.parquet"
        if not lcp.exists():
            continue
        lc = pd.read_parquet(lcp)
        lc = lc[lc["good"] & lc["camera"].astype(str).str[:2].isin(["fa", "fl"])]
        lc["band"] = lc["Filter"].map({v: k for k, v in S.FILTER_OF.items()})
        c_agn = g["c_phot"].iloc[0]
        for _, s in g.iterrows():
            near = lc[(lc["MJD"] - s["MJD"]).abs() < window]
            if near.empty:
                continue
            obs = near.groupby("band")["mag"].median()
            nobs = near.groupby("band").size()
            w, fl, _, _ = S.read_floyds(next(Path(cfg.spec_root / t / "reduced").glob(f"*/{s['basename']}*-1d.fits*")), float(cfg.spectroscopy.products.prepspec.red_min_wavelength))
            W, Fx, _ = S.extend(w, fl, s["z"])  # fringe-corrected orders, spliced as in the products
            m = F.mags(W, Fx)
            for b1, b2 in PAIRS:
                if b1 not in obs or b2 not in obs:
                    continue
                pred = lambda b: m[f"lco_{b}"] + tr.loc[b, "a"] + tr.loc[b, "C"] * c_agn  # noqa: E731
                rows.append(dict(target=t, spectrum=s["basename"], MJD=s["MJD"], colour=f"{b1}-{b2}",
                                 n=int(min(nobs[b1], nobs[b2])),
                                 dt=float((near["MJD"] - s["MJD"]).abs().median()),
                                 obs=obs[b1] - obs[b2], pred_ava=pred(b1) - pred(b2),
                                 true_ref=m[f"ref_{b1}"] - m[f"ref_{b2}"], nat=m[f"lco_{b1}"] - m[f"lco_{b2}"]))
    r = pd.DataFrame(rows)
    out.mkdir(parents=True, exist_ok=True)
    r.to_csv(out / "sed_photometry_check.csv", index=False)
    if r.empty:
        print("no same-night photometry")
        return
    s = r.groupby(["target", "colour"])[["obs", "pred_ava", "true_ref", "nat"]].median()
    s["obs-pred_ava"] = s["obs"] - s["pred_ava"]
    s["obs-true_ref"] = s["obs"] - s["true_ref"]
    pd.set_option("display.width", 200)
    print((s * 1e3).round(0).astype(int).to_string())
    print(r.groupby("target")[["spectrum", "n", "dt"]].agg({"spectrum": "nunique", "n": "median", "dt": "median"}))


if __name__ == "__main__":
    main()
