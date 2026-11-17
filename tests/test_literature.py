"""Offline tests for ava.database.literature (CSV → agn_literature, optional agn updates)."""

import sqlite3
from contextlib import closing

import pytest

from ava.database.literature import REQUIRED, import_literature, read_csv

HEAD = ",".join(REQUIRED + ["z_ref", "mbh_ref", "type_ref"])


def _db(tmp_path):
    db = tmp_path / "ava.db"
    with closing(sqlite3.connect(db)) as con:
        con.execute("CREATE TABLE agn (id INTEGER PRIMARY KEY, data_id TEXT, redshift REAL, red_cite TEXT, red_url TEXT,"
                    " logm REAL, logm_cite TEXT, logm_url TEXT, l_5100 REAL, l_5100_cite TEXT, l_5100_url TEXT,"
                    " AGN_type TEXT)")
        con.executemany("INSERT INTO agn (id, data_id, redshift, logm, l_5100, AGN_type) VALUES (?,?,?,?,?,?)",
                        [(1, "Mrk_817", 0.0313, 7.6, 43.78, None), (2, "IGR_X", None, 0.15, None, "XRB")])
        con.commit()
    return db


def _csv(tmp_path, rows):
    p = tmp_path / "agn_properties.csv"
    p.write_text(HEAD + "\n" + "\n".join(rows) + "\n")
    return p


ROW817 = "Mrk_817,Mrk 817,0.031455,7.59,0.07,19.0,3.0,43.74,Sy1.5,2021ApJ...922..151K,test,2010A&A...518A..10V,2015PASP..127...67B,VCV10"


def test_read_csv_validates(tmp_path):
    with pytest.raises(ValueError, match="non-numeric"):
        read_csv(_csv(tmp_path, ["Mrk_817,Mrk 817,abc,,,,,,,,"]))
    with pytest.raises(ValueError, match="duplicate"):
        read_csv(_csv(tmp_path, ["A,a,,,,,,,,,", "A,a,,,,,,,,,"]))


def test_dry_run_writes_nothing(tmp_path):
    db = _db(tmp_path)
    res = import_literature(db, _csv(tmp_path, [ROW817, "Nope,x,,,,,,,,,"]), apply_to_agn=True)
    assert res["rows"] == 1 and res["unknown"] == ["Nope"]
    assert {u["column"] for u in res["agn_updates"]} >= {"redshift", "logm", "l_5100", "AGN_type", "red_url"}
    with closing(sqlite3.connect(db)) as con:
        assert con.execute("SELECT count(*) FROM sqlite_master WHERE name='agn_literature'").fetchone()[0] == 0
        assert con.execute("SELECT logm FROM agn WHERE id=1").fetchone()[0] == 7.6


def test_upsert_and_empty_cells(tmp_path):
    db = _db(tmp_path)
    import_literature(db, _csv(tmp_path, [ROW817]), write=True)
    # second import: tau removed in the CSV → NULL in the table (CSV is the source of truth)
    import_literature(db, _csv(tmp_path, [ROW817.replace(",19.0,3.0,", ",,,")]), write=True)
    with closing(sqlite3.connect(db)) as con:
        rows = con.execute("SELECT data_id, z, tau_hbeta_days, agn_type FROM agn_literature").fetchall()
        assert rows == [("Mrk_817", 0.031455, None, "Sy1.5")]
        assert con.execute("SELECT logm FROM agn WHERE id=1").fetchone()[0] == 7.6   # agn untouched by default


def test_apply_to_agn_keeps_non_agn_type(tmp_path):
    db = _db(tmp_path)
    (tmp_path / "references.csv").write_text("bibcode,cite\n2015PASP..127...67B,Bentz & Katz (2015)\n")
    rows = [ROW817, "IGR_X,IGR X,,,,,,,Sy1,,,,,"]
    import_literature(db, _csv(tmp_path, rows), apply_to_agn=True, write=True)
    with closing(sqlite3.connect(db)) as con:
        r = con.execute("SELECT redshift, logm, logm_cite, logm_url, AGN_type FROM agn WHERE id=1").fetchone()
        assert r == (0.031455, 7.59, "Bentz & Katz (2015)", "2015PASP..127...67B", "Sy1.5")
        assert con.execute("SELECT AGN_type FROM agn WHERE id=2").fetchone()[0] == "XRB"


def test_cites_stored_and_plain_text_refs(tmp_path):
    db = _db(tmp_path)
    (tmp_path / "references.csv").write_text("bibcode,cite\n2015PASP..127...67B,Bentz & Katz (2015)\n")
    row = ROW817.replace(",VCV10", ",SIMBAD otype")
    res = import_literature(db, _csv(tmp_path, [row]), apply_to_agn=True, write=True)
    with closing(sqlite3.connect(db)) as con:
        r = con.execute("SELECT mbh_cite, type_cite, z_cite FROM agn_literature").fetchone()
        assert r == ("Bentz & Katz (2015)", "SIMBAD otype", "2010A&A...518A..10V")   # unknown bibcode: shown as is
    assert not any(u["column"] == "red_url" and u["new"] is None for u in res["agn_updates"])
