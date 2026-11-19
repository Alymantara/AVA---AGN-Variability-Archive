"""B16: a raw header without SATURATE / NAXIS gave saturate = naxis = NaN, and `if saturate:` treats NaN as true,
so every comparison with NaN failed and every standard was rejected: the frame got no_zp without a message."""
import numpy as np
import pandas as pd

from ava.photometry.calibration import ZPSettings, standard_mask
from ava.photometry.store import fill_camera_defaults


def _meas(n=10):
    return pd.DataFrame({"star_id": np.arange(n, dtype=float), "is_agn": False, "quality_ok": True, "sex_flags": 0,
                         "mag_inst": np.full(n, -10.0), "magerr": np.full(n, 0.01), "flux_max": np.full(n, 1e4),
                         "background": np.full(n, 100.0), "x": np.linspace(100, 3900, n), "y": np.full(n, 2000.0)})


def test_nan_saturation_and_size_skip_the_cut_not_every_star():
    m, ref, s = _meas(), np.full(10, 15.0), ZPSettings()
    ok = standard_mask(m, ref, saturate=None, naxis1=None, naxis2=None, s=s)
    assert ok.sum() == 10
    assert standard_mask(m, ref, saturate=np.nan, naxis1=np.nan, naxis2=np.nan, s=s).sum() == 10   # was 0
    assert standard_mask(m, ref, saturate=5000.0, naxis1=4096, naxis2=4096, s=s).sum() == 0          # cut still works


def test_camera_defaults_fill_a_header_without_saturate_or_size():
    defaults = {"fa": {"saturate": 128000, "naxis1": 4096, "naxis2": 4096}}
    meta = {"filter": "gp", "exptime": 60.0, "saturate": np.nan, "naxis1": np.nan, "naxis2": 4096.0}
    out = fill_camera_defaults(meta, "lsc1m005-fa15-20261010-0100-e91", defaults)
    assert out["saturate"] == 128000 and out["naxis1"] == 4096 and out["naxis2"] == 4096.0
    assert fill_camera_defaults(meta, "ogg2m001-ep04-20261010-0001-e91", defaults)["saturate"] is meta["saturate"]
    assert fill_camera_defaults(None, "x-fa15", defaults) is None
