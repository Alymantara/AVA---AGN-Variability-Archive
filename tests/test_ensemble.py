"""Offline tests for ava.photometry.ensemble (PyTICS port) and intercal on synthetic data."""

import numpy as np
import pandas as pd
import pytest

from ava.photometry import ensemble as E
from ava.photometry import intercal as IC


def synthetic(n_stars=40, n_epochs=120, scopes=("1m001-fa11", "1m008-fa05", "2m001-ep04"), seed=1, t0=60000.0):
    rng = np.random.default_rng(seed)
    m_true = np.sort(rng.uniform(-12, -7, n_stars))
    off = {s: o for s, o in zip(scopes, [0.0, 0.2, -1.1])}
    rows = []
    for t in range(n_epochs):
        scope = scopes[t % len(scopes)]
        dmagt = rng.normal(0, 0.15)
        mjd = t0 + t * 0.7
        frame = f"f{t:05d}"
        for s in range(n_stars):
            err = 0.002 + 0.01 * np.exp(m_true[s] + 7)
            rows.append(dict(frame=frame, MJD=mjd, Filter="gp", star_id=1000 + s, is_agn=False, scope=scope,
                             mag_inst=m_true[s] + dmagt + off[scope] + rng.normal(0, err), magerr=err, sex_flags=0,
                             dmagt_true=dmagt))
        agn = -9.0 + 0.3 * np.sin(mjd / 20.0)
        rows.append(dict(frame=frame, MJD=mjd, Filter="gp", star_id=-1, is_agn=True, scope=scope,
                         mag_inst=agn + dmagt + off[scope] + rng.normal(0, 0.003), magerr=0.003, sex_flags=0,
                         dmagt_true=dmagt))
    return pd.DataFrame(rows), off


def test_fit_recovers_scope_offsets_and_agn():
    d, off = synthetic()
    sol = E.fit(d, agn_id=-1)
    assert sol.meta["converged"]
    # the split DMAGT / DMAGS is a convention (DMAGT zero-mean per scope); the per-epoch
    # total correction DMAGT_t + DMAGS_k must match the injected one up to a constant
    ep = sol.epochs.merge(sol.scopes[["scope", "DMAGS"]], on="scope")
    tr = d.groupby("frame").first()
    true_total = ep["frame"].map(tr["dmagt_true"] + tr["scope"].map(off))
    diff = ep["DMAGT"] + ep["DMAGS"] - true_total
    assert np.std(diff - diff.median()) < 1.5e-3
    lc = E.apply(sol, d[d.is_agn])
    truth = -9.0 + 0.3 * np.sin(lc["MJD"] / 20.0)
    resid = lc["mag"] - truth
    assert np.std(resid - np.median(resid)) < 0.006       # σ_phot 3 mmag + ensemble noise


def test_update_matches_full_refit():
    d, _ = synthetic(n_epochs=150)
    cut = d["MJD"].quantile(0.8)
    base = E.fit(d[d.MJD < cut], agn_id=-1)
    upd, info = E.update(base, d)
    assert info["new_epochs"] == d.loc[d.MJD >= cut, "frame"].nunique()
    full = E.fit(d, agn_id=-1)
    a = E.apply(upd, d[d.is_agn]).set_index("frame")["mag"]
    b = E.apply(full, d[d.is_agn]).set_index("frame")["mag"]
    diff = (a - b)[d.loc[d.is_agn & (d.MJD >= cut), "frame"]]
    assert np.std(diff - diff.median()) < 1e-3


def test_flagged_comparison_rows_removed():
    d, _ = synthetic()
    bad = (d.star_id == 1005) & (d.frame == "f00010")
    d.loc[bad, "mag_inst"] += 2.5
    d.loc[bad, "sex_flags"] = 24
    sol = E.fit(d, agn_id=-1)
    assert sol.meta["converged"]
    assert len(E.clean_comparisons(d)) == len(d) - 1


def test_solution_roundtrip(tmp_path):
    d, _ = synthetic(n_epochs=30)
    sol = E.fit(d, agn_id=-1)
    sol.save(tmp_path / "gp")
    back = E.Solution.load(tmp_path / "gp")
    pd.testing.assert_frame_equal(back.stars, sol.stars)
    assert back.star_scope is not None and back.meta["filter"] == "gp"


def test_intercal_recovers_additive_offset():
    rng = np.random.default_rng(3)
    t = np.arange(0, 400, 1.0)
    f = 8 + 1.5 * np.sin(t / 30)
    rows = []
    for i, ti in enumerate(t):
        scope = "1m001-fa11" if i % 2 else "2m001-ep04"
        b = -0.55 if scope.endswith("ep04") else 0.0
        F = f[i] + b + rng.normal(0, 0.02)
        rows.append(dict(MJD=ti + 0.5, Filter="gp", scope=scope, F=F, Ferr=0.02))
    lc = pd.DataFrame(rows)
    lc["mag"], lc["mag_err"] = IC.to_mag(lc["F"], lc["Ferr"])
    tab = IC.intercalibrate(lc, ["1m001-fa11"])
    r = tab[tab.scope == "2m001-ep04"].iloc[0]
    assert r["b1"] == pytest.approx(-0.55, abs=0.02)
    assert r["a"] == pytest.approx(1.0, abs=0.03)
    out = IC.apply_intercal(lc, tab, scopes=["2m001-ep04"])
    ep = out[out.scope == "2m001-ep04"]
    assert np.mean(ep["F_ic"] - ep["F"]) == pytest.approx(0.55, abs=0.02)


def test_scope_colour_terms_recovered():
    """Cameras with different colour responses: m_obs gets CK_k (c_s - c0)."""
    rng = np.random.default_rng(7)
    n_stars, n_ep = 50, 150
    scopes = ["1m001-fa11", "1m008-fa05", "1m014-fa20"]
    ck_true = {"1m001-fa11": 0.0, "1m008-fa05": 0.03, "1m014-fa20": -0.02}
    m_true = rng.uniform(-12, -8, n_stars)
    col = pd.Series(rng.uniform(0.2, 2.5, n_stars), index=1000 + np.arange(n_stars))
    rows = []
    for t in range(n_ep):
        k = scopes[t % 3]
        dm = rng.normal(0, 0.1)
        for s in range(n_stars):
            rows.append(dict(frame=f"f{t}", MJD=60000 + t, Filter="gp", star_id=1000 + s, is_agn=False, scope=k,
                             mag_inst=m_true[s] + dm + ck_true[k] * col.iloc[s] + rng.normal(0, 0.003),
                             magerr=0.003, sex_flags=0))
        rows.append(dict(frame=f"f{t}", MJD=60000 + t, Filter="gp", star_id=-1, is_agn=True, scope=k,
                         mag_inst=-10 + dm + ck_true[k] * 0.3, magerr=0.003, sex_flags=0))
    d = pd.DataFrame(rows)
    plain = E.fit(d, agn_id=-1)
    sol = E.fit(d, agn_id=-1, colours=col)
    assert sol.meta["converged"] and sol.meta["colour_terms"]
    ck = sol.scopes.set_index("scope")["CK"]
    for a, b in [("1m008-fa05", "1m001-fa11"), ("1m014-fa20", "1m001-fa11")]:
        assert ck[a] - ck[b] == pytest.approx(ck_true[a] - ck_true[b], abs=1e-3)
    # the AGN (colour 0.3) is consistent across cameras only with the colour terms
    lc = E.apply(sol, d[d.is_agn], colour=0.3)
    lc0 = E.apply(plain, d[d.is_agn])
    spread = lc.groupby("scope").mag.median().pipe(lambda x: x.max() - x.min())
    spread0 = lc0.groupby("scope").mag.median().pipe(lambda x: x.max() - x.min())
    assert spread < 2e-3 < spread0


def _sol_with_zp(filt, zp, zp_fit_zp, C=0.03):
    meta = {"filter": filt, "zp": zp, "zp_err": 0.002, "colour_terms": True,
            "zp_fit": {"filter": filt, "zp": zp_fit_zp, "C": C, "c0": 0.8, "agn_colour": 0.34, "zp_agn": zp}}
    empty = pd.DataFrame()
    return E.Solution(filt, empty, empty, empty, meta=meta)


def test_zp_summary_matches_applied_meta(tmp_path):
    # A stale summary from an earlier fit (the Mrk 817 gp case: 0.022 mag off).
    (tmp_path / "pytics").mkdir()
    (tmp_path / "pytics" / E.ZP_SUMMARY).write_text(
        '{"gp": {"zp": 23.9234, "zp_agn": 23.9043}, "Y": {"zp": 20.09, "zp_agn": 20.11}}')
    sols = {"gp": _sol_with_zp("gp", 23.9262, 23.9456), "B": _sol_with_zp("B", 23.3370, 23.3300)}
    out = E.write_zp_summary(tmp_path, sols)
    import json
    disk = json.loads((tmp_path / "pytics" / E.ZP_SUMMARY).read_text())
    assert disk == out
    for f, s in sols.items():
        assert disk[f]["zp_agn"] == s.meta["zp"]                 # what apply() uses
        assert disk[f]["zp"] == s.meta["zp_fit"]["zp"]
        assert disk[f]["colour_terms"] is True
    assert disk["Y"]["zp_agn"] == 20.11                          # filters not refitted are kept


def test_zp_summary_drops_filter_without_absolute_zp(tmp_path):
    E.write_zp_summary(tmp_path, {"gp": _sol_with_zp("gp", 23.9, 23.9)})
    plain = E.Solution("gp", pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), meta={"filter": "gp"})
    assert E.write_zp_summary(tmp_path, {"gp": plain}) == {}


def test_intercal_per_season_offsets():
    """a camera whose additive offset changes between seasons is fixed season by season."""
    from ava.photometry import intercal as IC

    rng = np.random.default_rng(3)
    rows = []
    for season, b in ((0, -0.5), (1, -0.8)):
        for n in range(80):
            t = 1000 * season + n + 0.1
            F = 8 + np.sin(t / 15)
            for scope, off in (("1m005-fa05", 0.0), ("2m001-ep04", b)):
                f = F + off + rng.normal(0, 0.01)
                rows.append(dict(Filter="gp", scope=scope, MJD=t + (0.2 if off else 0), good=True,
                                 mag=IC.to_mag(f), mag_err=0.002))
    lc = pd.DataFrame(rows)
    lc["season"] = IC.seasons(lc.MJD, 60)
    assert sorted(lc.season.unique()) == [0, 1]
    tab = pd.concat([IC.intercalibrate(lc, ["1m005-fa05"]).assign(season=-1),
                     IC.intercalibrate_by_season(lc, ["1m005-fa05"], ["2m001-ep04"])], ignore_index=True)
    out = IC.apply_intercal(lc, tab, scopes=["2m001-ep04"])
    ep = out[out.scope == "2m001-ep04"]
    for s, b in ((0, -0.5), (1, -0.8)):
        assert abs(ep[ep.season == s].ic_b.iloc[0] - b) < 0.02


def test_load_pytics_filter_without_frames(tmp_path):
    """A filter with no passing frame (Y for most targets) gives an empty table, not an ArrowTypeError
    (host run 18 Nov 2026: pyarrow rejects an empty "in" filter on the string frame column)."""
    from ava.photometry import store

    db = tmp_path / "phot.sqlite"
    store.write_frame_qc(db, [dict(frame="f1", data_id="T", filter="gp", mjd_mid=61000.25, qc_pass=1,
                                   tel="1m008", camera="fa05", airmass=1.2, fwhm_arcsec=2.0)])
    store.update_measurements(tmp_path / "measurements.parquet", pd.DataFrame(
        {"frame": ["f1", "f1"], "star_id": [1, 2], "is_agn": [True, False], "mag_inst": [-9.0, -10.0],
         "magerr": [0.01, 0.01], "x": [1.0, 2.0], "y": [1.0, 2.0], "sex_flags": [0, 0],
         "sep_arcsec": [0.1, 0.1], "used_in_zp": [False, True]}))
    d = E.load_target(tmp_path, db, "T", "Y")
    assert d.empty and "frame" in d and "scope" in d and d["frame"].nunique() == 0
    assert len(E.load_target(tmp_path, db, "T", "gp")) == 2


def test_run_target_end_to_end_first_full_fit(tmp_path):
    """The whole PyTICS step on a fresh target folder (no pytics/ yet), with a filter that has no frames:
    both crashed on the Linux host on 18 Nov 2026 (empty-filter ArrowTypeError; absolute_zp_stars.parquet
    written before pytics/ existed)."""
    from ava.photometry import store

    rng = np.random.default_rng(3)
    n_stars, n_ep = 30, 60
    stars = 1000 + np.arange(n_stars)
    g_true = np.sort(rng.uniform(13, 17, n_stars))
    ref = pd.DataFrame({"star_id": np.r_[stars, -1], "lco_g": np.r_[g_true, np.nan], "lco_g_err": 0.01,
                        "lco_i": np.r_[g_true - 0.5 + rng.normal(0, 0.2, n_stars), np.nan], "lco_i_err": 0.01,
                        "quality_ok": np.r_[np.ones(n_stars, bool), False], "is_agn": np.r_[np.zeros(n_stars, bool), True]})
    ref.to_csv(tmp_path / "reference_stars.csv", index=False)
    qc, meas = [], []
    for k, filt in enumerate(("gp", "ip")):
        for t in range(n_ep):
            frame, cam = f"{filt}{t:04d}", ("fa05", "fa11")[t % 2]
            zp = -23.5 + rng.normal(0, 0.1)
            qc.append(dict(frame=frame, data_id="T", filter=filt, mjd_mid=60000.0 + t, qc_pass=1, tel="1m00" + cam[-1],
                           camera=cam, airmass=1.2, fwhm_arcsec=2.0))
            mags = np.r_[g_true - 0.5 * k, 15.0 + 0.2 * np.sin(t / 5)] + zp + rng.normal(0, 0.005, n_stars + 1)
            for sid, m, agn in zip(np.r_[stars, -1], mags, np.r_[np.zeros(n_stars, bool), True]):
                meas.append(dict(frame=frame, star_id=int(sid), is_agn=bool(agn), mag_inst=m, magerr=0.005, x=1.0,
                                 y=1.0, sex_flags=0, sep_arcsec=0.1, used_in_zp=not agn))
    db = tmp_path / "phot.sqlite"
    store.write_frame_qc(db, qc)
    store.update_measurements(tmp_path / "measurements.parquet", pd.DataFrame(meas))
    rep = E.run_target(tmp_path, db, "T", ["up", "gp", "ip", "Y"], mode="auto", log=lambda *a: None)
    assert set(rep) == {"gp", "ip"}
    assert (tmp_path / "pytics" / "absolute_zp_stars.parquet").exists()
    lc = pd.read_csv(tmp_path / "agn_lightcurve_pytics.csv")
    assert set(lc["Filter"]) == {"gp", "ip"} and len(lc) == 2 * n_ep


def _target_folder(tmp_path, cams=("fa05",), filters=("gp", "ip"), n_stars=30, n_ep=60, seed=3):
    """A fresh target folder (reference stars, frame QC, measurements) observed by ``cams`` only."""
    from ava.photometry import store

    rng = np.random.default_rng(seed)
    stars = 1000 + np.arange(n_stars)
    g_true = np.sort(rng.uniform(13, 17, n_stars))
    ref = pd.DataFrame({"star_id": np.r_[stars, -1], "lco_g": np.r_[g_true, np.nan], "lco_g_err": 0.01,
                        "lco_i": np.r_[g_true - 0.5 + rng.normal(0, 0.2, n_stars), np.nan], "lco_i_err": 0.01,
                        "quality_ok": np.r_[np.ones(n_stars, bool), False], "is_agn": np.r_[np.zeros(n_stars, bool), True]})
    ref.to_csv(tmp_path / "reference_stars.csv", index=False)
    qc, meas = [], []
    for k, filt in enumerate(filters):
        for t in range(n_ep):
            frame, cam = f"{filt}{t:04d}", cams[t % len(cams)]
            zp = -23.5 + rng.normal(0, 0.1)
            qc.append(dict(frame=frame, data_id="T", filter=filt, mjd_mid=60000.0 + t, qc_pass=1,
                           tel="1m00" + cam[-1], camera=cam, airmass=1.2, fwhm_arcsec=2.0))
            mags = np.r_[g_true - 0.5 * k, 15.0 + 0.2 * np.sin(t / 5)] + zp + rng.normal(0, 0.005, n_stars + 1)
            for sid, m, agn in zip(np.r_[stars, -1], mags, np.r_[np.zeros(n_stars, bool), True]):
                meas.append(dict(frame=frame, star_id=int(sid), is_agn=bool(agn), mag_inst=m, magerr=0.005, x=1.0,
                                 y=1.0, sex_flags=0, sep_arcsec=0.1, used_in_zp=not agn))
    db = tmp_path / "phot.sqlite"
    store.write_frame_qc(db, qc)
    store.update_measurements(tmp_path / "measurements.parquet", pd.DataFrame(meas))
    return db


@pytest.mark.parametrize("per_season", [False, True])
@pytest.mark.parametrize("cams", [("fa05",), ("ep04",)])
def test_intercal_with_no_camera_fitted(tmp_path, cams, per_season):
    """B02: a target seen by one camera only (or by MuSCAT only) has no intercal fit; the ensemble task
    crashed with KeyError 'scope' after rewriting the light curve without mag_ic / F_ic."""
    from ava.config import cfg
    from ava.pipeline.tasks import ensemble as _  # noqa: F401  (registers the module)
    import sys
    T = sys.modules["ava.pipeline.tasks.ensemble"]

    db = _target_folder(tmp_path, cams=cams)
    E.run_target(tmp_path, db, "T", ["gp", "ip"], mode="auto", log=lambda *a: None)
    import copy
    ec = copy.copy(cfg.ensemble)
    ec.intercal_per_season = per_season
    out = T.intercal_lightcurve(tmp_path, ec)
    assert {"mag_ic", "F_ic", "Ferr_ic"} <= set(out.columns)
    assert np.allclose(out["F_ic"], out["F"])                       # nothing to correct
    tab = pd.read_csv(tmp_path / "pytics" / "intercal.csv")
    assert len(tab) == 0 and {"filter", "scope", "b1", "corrected"} <= set(tab.columns)
    merged = T.export_merged_csv(out, tmp_path / "T_LCO_merged_lightcurve.csv", "T")
    assert len(merged) > 0


def _fake_zp(zp, C, c0, n, zp_err=0.002, C_err=0.004):
    return dict(zp=zp, zp_err=zp_err, C=C, C_err=C_err, c0=c0, n=n)


def test_agn_zero_points_one_failed_filter_does_not_spoil_the_others(monkeypatch):
    """B12 / B4p: a filter whose absolute ZP failed (Y with 2 stars; or g / i) made the AGN colour NaN and
    with it the ZP of EVERY filter."""
    fits = {"gp": _fake_zp(23.9, 0.045, 0.8, 60), "ip": _fake_zp(23.3, 0.027, 0.8, 60),
            "rp": _fake_zp(23.7, 0.0, 0.8, 60), "Y": _fake_zp(np.nan, np.nan, 0.0, 0)}
    monkeypatch.setattr(E, "absolute_zp", lambda s, ref, **k: dict(fits[s]))
    agn = {"gp": np.array([-9.0, np.nan]), "ip": np.array([-9.6]), "rp": np.array([-9.3]), "Y": np.array([np.nan])}
    out, z = E.agn_zero_points({f: f for f in fits}, None, agn)
    assert all(np.isfinite(out[f][0]) for f in ("gp", "ip", "rp")) and np.isnan(out["Y"][0])
    c_agn = (-9.0 + 23.9) - (-9.6 + 23.3)                     # converges here (equal pivots)
    assert z["gp"]["agn_colour"] == pytest.approx(c_agn, abs=0.01)
    assert out["rp"][0] == 23.7                                # no colour term: the plain ZP
    # the colour band itself fails: the others fall back to the star colour, not NaN
    fits["ip"] = _fake_zp(np.nan, np.nan, 0.0, 0)
    out, z = E.agn_zero_points({f: f for f in fits}, None, agn)
    assert np.isfinite(out["gp"][0]) and np.isfinite(out["rp"][0]) and np.isnan(out["ip"][0])
    assert z["gp"]["agn_colour"] == pytest.approx(0.8)


def test_error_model_ignores_filter_without_zero_point():
    """B4p: NaN mag_ic (filter with a NaN absolute ZP) crashed fit_s_cam: brentq 'f(0) is NaN'."""
    from ava.photometry import errors as ER

    rng = np.random.default_rng(5)
    rows = []
    for f in ("gp", "Y"):
        for i in range(400):
            cam = ("fa05", "fa11")[i % 2]
            m = 15.0 + rng.normal(0, 0.01) if f == "gp" else np.nan
            rows.append(dict(Filter=f, scope=f"1m00{cam[-1]}-{cam}", camera=cam, MJD=60000 + i * 0.02, good=True,
                             magerr=0.005, rms_t=0.002, mag_ic=m))
    lc = pd.DataFrame(rows)
    tab = ER.fit_error_model(lc, mag="mag_ic", min_pairs=50, min_cross_pairs=10)
    assert "Y" not in set(tab["Filter"]) and np.isfinite(tab["s_cam"]).all()


def test_fit_s_cam_caps_instead_of_raising():
    from ava.photometry import errors as ER

    Pc = pd.DataFrame({"dm": np.random.default_rng(1).normal(0, 2.0, 200)})   # 2 mag scatter: no root below 0.5
    assert ER.fit_s_cam(Pc, np.full(200, 0.01), np.full(200, 0.01)) == 0.5
    assert ER.fit_s_cam(Pc.assign(dm=np.nan), np.full(200, 0.01), np.full(200, 0.01)) == 0.0
