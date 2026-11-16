"""Offline tests (no network): python -m pytest tests"""
from datetime import datetime

import pytest

from ava.lcodb import calibs, db, ingest, standards
from ava.lcodb.config import load_config


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c.raw['db_dir'] = str(tmp_path)
    return c


@pytest.fixture
def cons(cfg):
    return {k: db.connect(cfg.db_path(k), k) for k in ('spectra', 'photometry')}, db.connect(cfg.db_dir / 'state.sqlite', 'state')


def frame(i, basename, inst='en12', obstype='SPECTRUM', rlevel=0, obj='Fairall9', prop='KEY2026B-007',
          date='2026-10-10T12:00:00.000Z', block=1, md5='a', ra=20.9):
    return {'id': i, 'basename': basename, 'filename': basename + '.fits.fz', 'proposal_id': prop,
            'instrument_id': inst, 'site_id': 'coj', 'telescope_id': '2m0a', 'observation_date': date,
            'observation_day': date[:10], 'exposure_time': 600.0, 'primary_optical_element': 'air',
            'configuration_type': obstype, 'reduction_level': rlevel, 'target_name': obj,
            'observation_id': block, 'request_id': 9, 'public_date': date,
            'version_set': [{'id': i * 10, 'md5': md5, 'extension': '.fits.fz'}], 'related_frames': [],
            'area': {'type': 'Polygon', 'coordinates': [[[ra - .01, -58.8], [ra + .01, -58.8], [ra + .01, -58.79],
                                                          [ra - .01, -58.79], [ra - .01, -58.8]]]}}


def test_name_variants():
    assert ingest.name_variants('Feige110') == {'FEIGE110', 'FEIGE 110'}
    assert 'BD+28 4211' in ingest.name_variants('BD+284211')


def test_footprint_wraps_ra():
    ra, dec = db.footprint_centre({'coordinates': [[[359.9, 0], [0.1, 0], [0.1, 0.1], [359.9, 0.1], [359.9, 0]]]})
    assert min(ra, 360 - ra) < 1e-6 and abs(dec - 0.05) < 1e-3


def test_exp_key_links_raw_and_products():
    assert db.exp_key('coj2m002-en12-20261010-0006-e00') == db.exp_key('coj2m002-en12-20261010-0006-e91-1d')


def test_classify(cfg):
    assert ingest.classify('en12', cfg) == 'spectra'
    assert ingest.classify('fa19', cfg) == 'photometry'
    assert ingest.classify('sd04', cfg) == 'ignore'
    assert ingest.classify('nrs01', cfg) == 'ignore'
    assert ingest.classify('fl12', cfg) == 'photometry'
    assert ingest.classify('zz01', cfg) is None


def test_router_and_upsert(cfg, cons):
    c, state = cons
    r = ingest.Router(cfg, c, state)
    r.add(frame(1, 'coj2m002-en12-20261010-0006-e00'))
    r.add(frame(2, 'coj1m011-fa12-20261010-0100-e91', inst='fa12', obstype='EXPOSE', rlevel=91))
    r.add(frame(6, 'coj1m011-fa12-20261010-0100-e00', inst='fa12', obstype='EXPOSE'))   # raw photometry: dropped
    r.add(frame(7, 'ogg2m001-nrs01-20261010-0100-e00', inst='nrs01'))                  # NRES: dropped
    r.add(frame(3, 'coj2m002-sd04-20261010-0001-x00', inst='sd04'))
    r.add(frame(4, 'coj2m002-zz01-20261010-0001-e00', inst='zz01'))
    r.add(frame(5, 'coj2m002-en12-20261010-0006-e90', rlevel=90))   # level not kept
    r.flush()
    assert c['spectra'].execute('SELECT COUNT(*) FROM frames').fetchone()[0] == 1
    assert c['photometry'].execute('SELECT COUNT(*) FROM frames').fetchone()[0] == 1
    assert state.execute('SELECT n_frames FROM unknown_instruments').fetchone()[0] == 1
    # same frame again with a new file version -> header must be refetched
    c['spectra'].execute('UPDATE frames SET header_status=1')
    n, u = db.upsert_frames(c['spectra'], [db.frame_row(frame(1, 'coj2m002-en12-20261010-0006-e00', md5='b'), set(), set())])
    assert (n, u) == (0, 1)
    assert c['spectra'].execute('SELECT header_status FROM frames').fetchone()[0] == 0


def test_headers_store_and_propagate(cfg, cons):
    con = cons[0]['spectra']
    db.upsert_frames(con, [db.frame_row(frame(1, 'coj2m002-en12-20261010-0006-e00'), set(), set()),
                           db.frame_row(frame(2, 'coj2m002-en12-20261010-0006-e91-1d', rlevel=91), set(), set())])
    db.store_header(con, 2, 'a', {'AIRMASS': '1.234', 'APERWID': 6.0, 'MOONDIST': 'N/A', 'GROUPID': 'F9 rm'})
    assert db.propagate_headers(con) == 1
    r = con.execute('SELECT airmass, aperwid, moondist, groupid, header_status FROM frames WHERE id=1').fetchone()
    assert tuple(r) == (1.234, 6.0, None, 'F9 rm', 2)
    assert con.execute('SELECT raw_id FROM frames WHERE id=2').fetchone()[0] == 1
    assert db.load_header(con, 2)['GROUPID'] == 'F9 rm'
    e = con.execute('SELECT id, product_id, airmass_best FROM exposures').fetchone()
    assert tuple(e) == (1, 2, 1.234)


def test_std_match_prefers_same_block_then_time(cfg, cons):
    con = cons[0]['spectra']
    names = {'FEIGE110', 'EG21'}
    rows = [frame(1, 'coj2m002-en12-20261010-0006-e00', block=10),
            frame(2, 'coj2m002-en12-20261010-0007-e00', obj='EG21', block=10, date='2026-10-10T20:00:00Z'),
            frame(3, 'coj2m002-en12-20261010-0008-e00', obj='Feige 110', block=11, date='2026-10-10T12:30:00Z',
                  prop='COJ_calib'),
            frame(4, 'ogg2m001-en06-20261010-0008-e00', inst='en06', obj='Feige110', block=12),  # other spectrograph
            frame(5, 'coj2m002-en12-20261201-0008-e00', obj='EG21', block=13, date='2026-12-01T12:00:00Z')]  # too late
    db.upsert_frames(con, [db.frame_row(f, names, set()) for f in rows])
    nsci, nrow = standards.rebuild(con, n_nearest=5, max_dt_days=30)
    got = con.execute('SELECT std_id, rank, same_block FROM std_match ORDER BY rank').fetchall()
    assert (nsci, [tuple(g) for g in got]) == (1, [(2, 1, 1), (3, 2, 0)])


def test_semester_start():
    assert ingest.semester_start('KEY2023B-001f') == datetime(2023, 7, 1)
    assert ingest.semester_start('KEY2017AB-001') == datetime(2017, 1, 1)


def test_std_match_keeps_each_slit(cfg, cons):
    con = cons[0]['spectra']
    rows = [frame(1, 'coj2m002-en12-20261010-0006-e00', block=10)] + [
        frame(10 + k, f'coj2m002-en12-20261010-00{10 + k}-e00', obj='EG21', block=20 + k,
              date=f'2026-10-10T{12 + k:02d}:10:00Z') for k in range(4)]
    db.upsert_frames(con, [db.frame_row(f, {'EG21'}, set()) for f in rows])
    for k in range(4):   # three 2" standards close in time, one 6" further away
        db.store_header(con, 10 + k, 'a', {'APERWID': 6.0 if k == 3 else 2.0})
    db.store_header(con, 1, 'a', {'APERWID': 6.0})
    standards.rebuild(con, n_nearest=2, max_dt_days=30)
    got = con.execute('SELECT std_id, same_slit FROM std_match ORDER BY rank').fetchall()
    assert [tuple(g) for g in got] == [(10, 0), (11, 0), (13, 1)]


def test_calib_match_block_then_slit_then_time(cfg, cons):
    con = cons[0]['spectra']
    rows = [frame(1, 'coj2m002-en12-20261010-0006-e00', block=10, date='2026-10-10T12:00:00Z'),
            frame(2, 'coj2m002-en12-20261010-0005-e00', obstype='ARC', block=10, date='2026-10-10T11:50:00Z'),
            frame(3, 'coj2m002-en12-20261010-0004-e00', obstype='ARC', block=9, date='2026-10-10T12:01:00Z'),
            frame(4, 'coj2m002-en12-20261010-0003-e00', obstype='ARC', block=8, date='2026-10-10T12:30:00Z'),
            frame(5, 'coj2m002-en12-20261010-0007-e00', obstype='LAMPFLAT', block=10, date='2026-10-10T12:10:00Z'),
            frame(6, 'ogg2m001-en06-20261010-0007-e00', inst='en06', obstype='ARC', block=10)]  # other spectrograph
    db.upsert_frames(con, [db.frame_row(f, set(), set()) for f in rows])
    for i, w in [(1, 6.0), (2, 6.0), (3, 2.0), (4, 6.0), (5, 6.0)]:
        db.store_header(con, i, 'a', {'APERWID': w})
    nspec, nrow = calibs.rebuild(con, n_nearest=3, max_dt_days=7)
    got = con.execute("SELECT calib_id, obstype, rank, same_block, same_slit FROM calib_match "
                      "ORDER BY obstype, rank").fetchall()
    # ARC: same block (2) > same slit (4, 30 min) > other slit (3, 1 min)
    assert [tuple(g) for g in got] == [(2, 'ARC', 1, 1, 1), (4, 'ARC', 2, 0, 1), (3, 'ARC', 3, 0, 0),
                                       (5, 'LAMPFLAT', 1, 1, 1)]
    v = con.execute('SELECT arc_id, flat_id FROM spectrum_calibs WHERE spec_id=1').fetchone()
    assert tuple(v) == (2, 5)


def test_l90_fallback_and_quality_view(cfg, cons):
    c, state = cons
    con = c['photometry']
    r = ingest.Router(cfg, c, state)
    kw = dict(inst='fl04', obstype='EXPOSE', obj='Mrk841')
    r.add(frame(1, 'lsc1m004-fl04-20160308-0119-e90', rlevel=90, **kw))   # only L90 -> best
    r.add(frame(2, 'lsc1m004-fl04-20160308-0120-e90', rlevel=90, **kw))   # L90 and L91 -> L91 best
    r.add(frame(3, 'lsc1m004-fl04-20160308-0120-e91', rlevel=91, **kw))
    r.flush()
    db.mark_best(con)
    best = [row[0] for row in con.execute('SELECT id FROM frames WHERE is_best=1 ORDER BY id')]
    assert best == [1, 3]
    from ava.lcodb import headers
    assert sorted(x['id'] for x in headers.pending(con, [90, 91], best_only=True)) == [1, 3]
    db.store_header(con, 3, 'a', {'NAXIS1': 4096, 'NAXIS2': '4096', 'PIXSCALE': 0.389, 'SKYMAG': 20.1,
                                  'AIRMASS': 1.3, 'FILTER': 'V'})
    q = con.execute('SELECT telid, naxis1, naxis2, pixscale, observatory, airmass FROM image_quality WHERE id=3').fetchone()
    assert tuple(q) == ('1m004', 4096, 4096, 0.389, 'coj', 1.3)


def test_readable_date_and_mjd(cfg, cons):
    con = cons[0]['spectra']
    db.upsert_frames(con, [db.frame_row(frame(1, 'coj2m002-en12-20261010-0006-e00',
                                              date='2026-10-10T12:00:00.500000Z'), set(), set())])
    d, m = con.execute('SELECT date_utc, mjd_obs FROM frames').fetchone()
    assert d == '2026-10-10 12:00:00' and abs(m - 61323.5) < 1e-5


class FakeClient:
    def __init__(self, frames):
        self.data, self.calls = frames, []

    def frames(self, start, end, page_size=1000, **flt):
        self.calls.append(flt)
        for f in self.data:
            if all(f.get({'reduction_level': 'reduction_level', 'instrument_id': 'instrument_id',
                          'proposal_id': 'proposal_id'}[k]) == v for k, v in flt.items() if k != 'exclude_OBSTYPE'):
                yield f


def test_crawl_plan_skips_raw_imaging(cfg, cons):
    c, state = cons
    data = [frame(1, 'coj2m002-en12-20261010-0006-e00'),
            frame(2, 'coj2m002-en12-20261010-0006-e90', rlevel=90),
            frame(3, 'coj1m011-fa12-20261010-0100-e00', inst='fa12', obstype='EXPOSE'),
            frame(4, 'coj1m011-fa12-20261010-0100-e91', inst='fa12', obstype='EXPOSE', rlevel=91)]
    fc = FakeClient(data)
    r = ingest.Router(cfg, c, state)
    ingest.crawl_window(fc, cfg, r, 'KEY2026B-007', datetime(2026, 10, 1), datetime(2026, 10, 15), False)
    raw_calls = [q for q in fc.calls if q.get('reduction_level') == 0]
    assert raw_calls == [{'proposal_id': 'KEY2026B-007', 'exclude_OBSTYPE': cfg['exclude_obstypes'],
                          'reduction_level': 0, 'instrument_id': 'en12'}]
    assert [x[0] for x in c['spectra'].execute('SELECT id FROM frames')] == [1]
    assert [x[0] for x in c['photometry'].execute('SELECT id FROM frames')] == [4]


def test_client_raises_throttled_on_long_retry_after():
    from ava.lcodb.api import Client, Throttled

    class R:
        status_code = 429
        headers = {'Retry-After': '6718'}

    class S:
        calls = 0
        def get(self, *a, **k):
            S.calls += 1
            return R()

    c = Client(max_wait_s=900)
    c._local.s = S()
    try:
        c.get('https://example.invalid/x')
        assert False, 'expected Throttled'
    except Throttled as e:
        assert e.retry_after == 6718
    try:  # a second call must not even hit the server while blocked
        c.get('https://example.invalid/y')
    except Throttled:
        pass
    assert S.calls == 1


def test_spectrum_standards_same_slit_then_2arcsec(cfg, cons):
    con = cons[0]['spectra']
    rows = [frame(1, 'coj2m002-en12-20261010-0006-e00', block=10),        # science, 6" slit
            frame(2, 'coj2m002-en12-20261011-0006-e00', block=11, date='2026-10-11T12:00:00Z')]   # science, 1.6"
    # standards: 2" (near), 6" (2 days later), 1.2" (nearest of all)
    for i, (h, wid) in enumerate([(13, 2.0), (60, 6.0), (12.5, 1.2)]):
        d = datetime(2026, 10, 10) + __import__('datetime').timedelta(hours=h)
        rows.append(frame(10 + i, f'coj2m002-en12-2026101{i}-00{20 + i}-e00', obj='EG21', block=20 + i,
                          date=d.strftime('%Y-%m-%dT%H:%M:%SZ')))
    db.upsert_frames(con, [db.frame_row(f, {'EG21'}, set()) for f in rows])
    for fid, wid in [(1, 6.0), (2, 1.6), (10, 2.0), (11, 6.0), (12, 1.2)]:
        db.store_header(con, fid, 'a', {'APERWID': wid})
    standards.rebuild(con, n_nearest=5, max_dt_days=30)
    got = {r['sci_id']: (r['std_id'], r['std_choice']) for r in con.execute('SELECT * FROM spectrum_standards')}
    assert got[1] == (11, 'same_slit')          # 6" science -> the 6" standard, though further in time
    assert got[2] == (10, 'nearest_2arcsec')    # no 1.6" standard -> nearest 2", not the nearer 1.2"


def test_ava_match_position_name_review_override():
    from ava.lcodb import ava
    A = [dict(id=1, data_id='fairall_9', name='Fairall 9', ra=20.94074, dec=-58.80578, keys={'FAIRALL9'}),
         dict(id=8, data_id='NGC_5548', name='NGC 5548', ra=214.4981, dec=25.1368, keys={'NGC5548'})]
    T = {'F9 field': dict(ra=20.941, dec=-58.8057, pos='header', n_phot=5, n_spec=0),      # position
         'Fairall9': dict(ra=None, dec=None, pos=None, n_phot=1, n_spec=0),                # name, no position
         'NGC5548': dict(ra=10.0, dec=10.0, pos='footprint', n_phot=3, n_spec=0),          # name but far
         'blank': dict(ra=100.0, dec=0.0, pos='header', n_phot=2, n_spec=0)}
    r = {x['object']: x for x in ava.match(T, A)}
    assert r['F9 field']['ava_id'] == 1 and r['F9 field']['matched_by'].startswith('position')
    assert r['Fairall9']['ava_id'] == 1 and r['Fairall9']['matched_by'] == 'name'
    assert r['NGC5548']['ava_id'] is None and 'same name' in r['NGC5548']['review']
    assert r['blank']['ava_id'] is None and r['blank']['review'] is None
    r = {x['object']: x for x in ava.match(T, A, overrides={'NGC5548': 8, 'F9 field': None})}
    assert r['NGC5548']['ava_id'] == 8 and r['F9 field']['ava_id'] is None
    assert ava.norm('MCG_08-11-011') == ava.norm('MCG 8-11-11') and ava.norm('Mrk%20817') == 'MRK817'


def test_query_archive_end_to_end(cfg, cons, tmp_path):
    import sqlite3 as sq
    import pandas as pd
    from ava.lcodb import ava
    from ava.lcodb.query import Archive, to_mjd
    sp, ph = cons[0]['spectra'], cons[0]['photometry']
    # photometry: two visits of Fairall9 in g on two nights, one camera
    rows = [frame(100 + k, f'cpt1m010-fa14-2026101{k}-00{10 + k}-e91', inst='fa14', obstype='EXPOSE', rlevel=91,
                  date=f'2026-10-1{k}T20:00:00Z', block=500 + k) for k in range(3)]
    for r in rows:
        r['primary_optical_element'] = 'gp'
    db.upsert_frames(ph, [db.frame_row(f, set(), set()) for f in rows])
    db.mark_best(ph)
    # spectra: one science spectrum + one standard
    srows = [frame(1, 'coj2m002-en12-20261010-0006-e00', block=10),
             frame(10, 'coj2m002-en12-20261010-0010-e00', obj='EG21', block=20, date='2026-10-10T13:00:00Z')]
    db.upsert_frames(sp, [db.frame_row(f, {'EG21'}, set()) for f in srows])
    db.store_header(sp, 1, 'a', {'APERWID': 6.0})
    db.store_header(sp, 10, 'a', {'APERWID': 2.0})
    standards.rebuild(sp, 5, 30)
    calibs.rebuild(sp, 3, 7)
    # AVA master + link + a small ava.sqlite
    csv = tmp_path / 'ava.csv'
    pd.DataFrame([dict(id=1, name='Fairall 9', data_id='fairall_9', lco_id='Fairall9', simbad_name='Fairall 9',
                       ra='01:23:45.78', dec='-58:48:20.81', ra_deg=20.9, dec_deg=-58.795, redshift=0.046,
                       cite_name='Hernandez Santisteban et al. 2020, MNRAS, 498, 5399|',
                       cite_url='2020MNRAS.498.5399H|')]).to_csv(csv, index=False)
    ava.link({'spectra': sp, 'photometry': ph}, csv)
    avadb = tmp_path / 'ava.sqlite'
    c = sq.connect(avadb)
    pd.read_csv(csv).to_sql('agn', c, index=False)
    c.execute('CREATE VIEW agn_full AS SELECT * FROM agn')
    c.commit()
    c.close()

    a = Archive(spectra=cfg.db_path('spectra'), photometry=cfg.db_path('photometry'), ava=avadb)
    for q in (1, 'Fairall 9', 'fairall9', 'FAIRALL_9', 'Fairall9'):
        assert a.resolve(q).ava_id == 1
    p = a.phot('Fairall 9', filters='g')
    assert len(p) == 3 and set(p['filter']) == {'gp'} and p.camera.iloc[0] == 'fa14'
    assert len(a.phot(1, start='2026-10-11', end='2026-10-12')) == 1
    assert len(a.phot(1, camera='sinistro')) == 3 and len(a.phot(1, camera='fa01')) == 0
    s = a.spectra('Fairall 9')
    assert len(s) == 1 and s.std_object.iloc[0] == 'EG21' and s.std_choice.iloc[0] == 'nearest_2arcsec'
    c = a.cadence(1, filters='g')
    assert c['points'] == 3 and abs(c['median_d'] - 1.0) < 1e-6
    assert len(a.seasons(1)) == 1
    assert a.citations(1).bibcode.iloc[0] == '2020MNRAS.498.5399H'
    summ = a.summary('Fairall 9')
    assert 'photometry' in summ and 'Fairall 9 (AVA 1)' in str(summ)
    assert len(a.night('2026-10-11')) >= 1
    o = a.overview()
    assert o.loc[0, 'phot_images'] == 3 and o.loc[0, 'spec_epochs'] == 1
    assert abs(to_mjd('2026-10-10') - 61323.0) < 1e-9
    a.close()
