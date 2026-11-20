"""C11: a reference star with no Gaia RUWE is not a comparison star."""
import numpy as np
import pandas as pd

from ava.photometry.reference import read_reference


def test_read_reference_fails_nan_ruwe(tmp_path):
    p = tmp_path / "reference_stars.csv"
    pd.DataFrame({"star_id": [1, 2, 3, 4], "quality_ok": [True, True, False, True],
                  "gaia_ruwe": [1.0, np.nan, 1.0, 1.39]}).to_csv(p, index=False)
    ref = read_reference(p)
    assert ref["quality_ok"].tolist() == [True, False, False, True]
    assert ref["quality_ok"].dtype == bool

