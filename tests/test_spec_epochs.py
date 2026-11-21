"""B49: a target never observed with FLOYDS (floyds_end NaN) must not crash the plots / ensemble task."""
import math

import pytest

import importlib

W = importlib.import_module("ava.pipeline.tasks.webplot")   # the package exports the task under the same name


@pytest.mark.parametrize("end, expected", [(float("nan"), None), ("nan", None), ("", None), (None, None),
                                           ("NaT", None), ("not a date", None), ("2024-03-23", 60392.0)])
def test_spectroscopy_epochs_floyds_end(monkeypatch, end, expected):
    import ava.lcodb.config as lc
    from ava.database import query

    def no_db(*a, **k):
        raise FileNotFoundError("spectra.sqlite")

    monkeypatch.setattr(lc, "load_config", no_db)                 # no spectra DB: fall back to floyds_end
    monkeypatch.setattr(query, "target", lambda t: {"floyds_end": end})
    mjds, last = W.spectroscopy_epochs("3C_445")
    assert mjds == []
    assert last == expected or (expected is None and last is None)
    assert last is None or not math.isnan(last)
