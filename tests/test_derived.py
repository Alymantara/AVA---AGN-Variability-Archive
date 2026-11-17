"""Offline tests for ava.database.derived (k_bol, L_bol, Eddington ratio, disc lags)."""

import math
import sqlite3
from contextlib import closing

import pandas as pd
import pytest

from ava.database.derived import DerivedSettings, derive, disc_lag_days, kbol_5100, update_derived

WL = {"u": 3500.0, "g": 4770.0, "z": 8700.0}
S = DerivedSettings()


def test_kbol_netzer():
    assert kbol_5100(42.0, S) == pytest.approx(40.0)
    assert kbol_5100(43.78, S) == pytest.approx(17.62, abs=0.01)          # Mrk 817 (legacy logl_comment)


def test_lag_scaling():
    base = disc_lag_days(8.0, 0.1, WL["g"], WL["u"], 0.0, S)
    assert base > 0
    # tau ∝ (M Mdot)^(1/3), Mdot ∝ M mdot  →  tau ∝ M^(2/3) mdot^(1/3)
    assert disc_lag_days(9.0, 0.1, WL["g"], WL["u"], 0.0, S) / base == pytest.approx(10 ** (2 / 3))
    assert disc_lag_days(8.0, 0.8, WL["g"], WL["u"], 0.0, S) / base == pytest.approx(2.0)
    # tau ∝ X^(4/3)
    s2 = DerivedSettings(disc_X=2 * S.disc_X)
    assert disc_lag_days(8.0, 0.1, WL["g"], WL["u"], 0.0, s2) / base == pytest.approx(2 ** (4 / 3))
    # observed frame: rest wavelengths λ/(1+z) and ×(1+z) → (1+z)^(-1/3)
    assert disc_lag_days(8.0, 0.1, WL["g"], WL["u"], 1.0, S) / base == pytest.approx(2 ** (-1 / 3))


def test_lag_value_hand_computed():
    # Independent evaluation of Fausnaugh+16 eq. 2 for log M = 8, mdot = 0.1, g vs u, z = 0.
    G, c, h, k, sig, msun = 6.674e-8, 2.99792458e10, 6.62607e-27, 1.380649e-16, 5.670374e-5, 1.98847e33
    M = 1e8 * msun
    ledd = 1.26e38 * 1e8
    core = ((G * M / (8 * math.pi * sig)) * (ledd / (0.1 * c ** 2)) * (3 + 1) * 0.1) ** (1 / 3)
    tau = lambda lam: (4.97 * k * lam * 1e-8 / (h * c)) ** (4 / 3) * core / c / 86400  # noqa: E731
    assert disc_lag_days(8.0, 0.1, WL["g"], WL["u"], 0.0, S) == pytest.approx(tau(4770) - tau(3500), rel=1e-6)


def test_derive_sources_and_missing():
    agn = pd.DataFrame([
        {"data_id": "A", "logm": 7.6, "l_5100": 43.78, "logl": 45.0, "redshift": 0.031},
        {"data_id": "B", "logm": 8.0, "l_5100": None, "logl": 45.5, "redshift": 0.1},
        {"data_id": "C", "logm": None, "l_5100": 44.0, "logl": None, "redshift": 0.2},
        {"data_id": "D", "logm": 7.0, "l_5100": 0.0, "logl": -1, "redshift": 0.05},
    ])
    d = derive(agn, WL, S).set_index("data_id")
    assert d.loc["A", "lbol_source"] == "l_5100"
    assert d.loc["A", "log_lbol"] == pytest.approx(43.78 + math.log10(kbol_5100(43.78, S)))
    assert d.loc["B", "lbol_source"] == "logl" and d.loc["B", "log_lbol"] == 45.5
    assert d.loc["A", "lag_ug_days"] > 0 and d.loc["A", "lag_gz_days"] > d.loc["A", "lag_ug_days"]
    assert pd.isna(d.loc["C", "lag_ug_days"])                       # no mass
    assert pd.isna(d.loc["D", "log_lbol"]) and pd.isna(d.loc["D", "lag_gz_days"])


def test_update_writes_table_not_agn(tmp_path):
    db = tmp_path / "ava.db"
    with closing(sqlite3.connect(db)) as c:
        c.execute("CREATE TABLE agn (id INTEGER PRIMARY KEY, data_id TEXT, logm, l_5100, logl, redshift, ledd)")
        c.execute("INSERT INTO agn (data_id, logm, l_5100, logl, redshift, ledd) VALUES ('Mrk_817', 7.6, 43.78, 45.026, 0.031, 0.205)")
        c.commit()
    update_derived(db, WL, S)
    update_derived(db, WL, S)                                         # idempotent
    with closing(sqlite3.connect(db)) as c:
        assert c.execute("SELECT COUNT(*) FROM agn_derived").fetchone()[0] == 1
        assert c.execute("SELECT logl, ledd FROM agn").fetchone() == (45.026, 0.205)   # curated: untouched
        lag = c.execute("SELECT lag_ug_days FROM agn_derived").fetchone()[0]
        assert 0.1 < lag < 1.0
    # a new lag pair adds its column
    update_derived(db, WL, DerivedSettings(lag_pairs=[["u", "z"]]))
    with closing(sqlite3.connect(db)) as c:
        assert c.execute("SELECT lag_uz_days FROM agn_derived").fetchone()[0] > lag
