"""B18: SExtractor's 'newest first' sorted by file name, i.e. by site and telescope, not by date."""
from ava.pipeline.tasks.sextract import newest_first_key


def test_newest_first_is_by_date_not_site():
    names = ["lsc1m005-fa15-20250101-0001-e91.fits.fz", "coj1m003-fa19-20261110-0002-e91.fits.fz",
             "ogg2m001-ep04-20261110-0010-e91.fits.fz", "tfn1m001-fa20-20240505-0100-e91.fits.fz",
             "coj1m003-fa19-20261110-0001-e91.fits.fz"]
    got = sorted(names, key=newest_first_key, reverse=True)
    assert [n.split("-")[2] for n in got] == ["20261110", "20261110", "20261110", "20250101", "20240505"]
    assert got[0].startswith("ogg2m001-ep04-20261110-0010")       # same night: highest frame number first
    # the old key (name) put tfn and ogg before every lsc/coj frame regardless of date
    assert sorted(names, reverse=True)[0].startswith("tfn1m001")
