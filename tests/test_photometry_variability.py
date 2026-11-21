"""Offline tests for per-band F_var of the merged light curve (ava.photometry.variability)."""

import sqlite3
from contextlib import closing

import numpy as np
import pandas as pd
import pytest

from ava.photometry.variability import (band_variability, legacy_frac, recent_means, record_band_variability,
                                        record_recent)
from ava.utils.variability import variability


def _lc(seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    t = np.arange(200.0)
    signal = {"g": 0.10, "B": 0.0}            # g varies by 10 %, B is constant
    for band, amp in signal.items():
        true = 10.0 * (1 + amp * np.sin(t / 15.0) * np.sqrt(2))   # rms of sin·√2 = 1 → F_var ≈ amp
        err = np.full_like(t, 0.05)
        rows.append(pd.DataFrame({"filter": band, "MJD": 60000 + t, "flux_mJy": true + rng.normal(0, 0.05, t.size),
                                  "flux_err_mJy": err, "flux_err_random_mJy": err / 2}))
    rows.append(pd.DataFrame({"filter": "Y", "MJD": [1.0, 2.0], "flux_mJy": [1.0, 2.0],
                              "flux_err_mJy": [0.1, 0.1], "flux_err_random_mJy": [0.1, 0.1]}))
    return pd.concat(rows, ignore_index=True)


def test_variability_recovers_known_fvar():
    v = variability(*[np.r_[9, 11] .repeat(100), np.full(200, 1e-6)])
    assert v["fvar"] == pytest.approx(0.1, rel=0.01) and v["rmax"] == pytest.approx(11 / 9)


def test_band_variability_per_band():
    bv = band_variability(_lc()).set_index("filter")
    assert set(bv.index) == {"B", "g"}                      # Y: too few epochs
    assert bv.loc["g", "fvar"] == pytest.approx(0.10, abs=0.01)
    assert np.isnan(bv.loc["B", "fvar"])                    # scatter == errors → no excess variance
    assert bv.loc["g", "n_epochs"] == 200 and bv.loc["g", "mjd_first"] == 60000


def test_random_errors_give_larger_fvar():
    lc = _lc()
    tot = band_variability(lc, "total").set_index("filter")
    rnd = band_variability(lc, "random").set_index("filter")
    assert rnd.loc["B", "fvar"] > 0 and np.isnan(tot.loc["B", "fvar"])


def test_legacy_format():
    assert legacy_frac(0.10215) == "10.215%"
    assert legacy_frac(np.nan) == "0.0" and legacy_frac(None) == "0.0"


def test_record_writes_table_and_legacy_columns(tmp_path):
    db = tmp_path / "ava.db"
    with closing(sqlite3.connect(db)) as c:
        c.execute("CREATE TABLE agn (id INTEGER PRIMARY KEY, data_id TEXT, frac_B, frac_g, frac_u)")
        c.execute("INSERT INTO agn (data_id, frac_B, frac_g, frac_u) VALUES ('Mrk_817', '9.9%', 0.0, '7.0%')")
        c.execute("INSERT INTO agn (data_id) VALUES ('other')")
        c.commit()
    bv = band_variability(_lc())
    out = record_band_variability(db, "Mrk_817", bv, "pytics/total")
    assert out["g"] == pytest.approx(0.10, abs=0.01)
    with closing(sqlite3.connect(db)) as c:
        b, g, u = c.execute("SELECT frac_B, frac_g, frac_u FROM agn WHERE data_id='Mrk_817'").fetchone()
        assert b == "0.0" and g.endswith("%") and abs(float(g[:-1]) - 10) < 1
        assert u == "7.0%"                                 # band not measured: untouched
        assert c.execute("SELECT frac_g FROM agn WHERE data_id='other'").fetchone() == (None,)
        rows = c.execute("SELECT filter, n_epochs, error_model FROM photometry_variability ORDER BY filter").fetchall()
        assert rows == [("B", 200, "pytics/total"), ("g", 200, "pytics/total")]
    # Re-running replaces, never duplicates.
    record_band_variability(db, "Mrk_817", bv, "pytics/total")
    with closing(sqlite3.connect(db)) as c:
        assert c.execute("SELECT COUNT(*) FROM photometry_variability").fetchone()[0] == 2


def _mags(rows):
    return pd.DataFrame(rows, columns=["filter", "MJD", "mag_AB"])


def test_recent_means_last_observed_nights():
    # g: 12 nights, two epochs on the last night; the mean uses the last 10 nights only, in flux
    rows = [("g", 60000.0 + 3 * d, 15.0) for d in range(10)] + [("g", 60030.1, 14.0), ("g", 60030.2, 14.0),
                                                                ("g", 60033.3, 16.0)]
    rows += [("B", 60001.2, 15.5), ("B", 60001.3, np.nan)]          # one night, a NaN magnitude ignored
    rec = recent_means(_mags(rows), nights=10).set_index("filter")
    g = rec.loc["g"]
    assert g.n_nights == 10 and g.n_epochs == 11                    # nights 60006 … 60033: drops 60000 and 60003
    assert g.mjd_first == 60006.0 and g.mjd_last == 60033.3
    flux = np.r_[np.full(8, 10 ** -6.0), 2 * [10 ** -5.6], 10 ** -6.4]
    assert g.mag == pytest.approx(-2.5 * np.log10(flux.mean()))
    assert rec.loc["B", "n_nights"] == 1 and rec.loc["B", "mag"] == pytest.approx(15.5)


def test_record_recent_writes_table_and_avg_columns(tmp_path):
    db = tmp_path / "ava.db"
    with closing(sqlite3.connect(db)) as c:
        c.execute("CREATE TABLE agn (id INTEGER PRIMARY KEY, data_id TEXT, avg_g, avg_u)")
        c.execute("INSERT INTO agn (data_id, avg_g, avg_u) VALUES ('Mrk_817', 13.0, 17.0)")
        c.commit()
    rec = recent_means(_mags([("g", 60000.5, 14.2), ("Y", 60000.5, 15.0)]))
    record_recent(db, "Mrk_817", rec)
    record_recent(db, "Mrk_817", rec)                               # re-run replaces
    with closing(sqlite3.connect(db)) as c:
        assert c.execute("SELECT avg_g, avg_u FROM agn").fetchone() == (14.2, 17.0)   # u not measured: kept
        assert c.execute("SELECT filter, n_nights FROM photometry_recent ORDER BY filter").fetchall() == [
            ("Y", 1), ("g", 1)]


def test_recent_means_from_flux_when_no_magnitudes():
    rec = recent_means(pd.DataFrame({"filter": ["g", "g"], "MJD": [60000.1, 60001.1], "flux_mJy": [3.631, 3.631]}))
    assert rec.loc[0, "mag"] == pytest.approx(15.0) and rec.loc[0, "n_nights"] == 2
    assert recent_means(pd.DataFrame({"filter": ["g"], "MJD": [1.0]})).empty
