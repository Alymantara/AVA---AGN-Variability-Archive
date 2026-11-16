"""Link every LCO target name to its AVA source (the AVA database `agn` table is the master target table;
a CSV export of it is accepted too).

Each target name (standards excluded) gets one position: the median requested position (CAT-RA/CAT-DEC
from the headers) or, without headers, the median image footprint centre. It is linked to the nearest AVA
source within `radius_arcsec` (header positions) or `radius_footprint_arcsec` (footprint only). A target with
no position match but the same normalised name as an AVA source is linked by name, unless its position is
known and far away: then it is left unlinked and flagged in `target_link.review`.

Manual decisions go in the overrides CSV (columns: object, ava_id; an empty ava_id = never link). They win
over the automatic match and survive every rebuild.

The result is the `target_link` table (identical in both databases) and frames.ava_id / frames.ava_data_id.
"""
import logging
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from . import db

log = logging.getLogger(__name__)


def norm(name):
    """Normalised name for comparisons: 'Mrk%20817', 'MRK 817', 'Mrk_817' -> 'MRK817'."""
    if not isinstance(name, str):
        return ''
    s = name.replace('%20', ' ').replace('#', '').upper()
    s = re.sub(r'[\s_]+', '', s)
    s = s.replace('MARKARIAN', 'MRK')
    s = re.sub(r'(?<![0-9])0+(\d)', r'\1', s)   # MCG_08-11-011 == MCG 8-11-11
    return s


def sexa(v, hours):
    if not isinstance(v, str) or ':' not in v:
        return None
    sign = -1 if v.strip().startswith('-') else 1
    try:
        p = [abs(float(x)) for x in v.strip().lstrip('+-').split(':')]
    except ValueError:
        return None
    x = p[0] + p[1] / 60 + (p[2] if len(p) > 2 else 0) / 3600
    return sign * x * (15 if hours else 1)


def sep_arcsec(ra1, de1, ra2, de2):
    r1, d1, r2, d2 = map(math.radians, (ra1, de1, ra2, de2))
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(min(1.0, max(-1.0, c)))) * 3600


def lco_targets(cons):
    """object name -> dict(ra, dec, pos='header'|'footprint', n_phot, n_spec), over both databases."""
    pos = defaultdict(lambda: {'cat': [], 'fp': [], 'n_phot': 0, 'n_spec': 0})
    for kind, con in cons.items():
        where = 'is_best=1' if kind == 'photometry' else "rlevel=0 AND obstype='SPECTRUM'"
        for obj, cra, cde, ra, de in con.execute(
                f"SELECT object, cat_ra, cat_dec, ra, dec FROM frames WHERE is_standard=0 AND {where} "
                f"AND TRIM(COALESCE(object, '')) != ''"):
            t = pos[obj]
            t['n_phot' if kind == 'photometry' else 'n_spec'] += 1
            a, d = sexa(cra, True), sexa(cde, False)
            if a is not None and d is not None:
                t['cat'].append((a, d))
            elif ra is not None and de is not None:
                t['fp'].append((ra, de))
    out = {}
    for obj, t in pos.items():
        src, code = (t['cat'], 'header') if t['cat'] else (t['fp'], 'footprint')
        if src:
            a = np.array(src)
            ra = float(np.degrees(np.arctan2(np.median(np.sin(np.radians(a[:, 0]))),
                                             np.median(np.cos(np.radians(a[:, 0]))))) % 360)
            dec = float(np.median(a[:, 1]))
        else:
            ra = dec = None
            code = None
        out[obj] = dict(ra=ra, dec=dec, pos=code, n_phot=t['n_phot'], n_spec=t['n_spec'])
    return out


def read_ava_table(path):
    """The AVA source table: the `agn` table of the AVA SQLite database (the source of truth) when `path` is a
    .db/.sqlite file, otherwise a CSV export of it."""
    path = Path(path)
    if path.suffix in ('.db', '.sqlite', '.sqlite3'):
        import sqlite3
        con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        try:
            return pd.read_sql('SELECT * FROM agn ORDER BY id', con)
        finally:
            con.close()
    return pd.read_csv(path, float_precision='round_trip')


def load_ava(path):
    ava = read_ava_table(path)
    rows = []
    for _, s in ava.iterrows():
        ra, dec = s.get('ra_deg'), s.get('dec_deg')
        ra = float(ra) if isinstance(ra, (int, float)) and not isinstance(ra, bool) else ra
        dec = float(dec) if isinstance(dec, (int, float)) and not isinstance(dec, bool) else dec
        if not (isinstance(ra, float) and np.isfinite(ra)):
            ra, dec = sexa(s.get('ra'), True), sexa(s.get('dec'), False)
        keys = {norm(s.get('name')), norm(s.get('lco_id')), norm(s.get('simbad_name')), norm(s.get('data_id'))}
        rows.append(dict(id=int(s['id']), data_id=s.get('data_id'), name=s.get('name'), ra=ra, dec=dec,
                         keys=keys - {''}))
    return rows


def load_overrides(path):
    if not path or not Path(path).exists():
        return {}
    o = pd.read_csv(path, dtype={'object': str})
    return {r.object: (None if pd.isna(r.ava_id) else int(r.ava_id)) for r in o.itertuples()}


def match(targets, ava, radius=30.0, radius_fp=180.0, overrides=None):
    """-> list of target_link rows (one per LCO object name)."""
    overrides = overrides or {}
    by_id = {s['id']: s for s in ava}
    out = []
    for obj, t in targets.items():
        row = dict(object=obj, ava_id=None, ava_data_id=None, ava_name=None, sep_arcsec=None,
                   matched_by=None, pos_source=t['pos'], obj_ra=t['ra'], obj_dec=t['dec'],
                   n_phot=t['n_phot'], n_spec=t['n_spec'], review=None, candidate_ava_id=None)
        seps = {}
        if t['ra'] is not None:
            for s in ava:
                if s['ra'] is not None and np.isfinite(s['ra']):
                    seps[s['id']] = sep_arcsec(s['ra'], s['dec'], t['ra'], t['dec'])
        r = radius if t['pos'] == 'header' else radius_fp
        if obj in overrides:
            sid = overrides[obj]
            row['matched_by'] = 'override'
            if sid is not None:
                s = by_id.get(sid)
                if s is None:
                    row['review'] = f'override ava_id {sid} is not in the AVA table'
                else:
                    row.update(ava_id=sid, ava_data_id=s['data_id'], ava_name=s['name'], sep_arcsec=seps.get(sid))
            out.append(row)
            continue
        near = sorted((d, sid) for sid, d in seps.items() if d <= r)
        named = [s for s in ava if norm(obj) in s['keys']]
        if near:
            d, sid = near[0]
            s = by_id[sid]
            how = f"position ({t['pos']})" + ('+name' if s in named else '')
            row.update(ava_id=sid, ava_data_id=s['data_id'], ava_name=s['name'], sep_arcsec=d, matched_by=how)
            if len(near) > 1:
                row['review'] = 'also within radius: ' + ', '.join(by_id[i]['name'] for _, i in near[1:])
        elif named:
            s = named[0]
            d = seps.get(s['id'])
            if d is None:
                row.update(ava_id=s['id'], ava_data_id=s['data_id'], ava_name=s['name'], matched_by='name')
            else:   # same name, but the pointing is far from the AVA position: do not link automatically
                row.update(sep_arcsec=d, matched_by='name only (not linked)', candidate_ava_id=s['id'],
                           review=f"same name as AVA {s['id']} ({s['name']}) but {d:.0f}\" away")
        out.append(row)
    return out


def link(cons, ava_csv, radius=30.0, radius_fp=180.0, overrides_csv=None):
    """Rebuild target_link and frames.ava_id in both databases. Returns (n_objects, n_linked, n_review)."""
    ava = load_ava(ava_csv)
    rows = match(lco_targets(cons), ava, radius, radius_fp, load_overrides(overrides_csv))
    ts = db.now()
    cols = ['object', 'ava_id', 'ava_data_id', 'ava_name', 'sep_arcsec', 'matched_by', 'pos_source',
            'obj_ra', 'obj_dec', 'n_phot', 'n_spec', 'review', 'candidate_ava_id']
    for con in cons.values():
        con.execute('DELETE FROM target_link')
        con.executemany(f"INSERT INTO target_link ({','.join(cols)}, updated) VALUES ({','.join('?' * (len(cols) + 1))})",
                        [tuple(r[c] for c in cols) + (ts,) for r in rows])
        con.execute('UPDATE frames SET ava_id=NULL, ava_data_id=NULL')
        con.execute("""UPDATE frames SET (ava_id, ava_data_id) =
                       (SELECT l.ava_id, l.ava_data_id FROM target_link l WHERE l.object = frames.object)
                       WHERE is_standard=0 AND object IN (SELECT object FROM target_link WHERE ava_id IS NOT NULL)""")
        con.commit()
    n_link = sum(r['ava_id'] is not None for r in rows)
    n_rev = sum(r['review'] is not None for r in rows)
    return len(rows), n_link, n_rev
