"""Linearity bias test v2 (Mrk 817): remove selection and seeing biases.

- Predicted peak: frame's peak-per-flux ratio (median over faint stars, peak < 20 % sat) x the star's EXPECTED
  flux (its median calibrated magnitude + the epoch/scope terms), so a star scattering bright in one frame
  does not also move into a higher peak bin (regression to the mean).
- Per-frame offset: residuals are taken relative to the median residual of the faint stars in the same frame,
  so anything common to all stars (seeing, aperture loss, the DMAGT weighting) cancels.
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PEAKS, OUT = Path(sys.argv[1]), Path(sys.argv[2])
PH = Path("/Users/juan/astro/AVA/data/test_archive/photometry/Mrk_817")
FQ = Path("/Users/juan/astro/AVA/data/test_archive/frame_qc.sqlite")
SAT = {"fa": 128000.0, "ep": 118000.0}
BANDS = ["up", "B", "gp", "V", "rp", "ip", "zs"]

pk = pd.read_parquet(PEAKS)
m = pd.read_parquet(PH / "measurements.parquet",
                    columns=["frame", "star_id", "is_agn", "mag_inst", "magerr", "x", "y", "sex_flags"])
m = m[~m.is_agn & ((m.sex_flags & 28) == 0)]
m["x"], m["y"] = m.x.round(2), m.y.round(2)
m = m.merge(pk, on=["frame", "x", "y"], how="inner")
fq = pd.read_sql("select frame, fwhm_arcsec from frame_qc where data_id='Mrk_817'", sqlite3.connect(FQ))
rows = []
for f in BANDS:
    d = PH / "pytics" / f
    if not (d / "epochs.parquet").exists():
        continue
    ep = pd.read_parquet(d / "epochs.parquet")[["frame", "scope", "DMAGT"]]
    sc = pd.read_parquet(d / "scopes.parquet").set_index("scope")["DMAGS"]
    x = m.merge(ep, on="frame")
    x["band"] = f
    x["off"] = x.DMAGT + x.scope.map(sc)
    x["mc"] = x.mag_inst - x.off
    x["fam"] = x.scope.str.split("-").str[1].str[:2]
    rows.append(x[["band", "fam", "star_id", "frame", "mc", "off", "mag_inst", "magerr", "peak"]])
X = pd.concat(rows, ignore_index=True).merge(fq, on="frame", how="left")
X["frac_obs"] = X.peak / X.fam.map(SAT)
key = ["band", "fam", "star_id"]
X["ref"] = X.groupby(key).mc.transform("median")
X["n"] = X.groupby(key).mc.transform("size")
X = X[X.n >= 30]
X["res"] = X.mc - X.ref
X["flux_exp"] = 10 ** (-0.4 * (X.ref + X.off))                 # expected flux (ADU/s scale of mag_inst)
faint = X.frac_obs < 0.2
ratio = (X.peak / X.flux_exp)[faint].groupby(X.frame[faint]).median()   # peak per unit flux: PSF + exptime
X["frac"] = X.frame.map(ratio) * X.flux_exp / X.fam.map(SAT)
foff = X[faint & (X.magerr < 0.02)].groupby("frame").res.median()
X["res_c"] = X.res - X.frame.map(foff)
X = X[X.frac.notna() & X.res_c.notna() & (X.magerr < 0.01)]
edges = np.array([0, .05, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0, 1.15])
X["bin"] = pd.cut(X.frac, edges)


def summ(df, by, col):
    g = df.groupby(by, observed=True)[col]
    s = pd.DataFrame({"n": g.size(), "med": g.median(),
                      "err": g.apply(lambda s: 1.2533 * 1.4826 * np.median(np.abs(s - s.median())) / np.sqrt(len(s)))})
    return s.reset_index()


A = summ(X, ["fam", "bin"], "res")       # v1-style, predicted peak only
B = summ(X, ["fam", "bin"], "res_c")     # + per-frame faint-star offset
for t in (A, B):
    t["mid"] = t.bin.apply(lambda b: b.mid)
A.to_csv(OUT / "lin_predicted_only.csv", index=False)
B.to_csv(OUT / "lin_corrected.csv", index=False)
Xb = X[X.frac < 0.2].copy()
Xb["fwbin"] = pd.cut(Xb.fwhm_arcsec, [0, 1.5, 2, 2.5, 3, 4.5])
C = summ(Xb, ["fam", "fwbin"], "res")    # does the raw residual depend on seeing?
C.to_csv(OUT / "lin_seeing.csv", index=False)
X[["band", "fam", "star_id", "frame", "frac", "frac_obs", "res", "res_c", "fwhm_arcsec"]].to_parquet(OUT / "lin_points.parquet")
print("stars:", X.groupby("fam").star_id.nunique().to_dict(), "points", len(X))
print("predicted peak, raw residual\n", A.drop(columns="bin").to_string())
print("predicted peak, frame-corrected\n", B.drop(columns="bin").to_string())
print("raw residual vs seeing (frac<0.2)\n", C.to_string())
