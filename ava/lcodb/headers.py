"""Download FITS headers for frames that lack them (resumable: progress is in header_status)."""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import db
from .api import Throttled

log = logging.getLogger(__name__)


def pending(con, levels, limit=None, best_only=False, since=None):
    """Frames still without a header; ``since`` (YYYY-MM-DD): only frames observed on or after that night."""
    q = (f"SELECT id, md5 FROM frames WHERE header_status=0 AND rlevel IN ({','.join('?' * len(levels))}) "
         + ("AND is_best=1 " if best_only else "") + ("AND day_obs >= ? " if since else "") + "ORDER BY date_obs DESC")
    if limit:
        q += f' LIMIT {int(limit)}'
    return con.execute(q, list(levels) + ([str(since)] if since else [])).fetchall()


def fetch(client, con, levels, workers=8, store_full=True, limit=None, commit_every=500, best_only=False,
          batch=2000, since=None):
    todo = pending(con, levels, limit, best_only, since)
    log.info('headers to fetch: %d', len(todo))
    if not todo:
        return 0, 0
    ok = bad = i = 0
    throttled = None
    t0 = time.time()
    # Work in batches and drop each future once stored, so memory stays flat (~MBs) even for 5e5 frames;
    # a finished future otherwise keeps its parsed header alive until the whole step ends.
    with ThreadPoolExecutor(workers) as ex:
        for b0 in range(0, len(todo), batch):
            futs = {ex.submit(client.headers_of, r['id']): r for r in todo[b0:b0 + batch]}
            for fut in as_completed(futs):
                r = futs.pop(fut)
                i += 1
                try:
                    db.store_header(con, r['id'], r['md5'], fut.result(), store_full)
                    ok += 1
                except Throttled as e:  # leave it pending (status 0); stop the whole step cleanly
                    throttled = e
                except Exception as e:  # keep going; failed ones are retried with --retry-failed
                    log.warning('header %s failed: %s', r['id'], e)
                    con.execute('UPDATE frames SET header_status=-1 WHERE id=?', (r['id'],))
                    bad += 1
                del fut
                if i % commit_every == 0:
                    con.commit()
                    rate = i / (time.time() - t0)
                    log.info('  %d/%d headers (%.1f/s, ~%.1f h left)', i, len(todo), rate,
                             (len(todo) - i) / rate / 3600)
            con.commit()
            if throttled:
                for f in futs:
                    f.cancel()
                log.warning('stopping headers: %s (UTC %s); %d left pending, rerun to resume',
                            throttled, throttled.until.strftime('%Y-%m-%d %H:%M'), len(todo) - ok - bad)
                break
    return ok, bad


def reextract(con):
    """Re-fill the header columns from stored full headers (after editing HEADER_COLUMNS)."""
    n = 0
    for (fid,) in con.execute('SELECT frame_id FROM headers').fetchall():
        hdr = db.load_header(con, fid)
        vals = db.header_values(hdr)
        con.execute(f"UPDATE frames SET {','.join(f'{c}=?' for c in vals)} WHERE id=?",
                    tuple(vals.values()) + (fid,))
        n += 1
        if n % 5000 == 0:
            con.commit()
    con.commit()
    return n
