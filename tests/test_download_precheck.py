"""Photometry download: skip the archive search when the fresh lcodb DB lists nothing new
(ava.lco.download.lcodb_precheck), offline — synthetic lcodb photometry and state DBs."""
import sqlite3
from datetime import datetime

from ava.lco.download import Query, lcodb_precheck

NOW = datetime(2026, 11, 20, 2, 0, 0)
PROP = "KEY2026B-007"


def _dbs(tmp_path, synced="2026-11-20T01:05:00", frames=()):
    phot, state = tmp_path / "photometry.sqlite", tmp_path / "state.sqlite"
    con = sqlite3.connect(phot)
    con.execute("CREATE TABLE frames (id INTEGER PRIMARY KEY, basename TEXT, filename TEXT, extension TEXT, "
                "proposal_id TEXT, instrument_id TEXT, telescope_id TEXT, date_obs TEXT, day_obs TEXT, "
                "filter TEXT, obstype TEXT, rlevel INTEGER, object TEXT)")
    con.executemany("INSERT INTO frames VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", frames)
    con.commit(); con.close()
    con = sqlite3.connect(state)
    con.execute("CREATE TABLE sync_state (proposal_id TEXT PRIMARY KEY, synced_until TEXT)")
    if synced:
        con.execute("INSERT INTO sync_state VALUES (?,?)", (PROP, synced))
    con.commit(); con.close()
    return phot, state


def _frame(fid, obj="Mrk 817", filt="gp", day="2026-11-19", rlevel=91, prop=PROP):
    base = f"ogg2m001-ep04-{day.replace('-', '')}-{fid:04d}-e91"
    return (fid, base, base + ".fits.fz", None, prop, "ep04", "2m0a", f"{day}T06:00:00.000000Z", day,
            filt, "EXPOSE", rlevel, obj)


def _q(**kw):
    return Query(names=["Mrk 817", "Mrk817"], proposals=[PROP], start=datetime(2026, 11, 17, 2),
                 end=datetime(2026, 11, 21, 2), kind="phot", filters=["gp", "rp"], **kw)


def test_skip_when_nothing_new(tmp_path):
    phot, state = _dbs(tmp_path, frames=[_frame(1, obj="NGC 4151"),            # another target
                                         _frame(2, filt="R"),                    # filter not kept
                                         _frame(3, day="2026-11-10"),            # before the window
                                         _frame(4, prop="KEY2023B-001")])        # another proposal
    skip, why = lcodb_precheck(phot, state, _q(), tmp_path / "raw", now=NOW)
    assert skip, why


def test_search_when_new_frame(tmp_path):
    phot, state = _dbs(tmp_path, frames=[_frame(5), _frame(6, obj="Mrk817")])
    skip, why = lcodb_precheck(phot, state, _q(), tmp_path / "raw", now=NOW)
    assert not skip and "2 new" in why


def test_on_disk_or_processed_is_not_new(tmp_path):
    phot, state = _dbs(tmp_path, frames=[_frame(5), _frame(6)])
    f5 = tmp_path / "raw" / "20261119" / "ogg2m001-ep04-20261119-0005-e91.fits.fz"
    f5.parent.mkdir(parents=True); f5.write_bytes(b"x")
    done = lambda name: "-0006-" in name  # noqa: E731 — frame 6 has a catalogue
    skip, why = lcodb_precheck(phot, state, _q(), tmp_path / "raw", done=done, now=NOW)
    assert skip, why


def test_stale_or_missing_lcodb_means_search(tmp_path):
    phot, state = _dbs(tmp_path, synced="2026-11-18T01:05:00")
    skip, why = lcodb_precheck(phot, state, _q(), tmp_path / "raw", now=NOW, max_age_hours=24)
    assert not skip and "not synced" in why
    (tmp_path / "b").mkdir()
    phot2, state2 = _dbs(tmp_path / "b", synced=None)
    assert not lcodb_precheck(phot2, state2, _q(), tmp_path / "raw", now=NOW)[0]       # proposal never synced
    assert not lcodb_precheck(None, state, _q(), tmp_path / "raw", now=NOW)[0]         # no DB
    assert not lcodb_precheck(tmp_path / "nope.sqlite", state, _q(), tmp_path / "raw", now=NOW)[0]


def test_spectra_never_prechecked(tmp_path):
    phot, state = _dbs(tmp_path)
    q = Query(names=["Mrk 817"], proposals=[PROP], start=NOW, end=NOW, kind="spec")
    assert not lcodb_precheck(phot, state, q, tmp_path, now=NOW)[0]
