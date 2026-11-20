"""Parallel S3 fetches (ava.lco.download.fetch_many / run, ava.spectroscopy.download.run), offline:
fake archive pages and a fake fetcher that records how many fetches overlap."""
import hashlib
import threading
import time
from datetime import datetime

from ava.lco import download as dl


def _md5(b):
    return hashlib.md5(b).hexdigest()


class Overlap:
    """Fake fetcher: writes ``frame <name>``; tracks the largest number of fetches running at once."""
    def __init__(self, bad=()):
        self.lock, self.now, self.max, self.calls, self.bad = threading.Lock(), 0, 0, 0, set(bad)

    def __call__(self, url, dest, limiter=None):
        with self.lock:
            self.now += 1; self.calls += 1; self.max = max(self.max, self.now)
        try:
            time.sleep(0.05)
            name = url.split("//")[1]
            dest.write_bytes(b"corrupt" if name in self.bad else f"frame {name}".encode())
            return dest.stat().st_size
        finally:
            with self.lock:
                self.now -= 1


def _frame(i):
    name = f"ogg2m001-ep04-20261119-{i:04d}-e91.fits.fz"
    return {"id": i, "filename": name, "url": f"fake://{name}", "md5": _md5(f"frame {name}".encode()),
            "observation_day": "2026-11-19", "primary_optical_element": "gp", "instrument_id": "ep04",
            "telescope_id": "2m0a", "configuration_type": "EXPOSE", "target_name": "Mrk 817"}


class Pages:
    """Fake archive: ``n`` frames, served by ``offset`` / ``limit`` (at most ``page_size`` per page).
    ``next`` is always None, as the real archive's estimate can be (B25)."""
    limiter = None

    def __init__(self, n, page_size):
        self.frames, self.ps, self.calls = [_frame(i) for i in range(1, n + 1)], page_size, 0

    def get(self, url, params=None):
        self.calls += 1
        assert params["ordering"] == "id"
        off, lim = params["offset"], min(params["limit"], self.ps)
        return {"results": self.frames[off:off + lim], "next": None, "count": 1}


def _q(page_size=1000):
    return dl.Query(names=["Mrk 817"], proposals=["KEY2026B-007"], start=datetime(2026, 11, 17),
                    end=datetime(2026, 11, 21), kind="phot", filters=["gp"], page_size=page_size)


def test_fetch_many_parallel_and_errors(tmp_path):
    f = Overlap(bad={"b"})
    jobs = [(k, f"fake://{k}", tmp_path / k, _md5(f"frame {k}".encode())) for k in "abcdefgh"]
    out = list(dl.fetch_many(f, jobs, parallel=4))
    assert [k for k, *_ in out] == list("abcdefgh")                    # job order kept
    assert f.max == 4 and f.calls == 8
    bad = [k for k, n, e in out if e is not None]
    assert bad == ["b"] and "md5" in str(out[1][2])
    assert not (tmp_path / "b").exists() and not (tmp_path / "b.part").exists()
    assert (tmp_path / "a").read_bytes() == b"frame a"


def test_run_parallel_downloads_every_frame_once(tmp_path):
    c, f = Pages(23, page_size=10), Overlap()
    res = dl.run(c, _q(page_size=10), tmp_path, live=True, max_frames=100, data_id="Mrk_817", fetcher=f,
                 parallel=4, log=lambda *_: None)
    assert not res.failed and len(res.downloaded) == 23 == f.calls and res.requests == c.calls == 3
    assert 1 < f.max <= 4
    again = dl.run(c, _q(page_size=10), tmp_path, live=True, max_frames=100, data_id="Mrk_817",
                   fetcher=Overlap(), parallel=4, log=lambda *_: None)
    assert again.on_disk == 23 and not again.downloaded


def test_run_parallel_respects_cap_and_sequential_default(tmp_path):
    f = Overlap()
    res = dl.run(Pages(30, 1000), _q(), tmp_path, live=True, max_frames=7, data_id="X", fetcher=f, parallel=4,
                 log=lambda *_: None)
    assert res.capped and len(res.downloaded) == 7 == f.calls
    f1 = Overlap()
    dl.run(Pages(5, 1000), _q(), tmp_path / "seq", live=True, max_frames=10, data_id="X", fetcher=f1,
           log=lambda *_: None)
    assert f1.max == 1 and f1.calls == 5


def test_listing_pages_by_offset_ignores_next():
    """B25: one 365-day window holding 2,500 frames, with the archive's ``next`` = None (an estimate):
    every frame is listed, in 3 requests (1000 + 1000 + 500)."""
    c, stats = Pages(2500, 1000), {}
    got = [f["id"] for page in dl.pages(c, _q(page_size=1000), stats) for f in page]
    assert got == list(range(1, 2501))
    assert stats["requests"] == c.calls == 3


def test_listing_pages_exact_multiple_ends_on_empty_page():
    c, stats = Pages(2000, 1000), {}
    pages = list(dl.listing_pages(c, {"target_name": "Mrk 817"}, 1000, stats))
    assert [len(p) for p in pages] == [1000, 1000, 0] and stats["requests"] == 3
