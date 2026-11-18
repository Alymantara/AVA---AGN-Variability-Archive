"""Crawl the archive and route frames to the spectra / photometry databases.

First run: every proposal from its semester start to now (`full`).
Daily run: each proposal from (synced_until - overlap_days) to now. Inactive proposals
whose full crawl is done are skipped unless --full.
"""
import logging
import re
from datetime import datetime, timedelta

from . import db
from .api import utcnow

log = logging.getLogger(__name__)


def semester_start(proposal_id):
    m = re.search(r'(\d{4})(A|B|AB)?', proposal_id)
    if not m:
        return datetime(2014, 1, 1)
    year, sem = int(m.group(1)), m.group(2) or 'A'
    return datetime(year, 1, 1) if sem in ('A', 'AB') else datetime(year, 7, 1)


def classify(instrument_id, cfg):
    inst = (instrument_id or '').lower()
    for kind in ('spectra', 'photometry', 'ignore'):
        if any(inst.startswith(p) for p in cfg['instruments'][kind]):
            return kind
    return None


def rejected(f, kind, cfg):
    """Why a frame of a kept camera is not stored (None = keep).

    * ``instruments.telescopes`` (prefix -> telescope_id prefixes): keep that camera only on those telescopes,
      e.g. SBIG ``kb`` on the 1 m only (the 0.4 m SBIG cameras share the prefix but have another pixel scale);
    * ``photometry_filters``: imaging filters kept in the photometry database (u B V g r i z Y).
    """
    inst = (f.get('instrument_id') or '').lower()
    for prefix, tels in ((cfg['instruments'].get('telescopes') or {}).items()):
        if inst.startswith(str(prefix).lower()):
            tel = (f.get('telescope_id') or '').lower()
            if not any(tel.startswith(str(t).lower()) for t in tels):
                return f'telescope {tel or "?"}'
    keep = cfg.get('photometry_filters')
    if kind == 'photometry' and keep and f.get('primary_optical_element') not in keep:
        return f'filter {f.get("primary_optical_element")}'
    return None


def discover_proposals(client, cfg):
    """Returns [(id, title, active, is_standard_source)].

    ``active`` comes from the observation portal for every proposal it lists, including the ones named in
    ``proposals.ids`` (co-I or public programmes); an id the portal does not list counts as inactive (crawled once,
    then only on request).  Without the portal listing (request failed) the ids count as active, as before."""
    pc = cfg['proposals']
    out = {}
    try:
        portal = {p['id']: p for p in client.proposals()}
    except Exception as e:  # noqa: BLE001 - the portal is optional for the ids
        log.warning('could not read the proposal list from the portal (%s): ids treated as active', e)
        portal = None
    if pc.get('mode', 'auto') == 'auto':
        me = client.profile()['username']
        rx = re.compile(pc.get('include_regex') or '.*')
        for p in (portal or {}).values():
            pis = [x.get('username') for x in p.get('pis', [])]
            if not rx.search(p['id']):
                continue
            if pc.get('pi_only', True) and pis and me not in pis:
                continue
            out[p['id']] = (p['id'], p.get('title', ''), int(bool(p.get('active'))), 0)
    for pid in pc.get('ids') or []:
        if pid in out:
            continue
        if portal is None:
            out[pid] = (pid, '', 1, 0)
        else:
            p = portal.get(pid) or {}
            out[pid] = (pid, p.get('title', ''), int(bool(p.get('active'))), 0)
    for pid in pc.get('exclude') or []:
        out.pop(pid, None)
    for pid in cfg.get('standard_proposals') or []:
        out[pid] = (pid, 'spectrophotometric standards', 1, 1)
    return list(out.values())


def daily_proposals(props, cfg):
    """The proposals ``lcodb daily`` crawls: the standard sources, plus the proposals the portal marks active whose id
    matches ``daily.include_regex``.  The others are left alone (``lcodb sync --proposal ID`` crawls one on request)."""
    rx = re.compile((cfg.get('daily') or {}).get('include_regex') or '.*')
    keep, skip = [], []
    for p in props:
        (keep if p[3] or (p[2] and rx.search(p[0])) else skip).append(p)
    if skip:
        log.info('daily: skipped (inactive or not matching daily.include_regex): %s', ', '.join(p[0] for p in skip))
    return keep


class Router:
    def __init__(self, cfg, cons, state):
        self.cfg, self.cons, self.state = cfg, cons, state
        self.std_names = {n.upper().replace(' ', '') for n in cfg['standards']['names']}
        self.std_props = set(cfg.get('standard_proposals') or [])
        self.buf = {'spectra': [], 'photometry': []}
        self.unknown = {}
        self.dropped = {}            # (instrument_id, reason) -> frames not stored (state.dropped_frames)
        self.n_new = self.n_upd = 0
        self.levels = {k: set(v) for k, v in cfg['reduction_levels'].items()}

    def add(self, f, standards_only=False):
        kind = classify(f.get('instrument_id'), self.cfg)
        if kind is None:
            self.unknown[f.get('instrument_id')] = self.unknown.get(f.get('instrument_id'), 0) + 1
            return
        if standards_only and kind != 'spectra':
            return
        if kind == 'ignore':
            self._drop(f, 'ignored prefix')
            return
        if f.get('reduction_level') not in self.levels[kind]:
            return
        why = rejected(f, kind, self.cfg)
        if why:
            self._drop(f, why)
            return
        self.buf[kind].append(db.frame_row(f, self.std_names, self.std_props))
        if len(self.buf[kind]) >= 2000:
            self.flush(kind)

    def _drop(self, f, reason):
        key = (f.get('instrument_id'), reason)
        self.dropped[key] = self.dropped.get(key, 0) + 1

    def flush(self, kind=None):
        for k in ([kind] if kind else list(self.buf)):
            n, u = db.upsert_frames(self.cons[k], self.buf[k])
            self.n_new += n
            self.n_upd += u
            self.buf[k] = []
        if not kind and self.unknown:
            ts = db.now()
            for inst, n in self.unknown.items():
                self.state.execute("""INSERT INTO unknown_instruments VALUES (?,?,?)
                    ON CONFLICT(instrument_id) DO UPDATE SET n_frames=n_frames+excluded.n_frames,
                    last_seen=excluded.last_seen""", (inst, n, ts))
            self.state.commit()
            self.unknown = {}
        if not kind and self.dropped:
            ts = db.now()
            for (inst, why), n in self.dropped.items():
                self.state.execute("""INSERT INTO dropped_frames VALUES (?,?,?,?)
                    ON CONFLICT(instrument_id, reason) DO UPDATE SET n_frames=n_frames+excluded.n_frames,
                    last_seen=excluded.last_seen""", (inst, why, n, ts))
            self.state.commit()
            self.dropped = {}


def crawl_window(client, cfg, router, pid, start, end, standards_only):
    """Products (levels > 0) are listed for all cameras. Raw frames are listed only where a DB keeps
    them: if photometry keeps no raw, raw frames are requested only for the spectrographs that showed
    up among the products of this window (every raw FLOYDS frame has an L90 tarball / L91 product).
    This avoids paging through ~10^5 raw imaging rows that would be thrown away."""
    base = dict(proposal_id=pid, exclude_OBSTYPE=cfg['exclude_obstypes'])
    levels = cfg['reduction_levels']
    product_levels = sorted({lv for v in levels.values() for lv in v if lv > 0} | {90})
    raw_everywhere = 0 in levels.get('photometry', [])
    k, spectrographs = 0, set()
    queries = [dict(reduction_level=lv) for lv in product_levels]
    if raw_everywhere:
        queries.append(dict(reduction_level=0))
    for q in queries:
        for f in client.frames(start, end, page_size=cfg['page_size'], **base, **q):
            if classify(f.get('instrument_id'), cfg) == 'spectra':
                spectrographs.add(f['instrument_id'])
            router.add(f, standards_only)
            k += 1
    if not raw_everywhere and 0 in levels.get('spectra', []):
        for inst in sorted(spectrographs):
            for f in client.frames(start, end, page_size=cfg['page_size'], **base,
                                   reduction_level=0, instrument_id=inst):
                router.add(f, standards_only)
                k += 1
    router.flush()
    if k:
        log.info('  %s %s .. %s: %d frames%s', pid, start.date(), end.date(), k,
                 f" (raw from {', '.join(sorted(spectrographs))})" if spectrographs else '')
    return k


def sync(client, cfg, cons, state, full=False, only=None, since=None, until=None, daily=False):
    props = discover_proposals(client, cfg)
    if only:
        props = [p for p in props if p[0] in only] or [(pid, '', 1, 0) for pid in only]
    elif daily:
        props = daily_proposals(props, cfg)
    router = Router(cfg, cons, state)
    end = until or utcnow()
    for pid, title, active, is_std in props:
        st = state.execute('SELECT * FROM sync_state WHERE proposal_id=?', (pid,)).fetchone()
        if st is None:
            state.execute('INSERT INTO sync_state (proposal_id, title, active, is_standard_source) VALUES (?,?,?,?)',
                          (pid, title, active, is_std))
        else:
            state.execute('UPDATE sync_state SET title=?, active=?, is_standard_source=? WHERE proposal_id=?',
                          (title or st['title'], active, is_std, pid))
        state.commit()
        if since:
            start = since
        elif full or st is None or not st['synced_until']:
            start = semester_start(pid) - timedelta(days=31)
        else:
            if not active and st['full_crawl_done']:
                log.info('%s: inactive, already complete; skipped (use --full to recrawl)', pid)
                continue
            start = datetime.fromisoformat(st['synced_until']) - timedelta(days=cfg['overlap_days'])
        log.info('%s (%s): %s -> %s', pid, title[:50], start.date(), end.date())
        n = 0
        for w0, w1 in _windows(start, end, cfg['window_days']):
            n += crawl_window(client, cfg, router, pid, w0, w1, standards_only=bool(is_std))
        complete = since is None and until is None
        if complete:
            state.execute("""UPDATE sync_state SET synced_until=?, n_frames=?,  -- frames read in the last run
                full_crawl_done=COALESCE(full_crawl_done, ?) WHERE proposal_id=?""",
                          (end.isoformat(timespec='seconds'), n, db.now(), pid))
            state.commit()
    return router.n_new, router.n_upd


def _windows(start, end, days):
    t = start
    while t < end:
        t2 = min(end, t + timedelta(days=days))
        yield t, t2
        t = t2


STD_SOURCE = '*standards-by-name*'


def name_variants(name):
    """'FEIGE110' -> {'FEIGE110', 'FEIGE 110'}; 'BD+284211' -> {'BD+284211', 'BD+28 4211'}."""
    n = name.upper().replace(' ', '')
    out = {n}
    m = re.match(r'^([A-Z]+)([+-]?\d.*)$', n)
    if m:
        out.add(f'{m.group(1)} {m.group(2)}')
    m = re.match(r'^(BD|CD)([+-]\d{2})(\d+)$', n)
    if m:
        out.add(f'{m.group(1)}{m.group(2)} {m.group(3)}')
    return out


def sync_calib_proposals(client, cfg, cons, state, full=False, since=None, until=None):
    """Raw FLOYDS spectra, arcs and lamp flats of the observatory calibration programmes
    (standards.calib_proposals, e.g. COJ_calib / OGG_calib). Their standards are often logged under
    ad-hoc names ('BD28', 't_GD71_1', 'eg 274'), so they are flagged by position afterwards
    (standards.flag_by_position, run by `lcodb match`). One query per programme and spectrograph."""
    scfg = cfg['standards']
    end = until or utcnow()
    router = Router(cfg, cons, state)
    n_seen = 0
    for pid in scfg.get('calib_proposals') or []:
        key = f'*calib:{pid}*'
        st = state.execute('SELECT * FROM sync_state WHERE proposal_id=?', (key,)).fetchone()
        if st is None:
            state.execute('INSERT INTO sync_state (proposal_id, title, active, is_standard_source) VALUES (?,?,1,1)',
                          (key, f'{pid}: FLOYDS raw spectra/arcs/flats'))
        if since:
            start = since
        elif full or st is None or not st['synced_until']:
            start = datetime(2014, 1, 1)
        else:
            start = datetime.fromisoformat(st['synced_until']) - timedelta(days=cfg['overlap_days'])
        k = 0
        for inst in scfg.get('calib_instruments') or ['en05', 'en06', 'en12']:
            for f in client.frames(start, end, page_size=cfg['page_size'], proposal_id=pid, instrument_id=inst,
                                   reduction_level=0, exclude_OBSTYPE=cfg['exclude_obstypes']):
                router.add(f, standards_only=True)
                k += 1
            router.flush()
        log.info('  %s %s .. %s: %d raw FLOYDS frames', pid, start.date(), end.date(), k)
        n_seen += k
        if since is None and until is None:
            state.execute('UPDATE sync_state SET synced_until=?, n_frames=? WHERE proposal_id=?',
                          (end.isoformat(timespec='seconds'), k, key))
        state.commit()
    return router.n_new, router.n_upd


def sync_standards(client, cfg, cons, state, full=False, since=None, until=None):
    """Flux standards on the spectrographs, from any proposal (observatory calib programs,
    engineering, other key projects...), matched by target name. Includes their arcs/flats."""
    scfg = cfg['standards']
    end = until or utcnow()
    st = state.execute('SELECT * FROM sync_state WHERE proposal_id=?', (STD_SOURCE,)).fetchone()
    if st is None:
        state.execute('INSERT INTO sync_state (proposal_id, title, active, is_standard_source) VALUES (?,?,1,1)',
                      (STD_SOURCE, 'flux standards from any proposal'))
    if since:
        start = since
    elif full or st is None or not st['synced_until']:
        first = cons['spectra'].execute('SELECT MIN(mjd_obs) FROM frames WHERE is_standard=0').fetchone()[0]
        start = (datetime(1858, 11, 17) + timedelta(days=first - scfg['max_dt_days'])) if first \
            else datetime(2014, 1, 1)
    else:
        start = datetime.fromisoformat(st['synced_until']) - timedelta(days=cfg['overlap_days'])
    router = Router(cfg, cons, state)
    wanted = {n.upper().replace(' ', '') for n in scfg['names']}
    log.info('standards by name: %s -> %s, %d names', start.date(), end.date(), len(wanted))
    seen = set()
    for name in sorted(scfg['names']):
        for variant in sorted(name_variants(name)):
            for w0, w1 in _windows(start, end, scfg.get('window_days', 365)):
                k = 0
                for f in client.frames(w0, w1, page_size=cfg['page_size'], target_name=variant,
                                       exclude_OBSTYPE=cfg['exclude_obstypes']):
                    norm = (f.get('target_name') or '').upper().replace(' ', '').replace('_', '')
                    if norm not in wanted or f['id'] in seen:   # the archive filter is loose
                        continue
                    seen.add(f['id'])
                    router.add(f, standards_only=True)
                    k += 1
                router.flush()
                if k:
                    log.info('  %-12s %s .. %s: %d frames', variant, w0.date(), w1.date(), k)
    if since is None and until is None:
        state.execute('UPDATE sync_state SET synced_until=?, n_frames=?, full_crawl_done=COALESCE(full_crawl_done, ?) '
                      'WHERE proposal_id=?', (end.isoformat(timespec='seconds'), len(seen), db.now(), STD_SOURCE))
    state.commit()
    return router.n_new, router.n_upd
