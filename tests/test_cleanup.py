"""Offline tests for the raw-frame clean-up (ava.archive.cleanup), the frame metadata kept in catalogues,
the download skip of already-processed frames, and the lcodb header cut-off."""
import os
import sqlite3
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from astropy.io import fits

from ava.archive import cleanup as C
from ava.lco import download as dl
from ava.photometry import process as P

OLD = time.time() - 30 * C.DAY
HDR = {"EXPTIME": 100.0, "MJD-OBS": 61000.25, "FILTER": "gp", "DAY-OBS": "20260101", "AIRMASS": 1.3,
       "L1FWHM": 2.1, "SATURATE": 120000.0, "SITEID": "lsc"}


def _image(path, old=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    sci = fits.CompImageHDU(np.zeros((20, 30), dtype=np.float32), name="SCI")
    for k, v in HDR.items():
        sci.header[k] = v
    fits.HDUList([fits.PrimaryHDU(), sci]).writeto(path)
    if old:
        os.utime(path, (OLD, OLD))
    return path


def _catalogue(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    t = fits.BinTableHDU.from_columns([fits.Column(name="X", format="E", array=np.zeros(3))])
    fits.HDUList([fits.PrimaryHDU(), t]).writeto(path)
    return path


def _touch(path, old=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * 10)
    if old:
        os.utime(path, (OLD, OLD))
    return path


def _qc(db, frames, complete=True):
    from ava.photometry import store

    rows = []
    for f in frames:
        r = dict(frame=f, data_id="T", pipeline_version=P.PIPELINE_VERSION, filter="gp", exptime=100.0,
                 mjd_mid=61000.25, day_obs="20260101", site="lsc")
        if complete:
            r.update(saturate=120000.0, naxis1=30, naxis2=20)
        rows.append(r)
    store.write_frame_qc(db, rows)


def test_frame_qc_keeps_image_metadata_and_adds_columns(tmp_path):
    from ava.photometry import store

    db = tmp_path / "phot.sqlite"
    with sqlite3.connect(db) as con:                       # a frame_qc made before saturate / naxis existed
        con.execute('CREATE TABLE frame_qc ("frame" TEXT PRIMARY KEY, "data_id" TEXT, "filter" TEXT, '
                    '"exptime" REAL, "mjd_mid" REAL, "pipeline_version" TEXT)')
        con.execute("INSERT INTO frame_qc VALUES ('f1', 'T', 'gp', 100, 61000.25, ?)", (P.PIPELINE_VERSION,))
    m = store.frame_meta(db, "T")["f1"]
    assert not store.meta_complete(m)
    img = _image(tmp_path / "raw/20260101/lsc1m005-fa15-20260101-0001-e91.fits.fz")
    store.fill_frame_meta(db, {"f1": P.header_meta(img)})
    m = store.frame_meta(db, "T")["f1"]
    assert store.meta_complete(m) and (m["saturate"], m["naxis1"], m["naxis2"]) == (120000.0, 30, 20)
    assert m["exptime"] == 100 and m["filter"] == "gp"
    _qc(db, ["f2"])                                         # new rows store everything directly
    assert store.meta_complete(store.frame_meta(db, "T")["f2"])


def test_photometry_rules_and_dry_run_does_not_write(tmp_path):
    from ava.photometry import store

    raw, cat, db = tmp_path / "raw", tmp_path / "cat", tmp_path / "phot.sqlite"
    frames = [f"lsc1m005-fa15-20260101-000{i}-e91" for i in range(1, 6)]
    for f in frames:
        _image(raw / "20260101" / f"{f}.fits.fz", old=not f.endswith("0004-e91"))
        if not f.endswith("0002-e91"):
            _catalogue(cat / f"{f}_cat.fits")
    _qc(db, [f for f in frames if not f.endswith(("0003-e91", "0005-e91"))])
    _qc(db, [frames[4]], complete=False)                    # calibrated before saturate/naxis were stored
    cutoff = time.time() - 7 * C.DAY
    cal = C.calibrated_frames(db, "T", P.PIPELINE_VERSION)
    assert cal == {frames[0]: True, frames[1]: True, frames[3]: True, frames[4]: False}
    r = C.photometry_target(raw, cat, cal, cutoff, frame_db=db, write=False)
    # 0001 deletable; 0002 no catalogue; 0003 not calibrated; 0004 too recent; 0005 deletable after completing
    assert sorted(p.name[:-8] for p in r.delete) == [frames[0], frames[4]]
    assert r.kept == {"no catalogue": 1, "not calibrated (no current frame_qc row)": 1, "within retention": 1}
    assert r.filled == 1 and not store.meta_complete(store.frame_meta(db, "T")[frames[4]])   # dry run: no write
    r = C.photometry_target(raw, cat, cal, cutoff, frame_db=db, write=True)
    assert store.meta_complete(store.frame_meta(db, "T")[frames[4]])
    C.delete_files(r.delete, [])
    assert not (raw / f"20260101/{frames[0]}.fits.fz").exists()
    assert (cat / f"{frames[0]}_cat.fits").exists()                     # catalogues are never deleted


def _night(root, night, n_sci=2, old=True):
    for i in range(n_sci):
        _touch(root / night / f"ogg2m001-en06-{night}-000{i + 1}-e00.fits.fz", old)
    _touch(root / night / f"ogg2m001-en06-{night}-0008-a00.fits.fz", old)
    _touch(root / night / f"ogg2m001-en06-{night}-0009-w00.fits.fz", old)
    return [f"ogg2m001-en06-{night}-000{i + 1}-e00" for i in range(n_sci)]


def _reduce(spec, night, sci):
    for s in sci:
        _touch(spec / "reduced" / night / (s.replace("-e00", "-e91-1d") + ".fits.fz"))


def test_spectra_night_needs_reduction_qc_and_products(tmp_path):
    raw, spec = tmp_path / "raw/Mrk_817", tmp_path / "spec/Mrk_817"
    done = _night(raw, "20260801")
    no_prod = _night(raw, "20260802")
    no_1d = _night(raw, "20260803")
    recent = _night(raw, "20260804", old=False)
    for n, s in (("20260801", done), ("20260802", no_prod), ("20260804", recent)):
        _reduce(spec, n, s)
    _reduce(spec, "20260803", no_1d[:1])
    pd.DataFrame({"basename": done + no_1d + recent}).to_parquet(spec / "hbeta_fits.parquet")
    qc = set(done + no_prod + no_1d + recent)
    r = C.spectra_target(raw, spec, qc, time.time() - 7 * C.DAY)
    assert sorted({p.parent.name for p in r.delete}) == ["20260801"] and len(r.delete) == 4   # e00 x2 + arc + flat
    assert r.kept == {"no final products (hbeta_fits)": 4, "not reduced (no -1d)": 4, "within retention": 4}
    assert C.spectra_target(raw, spec, qc - {done[0]}, time.time() - 7 * C.DAY).kept["no spec_qc row"] == 4
    C.delete_files(r.delete, [])
    assert not (raw / "20260801").exists() and (spec / "reduced/20260801").exists()


def test_standards_wait_for_target_nights(tmp_path):
    std = tmp_path / "standards"
    a = _night(std, "20260801", n_sci=1)
    b = _night(std, "20260802", n_sci=1)
    r = C.standards(std, waiting={"20260802"}, qc_basenames=set(a + b), cutoff=time.time() - 7 * C.DAY)
    assert {p.parent.name for p in r.delete} == {"20260801"} and r.kept == {"a target night still needs it": 3}
    r = C.standards(std, waiting=set(), qc_basenames=set(a), cutoff=time.time() - 7 * C.DAY)
    assert r.kept == {"standard not reduced (no spec_qc row)": 3}


def test_delete_marks_local_files(tmp_path):
    f = _touch(tmp_path / "raw/20260101/a.fits.fz")
    db = tmp_path / "phot.sqlite"
    with sqlite3.connect(db) as con:
        con.executescript(dl.LOCAL_FILES_DDL)
        con.execute("INSERT INTO local_files (frame_id, path) VALUES (1, ?)", (str(f),))
    assert C.delete_files([f], [db]) == 1
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT deleted_utc FROM local_files").fetchone()[0]
    assert not (tmp_path / "raw/20260101").exists()          # emptied night folder removed


def test_retention_must_exceed_download_lookback():
    cfg = SimpleNamespace(_raw={"download": {"overlap_days": 2}, "spectroscopy": {"download": {"overlap_days": 3}}})
    C.check_retention(cfg, 7)
    with pytest.raises(ValueError):
        C.check_retention(cfg, 3)


def test_download_skips_catalogued_frames(tmp_path):
    cat = _catalogue(tmp_path / "cat/lsc1m005-fa15-20260101-0001-e91_cat.fits").parent
    done = dl.catalogued(cat)
    assert done("lsc1m005-fa15-20260101-0001-e91.fits.fz") and not done("lsc1m005-fa15-20260101-0002-e91.fits.fz")

    class Client:
        limiter = None

        def get(self, *a, **k):
            return {"results": [{"id": i, "filename": f"lsc1m005-fa15-20260101-000{i}-e91.fits.fz",
                                 "configuration_type": "EXPOSE", "primary_optical_element": "gp",
                                 "observation_day": "2026-01-01", "url": "u"} for i in (1, 2)], "next": None}

    q = dl.Query(names=["X"], proposals=["P"], start=pd.Timestamp("2026-01-01").to_pydatetime(),
                 end=pd.Timestamp("2026-01-02").to_pydatetime(), kind="phot")
    res = dl.run(Client(), q, tmp_path / "raw", live=False, max_frames=10, data_id="X", done=done, log=lambda m: None)
    assert (res.found, res.processed, res.missing) == (2, 1, 1)


def test_header_cutoff(tmp_path):
    from ava.lcodb import headers

    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE frames (id INTEGER, md5 TEXT, header_status INTEGER, rlevel INTEGER, is_best INTEGER, "
                "day_obs TEXT, date_obs TEXT, exp_key TEXT)")
    con.executemany("INSERT INTO frames VALUES (?,?,?,?,?,?,?,?)",
                    [(1, "a", 0, 0, 1, "2018-01-01", "2018", "e1"), (2, "b", 0, 0, 1, "2026-11-01", "2026", "e2")])
    assert [r["id"] for r in headers.pending(con, [0])] == [2, 1]
    assert [r["id"] for r in headers.pending(con, [0], since="2021-09-01")] == [2]
