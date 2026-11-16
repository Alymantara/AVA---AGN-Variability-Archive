"""Census of every FLOYDS spectrum visible in the LCO archive (all programmes, not only ours).

  python3 tools/floyds_census.py --out ../AVA/floyds_census.csv [--start 2014-01-01] [--end today]

Lists raw (level 0) FLOYDS frames of type SPECTRUM / STANDARD (filtered by the archive, no related frames, so
one request per 1000 frames) in --window-day windows for en05, en06 and en12 and
writes one row per frame (id, basename, target, proposal, instrument, date, slit, airmass when given).
Used to find flux-standard stars observed under names or programmes our standards search does not know.
Resumable: windows already in the output are skipped. Honors the archive's Retry-After (waits, then goes on).
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ava.lcodb.api import Client  # noqa: E402
from ava.lcodb.config import load_config  # noqa: E402
from ava.lcodb.db import footprint_centre  # noqa: E402

FIELDS = ['id', 'basename', 'target_name', 'proposal_id', 'instrument_id', 'site_id', 'observation_date',
          'configuration_type', 'exposure_time', 'request_id', 'observation_id', 'ra', 'dec', 'window']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True)
    p.add_argument('--start', default='2014-01-01')
    p.add_argument('--end', default=datetime.utcnow().strftime('%Y-%m-%d'))
    p.add_argument('--instruments', nargs='+', default=['en05', 'en06', 'en12'])
    p.add_argument('--rate', type=float, default=1.0, help='requests per second')
    p.add_argument('--window-days', type=int, default=365)
    p.add_argument('--priority-proposals', nargs='*', default=['OGG_calib', 'COJ_calib'],
                   help='queried first, whole date range in one go per instrument')
    a = p.parse_args()
    cfg = load_config()
    c = Client(cfg.token, cfg.get('request_timeout', 180), 8, rate_per_s=a.rate, max_wait_s=8 * 3600)
    done = set()
    if os.path.exists(a.out):
        with open(a.out) as f:
            done = {r['window'] for r in csv.DictReader(f)}
    new = not os.path.exists(a.out)
    f = open(a.out, 'a', newline='')
    w = csv.DictWriter(f, FIELDS)
    if new:
        w.writeheader()
    t0, t1 = datetime.fromisoformat(a.start), datetime.fromisoformat(a.end)
    n = 0

    def sweep(key, **filters):
        nonlocal n
        if key in done:
            return
        rows = 0
        for fr in c.frames(filters.pop('t'), filters.pop('u'), page_size=1000, related=False,
                           reduction_level=0, **filters):
            if fr.get('configuration_type') not in ('SPECTRUM', 'STANDARD'):
                continue
            ra, dec = footprint_centre(fr.get('area'))
            w.writerow({k: fr.get(k) for k in FIELDS if k not in ('window', 'ra', 'dec')}
                       | {'ra': ra, 'dec': dec, 'window': key})
            rows += 1
        if rows == 0:   # keep a marker so the window is not re-queried
            w.writerow({'window': key})
        f.flush()
        n += rows
        print(f'{key}: {rows} spectra (total {n})', flush=True)

    for prop in a.priority_proposals:
        for inst in a.instruments:
            for ctype in ('SPECTRUM', 'STANDARD'):
                sweep(f'{prop}:{inst}:{ctype}', t=t0, u=t1, proposal_id=prop, instrument_id=inst,
                      configuration_type=ctype)
    for inst in a.instruments:
        t = t0
        while t < t1:
            u = min(t + timedelta(days=a.window_days), t1)
            for ctype in ('STANDARD', 'SPECTRUM'):
                sweep(f'{inst}:{ctype}:{t:%Y-%m-%d}', t=t, u=u, instrument_id=inst, configuration_type=ctype)
            t = u
    f.close()


if __name__ == '__main__':
    main()
