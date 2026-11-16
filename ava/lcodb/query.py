"""User-friendly, read-only access to the LCO spectra / photometry databases and the AVA target table.

    from lcodb import Archive
    a = Archive()                         # finds the databases from config.yaml

    a.find('fairall')                     # which AVA sources / LCO names match?
    a.summary('Fairall 9')                # one-page summary: properties, data, cadences, latest, papers
    ph = a.phot('Mrk 817', start='2024-01-01', filters='g', max_airmass=1.6)
    sp = a.spectra('NGC 4151', start='2023-01-01')     # science spectra + chosen standard + arc/flat
    a.overview()                          # one row per AVA source: data volume, cadence, last observation
    a.latest(days=7)                      # what was observed in the last week
    a.night('2026-11-10')                 # everything taken on one observing night
    a.cadence('Mrk 817', filters='g')     # visit cadence statistics
    a.seasons('Mrk 817')                  # observing seasons with start / end / cadence
    a.cameras('Fairall 9')                # which camera was on which telescope when (intercalibration groups)
    a.cone(20.94, -58.81, 60)             # what is near a position
    a.plot_coverage('Mrk 817')            # timeline of photometry and spectra

Targets can be given as an AVA id (int), AVA name ('Mrk 817', 'mrk817', 'MRK_817'), AVA data_id ('Mrk_817'),
any LCO target name ('Mrk%20817'), or a list of these. LCO names that are not AVA sources also work.
Dates can be 'YYYY-MM-DD[ HH:MM]', datetime / Timestamp, or an MJD (float). Every method returns a pandas
DataFrame (or a Summary, which prints nicely and is also a dict). Databases are opened read-only.
"""
import json
import sqlite3
import warnings
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .ava import norm
from .config import load_config

MJD0 = pd.Timestamp('1858-11-17')
FILTER_ALIASES = {'u': 'up', 'g': 'gp', 'r': 'rp', 'i': 'ip', 'z': 'zs', "u'": 'up', "g'": 'gp', "r'": 'rp',
                  "i'": 'ip', "z'": 'zs', 'zs': 'zs', 'b': 'B', 'v': 'V'}
PHOT_COLUMNS = ['id', 'basename', 'object', 'ava_id', 'date_utc', 'day_obs', 'mjd_obs', 'filter', 'exptime',
                'airmass', 'seeing', 'skymag', 'camera', 'camera_type', 'telid', 'site_id', 'proposal_id',
                'block_id', 'rlevel', 'naxis1', 'naxis2', 'pixscale', 'l1zp', 'moonfrac', 'moondist']
SPEC_COLUMNS = ['id', 'basename', 'object', 'ava_id', 'date_utc', 'day_obs', 'mjd_obs', 'exptime', 'airmass',
                'aperwid', 'instrument_id', 'site_id', 'proposal_id', 'block_id']


# ------------------------------------------------------------------ helpers
def to_mjd(x):
    """'2024-05-01', datetime, Timestamp or MJD -> MJD (float). None stays None."""
    if x is None:
        return None
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    t = pd.Timestamp(x)
    if t.tzinfo is not None:
        t = t.tz_convert('UTC').tz_localize(None)
    return (t - MJD0) / pd.Timedelta(days=1)


def mjd_to_date(m):
    return None if m is None or not np.isfinite(m) else (MJD0 + pd.Timedelta(days=float(m))).strftime('%Y-%m-%d')


def _list(x):
    if x is None:
        return None
    return list(x) if isinstance(x, (list, tuple, set, pd.Series, np.ndarray)) else [x]


def _filters(f):
    f = _list(f)
    return None if f is None else [FILTER_ALIASES.get(str(x).strip().lower(), x) if str(x).lower() in
                                   FILTER_ALIASES else x for x in f]


def _gaps(mjds):
    m = np.unique(np.round(np.sort(np.asarray(mjds, float)), 4))
    return np.diff(m)


def _cadence_stats(gaps):
    if len(gaps) == 0:
        return dict(n_gaps=0, median_d=np.nan, mean_d=np.nan, p10_d=np.nan, p90_d=np.nan, max_d=np.nan)
    return dict(n_gaps=len(gaps), median_d=float(np.median(gaps)), mean_d=float(np.mean(gaps)),
                p10_d=float(np.percentile(gaps, 10)), p90_d=float(np.percentile(gaps, 90)),
                max_d=float(np.max(gaps)))


NUMERIC = ['mjd_obs', 'exptime', 'airmass', 'seeing', 'skymag', 'naxis1', 'naxis2', 'pixscale', 'l1zp', 'l1fwhm',
           'agfwhm', 'moonfrac', 'moondist', 'aperwid', 'ava_id', 'std_id', 'std_aperwid', 'std_airmass',
           'std_dt_hours', 'arc_id', 'flat_id', 'arc_dt_hours', 'flat_dt_hours', 'l1zperr', 'wmscloud',
           'wmshumid', 'wmsskybr', 'moonalt', 'sunalt', 'altitude', 'azimuth', 'gain', 'rdnoise', 'saturate']


def _numeric(d):
    """Columns that are all NULL come back from SQLite as object dtype; make them float."""
    for c in NUMERIC:
        if c in d and d[c].dtype == object:
            d[c] = pd.to_numeric(d[c], errors='coerce')
    return d


def _sep_deg(ra1, de1, ra2, de2):
    r1, d1, r2, d2 = map(np.radians, (ra1, de1, ra2, de2))
    c = np.sin(d1) * np.sin(d2) + np.cos(d1) * np.cos(d2) * np.cos(r1 - r2)
    return np.degrees(np.arccos(np.clip(c, -1, 1)))


@dataclass
class Target:
    """A resolved target: an AVA source (ava_id set) or a plain LCO name."""
    query: object
    ava_id: int = None
    name: str = None
    data_id: str = None
    objects: list = field(default_factory=list)   # LCO target names that belong to it

    def __str__(self):
        return f'{self.name} (AVA {self.ava_id})' if self.ava_id is not None else f'{self.name} (not in AVA)'


class Summary(dict):
    """A dict that prints as a readable report (and as HTML in Jupyter)."""

    def _sections(self):
        for k, v in self.items():
            yield k, v

    def __str__(self):
        out = []
        for k, v in self._sections():
            if isinstance(v, pd.DataFrame):
                out.append(f'\n{k}:\n' + (v.to_string() if len(v) else '  (none)'))
            elif isinstance(v, pd.Series):
                out.append(f'{k:26s} <{len(v)} values; s[{k!r}]>')
            elif isinstance(v, dict):
                out.append(f'\n{k}:')
                out += [f'  {kk:24s} {vv}' for kk, vv in v.items()]
            else:
                out.append(f'{k:26s} {v}')
        return '\n'.join(out)

    __repr__ = __str__

    def _repr_html_(self):
        html = []
        for k, v in self._sections():
            if isinstance(v, pd.DataFrame):
                html.append(f'<h4>{k}</h4>' + (v.to_html() if len(v) else '<p>(none)</p>'))
            elif isinstance(v, pd.Series):
                html.append(f'<p><b>{k}</b>: {len(v)} values</p>')
            elif isinstance(v, dict):
                html.append(f'<h4>{k}</h4>' + pd.Series(v, dtype=object).to_frame('').to_html(header=False))
            else:
                html.append(f'<p><b>{k}</b>: {v}</p>')
        return '\n'.join(html)


# ------------------------------------------------------------------ the archive
warnings.filterwarnings('ignore', message='Mean of empty slice')
warnings.filterwarnings('ignore', message='All-NaN slice encountered')


class Archive:
    """Read-only access to spectra.sqlite, photometry.sqlite and AVA/ava.sqlite."""

    def __init__(self, config=None, spectra=None, photometry=None, ava=None):
        cfg = load_config(config)
        self.cfg = cfg
        paths = dict(spectra=spectra or cfg.db_path('spectra'), photometry=photometry or cfg.db_path('photometry'))
        if ava is None and cfg.get('ava', {}).get('csv'):
            ava = Path(cfg.resolve(cfg['ava']['csv'])).parent / 'ava.sqlite'
        if ava is not None:
            paths['ava'] = ava
        self.paths = {k: Path(v) for k, v in paths.items()}
        self._con = {}
        self._agn = None
        self._links = None

    # ---------------- low level
    def con(self, db):
        """sqlite3 connection (read-only) to 'spectra', 'photometry' or 'ava'."""
        if db not in self._con:
            p = self.paths.get(db)
            if p is None or not p.exists():
                raise FileNotFoundError(f'{db} database not found ({p}); for AVA run tools/ava_crossmatch.py')
            self._con[db] = sqlite3.connect(f'file:{p}?mode=ro', uri=True, check_same_thread=False)
        return self._con[db]

    def sql(self, query, db='photometry', params=()):
        """Run any SQL and get a DataFrame, e.g. a.sql('SELECT * FROM camera_epochs')."""
        return pd.read_sql(query, self.con(db), params=params)

    def tables(self, db='photometry'):
        """Tables and views of one database."""
        return self.sql("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name", db)

    def columns(self, table, db='photometry'):
        return self.sql(f'PRAGMA table_info({table})', db)[['name', 'type']]

    def close(self):
        for c in self._con.values():
            c.close()
        self._con = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __repr__(self):
        ok = {k: p.exists() for k, p in self.paths.items()}
        return 'Archive(' + ', '.join(f'{k}={"ok" if v else "missing"}' for k, v in ok.items()) + ')'

    # ---------------- targets
    def agn(self, columns=None):
        """The AVA table (original columns + recomputed LCO statistics, prefixed db_)."""
        if self._agn is None:
            try:
                self._agn = self.sql('SELECT * FROM agn_full', 'ava')
            except FileNotFoundError:
                self._agn = pd.DataFrame(columns=['id', 'name', 'data_id', 'ra_deg', 'dec_deg'])
        d = self._agn
        return d[columns].copy() if columns else d.copy()

    def links(self):
        """LCO target name -> AVA id (table target_link)."""
        if self._links is None:
            self._links = self.sql('SELECT * FROM target_link')
        return self._links.copy()

    def resolve(self, target):
        """Target (or list of them) from an AVA id, name, data_id or any LCO name."""
        if isinstance(target, Target):
            return target
        if isinstance(target, (list, tuple, set)):
            return [self.resolve(t) for t in target]
        agn, links = self.agn(), self.links()
        hit = None
        if isinstance(target, (int, np.integer)) or (isinstance(target, str) and target.strip().isdigit()):
            hit = agn[agn['id'] == int(target)]
        else:
            n = norm(str(target))
            keys = ['name', 'data_id', 'lco_id', 'simbad_name']
            m = np.zeros(len(agn), bool)
            for k in keys:
                if k in agn:
                    m |= agn[k].map(norm).values == n
            hit = agn[m]
            if hit.empty:   # an LCO name: linked to AVA, or a plain target
                L = links[links.object.map(norm) == n]
                if len(L) and L.ava_id.notna().any():
                    hit = agn[agn['id'] == int(L.ava_id.dropna().iloc[0])]
                elif len(L):
                    return Target(query=target, name=L.object.iloc[0], objects=list(L.object))
        if hit is None or hit.empty:
            raise KeyError(f'{target!r}: not an AVA source or LCO target name; try a.find({str(target)!r})')
        r = hit.iloc[0]
        i = int(r['id'])
        return Target(query=target, ava_id=i, name=r['name'], data_id=r.get('data_id'),
                      objects=sorted(links.loc[links.ava_id == i, 'object']))

    def find(self, text):
        """Substring / normalised-name search over AVA sources and LCO target names."""
        n = norm(text)
        agn, links = self.agn(), self.links()
        m = np.zeros(len(agn), bool)
        for k in ('name', 'data_id', 'lco_id', 'simbad_name'):
            if k in agn:
                m |= agn[k].map(norm).str.contains(n, regex=False).fillna(False).values
        a = agn.loc[m, ['id', 'name', 'data_id', 'ra', 'dec', 'redshift']].assign(kind='AVA')
        lk = links[links.object.map(norm).str.contains(n, regex=False)]
        b = lk[['object', 'ava_id', 'ava_name', 'n_phot', 'n_spec', 'matched_by']].assign(kind='LCO name')
        return pd.concat([a.rename(columns={'name': 'name'}), b.rename(columns={'object': 'name', 'ava_id': 'id'})],
                         ignore_index=True)

    def cone(self, ra, dec, radius_arcsec=60.0):
        """AVA sources and LCO target names within a radius of (ra, dec) in degrees."""
        agn, links = self.agn(), self.links()
        out = []
        if len(agn):
            s = _sep_deg(ra, dec, agn.ra_deg.astype(float), agn.dec_deg.astype(float)) * 3600
            a = agn.assign(sep_arcsec=s)[s <= radius_arcsec]
            out.append(a[['id', 'name', 'sep_arcsec', 'redshift']].assign(kind='AVA'))
        ok = links.obj_ra.notna()
        s = _sep_deg(ra, dec, links.obj_ra[ok], links.obj_dec[ok]) * 3600
        b = links[ok].assign(sep_arcsec=s)[s <= radius_arcsec]
        out.append(b[['object', 'ava_id', 'sep_arcsec', 'n_phot', 'n_spec']]
                   .rename(columns={'object': 'name', 'ava_id': 'id'}).assign(kind='LCO name'))
        return pd.concat(out, ignore_index=True).sort_values('sep_arcsec')

    def properties(self, target):
        """AVA properties of one source (Series)."""
        t = self.resolve(target)
        if t.ava_id is None:
            raise KeyError(f'{t.name} is not an AVA source')
        agn = self.agn()
        return agn[agn['id'] == t.ava_id].iloc[0]

    def citations(self, target):
        """Papers of one AVA source: citation text, ADS bibcode and link."""
        p = self.properties(target)
        names = str(p.get('cite_name') or '').split('|')
        urls = str(p.get('cite_url') or '').split('|')
        rows = []
        for i, n in enumerate(names):
            if not n.strip() or n == 'nan':
                continue
            b = urls[i].strip() if i < len(urls) and urls[i] != 'nan' else ''
            rows.append(dict(citation=n.strip(), bibcode=b or None,
                             ads=f'https://ui.adsabs.harvard.edu/abs/{b}/abstract' if b else None))
        return pd.DataFrame(rows, columns=['citation', 'bibcode', 'ads'])

    # ---------------- data
    def _where_target(self, target, alias=''):
        if target is None:
            return '', []
        ts = self.resolve(target)
        ts = ts if isinstance(ts, list) else [ts]
        ids = [t.ava_id for t in ts if t.ava_id is not None]
        objs = [o for t in ts if t.ava_id is None for o in t.objects]
        parts, params = [], []
        if ids:
            parts.append(f"{alias}ava_id IN ({','.join('?' * len(ids))})")
            params += ids
        if objs:
            parts.append(f"{alias}object IN ({','.join('?' * len(objs))})")
            params += objs
        return '(' + ' OR '.join(parts) + ')', params

    @staticmethod
    def _range(start, end, alias=''):
        w, p = [], []
        if start is not None:
            w.append(f'{alias}mjd_obs >= ?')
            p.append(to_mjd(start))
        if end is not None:
            w.append(f'{alias}mjd_obs < ?')
            p.append(to_mjd(end))
        return w, p

    def phot(self, target=None, start=None, end=None, filters=None, camera=None, telescope=None, site=None,
             proposal=None, max_airmass=None, max_seeing=None, min_exptime=None, columns=None, limit=None):
        """Photometric images (one row per exposure, BANZAI L91 or the old pipeline when no L91 exists).

        filters: 'g' / 'gp' / ['B','V']; camera: 'fa14' or a type ('sinistro','spectral','muscat');
        telescope: '1m010'; site: 'coj'; seeing in arcsec (needs headers); columns: list or 'all'."""
        w, p = ['is_best = 1'], []
        wt, pt = self._where_target(target)
        if wt:
            w.append(wt)
            p += pt
        wr, pr = self._range(start, end)
        w += wr
        p += pr
        for col, val in (('filter', _filters(filters)), ('telid', _list(telescope)), ('site_id', _list(site)),
                         ('proposal_id', _list(proposal))):
            if val:
                w.append(f"{'tel_key' if col == 'telid' else col} IN ({','.join('?' * len(val))})")
                p += list(val)
        if camera:
            cams = _list(camera)
            types = [c for c in cams if c in ('sinistro', 'spectral', 'muscat')]
            ids = [c for c in cams if c not in types]
            parts = []
            if types:
                parts.append(f"camera_type IN ({','.join('?' * len(types))})")
                p += types
            if ids:
                parts.append(f"camera IN ({','.join('?' * len(ids))})")
                p += ids
            w.append('(' + ' OR '.join(parts) + ')')
        if max_airmass is not None:
            w.append('COALESCE(airmass, airmass_calc) <= ?')
            p.append(max_airmass)
        if max_seeing is not None:
            w.append('COALESCE(CASE WHEN l1fwhm > 0 THEN l1fwhm END, agfwhm) <= ?')
            p.append(max_seeing)
        if min_exptime is not None:
            w.append('exptime >= ?')
            p.append(min_exptime)
        sel = ('*, COALESCE(airmass, airmass_calc) AS airmass_best, '
               'COALESCE(CASE WHEN l1fwhm > 0 THEN l1fwhm END, agfwhm) AS seeing_best, tel_key AS telid')
        q = f"SELECT {sel} FROM frames WHERE {' AND '.join(w)} ORDER BY mjd_obs" + (f' LIMIT {int(limit)}' if limit else '')
        d = self.sql(q, 'photometry', p)
        d['airmass'] = d.pop('airmass_best')
        d['seeing'] = d.pop('seeing_best')
        _numeric(d)
        d.loc[d.skymag == 22.0, 'skymag'] = np.nan   # telemetry placeholder
        d['date_utc'] = pd.to_datetime(d.date_utc)
        if columns != 'all':
            d = d[[c for c in (columns or PHOT_COLUMNS) if c in d]]
        return d.reset_index(drop=True)

    def spectra(self, target=None, start=None, end=None, slit=None, proposal=None, standards=False,
                with_standard=True, with_calibs=True, columns=None):
        """Raw FLOYDS science spectra (one row per exposure), with the selected flux standard
        (same slit, else nearest 2", else nearest; std_choice says which), the best arc and lamp flat, and the
        BANZAI 1d product name when one exists. standards=True returns the standard-star spectra instead."""
        w, p = ["s.rlevel = 0", "s.obstype = 'SPECTRUM'", f"s.is_standard = {1 if standards else 0}"], []
        wt, pt = self._where_target(target, 's.')
        if wt:
            w.append(wt)
            p += pt
        wr, pr = self._range(start, end, 's.')
        w += wr
        p += pr
        if slit is not None:
            w.append('ABS(s.aperwid - ?) < 0.05')
            p.append(float(slit))
        if proposal:
            pr_ = _list(proposal)
            w.append(f"s.proposal_id IN ({','.join('?' * len(pr_))})")
            p += pr_
        sel = ['s.*', 'COALESCE(s.airmass, s.airmass_calc) AS airmass_best', 'x.product_filename AS product_1d']
        join = "LEFT JOIN exposures x ON x.id = s.id"
        if with_standard and not standards:
            sel += ['st.std_id', 'st.std_basename', 'st.std_object', 'st.std_aperwid', 'st.std_airmass',
                    'st.dt_hours AS std_dt_hours', 'st.same_block AS std_same_block', 'st.std_choice']
            join += ' LEFT JOIN spectrum_standards st ON st.sci_id = s.id'
        if with_calibs:
            sel += ['c.arc_id', 'c.arc_basename', 'c.arc_dt_hours', 'c.arc_same_block',
                    'c.flat_id', 'c.flat_basename', 'c.flat_dt_hours', 'c.flat_same_block']
            join += ' LEFT JOIN spectrum_calibs c ON c.spec_id = s.id'
        q = f"SELECT {', '.join(sel)} FROM frames s {join} WHERE {' AND '.join(w)} ORDER BY s.mjd_obs"
        d = self.sql(q, 'spectra', p)
        d['airmass'] = d.pop('airmass_best')
        _numeric(d)
        d['date_utc'] = pd.to_datetime(d.date_utc)
        if columns == 'all':
            return d
        extra = [c for c in d.columns if c.startswith(('std_', 'arc_', 'flat_')) or c == 'product_1d']
        keep = (columns or SPEC_COLUMNS + extra)
        return d[[c for c in keep if c in d]].reset_index(drop=True)

    def standards(self, name=None, start=None, end=None, slit=None):
        """Standard-star spectra, optionally one star ('EG21', 'Feige 110' ...)."""
        d = self.spectra(None, start, end, slit=slit, standards=True, with_standard=False)
        if name:
            d = d[d.object.map(norm) == norm(name)]
        return d.reset_index(drop=True)

    def calibs(self, spec_id, n=3):
        """All matched arcs and lamp flats of one spectrum (ranked)."""
        return self.sql("""SELECT m.obstype, m.rank, m.calib_id, f.basename, m.dt_hours, m.same_block, m.same_slit,
                           m.calib_aperwid FROM calib_match m JOIN frames f ON f.id = m.calib_id
                           WHERE m.spec_id = ? AND m.rank <= ? ORDER BY m.obstype, m.rank""", 'spectra', (spec_id, n))

    def header(self, frame_id):
        """Full FITS header of a frame (dict), from whichever database has it."""
        for db in ('spectra', 'photometry'):
            r = self.con(db).execute('SELECT header FROM headers WHERE frame_id=?', (int(frame_id),)).fetchone()
            if r:
                return json.loads(zlib.decompress(r[0]))
        raise KeyError(f'no stored header for frame {frame_id}')

    # ---------------- statistics
    def _visits(self, d, key='block_id'):
        """One row per visit (observing block): start MJD, filters, n frames."""
        if d.empty:
            return d
        g = d.groupby(key)
        v = pd.DataFrame({'mjd': g.mjd_obs.min(), 'n': g.size()})
        if 'filter' in d:
            v['filters'] = g['filter'].agg(lambda s: ','.join(sorted(set(s))))
        return v.sort_values('mjd')

    def cadence(self, target, kind='phot', filters=None, start=None, end=None, by='visit'):
        """Cadence statistics (days). by='visit' (one point per observing block) or 'night'.
        kind='phot' or 'spec'. Returns a Summary with the stats and the gaps."""
        d = self.phot(target, start, end, filters) if kind == 'phot' else self.spectra(target, start, end,
                                                                                       with_standard=False,
                                                                                       with_calibs=False)
        if by == 'night':
            t = d.groupby('day_obs').mjd_obs.min().values
        else:
            t = self._visits(d).mjd.values if len(d) else []
        g = _gaps(t)
        s = Summary(target=str(self.resolve(target)), kind=kind, filters=','.join(_filters(filters) or ['all']),
                    points=len(t))
        s.update(_cadence_stats(g))
        s['gaps'] = pd.Series(g, name='gap_d')
        return s

    def seasons(self, target, kind='phot', gap_days=60, filters=None):
        """Observing seasons: runs of visits separated by less than gap_days."""
        d = self.phot(target, filters=filters) if kind == 'phot' else self.spectra(target, with_standard=False,
                                                                                    with_calibs=False)
        v = self._visits(d)
        if v.empty:
            return pd.DataFrame(columns=['season', 'start', 'end', 'days', 'visits', 'frames', 'median_cadence_d'])
        t = v.mjd.values
        sid = np.concatenate([[0], np.cumsum(np.diff(t) > gap_days)])
        rows = []
        for k in np.unique(sid):
            tt, nn = t[sid == k], v.n.values[sid == k]
            rows.append(dict(season=int(k) + 1, start=mjd_to_date(tt.min()), end=mjd_to_date(tt.max()),
                             days=round(tt.max() - tt.min(), 1), visits=len(tt), frames=int(nn.sum()),
                             median_cadence_d=round(float(np.median(np.diff(tt))), 3) if len(tt) > 1 else np.nan))
        return pd.DataFrame(rows)

    def cameras(self, target=None):
        """Which camera was on which telescope, and when (the intercalibration groups), optionally for one target."""
        if target is None:
            return self.sql('SELECT * FROM camera_epochs ORDER BY camera, first_utc')
        d = self.phot(target)
        if d.empty:
            return pd.DataFrame()
        g = d.groupby(['camera', 'camera_type', 'site_id', 'telid'])
        out = g.agg(first=('date_utc', 'min'), last=('date_utc', 'max'), images=('id', 'size'),
                    filters=('filter', lambda s: ','.join(sorted(set(s)))))
        return out.reset_index().sort_values('first').reset_index(drop=True)

    def quality(self, target=None, filters=None, start=None, end=None, by=('filter',)):
        """Median / percentile airmass, seeing and exposure time per filter (or other columns)."""
        d = self.phot(target, start, end, filters)
        if d.empty:
            return pd.DataFrame()
        by = list(by) if isinstance(by, (list, tuple)) else [by]
        g = d.groupby(by)
        return pd.DataFrame({
            'images': g.size(), 'exptime_med': g.exptime.median(),
            'airmass_med': g.airmass.median(), 'airmass_p90': g.airmass.quantile(0.9),
            'seeing_med': g.seeing.median(), 'seeing_p90': g.seeing.quantile(0.9),
            'seeing_known': g.seeing.count()}).round(2)

    def latest(self, target=None, days=None, n=20, kind='both'):
        """Most recent observations: last n visits (or everything in the last `days`), photometry and spectra."""
        start = None if days is None else to_mjd(pd.Timestamp.utcnow().tz_localize(None)) - days
        out = []
        if kind in ('both', 'phot'):
            d = self.phot(target, start=start)
            if len(d):
                g = d.groupby('block_id')
                out.append(pd.DataFrame({'kind': 'phot', 'date_utc': g.date_utc.min(), 'object': g.object.first(),
                                         'ava_id': g.ava_id.first(), 'site': g.site_id.first(),
                                         'telescope': g.telid.first(), 'camera': g.camera.first(),
                                         'filters': g['filter'].agg(lambda s: ','.join(sorted(set(s)))),
                                         'frames': g.size(), 'airmass': g.airmass.median().round(2)}))
        if kind in ('both', 'spec'):
            d = self.spectra(target, start=start, with_standard=False, with_calibs=False)
            if len(d):
                g = d.groupby('block_id')
                out.append(pd.DataFrame({'kind': 'spec', 'date_utc': g.date_utc.min(), 'object': g.object.first(),
                                         'ava_id': g.ava_id.first(), 'site': g.site_id.first(),
                                         'telescope': g.instrument_id.first(), 'camera': g.instrument_id.first(),
                                         'filters': g.aperwid.first().map(lambda w: f'{w:g}" slit' if w == w else ''),
                                         'frames': g.size(), 'airmass': g.airmass.median().round(2)}))
        if not out:
            return pd.DataFrame()
        r = pd.concat(out).sort_values('date_utc', ascending=False).reset_index(drop=True)
        r['ava_id'] = r.ava_id.astype('Int64')
        return r if days is not None else r.head(n)

    def night(self, day_obs, kind='both'):
        """Everything observed on one observing night (day_obs = 'YYYY-MM-DD', the LCO night label)."""
        d0 = pd.Timestamp(day_obs).strftime('%Y-%m-%d')
        out = []
        if kind in ('both', 'phot'):
            d = self.sql("SELECT object, ava_id, filter, site_id, tel_key AS telid, camera, COUNT(*) AS frames, "
                         "MIN(date_utc) AS first, MAX(date_utc) AS last FROM frames WHERE is_best=1 AND day_obs=? "
                         "GROUP BY object, ava_id, filter, site_id, tel_key, camera ORDER BY first",
                         'photometry', (d0,))
            out.append(d.assign(kind='phot'))
        if kind in ('both', 'spec'):
            d = self.sql("SELECT object, ava_id, obstype AS filter, site_id, instrument_id AS telid, "
                         "instrument_id AS camera, COUNT(*) AS frames, MIN(date_utc) AS first, MAX(date_utc) AS last "
                         "FROM frames WHERE rlevel=0 AND day_obs=? GROUP BY object, ava_id, obstype, site_id, "
                         "instrument_id ORDER BY first", 'spectra', (d0,))
            out.append(d.assign(kind='spec'))
        r = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
        if len(r):
            r['ava_id'] = pd.to_numeric(r.ava_id, errors='coerce').astype('Int64')
        return r

    def overview(self, sort='last_obs'):
        """One row per AVA source: data volume, date range, visit cadences, days since the last observation."""
        ph = self.sql("SELECT ava_id, block_id, MIN(mjd_obs) AS mjd, COUNT(*) AS n FROM frames "
                      "WHERE is_best=1 AND ava_id IS NOT NULL GROUP BY ava_id, block_id", 'photometry')
        sp = self.sql("SELECT ava_id, block_id, MIN(mjd_obs) AS mjd, COUNT(*) AS n FROM frames WHERE rlevel=0 "
                      "AND obstype='SPECTRUM' AND is_standard=0 AND ava_id IS NOT NULL GROUP BY ava_id, block_id",
                      'spectra')
        now = to_mjd(pd.Timestamp.utcnow().tz_localize(None))
        agn = self.agn(['id', 'name', 'redshift'])
        rows = []
        for r in agn.itertuples():
            a, b = ph[ph.ava_id == r.id], sp[sp.ava_id == r.id]
            last = max([x for x in (a.mjd.max(), b.mjd.max()) if x == x], default=np.nan)
            rows.append(dict(
                ava_id=r.id, name=r.name, z=r.redshift,
                phot_images=int(a.n.sum()), phot_visits=len(a),
                phot_first=mjd_to_date(a.mjd.min()) if len(a) else None,
                phot_last=mjd_to_date(a.mjd.max()) if len(a) else None,
                phot_cadence_d=_cadence_stats(_gaps(a.mjd))['median_d'],
                spec_frames=int(b.n.sum()), spec_epochs=len(b),
                spec_first=mjd_to_date(b.mjd.min()) if len(b) else None,
                spec_last=mjd_to_date(b.mjd.max()) if len(b) else None,
                spec_cadence_d=_cadence_stats(_gaps(b.mjd))['median_d'],
                last_obs=mjd_to_date(last), days_since_last=round(now - last, 1) if last == last else np.nan))
        o = pd.DataFrame(rows)
        if sort == 'last_obs':
            o = o.sort_values('days_since_last', na_position='last')
        elif sort:
            o = o.sort_values(sort)
        return o.reset_index(drop=True).round({'phot_cadence_d': 3, 'spec_cadence_d': 2})

    def summary(self, target):
        """One-page summary of a target: identifiers, properties, data, cadences, seasons, cameras, latest, papers."""
        t = self.resolve(target)
        s = Summary()
        s['target'] = str(t)
        s['LCO names'] = ', '.join(t.objects) or '-'
        if t.ava_id is not None:
            p = self.properties(t)
            props = {k: p.get(k) for k in ('ra', 'dec', 'redshift', 'ebv', 'AGN_type', 'logm', 'logl', 'ledd',
                                           'avg_g', 'PI', 'Comments') if k in p and pd.notna(p.get(k))}
            s['properties'] = props
        ph = self.phot(t)
        sp = self.spectra(t, with_calibs=False)
        if len(ph):
            v = self._visits(ph)
            c = _cadence_stats(_gaps(v.mjd))
            s['photometry'] = {
                'images': f'{len(ph):,}', 'visits': f'{len(v):,}',
                'range': f'{ph.day_obs.min()} .. {ph.day_obs.max()}',
                'cadence (median visit gap)': f"{c['median_d']:.2f} d  (10-90%: {c['p10_d']:.2f}-{c['p90_d']:.2f} d)",
                'filters': ', '.join(f'{k}:{n}' for k, n in ph['filter'].value_counts().items()),
                'cameras': ', '.join(f'{k}:{n}' for k, n in ph.camera.value_counts().items()),
                'sites': ', '.join(f'{k}:{n}' for k, n in ph.site_id.value_counts().items()),
                'proposals': ', '.join(sorted(ph.proposal_id.unique())),
                'median airmass': f'{ph.airmass.median():.2f}',
                'median seeing': f'{ph.seeing.median():.2f}"' if ph.seeing.notna().any() else 'n/a (no headers)'}
            s['photometric seasons'] = self.seasons(t)
        else:
            s['photometry'] = 'none'
        if len(sp):
            e = self._visits(sp)
            c = _cadence_stats(_gaps(e.mjd))
            s['spectroscopy'] = {
                'spectra': f'{len(sp):,}', 'epochs': f'{len(e):,}',
                'range': f'{sp.day_obs.min()} .. {sp.day_obs.max()}',
                'cadence (median epoch gap)': f"{c['median_d']:.2f} d" if c['n_gaps'] else '-',
                'slits': ', '.join(f'{k:g}":{n}' for k, n in sp.aperwid.value_counts().items()) or 'unknown',
                'spectrographs': ', '.join(f'{k}:{n}' for k, n in sp.instrument_id.value_counts().items()),
                'standard choice': ', '.join(f'{k}:{n}' for k, n in sp.std_choice.fillna('none').value_counts().items()),
                'median |dt| to standard': f'{sp.std_dt_hours.abs().median():.1f} h' if sp.std_dt_hours.notna().any() else '-',
                'BANZAI 1d products': f'{sp.product_1d.notna().sum():,}'}
        else:
            s['spectroscopy'] = 'none'
        s['latest visits'] = self.latest(t, n=8)
        if t.ava_id is not None:
            s['papers'] = self.citations(t)[['citation', 'bibcode']]
        return s

    # ---------------- live archive (optional, needs network; a few requests only)
    def new_in_archive(self, target, days=7):
        """Frames of a target in the LCO archive from the last `days` that are not yet in the local databases
        (i.e. arrived since the last daily sync). Uses the API token from config.yaml; a few requests per
        LCO name, rate-limited. Run `lcodb daily` to ingest them."""
        from .api import Client
        t = self.resolve(target)
        c = Client(self.cfg.token, self.cfg.get('request_timeout', 120), 2, rate_per_s=2)
        end = datetime.now(timezone.utc).replace(tzinfo=None)
        start = end - pd.Timedelta(days=days).to_pytimedelta()
        rows = []
        for name in (t.objects or [t.name]):
            for f in c.frames(start, end, page_size=1000 if self.cfg.token else 100, target_name=name,
                              exclude_OBSTYPE=self.cfg.get('exclude_obstypes', [])):
                rows.append(dict(id=f['id'], basename=f['basename'], object=f.get('target_name'),
                                 date_obs=f.get('observation_date'), obstype=f.get('configuration_type'),
                                 rlevel=f.get('reduction_level'), filter=f.get('primary_optical_element'),
                                 instrument=f.get('instrument_id'), site=f.get('site_id'),
                                 proposal=f.get('proposal_id')))
        d = pd.DataFrame(rows)
        if d.empty:
            return d
        have = set()
        for db in ('spectra', 'photometry'):
            ids = d.id.tolist()
            q = f"SELECT id FROM frames WHERE id IN ({','.join('?' * len(ids))})"
            have |= {r[0] for r in self.con(db).execute(q, ids)}
        return d[~d.id.isin(have)].sort_values('date_obs').reset_index(drop=True)

    # ---------------- plots
    def plot_coverage(self, target, ax=None, filters=None):
        """Timeline: one row per filter (photometry visits) plus a row for spectra."""
        import matplotlib.pyplot as plt
        t = self.resolve(target)
        ph = self.phot(t, filters=filters)
        sp = self.spectra(t, with_standard=False, with_calibs=False)
        rows = sorted(ph['filter'].unique(), key=lambda f: 'up gp rp ip zs U B V R I Y'.split().index(f)
                      if f in 'up gp rp ip zs U B V R I Y'.split() else 99)
        if ax is None:
            _, ax = plt.subplots(figsize=(10, 0.35 * (len(rows) + 1) + 1.2))
        for k, f in enumerate(rows):
            d = ph[ph['filter'] == f]
            ax.plot(d.date_utc, np.full(len(d), k), '|', ms=10, color='#2a78d6')
        if len(sp):
            ax.plot(sp.date_utc, np.full(len(sp), len(rows)), '|', ms=10, color='#eb6834')
        ax.set_yticks(range(len(rows) + (1 if len(sp) else 0)))
        ax.set_yticklabels(rows + (['FLOYDS'] if len(sp) else []))
        ax.set_ylim(-0.7, len(rows) + 0.7)
        ax.set_title(str(t))
        ax.grid(axis='x', alpha=0.3)
        return ax

    def plot_cadence(self, target, kind='phot', filters=None, ax=None):
        """Histogram of the gaps between visits (log scale)."""
        import matplotlib.pyplot as plt
        c = self.cadence(target, kind, filters)
        if ax is None:
            _, ax = plt.subplots(figsize=(6, 3.5))
        g = c['gaps'][c['gaps'] > 0]
        if len(g):
            ax.hist(g, bins=np.logspace(np.log10(max(g.min(), 1e-3)), np.log10(g.max()) + 0.01, 40), color='#2a78d6')
            ax.set_xscale('log')
            ax.axvline(c['median_d'], color='#eb6834', lw=2, label=f"median {c['median_d']:.2f} d")
            ax.legend(frameon=False)
        ax.set_xlabel('gap between visits (d)')
        ax.set_ylabel('number')
        ax.set_title(f"{c['target']} - {kind}")
        return ax
