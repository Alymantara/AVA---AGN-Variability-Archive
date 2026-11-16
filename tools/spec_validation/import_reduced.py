"""Import already-reduced FLOYDS -1d products (e.g. the final v3 runs in ~/astro/floyds/work) into AVA:
copy the target's science -1d into <spec_root>/<target>/reduced/<YYYYMMDD>/ and add their QC rows to the
spec_qc table of the lcodb spectra DB (as the spec-reduce stage does).  No reduction is run.

    import_reduced.py <data_id> <processed_dir> [--version LABEL] [--dry-run]

Matches products to the target by the raw frame's ava_id in the spectra DB (basename -e91-1d → -e00).
Idempotent: existing identical files are skipped; QC rows are replaced."""
import argparse, filecmp, shutil, sqlite3, sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/Users/juan/astro/AVA")
from ava.config import cfg  # noqa: E402
from ava.pipeline.tasks.download import lcodb_path  # noqa: E402
from ava.spectroscopy import reduce as R  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("data_id"); ap.add_argument("processed_dir")
ap.add_argument("--version", default=None, help="pipeline_version label (default: from the fork checkout)")
ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()

entry = cfg.target_by_data_id(a.data_id)
if entry is None:
    sys.exit(f"{a.data_id!r} is not a known data_id")
db = lcodb_path("spec")
version = a.version or R.pipeline_version(cfg._raw["spectroscopy"]["reduction"].get("package"))
files = sorted(Path(a.processed_dir).glob("**/*-e91-1d.fits*"))
raw = {f.name.split(".fits")[0].replace("-e91-1d", "-e00"): f for f in files}
with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
    q = ",".join("?" * len(raw))
    match = {b: (i, std) for b, i, std in con.execute(
        f"SELECT basename, id, COALESCE(is_standard,0) FROM frames WHERE rlevel=0 AND ava_id=? AND basename IN ({q})",
        (int(entry["ava_id"]), *raw))}
now = datetime.now(timezone.utc).isoformat(timespec="seconds")
rows, copied, same = [], 0, 0
for base, (fid, std) in sorted(match.items()):
    if std:
        continue
    src = raw[base]
    night = base.split("-")[2]
    dest = cfg.spec_dir(a.data_id) / "reduced" / night / src.name
    if dest.exists() and filecmp.cmp(src, dest, shallow=False):
        same += 1
    elif not a.dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    why = R.validate_product(src)
    if why:
        print(f"  invalid {base}: {why}")
    rows.append(dict(frame_id=fid, basename=base, data_id=a.data_id, role="science",
                     day_obs=f"{night[:4]}-{night[4:6]}-{night[6:]}", path_1d=str(dest), path_2d=None,
                     reduced_utc=now, pipeline="banzai-floyds", pipeline_version=f"{version} (imported from {a.processed_dir})",
                     **R.read_qc(src)))
n = 0 if a.dry_run else R.write_qc(db, rows)
print(f"{a.data_id}: {len(files)} -1d in {a.processed_dir}; {len(rows)} science of this target "
      f"({len(raw) - len(match)} other objects/standards skipped); copied {copied}, identical {same}; "
      f"{n} QC rows → spec_qc{' (dry run)' if a.dry_run else ''}")
