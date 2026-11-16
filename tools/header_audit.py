"""Sample archive headers across years / cameras / reduction levels and report keyword coverage.

  python3 tools/header_audit.py [--per-cell 3] [--out audit.json]

Cells are (year, camera prefix, rlevel). For each, up to --per-cell frames spread over the
year are fetched (headers only). Output: presence fraction and example values per keyword.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ava.lcodb.api import Client          # noqa: E402
from ava.lcodb.config import load_config  # noqa: E402
from ava.lcodb.ingest import classify, discover_proposals  # noqa: E402

PHOT_KEYS = ['FILTER', 'OBJECT', 'EXPTIME', 'MJD-OBS', 'DATE-OBS', 'AIRMASS', 'NAXIS1', 'NAXIS2', 'SITEID',
             'SKYMAG', 'TELID', 'PIXSCALE', 'L1FWHM', 'CCDSUM', 'EXTNAME', 'RLEVEL']
SPEC_KEYS = ['OBJECT', 'EXPTIME', 'MJD-OBS', 'DATE-OBS', 'AIRMASS', 'APERWID', 'OBSTYPE', 'SITEID', 'TELID', 'BLKUID']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--per-cell', type=int, default=3)
    p.add_argument('--out', default='header_audit.json')
    a = p.parse_args()
    cfg = load_config()
    c = Client(cfg.token, 180, 4)
    props = [x[0] for x in discover_proposals(c, cfg) if not x[3]]
    cells = defaultdict(list)       # (year, prefix, level, kind) -> [frame]
    for pid in props:
        for year in range(2014, datetime.utcnow().year + 1):
            for month in (2, 5, 8, 11):
                s = datetime(year, month, 1)
                e = datetime(year, month, 15)
                try:
                    fr = list(c.frames(s, e, page_size=1000, proposal_id=pid,
                                       exclude_OBSTYPE=cfg['exclude_obstypes']))
                except Exception as ex:
                    print('ERR', pid, s, ex)
                    continue
                for f in fr:
                    kind = classify(f['instrument_id'], cfg)
                    if kind not in ('spectra', 'photometry'):
                        continue
                    if kind == 'spectra' and f['configuration_type'] != 'SPECTRUM':
                        continue
                    key = (year, f['instrument_id'][:2], f['reduction_level'], kind)
                    if len(cells[key]) < a.per_cell and all(g['basename'][:13] != f['basename'][:13] or
                                                           g['observation_day'] != f['observation_day']
                                                           for g in cells[key]):
                        cells[key].append(f)
        print('sampled', pid, sum(len(v) for v in cells.values()), 'frames so far', flush=True)
    report = {}
    for key in sorted(cells):
        keys = SPEC_KEYS if key[3] == 'spectra' else PHOT_KEYS
        rows = []
        for f in cells[key]:
            try:
                h = c.headers_of(f['id'])
            except Exception as ex:
                print('ERR header', f['id'], ex)
                continue
            rows.append((f['basename'], {k: h.get(k) for k in keys}))
        if not rows:
            continue
        cov = {k: sum(r[1][k] not in (None, '', 'N/A', 'UNKNOWN') for r in rows) / len(rows) for k in keys}
        report['%d %s L%d %s' % key] = {'n': len(rows), 'coverage': cov, 'examples': rows}
        missing = [k for k, v in cov.items() if v < 1]
        vals = {k: sorted({str(r[1][k]) for r in rows})[:4] for k in ('SKYMAG', 'PIXSCALE', 'NAXIS1', 'TELID', 'L1FWHM') if k in keys}
        print('%d %-2s L%-2d %-10s n=%d missing=%s %s' % (key + (len(rows), missing or '-', vals)), flush=True)
    json.dump(report, open(a.out, 'w'), indent=1, default=str)


if __name__ == '__main__':
    main()
