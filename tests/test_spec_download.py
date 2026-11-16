"""FLOYDS download planning and fetching (ava.spectroscopy.download), offline: synthetic spectra DB,
fake archive client and fetcher."""
import hashlib
import sqlite3
from pathlib import Path

import pytest

from ava.spectroscopy import download as SD

BODY = {}  # frame_id -> bytes served by the fake archive


def _md5(b):
    return hashlib.md5(b).hexdigest()


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "spectra.sqlite"
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE frames (id INTEGER PRIMARY KEY, basename TEXT, filename TEXT, extension TEXT, rlevel INTEGER,
                         obstype TEXT, day_obs TEXT, date_obs TEXT, md5 TEXT, raw_id INTEGER, ava_id INTEGER,
                         is_standard INTEGER DEFAULT 0);
    CREATE TABLE cal (spec_id INTEGER, arc_id INTEGER, flat_id INTEGER);
    CREATE TABLE std (sci_id INTEGER, std_id INTEGER);
    CREATE VIEW spectrum_calibs AS SELECT spec_id, arc_id, flat_id FROM cal;
    CREATE VIEW spectrum_standards AS SELECT sci_id, std_id FROM std;
    """)
    rows = []

    def add(fid, base, rlevel, obstype, day, ava=None, raw=None, std=0):
        body = f"frame {fid}".encode()
        BODY[fid] = body
        rows.append((fid, base, None, ".fits.fz", rlevel, obstype, day, day + "T05:00", _md5(body), raw, ava, std))

    for k, day in enumerate(["2026-08-13", "2026-08-18", "2026-09-15"]):
        b = 100 * (k + 1); d = day.replace("-", "")
        add(b + 1, f"ogg-en06-{d}-0001-e00", 0, "SPECTRUM", day, ava=2)
        add(b + 2, f"ogg-en06-{d}-0002-e00", 0, "SPECTRUM", day, ava=2)
        add(b + 3, f"ogg-en06-{d}-0003-a00", 0, "ARC", day)
        add(b + 4, f"ogg-en06-{d}-0004-w00", 0, "LAMPFLAT", day)
        add(b + 5, f"ogg-en06-{d}-0005-e00", 0, "SPECTRUM", day, std=1)      # standard
        add(b + 6, f"ogg-en06-{d}-0006-a00", 0, "ARC", day)
        add(b + 7, f"ogg-en06-{d}-0007-w00", 0, "LAMPFLAT", day)
        add(b + 11, f"ogg-en06-{d}-0001-e91-1d", 91, "SPECTRUM", day, raw=b + 1)
        add(b + 12, f"ogg-en06-{d}-0001-e91-2d", 91, "SPECTRUM", day, raw=b + 1)
        add(b + 15, f"ogg-en06-{d}-0005-e91-1d", 91, "STANDARD", day, raw=b + 5)
        add(b + 19, f"ogg-en06-{d}-0003-a91", 91, "ARC", day, raw=b + 3)    # not a -1d/-2d: never planned
        for s in (b + 1, b + 2):
            con.execute("INSERT INTO cal VALUES (?,?,?)", (s, b + 3, b + 4))
            con.execute("INSERT INTO std VALUES (?,?)", (s, b + 5))
        con.execute("INSERT INTO cal VALUES (?,?,?)", (b + 5, b + 6, b + 7))
    con.executemany("INSERT INTO frames VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit(); con.close()
    return db


class FakeClient:
    def __init__(self):
        self.calls = 0
        self.limiter = None

    def get(self, url, params=None):
        self.calls += 1
        fid = int(url.rstrip("/").split("/")[-1])
        return {"url": f"fake://{fid}", "md5": _md5(BODY[fid])}


def fake_fetch(url, dest, limiter=None):
    b = BODY[int(url.split("//")[1])]
    dest.write_bytes(b)
    return len(b)


def test_nights_and_plan(tmp_path):
    db = _db(tmp_path)
    assert SD.science_nights(db, 2, select="latest", max_nights=2) == ["2026-09-15", "2026-08-18"]
    assert SD.science_nights(db, 2, nights=["20260813"]) == ["2026-08-13"]
    assert SD.science_nights(db, 2, since="2026-08-15", select="oldest") == ["2026-08-18", "2026-09-15"]
    p = SD.plan(db, 2, ["2026-08-13"])
    assert p.role.value_counts().to_dict() == {"science": 2, "arc": 1, "flat": 1, "standard": 1, "std_arc": 1,
                                               "std_flat": 1, "archive_1d": 1, "archive_2d": 1, "std_archive_1d": 1}
    assert len(SD.plan(db, 2, ["2026-08-13"], archive_products=False)) == 7
    r = p.set_index("role")
    raw, root = tmp_path / "raw_data", tmp_path
    dest = {k: SD.destination(r.loc[[k]].reset_index().iloc[0], spec_raw_root=raw, spec_root=root, target="Mrk_817")
            for k in ("arc", "std_flat", "archive_1d", "std_archive_1d")}
    assert dest["arc"] == raw / "Mrk_817" / "20260813" / "ogg-en06-20260813-0003-a00.fits.fz"
    assert dest["std_flat"].parent == raw / "standards" / "20260813"
    assert dest["archive_1d"].parent == root / "Mrk_817" / "archive" / "20260813"
    assert dest["std_archive_1d"].parent == root / "standards" / "archive" / "20260813"


def test_dry_run_live_and_rerun(tmp_path):
    db = _db(tmp_path)
    p = SD.plan(db, 2, SD.science_nights(db, 2, select="latest", max_nights=2))
    kw = dict(spec_raw_root=tmp_path / "raw_data", spec_root=tmp_path, target="Mrk_817", registry_db=db)
    dry = SD.run(None, p, live=False, max_frames=100, **kw)          # no client needed: no request
    assert dry.missing == len(p) and dry.requests == 0 and not list((tmp_path / "raw_data").glob("**/*.fz"))
    c = FakeClient()
    capped = SD.run(c, p, live=True, max_frames=5, fetcher=fake_fetch, **kw)
    assert capped.capped and len(capped.downloaded) == 5 and c.calls == 5
    live = SD.run(c, p, live=True, max_frames=100, fetcher=fake_fetch, **kw)
    assert not live.failed and live.on_disk == 5 and len(live.downloaded) == len(p) - 5
    again = SD.run(c, p, live=True, max_frames=100, fetcher=fake_fetch, **kw)
    assert again.on_disk == len(p) and again.requests == 0
    n, roles = sqlite3.connect(db).execute("SELECT COUNT(*), COUNT(DISTINCT role) FROM local_files").fetchone()
    assert n == len(p) and roles == 9


def test_md5_mismatch_is_a_failure(tmp_path):
    db = _db(tmp_path)
    p = SD.plan(db, 2, ["2026-08-13"]).head(1)
    bad = lambda url, dest, limiter=None: dest.write_bytes(b"corrupt") or 7  # noqa: E731
    res = SD.run(FakeClient(), p, spec_raw_root=tmp_path / "r", spec_root=tmp_path, target="T", live=True,
                 max_frames=10, fetcher=bad)
    assert len(res.failed) == 1 and "md5" in next(iter(res.failed.values()))
    assert not [f for f in (tmp_path / "r").glob("**/*") if f.is_file()]   # neither the file nor its .part


def test_archive_products_1d_only(tmp_path):
    db = _db(tmp_path)
    roles = set(SD.plan(db, 2, ["2026-08-13"], archive_products="1d").role)
    assert {"archive_1d", "std_archive_1d"} <= roles and "archive_2d" not in roles
