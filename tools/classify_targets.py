"""Classify LCO targets with SIMBAD object types (which of them are AGN?).

  python3 tools/classify_targets.py --targets ../AVA/lco_targets_not_in_ava.csv --out ../AVA/lco_targets_not_in_ava_simbad.csv

For each target position, the nearest SIMBAD object within --radius is taken (TAP cone search).
Only coordinates are sent to SIMBAD.
"""
import argparse
import time

import pandas as pd
import requests

TAPS = ['https://simbad.harvard.edu/simbad/sim-tap/sync', 'https://simbad.cds.unistra.fr/simbad/sim-tap/sync']
AGN_TYPES = {'AGN', 'SyG', 'Sy1', 'Sy2', 'QSO', 'Bla', 'BLL', 'LIN', 'AG?', 'Q?', 'Bz?', 'BL?', 'LeQ', 'Sy?', 'rG'}
# SIMBAD short codes: AGN, Seyfert (SyG, Sy1, Sy2), QSO, blazars (Bla, BLL), LINER, candidates (...?), radio galaxy


def query(ra, dec, radius_arcsec):
    adql = (f"SELECT TOP 1 main_id, otype, ra, dec, rvz_redshift, "
            f"DISTANCE(POINT('ICRS', ra, dec), POINT('ICRS', {ra}, {dec})) * 3600 AS sep "
            f"FROM basic WHERE CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {radius_arcsec / 3600})) = 1 "
            f"ORDER BY sep")
    for attempt in range(4):
        TAP = TAPS[attempt % len(TAPS)]
        try:
            r = requests.get(TAP, params=dict(request='doQuery', lang='adql', format='json', query=adql), timeout=60)
            r.raise_for_status()
            d = r.json()
            rows = d.get('data') or []
            if not rows:
                return None
            cols = [c['name'] for c in d['metadata']]
            return dict(zip(cols, rows[0]))
        except Exception:
            time.sleep(3 * (attempt + 1))
    return {'main_id': 'QUERY FAILED'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--targets', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--radius', type=float, default=60.0, help='arcsec')
    a = p.parse_args()
    t = pd.read_csv(a.targets)
    out = []
    for r in t.itertuples():
        s = query(r.ra, r.dec, a.radius) or {}
        otype = s.get('otype')
        out.append(dict(r._asdict(), simbad_id=s.get('main_id'), simbad_otype=otype, simbad_z=s.get('rvz_redshift'),
                        simbad_sep=s.get('sep'), is_agn=otype in AGN_TYPES))
        time.sleep(0.2)
    o = pd.DataFrame(out).drop(columns=['Index'])
    o.to_csv(a.out, index=False)
    agn = o[o.is_agn]
    print(f'{len(o)} targets, {len(agn)} classified as AGN by SIMBAD')
    print(agn[['object', 'simbad_id', 'simbad_otype', 'simbad_z', 'simbad_sep', 'n_phot', 'n_spec']].to_string(index=False))
    other = o[~o.is_agn]
    print('\nnot AGN / no SIMBAD match:')
    print(other[['object', 'simbad_id', 'simbad_otype', 'simbad_sep', 'n_phot', 'n_spec']].to_string(index=False))


if __name__ == '__main__':
    main()
