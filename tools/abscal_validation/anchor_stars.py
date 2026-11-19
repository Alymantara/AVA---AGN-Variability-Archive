"""Test: absolute ZP from ALL catalogue stars in the frames (not only the PyTICS comparison stars), with a
variability cut on the scatter in excess of the photometric noise.

For every star in measurements.parquet: m_e = mag_inst - DMAGT_e - DMAGS_scope [- CK_scope (c - c0)]
on QC-pass epochs of the stored solution (sex_flags & 28 == 0). Star mean = weighted mean; rms; noise =
median magerr; excess = sqrt(max(rms^2 - noise^2 - median(rms_t)^2, 0)).
Then the same fit as ensemble.absolute_zp (copied code) on: (A) the stored comparison stars [current], (B) all
stars with rms < 0.05 [all stars, old cut], (C) all stars with excess < 0.03 and >= 20 epochs [new].
Read-only. Usage: python anchors_all_stars.py OUT.csv field:filter ...
"""
import ast
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ava.config import cfg  # noqa: E402
PH = cfg.phot_root
src = (ROOT / "ava/photometry/ensemble.py").read_text()
fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "absolute_zp")
code = ast.get_source_segment(src, fn).replace("    from ava.photometry.calibration import FILTER_TO_BAND\n", "")
F2B = dict(up="u", B="B", gp="g", V="V", rp="r", ip="i", zs="z", Y="Y")
ns = dict(np=np, pd=pd, Solution=object, FILTER_TO_BAND=F2B)
exec(code, ns)
absolute_zp = ns["absolute_zp"]


class Sol:
    pass


def star_means(t, f):
    d = PH / t / "pytics" / f
    ep = pd.read_parquet(d / "epochs.parquet")
    sc = pd.read_parquet(d / "scopes.parquet").set_index("scope")
    meta = json.loads((d / "meta.json").read_text())
    ref = pd.read_csv(PH / t / "reference_stars.csv")
    meas = pd.read_parquet(PH / t / "measurements.parquet", columns=["frame", "star_id", "is_agn", "mag_inst", "magerr", "sex_flags"])
    m = meas[meas.frame.isin(ep.frame) & ~meas.is_agn.astype(bool) & ((meas.sex_flags & 28) == 0)]
    m = m.merge(ep[["frame", "scope", "DMAGT", "rms_t"]], on="frame")
    m["DMAGS"] = m.scope.map(sc["DMAGS"])
    if meta.get("colour_terms") and "CK" in sc:
        cmap = (ref.set_index("star_id")["lco_g"] - ref.set_index("star_id")["lco_i"])
        m["c"] = m.star_id.map(cmap)
        m["CK"] = m.scope.map(sc["CK"]).fillna(0) * (m["c"] - meta["c0"])
        m = m[m["c"].notna() | (m.scope.map(sc["CK"]).fillna(0) == 0)]
        m["CK"] = m["CK"].fillna(0)
    else:
        m["CK"] = 0.0
    m["mc"] = m.mag_inst - m.DMAGT - m.DMAGS - m.CK
    m = m[np.isfinite(m.mc) & (m.magerr > 0) & (m.magerr < 0.3)]
    w = 1 / (m.magerr ** 2 + m.rms_t ** 2 + 1e-6)
    m = m.assign(w=w, wm=w * m.mc)
    g = m.groupby("star_id")
    med = g.mc.median()
    mad = 1.4826 * (m.mc - m.star_id.map(med)).abs().groupby(m.star_id).median()
    s = pd.DataFrame({"n": g.size(), "m_star": med, "noise": g.magerr.median(), "rmst": g.rms_t.median()})
    s["rms_star"] = mad                     # robust scatter (MAD) of the star's calibrated magnitudes
    s["m_star_err"] = s.rms_star / np.sqrt(s.n)
    s["excess"] = np.sqrt(np.clip(s.rms_star ** 2 - s.noise ** 2 - s.rmst ** 2, 0, None))
    return s.reset_index(), ref, meta


def fit(t, f, stars, ref, **kw):
    so = Sol(); so.filter = f; so.stars = stars
    z = absolute_zp(so, ref, **kw)
    return z


def main():
    out = []
    for arg in sys.argv[2:]:
        t, f = arg.split(":")
        allst, ref, meta = star_means(t, f)
        comp = pd.read_parquet(PH / t / "pytics" / f / "stars.parquet")
        # check: our means reproduce PyTICS m_star for the comparison stars (up to a constant gauge)
        chk = comp.merge(allst[["star_id", "m_star"]], on="star_id", suffixes=("", "_ours"))
        dd = chk.m_star_ours - chk.m_star
        c_agn = json.loads((PH / t / "pytics/absolute_zp.json").read_text()).get(f, {}).get("agn_colour", meta.get("agn_colour", 0.5))
        A = fit(t, f, comp, ref)
        B = fit(t, f, allst, ref)
        C_in = allst[(allst.n >= 20)].copy()
        C_in["rms_star"] = C_in["excess"]                 # cut on excess scatter instead of raw scatter
        C = fit(t, f, C_in, ref, max_rms_star=0.03)
        # D: all stars detected in >= 50 % of the epochs; variability = scatter in excess of the typical scatter
        # of stars of the same brightness (running median of rms_star vs m_star); cut at 0.05 as now.
        D_in = allst[allst.n >= 0.5 * allst.n.max()].sort_values("m_star").copy()
        trend = D_in.rms_star.rolling(15, center=True, min_periods=5).median()
        D_in["rms_raw"] = D_in.rms_star
        D_in["rms_star"] = np.sqrt(np.clip(D_in.rms_star ** 2 - trend ** 2, 0, None))
        D_in["m_star_err"] = D_in.rms_raw / np.sqrt(D_in.n)
        D = fit(t, f, D_in, ref)
        for name, z, gauge in (("A_current", A, 0.0), ("B_all_rms", B, float(np.median(dd))), ("C_all_excess", C, float(np.median(dd))),
                               ("D_all_reltrend", D, float(np.median(dd)))):
            zp_agn = z["zp"] + z["C"] * (c_agn - z["c0"]) if np.isfinite(z["zp"]) else np.nan
            out.append(dict(field=t, filter=f, variant=name, n=z["n"], n_all=z["n_all"], scatter=z["scatter"],
                            C=z["C"], zp_agn=zp_agn + gauge, zp_agn_err=z["zp_err"],
                            check_dm_median=float(np.median(dd)), check_dm_sd=float(np.std(dd)), n_check=len(chk)))
    r = pd.DataFrame(out)
    r.to_csv(sys.argv[1], index=False)
    zA = r[r.variant == "A_current"].set_index(["field", "filter"]).zp_agn      # NaN when the current fit failed
    r["dzp_vs_A_mmag"] = (r.zp_agn - [zA.get((a, b), float("nan")) for a, b in zip(r.field, r.filter)]) * 1e3
    pd.set_option("display.width", 220)
    show = r.assign(scatter=(r.scatter * 1e3).round(1), zp_agn_err=(r.zp_agn_err * 1e3).round(1),
                    check_dm_sd=(r.check_dm_sd * 1e3).round(2), C=r.C.round(3), dzp_vs_A_mmag=r.dzp_vs_A_mmag.round(1))
    print(show[["field", "filter", "variant", "n", "n_all", "scatter", "C", "zp_agn_err", "dzp_vs_A_mmag", "check_dm_sd", "n_check"]].to_string(index=False))


if __name__ == "__main__":
    main()
