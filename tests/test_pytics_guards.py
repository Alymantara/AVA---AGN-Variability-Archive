"""PyTICS task guards found on the laptop test-archive run of the turgon bundle (19 Nov 2026):
B1ₚ frame_db relative to archive_root and a missing frame_qc DB, B2ₚ every filter skipped."""

import importlib
import logging
from pathlib import Path

import pandas as pd

from ava.photometry import store


def _task(monkeypatch, tmp_path, frame_db):
    T = importlib.import_module("ava.pipeline.tasks.ensemble")
    C = importlib.import_module("ava.pipeline.tasks.calibrate")
    monkeypatch.setattr(T.cfg, "phot_dir", lambda t: tmp_path / t)
    monkeypatch.setattr(T, "get_run_logger", lambda: logging.getLogger("test"))
    monkeypatch.setattr(C, "frame_db_path", lambda: Path(frame_db))
    return T


def _measurements(folder: Path):
    folder.mkdir(parents=True)
    store.update_measurements(folder / "measurements.parquet", pd.DataFrame([dict(
        frame="f1", star_id=1, is_agn=False, mag_inst=-10.0, magerr=0.01, x=1.0, y=1.0, sex_flags=0,
        sep_arcsec=0.1, used_in_zp=True)]))


def test_frame_db_relative_to_archive_root(monkeypatch, tmp_path):
    """B1ₚ: a relative frame_db is taken from paths.archive_root (it was resolved from ava_root)."""
    C = importlib.import_module("ava.pipeline.tasks.calibrate")
    cal = C.cfg.photometry.calibration
    monkeypatch.setattr(cal, "frame_db", "lcodb/frame_qc.sqlite")
    monkeypatch.setitem(C.cfg._raw["paths"], "archive_root", str(tmp_path))
    assert C.frame_db_path() == (tmp_path / "lcodb" / "frame_qc.sqlite").resolve()
    monkeypatch.setattr(cal, "frame_db", str(tmp_path / "abs.sqlite"))
    assert C.frame_db_path() == tmp_path / "abs.sqlite"


def test_ensemble_skips_when_frame_db_missing(monkeypatch, tmp_path):
    """B1ₚ: a frame_qc DB that does not exist is reported, not read as '0 frames' in every filter."""
    _measurements(tmp_path / "T")
    T = _task(monkeypatch, tmp_path, tmp_path / "missing.sqlite")
    out = T.ensemble.fn("T")
    assert out["target"] == "T" and out["skipped"].startswith("no frame_qc database")


def test_ensemble_skips_when_every_filter_is_skipped(monkeypatch, tmp_path):
    """B2ₚ: no filter with min_epochs passing frames (no frame_qc rows, or none pass QC) skips the target;
    it raised FileNotFoundError on agn_lightcurve_pytics.parquet (NGC_3783, NGC_7469, PG_2304+043)."""
    _measurements(tmp_path / "T")
    db = tmp_path / "phot.sqlite"
    store.write_frame_qc(db, [dict(frame="f1", data_id="T", filter="V", mjd_mid=60000.0, qc_pass=0,
                                   tel="1m001", camera="fa11", airmass=1.2, fwhm_arcsec=2.0)])
    T = _task(monkeypatch, tmp_path, db)
    out = T.ensemble.fn("T", mode="full", plot=False)
    assert out == {"target": "T", "skipped": "no filter with enough passing frames"}
    assert not (tmp_path / "T" / "agn_lightcurve_pytics.parquet").exists()


def test_merged_csv_drops_epochs_without_magnitude(tmp_path):
    """B4ₚ (task side): a filter without an absolute ZP has NaN mag_ic; those epochs are left out of the
    shareable CSV (and of the merged plots, which raised 'Axis limits cannot be NaN' for fairall_9, NGC_4151)."""
    import numpy as np

    T = importlib.import_module("ava.pipeline.tasks.ensemble")
    n = 4
    lc = pd.DataFrame({"good": True, "MJD": 60000.0 + np.arange(n), "Filter": ["V", "V", "Y", "Y"],
                       "telid": "1m001", "camera": "fa11", "F_ic": [1.0, 1.1, np.nan, np.nan],
                       "Ferr_ic": 0.01, "mag_ic": [16.4, 16.3, np.nan, np.nan], "mag_ic_err": 0.01,
                       "mag_err_rand": 0.01, "ic_a": 1.0, "frame": [f"f{i}" for i in range(n)]})
    out = T.export_merged_csv(lc, tmp_path / "m.csv", "T")
    assert list(out["filter"]) == ["V", "V"] and np.isfinite(out["mag_AB"]).all()
