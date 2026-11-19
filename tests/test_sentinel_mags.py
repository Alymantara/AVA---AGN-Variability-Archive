"""B11: SExtractor writes MAG_APER = MAGERR_APER = 99 when the aperture flux is <= 0.  Those rows went into
measurements.parquet and on into PyTICS (Mrk 817: 4865 of 2.2 M rows, 3310 with FLAGS 0, which the flag cut
keeps).  Offline."""
from pathlib import Path

import numpy as np
import pandas as pd

from ava.photometry import catalogs as C
from ava.photometry import store


def test_measurements_drop_no_measurement_rows():
    mag = np.array([[15.0, 14.9], [99.0, 99.0], [16.0, 15.8], [14.0, 13.9]])
    err = np.array([[0.01, 0.01], [99.0, 99.0], [0.02, 813.4], [0.01, 0.01]])
    cat = C.Catalog(table=pd.DataFrame({"x": [1, 2, 3, 4]}), mag_aper=mag, magerr_aper=err, n_apertures=2,
                    path=Path("ogg2m001-ep04-20261010-0001-e91_cat.fits"))
    matched = pd.DataFrame({"star_id": [10, 11, 12, np.nan], "is_agn": [False, True, False, False],
                            "x": [1, 2, 3, 4]})
    out = C.measurements(cat, matched, 1)
    assert out["star_id"].tolist() == [10]                   # 11: flux <= 0 (99); 12: error 813 mag; 4: unmatched
    assert out["mag"].tolist() == [14.9] and out["frame"].iloc[0] == "ogg2m001-ep04-20261010-0001-e91"


def test_load_pytics_ignores_sentinel_rows_already_stored(tmp_path):
    db = tmp_path / "phot.sqlite"
    store.write_frame_qc(db, [dict(frame="f1", data_id="T", filter="gp", mjd_mid=61000.25, qc_pass=1,
                                   tel="1m008", camera="fa05", airmass=1.2, fwhm_arcsec=2.0)])
    store.update_measurements(tmp_path / "measurements.parquet", pd.DataFrame(
        {"frame": ["f1"] * 4, "star_id": [1, 2, 3, 4], "is_agn": [True, False, False, False],
         "mag_inst": [-9.0, 99.0 + 2.5 * np.log10(60), -10.0, -11.0], "magerr": [0.01, 99.0, 0.01, 813.0],
         "x": [1.0] * 4, "y": [1.0] * 4, "sex_flags": [0] * 4, "sep_arcsec": [0.1] * 4,
         "used_in_zp": [False, True, True, True]}))
    d = store.load_pytics(tmp_path, db, "T", "gp")
    assert sorted(d["star_id"]) == [1, 3]
