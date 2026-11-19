"""B03: the standard chosen for a science night may be from ANOTHER night (39 % of AGN spectra); it was
downloaded under its own night but never staged for banzai-floyds.  Offline."""
from datetime import datetime

import pytest

from ava.lcodb import db, standards
from ava.lcodb.config import load_config
from ava.spectroscopy import download as SD
from ava.spectroscopy import reduce as R
from test_lcodb import frame


@pytest.fixture
def spec_db(tmp_path):
    cfg = load_config()
    cfg.raw['db_dir'] = str(tmp_path)
    con = db.connect(cfg.db_path('spectra'), 'spectra')
    rows = [frame(1, 'coj2m002-en12-20261010-0006-e00', block=10),                       # science, night 10 Oct
            frame(11, 'coj2m002-en12-20261012-0021-e00', obj='EG21', block=21,           # its standard, 12 Oct
                  date='2026-10-12T12:00:00Z')]
    db.upsert_frames(con, [db.frame_row(f, {'EG21'}, set()) for f in rows])
    for fid in (1, 11):
        db.store_header(con, fid, 'a', {'APERWID': 6.0})
    con.execute('UPDATE frames SET ava_id=7 WHERE id=1')
    standards.rebuild(con, n_nearest=5, max_dt_days=30)
    con.commit()
    path = cfg.db_path('spectra')
    con.close()
    return path


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b'x')
    return p


def test_standard_from_another_night_is_staged(tmp_path, spec_db):
    raw_root, spec_root = tmp_path / 'raw', tmp_path / 'spec'
    sci = _touch(raw_root / 'T' / '20261010' / 'coj2m002-en12-20261010-0006-e00.fits.fz')
    std = _touch(raw_root / 'standards' / '20261012' / 'coj2m002-en12-20261012-0021-e00.fits.fz')
    p = SD.plan(spec_db, 7, ['2026-10-10'], archive_products=False)
    assert set(p.role) == {'science', 'standard'}
    assert SD.destination(p[p.role == 'standard'].iloc[0], spec_raw_root=raw_root, spec_root=spec_root,
                          target='T') == std                          # filed under the standard's own night
    # the old staging (science night only) missed it
    old = R.stage(['20261010'], raw_root / 'T', raw_root / 'standards', tmp_path / 'stage_old')
    assert [q.name for q in old] == [sci.name]
    on_disk, missing = R.chosen_standards(spec_db, 7, ['20261010'], raw_root, spec_root, 'T')
    assert on_disk == [std] and missing == []
    new = R.stage(['20261010'], raw_root / 'T', raw_root / 'standards', tmp_path / 'stage', extra=on_disk)
    assert sorted(q.name for q in new) == sorted([sci.name, std.name])
    assert (tmp_path / 'stage' / std.name).resolve() == std.resolve()


def test_missing_standard_is_reported_not_staged(tmp_path, spec_db):
    raw_root = tmp_path / 'raw'
    _touch(raw_root / 'T' / '20261010' / 'coj2m002-en12-20261010-0006-e00.fits.fz')
    on_disk, missing = R.chosen_standards(spec_db, 7, ['2026-10-10'], raw_root, tmp_path / 'spec', 'T')
    assert on_disk == [] and missing == ['coj2m002-en12-20261012-0021-e00.fits.fz']
