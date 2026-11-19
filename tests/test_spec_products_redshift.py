"""B06 / B07: spectroscopy products crashed for targets where FLOYDS' blue arm does not reach 5100 Å (z ≈ 0.095–0.114)
or the Hβ window (z > ~0.19).  Offline: synthetic per-spectrum fits through the fit cache, no FITS files."""
import numpy as np
import pandas as pd

from ava.spectroscopy import lines as L
from ava.spectroscopy import products as P


def test_nightly_of_nothing_keeps_its_columns():
    t = pd.DataFrame({"good": [True, True], "MJD": [60000.1, 60001.1], "cont5100": [np.nan, np.nan],
                      "cont5100_err": [np.nan, np.nan]})
    out = L.nightly(t, "cont5100", "cont5100_err")
    assert len(out) == 0 and list(out.columns) == ["night", "MJD", "cont5100", "cont5100_err", "n_exp"]


def test_hbeta_series_without_5100_continuum(tmp_path):
    """Hβ fitted on every spectrum, 5100 Å never covered: cont5100 is NaN everywhere (PG 0804+761, z = 0.102)."""
    z, s = 0.102, L.FitSettings()
    key = P.fit_key(s, z)
    rows, files = [], []
    for i in range(6):
        f = tmp_path / f"coj2m002-en12-2026101{i}-0006-e91-1d.fits"
        f.write_bytes(b"x")
        size, mtime = P._file_stamp(f)
        rows.append(dict(path=str(f), fit_key=key, file_size=size, file_mtime=mtime,
                         basename=f.name.split("-e91")[0] + "-e00", MJD=60000.2 + i, night=f"2026101{i}", qc="OK",
                         ok=True, hb_broad=2e-13, hb_broad_err=5e-15, oiii5007=1e-13 * (1 + 0.01 * i),
                         oiii5007_err=2e-15, cont5100=np.nan, cont5100_err=np.nan))
        files.append(f)
    cache = tmp_path / "hbeta_fits.parquet"
    pd.DataFrame(rows).to_parquet(cache, index=False)
    t, night, meta = P.hbeta_series(files, z, s, cache=cache)
    assert meta["n_fitted"] == 0 and len(night) == 6
    assert np.isfinite(night["hb"]).all() and night["cont5100"].isna().all()


def test_latest_hbeta_plot_skipped_when_window_not_covered(tmp_path):
    """z = 0.2: the blue arm (to ~5606 Å observed) ends before 4720 Å rest; there is nothing to plot."""
    from ava.spectroscopy import webplots as W

    w = np.linspace(3300, 5606, 500) / 1.2
    sp = pd.DataFrame({"w": w, "f": np.ones_like(w) * 1e-15, "e": np.ones_like(w) * 1e-17})
    out = W.latest_hbeta_fit(sp, {"ok": False}, L.FitSettings(), {"DATE-OBS": "2026-10-10", "MJD-OBS": 60000.0},
                             "PG 0923+201", 0.2, tmp_path / "hb", formats=("png",))
    assert out == [] and not list(tmp_path.glob("hb*"))


def test_hbeta_arm_choice():
    """B08: one arm per target; red above the configured redshift."""
    import pytest
    assert L.hbeta_arm(0.03) == "blue" and L.hbeta_arm(0.102) == "red" and L.hbeta_arm(0.278) == "red"
    assert L.hbeta_arm(0.3, "blue") == "blue" and L.hbeta_arm(0.01, "red") == "red"
    assert L.hbeta_arm(0.05, "auto", red_above_z=0.04) == "red"
    with pytest.raises(ValueError):
        L.hbeta_arm(0.1, "green")


def test_fit_key_blue_unchanged_red_distinct():
    s = L.FitSettings()
    assert P.fit_key(s, 0.1) == P.fit_key(s, 0.1, "blue")          # existing caches stay valid
    assert P.fit_key(s, 0.1, "red") != P.fit_key(s, 0.1)            # a red-arm fit is never taken for a blue one


def test_arm_spectrum_reads_the_red_order(tmp_path):
    from astropy.io import fits
    from astropy.table import Table
    w = np.r_[np.linspace(3300, 5600, 50), np.linspace(4900, 10000, 50)]
    t = Table({"order": np.r_[np.full(50, 2), np.full(50, 1)], "wavelength": w, "mask": np.zeros(100, int),
               "flux_optimal": np.r_[np.full(50, 2.0), np.full(50, 1.0)], "fluxerror_optimal": np.full(100, 0.1)})
    f = tmp_path / "x-1d.fits"
    fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU(t, name="EXTRACTED")]).writeto(f)
    red = L.arm_spectrum(f, 0.1, "red")
    assert np.allclose(red.f, 1.0) and red.w.min() == pytest_approx(4900 / 1.1)
    assert np.allclose(L.arm_spectrum(f, 0.1, "blue").f, 2.0)


def pytest_approx(x):
    import pytest
    return pytest.approx(x)
