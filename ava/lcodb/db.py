"""SQLite helpers: open (with automatic migration), upsert frames, store headers."""
import json
import math
import sqlite3
import zlib
from datetime import datetime

from . import schema


def _existing_columns(con, table):
    return {r[1] for r in con.execute(f'PRAGMA table_info({table})')}


def connect(path, kind):
    """kind: 'spectra', 'photometry' or 'state'."""
    con = sqlite3.connect(str(path), timeout=120)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA synchronous=NORMAL')
    if kind == 'state':
        con.executescript(schema.STATE)
        return con
    con.executescript(schema.FRAMES)
    have = _existing_columns(con, 'frames')
    for col, typ in list(schema.DERIVED_COLUMNS.items()) + [(c, t) for c, (_, t) in schema.HEADER_COLUMNS.items()]:
        if col not in have:
            con.execute(f'ALTER TABLE frames ADD COLUMN {col} {typ}')
    if 'date_utc' not in have:
        con.execute("UPDATE frames SET date_utc = datetime(date_obs)")
    if 'tel_key' not in have:   # backfill on migration
        con.executemany('UPDATE frames SET tel_key=? WHERE id=?',
                        [(tel_key(b), i) for i, b in con.execute('SELECT id, basename FROM frames')])
    if 'camera_type' not in have:   # backfill on migration
        con.executemany('UPDATE frames SET camera=?, camera_type=? WHERE id=?',
                        [(c, camera_type(c), i) for i, c in con.execute('SELECT id, instrument_id FROM frames')])
    con.execute('CREATE INDEX IF NOT EXISTS ix_frames_camera ON frames(camera, date_obs)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_frames_ava ON frames(ava_id, date_obs)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_frames_object ON frames(object)')
    con.executescript(schema.VIEWS)
    if 'candidate_ava_id' not in _existing_columns(con, 'target_link'):
        con.execute('ALTER TABLE target_link ADD COLUMN candidate_ava_id INTEGER')
    con.executescript(schema.SPECTRA_EXTRA if kind == 'spectra' else schema.PHOTOMETRY_EXTRA)
    con.commit()
    return con


def now():
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')


CAMERA_TYPES = {'fa': 'sinistro', 'fl': 'sinistro', 'fs': 'spectral', 'ep': 'muscat', 'kb': 'sbig', 'en': 'floyds'}


def camera_type(instrument_id):
    """Camera family from the instrument prefix; a new camera family shows up as 'unknown'."""
    return CAMERA_TYPES.get((instrument_id or '')[:2], 'unknown')


def tel_key(basename):
    return basename.split('-')[0][-5:]


def exp_key(basename):
    return '-'.join(basename.split('-')[:4])


def footprint_centre(area):
    """Mean of the polygon vertices on the unit sphere -> (ra, dec) in degrees."""
    try:
        pts = area['coordinates'][0][:-1]
    except (TypeError, KeyError, IndexError):
        return None, None
    if not pts:
        return None, None
    x = y = z = 0.0
    for ra, dec in pts:
        a, d = math.radians(ra), math.radians(dec)
        x += math.cos(d) * math.cos(a)
        y += math.cos(d) * math.sin(a)
        z += math.sin(d)
    ra = math.degrees(math.atan2(y, x)) % 360.0
    dec = math.degrees(math.atan2(z, math.hypot(x, y)))
    return ra, dec


def mjd(iso):
    t = datetime.strptime(iso[:19], '%Y-%m-%dT%H:%M:%S')
    frac = float('0' + iso[19:].rstrip('Z')) if len(iso) > 19 and iso[19] == '.' else 0.0
    return (t - datetime(1858, 11, 17)).total_seconds() / 86400.0 + frac / 86400.0


def frame_row(f, standard_names, standard_proposals):
    ra, dec = footprint_centre(f.get('area'))
    v = (f.get('version_set') or [{}])[0]
    obj = f.get('target_name') or ''
    norm = obj.upper().replace(' ', '').replace('_', '')
    is_std = int(f.get('configuration_type') == 'STANDARD'
                 or f.get('proposal_id') in standard_proposals
                 or norm in standard_names)
    return dict(
        id=f['id'], basename=f['basename'], exp_key=exp_key(f['basename']), tel_key=tel_key(f['basename']),
        filename=f.get('filename'), extension=v.get('extension'),
        proposal_id=f.get('proposal_id'), instrument_id=f.get('instrument_id'),
        camera=f.get('instrument_id'), camera_type=camera_type(f.get('instrument_id')),
        site_id=f.get('site_id'), telescope_id=f.get('telescope_id'),
        date_obs=f.get('observation_date'), day_obs=f.get('observation_day'),
        date_utc=(f.get('observation_date') or '')[:19].replace('T', ' ') or None,
        mjd_obs=mjd(f['observation_date']) if f.get('observation_date') else None,
        exptime=f.get('exposure_time'), filter=f.get('primary_optical_element'),
        obstype=f.get('configuration_type'), rlevel=f.get('reduction_level'),
        object=obj, ra=ra, dec=dec,
        block_id=f.get('observation_id'), request_id=f.get('request_id'),
        public_date=f.get('public_date'), version_id=v.get('id'), md5=v.get('md5'),
        related=json.dumps(f.get('related_frames') or []), is_standard=is_std,
    )


_MUTABLE = ('filename', 'extension', 'object', 'public_date', 'version_id', 'md5', 'related',
            'is_standard', 'ra', 'dec', 'exptime', 'filter', 'obstype')


def upsert_frames(con, rows):
    """Insert new frames, refresh mutable fields of known ones. Returns (n_new, n_updated)."""
    if not rows:
        return 0, 0
    ts = now()
    ids = [r['id'] for r in rows]
    known = {}
    for i in range(0, len(ids), 900):
        chunk = ids[i:i + 900]
        q = f"SELECT id, md5 FROM frames WHERE id IN ({','.join('?' * len(chunk))})"
        known.update({r[0]: r[1] for r in con.execute(q, chunk)})
    new = [r for r in rows if r['id'] not in known]
    old = [r for r in rows if r['id'] in known]
    if new:
        cols = list(new[0]) + ['first_seen', 'last_seen']
        con.executemany(f"INSERT INTO frames ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        [tuple(r.values()) + (ts, ts) for r in new])
    if old:
        sets = ','.join(f'{c}=?' for c in _MUTABLE)
        con.executemany(f'UPDATE frames SET {sets}, last_seen=? WHERE id=?',
                        [tuple(r[c] for c in _MUTABLE) + (ts, r['id']) for r in old])
        changed = [r['id'] for r in old if r['md5'] != known[r['id']]]   # new file version
        con.executemany('UPDATE frames SET header_status=0 WHERE id=?', [(i,) for i in changed])
    con.commit()
    return len(new), len(old)


def _coerce(value, typ):
    if value is None:
        return None
    if typ == 'INTEGER':
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
    if typ == 'REAL':
        try:
            x = float(value)
            return x if math.isfinite(x) else None
        except (TypeError, ValueError):
            return None
    s = str(value).strip()
    return None if s.upper() in ('', 'N/A', 'NA', 'UNKNOWN', 'NONE') else s


def header_values(hdr):
    return {col: _coerce(hdr.get(kw), typ) for col, (kw, typ) in schema.HEADER_COLUMNS.items()}


def store_header(con, frame_id, md5, hdr, store_full=True):
    vals = header_values(hdr)
    sets = ','.join(f'{c}=?' for c in vals)
    con.execute(f'UPDATE frames SET {sets}, header_status=1 WHERE id=?', tuple(vals.values()) + (frame_id,))
    if store_full:
        blob = zlib.compress(json.dumps(hdr, default=str).encode(), 6)
        con.execute('INSERT OR REPLACE INTO headers (frame_id, fetched_at, md5, header) VALUES (?,?,?,?)',
                    (frame_id, now(), md5, blob))


def load_header(con, frame_id):
    r = con.execute('SELECT header FROM headers WHERE frame_id=?', (frame_id,)).fetchone()
    return json.loads(zlib.decompress(r[0])) if r else None


def propagate_headers(con):
    """Frames without their own header take the values of their raw/product twin (same exp_key)."""
    cols = list(schema.HEADER_COLUMNS)
    sets = ','.join(f'{c}=(SELECT t.{c} FROM frames t WHERE t.exp_key=frames.exp_key '
                    f'AND t.header_status=1 ORDER BY t.rlevel DESC LIMIT 1)' for c in cols)
    cur = con.execute(f"""UPDATE frames SET {sets}, header_status=2
        WHERE header_status = 0 AND EXISTS (SELECT 1 FROM frames t
              WHERE t.exp_key=frames.exp_key AND t.header_status=1)""")
    con.execute("""UPDATE frames SET raw_id=(SELECT r.id FROM frames r WHERE r.exp_key=frames.exp_key
                   AND r.rlevel=0 LIMIT 1) WHERE rlevel>0 AND raw_id IS NULL""")
    con.commit()
    return cur.rowcount


def mark_best(con):
    """is_best = 1 for the highest reduction level of each exposure (L91 over L90 over raw)."""
    con.execute("""UPDATE frames SET is_best = (rlevel = (SELECT MAX(t.rlevel) FROM frames t
                   WHERE t.exp_key = frames.exp_key))""")
    con.commit()
