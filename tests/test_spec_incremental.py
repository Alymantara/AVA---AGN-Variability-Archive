"""Incremental spectroscopy products: fit cache, stored arm offsets, mean/RMS edge cases, pending nights."""
import os

import numpy as np
import pandas as pd
from astropy.io import fits

from ava.spectroscopy import lines as L
from ava.spectroscopy import products as P

Z = 0.02


def _g(w, f, mu, s):
    return f / (np.sqrt(2 * np.pi) * s) * np.exp(-0.5 * ((w - mu) / s) ** 2)


def make(dirp, night, frame, mjd, shift_blue=0.0, shift_red=0.0, hb=8e-13, grey=1.0):
    """A synthetic -1d: blue arm with Hβ + [O III], red arm with [O I], Hα, [S II]; arm shifts in rest Å."""
    wb = np.arange(3300, 5700, 1.7)
    wr = np.arange(4900, 10000, 3.5)
    rb, rr = wb / (1 + Z) - shift_blue, wr / (1 + Z) - shift_red
    fb = 1e-14 + _g(rb, hb, L.HB, 30) + _g(rb, 3e-13, L.O3B, 4) + _g(rb, 1e-13, L.O3A, 4) + _g(rb, 2e-14, L.HB, 4)
    fr = 8e-15 + _g(rr, 2e-13, 6300.3, 5) + _g(rr, 2e-12, 6562.8, 40) + _g(rr, 1.5e-13, 6716.4, 5) \
        + _g(rr, 1.2e-13, 6730.8, 5)
    w = np.r_[wb, wr]
    f = grey * np.r_[fb, fr]
    o = np.r_[np.full(len(wb), 2), np.full(len(wr), 1)]
    t = fits.BinTableHDU.from_columns([fits.Column("wavelength", "D", array=w), fits.Column("order", "I", array=o),
                                       fits.Column("flux_optimal", "D", array=f),
                                       fits.Column("fluxerror_optimal", "D", array=0.005 * f),
                                       fits.Column("mask", "I", array=np.zeros(len(w)))], name="EXTRACTED")
    h = fits.Header({"MJD-OBS": mjd, "EXPTIME": 600.0, "L1QFLAGS": "OK", "OBJECT": "T", "SITEID": "ogg",
                     "DATE-OBS": "2026-01-01T00:00:00", "AIRMASS": 1.2, "APERWID": 6.0})
    p = dirp / night / f"ogg2m001-en06-{night}-{frame}-e91-1d.fits"
    p.parent.mkdir(parents=True, exist_ok=True)
    fits.HDUList([fits.PrimaryHDU(header=h), t]).writeto(p, overwrite=True)
    return p


def test_fit_cache_reused_and_refit_on_change(tmp_path):
    files = [make(tmp_path / "r", f"202601{d:02d}", "0001", 61000 + d, grey=g) for d, g in ((1, 1.0), (2, 0.6), (3, 0.9))]
    cache = tmp_path / "hbeta_fits.parquet"
    t1, n1, m1 = P.hbeta_series(files, Z, cache=cache)
    assert m1["n_fitted"] == 3 and m1["n_cached"] == 0 and m1["oiii_calibrated"]
    t2, n2, m2 = P.hbeta_series(files, Z, cache=cache)
    assert m2["n_fitted"] == 0 and m2["n_cached"] == 3
    assert np.allclose(t1.hb_broad_cal, t2.hb_broad_cal)
    assert abs(t2.hb_broad_cal.std() / t2.hb_broad_cal.mean()) < 0.02          # grey factors removed
    os.utime(files[1], (1, 1))                                                   # a changed file is refitted
    _, _, m3 = P.hbeta_series(files, Z, cache=cache)
    assert m3["n_fitted"] == 1
    _, _, m4 = P.hbeta_series(files, Z, L.FitSettings(oiii_wing=False), cache=cache)
    assert m4["n_fitted"] == 3                                                   # new settings: all refitted


def test_offsets_stored_and_recovered(tmp_path):
    shifts = [(0.0, 0.0), (0.8, -1.5), (-0.5, 2.0), (0.3, 0.7)]
    files = [make(tmp_path / "r", f"202601{i + 1:02d}", "0001", 61000 + i, sb, sr) for i, (sb, sr) in enumerate(shifts)]
    t = pd.DataFrame({"path": [str(f) for f in files[:3]]})
    off = P.arm_offsets(t, Z, tmp_path)
    assert (tmp_path / "spec_offsets.csv").exists() and (tmp_path / "spec_align_template.npz").exists()
    rel_b = off.shift_blue_A - off.shift_blue_A.iloc[0]
    rel_r = off.shift_red_A - off.shift_red_A.iloc[0]
    assert np.allclose(rel_b, [s[0] for s in shifts[:3]], atol=0.15)
    assert np.allclose(rel_r, [s[1] for s in shifts[:3]], atol=0.4)
    off2 = P.arm_offsets(pd.DataFrame({"path": [str(f) for f in files]}), Z, tmp_path)   # one new spectrum
    assert np.allclose(off2.shift_blue_A.iloc[:3], off.shift_blue_A, atol=1e-3)          # old ones read back
    assert abs(off2.shift_red_A.iloc[3] - off.shift_red_A.iloc[0] - 0.7) < 0.4


def test_mean_rms_any_number_of_nights(tmp_path):
    files = [make(tmp_path / "r", f"202601{d:02d}", "0001", 61000 + d, hb=h) for d, h in ((1, 8e-13), (2, 1e-12))]
    t, _, _ = P.hbeta_series(files[:1], Z)
    one = P.mean_rms(t, Z)
    assert one["blue"]["n_nights"] == 1 and one["blue"]["rms"] is None and np.isfinite(one["blue"]["mean"]).all()
    t, _, _ = P.hbeta_series(files, Z)
    two = P.mean_rms(t, Z)
    rms, w = two["blue"]["rms"], two["blue"]["w"]
    assert rms[np.abs(w - L.HB) < 30].max() > 5 * np.median(rms[(w > 4000) & (w < 4500)])   # Hβ varies
    assert P.mean_rms(pd.DataFrame(columns=["path", "good", "ok"]), Z) == {"calibrated": False, "n_spectra": 0}


def test_pending_nights(tmp_path):
    from ava.pipeline.tasks.spec_reduce import pending_nights

    raw, red = tmp_path / "raw", tmp_path / "reduced"
    for night in ("20260101", "20260102"):
        (raw / night).mkdir(parents=True)
        (raw / night / f"ogg2m001-en06-{night}-0005-e00.fits.fz").write_bytes(b"x")
        (raw / night / f"ogg2m001-en06-{night}-0006-a00.fits.fz").write_bytes(b"x")
    (red / "20260101").mkdir(parents=True)
    (red / "20260101" / "ogg2m001-en06-20260101-0005-e91-1d.fits.fz").write_bytes(b"x")
    assert pending_nights(raw, red) == ["20260102"]
