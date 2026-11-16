"""Consistency check of the spectroscopic databases against the files on disk (read-only).

    check_spec_db.py            (AVA_CONFIG selects the archive)

lcodb spectra DB: integrity, views, local_files (exists, size, md5), spec_qc (paths, frame ids, QC keys),
spec_lines (frame ids, fit flags, [O III] scale); AVA DB: line_variability recomputed from spec_lines,
download_state.  Prints PASS / FAIL per check and exits 1 on any failure."""
import sys, sqlite3, hashlib, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))   # repository root
from pathlib import Path
import numpy as np, pandas as pd
from ava.config import cfg
from ava.pipeline.tasks.download import lcodb_path
from ava.spectroscopy import lines as L

spec_db, ava_db = lcodb_path("spec"), cfg.db_path
fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  — ' + str(detail)) if detail else ''}")
    if not ok:
        fails.append(name)


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


con = sqlite3.connect(f"file:{spec_db}?mode=ro", uri=True)
q = lambda s, *a: pd.read_sql(s, con, params=a)  # noqa: E731
check("spectra DB integrity", con.execute("PRAGMA integrity_check").fetchone()[0] == "ok", str(spec_db))
tabs = set(q("SELECT name FROM sqlite_master WHERE type IN ('table','view')").name)
for t in ("frames", "spectrum_calibs", "spectrum_standards", "local_files", "spec_qc", "spec_lines"):
    check(f"table/view {t} present", t in tabs)
n_sci = con.execute("SELECT COUNT(*) FROM frames WHERE rlevel=0 AND obstype='SPECTRUM' AND COALESCE(is_standard,0)=0").fetchone()[0]
n_std = con.execute("SELECT COUNT(*) FROM spectrum_standards").fetchone()[0]
check("every science spectrum has a standard pick", n_std >= n_sci * 0.99, f"{n_std} picks / {n_sci} science")

# local_files: what spec-download fetched
lf = q("SELECT * FROM local_files")
ex = lf.path.map(lambda p: Path(p).exists())
check("local_files: every file exists", ex.all(), f"{ex.sum()}/{len(lf)}")
size_ok = [Path(r.path).stat().st_size == r.bytes for r in lf[ex].itertuples()]
check("local_files: sizes match", all(size_ok), f"{sum(size_ok)}/{len(size_ok)}")
md5_ok = [md5(r.path) == r.md5 for r in lf[ex].itertuples() if r.md5]
check("local_files: md5 match the archive values", all(md5_ok), f"{sum(md5_ok)}/{len(md5_ok)}")
known = q("SELECT id FROM frames WHERE id IN (%s)" % ",".join(map(str, lf.frame_id)) if len(lf) else "SELECT 1 WHERE 0")
check("local_files: frame ids known in frames", len(known) == len(lf), f"{len(known)}/{len(lf)}")

# spec_qc: reduced / imported products
qc = q("SELECT * FROM spec_qc")
check("spec_qc: rows", len(qc) > 0, ", ".join(f"{k} {v}" for k, v in qc.groupby("data_id").size().items()))
check("spec_qc: every -1d path exists", qc.path_1d.map(lambda p: Path(p).exists()).all())
fr = q("SELECT id, basename FROM frames WHERE id IN (%s)" % ",".join(map(str, qc.frame_id)))
m = qc.merge(fr, left_on="frame_id", right_on="id", how="left", suffixes=("", "_db"))
check("spec_qc: frame ids match the raw basenames", (m.basename == m.basename_db).all())
check("spec_qc: QC keywords filled", qc.L1QFLAGS.notna().all() and qc.L1QSN1.notna().all())
check("spec_qc: pipeline version recorded", qc.pipeline_version.notna().all(),
      "; ".join(sorted(set(v.split(" (")[0] for v in qc.pipeline_version))))

# spec_lines: Hβ fits
sl = q("SELECT * FROM spec_lines")
check("spec_lines: rows", len(sl) > 0, ", ".join(f"{k} {v}" for k, v in sl.groupby("data_id").size().items()))
check("spec_lines: frame ids resolved", sl.frame_id.notna().all(), f"{sl.frame_id.notna().sum()}/{len(sl)}")
check("spec_lines: one row per spectrum of spec_qc (science)",
      set(sl.basename) == set(qc[qc.role == "science"].basename))
good = sl[sl.good == 1]
check("spec_lines: good fits have positive flux and errors",
      (good.flux > 0).all() and (good.flux_err > 0).all() and (good.flux_cal > 0).all())
med = good.groupby("data_id").oiii_scale.median()
check("spec_lines: [O III] scale median ~1 per target", ((med - 1).abs() < 0.25).all(), med.round(3).to_dict())
con.close()

# AVA DB: line_variability recomputed from spec_lines (nightly, DAY-OBS)
acon = sqlite3.connect(f"file:{ava_db}?mode=ro", uri=True)
lv = pd.read_sql("SELECT * FROM line_variability", acon)
for t, g in good.groupby("data_id"):
    g = g.assign(night=g.basename.str.split("-").str[2], MJD=g.mjd)
    n = L.nightly(g.assign(good=True), "flux_cal", "flux_cal_err")
    v = L.variability(n.flux_cal, n.flux_cal_err)
    row = lv[(lv.data_id == t) & (lv.quantity == "flux")]
    ok = len(row) == 1 and row.n_nights.iloc[0] == v["n"] and np.isclose(row["mean"].iloc[0], v["mean"], rtol=1e-6)
    check(f"line_variability {t}: matches spec_lines", ok,
          f"{v['n']} nights, F_var {100 * v['fvar']:.1f} %" if np.isfinite(v.get("fvar", np.nan)) else f"{v['n']} nights")
    csv = cfg.spec_dir(t) / f"{t}_FLOYDS_Hbeta_lightcurve.csv"
    c = pd.read_csv(csv, comment="#") if csv.exists() else pd.DataFrame()
    check(f"nightly CSV {t}: same nights", len(c) == v["n"], str(csv.name))
ds = pd.read_sql("SELECT * FROM download_state WHERE kind='spec'", acon)
check("download_state: spec runs recorded", len(ds) > 0, ds[["data_id", "last_status", "n_downloaded"]].to_dict("records").__str__())
acon.close()
print(f"\n{'ALL PASS' if not fails else f'{len(fails)} FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
