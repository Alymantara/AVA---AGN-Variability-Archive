"""lcodb command line.

  lcodb sync        [--full] [--proposal ID ...] [--since DATE] [--until DATE] [--no-standards]
  lcodb headers     [--db spectra|photometry|both] [--limit N] [--retry-failed]
  lcodb airmass
  lcodb match       science->standards and spectrum->arcs/lamp flats (alias: standards)
  lcodb link        LCO target names -> AVA ids (frames.ava_id, table target_link)
  lcodb reextract
  lcodb daily       = sync + standards harvest + headers + airmass + matching + link
  lcodb status
"""
import argparse
import logging
import sys
import traceback
from datetime import datetime

from . import airmass, ava, calibs, db, headers, ingest, standards
from .api import Client
from .config import load_config

log = logging.getLogger('lcodb')


def _open(cfg):
    cons = {k: db.connect(cfg.db_path(k), k) for k in ('spectra', 'photometry')}
    state = db.connect(cfg.db_dir / 'state.sqlite', 'state')
    return cons, state


def _client(cfg, rate=None):
    if not cfg.token:
        log.warning('no API token found (%s / LCO_TOKEN): only public data, 100 frames per page',
                    cfg.get('token_file'))
        cfg.raw['page_size'] = min(cfg['page_size'], 100)
    return Client(cfg.token, cfg['request_timeout'], cfg['max_retries'], rate)


def _date(s):
    return datetime.fromisoformat(s) if s else None


def cmd_sync(cfg, a):
    cons, state = _open(cfg)
    c = _client(cfg)
    n, u = ingest.sync(c, cfg, cons, state, full=a.full, only=a.proposal,
                       since=_date(a.since), until=_date(a.until))
    log.info('proposals: %d new, %d refreshed frames', n, u)
    db.mark_best(cons['photometry'])
    if not a.no_standards and not a.proposal:
        n2, u2 = ingest.sync_standards(c, cfg, cons, state, full=a.full,
                                       since=_date(a.since), until=_date(a.until))
        log.info('standards by name: %d new, %d refreshed frames', n2, u2)
        n, u = n + n2, u + u2
    return n, u


def cmd_headers(cfg, a):
    cons, _ = _open(cfg)
    c = _client(cfg, cfg['header_rate_per_s'])
    if a.db == 'both':  # 'both' respects `enabled: false`; naming a db explicitly always runs it
        kinds = [k for k in ('spectra', 'photometry') if cfg['headers'][k].get('enabled', True)]
    else:
        kinds = [a.db]
    tot = 0
    for k in kinds:
        con = cons[k]
        if a.retry_failed:
            con.execute('UPDATE frames SET header_status=0 WHERE header_status=-1')
            con.commit()
        if k == 'photometry':
            db.mark_best(con)
        ok, bad = headers.fetch(c, con, cfg['headers'][k]['levels'], cfg['header_workers'],
                                cfg['headers']['store_full'], a.limit, best_only=cfg['headers'][k].get('best_only', False))
        inh = db.propagate_headers(con)
        log.info('%s: %d headers fetched, %d failed, %d frames inherited from their twin', k, ok, bad, inh)
        tot += ok
    return tot, 0


def cmd_airmass(cfg, a):
    cons, _ = _open(cfg)
    n = sum(airmass.fill(cons[k], cfg['sites']) for k in cons)
    log.info('airmass computed for %d frames', n)
    return n, 0


def cmd_match(cfg, a):
    cons, _ = _open(cfg)
    s, c = cfg['standards'], cfg['calibs']
    nsci, nrow = standards.rebuild(cons['spectra'], s['n_nearest'], s['max_dt_days'])
    log.info('standards: %d science spectra, %d matches', nsci, nrow)
    nspec, ncal = calibs.rebuild(cons['spectra'], c['n_nearest'], c['max_dt_days'])
    log.info('arcs/flats: %d spectra, %d matches', nspec, ncal)
    return nrow + ncal, 0


cmd_standards = cmd_match


def cmd_link(cfg, a):
    cons, _ = _open(cfg)
    c = cfg.get('ava') or {}
    src = c.get('db') or c.get('csv')   # the AVA database is the source of truth; the CSV is a fallback
    if not src:
        log.warning('link: no `ava.db` or `ava.csv` in config.yaml; skipped')
        return 0, 0
    n, nl, nr = ava.link(cons, cfg.resolve(src), c.get('radius_arcsec', 30.0),
                         c.get('radius_footprint_arcsec', 180.0), cfg.resolve(c.get('overrides_csv')))
    log.info('link: %d LCO targets, %d linked to AVA, %d flagged for review (see target_link.review)', n, nl, nr)
    return nl, 0


def cmd_reextract(cfg, a):
    cons, _ = _open(cfg)
    for k, con in cons.items():
        n = headers.reextract(con)
        con.execute('UPDATE frames SET header_status=0 WHERE header_status=2')
        con.commit()
        db.propagate_headers(con)
        log.info('%s: re-extracted %d headers', k, n)
    return 0, 0


def cmd_daily(cfg, a):
    a.full = a.full if hasattr(a, 'full') else False
    n, u = cmd_sync(cfg, a)
    a.db, a.limit, a.retry_failed = 'both', None, False
    cmd_headers(cfg, a)
    cmd_airmass(cfg, a)
    cmd_match(cfg, a)
    cmd_link(cfg, a)
    return n, u


def cmd_status(cfg, a):
    cons, state = _open(cfg)
    print(f'config: {cfg.path}\ndatabases: {cfg.db_dir}   token: {"yes" if cfg.token else "NO"}\n')
    print(f'{"proposal":24s} {"active":6s} {"synced until":20s} {"full crawl done":20s}')
    for r in state.execute('SELECT * FROM sync_state ORDER BY proposal_id'):
        print(f'{r["proposal_id"]:24s} {r["active"]!s:6s} {r["synced_until"] or "-":20s} {r["full_crawl_done"] or "-":20s}')
    for k, con in cons.items():
        print(f'\n== {k} ({cfg.db_path(k).name})')
        for r in con.execute("""SELECT proposal_id, rlevel, COUNT(*) n, SUM(header_status>0) hdr,
                MIN(day_obs) first, MAX(day_obs) last FROM frames GROUP BY proposal_id, rlevel
                ORDER BY proposal_id, rlevel"""):
            print(f'  {r["proposal_id"]:24s} L{r["rlevel"]:<3d} {r["n"]:8d} frames  {r["hdr"] or 0:8d} with header  '
                  f'{r["first"]} .. {r["last"]}')
        if k == 'spectra':
            m = con.execute('SELECT COUNT(DISTINCT sci_id), AVG(ABS(dt_hours)) FROM std_match WHERE rank=1').fetchone()
            print(f'  science spectra with a matched standard: {m[0]}  (mean |dt| of best: {m[1] or 0:.1f} h)')
            for r in con.execute("""SELECT obstype, COUNT(*), SUM(same_block), AVG(ABS(dt_hours))
                    FROM calib_match WHERE rank=1 GROUP BY obstype"""):
                print(f'  spectra with an {r[0]:8s}: {r[1]}  ({r[2]} from the same block; mean |dt| {r[3]:.2f} h)')
    unk = state.execute('SELECT * FROM unknown_instruments ORDER BY n_frames DESC').fetchall()
    if unk:
        print('\nunclassified instruments (add their prefix to config.yaml `instruments`):')
        for r in unk:
            print(f'  {r["instrument_id"]:10s} {r["n_frames"]:8d}  last {r["last_seen"]}')
    print('\nlast runs:')
    for r in state.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 5'):
        print(f'  {r["started"]}  {r["command"]:40s} {r["status"]:6s} new={r["n_new"]} upd={r["n_updated"]} {r["message"] or ""}')
    return None


def main(argv=None):
    p = argparse.ArgumentParser(prog='lcodb', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--config', help='config.yaml (default: next to the package, or $LCODB_CONFIG)')
    p.add_argument('-v', '--verbose', action='store_true')
    sub = p.add_subparsers(dest='cmd', required=True)
    for name in ('sync', 'daily'):
        s = sub.add_parser(name)
        s.add_argument('--full', action='store_true', help='recrawl from each proposal start')
        s.add_argument('--proposal', nargs='+', help='only these proposals')
        s.add_argument('--since', help='YYYY-MM-DD: crawl from this date (does not move the sync marker)')
        s.add_argument('--until', help='YYYY-MM-DD: crawl up to this date (does not move the sync marker)')
        s.add_argument('--no-standards', action='store_true', help='skip the by-name standards search')
    s = sub.add_parser('headers')
    s.add_argument('--db', choices=['spectra', 'photometry', 'both'], default='both')
    s.add_argument('--limit', type=int)
    s.add_argument('--retry-failed', action='store_true')
    for name in ('airmass', 'match', 'standards', 'link', 'reextract', 'status'):
        sub.add_parser(name)
    a = p.parse_args(argv)

    cfg = load_config(a.config)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S',
                        handlers=[logging.StreamHandler(),
                                  logging.FileHandler(cfg.db_dir / 'lcodb.log')])
    fn = globals()[f'cmd_{a.cmd}']
    if a.cmd == 'status':
        fn(cfg, a)
        return 0
    _, state = _open(cfg)
    args = argv if argv is not None else sys.argv[1:]
    cmdline = ' '.join(args[args.index(a.cmd):]) if a.cmd in args else a.cmd
    cur = state.execute('INSERT INTO runs (command, started, status) VALUES (?,?,?)',
                        (cmdline, db.now(), 'running'))
    run_id = cur.lastrowid
    state.commit()
    try:
        n, u = fn(cfg, a) or (0, 0)
        state.execute('UPDATE runs SET finished=?, status=?, n_new=?, n_updated=? WHERE id=?',
                      (db.now(), 'ok', n, u, run_id))
        rc = 0
    except Exception as e:
        log.error('failed: %s', e)
        log.debug(traceback.format_exc())
        state.execute('UPDATE runs SET finished=?, status=?, message=? WHERE id=?',
                      (db.now(), 'error', str(e)[:500], run_id))
        rc = 1
    state.commit()
    return rc


if __name__ == '__main__':
    sys.exit(main())
