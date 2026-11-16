"""
ava.archive.cleanup — delete downloaded raw frames once AVA has made everything it needs from them.

Run daily by cron (``scripts/cleanup.py``; settings ``cleanup:`` in the AVA config).  Dry run by default:
it reports what it would delete and why the rest is kept.  A file is deleted only when **all** its checks pass.

Photometry image ``<phot raw>/<target>/YYYYMMDD/<frame>.fits.fz``:

1. its SExtractor catalogue ``<phot>/<target>/sextractor_ava/<frame>_cat.fits`` exists;
2. the frame has a ``frame_qc`` row at the current calibration version (``process.PIPELINE_VERSION``):
   it is calibrated, its QC numbers and AGN measurement are stored, and so is everything a recalibration
   needs from the image header (time, filter, airmass, seeing, ``SATURATE``, image size).  Rows written
   before ``saturate`` / ``naxis1`` / ``naxis2`` were stored are completed here from the image before it goes;
3. the file is older than ``retention_days`` (file time = download time).

FLOYDS night ``<spec raw>/<target>/YYYYMMDD/`` (science spectra ``e00`` with their arcs ``a00`` and lamp
flats ``w00``), deleted as a whole when:

1. every science spectrum has its reduced ``-1d`` in ``<spec>/<target>/reduced/YYYYMMDD/`` and a ``spec_qc``
   row (lcodb spectra DB);
2. every science spectrum has a row in ``<spec>/<target>/hbeta_fits.parquet`` (the products step ran on it:
   line fits, light curves, mean/RMS);
3. every file in the night is older than ``retention_days``.

Flux-standard night ``<spec raw>/standards/YYYYMMDD/``: deleted when no target still has a raw folder for that
night (the standard may be needed to reduce it), every standard spectrum has a ``spec_qc`` row, and every file
is older than ``retention_days``.

Catalogues, reduced spectra and all products are never touched.  Each deleted file is marked in the lcodb
``local_files`` table (``deleted_utc``; the row and its md5 stay).  ``retention_days`` must be longer than the
download look-back (``download.overlap_days``, ``spectroscopy.download.overlap_days``), so the daily download
never sees a deleted frame again; photometry downloads also skip frames that have a catalogue.
"""

from __future__ import annotations

import sqlite3
import time
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DAY = 86400.0


@dataclass
class Report:
    delete: list[Path] = field(default_factory=list)       # files to delete (or deleted, when live)
    kept: Counter = field(default_factory=Counter)          # reason -> number of files kept
    filled: int = 0                                         # frame_qc rows completed from the image
    bytes: int = 0

    def add(self, other: "Report") -> None:
        self.delete += other.delete
        self.kept.update(other.kept)
        self.filled += other.filled
        self.bytes += other.bytes


def _old(p: Path, cutoff: float) -> bool:
    return p.stat().st_mtime < cutoff


# ---------------------------------------------------------------------------
# Photometry
# ---------------------------------------------------------------------------

def photometry_target(raw_dir: Path, catdir: Path, calibrated: dict[str, bool], cutoff: float,
                      frame_db: Path | None = None, write: bool = False) -> Report:
    """Decide for every image of one target.  ``calibrated``: frame -> its current ``frame_qc`` row holds all
    the image metadata.  Incomplete rows are completed from the image first (``write``; a dry run only counts)."""
    from ava.photometry import store
    from ava.photometry.process import header_meta

    r, fill = Report(), {}
    for img in sorted(Path(raw_dir).glob("2*/*.fits.fz")):
        frame = img.name[: -len(".fits.fz")]
        if not (Path(catdir) / f"{frame}_cat.fits").exists():
            r.kept["no catalogue"] += 1
        elif frame not in calibrated:
            r.kept["not calibrated (no current frame_qc row)"] += 1
        elif not _old(img, cutoff):
            r.kept["within retention"] += 1
        else:
            if not calibrated[frame]:
                try:
                    m = header_meta(img)
                except Exception:  # noqa: BLE001 — unreadable image: keep it, report
                    r.kept["frame_qc incomplete (image unreadable)"] += 1
                    continue
                if not store.meta_complete(m):
                    r.kept["frame_qc incomplete (image header lacks values)"] += 1
                    continue
                fill[frame] = m
            r.delete.append(img)
            r.bytes += img.stat().st_size
    r.filled = len(fill)
    if write and fill:
        store.fill_frame_meta(frame_db, fill)
    return r


def calibrated_frames(frame_db: Path, data_id: str, version: str) -> dict[str, bool]:
    """frame -> True if its ``frame_qc`` row (current version) holds all the image metadata."""
    from ava.photometry import store

    fq = store.read_frame_qc(frame_db, data_id)
    if fq.empty:
        return {}
    meta = store.frame_meta(frame_db, data_id)
    return {f: store.meta_complete(meta.get(f)) for f in fq.loc[fq["pipeline_version"] == version, "frame"]}


# ---------------------------------------------------------------------------
# Spectroscopy
# ---------------------------------------------------------------------------

def _reduced_1d(reduced_night: Path, e00: str) -> bool:
    stem = e00.replace("-e00", "-e91-1d")
    return any(reduced_night.glob(f"{stem}.fits*"))


def spectra_target(raw_dir: Path, spec_dir: Path, qc_basenames: set[str], cutoff: float) -> Report:
    """Decide for every downloaded night of one target (the night's files go together)."""
    import pandas as pd

    r = Report()
    pq = Path(spec_dir) / "hbeta_fits.parquet"
    products = set(pd.read_parquet(pq, columns=["basename"])["basename"]) if pq.exists() else set()
    for night in sorted(p for p in Path(raw_dir).glob("20??????") if p.is_dir()):
        files = [f for f in night.iterdir() if f.is_file()]
        if not files:
            continue
        sci = [f.name.split(".fits")[0] for f in files if "-e00.fits" in f.name]
        why = None
        if not sci:
            why = "night without science spectra"
        elif not all(_reduced_1d(Path(spec_dir) / "reduced" / night.name, s) for s in sci):
            why = "not reduced (no -1d)"
        elif not all(s in qc_basenames for s in sci):
            why = "no spec_qc row"
        elif not all(s in products for s in sci):
            why = "no final products (hbeta_fits)"
        elif not all(_old(f, cutoff) for f in files):
            why = "within retention"
        if why:
            r.kept[why] += len(files)
            continue
        r.delete += files
        r.bytes += sum(f.stat().st_size for f in files)
    return r


def standards(std_dir: Path, waiting: set[str], qc_basenames: set[str], cutoff: float) -> Report:
    """Standard-star nights, once no target night still on disk (``waiting``: YYYYMMDD) may need them."""
    r = Report()
    for night in sorted(p for p in Path(std_dir).glob("20??????") if p.is_dir()):
        files = [f for f in night.iterdir() if f.is_file()]
        sci = [f.name.split(".fits")[0] for f in files if "-e00.fits" in f.name]
        if night.name in waiting:
            why = "a target night still needs it"
        elif not all(s in qc_basenames for s in sci):
            why = "standard not reduced (no spec_qc row)"
        elif not all(_old(f, cutoff) for f in files):
            why = "within retention"
        else:
            why = None
        if why:
            r.kept[why] += len(files)
            continue
        r.delete += files
        r.bytes += sum(f.stat().st_size for f in files)
    return r


def spec_qc_basenames(spectra_db: Path | None, role: str) -> set[str]:
    if spectra_db is None or not Path(spectra_db).exists():
        return set()
    with closing(sqlite3.connect(f"file:{spectra_db}?mode=ro", uri=True)) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='spec_qc'").fetchone():
            return set()
        return {b for (b,) in con.execute("SELECT basename FROM spec_qc WHERE role=?", (role,))}


# ---------------------------------------------------------------------------
# Deleting and recording
# ---------------------------------------------------------------------------

def delete_files(files: list[Path], registry_dbs: list[Path]) -> int:
    """Delete ``files``, remove emptied night folders, mark them in ``local_files`` (``deleted_utc``)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    gone = []
    for f in files:
        try:
            f.unlink()
            gone.append(f)
        except FileNotFoundError:
            pass
    for d in sorted({f.parent for f in gone}):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    for db in registry_dbs:
        if db is None or not Path(db).exists():
            continue
        with closing(sqlite3.connect(db, timeout=60)) as con:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='local_files'").fetchone():
                continue
            cols = {r[1] for r in con.execute("PRAGMA table_info(local_files)")}
            if "deleted_utc" not in cols:
                con.execute("ALTER TABLE local_files ADD COLUMN deleted_utc TEXT")
            con.executemany("UPDATE local_files SET deleted_utc=? WHERE path=?", [(now, str(f)) for f in gone])
            con.commit()
    return len(gone)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def settings(cfg) -> dict:
    c = cfg._raw.get("cleanup", {}) or {}
    return dict(mode=c.get("mode", "dry_run"), retention_days=float(c.get("retention_days", 7)),
                photometry=bool(c.get("photometry", True)), spectra=bool(c.get("spectra", True)))


def check_retention(cfg, retention_days: float) -> None:
    look_back = [float(cfg._raw.get("download", {}).get("overlap_days", 2)),
                 float((cfg._raw.get("spectroscopy", {}).get("download", {}) or {}).get("overlap_days", 2))]
    if retention_days <= max(look_back):
        raise ValueError(f"cleanup.retention_days ({retention_days:g}) must be longer than the download look-back "
                         f"(overlap_days {max(look_back):g}), or deleted frames would be downloaded again")


def _lcodb(cfg, kind: str) -> Path | None:
    try:
        from ava.lcodb.config import load_config

        p = load_config(cfg.lcodb_config_path).db_path(kind)
        return p if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _frame_db(cfg) -> Path | None:
    cc = cfg._raw.get("photometry", {}).get("calibration", {}) or {}
    return cfg._resolve(cc["frame_db"]) if cc.get("frame_db") else _lcodb(cfg, "photometry")


def run(cfg, *, live: bool = False, retention_days: float | None = None, targets: list[str] | None = None,
        photometry: bool | None = None, spectra: bool | None = None, now: float | None = None,
        log=print) -> dict:
    """Decide (and, if ``live``, delete) for every target folder under the raw-data roots."""
    from ava.photometry.process import PIPELINE_VERSION

    s = settings(cfg)
    retention = s["retention_days"] if retention_days is None else float(retention_days)
    check_retention(cfg, retention)
    cutoff = (time.time() if now is None else now) - retention * DAY
    phot_db, spec_db = _lcodb(cfg, "photometry"), _lcodb(cfg, "spectra")
    out = {"mode": "live" if live else "dry_run", "retention_days": retention}

    if s["photometry"] if photometry is None else photometry:
        root, frame_db, rep = cfg.phot_raw("_").parent, _frame_db(cfg), Report()
        for d in sorted(p for p in root.glob("*") if p.is_dir() and (not targets or p.name in targets)):
            # completing frame_qc rows writes to the database: only when deleting for real
            r = photometry_target(d, cfg.sextractor_dir(d.name),
                                  calibrated_frames(frame_db, d.name, PIPELINE_VERSION) if frame_db else {},
                                  cutoff, frame_db=frame_db, write=live)
            log(f"photometry {d.name}: delete {len(r.delete)} ({r.bytes / 1e9:.2f} GB); kept {dict(r.kept)}"
                + (f"; {r.filled} frame_qc row(s) completed from the image first" if r.filled else ""))
            rep.add(r)
        if live and rep.delete:
            delete_files(rep.delete, [phot_db])
        out["photometry"] = dict(files=len(rep.delete), gb=rep.bytes / 1e9, kept=dict(rep.kept), filled=rep.filled)

    if s["spectra"] if spectra is None else spectra:
        root, rep = cfg.spec_raw("_").parent, Report()
        sci_qc = spec_qc_basenames(spec_db, "science")
        tdirs = sorted(p for p in root.glob("*") if p.is_dir() and p.name != "standards")
        for d in tdirs:
            if targets and d.name not in targets:
                continue
            r = spectra_target(d, cfg.spec_dir(d.name), sci_qc, cutoff)
            log(f"spectra {d.name}: delete {len(r.delete)} ({r.bytes / 1e6:.1f} MB); kept {dict(r.kept)}")
            rep.add(r)
        # standards: a night is free once no target night that may need it is still on disk (after this run)
        std = Report()
        if (root / "standards").is_dir() and not targets:
            going = {f.parent for f in rep.delete}
            waiting = {n.name for d in tdirs for n in d.glob("20??????")
                       if n.is_dir() and n not in going and any(n.iterdir())}
            std = standards(root / "standards", waiting, spec_qc_basenames(spec_db, "standard"), cutoff)
            log(f"spectra standards: delete {len(std.delete)} ({std.bytes / 1e6:.1f} MB); kept {dict(std.kept)}")
        rep.add(std)
        if live and rep.delete:
            delete_files(rep.delete, [spec_db])
        out["spectra"] = dict(files=len(rep.delete), mb=rep.bytes / 1e6, kept=dict(rep.kept))
    return out
