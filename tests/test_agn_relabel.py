"""B14: when the AGN's Gaia source is not in the reference catalogue, any catalogue row within 2" was given the
AGN's id and marked as the AGN, so a real GSPC neighbour (with its own Gaia id) became the AGN and disappeared.
Only a row WITHOUT a Gaia id (APASS) may be taken as the nucleus.  Offline."""
import numpy as np
import pandas as pd

from ava.photometry import reference as ref

AGN_ID, STAR_ID = 4909106117059866112, 4716954640356211072
RA0, DEC0 = 20.940742, -58.805775                  # Fairall 9


def _cat(star_id):
    d = 1.8 / 3600                                   # a row 1.8" north of the nucleus
    return pd.DataFrame({"gaia_source_id": pd.array([star_id, 4716954159319873024], dtype="Int64"),
                         "ra": [RA0, RA0 + 0.01], "dec": [DEC0 + d, DEC0 + 0.01], "lco_g": [17.2, 15.0],
                         "quality_ok": [True, True]})


def test_gspc_neighbour_is_not_relabelled_as_the_agn():
    gaia_ids, gaia_ra, gaia_dec = np.array([AGN_ID, STAR_ID]), np.array([RA0, RA0]), np.array([DEC0, DEC0 + 1.8 / 3600])
    cat, _ = ref.assign_star_ids(_cat(STAR_ID), RA0, DEC0, gaia_ids, gaia_ra, gaia_dec, log=lambda *_: None)
    agn = cat[cat["is_agn"]].iloc[0]
    assert agn["star_id"] == AGN_ID and agn["ra"] == RA0 and agn["dec"] == DEC0     # added at the Gaia nucleus
    assert STAR_ID in set(cat["star_id"])                                          # the neighbour is kept
    assert not cat.loc[cat["star_id"] == STAR_ID, "is_agn"].item()


def test_apass_row_at_the_nucleus_is_still_taken_as_the_agn():
    gaia_ids, gaia_ra, gaia_dec = np.array([AGN_ID]), np.array([RA0]), np.array([DEC0])
    cat, _ = ref.assign_star_ids(_cat(pd.NA), RA0, DEC0, gaia_ids, gaia_ra, gaia_dec, log=lambda *_: None)
    agn = cat[cat["is_agn"]].iloc[0]
    assert agn["star_id"] == AGN_ID and agn["lco_g"] == 17.2                        # the APASS row, relabelled
