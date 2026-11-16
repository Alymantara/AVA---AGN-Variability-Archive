"""Run the ORIGINAL PyTICS (Astroberta/PyTICS, Filter.Corr) on a subset; save its solution."""
import sys, time, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, sys.argv[1])           # cloned repo root
import numpy as np, pandas as pd
from PyTICS.filter import Filter
d = pd.read_parquet(sys.argv[2])
AGN = int(d.loc[d.is_agn, "star_id"].iloc[0])
star_file = pd.DataFrame({"id_apass": d.star_id.values, "Filter": d.Filter.values, "MJD": d.MJD.values,
                          "telid": d.scope.values, "mag_aper": d.mag_inst.values.astype(float),
                          "err_aper": d.magerr.values.astype(float), "airmass": d.airmass.values, "seeing": d.seeing.values})
f = Filter(d.Filter.iloc[0], verbose=False)
t0 = time.time()
f.Corr(star_file, d.Filter.iloc[0], MAX_LOOPS=int(sys.argv[4]), bad_IDs=[AGN], safe=0.6, frac=0.5, AGN_ID=AGN, Star_Lim=100)
dt = time.time() - t0
f.zp = [0.0, 0.0]
agn = f.AGN_LC(Plot=False, Rem_out=False, AGN_ID=AGN)
f.DF.to_parquet(sys.argv[3] + "_stars.parquet"); agn.astype({"mag": float, "err": float, "MJD": float}).to_parquet(sys.argv[3] + "_agn.parquet")
print(f"ORIGINAL PyTICS: {dt:.1f} s, stars used {f.DF.id_apass.nunique()}, epochs {f.DF.MJD.nunique()}, loops {len(f.TR[0])}")
