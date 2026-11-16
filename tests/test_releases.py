"""Offline tests for data releases: registration (the per-AGN flag) and what the website publishes."""
import sqlite3
from datetime import date

import pytest

from ava.database import releases as R
from ava.web.releases import publish_releases


def _setup(tmp_path, release_date="2027-01-15"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "ava.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE agn (id INTEGER, name TEXT, data_id TEXT)")
        con.executemany("INSERT INTO agn VALUES (?, ?, ?)", [(1, "Mrk 817", "Mrk_817"), (2, "NGC 4151", "NGC_4151")])
    root = tmp_path / "releases"
    rd = root / "DR1"
    (rd / "Mrk_817" / "photometry").mkdir(parents=True)
    (rd / "Mrk_817" / "photometry" / "Mrk_817_DR1_lightcurve.csv").write_text("MJD,flux\n59000,1.0\n")
    (rd / "Mrk_817" / "README.txt").write_text("readme\n")
    (rd / "NGC_4151").mkdir()
    (rd / "NGC_4151" / "NGC_4151_DR1_lightcurve.csv").write_text("MJD,flux\n59001,2.0\n")
    (rd / "not_an_agn").mkdir()
    (rd / "not_an_agn" / "x.txt").write_text("x")
    (rd / "release.yaml").write_text(f'title: "AVA Data Release 1"\ndate_start: "2020-08-01"\n'
                                     f'date_end: "2023-07-31"\nrelease_date: {release_date or "null"}\n')
    return db, root


def test_scan_kinds_and_unknown_folders(tmp_path):
    db, root = _setup(tmp_path)
    s = R.scan(root, "DR1", {"Mrk_817", "NGC_4151"})
    assert s.data_ids == ["Mrk_817", "NGC_4151"] and s.unknown == ["not_an_agn"]
    kinds = {f["path"]: f["kind"] for f in s.files}
    assert kinds == {"Mrk_817/README.txt": "data", "Mrk_817/photometry/Mrk_817_DR1_lightcurve.csv": "photometry",
                     "NGC_4151/NGC_4151_DR1_lightcurve.csv": "data"}
    assert s.meta["release_date"] == "2027-01-15" and s.meta["doi"] is None


def test_register_flags_and_withhold_is_sticky(tmp_path):
    db, root = _setup(tmp_path)
    s = R.scan(root, "DR1", {"Mrk_817", "NGC_4151"})
    out = R.register(db, s, withhold={"NGC_4151"})
    assert out["agn"] == 2 and out["withheld"] == ["NGC_4151"] and out["files"] == 3
    R.register(db, s)                                       # re-registering keeps the manual withhold
    with sqlite3.connect(db) as con:
        flags = dict(con.execute("SELECT data_id, available FROM agn_releases WHERE release='DR1'"))
    assert flags == {"Mrk_817": 1, "NGC_4151": 0}


def test_public_only_after_release_date(tmp_path):
    db, root = _setup(tmp_path)
    R.register(db, R.scan(root, "DR1", {"Mrk_817", "NGC_4151"}))
    assert R.public_files(db, today=date(2027, 1, 14)) == []
    assert len(R.public_files(db, today=date(2027, 1, 15))) == 3
    db2, root2 = _setup(tmp_path / "b", release_date=None)
    R.register(db2, R.scan(root2, "DR1", {"Mrk_817", "NGC_4151"}))
    assert R.public_files(db2, today=date(2100, 1, 1)) == []


def test_publish_copies_public_and_removes_withdrawn(tmp_path):
    db, root = _setup(tmp_path)
    s = R.scan(root, "DR1", {"Mrk_817", "NGC_4151"})
    R.register(db, s)
    web = tmp_path / "web"
    day = date(2027, 2, 1)
    r = publish_releases(db, root, web, today=day)
    assert r["copied"] == 3 and r["pruned"] == 0 and not r["problems"]
    assert (web / "releases/DR1/Mrk_817/photometry/Mrk_817_DR1_lightcurve.csv").read_text().startswith("MJD")
    assert (web / "releases/.htaccess").exists()
    assert publish_releases(db, root, web, today=day)["copied"] == 0       # unchanged: nothing copied
    R.register(db, s, withhold={"NGC_4151"})                                # withdraw one AGN
    r = publish_releases(db, root, web, today=day)
    assert r["pruned"] == 1 and not (web / "releases/DR1/NGC_4151").exists()


def test_publish_skips_files_changed_after_registration(tmp_path):
    db, root = _setup(tmp_path)
    R.register(db, R.scan(root, "DR1", {"Mrk_817", "NGC_4151"}))
    (root / "DR1/Mrk_817/README.txt").write_text("edited after registration\n")
    r = publish_releases(db, root, tmp_path / "web", today=date(2027, 2, 1))
    assert r["copied"] == 2 and any("re-register" in p for p in r["problems"])


def test_register_refuses_unknown_data_id(tmp_path):
    db, root = _setup(tmp_path)
    with pytest.raises(ValueError):
        R.register(db, R.scan(root, "DR1"))                 # no known_ids: not_an_agn is kept, then refused
