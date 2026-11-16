"""Mrk 817 PyTICS input from the new products (QC-pass frames)."""
import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/juan/astro/AVA")
import pandas as pd
from pathlib import Path
from ava.photometry.store import load_pytics
PHOT = Path("/Users/juan/astro/AVA/data/test_archive/photometry/Mrk_817")
DB = Path("/Users/juan/astro/AVA/data/test_archive/frame_qc.sqlite")
def load(filt, mjd_range=None):
    d = load_pytics(PHOT, DB, "Mrk_817", filt=filt, qc_only=True)
    d["scope"] = d["telid"].astype(str) + "-" + d["camera"].astype(str)
    if mjd_range:
        d = d[(d.MJD >= mjd_range[0]) & (d.MJD < mjd_range[1])]
    return d.reset_index(drop=True)
if __name__ == "__main__":
    d = load(sys.argv[1], (float(sys.argv[2]), float(sys.argv[3])))
    d.to_parquet(sys.argv[4]); print(len(d), "rows", d.frame.nunique(), "frames", d.star_id.nunique(), "stars", d.scope.nunique(), "scopes:", sorted(d.scope.unique()))
