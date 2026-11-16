"""Offline tests for ava.web.publish (website data folder)."""

import os
import sqlite3
from contextlib import closing

import pytest

from ava.web.publish import publish


def _db(path, data_ids):
    with closing(sqlite3.connect(path)) as c:
        c.execute("CREATE TABLE agn (id INTEGER PRIMARY KEY, name TEXT, data_id TEXT)")
        c.executemany("INSERT INTO agn (name, data_id) VALUES (?, ?)", [(d, d) for d in data_ids])
        c.commit()


def _png(path, payload=b"png"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


@pytest.fixture
def src(tmp_path):
    db = tmp_path / "ava.db"
    _db(db, ["Mrk_817", "NGC_4151"])
    fd = tmp_path / "filter_dict.txt"
    fd.write_text("Filter,wave,color\ng,4770,#006266\n")
    phot = tmp_path / "phot"
    _png(phot / "Mrk_817" / "plots" / "lco_latest_Mrk_817.png")
    _png(phot / "Mrk_817" / "plots" / "lco_latest_Mrk_817_last6.png")
    _png(phot / "Mrk_817" / "plots" / "other_figure.png")          # not a web plot
    return dict(db=db, filter_dict=fd, plots_dir_for=lambda t: phot / t / "plots"), phot


def test_publishes_snapshot_filter_dict_and_plots(tmp_path, src):
    kw, _ = src
    dest = tmp_path / "web" / "data"
    s = publish(dest=dest, **kw)

    assert s.agn == 2 and s.targets_with_plots == 1 and s.plots_copied == 2
    with closing(sqlite3.connect(dest / "ava.db")) as c:
        assert c.execute("SELECT COUNT(*) FROM agn").fetchone()[0] == 2
    assert (dest / "filter_dict.txt").read_text().startswith("Filter")
    assert sorted(p.name for p in (dest / "plots" / "Mrk_817").iterdir()) == [
        "lco_latest_Mrk_817.png", "lco_latest_Mrk_817_last6.png"]
    assert not (dest / "plots" / "NGC_4151").exists()
    assert "Require all denied" in (dest / ".htaccess").read_text()
    assert not list(dest.rglob("*.tmp"))


def test_second_run_copies_only_changes(tmp_path, src):
    kw, phot = src
    dest = tmp_path / "out"
    publish(dest=dest, **kw)
    assert publish(dest=dest, **kw).plots_copied == 0

    f = phot / "Mrk_817" / "plots" / "lco_latest_Mrk_817.png"
    f.write_bytes(b"new plot")
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))
    s = publish(dest=dest, **kw)
    assert s.plots_copied == 1
    assert (dest / "plots" / "Mrk_817" / f.name).read_bytes() == b"new plot"


def test_target_filter_and_missing_source_keep_published_plots(tmp_path, src):
    kw, phot = src
    dest = tmp_path / "out"
    publish(dest=dest, **kw)
    for p in (phot / "Mrk_817" / "plots").glob("*"):
        p.unlink()                                   # e.g. data disk not mounted
    s = publish(dest=dest, targets=["Mrk_817"], **kw)
    assert s.targets_with_plots == 0
    assert len(list((dest / "plots" / "Mrk_817").glob("*.png"))) == 2


def test_prune_removes_plots_no_longer_produced(tmp_path, src):
    kw, phot = src
    dest = tmp_path / "out"
    publish(dest=dest, **kw)
    (phot / "Mrk_817" / "plots" / "lco_latest_Mrk_817_last6.png").unlink()
    assert publish(dest=dest, **kw).plots_pruned == 0           # off by default
    s = publish(dest=dest, prune=True, **kw)
    assert s.plots_pruned == 1
    assert not (dest / "plots" / "Mrk_817" / "lco_latest_Mrk_817_last6.png").exists()


def test_dry_run_writes_nothing(tmp_path, src):
    kw, _ = src
    dest = tmp_path / "out"
    s = publish(dest=dest, dry_run=True, **kw)
    assert s.plots_copied == 2 and not dest.exists()


def test_refuses_empty_database(tmp_path, src):
    kw, _ = src
    empty = tmp_path / "empty.db"
    _db(empty, [])
    with pytest.raises(RuntimeError, match="no rows"):
        publish(dest=tmp_path / "out", **{**kw, "db": empty})


def test_usage_plots(tmp_path, src):
    kw, _ = src
    usage = tmp_path / "usage_src"
    _png(usage / "lco_usage_2026B.png")
    _png(usage / "notes.png")
    s = publish(dest=tmp_path / "out", usage_src=usage, **kw)
    assert s.usage_copied == 1 and (tmp_path / "out" / "usage" / "lco_usage_2026B.png").exists()
