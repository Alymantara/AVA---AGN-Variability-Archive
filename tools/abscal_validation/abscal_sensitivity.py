"""Sensitivity of the AGN zero point to absolute_clip / absolute_floor / absolute_max_rms_star / colour_term.
Uses a copy of ensemble.absolute_zp (source extracted, numba not needed). Read-only."""
import ast, json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; PH = ROOT / "data/test_archive/photometry/Mrk_817"
src = (ROOT / "ava/photometry/ensemble.py").read_text()
fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "absolute_zp")
code = ast.get_source_segment(src, fn).replace("    from ava.photometry.calibration import FILTER_TO_BAND\n", "")
ns = dict(np=np, pd=pd, Solution=object, FILTER_TO_BAND=dict(up="u", B="B", gp="g", V="V", rp="r", ip="i", zs="z", Y="Y"))
exec(code, ns); absolute_zp = ns["absolute_zp"]
class Sol: pass
ref = pd.read_csv(PH / "reference_stars.csv"); zpj = json.loads((PH / "pytics/absolute_zp.json").read_text())
rows = []
for f in ["up", "B", "gp", "V", "rp", "ip", "zs"]:
    s = Sol(); s.filter = f; s.stars = pd.read_parquet(PH / f"pytics/{f}/stars.parquet")
    c_agn = zpj[f]["agn_colour"]
    def zagn(**kw):
        z = absolute_zp(s, ref, **kw); return z["zp"] + z["C"] * (c_agn - z["c0"]), z["n"], z["C"]
    nom, n0, C0 = zagn()
    assert abs(nom - zpj[f]["zp_agn"]) < 2e-3, (f, nom, zpj[f]["zp_agn"])
    for k, vals in dict(clip=[2.0, 2.5, 3.0, 4.0, 5.0, 100.0], floor=[0.003, 0.005, 0.01, 0.02, 0.03],
                        max_rms_star=[0.01, 0.02, 0.03, 0.05, 0.1, 10.0], colour_term=[True, False]).items():
        for v in vals:
            z, n, C = zagn(**{k: v})
            rows.append(dict(filter=f, param=k, value=v, dzp_mmag=(z - nom) * 1e3, n=n, C=C))
r = pd.DataFrame(rows); r.to_csv(Path(sys.argv[1]) / "sensitivity.csv", index=False)
pd.set_option("display.width", 200)
print(r.pivot_table(index=["param", "value"], columns="filter", values="dzp_mmag")[["up","B","gp","V","rp","ip","zs"]].round(1).to_string())
print(r.pivot_table(index=["param", "value"], columns="filter", values="n")[["up","B","gp","V","rp","ip","zs"]].to_string())
