"""Mrk 817 PyTICS input from the new products (QC-pass frames)."""
import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))   # repository root
import pandas as pd
from pathlib import Path
from ava.config import cfg  # noqa: E402  (AVA_CONFIG selects the archive; AVA_TARGET the target)
from ava.pipeline.tasks.calibrate import frame_db_path  # noqa: E402
TARGET = __import__("os").environ.get("AVA_TARGET", "Mrk_817")
from ava.photometry.store import load_pytics
PHOT = cfg.phot_dir(TARGET)
DB = frame_db_path()
def load(filt, mjd_range=None):
    d = load_pytics(PHOT, DB, TARGET, filt=filt, qc_only=True)
    d["scope"] = d["telid"].astype(str) + "-" + d["camera"].astype(str)
    if mjd_range:
        d = d[(d.MJD >= mjd_range[0]) & (d.MJD < mjd_range[1])]
    return d.reset_index(drop=True)
if __name__ == "__main__":
    d = load(sys.argv[1], (float(sys.argv[2]), float(sys.argv[3])))
    d.to_parquet(sys.argv[4]); print(len(d), "rows", d.frame.nunique(), "frames", d.star_id.nunique(), "stars", d.scope.nunique(), "scopes:", sorted(d.scope.unique()))
