"""What is left to do after porting the legacy data: per AVA target, the LCO frames still to download and extract
(photometry) or download and reduce (FLOYDS), from the lcodb databases and what is on disk.  Offline: no archive
request.

    python tools/backfill_status.py                       # all targets
    python tools/backfill_status.py --target Mrk_817 --apertures 200   # + aperture series of 200 catalogues
    python tools/backfill_status.py --csv backfill_status.csv

Photometry: frames wanted = linked to the target (``ava_data_id``), best reduction level (BANZAI 91), imaging
camera (``photometry.imaging_camera_prefixes``), science exposure in a ``photometry.filters`` filter.  A frame is
done when its catalogue exists; calibrated when it also has a ``frame_qc`` row at the current version.  Download
estimate: measured e91 sizes (Sinistro 37.8 MB; MuSCAT assumed 10 MB) at ``download.rate_per_s``.

FLOYDS: a science spectrum is on disk when its raw e00 is in ``<spec raw>/<target>/<night>/`` and reduced when its
``-1d`` exists in ``<spec>/<target>/reduced/<night>/``.

``--apertures N`` reads N catalogue headers per target and counts their aperture series (``APERDIAM``, else the
aperture count): a count that is neither 10 (pre-2025) nor 12-16 (current series) cannot be calibrated.
"""
import argparse
import os
import random
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ava.config import cfg  # noqa: E402

MB = {"fa": 37.8, "fl": 37.8, "fs": 37.8, "ep": 10.0}


def listdir(d: Path) -> set[str]:
    try:
        return set(os.listdir(d))
    except (FileNotFoundError, NotADirectoryError):
        return set()


def photometry(db: Path, frame_db: Path, targets, imaging, filters):
    from ava.photometry.process import PIPELINE_VERSION
    from ava.photometry.store import read_frame_qc

    q = (f"SELECT ava_data_id, basename, instrument_id FROM frames WHERE ava_data_id IS NOT NULL AND is_best = 1 "
         f"AND rlevel = 91 AND COALESCE(obstype, 'EXPOSE') = 'EXPOSE' "
         f"AND filter IN ({','.join('?' * len(filters))})")
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        rows = [r for r in con.execute(q, list(filters)) if str(r[2])[:2] in imaging]
    by = {}
    for d, b, inst in rows:
        by.setdefault(d, []).append((b, str(inst)[:2]))
    out = []
    for d in sorted(by):
        if targets and d not in targets:
            continue
        cats = {n[: -len("_cat.fits")] for n in listdir(cfg.sextractor_dir(d)) if n.endswith("_cat.fits")}
        raw = cfg.phot_raw(d)
        imgs = {n[: -len(".fits.fz")] for night in listdir(raw) for n in listdir(raw / night) if n.endswith(".fits.fz")}
        fq = read_frame_qc(frame_db, d) if frame_db and Path(frame_db).exists() else None
        done = set(fq.loc[fq["pipeline_version"] == PIPELINE_VERSION, "frame"]) if fq is not None and len(fq) else set()
        want = by[d]
        no_cat = [(b, c) for b, c in want if b not in cats]
        to_dl = [(b, c) for b, c in no_cat if b not in imgs]
        out.append(dict(data_id=d, frames=len(want), catalogues=sum(b in cats for b, _ in want),
                        to_extract_on_disk=len(no_cat) - len(to_dl), to_download=len(to_dl),
                        download_gb=sum(MB.get(c, 37.8) for _, c in to_dl) / 1e3,
                        calibrated=sum(b in done for b, _ in want),
                        to_calibrate=sum(b in cats and b not in done for b, _ in want)))
    return out


def spectra(db: Path, targets):
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        rows = con.execute("SELECT ava_data_id, basename, day_obs FROM frames WHERE ava_data_id IS NOT NULL "
                           "AND rlevel = 0 AND obstype = 'SPECTRUM' AND COALESCE(is_standard, 0) = 0").fetchall()
    by = {}
    for d, b, day in rows:
        by.setdefault(d, []).append((b, str(day).replace("-", "")))
    out = []
    for d in sorted(by):
        if targets and d not in targets:
            continue
        raw, red = cfg.spec_raw(d), cfg.spec_dir(d) / "reduced"
        st = [(f"{b}.fits.fz" in listdir(raw / n),
               any(x.startswith(b.replace("-e00", "-e91-1d")) for x in listdir(red / n))) for b, n in by[d]]
        out.append(dict(data_id=d, spectra=len(st), nights=len({n for _, n in by[d]}),
                        raw_on_disk=sum(r for r, _ in st), reduced=sum(x for _, x in st),
                        to_download=sum(not r and not x for r, x in st), to_reduce=sum(r and not x for r, x in st)))
    return out


def aperture_survey(targets, n):
    from ava.photometry.catalogs import APERDIAM_KEY, parse_aperdiam
    from astropy.io import fits

    print(f"\naperture series in {n} sampled catalogue(s) per target (APERDIAM, else aperture count):")
    for d in targets:
        cd = cfg.sextractor_dir(d)
        names = sorted(x for x in listdir(cd) if x.endswith("_cat.fits"))
        c = Counter()
        for x in random.Random(0).sample(names, min(n, len(names))):
            try:
                with fits.open(cd / x, memmap=False) as h:
                    diam = parse_aperdiam(h[0].header.get(APERDIAM_KEY))
                    k = len(diam) if diam else len(h[1].columns["MAG_APER"].array[0]) if len(h) > 1 and len(h[1].data) else 0
                    c[f"{k}{'' if diam else ' (count)'}"] += 1
            except Exception as exc:  # noqa: BLE001
                c[f"unreadable ({type(exc).__name__})"] += 1
        bad = sum(v for k, v in c.items() if k.split()[0] not in {"10", "12", "13", "14", "15", "16"})
        print(f"  {d:22s} {dict(c)}" + (f"   <-- {bad} cannot be calibrated" if bad else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", action="append", help="data_id (repeatable)")
    ap.add_argument("--apertures", type=int, default=0, help="sample N catalogues per target for their apertures")
    ap.add_argument("--csv", help="write the photometry and spectra tables (two files: _phot / _spec)")
    a = ap.parse_args()

    import pandas as pd

    from ava.lcodb.config import load_config
    from ava.photometry.process import IMAGING_PREFIXES

    lc = load_config(cfg.lcodb_config_path)
    cc = cfg._raw.get("photometry", {}).get("calibration", {}) or {}
    frame_db = cfg._resolve(cc["frame_db"]) if cc.get("frame_db") else lc.db_path("photometry")
    filters = list(cfg.photometry.filters)
    p = pd.DataFrame(photometry(lc.db_path("photometry"), frame_db, a.target, tuple(IMAGING_PREFIXES), filters))
    s = pd.DataFrame(spectra(lc.db_path("spectra"), a.target))
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 500)
    print(f"PHOTOMETRY (filters {filters})")
    if len(p):
        print(p.to_string(index=False, float_format=lambda x: f"{x:.1f}"))
        n, gb = int(p.to_download.sum()), p.download_gb.sum()
        rate = float(cfg.download.rate_per_s)
        print(f"TOTAL: {int(p.frames.sum())} frames; {int(p.catalogues.sum())} catalogued; "
              f"{int(p.to_extract_on_disk.sum())} on disk to extract; {n} to download ({gb / 1e3:.2f} TB, "
              f">= {n / rate / 86400:.1f} days at {rate:g} file/s); {int(p.to_calibrate.sum())} catalogued "
              f"but not calibrated")
    print("\nFLOYDS (science spectra)")
    if len(s):
        print(s.to_string(index=False))
        print(f"TOTAL: {int(s.spectra.sum())} spectra in {int(s.nights.sum())} target-nights; "
              f"{int(s.raw_on_disk.sum())} raw on disk; {int(s.to_download.sum())} to download; "
              f"{int(s.reduced.sum())} reduced")
    if a.csv:
        stem = a.csv[:-4] if a.csv.endswith(".csv") else a.csv
        p.to_csv(f"{stem}_phot.csv", index=False)
        s.to_csv(f"{stem}_spec.csv", index=False)
        print(f"\nwrote {stem}_phot.csv, {stem}_spec.csv")
    if a.apertures:
        aperture_survey(list(p.data_id) if len(p) else [], a.apertures)


if __name__ == "__main__":
    main()
