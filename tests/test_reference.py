"""Offline tests for ava.photometry.reference (no network): python -m pytest tests"""
import numpy as np
import pandas as pd
import pytest
from astropy.table import Table

from ava.photometry import reference as ref

# Real Fairall 9 field ids; none survives a float64 round trip (spacing 1024).
IDS = np.array([4716954640356211072, 4716954159319873024, 4909106117059866112], dtype="int64")
RA = np.array([21.039866, 21.170525, 20.757355])
DEC = np.array([-59.118843, -59.102258, -59.094516])


def gaia_table(ids=IDS, ra=RA, dec=DEC):
    return pd.DataFrame({"gaia_source_id": ids, "gaia_ra": ra, "gaia_dec": dec,
                         "gaia_g": [10.46, 15.74, 14.57], "gaia_parallax": [1.0, 2.0, 3.0]})


def test_float64_would_corrupt_these_ids():
    assert all(int(float(i)) != i for i in IDS)


def test_match_gaia_keeps_source_ids_exact():
    # Two matched stars (offset 0.36") and one with no Gaia source nearby.
    stars = pd.DataFrame({"ra": [RA[0], RA[2], 21.5], "dec": [DEC[0] + 1e-4, DEC[2], -59.0]})
    out = ref.match_gaia(stars, gaia_table(), max_sep_arcsec=1.5)
    assert str(out["gaia_source_id"].dtype) == "Int64"
    assert out["gaia_source_id"].iloc[0] == IDS[0]
    assert out["gaia_source_id"].iloc[1] == IDS[2]
    assert pd.isna(out["gaia_source_id"].iloc[2])
    assert out["gaia_g"].iloc[0] == pytest.approx(10.46)
    assert np.isnan(out["gaia_g"].iloc[2])


def test_match_gaia_to_star_id_end_to_end():
    stars = pd.DataFrame({"ra": RA, "dec": DEC})
    m = ref.match_gaia(stars, gaia_table(), max_sep_arcsec=1.5)
    cat, _ = ref.assign_star_ids(m, RA[1], DEC[1], IDS, RA, DEC, log=lambda *_: None)
    assert cat["star_id"].dtype == np.int64
    assert sorted(cat["star_id"]) == sorted(IDS.tolist())
    assert cat.loc[cat["is_agn"], "star_id"].item() == IDS[1]


def test_match_gaia_empty_gaia():
    stars = pd.DataFrame({"ra": RA, "dec": DEC})
    out = ref.match_gaia(stars, gaia_table().iloc[:0], max_sep_arcsec=1.5)
    assert out["gaia_source_id"].isna().all()


@pytest.mark.parametrize("server", ["vizier.cfa.harvard.edu", "vizier.cds.unistra.fr"])
def test_vizier_uses_https(server):
    # http:// POSTs to mirrors that redirect to https came back empty.
    assert ref._vizier(server)._server_to_url("votable") == f"https://{server}/viz-bin/votable"
    assert ref._vizier(server)._server_to_url("asu-tsv").startswith("https://")


def apass_dr9(sloan_sep):
    t = {"RAJ2000": [20.9, 21.0], "DEJ2000": [-58.8, -58.7],
         "e_RAJ2000": [0.2, 0.3], "e_DEJ2000": [0.2, 0.3], "nobs": [5, 6],
         "Vmag": [14.0, 15.0], "e_Vmag": [0.02, 0.03], "Bmag": [14.6, 15.7], "e_Bmag": [0.03, 0.0]}
    for b, m in zip("gri", (14.3, 13.8, 13.6)):
        t[f"{b}{sloan_sep}mag"] = [m, m + 1]
        t[f"e_{b}{sloan_sep}mag"] = [0.02, 0.04]
    return Table(t)


@pytest.mark.parametrize("sep", ["'", "_"])
def test_clean_apass_dr9_column_names(sep):
    df = ref.clean_apass_dr9_vizier(apass_dr9(sep))
    row = df.sort_values("dec").iloc[0]
    assert row["apass_g"] == pytest.approx(14.3)
    assert row["apass_i_err"] == pytest.approx(0.02)
    assert np.isnan(df["apass_u"]).all()
    # error 0 -> missing (APASS convention)
    assert np.isnan(df.sort_values("dec")["apass_B"].iloc[1])


@pytest.mark.parametrize("feh_col", ["[Fe/H]", "__Fe_H_"])
def test_fetch_gaia_metallicity_column(monkeypatch, feh_col):
    src = Table({"Source": IDS, "RA_ICRS": RA, "DE_ICRS": DEC, "Gmag": [10.5, 15.7, 14.6],
                 "BP-RP": [0.8, 1.2, 0.9], "Plx": [1.0, 2.0, 3.0], "e_Plx": [0.1, 0.1, 0.1],
                 "RUWE": [1.0, 1.1, 1.2]})
    par = Table({"Source": IDS, "Teff": [5800.0, 4500.0, 6500.0], "logg": [4.4, 4.6, 4.2],
                 feh_col: [0.0, -0.5, 0.1], "Dist": [1000.0, 500.0, 330.0]})

    def fake_query(server, coord, radius, catalog, columns=("**",), accept=None):
        if catalog == "I/355/gaiadr3":
            return src, server
        if catalog == "I/355/paramp":
            return par, server
        raise RuntimeError("not in this test")   # GSPC -> columns filled with NaN

    monkeypatch.setattr(ref, "vizier_query", fake_query)
    g = ref.fetch_gaia(20.9, -58.8, 1.0, "vizier.example")
    assert g["gaia_source_id"].tolist() == IDS.tolist()
    assert g["gaia_mh"].tolist() == [0.0, -0.5, 0.1]
    assert g["gaia_teff"].iloc[1] == 4500.0
    assert g["gspc_u_sdss"].isna().all()
