"""Thin clients for the LCO science archive and observation portal.

Only this module talks HTTP. Retries with exponential backoff on 429/5xx/timeouts.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

log = logging.getLogger(__name__)

ARCHIVE = 'https://archive-api.lco.global'
PORTAL = 'https://observe.lco.global/api'
DATEFMT = '%Y-%m-%d %H:%M:%S'


class Throttled(RuntimeError):
    """The archive asked us to back off for longer than we are willing to wait (HTTP 429 + Retry-After)."""
    def __init__(self, retry_after):
        super().__init__(f'archive throttled us; retry after {retry_after:.0f} s')
        self.retry_after = retry_after
        self.until = datetime.now(timezone.utc) + timedelta(seconds=retry_after)


class RateLimiter:
    def __init__(self, per_s):
        self.dt = 1.0 / per_s if per_s else 0.0
        self.lock = threading.Lock()
        self.next = 0.0

    def wait(self):
        if not self.dt:
            return
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next)
            self.next = t + self.dt
        if t > now:
            time.sleep(t - now)


class Client:
    def __init__(self, token=None, timeout=180, max_retries=6, rate_per_s=None, max_wait_s=900):
        self.timeout = timeout
        self.max_wait_s = max_wait_s  # longer Retry-After -> raise Throttled instead of sleeping
        self._blocked_until = 0.0     # shared by all threads: once throttled, nobody sends until then
        self._block_lock = threading.Lock()
        self.max_retries = max_retries
        self.limiter = RateLimiter(rate_per_s)
        self.headers = {'Authorization': f'Token {token}'} if token else {}
        self._local = threading.local()

    @property
    def session(self):  # one session per thread
        s = getattr(self._local, 's', None)
        if s is None:
            s = requests.Session()
            s.headers.update(self.headers)
            self._local.s = s
        return s

    def get(self, url, params=None):
        for attempt in range(self.max_retries + 1):
            wait_block = self._blocked_until - time.monotonic()
            if wait_block > self.max_wait_s:
                raise Throttled(wait_block)
            if wait_block > 0:
                time.sleep(wait_block)
            self.limiter.wait()
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                if r.status_code == 429:
                    try:
                        ra = float(r.headers.get('Retry-After', 60))
                    except ValueError:
                        ra = 60.0
                    with self._block_lock:
                        self._blocked_until = max(self._blocked_until, time.monotonic() + ra)
                    if ra > self.max_wait_s:
                        raise Throttled(ra)
                    log.warning('429: pausing all requests for %.0f s', ra)
                    continue
                if r.status_code in (500, 502, 503, 504):
                    raise requests.HTTPError(f'{r.status_code}', response=r)
                r.raise_for_status()
                return r.json()
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
                status = getattr(getattr(e, 'response', None), 'status_code', None)
                if status is not None and status < 500 and status != 429:
                    raise RuntimeError(f'{url} {params}: HTTP {status}: {e.response.text[:300]}') from e
                if attempt == self.max_retries:
                    raise
                wait = min(300, 2 ** attempt * 3)
                log.warning('retry %d after %ss: %s %s', attempt + 1, wait, url, e)
                time.sleep(wait)

    # ---------------- archive ----------------
    def frames(self, start, end, page_size=1000, related=True, **filters):
        """Yield every frame with start <= DATE_OBS < end matching the filters."""
        params = dict(filters, start=start.strftime(DATEFMT), end=end.strftime(DATEFMT),
                      limit=page_size, offset=0, ordering='id',
                      include_related_frames='true' if related else 'false')
        while True:
            d = self.get(f'{ARCHIVE}/frames/', params)
            yield from d['results']
            # `count`/`next` are estimates for some filters; stop only on a short page
            if len(d['results']) < page_size:
                return
            params['offset'] += len(d['results'])

    def count(self, start, end, **filters):
        params = dict(filters, start=start.strftime(DATEFMT), end=end.strftime(DATEFMT), limit=1)
        return self.get(f'{ARCHIVE}/frames/', params)['count']

    def headers_of(self, frame_id):
        d = self.get(f'{ARCHIVE}/frames/{frame_id}/headers/')
        return d.get('data', d)

    # ---------------- portal ----------------
    def profile(self):
        return self.get(f'{PORTAL}/profile/')

    def proposals(self):
        out, url, params = [], f'{PORTAL}/proposals/', {'limit': 200}
        while url:
            d = self.get(url, params)
            out += d['results']
            url, params = d.get('next'), None
        return out


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def windows(start, end, days):
    t = start
    while t < end:
        t2 = min(end, t + timedelta(days=days))
        yield t, t2
        t = t2
