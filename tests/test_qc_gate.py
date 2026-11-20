"""Frame QC gate before PyTICS (20 Nov 2026, ESO 511-30): AGN FLAGS mask, zero-point flags ignored by PyTICS,
zp_offset against the camera's own median; offline."""
import pandas as pd

from ava.photometry import store
from ava.photometry.process import qc_flags, requalify, zp_dev

Q = dict(min_matched=5, max_zp_scatter=0.05, max_fwhm_arcsec=4.5, max_zp_dev=0.5, max_agn_peak_frac=0.8)


def _row(**kw):
    r = dict(filter="rp", camera="fa15", zp=23.0, n_matched=50, agn_matched=1, agn_flags=0, zp_scatter=0.01,
             fwhm_arcsec=2.0, zp_dev=0.0, saturate=128000.0, agn_peak=20000.0)
    r.update(kw)
    return r


def test_deblended_agn_is_not_flagged():
    for fl in (1, 2, 3):                                    # neighbours / deblended from the host: MAG_APER fine
        assert qc_flags(_row(agn_flags=fl), Q) == []
    for fl in (4, 8, 16, 6, 18):                            # saturated / truncated / aperture incomplete
        assert qc_flags(_row(agn_flags=fl), Q) == ["agn_flagged"]
    assert qc_flags(_row(agn_flags=2), {**Q, "agn_bad_flags": 31}) == ["agn_flagged"]   # configurable
    # a deblended AGN still gets the peak test
    assert qc_flags(_row(agn_flags=2, agn_peak=0.9 * 128000), Q) == ["agn_saturated"]
    assert qc_flags(_row(agn_flags=None), Q) == []


def test_zp_dev_per_camera_with_family_fallback():
    fq = pd.DataFrame({"camera": ["fa03"] * 12 + ["fa15"] * 12 + ["fa07"] * 2, "filter": "up",
                       "zp": [20.0] * 12 + [20.7] * 12 + [21.5] * 2})
    d = zp_dev(fq, min_frames=10)
    assert (d[:24].abs() < 1e-9).all()                      # two units 0.7 mag apart: neither is offset
    assert abs(d.iloc[-1] - (21.5 - 20.7)) < 1e-9           # 2 frames only: against the "fa" median
    fq.loc[0, "zp"] = 19.0                                  # a cloudy frame is still caught
    assert abs(zp_dev(fq).iloc[0] + 1.0) < 1e-9


def test_requalify_does_not_flag_a_whole_camera(tmp_path):
    db = tmp_path / "phot.sqlite"
    rows = [dict(frame=f"{c}-{i}", data_id="T", filter="up", camera=c, mjd_mid=61000 + i, zp=z, n_matched=50,
                 agn_matched=1, agn_flags=0, zp_scatter=0.02, fwhm_arcsec=2.0, qc_flags="", qc_pass=1)
            for c, z in (("fa03", 20.0), ("fa15", 20.7), ("fa05", 19.4)) for i in range(12)]
    store.write_frame_qc(db, rows)
    fq = requalify(db, "T", Q)
    assert (fq["qc_pass"] == 1).all()


def test_pytics_gate_ignores_zero_point_flags():
    fq = pd.DataFrame({"qc_pass": [1, 0, 0, 0, 0, 0, 0],
                       "qc_flags": ["", "zp_scatter", "no_zp,zp_offset", "seeing", "zp_scatter,seeing",
                                    "agn_flagged", "error:ValueError"]})
    assert list(store.pytics_pass(fq)) == [True, True, True, False, False, False, False]
    assert list(store.pytics_pass(fq, ignore_flags=())) == [True] + [False] * 6     # strict: qc_pass only


def test_load_pytics_keeps_zp_flagged_frames(tmp_path):
    db = tmp_path / "phot.sqlite"
    common = dict(data_id="T", filter="zs", tel="1m009", camera="fa15", airmass=1.2, fwhm_arcsec=2.0)
    store.write_frame_qc(db, [dict(frame="ok", mjd_mid=61000.1, qc_pass=1, qc_flags="", **common),
                              dict(frame="zps", mjd_mid=61000.2, qc_pass=0, qc_flags="zp_scatter", **common),
                              dict(frame="see", mjd_mid=61000.3, qc_pass=0, qc_flags="seeing", **common)])
    frames = ["ok", "zps", "see"]
    store.update_measurements(tmp_path / "measurements.parquet", pd.DataFrame(
        {"frame": [f for f in frames for _ in (0, 1)], "star_id": [1, 2] * 3, "is_agn": [True, False] * 3,
         "mag_inst": -9.0, "magerr": 0.01, "x": 1.0, "y": 1.0, "sex_flags": 0, "sep_arcsec": 0.1,
         "used_in_zp": False}))
    assert set(store.load_pytics(tmp_path, db, "T", "zs")["frame"]) == {"ok", "zps"}
    assert set(store.load_pytics(tmp_path, db, "T", "zs", ignore_flags=())["frame"]) == {"ok"}
