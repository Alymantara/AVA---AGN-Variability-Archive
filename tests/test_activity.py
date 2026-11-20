"""Offline tests for ava.database.activity (observing flag agn.ava)."""

import sqlite3
from contextlib import closing
from datetime import date

from ava.database.activity import last_frames, new_flag, update_observing

TODAY = date(2026, 11, 16)          # cutoff (30 d) = 2026-10-17


def test_new_flag_rules():
    cut = "2026-10-17"
    assert new_flag(1, "2026-11-10", cut) == 2      # archived, observed again
    assert new_flag(0, "2026-10-17", cut) == 2      # inclusive cutoff
    assert new_flag(2, "2026-09-20", cut) == 0      # stopped: to be processed
    assert new_flag(1, "2025-01-01", cut) == 1      # archived stays archived
    assert new_flag(None, None, cut) is None        # no frames: untouched
    assert new_flag(None, "2026-09-13", cut) == 0   # old data, no status yet: to be processed
    assert new_flag(None, "2026-11-01", cut) == 2   # new data, no status yet: observing


def _frames(path, rows):
    with closing(sqlite3.connect(path)) as c:
        c.execute("CREATE TABLE frames (ava_id INTEGER, obstype TEXT, day_obs TEXT)")
        c.executemany("INSERT INTO frames VALUES (?,?,?)", rows)
        c.commit()


def test_last_frames_science_only(tmp_path):
    ph, sp = tmp_path / "p.sqlite", tmp_path / "s.sqlite"
    _frames(ph, [(1, "EXPOSE", "2026-09-01"), (1, "BIAS", "2026-11-15"), (None, "EXPOSE", "2026-11-15")])
    _frames(sp, [(1, "SPECTRUM", "2026-11-01"), (2, "ARC", "2026-11-15"), (3, "SPECTRUM", "2026-08-01")])
    assert last_frames([("photometry", ph), ("spectra", sp), ("spectra", None)]) == {1: "2026-11-01", 3: "2026-08-01"}


def test_update_observing(tmp_path):
    db = tmp_path / "ava.db"
    with closing(sqlite3.connect(db)) as c:
        c.execute("CREATE TABLE agn (id INTEGER PRIMARY KEY, data_id TEXT, ava INTEGER)")
        c.executemany("INSERT INTO agn VALUES (?,?,?)", [(1, "A", 1), (2, "B", 2), (3, "C", None), (4, "D", 2),
                                                        (5, "E", None)])
        c.commit()
    last = {1: "2026-11-14", 2: "2026-09-01", 4: "2026-11-01", 5: "2026-09-13"}
    assert update_observing(db, last, today=TODAY, dry_run=True) == [
        ("A", 1, 2, "2026-11-14"), ("B", 2, 0, "2026-09-01"), ("E", None, 0, "2026-09-13")]
    update_observing(db, last, today=TODAY)
    assert update_observing(db, last, today=TODAY) == []                     # idempotent
    with closing(sqlite3.connect(db)) as c:
        assert dict(c.execute("SELECT data_id, ava FROM agn")) == {"A": 2, "B": 0, "C": None, "D": 2, "E": 0}


# --- recent cadence (observing_recent) -------------------------------------------------------------------------

from ava.database.activity import cadence, recent_nights, update_recent_cadence  # noqa: E402


def test_cadence_windows():
    today = date(2026, 11, 19)                       # 30 d -> 2026-10-20, 60 d -> 2026-09-20
    assert cadence(["2026-11-01", "2026-11-03", "2026-11-07"], today) == (3, 3.0, 30)
    assert cadence(["2026-10-20", "2026-11-19"], today) == (2, 30.0, 30)            # both window edges inclusive
    # one night in 30 d: fall back to 60 d
    assert cadence(["2026-09-25", "2026-10-05", "2026-11-14"], today) == (3, 25.0, 60)
    assert cadence(["2026-11-14"], today) == (1, None, 60)                           # a single visit
    assert cadence(["2026-08-01"], today) == (0, None, 60)                           # nothing recent
    assert cadence([], today) == (0, None, 60)


def test_recent_nights_distinct_science(tmp_path):
    ph, sp = tmp_path / "p.sqlite", tmp_path / "s.sqlite"
    _frames(ph, [(1, "EXPOSE", "2026-11-10"), (1, "EXPOSE", "2026-11-10"), (1, "EXPOSE", "2026-11-12"),
                 (1, "BIAS", "2026-11-13"), (1, "EXPOSE", "2026-08-01")])
    _frames(sp, [(1, "SPECTRUM", "2026-11-11"), (2, "SPECTRUM", "2026-11-01")])
    assert recent_nights([("photometry", ph), ("spectra", sp)], "2026-09-20") == {
        1: {"photometry": ["2026-11-10", "2026-11-12"], "spectra": ["2026-11-11"]}, 2: {"spectra": ["2026-11-01"]}}


def test_update_recent_cadence(tmp_path):
    db = tmp_path / "ava.db"
    with closing(sqlite3.connect(db)) as c:
        c.execute("CREATE TABLE agn (id INTEGER PRIMARY KEY, data_id TEXT, ava INTEGER)")
        c.executemany("INSERT INTO agn VALUES (?,?,?)", [(1, "A", 2), (2, "B", 2)])
        c.commit()
    nights = {1: {"photometry": ["2026-11-10", "2026-11-12"], "spectra": ["2026-11-11"]}, 9: {"photometry": ["2026-11-01"]}}
    today = date(2026, 11, 19)
    assert update_recent_cadence(db, nights, today=today, dry_run=True)[0][:9] == \
        ("A", 2, 2.0, 30, "2026-11-12", 1, None, 60, "2026-11-11")                  # unknown ava_id 9 skipped
    assert not sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE name='observing_recent'").fetchone()
    update_recent_cadence(db, nights, today=today)
    update_recent_cadence(db, nights, today=today)                                     # rebuilt, not appended
    with closing(sqlite3.connect(db)) as c:
        assert c.execute("SELECT data_id, phot_nights, phot_cadence, spec_nights FROM observing_recent").fetchall() == \
            [("A", 2, 2.0, 1)]
