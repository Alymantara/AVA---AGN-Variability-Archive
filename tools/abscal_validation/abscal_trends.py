"""Residual trends of the absolute calibration (Mrk 817): magnitude, colour, airmass, time, camera.

Star residual  r = m_GSPC - m_cal,  m_cal = mag_inst - DMAGT - DMAGS - CK (c - c0) + ZP + C (c - c0)
(per epoch), or the ensemble mean version from pytics/absolute_zp_stars.parquet.
Per-frame colour slope s_f: fit r = a_f + s_f (c - c0) over the frame's stars -> the error of the AGN
(colour c_AGN) in that frame relative to the comparison stars is ~ s_f (c_AGN - c0).
Read-only: measurements.parquet, pytics/*, frame_qc.sqlite.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
FILTER_TO_BAND = dict(up="u", B="B", gp="g", V="V", rp="r", ip="i", zs="z", Y="Y")


class Solution:   # minimal reader of pytics/<f>/ (avoids importing numba)
    def __init__(self, d):
        self.epochs = pd.read_parquet(d / "epochs.parquet")
        self.scopes = pd.read_parquet(d / "scopes.parquet")
        self.meta = json.loads((d / "meta.json").read_text())

    @classmethod
    def load(cls, d):
        return cls(d)


def solution_dir(ph, f):
    return ph / "pytics" / f

PH = ROOT / "data/test_archive/photometry/Mrk_817"
DB = ROOT / "data/test_archive/frame_qc.sqlite"
OUT = Path(sys.argv[1])
FILTERS = ["up", "B", "gp", "V", "rp", "ip", "zs"]
zpj = json.loads((PH / "pytics/absolute_zp.json").read_text())
ref = pd.read_csv(PH / "reference_stars.csv")
ref = ref[ref["quality_ok"].astype(bool) & ~ref["is_agn"].astype(bool)].copy()
ref["c"] = ref["lco_g"] - ref["lco_i"]
meas = pd.read_parquet(PH / "measurements.parquet", columns=["frame", "star_id", "is_agn", "mag_inst", "magerr", "sex_flags"])
import sqlite3
qc = pd.read_sql("select frame, filter, camera, tel, site, mjd_mid, airmass, fwhm_arcsec, qc_pass from frame_qc",
                 sqlite3.connect(f"file:{DB}?mode=ro", uri=True))

wt = lambda x: x  # noqa
summ, frames_all, mean_rows = [], [], []
for f in FILTERS:
    band = FILTER_TO_BAND[f]
    z = zpj[f]
    sol = Solution.load(solution_dir(PH, f))
    c_agn = z["agn_colour"]
    # ---------- ensemble means (absolute_zp_stars) ----------
    s = pd.read_parquet(PH / "pytics/absolute_zp_stars.parquet")
    s = s[(s["filter"] == f)]
    u = s[s["used"]]
    # magnitude trend (used stars)
    pm = np.polyfit(u["m_star"] - u["m_star"].median(), u["res"], 1, w=1 / u["sig"])
    # colour curvature: quadratic in (c - c0) on top of the linear term
    pq = np.polyfit(u["c"] - z["c0"], u["res"], 2, w=1 / u["sig"])
    blue = u[u["c"] < 0.6]
    for _, r in s.iterrows():
        mean_rows.append(dict(filter=f, star_id=r["star_id"], m=r["m_star"], c=r["c"], res=r["res"], used=r["used"],
                              rms=r["rms_star"]))
    # ---------- per-epoch calibrated star mags ----------
    ep = sol.epochs[["frame", "scope", "DMAGT"]]
    sc = sol.scopes.set_index("scope")
    d = meas[meas["frame"].isin(ep["frame"]) & ~meas["is_agn"].astype(bool) & ((meas["sex_flags"] & 28) == 0)]
    d = d.merge(ep, on="frame").merge(ref[["star_id", f"lco_{band}", "c"]], on="star_id")
    d = d[d["star_id"].isin(u["star_id"])]           # stars used for the absolute ZP
    ck = sc["CK"] if (sol.meta.get("colour_terms") and "CK" in sc) else pd.Series(0.0, index=sc.index)
    c0p = sol.meta["c0"]
    d["mcal"] = (d["mag_inst"] - d["DMAGT"] - d["scope"].map(sc["DMAGS"]) - d["scope"].map(ck).fillna(0) * (d["c"] - c0p)
                 + z["zp"] + z["C"] * (d["c"] - z["c0"]))
    d["r"] = d[f"lco_{band}"] - d["mcal"]
    d["x"] = d["c"] - z["c0"]
    rows = []
    for fr, g in d.groupby("frame"):
        if len(g) < 6 or np.ptp(g["x"]) < 0.3:
            continue
        w = 1 / (g["magerr"] ** 2 + 0.01 ** 2)
        A = np.vstack([np.ones(len(g)), g["x"]]).T
        try:
            p = np.linalg.solve(A.T @ (A * w.to_numpy()[:, None]), A.T @ (w * g["r"]))
        except np.linalg.LinAlgError:
            continue
        rows.append(dict(frame=fr, a=p[0], s=p[1], n=len(g), med=np.median(g["r"])))
    fr = pd.DataFrame(rows).merge(qc, on="frame").merge(ep[["frame", "scope"]], on="frame")
    fr["agn_err"] = fr["a"] + fr["s"] * (c_agn - z["c0"])     # AGN-colour residual of the frame
    fr["year"] = pd.to_datetime(fr["mjd_mid"] - 40587, unit="D").dt.year
    fr["filt"] = f
    frames_all.append(fr)
    # airmass slope of the colour slope (second-order extinction) and of the AGN-colour residual
    ka = np.polyfit(fr["airmass"], fr["s"], 1)[0]
    kagn = np.polyfit(fr["airmass"], fr["agn_err"], 1)[0]
    kfw = np.polyfit(fr["fwhm_arcsec"].clip(0.5, 5), fr["agn_err"], 1)[0]
    yr = fr.groupby("year")["agn_err"].median()
    cam = fr.groupby("scope")["agn_err"].median()
    summ.append(dict(filter=f, n_used=len(u), mag_slope_mmag_per_mag=pm[0] * 1e3,
                     mag_range=f"{u['m_star'].min():.1f}-{u['m_star'].max():.1f}",
                     curv_mmag_per_mag2=pq[0] * 1e3, quad_at_agn_mmag=(np.polyval(pq, c_agn - z["c0"])) * 1e3,
                     n_blue_lt0p6=len(blue), blue_res_mmag=blue["res"].median() * 1e3 if len(blue) else np.nan,
                     frames=len(fr), colour_slope_med=fr["s"].median(), colour_slope_sd=fr["s"].std(),
                     dslope_dX=ka, agn_err_dX_mmag=kagn * 1e3, agn_err_dfwhm_mmag=kfw * 1e3,
                     agn_err_sd_mmag=fr["agn_err"].std() * 1e3,
                     year_range_mmag=(yr.max() - yr.min()) * 1e3, year_sd_mmag=yr.std() * 1e3,
                     camera_sd_mmag=cam[fr.groupby("scope").size() >= 20].std() * 1e3))
summ = pd.DataFrame(summ)
pd.concat(frames_all).to_csv(OUT / "trends_frames.csv", index=False)
pd.DataFrame(mean_rows).to_csv(OUT / "trends_star_means.csv", index=False)
summ.to_csv(OUT / "trends_summary.csv", index=False)
pd.set_option("display.width", 250)
print(summ.round(3).to_string(index=False))
