"""Hβ-region fit, [O III] calibration and variability (ava.spectroscopy.lines) on synthetic spectra."""
import numpy as np
import pandas as pd

from ava.spectroscopy import lines as L


def synth(hb=8e-13, o3=3e-13, grey=1.0, cont=1e-14, noise=0.01, seed=0, sigma_b=30.0):
    rng = np.random.default_rng(seed)
    w = np.arange(4600.0, 5300.0, 1.7)
    f = cont * (1 - 0.1 * (w - 4930) / 1000) + L.gauss(w, hb, L.HB + 3, sigma_b) \
        + L.gauss(w, o3, L.O3B, 5.0) + L.gauss(w, o3 / L.O3_RATIO, L.O3A, 5.0) + L.gauss(w, 0.05 * o3, L.HB, 5.0)
    f = grey * f
    e = noise * np.median(f) * np.ones_like(w)
    return pd.DataFrame({"w": w, "f": f + rng.normal(0, e), "e": e})


def test_fit_recovers_fluxes():
    r = L.fit_hbeta(synth())
    assert r["ok"]
    assert abs(r["hb_broad"] / 8e-13 - 1) < 0.03 and abs(r["oiii5007"] / 3e-13 - 1) < 0.03
    assert abs(r["hb_broad"] - 8e-13) < 4 * r["hb_broad_err"] + 0.02 * 8e-13
    sp = synth()
    assert abs(L.integrated_hbeta(sp, r) / 8e-13 - 1) < 0.08
    assert not L.fit_hbeta(synth().iloc[:20])["ok"]            # no window coverage: refused


def test_oiii_calibration_removes_grey_factors():
    greys = [1.0, 0.5, 0.8, 0.3, 1.1, 0.9]
    rows = [{**{k: v for k, v in L.fit_hbeta(synth(grey=g, seed=i)).items() if k != "params"},
             "MJD": 60000.0 + i} for i, g in enumerate(greys)]
    t, ref = L.oiii_calibrate(pd.DataFrame(rows))
    raw = t.hb_broad.std() / t.hb_broad.mean()
    cal = t.hb_broad_cal.std() / t.hb_broad_cal.mean()
    assert raw > 0.3 and cal < 0.03 and t.good.all()
    v = L.variability(t.hb_broad_cal, t.hb_broad_cal_err)
    assert not np.isfinite(v["fvar"]) or v["fvar"] < 0.03            # constant line: no variability
    t2, _ = L.oiii_calibrate(pd.DataFrame(rows[:2]), min_spectra=3)   # too short a series: not scaled
    assert (t2.oiii_scale == 1).all() and not t2.oiii_calibrated.any()


def test_variability_and_nightly():
    rng = np.random.default_rng(1)
    f = 10 * (1 + 0.2 * np.sin(np.arange(200) / 10)) + rng.normal(0, 0.1, 200)
    v = L.variability(f, np.full(200, 0.1))
    assert abs(v["fvar"] - 0.2 / np.sqrt(2)) < 0.02 and v["rmax"] > 1.4
    t = pd.DataFrame({"MJD": [1.1, 1.2, 1.9, 2.1], "night": ["a", "a", "b", "b"], "x": [1.0, 3.0, 2.0, 2.0],
                      "e": [1.0, 1.0, 0.1, 0.1], "good": True})
    n = L.nightly(t, "x", "e")
    assert list(n.n_exp) == [2, 2] and n.x.iloc[0] == 2.0 and n.e.iloc[0] >= 1.0   # scatter sets the error


def test_export_prepspec(tmp_path):
    from astropy.io import fits

    from ava.spectroscopy import products as P

    def make(night, frame, mjd, flags="OK"):
        w = np.r_[np.linspace(3300, 5700, 300), np.linspace(4900, 10000, 300)]
        o = np.r_[np.full(300, 2), np.full(300, 1)]
        t = fits.BinTableHDU.from_columns([fits.Column("wavelength", "D", array=w), fits.Column("order", "I", array=o),
                                           fits.Column("flux_optimal", "D", array=np.full(600, 1e-15)),
                                           fits.Column("fluxerror_optimal", "D", array=np.full(600, 1e-17)),
                                           fits.Column("mask", "I", array=np.zeros(600))], name="EXTRACTED")
        h = fits.Header({"MJD-OBS": mjd, "EXPTIME": 864.0, "L1QFLAGS": flags, "OBJECT": "X", "SITEID": "ogg"})
        p = tmp_path / "red" / night / f"ogg2m001-en06-{night}-{frame}-e91-1d.fits"
        p.parent.mkdir(parents=True, exist_ok=True)
        fits.HDUList([fits.PrimaryHDU(header=h), t]).writeto(p)
        return p

    files = [make("20260915", "0002", 61299.0), make("20260813", "0005", 61266.0), make("20260818", "0008", 61271.0, "LOWSNR")]
    out = tmp_path / "prepspec"
    (out).mkdir(); (out / "T_old_ogg_0001_blue.dat").write_text("stale")
    r = P.export_prepspec(files, "T", out, exclude_flags=("LOWSNR",))
    assert r["blue"] == r["red"] == 2 and r["removed"] == 1 and len(r["skipped"]) == 1
    hjd = (out / "T_blue.hjd").read_text().split()
    assert hjd == ["T_20260813_ogg_0005_blue.dat", "61266.00500", "T_20260915_ogg_0002_blue.dat", "61299.00500"]
    d = np.loadtxt(out / "T_20260915_ogg_0002_red.dat")
    assert d.shape[1] == 3 and d[:, 0].min() >= 5300 and np.allclose(d[:, 1], 1e-15)
