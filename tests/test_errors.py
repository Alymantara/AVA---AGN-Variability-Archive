"""Empirical AGN error model (ava.photometry.errors) on synthetic light curves."""
import numpy as np
import pandas as pd

from ava.photometry import errors as ER


def _lc(k=1.0, beta=0.25, s0=0.002, s_cam=0.006, n_nights=400, seed=1):
    """two Sinistro cameras, 2 back-to-back epochs per visit; true σ = model(k, β, s0) ⊕ camera-night term."""
    rng = np.random.default_rng(seed)
    rows = []
    for n in range(n_nights):
        truth = 15 + 0.2 * np.sin(n / 30)
        for cam, t0 in (("fa05", 0.10), ("fa07", 0.20)):
            off = rng.normal(0, s_cam)                       # this camera, this night
            for j in range(2):
                p = np.exp(rng.uniform(np.log(0.001), np.log(0.03))); rt = rng.uniform(0.0, 0.012)
                sig = np.sqrt((k * p) ** 2 + (beta * rt) ** 2 + s0 ** 2)
                rows.append(dict(Filter="gp", camera=cam, scope=f"1m00{5 if cam == 'fa05' else 6}-{cam}",
                                 MJD=n + t0 + j * 0.003, magerr=p, rms_t=rt, good=True,
                                 mag=truth + off + rng.normal(0, sig)))
    return pd.DataFrame(rows)


def test_recovers_error_scale():
    """k, β and s0 are partly degenerate (800 pairs: β ± 0.3), so test what is used: the
    predicted σ against the true σ, flat over the error range, and the camera term."""
    for seed in (1, 2, 3):
        lc = _lc(seed=seed)
        t = ER.fit_error_model(lc, min_pairs=100)
        row = t.set_index(["Filter", "family"]).loc[("gp", "fa")]
        assert row.source == "fit" and abs(row.s_cam - 0.006) < 0.0015
        pred = ER.sigma_rand(lc, t)
        true = np.sqrt(lc.magerr ** 2 + (0.25 * lc.rms_t) ** 2 + 0.002 ** 2)
        r = pd.Series(pred / true)
        assert abs(r.median() - 1) < 0.1
        assert (r.groupby(pd.qcut(true, 4)).median().sub(1).abs() < 0.25).all()


def test_scale_fallback_and_default_keep_the_floor():
    """19 Nov 2026: the fallbacks use the default model (with the floor), not the PyTICS form (no floor)."""
    lc = _lc(n_nights=60)
    lc["magerr"] = 0.003; lc["rms_t"] = 0.001                # no dynamic range -> scale only
    t = ER.fit_error_model(lc, min_pairs=50)
    d = ER.DEFAULT
    assert (t.source == "scale").all() and (t.s0 > 0).all()
    assert np.allclose(t.k / t.beta, d["k"] / d["beta"]) and np.allclose(t.k / t.s0, d["k"] / d["s0"])
    t = ER.fit_error_model(lc, min_pairs=10_000)             # too few pairs -> the default model
    assert (t.source == "default").all()
    assert np.allclose(t[["k", "beta", "s0"]].to_numpy(), [[d["k"], d["beta"], d["s0"]]])


def test_min_floor_and_missing_group_get_a_floor():
    lc = _lc(s0=0.0)                                         # data without a floor: the fit finds s0 ~ 0
    t = ER.fit_error_model(lc, min_pairs=100, min_floor=0.001)
    assert (t.s0 >= 0.001).all()
    bright = pd.DataFrame({"Filter": ["rp"], "camera": ["fa05"], "magerr": [0.0003], "rms_t": [0.0]})
    sig = ER.sigma_rand(bright, t)                            # rp not in the table -> DEFAULT
    assert sig[0] >= ER.DEFAULT["s0"]
