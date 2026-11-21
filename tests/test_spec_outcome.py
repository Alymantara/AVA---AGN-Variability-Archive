"""B48 / B51: no-object spectra and the outcome rules of a reduction run (offline)."""
import sqlite3

import numpy as np
import pytest
from astropy.io import fits

from ava.spectroscopy import reduce as R

BASE = "coj2m002-en12-20240323-0012-e00"


def test_no_object_frames_from_the_chain_log(tmp_path):
    log = tmp_path / "chain.log"
    log.write_text("old line No object was detected ogg2m001-en06-20140801-0001-e91\n"
                   "coj2m002-en12-20240323-0011-e00.fits.fz ok 30s\n"
                   f"WARNING: No object was detected in the slit, so no profile was fit. | "
                   f"{{'filename': '{BASE.replace('-e00', '-e91')}.fits.fz'}}\n"
                   "WARNING: some other warning coj2m002-en12-20240323-0013-e91.fits.fz\n")
    assert R.no_object_frames(log, since=1) == {BASE}            # earlier runs' lines ignored; others don't qualify


def test_two_d_says_no_object(tmp_path):
    f = tmp_path / "x-2d.fits"
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.zeros((2, 2)), fits.Header({"L1OBJDET": False}),
                                                   name="SCI")]).writeto(f)
    assert R.two_d_says_no_object(f) and not R.two_d_says_no_object(None)
    assert not R.two_d_says_no_object(tmp_path / "missing.fits")


def test_outcome_rules(tmp_path):
    log = tmp_path / "x.log"
    assert R.outcome(10, 3, False, 0, log) == "complete"
    assert R.outcome(10, 2, True, 0, log) == "partial"           # products go on from whatever reduced
    with pytest.raises(RuntimeError, match="no frames"):
        R.outcome(0, 0, False, 0, log)                           # exit 0 with nothing done is not a success
    with pytest.raises(RuntimeError, match="no science product"):
        R.outcome(5, 0, True, 0, log)


def test_noobject_rows_and_reprocess_table(tmp_path):
    db = tmp_path / "spectra.sqlite"
    row = R.no_object_row(BASE, "science", "ESO_511-30", "20240323", None, "2026-11-21T10:00:00+00:00", "v", 7)
    R.write_qc(db, [row])
    assert R.no_object_basenames(db, "ESO_511-30") == {BASE} and R.no_object_basenames(db, "other") == set()
    con = sqlite3.connect(db)
    assert con.execute("SELECT path_1d, L1QFLAGS, L1OBJDET FROM spec_qc").fetchone() == (None, "NOOBJECT", 0)

    f = dict(basename="b1", data_id="T", day_obs="2024-03-23", reason="no product")
    R.record_reprocess(db, [f], "t1")
    R.record_reprocess(db, [f], "t2")                            # a second run that left it: runs = 2
    rows = R.open_reprocess(db)
    assert [(r["basename"], r["runs"], r["first_utc"], r["last_utc"]) for r in rows] == [("b1", 2, "t1", "t2")]
    assert R.resolve_reprocess(db, ["b1"], "t3") == 1 and R.open_reprocess(db) == []
    R.record_reprocess(db, [f], "t4")                            # fails again later: reopened
    assert len(R.open_reprocess(db)) == 1


def test_pending_nights_skips_noobject(tmp_path):
    from ava.pipeline.tasks.spec_reduce import pending_nights

    raw, red = tmp_path / "raw", tmp_path / "reduced"
    (raw / "20240323").mkdir(parents=True)
    (raw / "20240323" / f"{BASE}.fits.fz").write_bytes(b"x")
    assert pending_nights(raw, red) == ["20240323"]
    assert pending_nights(raw, red, skip={BASE}) == []           # not re-reduced every daily run


def test_daily_report_flags_reprocess_and_noobject(tmp_path, capsys):
    import sys
    from datetime import datetime, timezone
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import daily_check

    db = tmp_path / "spectra.sqlite"
    rep = daily_check.Report()
    daily_check.check_spectra_flags(rep, db)                      # no DB: nothing reported
    assert rep.warn == 0 and rep.items == []

    R.write_qc(db, [R.no_object_row(BASE, "science", "ESO_511-30", "20240323", None,
                                    "2026-11-21T10:00:00+00:00", "v", 7)])
    R.record_reprocess(db, [dict(basename="b1", data_id="Mrk_352", day_obs="2014-08-01", reason="no product")],
                       "2026-11-21T10:00:00+00:00")
    rep = daily_check.Report()
    daily_check.check_spectra_flags(rep, db, now=datetime(2026, 11, 22, tzinfo=timezone.utc))
    out = capsys.readouterr().out
    assert rep.warn == 2 and rep.fail == 0
    assert "Mrk_352 (20140801)" in out and BASE in out and "NOOBJECT" in out
    assert {i["check"] for i in rep.items} == {"Spectra to reprocess", "Spectra with no object in the slit"}
