import sys, time, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))   # repository root
import numpy as np, pandas as pd
from ava.photometry import ensemble as E
d = pd.read_parquet(sys.argv[1]); AGN = int(d.loc[d.is_agn, "star_id"].iloc[0])
E.fit(d.head(3000), agn_id=AGN, max_loops=2)  # jit warm-up
t0 = time.time(); sol = E.fit(d, agn_id=AGN, log=print, rms_err_floor=float(sys.argv[3]) if len(sys.argv) > 3 else 0.0, atol=0.0 if len(sys.argv) <= 3 or float(sys.argv[3]) == 0 else 1e-5); print("port seconds", round(time.time()-t0, 2))
o = pd.read_parquet(sys.argv[2] + "_stars.parquet"); oa = pd.read_parquet(sys.argv[2] + "_agn.parquet")
# stars
os_ = o.groupby("id_apass")[["m_star", "rms_star"]].first()
st = sol.stars.set_index("star_id")
print("star sets equal:", set(os_.index) == set(st.index), len(os_), len(st))
j = st.join(os_, rsuffix="_o", how="inner")
dm = j.m_star - j.m_star_o
print(f"m_star diff: median {dm.median():+.5f} std {dm.std()*1e3:.3f} mmag max|dev| {np.abs(dm-dm.median()).max()*1e3:.3f} mmag")
print(f"rms_star diff max {np.abs(j.rms_star - j.rms_star_o).max()*1e3:.3f} mmag")
# epochs: original keyed by MJD
oe = o.groupby("MJD")[["DMAGT", "DMAGS", "rms_t"]].first()
ep = sol.epochs.set_index("MJD")
k = ep.join(oe, rsuffix="_o", how="inner"); print("epochs matched", len(k), "of", len(ep))
print(f"DMAGT diff std {(k.DMAGT-k.DMAGT_o).std()*1e3:.3f} mmag, max {np.abs(k.DMAGT-k.DMAGT_o - (k.DMAGT-k.DMAGT_o).median()).max()*1e3:.3f}")
print(f"rms_t diff max {np.abs(k.rms_t-k.rms_t_o).max()*1e3:.3f} mmag")
print("scopes port\n", sol.scopes.to_string()); print("scopes orig\n", o.groupby("telid")[["DMAGS", "rms_sc"]].first())
a = E.apply(sol, d[d.is_agn]); a = a.merge(oa[["MJD", "mag", "err"]], on="MJD", suffixes=("", "_o"))
dd = a.mag - a.mag_o
print(f"AGN: n {len(a)}, diff median {dd.median():+.5f}, std {dd.std()*1e3:.3f} mmag, max|dev| {np.abs(dd-dd.median()).max()*1e3:.2e} mmag; err ratio median {(a.mag_err/a.err).median():.4f}")
a.to_parquet(sys.argv[2] + "_portcmp.parquet")
sol.save(sys.argv[2] + "_portsol")
