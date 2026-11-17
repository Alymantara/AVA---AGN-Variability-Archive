"""Offline tests for the LCO time-usage plots (ava.lco.usage, scripts/lco_usage.py): semesters, the per-proposal
file reader, the dummy files and the plots."""
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ava.lco import usage as U

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
ALLOC = [
    dict(proposal="KEY2026B-007", semester="2026B", instrument="1M0-SCICAM-SINISTRO", used=450.6, alloc=954.0),
    dict(proposal="KEY2026B-007", semester="2026B", instrument="2M0-FLOYDS-SCICAM", used=104.7, alloc=156.0),
    dict(proposal="KEY2026B-007f", semester="2026B", instrument="2M0-FLOYDS-SCICAM", used=20.6, alloc=50.0),
    dict(proposal="KEY2023B-001", semester="2026A", instrument="1M0-SCICAM-SINISTRO", used=763.2, alloc=771.0),
    dict(proposal="KEY2023B-001", semester="2026A", instrument="2M0-SCICAM-MUSCAT", used=0.0, alloc=13.0),
]


def _cfg(tmp_path, **lco_usage):
    raw = {"lco_usage": {"input_dir": str(tmp_path / "in"), "allocations": str(tmp_path / "allocations.json"),
                         "plots_dir": str(tmp_path / "plots"), **lco_usage},
           "web": {"data_dir": str(tmp_path / "web")}}
    return SimpleNamespace(_raw=raw, _resolve=lambda p: tmp_path / p if not str(p).startswith("/") else
                           __import__("pathlib").Path(p))


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


# --- semesters ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("d,sem", [(date(2026, 11, 17), "2026B"), (date(2027, 1, 31), "2026B"),
                                   (date(2026, 2, 1), "2026A"), (date(2026, 7, 31), "2026A"),
                                   (date(2017, 6, 1), "2017AB"), (date(2018, 1, 15), "2017AB"),
                                   (date(2018, 2, 1), "2018A")])
def test_semester_of(d, sem):
    assert U.semester_of(d) == sem


def test_semester_bounds():
    a, b = U.semester_bounds("2026B")
    assert a == U.mjd_of(date(2026, 8, 1)) and b - a == 184
    a, b = U.semester_bounds("2024A")
    assert b - a == 182                       # the legacy plot's "182 days"
    assert U.semester_bounds("2017AB")[1] - U.semester_bounds("2017AB")[0] == 365
    assert U.mjd_of(date(2024, 10, 17)) == 60600.0
    with pytest.raises(ValueError):
        U.semester_bounds("2026C")


# --- reader -------------------------------------------------------------------------------------------------

def test_read_usage_file(tmp_path):
    p = _write(tmp_path / "KEY2026B-007.csv",
               "# dummy: false\n# note: test\nmjd, 1m0-scicam-sinistro ,2M0-FLOYDS-SCICAM\n"
               "61300.0,2.5,\n61301.0,0,1.25\n61300.0,0.5,0\n")
    u = U.read_usage_file(p)
    assert u.proposal == "KEY2026B-007" and not u.dummy and u.meta["note"] == "test"
    assert set(u.data["instrument"]) == {"1M0-SCICAM-SINISTRO", "2M0-FLOYDS-SCICAM"}
    assert u.data["hours"].sum() == pytest.approx(4.25)
    assert (u.data["hours"] > 0).all()        # zero / empty cells dropped


def test_read_usage_file_proposal_from_header(tmp_path):
    p = _write(tmp_path / "x.csv", "# proposal: KEY2026B-007f\n# dummy: true\nmjd,2M0-FLOYDS-SCICAM\n61300,1\n")
    u = U.read_usage_file(p)
    assert u.proposal == "KEY2026B-007f" and u.dummy


@pytest.mark.parametrize("body,msg", [
    ("date,1M0-SCICAM-SINISTRO\n61300,1\n", "first column"),
    ("mjd\n61300\n", "no instrument"),
    ("mjd,1M0-SCICAM-SINISTRO\n2461300.5,1\n", "outside"),
    ("mjd,1M0-SCICAM-SINISTRO\n61300,-1\n", "negative"),
    ("mjd,1M0-SCICAM-SINISTRO\n61300,abc\n", "non-numeric hours"),
    ("mjd,1M0-SCICAM-SINISTRO\n,1\n", "mjd"),
])
def test_read_usage_file_rejects(tmp_path, body, msg):
    p = _write(tmp_path / "KEY.csv", body)
    with pytest.raises(ValueError, match=msg):
        U.read_usage_file(p)


def test_write_read_roundtrip(tmp_path):
    wide = pd.DataFrame({"mjd": [61301.0, 61300.0], "2M0-SCICAM-MUSCAT": [0.0, 0.5],
                         "1M0-SCICAM-SINISTRO": [1.0, 2.0]})
    p = U.write_usage_file(tmp_path / "P.csv", "P", wide, {"dummy": "true"})
    u = U.read_usage_file(p)
    assert u.dummy and u.proposal == "P"
    assert u.data.groupby("instrument")["hours"].sum().to_dict() == {"1M0-SCICAM-SINISTRO": 3.0,
                                                                      "2M0-SCICAM-MUSCAT": 0.5}


# --- dummy files ----------------------------------------------------------------------------------------------

def test_make_dummy_matches_totals(tmp_path):
    alloc = pd.DataFrame(ALLOC)
    until = U.mjd_of(date(2026, 11, 16))
    files = U.make_dummy(alloc, tmp_path, until_mjd=until, seed=1)
    assert sorted(f.name for f in files) == ["KEY2023B-001.csv", "KEY2026B-007.csv", "KEY2026B-007f.csv"]
    usage, dummy = U.load_usage(tmp_path)
    assert dummy == {"KEY2023B-001", "KEY2026B-007", "KEY2026B-007f"}
    for r in ALLOC:
        a, b = U.semester_bounds(r["semester"])
        got = usage[(usage["proposal"] == r["proposal"]) & (usage["instrument"] == r["instrument"])
                    & (usage["mjd"] >= a) & (usage["mjd"] < b)]["hours"].sum()
        assert got == pytest.approx(r["used"], abs=1e-3)
    cur = usage[usage["proposal"] == "KEY2026B-007"]
    assert cur["mjd"].max() <= until and cur["mjd"].min() >= U.semester_bounds("2026B")[0]
    # deterministic
    U.make_dummy(alloc, tmp_path / "again", until_mjd=until, seed=1)
    assert (tmp_path / "again" / "KEY2026B-007.csv").read_text() == (tmp_path / "KEY2026B-007.csv").read_text()


# --- series and plots ---------------------------------------------------------------------------------------

def _usage():
    return pd.DataFrame({"proposal": ["KEY2026B-007", "KEY2026B-007", "KEY2026B-007f", "KEY2023B-001"],
                         "mjd": [61260.0, 61270.0, 61265.0, 61200.0],
                         "instrument": ["1M0-SCICAM-SINISTRO"] * 2 + ["2M0-FLOYDS-SCICAM", "1M0-SCICAM-SINISTRO"],
                         "hours": [10.0, 5.0, 2.0, 99.0]})


def test_semester_series():
    ser = U.semester_series(_usage(), pd.DataFrame(ALLOC), "2026B", now_mjd=U.mjd_of(NOW))
    by = {s.label: s for s in ser}
    assert set(by) == {"1m", "2m/Floyds", "2m/Floyds (filler)"}       # MuSCAT: no allocation, no use in 2026B
    assert by["1m"].used == 15.0 and by["1m"].alloc == 954.0     # 2026A row not counted
    assert by["2m/Floyds (filler)"].used == 2.0 and by["2m/Floyds"].used == 0.0
    assert by["1m"].mjd[0] == U.semester_bounds("2026B")[0] and by["1m"].mjd[-1] == pytest.approx(U.mjd_of(NOW))
    assert np.all(np.diff(by["1m"].cum) >= 0)


@pytest.mark.parametrize("style", U.STYLES)
def test_plot_semester_styles(tmp_path, style):
    ser = U.semester_series(_usage(), pd.DataFrame(ALLOC), "2026B", now_mjd=U.mjd_of(NOW))
    files = U.plot_semester(ser, "2026B", tmp_path / "lco_usage_2026B", now=NOW, dummy=True,
                            formats=("png",), style=style)
    assert files == [tmp_path / "lco_usage_2026B.png"] and files[0].stat().st_size > 10_000


def test_plot_semester_bad_style(tmp_path):
    with pytest.raises(ValueError):
        U.plot_semester([], "2026B", tmp_path / "x", now=NOW, style="nope")


def test_run_and_publish(tmp_path):
    (tmp_path / "allocations.json").write_text(json.dumps(ALLOC))
    _write(tmp_path / "in" / "KEY2026B-007.csv", "mjd,1M0-SCICAM-SINISTRO\n61260,10\n")
    _write(tmp_path / "in" / "KEY2023B-001.csv", "# dummy: true\nmjd,1M0-SCICAM-SINISTRO\n61200,99\n")
    cfg = _cfg(tmp_path)
    out = U.run(cfg, all_semesters=True, publish=True, now=NOW, log=lambda *_: None)
    assert out["semesters"] == ["2026A", "2026B"]
    assert (tmp_path / "plots" / "lco_usage_2026A.png").exists()
    # 2026B (real file) is published; 2026A (dummy) is not
    assert [p.name for p in out["published"]] == ["lco_usage_2026B.png"]
    assert (tmp_path / "web" / "usage" / "lco_usage_2026B.png").exists()
    # unchanged plot is not copied again; the default is the current semester
    again = U.run(cfg, publish=True, now=NOW, log=lambda *_: None)
    assert again["semesters"] == ["2026B"]
    out = U.run(cfg, semesters=["2026A"], publish=True, allow_dummy=True, now=NOW, log=lambda *_: None)
    assert [p.name for p in out["published"]] == ["lco_usage_2026A.png"]


def test_run_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        U.run(_cfg(tmp_path), now=NOW, log=lambda *_: None)


def test_run_publishes_by_default(tmp_path):
    """Every run copies the plot to the website (lco_usage.publish, default on); dummy plots only if
    lco_usage.publish_dummy."""
    (tmp_path / "allocations.json").write_text(json.dumps(ALLOC))
    _write(tmp_path / "in" / "KEY2026B-007.csv", "# dummy: true\nmjd,1M0-SCICAM-SINISTRO\n61260,10\n")
    out = U.run(_cfg(tmp_path), now=NOW, log=lambda *_: None)
    assert out["published"] == []                                  # dummy, publish_dummy off
    out = U.run(_cfg(tmp_path, publish_dummy=True), now=NOW, log=lambda *_: None)
    assert [p.name for p in out["published"]] == ["lco_usage_2026B.png"]
    out = U.run(_cfg(tmp_path, publish=False, publish_dummy=True), semesters=["2026A"], now=NOW,
                log=lambda *_: None)
    assert out["published"] == [] and not (tmp_path / "web" / "usage" / "lco_usage_2026A.png").exists()


# --- estimate from the lcodb databases --------------------------------------------------------------------------

def _lcodb(tmp_path):
    import sqlite3
    phot, spec = tmp_path / "photometry.sqlite", tmp_path / "spectra.sqlite"
    m = U.mjd_of(date(2026, 9, 1)) + 0.2
    with sqlite3.connect(phot) as con:
        con.execute("CREATE TABLE frames (proposal_id, exp_key, basename, camera_type, telescope_id, mjd_obs, "
                    "exptime, obstype, rlevel)")
        rows = [
            # one Sinistro exposure at two reduction levels: counted once
            ("KEY2026B-007", "lsc1m005-fa15-20260901-0001", "a-e91", "sinistro", "1m0a", m, 3600.0, "EXPOSE", 91),
            ("KEY2026B-007", "lsc1m005-fa15-20260901-0001", "a-e90", "sinistro", "1m0a", m, 3600.0, "EXPOSE", 90),
            ("KEY2026B-007", "lsc1m005-fa15-20260902-0002", "b-e91", "sinistro", "1m0a", m + 1, 3600.0, "EXPOSE", 91),
        ] + [  # four MuSCAT channels of one exposure: counted once
            ("KEY2026B-007", f"ogg2m001-ep0{c}-20260901-0005", f"m{c}", "muscat", "2m0a", m, 1800.0, "EXPOSE", 91)
            for c in range(1, 5)
        ] + [
            ("KEY2014A-003", "x", "x", "sinistro", "1m0a", m, 3600.0, "EXPOSE", 91),       # not an AVA proposal
            ("KEY2026B-007", "y", "y", "sinistro", "1m0a", m, 3600.0, "BIAS", 91),         # not EXPOSE
        ]
        con.executemany("INSERT INTO frames VALUES (?,?,?,?,?,?,?,?,?)", rows)
    with sqlite3.connect(spec) as con:
        con.execute("CREATE TABLE frames (proposal_id, exp_key, basename, mjd_obs, exptime)")
        con.executemany("INSERT INTO frames VALUES (?,?,?,?,?)", [
            ("KEY2026B-007f", "coj2m002-en12-20260901-0010", "s0", m, 1800.0),
            ("KEY2026B-007f", "coj2m002-en12-20260901-0010", "s91", m, 1800.0),   # same exposure, level 91
            ("KEY2026B-007f", "coj2m002-en12-20260901-0011", "arc", m, 60.0),      # arcs count too
        ])
    return phot, spec


def test_exposures_from_lcodb(tmp_path):
    ex = U.exposures_from_lcodb(*_lcodb(tmp_path))
    by = ex.groupby(["proposal", "instrument"])["hours"].sum().to_dict()
    assert by == {("KEY2014A-003", "1M0-SCICAM-SINISTRO"): 1.0,
                  ("KEY2026B-007", "1M0-SCICAM-SINISTRO"): 2.0,
                  ("KEY2026B-007", "2M0-SCICAM-MUSCAT"): 0.5,
                  ("KEY2026B-007f", "2M0-FLOYDS-SCICAM"): pytest.approx(31 / 60)}
    assert set(ex["mjd"]) == {U.mjd_of(date(2026, 9, 1)), U.mjd_of(date(2026, 9, 2))}


def test_estimate_charged_scales_to_totals(tmp_path):
    ex = U.exposures_from_lcodb(*_lcodb(tmp_path))
    alloc = pd.DataFrame(ALLOC + [dict(proposal="KEY2026B-007", semester="2026B", instrument="2M0-SCICAM-MUSCAT",
                                       used=0.0, alloc=10.0)])
    totals = U.mjd_of(date(2026, 9, 2))                  # totals taken before the 2 Sep exposure
    est, fac = U.estimate_charged(ex, alloc, totals_mjd=totals)
    got = est.groupby(["proposal", "instrument"])["hours"].sum().to_dict()
    assert "KEY2014A-003" not in set(est["proposal"])                     # not in the allocations
    assert ("KEY2026B-007", "2M0-SCICAM-MUSCAT") not in got               # nothing charged: dropped
    # 1 h exposed before the totals date, 450.6 h charged: factor 450.6; the later 1 h gets it too
    assert got[("KEY2026B-007", "1M0-SCICAM-SINISTRO")] == pytest.approx(2 * 450.6)
    assert got[("KEY2026B-007f", "2M0-FLOYDS-SCICAM")] == pytest.approx(20.6)
    assert fac.set_index(["proposal", "instrument"]).loc[("KEY2026B-007", "2M0-SCICAM-MUSCAT"), "factor"] == 0


def test_fold_class():
    # 2014-2018: FLOYDS charged as Spectral; a MuSCAT on a 1-m goes to the 1-m class
    assert U._fold_class("2M0-FLOYDS-SCICAM", ["1M0-SCICAM-SINISTRO", "2M0-SCICAM-SPECTRAL"]) == "2M0-SCICAM-SPECTRAL"
    assert U._fold_class("1M0-SCICAM-MUSCAT", ["1M0-SCICAM-SINISTRO", "2M0-SCICAM-MUSCAT"]) == "1M0-SCICAM-SINISTRO"
    assert U._fold_class("2M0-SCICAM-MUSCAT", ["1M0-SCICAM-SINISTRO"]) == "2M0-SCICAM-MUSCAT"


def test_estimated_files_marked(tmp_path):
    est = pd.DataFrame({"proposal": ["P"], "mjd": [61300.0], "instrument": ["1M0-SCICAM-SINISTRO"],
                        "hours": [1.5]})
    (f,) = U.write_estimated(est, tmp_path, note="test")
    seen: set = set()
    usage, dummy = U.load_usage(tmp_path, seen)
    assert seen == {"P"} and dummy == set() and usage["hours"].sum() == 1.5


# --- snapshots of the charged totals (made-up portal data; no network) ------------------------------------------

def _portal(used_1m, used_fl, sem="2026B", alloc_1m=954.0):
    return [{"id": "KEY2026B-007", "timeallocation_set": [
                {"semester": sem, "instrument_types": ["1M0-SCICAM-SINISTRO"], "std_allocation": alloc_1m,
                 "std_time_used": used_1m, "rr_allocation": 0, "rr_time_used": None, "tc_allocation": 0,
                 "tc_time_used": 0},
                {"semester": sem, "instrument_type": "2M0-FLOYDS-SCICAM", "std_allocation": 150.0,
                 "std_time_used": used_fl, "rr_allocation": 6.0, "rr_time_used": 0.5}]},
            {"id": "LCO2026B-999", "timeallocation_set": [{"semester": sem, "instrument_type": "1M0-SCICAM-SINISTRO",
                                                           "std_allocation": 10.0, "std_time_used": 1.0}]}]


def test_parse_proposals():
    rows = U.parse_proposals(_portal(100.0, 20.0))
    assert rows == [dict(proposal="KEY2026B-007", semester="2026B", instrument="1M0-SCICAM-SINISTRO",
                         alloc=954.0, used=100.0),
                    dict(proposal="KEY2026B-007", semester="2026B", instrument="2M0-FLOYDS-SCICAM",
                         alloc=156.0, used=20.5)]                           # std + rr; other prefixes dropped


def _snaps(tmp_path, series):
    """series: [(datetime, used_1m, used_floyds, semester)] -> snapshot log."""
    path = tmp_path / "snapshots.csv"
    for when, u1, uf, sem in series:
        U.append_snapshot(path, U.parse_proposals(_portal(u1, uf, sem)), when)
    return path


def _dt(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_snapshot_increments(tmp_path):
    path = _snaps(tmp_path, [(_dt(2026, 11, 16, 0), 100.0, 20.0, "2026B"),
                             (_dt(2026, 11, 16, 6), 100.0, 21.0, "2026B"),     # FLOYDS +1 h (+ rr 0.5 both times)
                             (_dt(2026, 11, 16, 12), 103.5, 21.0, "2026B"),
                             (_dt(2026, 11, 16, 18), 103.0, 21.0, "2026B")])   # refund -0.5 h
    snaps = U.read_snapshots(path)
    assert len(snaps) == 8 and list(snaps.columns) == U.SNAPSHOT_COLS
    inc, anchors = U.snapshot_increments(snaps)
    got = {(r.instrument[:3], round(r.mjd - U.mjd_of(date(2026, 11, 16)), 2)): r.hours for r in inc.itertuples()}
    assert got == {("2M0", 0.25): pytest.approx(1.0), ("1M0", 0.5): pytest.approx(3.5),
                   ("1M0", 0.75): pytest.approx(-0.5)}
    assert set(anchors["used0"]) == {100.0, 20.5}


def test_join_snapshots_anchors_estimate(tmp_path):
    d0 = U.mjd_of(date(2026, 11, 10))
    usage = pd.DataFrame({"proposal": ["KEY2026B-007"] * 3, "mjd": [d0, d0 + 1, d0 + 7.5],
                          "instrument": ["1M0-SCICAM-SINISTRO"] * 3, "hours": [30.0, 10.0, 99.0]})
    path = _snaps(tmp_path, [(_dt(2026, 11, 16, 0), 100.0, 20.0, "2026B"),
                             (_dt(2026, 11, 16, 6), 102.0, 20.0, "2026B")])
    j = U.join_snapshots(usage, U.read_snapshots(path))
    one = j[j["instrument"] == "1M0-SCICAM-SINISTRO"].sort_values("mjd")
    # before the first snapshot: 30:10 rescaled to its 100 h; after it: only the +2 h increment (the 99 h
    # estimated row after t0 is replaced)
    assert one["hours"].tolist() == pytest.approx([75.0, 25.0, 2.0])
    assert one["hours"].sum() == pytest.approx(102.0)
    fl = j[j["instrument"] == "2M0-FLOYDS-SCICAM"]
    assert fl["hours"].tolist() == [20.5] and fl["mjd"].iloc[0] == pytest.approx(U.mjd_of(_dt(2026, 11, 16, 0)))


def test_merge_allocations_new_semester(tmp_path):
    path = _snaps(tmp_path, [(_dt(2027, 2, 2, 0), 5.0, 1.0, "2027A")])
    a = U.merge_allocations(pd.DataFrame(ALLOC), U.read_snapshots(path))
    new = a[a["semester"] == "2027A"].set_index("instrument")
    assert new.loc["1M0-SCICAM-SINISTRO", "alloc"] == 954.0 and new.loc["2M0-FLOYDS-SCICAM", "used"] == 1.5
    assert len(a[a["semester"] == "2026B"]) == 3                              # untouched


@pytest.mark.parametrize("sem,prev", [("2027A", "2026B"), ("2026B", "2026A"), ("2018A", "2017AB"),
                                      ("2017AB", "2016B")])
def test_previous_semester(sem, prev):
    assert U.previous_semester(sem) == prev


def test_run_new_semester_from_snapshots(tmp_path):
    """Across a semester boundary: the new semester gets its own plot, its allocation from the snapshots, and
    the old one is finalised during the first finalise_days."""
    (tmp_path / "allocations.json").write_text(json.dumps(ALLOC))
    _write(tmp_path / "in" / "KEY2026B-007.csv", "mjd,1M0-SCICAM-SINISTRO\n61300,10\n")
    _snaps(tmp_path, [(_dt(2027, 1, 31, 18), 900.0, 150.0, "2026B"),
                      (_dt(2027, 2, 1, 0), 905.0, 150.0, "2026B"),
                      (_dt(2027, 2, 1, 0), 0.0, 0.0, "2027A"),
                      (_dt(2027, 2, 1, 6), 3.0, 0.5, "2027A")])
    cfg = _cfg(tmp_path, snapshots={"file": str(tmp_path / "snapshots.csv")}, finalise_days=7)
    logs = []
    out = U.run(cfg, now=_dt(2027, 2, 2, 12), publish=False, log=logs.append)
    assert out["semesters"] == ["2026B", "2027A"]
    assert any("new semester 2027A" in m for m in logs)
    assert any("dry run" in m for m in logs)                                   # no live request by default
    assert (tmp_path / "plots" / "lco_usage_2027A.png").exists()
    # after the finalising window only the current semester is drawn
    assert U.run(cfg, now=_dt(2027, 2, 20), publish=False, log=lambda *_: None)["semesters"] == ["2027A"]
    a = U.merge_allocations(U.load_allocations(tmp_path / "allocations.json"),
                            U.read_snapshots(tmp_path / "snapshots.csv"))
    ser = U.semester_series(U.join_snapshots(U.load_usage(tmp_path / "in")[0],
                                             U.read_snapshots(tmp_path / "snapshots.csv")),
                            a, "2027A", now_mjd=U.mjd_of(_dt(2027, 2, 2, 12)))
    by = {s.label: s for s in ser}
    assert by["1m"].used == pytest.approx(3.0) and by["1m"].alloc == 954.0
    assert by["2m/Floyds"].used == pytest.approx(1.0)                      # std 0.5 + rr 0.5 h


def test_take_snapshot_live_mocked(tmp_path, monkeypatch):
    import ava.lcodb.api as api

    class FakeClient:
        def __init__(self, token, **kw):
            assert token == "t0ken"

        def proposals(self):
            return _portal(10.0, 2.0)

    monkeypatch.setattr(api, "Client", FakeClient)
    cfg = _cfg(tmp_path, snapshots={"file": str(tmp_path / "snap.csv")})
    cfg.lco_token = "t0ken"
    assert U.take_snapshot(cfg, live=False, log=lambda *_: None) == 0 and not (tmp_path / "snap.csv").exists()
    assert U.take_snapshot(cfg, live=True, now=_dt(2026, 11, 17, 6), log=lambda *_: None) == 2
    assert U.read_snapshots(tmp_path / "snap.csv")["utc"].tolist() == ["2026-11-17T06:00:00Z"] * 2
