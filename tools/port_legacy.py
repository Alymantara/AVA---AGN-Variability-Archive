"""Copy the old pipeline's SExtractor catalogues and raw FLOYDS frames into the new archive layout.

    python tools/port_legacy.py                                   # dry run: counts per target, nothing copied
    python tools/port_legacy.py --write                           # copy
    python tools/port_legacy.py --write --link                    # hard links instead (same filesystem only)
    python tools/port_legacy.py --photo-root /data3/jvhs1/agn --spec-root /data2/jvhs1/agn --only photo

Old layout (``__old_pipeline__``: ava_calibrate.py, ava_floyds_sort.py):

* photometry catalogues  ``<photo-root>/<folder>/sextractor_ava/<frame>_cat.fits``
* FLOYDS raw frames      ``<spec-root>/raw_data/<folder>_spec/all_spec/<YYYYMMDD>/*.fits.fz`` (and the sorted
  ``<YYYYMMDD>_<n>/`` copies), standards in ``<spec-root>/all_standards/<YYYYMMDD>/``

``<folder>`` is the old ``directory`` name (``database_all_targets.txt``), which is not always the new
``data_id`` (e.g. ``1H1934-063`` vs ``1H_1934-063``).  So files are NOT placed by folder: every file is looked up
by its frame name in the LCO archive databases (lcodb), which know each frame's AVA target:

* catalogue ``<frame>_cat.fits`` -> photometry DB ``frames.basename`` -> ``ava_data_id``
  -> ``cfg.sextractor_dir(data_id)/<frame>_cat.fits`` (imaging cameras only);
* raw FLOYDS ``<frame>.fits.fz`` (e00 / a00 / w00) -> spectra DB -> standard (``is_standard``) ->
  ``<spec raw>/standards/<night>/``, else ``<spec raw>/<ava_data_id>/<night>/`` (the layout the spectroscopy
  download step expects, so those frames are not downloaded again).

Files whose frame is not in the databases (other proposals, renamed objects) or not linked to an AVA target are
listed in the report (``--report``, CSV) and not copied.  Existing files of the same size are skipped; nothing is
overwritten or deleted.  The legacy folders are only read.
"""
import argparse
import os
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ava.config import cfg  # noqa: E402

RAW_SPEC_SUFFIXES = ("-e00.fits.fz", "-a00.fits.fz", "-w00.fits.fz")


def scan(root: Path, pattern_dirs, suffixes):
    """Yield files under ``root`` (os.scandir: fast on 10^5 files).  ``pattern_dirs(root)`` gives the folders."""
    for d in pattern_dirs(root):
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.is_file() and e.name.endswith(suffixes):
                        yield Path(e.path)
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            continue


def photo_dirs(root: Path):
    for t in sorted(p for p in root.iterdir() if p.is_dir()):
        if (t / "sextractor_ava").is_dir():
            yield t / "sextractor_ava"


def spec_dirs(root: Path):
    for t in sorted((root / "raw_data").glob("*_spec")):
        for night in sorted(t.glob("all_spec/20*")) + sorted(t.glob("20*")):
            if night.is_dir():
                yield night
    yield from sorted(p for p in (root / "all_standards").glob("20*") if p.is_dir())


def lookup(db: Path, sql: str) -> dict:
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        return {r[0]: r[1:] for r in con.execute(sql)}


def plan_photo(root: Path, db: Path, imaging: tuple) -> tuple[list, list, Counter]:
    from ava.photometry.process import imaging_frame_ok

    known = lookup(db, "SELECT basename, ava_data_id FROM frames")
    jobs, problems, seen = [], [], set()
    for f in scan(root, photo_dirs, ("_cat.fits",)):
        frame = f.name[: -len("_cat.fits")]
        if frame in seen:
            continue
        seen.add(frame)
        parts = frame.split("-")
        if len(parts) < 3 or not imaging_frame_ok(frame, prefixes=imaging):
            problems.append((str(f), "not an imaging camera"))      # incl. 0.4 m SBIG (photometry.camera_telescopes)
            continue
        hit = known.get(frame)
        if hit is None:
            problems.append((str(f), "frame not in the photometry database"))
        elif not hit[0]:
            problems.append((str(f), "frame not linked to an AVA target"))
        else:
            jobs.append((f, cfg.sextractor_dir(hit[0]) / f.name, hit[0], f.parent.parent.name))
    return jobs, problems, Counter()


def plan_spec(root: Path, db: Path) -> tuple[list, list, Counter]:
    known = lookup(db, "SELECT basename, ava_data_id, COALESCE(is_standard, 0), day_obs FROM frames WHERE rlevel = 0")
    raw_root = cfg.spec_raw("_").parent
    jobs, problems, seen = [], [], set()
    tars = Counter()
    for d in spec_dirs(root):
        tars[d.parent.parent.name if d.parent.name == "all_spec" else d.parent.name] += sum(
            1 for _ in d.glob("*.tar.gz"))
    for f in scan(root, spec_dirs, RAW_SPEC_SUFFIXES):
        frame = f.name[: -len(".fits.fz")]
        if frame in seen:
            continue
        seen.add(frame)
        hit = known.get(frame)
        if hit is None:
            problems.append((str(f), "frame not in the spectra database"))
            continue
        data_id, is_std, day = hit
        night = str(day or frame.split("-")[2]).replace("-", "")
        if is_std:
            jobs.append((f, raw_root / "standards" / night / f.name, "standards", f.parent.name))
        elif data_id:
            folder = f.parent.parent.parent.name if f.parent.parent.name == "all_spec" else f.parent.parent.name
            jobs.append((f, raw_root / data_id / night / f.name, data_id, folder))
        else:
            problems.append((str(f), "frame not linked to an AVA target"))
    return jobs, problems, Counter({k: v for k, v in tars.items() if v})


def place(src: Path, dst: Path, link: bool) -> str:
    if dst.exists():
        return "exists" if dst.stat().st_size == src.stat().st_size else "exists (different size: kept)"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if link:
        os.link(src, dst)
    else:
        part = dst.with_name(dst.name + ".part")
        shutil.copy2(src, part)
        part.replace(dst)
    return "copied"


def run(kind, jobs, problems, extra, write, link, workers):
    per = defaultdict(Counter)
    for src, dst, data_id, folder in jobs:
        per[data_id]["files"] += 1
        per[data_id]["already there"] += dst.exists()
    folders = defaultdict(set)
    for _, _, data_id, folder in jobs:
        folders[data_id].add(folder)
    print(f"\n== {kind}: {len(jobs)} file(s) for {len(per)} target(s); {len(problems)} not placed")
    for d in sorted(per):
        c = per[d]
        print(f"  {d:22s} {c['files']:8d} files  {c['already there']:8d} already there   from {sorted(folders[d])}")
    for why, n in Counter(w for _, w in problems).most_common():
        print(f"  not placed: {n:7d}  {why}")
    for folder, n in extra.items():
        print(f"  NOTE {folder}: {n} .tar.gz archive(s) (old downloads) — not unpacked; those frames will be downloaded")
    if not write:
        return Counter()
    with ThreadPoolExecutor(workers) as ex:
        out = Counter(ex.map(lambda j: place(j[0], j[1], link), jobs))
    print(f"  {kind}: {dict(out)}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--photo-root", default="/data3/jvhs1/agn", help="old photometry base folder")
    ap.add_argument("--spec-root", default="/data2/jvhs1/agn", help="old spectroscopy base folder")
    ap.add_argument("--only", choices=["photo", "spec"], help="one kind only")
    ap.add_argument("--write", action="store_true", help="copy (default: dry run)")
    ap.add_argument("--link", action="store_true", help="hard-link instead of copying (same filesystem)")
    ap.add_argument("--workers", type=int, default=8, help="parallel copies")
    ap.add_argument("--report", default="port_legacy_not_placed.csv", help="CSV of files not placed")
    a = ap.parse_args()

    from ava.lcodb.config import load_config
    from ava.photometry.process import IMAGING_PREFIXES

    lc = load_config(cfg.lcodb_config_path)
    problems_all = []
    if a.only in (None, "photo"):
        root = Path(a.photo_root)
        if not root.is_dir():
            sys.exit(f"photometry root not found: {root}")
        jobs, probs, extra = plan_photo(root, lc.db_path("photometry"), tuple(IMAGING_PREFIXES))
        run("photometry catalogues", jobs, probs, extra, a.write, a.link, a.workers)
        problems_all += [("photo", *p) for p in probs]
    if a.only in (None, "spec"):
        root = Path(a.spec_root)
        if not root.is_dir():
            sys.exit(f"spectroscopy root not found: {root}")
        jobs, probs, extra = plan_spec(root, lc.db_path("spectra"))
        run("FLOYDS raw frames", jobs, probs, extra, a.write, a.link, a.workers)
        problems_all += [("spec", *p) for p in probs]
    if problems_all:
        import csv

        with open(a.report, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["kind", "path", "reason"])
            w.writerows(problems_all)
        print(f"\nfiles not placed: {a.report}")
    if not a.write:
        print("\n(dry run: nothing copied; add --write)")


if __name__ == "__main__":
    main()
