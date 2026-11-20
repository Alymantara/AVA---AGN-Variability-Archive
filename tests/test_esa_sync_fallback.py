"""ESA Gaia archive: async failure falls back to sync jobs, paged past the sync row cap (20 Nov 2026)."""
import re
import sys
import types

import pytest
from astropy.table import Table

import ava.photometry.reference as R

ADQL = ("SELECT gs.source_id, gs.ra FROM gaiadr3.gaia_source AS gs WHERE "
        "1=CONTAINS(POINT('ICRS', gs.ra, gs.dec), CIRCLE('ICRS', 10.0, 20.0, 0.3))")


class _Job:
    def __init__(self, t):
        self.t = t

    def get_results(self):
        return self.t


def _fake_gaia(monkeypatch, n_rows, cap, async_ok=False, lose_rows=False):
    """A stand-in for astroquery.gaia.Gaia with ``n_rows`` sources and a sync cap of ``cap`` rows."""
    ids = list(range(1000, 1000 + n_rows))
    calls = []

    class Gaia:
        ROW_LIMIT = 50

        @staticmethod
        def launch_job_async(q, verbose=False):
            calls.append(("async", q))
            if not async_ok:
                raise RuntimeError("Error 500")
            return _Job(Table({"source_id": ids, "ra": [1.0] * len(ids)}))

        @staticmethod
        def launch_job(q, verbose=False):
            calls.append(("sync", q))
            if q.startswith("SELECT COUNT(*)"):
                return _Job(Table({"n": [n_rows]}))
            m = re.search(r"gs.source_id > (-?\d+)", q)
            rest = [i for i in ids if i > int(m.group(1))] if m else ids
            if lose_rows and m:
                rest = rest[1:]
            rest = rest[:cap]
            return _Job(Table({"source_id": rest, "ra": [1.0] * len(rest)}))

    mod = types.ModuleType("astroquery.gaia")
    mod.Gaia = Gaia
    monkeypatch.setitem(sys.modules, "astroquery.gaia", mod)
    monkeypatch.setattr(R, "ESA_PAGE_PAUSE_S", 0.0)
    return calls


def test_async_ok_no_sync(monkeypatch):
    calls = _fake_gaia(monkeypatch, 5, cap=2, async_ok=True)
    assert len(R._esa_job(ADQL)) == 5
    assert [c[0] for c in calls] == ["async"]


def test_async_fails_sync_under_cap(monkeypatch):
    calls = _fake_gaia(monkeypatch, 3, cap=10)
    t = R._esa_job(ADQL)
    assert list(t["source_id"]) == [1000, 1001, 1002]
    assert [c[0] for c in calls] == ["async", "sync", "sync"]          # COUNT + query, no paging


def test_async_fails_sync_paged_past_cap(monkeypatch):
    calls = _fake_gaia(monkeypatch, 7, cap=3)
    t = R._esa_job(ADQL)
    assert sorted(t["source_id"]) == list(range(1000, 1007))
    assert any("ORDER BY gs.source_id" in q for _, q in calls)


def test_incomplete_paging_raises(monkeypatch):
    _fake_gaia(monkeypatch, 7, cap=3, lose_rows=True)
    with pytest.raises(RuntimeError, match="ESA async: .*sync: .*incomplete"):
        R._esa_job(ADQL)
