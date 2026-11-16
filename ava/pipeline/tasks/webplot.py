"""
Web-plot task — the AVA website figures for one target.

Replaces ``ava_update.py -p`` → ``__old_pipeline__/ava_webplot.py``; figures
are drawn by :mod:`ava.plots.webplots` from the calibrated products
(``frame_qc``, ``measurements.parquet``, ``agn_lightcurve``), with filter
colours and wavelengths from ``plots.filter_dict``.

Outputs (``cfg.target_plots_dir(target)`` = ``<phot>/<target>/plots/``, legacy names):
  lco_latest_<obj>.png/.pdf          full light curves (flux, mJy)
  lco_latest_<obj>_last6.png/.pdf    last ``plots.recent_days`` days
  lco_latest_<obj>_<filter>_sky      seeing / airmass / zero point per filter
  lco_latest_<obj>_stan              field-star magnitude vs RMS, AGN marked
  lco_latest_<obj>_swift             Swift (if the target is in ``paths.swift_db``)

Spectroscopic epochs: raw FLOYDS science spectra in the lcodb spectra DB
(red ticks); without it, only the last FLOYDS date from ``ava.db``.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
from prefect import get_run_logger, task

from ava.config import cfg


def spectroscopy_epochs(target: str) -> tuple[list[float], float | None]:
    """(MJDs of FLOYDS science spectra, last spectrum MJD)."""
    from astropy.time import Time

    mjds = []
    try:
        from ava.lcodb.config import load_config

        db = load_config(cfg.lcodb_config_path).db_path("spectra")
        if db.exists():
            with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
                mjds = [r[0] for r in con.execute(
                    "SELECT DISTINCT mjd_obs FROM frames WHERE ava_data_id = ? AND rlevel = 0 "
                    "AND obstype = 'SPECTRUM' AND is_standard = 0", (target,))]
    except Exception:  # noqa: BLE001
        mjds = []
    last = max(mjds) if mjds else None
    if last is None:
        from ava.database import query

        end = (query.target(target) or {}).get("floyds_end")
        if end:
            last = float(Time(str(end)[:10]).mjd)
    return mjds, last


@task(name="webplot", tags=["web"])
def webplot(target: str) -> dict:
    """Draw the website figures for ``target``."""
    from ava.photometry import store
    from ava.pipeline.tasks.calibrate import frame_db_path
    from ava.plots import webplots as wp

    logger = get_run_logger()
    pc = cfg.plots
    fd = wp.load_filter_dict(cfg._resolve(pc.filter_dict))
    out_dir = cfg.target_plots_dir(target)
    out_dir.mkdir(parents=True, exist_ok=True)
    phot, db = cfg.phot_dir(target), frame_db_path()
    lc = pd.read_parquet(phot / "agn_lightcurve.parquet")
    fq = store.read_frame_qc(db, target)
    formats = list(pc.formats)
    spec, last_spec = spectroscopy_epochs(target)
    base = out_dir / f"lco_latest_{target}"
    files = wp.plot_lightcurves(lc, fd, base, spec_mjd=spec, last_spec_mjd=last_spec, formats=formats)
    files += wp.plot_lightcurves(lc, fd, Path(f"{base}_last6"), spec_mjd=spec, last_spec_mjd=last_spec,
                                 recent_days=float(pc.recent_days), formats=formats)
    files += wp.plot_diagnostics(fq, fd, base, formats=formats)
    meas = pd.read_parquet(phot / "measurements.parquet", columns=["frame", "star_id", "is_agn", "mag_inst"])
    files += wp.plot_standards_rms(meas, fq, fd, Path(f"{base}_stan"), last_epochs=int(pc.rms_last_epochs),
                                   formats=formats)
    if cfg.swift_db.exists():
        sw = pd.read_csv(cfg.swift_db)
        sw = sw[sw["Object"] == target]
        if len(sw):
            files += wp.plot_swift(sw, fd, Path(f"{base}_swift"), spec_mjd=spec, formats=formats)
    logger.info("%s: %d figure files in %s", target, len(files), out_dir)
    return {"target": target, "plots": files}
