"""
Calibration task — per-frame zero points, AGN magnitudes and frame QC.

Replaces ``__old_pipeline__/ava_calibrate.py`` (run by ``ava_update.py -c``);
the logic is :mod:`ava.photometry.process` / :mod:`ava.photometry.calibration`
(equations and the legacy issues they fix are documented there).

For every catalogue in ``cfg.sextractor_dir(target)`` not yet calibrated with
the current pipeline version (or all with ``force``):

1. frame metadata from the raw frame's SCI header
   (``cfg.phot_raw(target)/YYYYMMDD/<frame>.fits.fz``), or — once the image has
   been deleted — from the values stored in ``frame_qc`` at its first calibration;
2. detections matched to ``reference_stars.csv`` (``star_id``; WCS re-solved
   from star patterns when needed);
3. zero point at the catalogue's science aperture (10.5"), AGN magnitude,
   frame QC numbers and flags (``photometry.qc``).

Outputs
-------
* ``frame_qc`` rows in the photometry database (``photometry.calibration.frame_db``,
  default: the lcodb photometry DB) — every frame-level number;
* ``cfg.phot_dir(target)/measurements.parquet`` — all matched stars + the AGN
  (PyTICS input; ``ava.photometry.store.load_pytics``);
* ``cfg.phot_dir(target)/agn_lightcurve.parquet`` / ``.csv`` — calibrated AGN.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from prefect import get_run_logger, task

from ava.config import cfg


def frame_db_path() -> Path:
    cc = cfg.photometry.calibration
    if cc.get("frame_db"):
        return cfg._resolve(cc.frame_db)
    from ava.lcodb.config import load_config

    return load_config(cfg.lcodb_config_path).db_path("photometry")


def raw_meta_provider(target: str):
    """Frame metadata: the raw image's header if the image is on disk, else the values stored in ``frame_qc``
    when the frame was first calibrated (images are deleted after processing: ``ava.archive.cleanup``);
    None if neither exists."""
    from ava.photometry.process import header_meta
    from ava.photometry.store import frame_meta, meta_complete

    raw, stored = cfg.phot_raw(target), None

    def meta(frame: str):
        nonlocal stored
        p = raw / frame.split("-")[2] / f"{frame}.fits.fz"
        if p.exists() and p.stat().st_size > 0:
            return header_meta(p)
        if stored is None:
            stored = frame_meta(frame_db_path(), target)
        m = stored.get(frame)
        return m if meta_complete(m) else None
    return meta


@task(name="calibrate", tags=["calibration"])
def calibrate(target: str, force: bool = False, max_frames: int | None = None) -> dict:
    """Calibrate ``target``'s catalogues (see module docstring)."""
    from ava.photometry.calibration import ZPSettings
    from ava.photometry.process import calibrate_target

    logger = get_run_logger()
    ref_path = cfg.phot_dir(target) / "reference_stars.csv"
    if not ref_path.exists():
        raise FileNotFoundError(f"{ref_path} missing — run -o (initialise) first")
    cc = cfg.photometry.calibration
    settings = ZPSettings(min_snr=float(cc.min_snr), max_peak_frac=float(cc.max_peak_frac),
                          edge_px=float(cfg.photometry.pix_edge), sigma_floor=float(cc.sigma_floor),
                          clip_kappa=float(cc.clip_kappa), min_standards=int(cc.min_standards))
    out = calibrate_target(
        target, catdir=cfg.sextractor_dir(target), phot_dir=cfg.phot_dir(target),
        ref=pd.read_csv(ref_path), frame_db=frame_db_path(), meta_provider=raw_meta_provider(target),
        settings=settings, q=dict(vars(cfg.photometry.qc)), force=force, max_frames=max_frames,
        n_workers=int(cc.n_workers), log=logger.info)
    return {"target": target, **out}
