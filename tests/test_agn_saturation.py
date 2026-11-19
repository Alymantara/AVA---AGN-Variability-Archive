"""AGN peak check (19 Nov 2026): frame_qc.agn_peak and the agn_saturated QC flag; offline."""
import numpy as np
import pandas as pd

from ava.photometry.calibration import ZPSettings, calibrate_frame
from ava.photometry.process import qc_flags

Q = dict(min_matched=5, max_zp_scatter=0.05, max_fwhm_arcsec=4.5, max_zp_dev=0.5, max_agn_peak_frac=0.8)


def _row(**kw):
    r = dict(filter="gp", camera="ep04", zp=23.0, n_matched=50, agn_matched=1, agn_flags=0, zp_scatter=0.01,
             fwhm_arcsec=2.0, zp_dev=0.0, saturate=118000.0, agn_peak=50000.0)
    r.update(kw)
    return r


def test_calibrate_frame_returns_agn_peak():
    n = 8
    ref = pd.DataFrame({"star_id": np.arange(n) + 1, "quality_ok": True, "lco_g": np.linspace(15, 16, n),
                        "lco_g_err": 0.01, "lco_i": 14.0})
    meas = pd.DataFrame({"star_id": list(ref.star_id) + [99], "is_agn": [False] * n + [True],
                         "mag": list(ref.lco_g - 23.0) + [-9.0], "magerr": 0.01, "sex_flags": 0,
                         "flux_max": 1000.0, "background": 200.0, "x": 500.0, "y": 500.0})
    meas.loc[meas.is_agn, "flux_max"] = 99800.0
    _, zp, agn = calibrate_frame(meas, ref, filt="gp", exptime=1.0, settings=ZPSettings())
    assert np.isfinite(zp.zp) and agn["peak"] == 100000.0


def test_agn_saturated_flag():
    assert qc_flags(_row(), Q) == []
    assert qc_flags(_row(agn_peak=0.81 * 118000), Q) == ["agn_saturated"]
    assert qc_flags(_row(agn_peak=200000.0, saturate=None), Q) == []          # level unknown: no flag
    assert qc_flags(_row(agn_peak=None), Q) == []                             # old rows without a peak
    assert qc_flags(_row(agn_peak=200000.0), {k: v for k, v in Q.items() if k != "max_agn_peak_frac"}) == []
    assert qc_flags(_row(agn_flags=4, agn_peak=200000.0), Q) == ["agn_flagged"]  # SExtractor flag first
