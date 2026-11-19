"""B01 / B09: the archive client must not loop on server errors or short 429s, and the header step
keeps only the slit width, one request per exposure.  Offline (fake sessions, no network)."""
from types import SimpleNamespace

import pytest

from ava.lcodb import api, db, headers
from ava.lcodb.api import Client, ServerError, Throttled
from ava.lcodb.config import load_config


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(api.time, 'sleep', lambda s: None)


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}
        self.text = ''

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code), response=self)


class Session:
    """Answers from a list of responses (the last one repeats); counts the requests."""
    def __init__(self, responses):
        self.responses, self.calls = list(responses), 0

    def get(self, *a, **k):
        self.calls += 1
        return self.responses[min(self.calls, len(self.responses)) - 1]


def client(responses, **kw):
    c = Client(**kw)
    c._local.s = Session(responses)
    return c


def test_repeated_500_is_retried_once_then_raises():
    c = client([Resp(500)])
    with pytest.raises(ServerError):
        c.get('https://example.invalid/x')
    assert c._local.s.calls == 2                 # the request and ONE retry, not 7


def test_one_500_then_success_is_fine_and_resets_the_count():
    c = client([Resp(500), Resp(200, {'ok': 1})])
    assert c.get('https://example.invalid/x') == {'ok': 1}
    assert c._server_fails == 0


def test_after_three_failed_requests_the_client_refuses_to_send():
    c = client([Resp(503)], server_error_limit=3)
    for _ in range(3):
        with pytest.raises(ServerError):
            c.get('https://example.invalid/x')
    sent = c._local.s.calls
    with pytest.raises(ServerError):
        c.get('https://example.invalid/y')
    assert c._local.s.calls == sent == 6         # nothing more reaches the archive


def test_short_429s_raise_throttled_instead_of_returning_none():
    c = client([Resp(429, headers={'Retry-After': '1'})], max_retries=2)
    with pytest.raises(Throttled):
        c.get('https://example.invalid/x')
    assert c._local.s.calls == 3


@pytest.fixture
def con(tmp_path):
    cfg = load_config()
    cfg.raw['db_dir'] = str(tmp_path)
    return db.connect(cfg.db_path('spectra'), 'spectra')


def _frames(con, n_exp=3):
    """n_exp exposures, each a raw frame (e00) and a product (e91)."""
    from test_lcodb import frame
    rows = []
    for e in range(n_exp):
        base = f'coj2m002-en12-20261010-{e:04d}'
        rows += [db.frame_row(frame(10 * e + 1, base + '-e00'), set(), set()),
                 db.frame_row(frame(10 * e + 2, base + '-e91-1d', rlevel=91), set(), set())]
    db.upsert_frames(con, rows)


def test_pending_fetches_one_header_per_exposure(con):
    _frames(con, 3)
    ids = sorted(r['id'] for r in headers.pending(con, [0, 91]))
    assert ids == [2, 12, 22]                    # the product of each exposure; its raw twin inherits


class HeaderClient:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, 0

    def headers_of(self, frame_id):
        self.calls += 1
        if self.fail:
            raise ServerError('HTTP 500')
        return {'APERWID': 2.0, 'AIRMASS': 1.3, 'OBJECT': 'x'}


def test_only_the_slit_width_is_kept_and_no_full_header(con):
    _frames(con, 2)
    hc = HeaderClient()
    ok, bad = headers.fetch(hc, con, [0, 91], workers=1, columns=['aperwid'])
    db.propagate_headers(con, ['aperwid'])
    assert (ok, bad, hc.calls) == (2, 0, 2)
    rows = con.execute('SELECT aperwid, airmass, header_status FROM frames ORDER BY id').fetchall()
    assert [tuple(r) for r in rows] == [(2.0, None, 2), (2.0, None, 1)] * 2
    assert con.execute('SELECT COUNT(*) FROM headers').fetchone()[0] == 0


def test_server_errors_stop_the_header_step_and_leave_frames_pending(con):
    _frames(con, 3)
    hc = HeaderClient(fail=True)
    ok, bad = headers.fetch(hc, con, [0, 91], workers=1, columns=['aperwid'], batch=1)
    assert (ok, bad) == (0, 0)
    assert hc.calls == 1                         # stops at the first ServerError, does not walk the backlog
    assert con.execute('SELECT COUNT(*) FROM frames WHERE header_status=-1').fetchone()[0] == 0


def test_purge_headers_dry_run_then_live(tmp_path, monkeypatch):
    from ava.lcodb import cli
    cfg = load_config()
    cfg.raw['db_dir'] = str(tmp_path)
    con = db.connect(cfg.db_path('spectra'), 'spectra')
    _frames(con, 1)
    db.store_header(con, 2, 'a', {'APERWID': 6.0}, store_full=True)
    con.commit()
    con.close()
    cli.cmd_purge_headers(cfg, SimpleNamespace(live=False))
    con = db.connect(cfg.db_path('spectra'), 'spectra')
    assert con.execute('SELECT COUNT(*) FROM headers').fetchone()[0] == 1
    con.close()
    cli.cmd_purge_headers(cfg, SimpleNamespace(live=True))
    con = db.connect(cfg.db_path('spectra'), 'spectra')
    assert con.execute('SELECT COUNT(*) FROM headers').fetchone()[0] == 0
    assert con.execute('SELECT aperwid FROM frames WHERE id=2').fetchone()[0] == 6.0
    assert list((tmp_path / 'backups').glob('spectra_*_before_purge_headers.sqlite'))
