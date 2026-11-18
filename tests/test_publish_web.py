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


def test_manuals(tmp_path, src):
    kw, _ = src
    m = tmp_path / "docs" / "photometry_manual.pdf"
    m.parent.mkdir()
    m.write_bytes(b"%PDF-1.5")
    notpdf = tmp_path / "docs" / "notes.tex"
    notpdf.write_text("x")
    dest = tmp_path / "out"
    s = publish(dest=dest, manuals=[m, notpdf, tmp_path / "docs" / "missing.pdf"], **kw)
    assert s.manuals_copied == 1 and (dest / "manuals" / "photometry_manual.pdf").read_bytes() == b"%PDF-1.5"
    assert publish(dest=dest, manuals=[m], **kw).manuals_copied == 0


def test_filters(tmp_path, src):
    import json
    import zipfile

    import numpy as np

    kw, _ = src
    fdir = tmp_path / "lco_filters"
    fdir.mkdir()
    w = np.arange(4000.0, 6001.0, 2.0)
    np.savetxt(fdir / "lco_g.txt", np.c_[w, np.where((w > 4500) & (w < 5500), 0.8, 0.0)])
    dest = tmp_path / "out"
    s = publish(dest=dest, filters_src=fdir, **kw)
    assert s.filters_copied == 1
    g = json.loads((dest / "filters" / "filters.json").read_text())["filters"]["g"]
    assert g["file"] == "lco_g.txt" and g["peak"] == 0.8
    assert g["fwhm_A"] == pytest.approx(996, abs=4) and 4990 < g["pivot_A"] < 5010
    assert "README.txt" in " ".join(zipfile.ZipFile(dest / "filters" / "ava_lco_filters.zip").namelist())
    assert "filter_dict" in (dest / ".htaccess").read_text()          # curves themselves stay downloadable
    assert publish(dest=dest, filters_src=fdir, **kw).filters_copied == 0


def test_calibration_json(tmp_path, src):
    kw, _ = src
    dest = tmp_path / "out"
    cal = tmp_path / "products" / "calibration.json"
    s = publish(dest=dest, calibration_src=cal, **kw)            # not made yet: skipped
    assert not s.calibration_copied and not (dest / "calibration").exists()
    cal.parent.mkdir(parents=True)
    cal.write_text('{"targets": []}')
    assert publish(dest=dest, calibration_src=cal, **kw).calibration_copied
    assert (dest / "calibration" / "calibration.json").read_text() == '{"targets": []}'
    assert not publish(dest=dest, calibration_src=cal, **kw).calibration_copied   # unchanged


def test_publish_download_copy_and_zip(tmp_path):
    import os
    import zipfile

    from ava.web.publish import PublishSummary, publish_download

    src = tmp_path / "src"
    src.mkdir()
    a, b = src / "a_blue.dat", src / "a.hjd"
    a.write_text("1 2 3\n")
    b.write_text("a_blue.dat 60000.1\n")
    csv = src / "T_LCO_merged_lightcurve.csv"
    csv.write_text("MJD,flux\n")
    out = tmp_path / "web" / "downloads" / "T"
    s = PublishSummary(dest=tmp_path)
    assert publish_download([csv], out / csv.name, False, s)
    assert (out / csv.name).read_text() == "MJD,flux\n"
    z = out / "T_FLOYDS_prepspec.zip"
    assert publish_download([a, b, src / "missing.dat"], z, False, s)
    assert sorted(zipfile.ZipFile(z).namelist()) == ["T_FLOYDS_prepspec/a.hjd", "T_FLOYDS_prepspec/a_blue.dat"]
    assert not publish_download([a, b], z, False, s)          # unchanged: zip kept
    os.utime(a, (z.stat().st_mtime + 10,) * 2)
    assert publish_download([a, b], z, False, s)              # newer member: rebuilt
    assert not publish_download([], out / "T_FLOYDS_1d.zip", False, s)
    assert not (out / "T_FLOYDS_1d.zip").exists()


def test_downloads_switch(tmp_path):
    import json

    from ava.web.publish import publish

    db = tmp_path / "ava.db"
    _db(db, ["Mrk_817", "NGC_4151"])
    plots = tmp_path / "plots"
    lc = tmp_path / "src" / "Mrk_817_LCO_merged_lightcurve.csv"
    lc.parent.mkdir()
    lc.write_text("MJD,flux\n")
    dl = lambda t: {f"{t}_LCO_merged_lightcurve.csv": [lc] if t == "Mrk_817" else []}  # noqa: E731
    fd = tmp_path / "filter_dict.txt"
    fd.write_text("u 3500\n")
    dest = tmp_path / "web"
    kw = dict(db=db, filter_dict=fd, dest=dest, plots_dir_for=lambda t: plots / t, downloads_for=dl)
    publish(**kw, downloads=True)
    assert json.loads((dest / "site.json").read_text()) == {"downloads": True}
    assert (dest / "downloads" / "Mrk_817" / lc.name).exists()
    assert not (dest / "downloads" / ".htaccess").exists()
    publish(**kw, downloads=False)
    assert json.loads((dest / "site.json").read_text()) == {"downloads": False}
    assert "Require all denied" in (dest / "downloads" / ".htaccess").read_text()
