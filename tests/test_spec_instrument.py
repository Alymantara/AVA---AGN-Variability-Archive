"""C06: the spectra archive search keeps FLOYDS frames only."""
from datetime import datetime

from ava.lco.download import Query


def _q(cameras):
    return Query(names=["Fairall9"], proposals=["KEY2026B-007"], start=datetime(2026, 9, 1),
                 end=datetime(2026, 11, 1), kind="spec", cameras=cameras)


def test_spec_keeps_floyds_only():
    q = _q(["en"])
    f = dict(filename="coj2m002-en12-20261003-0012-e00.fits.fz", configuration_type="SPECTRUM",
             instrument_id="en12", telescope_id="2m0a")
    assert q.keep(f)
    assert q.keep({**f, "configuration_type": "ARC"})
    assert not q.keep({**f, "instrument_id": "ghts_red", "telescope_id": "4m0a"})   # SOAR Goodman
    assert not q.keep({**f, "instrument_id": "nres01"})
    assert not q.keep({**f, "configuration_type": "EXPOSE"})


def test_spec_without_cameras_unchanged():
    assert _q(None).keep(dict(filename="x.fits.fz", configuration_type="SPECTRUM", instrument_id="ghts_red"))
