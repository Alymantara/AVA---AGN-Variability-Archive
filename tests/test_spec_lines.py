"""Hβ-region fit, [O III] calibration and variability (ava.spectroscopy.lines) on synthetic spectra."""
import numpy as np
import pandas as pd
import pytest

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


def test_oiii_lines_measured_independently():
    """Each [O III] line on its own recovers the injected doublet (5007/4959 = 2.98), also under a broad Hβ."""
    sp = synth(o3=3e-13, noise=0.005)
    r = L.fit_hbeta(sp)
    n = L.narrow_line_fluxes(sp, r)
    assert abs(n["oiii5007_int"] / 3e-13 - 1) < 0.05
    assert abs(n["oiii4959_int"] / (3e-13 / L.O3_RATIO) - 1) < 0.08
    assert n["oiii5007_int_err"] > 0 and n["oiii4959_int_err"] > 0
    assert np.isnan(L.narrow_line_fluxes(sp, {})["oiii5007_int"])        # no fit: nothing measured


def test_lightcurve_csv_keeps_mjd(tmp_path):
    """QC-0002: "%.6g" rounded MJD 60123.456 to 60123.5."""
    import pandas as pd

    from ava.spectroscopy.products import write_lightcurve_csv

    out = pd.DataFrame({"target": ["X", "X"], "MJD": [60123.456789, 59000.123456], "night": ["20230701", "20200531"],
                        "n_exp": [2, 1], "hbeta_flux": [1.234567e-13, 2.0e-13], "hbeta_flux_err": [1e-15, 2e-15],
                        "cont5100": [3e-15, 4e-15], "cont5100_err": [1e-17, 1e-17], "oiii_calibrated": [True, True]})
    path = tmp_path / "lc.csv"
    write_lightcurve_csv(out, path, "header")
    back = pd.read_csv(path, comment="#")
    assert np.abs(back["MJD"].values - out["MJD"].values).max() <= 1e-5
    assert back["hbeta_flux"].values == pytest.approx(out["hbeta_flux"].values, rel=1e-5)


# --- QC-0009: additive model, grey factors, and an [O III] calibrator independent of the broad lines -------------

def synth_blend(hb=1.0, cont=1.0, slope=1.0, grey=1.0, seed=0):
    """Asymmetric broad Hβ (main + red shoulder) + He I / Fe II blend under [O III], all scaling with ``hb``;
    [O III] core (σ 6 Å) + a real blue wing (σ 8 Å, 25 %), constant.  Returns the spectrum and the true [O III]."""
    w = np.arange(4650.0, 5150.0, 1.74)
    H, o3c, o3w = 6e-13 * hb, 1.6e-13, 0.4e-13
    f = (cont * 9.8e-15 - slope * 5.4e-16 * (w - 4930) / 100
         + L.gauss(w, 0.78 * H, L.HB - 3, 30.0) + L.gauss(w, 0.22 * H, L.HB + 50, 40.0)
         + L.gauss(w, 0.075 * H, 4923, 20.0) + L.gauss(w, 0.085 * H, 5017, 20.0)
         + sum(L.gauss(w, F / r, lam + d, sg) for F, d, sg in ((o3c, -2.0, 6.0), (o3w, -4.0, 8.0))
               for lam, r in ((L.O3B, 1.0), (L.O3A, L.O3_RATIO)))
         + L.gauss(w, 2.5e-14, L.HB - 2, 6.0))
    e = np.full_like(w, 1.2e-16)
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"w": w, "f": grey * (f + rng.normal(0, e)), "e": grey * e}), grey * (o3c + o3w)


def test_continuum_does_not_enter_line_fluxes():
    """Lines are additive Gaussians from zero: a different linear continuum under the same lines (same noise)
    changes no line flux."""
    ref = L.fit_hbeta(synth_blend()[0])
    for cont, slope in ((0.5, 1.0), (3.0, 1.0), (1.0, -2.0)):
        r = L.fit_hbeta(synth_blend(cont=cont, slope=slope)[0])
        for k in ("hb_broad", "oiii5007", "blend_flux"):
            assert r[k] == pytest.approx(ref[k], rel=1e-4)


def test_grey_factor_scales_everything():
    rows = []
    for i, k in enumerate((1.0, 0.4, 0.7, 1.2)):
        r = L.fit_hbeta(synth_blend(grey=k)[0])
        assert r["oiii5007"] / k == pytest.approx(L.fit_hbeta(synth_blend()[0])["oiii5007"], rel=1e-4)
        rows.append({**{x: v for x, v in r.items() if x != "params"}, "MJD": 60000.0 + i})
    t, _ = L.oiii_calibrate(pd.DataFrame(rows))
    assert np.allclose(t.oiii_scale * np.array([1.0, 0.4, 0.7, 1.2]), t.oiii_scale.iloc[0] * 1.0, rtol=1e-4)


def test_oiii_independent_of_broad_lines():
    """The [O III] calibrator must not follow broad Hβ + the He I/Fe II blend (QC-0009: the old 37.5 Å 'wing'
    took the blend, [O III] rose 25 % over Hβ ×0.5–1.6 and the calibrated Hβ was damped)."""
    def spread(s):
        o3 = [L.fit_hbeta(synth_blend(hb=h, seed=3)[0], s)["oiii5007"] for h in (0.5, 1.0, 1.6)]
        return (max(o3) - min(o3)) / np.mean(o3)

    assert spread(L.FitSettings()) < 0.20            # 14 % (one broad Gaussian cannot follow Hβ's red shoulder)
    old = L.FitSettings(blend=False, oiii_wing_sigma_max=37.5, oiii_wing_max_shift=20.0)   # before QC-0009
    assert spread(old) > 0.35                         # 47 %
    r = L.fit_hbeta(synth_blend(seed=3)[0])
    assert r["params"]["sw"] <= L.FitSettings().oiii_wing_sigma_max + 1e-9 and r["blend_flux"] > 0


def test_blend_off_reproduces_old_model_parts():
    s = L.FitSettings(blend=False)
    r = L.fit_hbeta(synth(), s)
    assert "Fe1" not in r["params"] and r["blend_flux"] == 0.0
    assert np.all(L.model(r["params"], np.linspace(4800, 5000, 5), s, "blend") == 0)
