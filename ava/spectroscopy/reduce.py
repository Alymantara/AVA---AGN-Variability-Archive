"""
ava.spectroscopy.reduce — run the improved banzai-floyds (external environment) on downloaded nights,
file the products, and put the quality keywords in the spectra database.

The reduction runs in its own Python environment (``spectroscopy.reduction.python``: the fork needs
Python 3.12 + torch), as a subprocess with a clean environment (as ``floyds/work/banzai_run/benv``):

  1. calibration DB (once): ``banzai_floyds_offline setup-db`` and ``skyflats`` from
     ``skyflats_dir`` (the order trace of each site);
  2. staging: ``<work>/input/<target>_<run>/`` holds symlinks to the nights' raw frames
     (target science + arcs + flats, and the standards with their arcs + flats);
  3. ``banzai_floyds_offline chain`` → ``<work>/processed/<site>/<camera>/<night>/processed/``
     (arcs, lamp flats, phase masters, standards, residual templates, science);
  4. the target's science -1d/-2d are moved to ``<spec_root>/<target>/reduced/<YYYYMMDD>/``;
     calibrations and standards stay in the shared ``<work>/processed`` tree (the calibration DB
     points at them);
  5. QC: every -1d (science and standard) → table ``spec_qc`` of the lcodb spectra DB, one row
     per raw frame: product paths, pipeline version, the L1Q keywords (docs/QC_KEYWORDS.md of
     the fork), observing conditions and the other L1 keywords (``header_json``).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

#: L1Q / condition keywords stored as columns (the rest of the L1* header goes to header_json)
QC_COLUMNS = ["L1QSN1", "L1QSN2", "L1QXJ1", "L1QXJ2", "L1QBJ1", "L1QBJ2", "L1QCR1", "L1QCR2", "L1QCRLN", "L1QCRLP",
              "L1QCRB1", "L1QCRB2", "L1QSEE1", "L1QSEE2", "L1QPOFF", "L1QSTDGR", "L1QSTDDT", "L1QSTDSP", "L1QFLAG",
              "L1QFLAGS", "L1QVER", "L1TRCMOD", "L1TRCADR", "L1FRGRES", "L1FLXNST", "L1FLXGRY", "L1WZP1", "L1WZP2",
              "L1OBJDET", "L1CRMETH", "AIRMASS", "AGFWHM", "MOONFRAC", "MOONDIST", "WMSCLOUD", "SKYMAG", "APERWID",
              "OBJECT", "DATE-OBS", "EXPTIME"]

SPEC_QC_DDL = """
CREATE TABLE IF NOT EXISTS spec_qc (        -- one row per reduced raw spectrum (AVA ava.spectroscopy.reduce)
    frame_id INTEGER PRIMARY KEY,           -- raw (e00) archive frame id
    basename TEXT, data_id TEXT, role TEXT, day_obs TEXT,
    path_1d TEXT, path_2d TEXT, reduced_utc TEXT, pipeline TEXT, pipeline_version TEXT,
    {cols},
    header_json TEXT
);
""".format(cols=",\n    ".join(f'"{c}" {"TEXT" if c in ("L1QFLAGS", "L1TRCMOD", "L1CRMETH", "OBJECT", "DATE-OBS") else "REAL"}'
                               for c in QC_COLUMNS))


def clean_env(python: str) -> dict:
    """The environment the reduction runs in: its own bin first, nothing from the caller's conda."""
    return {"HOME": os.environ.get("HOME", ""), "PATH": f"{Path(python).parent}:/usr/bin:/bin:/usr/sbin:/sbin",
            "OPENTSDB_PYTHON_METRICS_TEST_MODE": "True", "CC": "/usr/bin/clang", "CXX": "/usr/bin/clang++"}


def offline(python: str, args: list[str], log: Path, cwd: Path | None = None) -> int:
    """``banzai_floyds_offline <args>`` in the reduction environment; output appended to ``log``."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a") as fh:
        fh.write(f"\n### {datetime.now(timezone.utc).isoformat(timespec='seconds')}  "
                 f"banzai_floyds_offline {' '.join(args)}\n")
        fh.flush()
        return subprocess.run([python, "-m", "banzai_floyds.offline", *args], env=clean_env(python), stdout=fh,
                              stderr=subprocess.STDOUT, cwd=cwd).returncode


def pipeline_version(package: str | None) -> str:
    """git describe of the fork (``+dirty`` when it has uncommitted changes)."""
    if not package:
        return "unknown"
    try:
        h = subprocess.run(["git", "-C", package, "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                           check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", package, "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True).stdout.strip()
        br = subprocess.run(["git", "-C", package, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True,
                            text=True).stdout.strip()
        return f"{br}@{h}{'+dirty' if dirty else ''}"
    except Exception:  # noqa: BLE001
        return "unknown"


def ensure_calibration_db(python: str, db: Path, skyflats_dir: Path, processed: Path, log: Path) -> bool:
    """Create the calibration DB with both sites and the sky flats, once.  Returns True if created."""
    if db.exists():
        return False
    db.parent.mkdir(parents=True, exist_ok=True)
    addr = f"sqlite:///{db}"
    if offline(python, ["setup-db", "--db-address", addr], log):
        db.unlink(missing_ok=True)
        raise RuntimeError(f"banzai_floyds_offline setup-db failed (see {log})")
    if offline(python, ["skyflats", "--db-address", addr, "--raw-dir", str(skyflats_dir),
                        "--processed-dir", str(processed)], log):
        raise RuntimeError(f"banzai_floyds_offline skyflats failed (see {log})")
    return True


def stage(nights: list[str], target_raw: Path, std_raw: Path, staging: Path, extra=()) -> list[Path]:
    """Symlink the nights' raw frames (target and standards) into one input folder.

    ``extra``: more raw files to stage. These are the standards chosen for these nights (with their arcs
    and flats), which are filed under the standard's OWN night and so are often not in
    ``std_raw/<science night>`` (legacy ``ava_floyds_sort.py`` copied the nearest standard into the night's
    folder in the same way)."""
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    out = []
    files = [f for n in nights for d in (target_raw / n.replace("-", ""), std_raw / n.replace("-", ""))
             for f in sorted(d.glob("*.fits*"))] + [Path(f) for f in extra]
    for f in files:
        if f.name.endswith(".part") or not f.exists() or (staging / f.name).exists():
            continue
        (staging / f.name).symlink_to(f.resolve())
        out.append(staging / f.name)
    return out


def chosen_standards(spec_db: Path, ava_id: int, nights: list[str], spec_raw_root: Path, spec_root: Path,
                     target: str) -> tuple[list[Path], list[str]]:
    """Raw standards (with their arcs and flats) that the spectra DB picked for these nights' science
    spectra (view ``spectrum_standards``, as the download used), as local paths: (on disk, missing names)."""
    from ava.spectroscopy import download as SD

    days = [n if "-" in n else f"{n[:4]}-{n[4:6]}-{n[6:8]}" for n in nights]
    p = SD.plan(spec_db, ava_id, days, archive_products=False)
    p = p[p.side == "standard"]
    paths = [SD.destination(r, spec_raw_root=spec_raw_root, spec_root=spec_root, target=target)
             for r in p.itertuples()]
    return [q for q in paths if q.exists()], [q.name for q in paths if not q.exists()]


def parse_chain_log(log: Path, since: int = 0) -> dict:
    """{raw file name: 'ok' | 'ERROR ...'} from the chain's per-frame lines (last attempt wins)."""
    res = {}
    lines = log.read_text().splitlines()[since:]
    for line in lines:
        m = re.match(r"^(\S+\.fits(?:\.fz)?) (ok|ERROR.*?)(?: \d+s)?$", line)
        if m:
            res[m.group(1)] = m.group(2)
    return res


def products_of(processed: Path, raw_name: str) -> dict:
    """The -1d / -2d of a raw e00 frame in the banzai processed tree."""
    stem = raw_name.split(".fits")[0].replace("-e00", "-e91")
    site, cam, night = stem.split("-")[0][:3], stem.split("-")[1], stem.split("-")[2]
    d = processed / site / cam / night / "processed"
    return {k: next(iter(sorted(d.glob(f"{stem}-{k}.fits*"))), None) for k in ("1d", "2d")}


def read_qc(path_1d: Path) -> dict:
    from astropy.io import fits

    h = fits.getheader(path_1d, 0)
    if "L1QFLAG" not in h and len(fits.open(path_1d)) > 1:
        h = fits.getheader(path_1d, 1)
    row = {c: (h.get(c) if not isinstance(h.get(c), bool) else int(h.get(c))) for c in QC_COLUMNS}
    extra = {k: (v if isinstance(v, (int, float, str)) else str(v)) for k, v in h.items()
             if k.startswith("L1") and k not in QC_COLUMNS}
    row["header_json"] = json.dumps(extra)
    return row


def write_qc(db: Path, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = ["frame_id", "basename", "data_id", "role", "day_obs", "path_1d", "path_2d", "reduced_utc", "pipeline",
            "pipeline_version", *QC_COLUMNS, "header_json"]
    with closing(sqlite3.connect(db, timeout=60)) as con:
        con.executescript(SPEC_QC_DDL)
        con.executemany(f"INSERT OR REPLACE INTO spec_qc ({','.join(chr(34) + c + chr(34) for c in cols)}) "
                        f"VALUES ({','.join('?' * len(cols))})", [[r.get(c) for c in cols] for r in rows])
        con.commit()
    return len(rows)


# ---------------------------------------------------------------------------
# Validation and cleanup of secondary products (after a successful reduction)
# ---------------------------------------------------------------------------

#: diagnostic images of the -2d products that nothing reads back (their content is in BINNED2D)
DIAGNOSTIC_HDUS = {"PROFILE", "BACKGROUND", "FRINGE"}


def validate_product(path_1d: Path, min_good: float = 0.8) -> str | None:
    """None if the -1d is usable, else the reason: it opens, has EXTRACTED with both orders, and at least
    ``min_good`` of each order's bins have a finite, unmasked flux."""
    import numpy as np
    from astropy.io import fits

    try:
        with fits.open(path_1d) as h:
            if "EXTRACTED" not in h:
                return "no EXTRACTED table"
            d = h["EXTRACTED"].data
            for order in (1, 2):
                m = d["order"] == order
                if not m.any():
                    return f"order {order} missing"
                good = np.isfinite(d["flux_optimal"][m]) & (d["mask"][m] == 0)
                if good.mean() < min_good:
                    return f"order {order}: only {100 * good.mean():.0f}% good bins"
    except Exception as exc:  # noqa: BLE001
        return f"unreadable: {type(exc).__name__}: {exc}"
    return None


def rewrite_without(path: Path, drop: set[str]) -> int:
    """Rewrite a FITS file without the HDUs in ``drop`` (via a checked temporary file). Returns bytes freed."""
    from astropy.io import fits

    with fits.open(path) as h:
        names = {x.name for x in h}
        if not drop & names:
            return 0
        keep = [x for x in h if x.name not in drop]
        tmp = path.with_name(path.name + ".lean.tmp")
        fits.HDUList(keep).writeto(tmp, overwrite=True)
    with fits.open(tmp) as check:
        assert {x.name for x in check} == names - drop
    before = path.stat().st_size
    os.replace(tmp, path)
    return before - path.stat().st_size


def has_hdu(path: Path, name: str) -> bool:
    from astropy.io import fits

    with fits.open(path) as h:
        return name in h


def clean_secondary(products: list[dict], calib_files: list[Path], staging: list[Path], *,
                    drop_binned: bool = True, keep_binned_examples: int = 2, example_roots=()) -> dict:
    """Make validated products lean.  ``products``: dicts with path_2d, OBJECT (validated frames only).
    Science/standard -2d: drop DIAGNOSTIC_HDUS, and BINNED2D unless fewer than ``keep_binned_examples``
    -2d files of that OBJECT under ``example_roots`` still have it.  Calibrations (arcs, lamp flats):
    drop BINNED2D.  Staging folders: removed.  Returns {files, bytes}."""
    from astropy.io import fits

    freed, n = 0, 0
    examples: dict[str, int] = {}
    if drop_binned:
        for root in example_roots:
            for f in Path(root).glob("**/*-e91-2d.fits*"):
                if f.name.endswith(".tmp"):
                    continue
                try:
                    obj = str(fits.getheader(f, "SCI").get("OBJECT", "")).strip()
                except Exception:  # noqa: BLE001
                    continue
                if has_hdu(f, "BINNED2D"):
                    examples[obj] = examples.get(obj, 0) + 1
    for p in products:
        f = p.get("path_2d")
        if not f or not Path(f).exists():
            continue
        drop = set(DIAGNOSTIC_HDUS)
        obj = str(p.get("OBJECT") or "").strip()
        if drop_binned and has_hdu(Path(f), "BINNED2D"):
            if examples.get(obj, 0) > keep_binned_examples:
                drop.add("BINNED2D")
                examples[obj] -= 1
        b = rewrite_without(Path(f), drop)
        freed += b; n += b > 0
    for f in calib_files:
        b = rewrite_without(Path(f), {"BINNED2D"})
        freed += b; n += b > 0
    for d in staging:
        d = Path(d)
        if d.exists():
            freed += sum(x.stat().st_size for x in d.glob("**/*") if x.is_file() and not x.is_symlink())
            shutil.rmtree(d)
    return {"files": n, "bytes": freed}
