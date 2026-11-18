"""
Publish pipeline outputs into the website's own data folder.

The website (``web/``) never reads pipeline paths. After each update the
``publish_web`` step copies what it shows into ``web.data_dir`` (default
``web/data``):

  ava.db                       consistent snapshot of the AVA database
  filter_dict.txt              filter names / wavelengths / colours
  plots/<data_id>/*.png        per-target figures (lco_latest_<data_id>*.png)
  usage/lco_usage_<sem>.png    LCO time-usage plots (when ``web.usage_src`` is set)
  manuals/<name>.pdf           the AVA manuals (``web.manuals``; PDFs in docs/manuals/, docs/reports/)
  filters/lco_<band>.txt       LCO filter transmission curves (photometry.reference.lco_filters),
  filters/ava_lco_filters.zip  all of them, and filters/filters.json (per-band summary + a
                               thinned curve for the Data & Access plot)
  calibration/calibration.json photometric-calibration study for calibration.php (``web.calibration_src``,
                               made by tools/abscal_validation/export_web.py)
  site.json                    site switches read by the PHP pages (``downloads``: true/false)
  downloads/<data_id>/         per-target products, only when ``web.downloads`` is true:
      <t>_LCO_merged_lightcurve.csv   PyTICS-merged photometry
      <t>_FLOYDS_1d.zip               reduced 1-d FLOYDS spectra (*-e91-1d.fits*)
      <t>_FLOYDS_prepspec.zip         PrepSpec input (per-spectrum .dat + .hjd lists)

Only changed files are copied (size + mtime); every write goes to a temporary
file that is renamed into place, so the live site never serves a half-written
file. The source database is opened read-only, and a snapshot with no AGN is
refused. A target with no plots in its source folder keeps whatever was
published before (a missing mount never wipes the site); with ``prune`` the
plots that the pipeline no longer produces are removed.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

DEFAULT_MANUALS = ("docs/manuals/ava_system_manual.pdf", "docs/manuals/photometry_manual.pdf",
                   "docs/manuals/spectroscopy_manual.pdf",
                   "docs/reports/report_pytics_update.pdf")

HTACCESS = """# Published data for the AVA website (written by ava.web.publish).
# Plots are public; the database snapshot and text files are not.
<FilesMatch "(\\.(db|sqlite|tmp)|^filter_dict\\.txt|^site\\.json)$">
  Require all denied
</FilesMatch>
Options -Indexes
"""

#: written to downloads/.htaccess while web.downloads is false (already published files are not served)
HTACCESS_NO_DOWNLOADS = "# Downloads disabled (web.downloads: false in the AVA config).\nRequire all denied\n"


@dataclass
class PublishSummary:
    dest: Path
    agn: int = 0
    targets_with_plots: int = 0
    plots_copied: int = 0
    plots_pruned: int = 0
    usage_copied: int = 0
    manuals_copied: int = 0
    filters_copied: int = 0
    calibration_copied: bool = False
    downloads_updated: int = 0
    filter_dict_copied: bool = False
    changes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: (str(v) if isinstance(v, Path) else v) for k, v in self.__dict__.items() if k != "changes"}


def _same(src: Path, dst: Path) -> bool:
    if not dst.exists():
        return False
    a, b = src.stat(), dst.stat()
    return a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime)


def _atomic_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, prefix=f".{dst.name}.", suffix=".tmp")
    os.close(fd)
    try:
        shutil.copy2(src, tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _copy_if_changed(src: Path, dst: Path, dry_run: bool, s: PublishSummary) -> bool:
    if _same(src, dst):
        return False
    s.changes.append(f"{src} -> {dst}")
    if not dry_run:
        _atomic_copy(src, dst)
    return True


def snapshot_db(src: Path, dest: Path, dry_run: bool = False) -> tuple[int, list[str]]:
    """Copy ``src`` to ``dest/ava.db`` with the SQLite backup API. Returns (n_agn, data_ids)."""
    with closing(sqlite3.connect(f"file:{src}?mode=ro", uri=True)) as con:
        n = con.execute("SELECT COUNT(*) FROM agn").fetchone()[0]
        if n == 0:
            raise RuntimeError(f"refusing to publish: {src} has no rows in agn")
        ids = [r[0] for r in con.execute(
            "SELECT data_id FROM agn WHERE data_id IS NOT NULL AND data_id != ''")]
        if dry_run:
            return n, ids
        dest.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest, prefix=".ava.db.", suffix=".tmp")
        os.close(fd)
        try:
            with closing(sqlite3.connect(tmp)) as out:
                con.backup(out)
            os.chmod(tmp, 0o644)
            os.replace(tmp, dest / "ava.db")
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return n, ids


def publish(
    *,
    db: Path,
    filter_dict: Path,
    dest: Path,
    plots_dir_for: Callable[[str], Path],
    targets: Iterable[str] | None = None,
    usage_src: Path | None = None,
    manuals: Iterable[Path] = (),
    filters_src: Path | None = None,
    calibration_src: Path | None = None,
    downloads_for: Callable[[str], dict[str, list[Path]]] | None = None,
    downloads: bool = True,
    prune: bool = False,
    dry_run: bool = False,
) -> PublishSummary:
    """Refresh the website data folder.

    Parameters
    ----------
    plots_dir_for
        ``data_id -> folder`` holding that target's ``lco_latest_<data_id>*.png``
        (the pipeline's ``cfg.target_plots_dir``).
    targets
        Only publish plots for these data_ids (default: every AGN in the database).
        The database snapshot and filter dictionary are always refreshed.
    manuals
        PDF files copied to ``manuals/``; missing ones are skipped (a manual not
        built yet keeps any previously published copy).
    """
    dest = Path(dest)
    s = PublishSummary(dest=dest)
    s.agn, ids = snapshot_db(Path(db), dest, dry_run)
    s.filter_dict_copied = _copy_if_changed(Path(filter_dict), dest / "filter_dict.txt", dry_run, s)

    wanted = set(targets) if targets is not None else None
    for t in ids:
        if (wanted is not None and t not in wanted) or "/" in t or t.startswith("."):
            continue
        src_dir = Path(plots_dir_for(t))
        files = sorted(src_dir.glob(f"lco_latest_{t}*.png")) if src_dir.is_dir() else []
        if not files:
            continue
        s.targets_with_plots += 1
        out_dir = dest / "plots" / t
        s.plots_copied += sum(_copy_if_changed(f, out_dir / f.name, dry_run, s) for f in files)
        if prune and out_dir.is_dir():
            keep = {f.name for f in files}
            for old in out_dir.glob("*.png"):
                if old.name not in keep:
                    s.plots_pruned += 1
                    s.changes.append(f"prune {old}")
                    if not dry_run:
                        old.unlink()

    if downloads and downloads_for is not None:
        for t in ids:
            if (wanted is not None and t not in wanted) or "/" in t or t.startswith("."):
                continue
            for name, files in downloads_for(t).items():
                s.downloads_updated += publish_download(files, dest / "downloads" / t / name, dry_run, s)

    if usage_src is not None and Path(usage_src).is_dir():
        s.usage_copied = sum(_copy_if_changed(f, dest / "usage" / f.name, dry_run, s)
                             for f in sorted(Path(usage_src).glob("lco_usage_*.png")))

    s.manuals_copied = sum(_copy_if_changed(Path(m), dest / "manuals" / Path(m).name, dry_run, s)
                           for m in manuals if Path(m).is_file() and Path(m).suffix.lower() == ".pdf")

    if filters_src is not None and Path(filters_src).is_dir():
        s.filters_copied = publish_filters(Path(filters_src), dest / "filters", dry_run, s)

    if calibration_src is not None and Path(calibration_src).is_file():
        s.calibration_copied = _copy_if_changed(Path(calibration_src), dest / "calibration" / "calibration.json",
                                                dry_run, s)

    if not dry_run:
        import json

        (dest / ".htaccess").write_text(HTACCESS)
        (dest / "site.json").write_text(json.dumps({"downloads": bool(downloads)}) + "\n")
        block = dest / "downloads" / ".htaccess"
        if downloads:
            block.unlink(missing_ok=True)
        elif block.parent.is_dir():
            block.write_text(HTACCESS_NO_DOWNLOADS)
    return s


def publish_download(files: list[Path], dst: Path, dry_run: bool, s: PublishSummary) -> bool:
    """One download: a single file is copied as is; several are zipped into ``dst`` (rebuilt only
    when a member is newer than the zip or the member list changed). No source files: nothing
    is touched (a previously published download stays)."""
    import zipfile

    files = sorted(Path(f) for f in files if Path(f).is_file())
    if not files:
        return False
    if dst.suffix.lower() != ".zip":
        return _copy_if_changed(files[0], dst, dry_run, s)
    folder = dst.stem
    names = [f"{folder}/{f.name}" for f in files]
    if dst.exists():
        with zipfile.ZipFile(dst) as z:
            same = sorted(z.namelist()) == sorted(names)
        if same and max(f.stat().st_mtime for f in files) <= dst.stat().st_mtime:
            return False
    s.changes.append(f"{len(files)} file(s) -> {dst}")
    if dry_run:
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, prefix=f".{dst.name}.", suffix=".tmp")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for f, n in zip(files, names):
                z.write(f, n)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return True


def downloads_from_config(cfg) -> Callable[[str], dict[str, list[Path]]]:
    """``data_id -> {published name: source files}`` for the per-target downloads."""
    spec = cfg._raw.get("spectroscopy", {}) or {}
    folder = (((spec.get("products") or {}).get("prepspec") or {}).get("folder")) or "prepspec"

    def files(t: str) -> dict[str, list[Path]]:
        ph, sp = cfg.phot_dir(t), cfg.spec_dir(t)
        pp = sp / folder
        return {
            f"{t}_LCO_merged_lightcurve.csv": [ph / f"{t}_LCO_merged_lightcurve.csv"],
            f"{t}_FLOYDS_1d.zip": sorted((sp / "reduced").glob("*/*-e91-1d.fits*")),
            f"{t}_FLOYDS_prepspec.zip": sorted([*pp.glob("*.dat"), *pp.glob("*.hjd")]) if pp.is_dir() else [],
        }
    return files


def filter_summary(path: Path, n_points: int = 240) -> dict:
    """Pivot / mean wavelength, FWHM, peak and a thinned curve of one transmission file (Å, T)."""
    import numpy as np

    d = np.loadtxt(path)
    w, t = d[:, 0], np.clip(d[:, 1], 0, None)
    tr = getattr(np, "trapezoid", None) or np.trapz
    pivot = float(np.sqrt(tr(t * w, w) / tr(t / w, w)))
    mean = float(tr(t * w, w) / tr(t, w))
    half = np.where(t >= t.max() / 2)[0]
    lo_i, hi_i = np.where(t >= 0.002 * t.max())[0][[0, -1]]
    pad = 0.04 * (w[hi_i] - w[lo_i])
    grid = np.linspace(max(w[0], w[lo_i] - pad), min(w[-1], w[hi_i] + pad), n_points)
    return {"pivot_A": round(pivot, 1), "mean_A": round(mean, 1),
            "fwhm_A": round(float(w[half[-1]] - w[half[0]]), 1),
            "half_lo_A": round(float(w[half[0]]), 1), "half_hi_A": round(float(w[half[-1]]), 1),
            "peak": round(float(t.max()), 4),
            "curve": [[round(float(x), 1), round(float(y), 4)] for x, y in zip(grid, np.interp(grid, w, t))]}


def publish_filters(src: Path, out: Path, dry_run: bool, s: PublishSummary) -> int:
    """Copy lco_<band>.txt, write filters.json and a zip of all curves (only when something changed)."""
    import json
    import zipfile

    files = sorted(src.glob("lco_*.txt"))
    n = sum(_copy_if_changed(f, out / f.name, dry_run, s) for f in files)
    meta, zpath = out / "filters.json", out / "ava_lco_filters.zip"
    if dry_run or not files or (n == 0 and meta.exists() and zpath.exists()):
        return n
    info = {"note": "LCO filter transmission including the Sinistro CCD response (only instrument component) and the atmosphere at airmass = 1",
            "filters": {f.stem[len("lco_"):]: {"file": f.name, **filter_summary(f)} for f in files}}
    fd, tmp = tempfile.mkstemp(dir=out, prefix=".filters.", suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        json.dump(info, fh, separators=(",", ":"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, meta)
    fd, tmp = tempfile.mkstemp(dir=out, prefix=".zip.", suffix=".tmp")
    os.close(fd)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f"ava_lco_filters/{f.name}")
        z.writestr("ava_lco_filters/README.txt",
                   "AVA - LCO filter transmission curves.\n"
                   "Two columns: wavelength (Angstrom), transmission.\n"
                   "Filter x Sinistro CCD response x atmosphere at airmass = 1 (no telescope mirrors or other optics).\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, zpath)
    s.changes.append(f"filters.json + zip -> {out}")
    return n


def publish_from_config(cfg, targets: Iterable[str] | None = None, dry_run: bool = False, **overrides) -> PublishSummary:
    """``publish`` with every path taken from the AVA config (``web`` section)."""
    web = cfg._raw.get("web", {}) or {}
    plots = cfg._raw.get("plots", {}) or {}
    usage = overrides.pop("usage_src", None) or web.get("usage_src")
    kw = dict(
        db=cfg.db_path,
        filter_dict=cfg._resolve(plots.get("filter_dict") or "data/reference/filter_dict.txt"),
        dest=cfg._resolve(web.get("data_dir") or "web/data"),
        plots_dir_for=cfg.target_plots_dir,
        usage_src=cfg._resolve(usage) if usage else None,
        manuals=[cfg._resolve(m) for m in web.get("manuals", DEFAULT_MANUALS) or []],
        filters_src=cfg._resolve(web.get("filters_src") or
                                 ((cfg._raw.get("photometry", {}) or {}).get("reference", {}) or {}).get("lco_filters")
                                 or "data/reference/lco_filters"),
        calibration_src=cfg._resolve(web["calibration_src"]) if web.get("calibration_src") else None,
        prune=bool(web.get("prune", False)),
        downloads_for=downloads_from_config(cfg),
        downloads=bool(web.get("downloads", False)),
    )
    kw.update({k: v for k, v in overrides.items() if v is not None})
    return publish(targets=targets, dry_run=dry_run, **kw)
