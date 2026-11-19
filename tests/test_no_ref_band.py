"""B15: an R or I frame with the APASS-fallback reference catalogue (bands u B g V r i z Y only) raised
KeyError 'lco_R'; the frame was stored as error:KeyError and lost its measurements."""
import numpy as np
import pandas as pd

from ava.photometry.calibration import ZPSettings, calibrate_frame


def _frame(n=8):
    ref = pd.DataFrame({"star_id": np.arange(n) + 1, "quality_ok": True, "lco_g": np.linspace(15, 16, n),
                        "lco_g_err": 0.01, "lco_r": np.linspace(14.6, 15.6, n), "lco_r_err": 0.01,
                        "lco_i": 14.0})
    meas = pd.DataFrame({"star_id": list(ref.star_id) + [99], "is_agn": [False] * n + [True],
                         "mag": list(ref.lco_g - 23.0) + [-9.0], "magerr": 0.01, "sex_flags": 0,
                         "flux_max": 1000.0, "background": 200.0, "x": 500.0, "y": 500.0})
    return ref, meas


def test_band_without_reference_magnitudes_gives_no_zero_point():
    ref, meas = _frame()
    for filt in ("R", "I"):
        m, zp, agn = calibrate_frame(meas, ref, filt=filt, exptime=60.0, settings=ZPSettings())
        assert np.isnan(zp.zp) and agn == {} and len(m) == len(meas) and not m["is_standard"].any()
    _, zp, _ = calibrate_frame(meas, ref, filt="rp", exptime=60.0, settings=ZPSettings())
    assert np.isfinite(zp.zp)                                   # a band the catalogue has still calibrates


def test_calibrate_target_skips_filters_not_in_the_list(tmp_path):
    """R / I / U are not used at all: their catalogues are never calibrated (no frame_qc, no measurements)."""
    from pathlib import Path
    from ava.photometry import process as P

    for f in ("lsc1m005-fa15-20261010-0001-e91", "lsc1m005-fa15-20261010-0002-e91", "lsc1m005-fa15-20261010-0003-e91"):
        (tmp_path / f"{f}_cat.fits").write_bytes(b"")
    filt = {"0001": "R", "0002": "I", "0003": "U"}
    logs = []
    out = P.calibrate_target("T", catdir=tmp_path, phot_dir=tmp_path, ref=pd.DataFrame(), frame_db=tmp_path / "q.sqlite",
                             meta_provider=lambda fr: {"filter": filt[fr.split("-")[3]]}, settings=ZPSettings(),
                             q={}, log=logs.append, filters=["up", "B", "V", "gp", "rp", "ip", "zs", "Y"])
    assert out["processed"] == 0 and not (tmp_path / "q.sqlite").exists()
    assert "not calibrated" in logs[0] and "'R': 1" in logs[0]
