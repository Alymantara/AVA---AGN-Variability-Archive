"""Offline helpers of ava.spectroscopy.reduce: chain-log parsing, product lookup, staging, QC table."""
import sqlite3

import numpy as np
from astropy.io import fits

from ava.spectroscopy import reduce as R


def test_parse_chain_log(tmp_path):
    log = tmp_path / "chain.log"
    log.write_text("old-a00.fits.fz ok 3s\n### run\n"
                   "ogg2m001-en06-20260813-0008-a00.fits.fz ok 34s\n"
                   "ogg2m001-en06-20260813-0005-e00.fits.fz ERROR ValueError: x 2s\n"
                   "ogg2m001-en06-20260813-0005-e00.fits.fz ok 11s\nnoise line\n")
    s = R.parse_chain_log(log, since=1)
    assert s == {"ogg2m001-en06-20260813-0008-a00.fits.fz": "ok", "ogg2m001-en06-20260813-0005-e00.fits.fz": "ok"}


def test_stage_products_and_qc(tmp_path):
    raw, std = tmp_path / "raw" / "T", tmp_path / "raw" / "standards"
    for d, names in ((raw / "20260813", ["ogg2m001-en06-20260813-0005-e00.fits.fz", "x.fits.fz.part"]),
                     (std / "20260813", ["ogg2m001-en06-20260813-0009-e00.fits.fz"])):
        d.mkdir(parents=True)
        for n in names:
            (d / n).write_bytes(b"x")
    staged = R.stage(["2026-08-13"], raw, std, tmp_path / "input" / "run1")
    assert sorted(p.name for p in staged) == ["ogg2m001-en06-20260813-0005-e00.fits.fz",
                                              "ogg2m001-en06-20260813-0009-e00.fits.fz"]
    assert all(p.is_symlink() for p in staged)
    proc = tmp_path / "processed" / "ogg" / "en06" / "20260813" / "processed"
    proc.mkdir(parents=True)
    h = fits.Header({"L1QSN1": 88.0, "L1QFLAG": 0, "L1QFLAGS": "OK", "AIRMASS": 2.1, "L1FRGMET": "harmonic"})
    p1 = proc / "ogg2m001-en06-20260813-0005-e91-1d.fits"
    fits.HDUList([fits.PrimaryHDU(header=h)]).writeto(p1)
    prod = R.products_of(tmp_path / "processed", "ogg2m001-en06-20260813-0005-e00.fits.fz")
    assert prod["1d"] == p1 and prod["2d"] is None
    qc = R.read_qc(p1)
    assert qc["L1QSN1"] == 88.0 and qc["L1QFLAGS"] == "OK" and "L1FRGMET" in qc["header_json"]
    db = tmp_path / "spectra.sqlite"
    assert R.write_qc(db, [dict(frame_id=1, basename="b", role="science", **qc)]) == 1
    assert R.write_qc(db, [dict(frame_id=1, basename="b", role="science", **{**qc, "L1QSN1": 90.0})]) == 1
    assert sqlite3.connect(db).execute('SELECT COUNT(*), MAX("L1QSN1") FROM spec_qc').fetchone() == (1, 90.0)


def _spec(path, good=1.0, obj="Mrk 817"):
    n = 100
    flux = np.ones(2 * n)
    flux[: int(n * (1 - good))] = np.nan
    t = fits.BinTableHDU.from_columns([fits.Column("order", "I", array=np.r_[np.ones(n), 2 * np.ones(n)]),
                                       fits.Column("flux_optimal", "E", array=flux),
                                       fits.Column("mask", "I", array=np.zeros(2 * n))], name="EXTRACTED")
    fits.HDUList([fits.PrimaryHDU(), t]).writeto(path)


def _two_d(path, obj="Mrk 817"):
    img = np.zeros((50, 50), np.float32)
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(img, fits.Header({"OBJECT": obj}), name="SCI")]
                 + [fits.ImageHDU(img, name=n) for n in ("BINNED2D", "PROFILE", "BACKGROUND", "FRINGE")]).writeto(path)


def test_validate_product(tmp_path):
    _spec(tmp_path / "ok.fits"); _spec(tmp_path / "bad.fits", good=0.5)
    assert R.validate_product(tmp_path / "ok.fits") is None
    assert "order 1" in R.validate_product(tmp_path / "bad.fits")
    assert "unreadable" in R.validate_product(tmp_path / "missing.fits")


def test_clean_secondary(tmp_path):
    red = tmp_path / "reduced"; red.mkdir()
    prods = []
    for i in range(4):
        f = red / f"s{i}-e91-2d.fits"; _two_d(f)
        prods.append({"path_2d": str(f), "OBJECT": "Mrk 817"})
    arc = tmp_path / "x-a91.fits"; _two_d(arc, obj="ARC")
    stage = tmp_path / "input"; stage.mkdir(); (stage / "l.fits").symlink_to(arc)
    out = R.clean_secondary(prods, [arc], [stage], keep_binned_examples=2, example_roots=[red])
    names = [{h.name for h in fits.open(p["path_2d"])} for p in prods]
    assert all(not ({"PROFILE", "BACKGROUND", "FRINGE"} & n) and "SCI" in n for n in names)
    assert sum("BINNED2D" in n for n in names) == 2                 # examples kept
    assert "BINNED2D" not in {h.name for h in fits.open(arc)} and arc.exists()
    assert not stage.exists() and out["files"] == 5 and out["bytes"] > 0
    again = R.clean_secondary(prods, [arc], [], keep_binned_examples=2, example_roots=[red])
    assert again["files"] == 0                                      # idempotent
