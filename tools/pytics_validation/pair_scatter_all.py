#!/usr/bin/env python
"""Point-to-point scatter of the PyTICS light curves of every AGN: are the error bars right and Gaussian?

Pairs of good epochs of the same band (read-only, from <photometry_root>/<target>/agn_lightcurve_pytics.parquet):

  same    consecutive epochs of one telescope+camera less than --max-dt-same minutes apart ("back to back").
          AGN variability over minutes is negligible, the camera offset cancels, so
              z = Δm / sqrt(σ1² + σ2²)
          should be N(0, 1) with the *random* error.  Four error definitions are tested:
              phot   SExtractor photometric error only (magerr)
              rand   PyTICS random error  σ_phot ⊕ rms_t           (mag_err_rand; QC file)
              total  PyTICS total error   σ_phot ⊕ rms_t ⊕ rms_sc   (mag_err; merged CSV)
              model  fitted error model, random part (mag_err_model_rand, ava.photometry.errors)
  cross   epochs of different telescope+camera less than --max-dt-cross days apart (same night), on the
          intercalibrated magnitudes (mag_ic) with the total error (the camera term must be included).

Statistics per group: N, robust σ_z (1.4826 MAD), plain σ_z, median z, fraction |z| > 3 and > 5 (Gaussian:
0.27 %, 5.7e-5 %), excess kurtosis of z / robust σ_z within |z| < 10, and the Anderson-Darling statistic of
z / robust σ_z (shape only).  Groups: all; band; band x camera family; target x band; bins of the predicted
error, magnitude, seeing, airmass, rms_t and Δt.

    python tools/pytics_validation/pair_scatter_all.py --out <work>      [--targets Mrk_817 ...]

Writes <work>/pairs_same.parquet, pairs_cross.parquet, stats_*.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import click
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ava.config import cfg  # noqa: E402

BAND = {"up": "u", "B": "B", "gp": "g", "V": "V", "rp": "r", "ip": "i", "zs": "z", "Y": "Y"}
ORDER = ["u", "B", "g", "V", "r", "i", "z", "Y"]
ERRS = {"phot": "magerr", "rand": "mag_err_rand", "total": "mag_err", "model": "mag_err_model_rand"}


def rob(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(1.4826 * np.median(np.abs(x - np.median(x)))) if len(x) else np.nan


def zstats(z) -> dict:
    z = np.asarray(z, float)
    z = z[np.isfinite(z)]
    n = len(z)
    if n < 10:
        return dict(n=n)
    s = rob(z)
    u = z / s
    core = u[np.abs(u) < 10]
    ad = stats.anderson(core[:20000] if len(core) > 20000 else core, dist="norm").statistic
    return dict(n=n, sig_rob=s, sig_std=float(np.std(z)), med=float(np.median(z)),
                f3=float(np.mean(np.abs(z) > 3)), f5=float(np.mean(np.abs(z) > 5)),
                f3_rob=float(np.mean(np.abs(u) > 3)), kurt=float(stats.kurtosis(core)), ad=float(ad))


def load(t: str) -> pd.DataFrame | None:
    p = cfg.phot_dir(t) / "agn_lightcurve_pytics.parquet"
    if not p.exists():
        return None
    lc = pd.read_parquet(p)
    lc = lc[lc["good"] & np.isfinite(lc["mag"].to_numpy(float))].copy()
    lc["target"] = t
    lc["band"] = lc["Filter"].map(BAND).fillna(lc["Filter"])
    lc["fam"] = lc["camera"].astype(str).str.extract(r"^([A-Za-z]+)")[0]
    for c in ERRS.values():
        if c not in lc:
            lc[c] = np.nan
    if "mag_ic" not in lc:
        lc["mag_ic"] = lc["mag"]
    return lc


def same_pairs(lc: pd.DataFrame, max_dt_min: float) -> pd.DataFrame:
    out = []
    for (b, sc), h in lc.groupby(["band", "scope"]):
        h = h.sort_values("MJD")
        if len(h) < 2:
            continue
        a, c = h.iloc[:-1].reset_index(drop=True), h.iloc[1:].reset_index(drop=True)
        dt = (c["MJD"] - a["MJD"]).to_numpy() * 1440
        ok = dt < max_dt_min
        if not ok.any():
            continue
        a, c = a[ok].reset_index(drop=True), c[ok].reset_index(drop=True)
        r = pd.DataFrame({"target": a["target"], "band": b, "scope": sc, "fam": a["fam"], "MJD": a["MJD"],
                          "dt_min": dt[ok], "dm": (c["mag"] - a["mag"]).to_numpy(), "mag": (a["mag"] + c["mag"]) / 2,
                          "seeing": (a["seeing"] + c["seeing"]) / 2, "airmass": (a["airmass"] + c["airmass"]) / 2,
                          "rms_t": np.hypot(a["rms_t"], c["rms_t"]) / np.sqrt(2),
                          "n_stars": np.minimum(a["n_stars"], c["n_stars"]),
                          "mag_inst": np.minimum(a["mag_inst"], c["mag_inst"])})   # brighter of the two
        for k, col in ERRS.items():
            r[f"e_{k}"] = np.hypot(a[col].to_numpy(float), c[col].to_numpy(float))
            r[f"z_{k}"] = r["dm"] / r[f"e_{k}"]
        out.append(r)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def cross_pairs(lc: pd.DataFrame, max_dt_d: float) -> pd.DataFrame:
    """Nearest epoch of a different scope within max_dt_d (each epoch at most once as the first member)."""
    out = []
    for b, h in lc.groupby("band"):
        h = h.sort_values("MJD").reset_index(drop=True)
        t, sc = h["MJD"].to_numpy(), h["scope"].to_numpy()
        for j in (1, 2, 3):
            k = np.arange(len(h) - j)
            ok = (t[k + j] - t[k] < max_dt_d) & (sc[k] != sc[k + j])
            k = k[ok]
            if not len(k):
                continue
            a, c = h.iloc[k].reset_index(drop=True), h.iloc[k + j].reset_index(drop=True)
            out.append(pd.DataFrame({
                "target": a["target"], "band": b, "fam1": a["fam"], "fam2": c["fam"], "MJD": a["MJD"],
                "dt_d": c["MJD"] - a["MJD"], "dm": c["mag_ic"] - a["mag_ic"],
                "e_total": np.hypot(a["mag_err"], c["mag_err"]), "e_rand": np.hypot(a["mag_err_rand"], c["mag_err_rand"]),
                "lag": j}))
    if not out:
        return pd.DataFrame()
    x = pd.concat(out, ignore_index=True).drop_duplicates(["target", "band", "MJD"])
    x["z_total"], x["z_rand"] = x["dm"] / x["e_total"], x["dm"] / x["e_rand"]
    x["pair"] = np.where(x["fam1"] == x["fam2"], x["fam1"] + "-" + x["fam2"], "mixed")
    return x


def table(P: pd.DataFrame, by, zcols) -> pd.DataFrame:
    rows = []
    groups = [((), P)] if not by else P.groupby(by, observed=True)
    for key, g in groups:
        key = key if isinstance(key, tuple) else (key,)
        for zc in zcols:
            rows.append({**dict(zip(by, key)), "err": zc.replace("z_", ""), **zstats(g[zc])})
    return pd.DataFrame(rows)


@click.command()
@click.option("--out", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--targets", multiple=True)
@click.option("--max-dt-same", default=60.0, show_default=True, help="minutes")
@click.option("--max-dt-cross", default=0.25, show_default=True, help="days")
def main(out, targets, max_dt_same, max_dt_cross):
    out.mkdir(parents=True, exist_ok=True)
    names = targets or sorted(p.parent.name for p in cfg.phot_root.glob("*/agn_lightcurve_pytics.parquet"))
    S, X = [], []
    for t in names:
        lc = load(t)
        if lc is None or lc.empty:
            continue
        s, x = same_pairs(lc, max_dt_same), cross_pairs(lc, max_dt_cross)
        S.append(s); X.append(x)
        print(f"{t:16s} epochs {len(lc):6d}  back-to-back pairs {len(s):6d}  cross-camera pairs {len(x):5d}")
    S = pd.concat(S, ignore_index=True)
    X = pd.concat([x for x in X if len(x)], ignore_index=True)
    S.to_parquet(out / "pairs_same.parquet", index=False)
    X.to_parquet(out / "pairs_cross.parquet", index=False)
    zc = [f"z_{k}" for k in ERRS]
    S["band"] = pd.Categorical(S["band"], ORDER)
    X["band"] = pd.Categorical(X["band"], ORDER)
    table(S, [], zc).to_csv(out / "stats_same_all.csv", index=False)
    table(S, ["band"], zc).to_csv(out / "stats_same_band.csv", index=False)
    table(S, ["band", "fam"], zc).to_csv(out / "stats_same_band_fam.csv", index=False)
    table(S, ["target", "band"], ["z_rand", "z_model"]).to_csv(out / "stats_same_target_band.csv", index=False)
    for v, edges in [("e_rand", np.r_[0, 0.004, 0.006, 0.008, 0.01, 0.015, 0.02, 0.03, 0.05, 0.1, 1]),
                     ("mag", None), ("seeing", np.r_[0, 1.5, 2, 2.5, 3, 4, 10]),
                     ("airmass", np.r_[1, 1.2, 1.4, 1.6, 2, 3]), ("rms_t", np.r_[0, 0.002, 0.004, 0.008, 0.015, 0.03, 0.1]),
                     ("dt_min", np.r_[0, 2, 5, 10, 20, 40, 60])]:
        S["bin"] = pd.qcut(S[v], 8, duplicates="drop") if edges is None else pd.cut(S[v], edges)
        tb = table(S, ["band", "bin"], ["z_phot", "z_rand", "z_model"])
        tb["bin_mid"] = [iv.mid if hasattr(iv, "mid") else np.nan for iv in tb["bin"]]
        tb.assign(var=v).to_csv(out / f"stats_same_by_{v}.csv", index=False)
    table(X, ["band"], ["z_total", "z_rand"]).to_csv(out / "stats_cross_band.csv", index=False)
    table(X, ["band", "pair"], ["z_total"]).to_csv(out / "stats_cross_band_pair.csv", index=False)
    pd.set_option("display.width", 220)
    print(pd.read_csv(out / "stats_same_band.csv").round(3).to_string(index=False))
    print(pd.read_csv(out / "stats_cross_band.csv").round(3).to_string(index=False))


if __name__ == "__main__":
    main()
