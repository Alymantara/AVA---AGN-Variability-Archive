"""Offline tests for tools/port_legacy.py (legacy catalogues / FLOYDS frames -> new layout, placed by frame name
through the lcodb databases) and for the archive-listing frame metadata used for catalogues without images."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import port_legacy as PL  # noqa: E402

from ava.photometry.store import listing_meta  # noqa: E402


def _db(path, rows, cols):
    with sqlite3.connect(path) as con:
        con.execute(f"CREATE TABLE frames ({', '.join(cols)})")
        con.executemany(f"INSERT INTO frames VALUES ({','.join('?' * len(cols))})", rows)
    return path


def _touch(p, n=5):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * n)
    return p


@pytest.fixture
def new_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(PL.cfg.__class__, "sextractor_dir", lambda self, d: tmp_path / "new/photometry" / d / "sextractor_ava")
    monkeypatch.setattr(PL.cfg.__class__, "spec_raw", lambda self, d: tmp_path / "new/spectroscopy/raw_data" / d)
    return tmp_path / "new"


def test_photometry_placed_by_frame_name_not_folder(tmp_path, new_layout):
    old = tmp_path / "data3/agn"
    a = "lsc1m005-fa15-20250101-0001-e91"
    b = "lsc1m005-fa15-20250101-0002-e91"
    c = "ogg2m001-en06-20250101-0003-w91"
    d = "coj1m011-fa12-20250101-0004-e91"
    for f in (a, b, c, d):
        _touch(old / "1H1934-063" / "sextractor_ava" / f"{f}_cat.fits")           # old folder name
    db = _db(tmp_path / "phot.sqlite", [(a, "1H_1934-063"), (b, None)], ["basename", "ava_data_id"])
    jobs, probs, _ = PL.plan_photo(old, db, ("fa", "fl", "fs", "ep"))
    assert [(j[1].relative_to(new_layout).as_posix(), j[2]) for j in jobs] == [
        (f"photometry/1H_1934-063/sextractor_ava/{a}_cat.fits", "1H_1934-063")]
    assert sorted(w for _, w in probs) == ["frame not in the photometry database", "frame not linked to an AVA target",
                                          "not an imaging camera"]
    out = PL.run("phot", jobs, probs, {}, write=True, link=False, workers=2)
    assert out == {"copied": 1} and jobs[0][1].exists()
    assert PL.run("phot", jobs, probs, {}, write=True, link=False, workers=2) == {"exists": 1}   # idempotent
    assert (old / "1H1934-063/sextractor_ava" / f"{a}_cat.fits").exists()                     # source untouched


def test_spectra_target_and_standards(tmp_path, new_layout):
    old = tmp_path / "data2/agn"
    sci, arc, std, unk = ("ogg2m001-en06-20250102-0005-e00", "ogg2m001-en06-20250102-0006-a00",
                          "ogg2m001-en06-20250102-0009-e00", "ogg2m001-en06-20250102-0010-w00")
    for f in (sci, arc):
        _touch(old / "raw_data/Mrk817_spec/all_spec/20250102" / f"{f}.fits.fz")
        _touch(old / "raw_data/Mrk817_spec/20250102_1" / f"{f}.fits.fz")                    # sorted copy (dup)
    _touch(old / "all_standards/20250102" / f"{std}.fits.fz")
    _touch(old / "all_standards/20250102" / f"{unk}.fits.fz")
    _touch(old / "raw_data/Mrk817_spec/all_spec/20250102/KEY_old.tar.gz")
    db = _db(tmp_path / "spec.sqlite",
             [(sci, "Mrk_817", 0, "2025-01-01", 0), (arc, "Mrk_817", 0, "2025-01-01", 0), (std, None, 1, "2025-01-01", 0)],
             ["basename", "ava_data_id", "is_standard", "day_obs", "rlevel"])
    jobs, probs, tars = PL.plan_spec(old, db)
    got = sorted(j[1].relative_to(new_layout).as_posix() for j in jobs)
    # the night folder comes from the database's day_obs (20250101), not the file name
    assert got == sorted([f"spectroscopy/raw_data/Mrk_817/20250101/{arc}.fits.fz",
                          f"spectroscopy/raw_data/Mrk_817/20250101/{sci}.fits.fz",
                          f"spectroscopy/raw_data/standards/20250101/{std}.fits.fz"])
    assert [w for _, w in probs] == ["frame not in the spectra database"] and sum(tars.values()) == 1


def test_listing_meta_for_catalogues_without_images(tmp_path):
    cols = ["basename", "filter", "exptime", "mjd_obs", "day_obs", "site_id", "airmass", "airmass_calc", "l1fwhm",
            "instrument_id", "ava_data_id", "rlevel"]
    db = _db(tmp_path / "phot.sqlite",
             [("tfn1m001-fa20-20260820-0081-e91", "up", 120.0, 61272.88, "2026-08-20", "tfn", None, 1.43, None,
               "fa20", "Mrk_817", 91),
              ("tfn0m414-ep02-20260820-0001-e91", "gp", 60.0, 61272.9, "2026-08-20", "tfn", None, 1.2, None,
               "ep02", "Mrk_817", 91)], cols)
    m = listing_meta(db, "Mrk_817", {"fa": {"saturate": 128000, "naxis1": 4096, "naxis2": 4096}})
    fa = m["tfn1m001-fa20-20260820-0081-e91"]
    assert fa["mjd_mid"] == pytest.approx(61272.88 + 60 / 86400) and fa["day_obs"] == "20260820"
    assert (fa["filter"], fa["airmass"], fa["saturate"], fa["naxis1"], fa["site"]) == ("up", 1.43, 128000, 4096, "tfn")
    ep = m["tfn0m414-ep02-20260820-0001-e91"]
    assert ep["saturate"] is None and ep["naxis1"] is None      # no camera default: SExtractor FLAGS only
