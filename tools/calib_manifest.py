"""Every raw frame needed to calibrate every science spectrum (local databases only, no archive requests).

  python3 tools/calib_manifest.py --outdir ../AVA/manifest

Writes
  calibration_plan.csv  one row per raw science spectrum: its arc and lamp flat, the chosen flux standard
                        (spectrum_standards: same block > same slit > 2" slit > nearest), and that standard's
                        own arc and lamp flat; std_choice = 'none' where no standard is known yet.
  frames_to_download.csv  the unique frames in that plan (archive frame id, basename, role(s), proposal,
                        instrument, date). Download later by id from https://archive-api.lco.global/frames/<id>/
Prints a summary of what is complete and what is missing.
"""
import argparse
import os
import sqlite3
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ava.lcodb.config import load_config  # noqa: E402

PLAN = """
SELECT s.sci_id, s.basename AS sci_basename, s.object, s.ava_id, f.proposal_id, s.instrument_id,
       s.date_utc, s.aperwid,
       c.arc_id, c.arc_basename, c.arc_dt_hours, c.flat_id, c.flat_basename, c.flat_dt_hours,
       COALESCE(s.std_choice, 'none') AS std_choice, s.std_id, s.std_basename, s.std_object, s.std_aperwid,
       s.dt_hours AS std_dt_hours, s.same_block AS std_same_block,
       sc.arc_id AS std_arc_id, sc.arc_basename AS std_arc_basename,
       sc.flat_id AS std_flat_id, sc.flat_basename AS std_flat_basename
FROM spectrum_standards s
JOIN frames f ON f.id = s.sci_id
LEFT JOIN spectrum_calibs c ON c.spec_id = s.sci_id
LEFT JOIN spectrum_calibs sc ON sc.spec_id = s.std_id
ORDER BY s.object, s.date_utc
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--outdir', required=True)
    a = p.parse_args()
    cfg = load_config()
    os.makedirs(a.outdir, exist_ok=True)
    con = sqlite3.connect(f"file:{cfg.db_path('spectra')}?mode=ro", uri=True)
    plan = pd.read_sql(PLAN, con)
    for col in ('ava_id', 'arc_id', 'flat_id', 'std_id', 'std_arc_id', 'std_flat_id'):
        plan[col] = plan[col].astype('Int64')
    plan.to_csv(os.path.join(a.outdir, 'calibration_plan.csv'), index=False)

    roles = []
    for col, role in [('sci_id', 'science'), ('arc_id', 'arc'), ('flat_id', 'flat'), ('std_id', 'standard'),
                      ('std_arc_id', 'standard_arc'), ('std_flat_id', 'standard_flat')]:
        roles.append(plan[[col]].dropna().rename(columns={col: 'id'}).assign(role=role))
    r = pd.concat(roles)
    r = r.groupby('id').role.agg(lambda x: ','.join(sorted(set(x)))).reset_index()
    meta = pd.read_sql('SELECT id, basename, object, proposal_id, instrument_id, site_id, obstype, date_utc, '
                       'exptime FROM frames', con)
    dl = r.merge(meta, on='id', how='left').sort_values(['date_utc', 'id'])
    dl.to_csv(os.path.join(a.outdir, 'frames_to_download.csv'), index=False)

    n = len(plan)
    print(f'science spectra: {n:,}')
    print(f'  with arc: {plan.arc_id.notna().sum():,}   with flat: {plan.flat_id.notna().sum():,}')
    print(f'  with standard: {plan.std_id.notna().sum():,}   ' +
          ', '.join(f'{k}: {v:,}' for k, v in plan.std_choice.value_counts().items()))
    w = plan.std_id.notna()
    print(f'  standard with its own arc: {plan[w].std_arc_id.notna().sum():,}   flat: {plan[w].std_flat_id.notna().sum():,}')
    full = plan.arc_id.notna() & plan.flat_id.notna() & w & plan.std_arc_id.notna() & plan.std_flat_id.notna()
    print(f'  fully calibratable (arc + flat + standard + standard arc + flat): {full.sum():,} / {n:,}')
    print(f'unique frames to download: {len(dl):,}')
    for role, k in dl.role.str.split(',').explode().value_counts().items():
        print(f'  {role}: {k:,}')


if __name__ == '__main__':
    main()
