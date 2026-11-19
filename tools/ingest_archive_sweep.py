"""Add frames found by a read-only archive sweep to the lcodb databases, offline (no archive requests).

The sweep (18 Nov 2026) listed every AVA target by position (`covers=POINT(ra dec)`), 2010 -> 2020-07, levels 90 and 91,
and saved the archive's full frame records as one JSON list per target (<sweep_dir>/<ava_id>.json). This script feeds
those records through the same `ingest.Router` as `lcodb sync`, so the same rules apply: camera prefixes, SBIG on the
1 m only, u B V g r i z Y, reduction levels, `state.dropped_frames` bookkeeping.

Left out on purpose: focus / engineering / calibration programmes and education-outreach (EPO) proposals, and
non-science obstypes. Report: docs/notes/future_improvements.md, "LCO archive: frames missing from the lcodb mirror".

    python tools/ingest_archive_sweep.py <sweep_dir>            # dry run: what would be added, per target/proposal
    python tools/ingest_archive_sweep.py <sweep_dir> --write    # backup, insert, mark_best; then run `lcodb link`
"""
import argparse
import collections
import glob
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ava.lcodb import db, ingest  # noqa: E402
from ava.lcodb.config import load_config  # noqa: E402

LOW_VALUE = ('auto_focus', 'LCOEngineering', 'calibrate', 'ENG', 'pointing')
SCIENCE = {'EXPOSE', 'SPECTRUM', 'STANDARD'}


def skip_reason(f):
    p = f.get('proposal_id') or ''
    if not p or p.startswith(LOW_VALUE) or 'EPO' in p:
        return 'low-value proposal'
    if f.get('configuration_type') not in SCIENCE:
        return 'obstype'
    return None


class DryRouter(ingest.Router):
    """Routes like the real one but only counts what would be stored."""
    def flush(self, kind=None):
        for k in ([kind] if kind else list(self.buf)):
            self.stored[k].extend(self.buf[k])
            self.buf[k] = []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('sweep_dir')
    ap.add_argument('--write', action='store_true', help='back up the databases, then insert (default: dry run)')
    ap.add_argument('--config')
    a = ap.parse_args()
    cfg = load_config(a.config)

    frames, skipped = {}, collections.Counter()
    for fn in sorted(glob.glob(os.path.join(a.sweep_dir, '*.json'))):
        for f in json.load(open(fn)):
            why = skip_reason(f)
            if why:
                skipped[why] += 1
            else:
                frames[f['id']] = f
    paths = {k: cfg.db_path(k) for k in ('spectra', 'photometry')}
    known = set()
    for p in paths.values():
        known |= {r[0] for r in sqlite3.connect(f'file:{p}?mode=ro', uri=True).execute('SELECT id FROM frames')}
    new = [f for i, f in frames.items() if i not in known]
    print(f'{len(frames)} candidate frames, {len(new)} not in the mirror; skipped: {dict(skipped)}')

    if not a.write:
        r = DryRouter(cfg, cons=None, state=None)
        r.stored = {'spectra': [], 'photometry': []}
        for f in new:
            r.add(f)
        r.flush()
        print('would be dropped by the crawl rules:', dict(collections.Counter(why for (_, why) in r.dropped.elements())
                                                          if hasattr(r.dropped, 'elements') else r.dropped))
        for k, rows in r.stored.items():
            c = collections.Counter((x['proposal_id'], x['camera_type'], x['telescope_id']) for x in rows)
            print(f'\n{k}: {len(rows)} frames would be added')
            for key, n in c.most_common():
                print(f'   {n:6d}  {key[0]:20s} {key[1]:9s} {key[2]}')
        print('\ndry run: nothing written. Re-run with --write.')
        return

    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    bdir = cfg.db_dir / 'backups'
    bdir.mkdir(exist_ok=True)
    for k, p in list(paths.items()) + [('state', cfg.db_dir / 'state.sqlite')]:
        dst = bdir / f'{k}_{ts}_before_archive_sweep.sqlite'
        with sqlite3.connect(p) as s, sqlite3.connect(dst) as d:
            s.backup(d)
        print('backup:', dst)
    cons = {k: db.connect(p, k) for k, p in paths.items()}
    state = db.connect(cfg.db_dir / 'state.sqlite', 'state')
    r = ingest.Router(cfg, cons, state)
    for f in new:
        r.add(f)
    print('dropped by the crawl rules (not recorded in state.dropped_frames):', sum(r.dropped.values()))
    r.dropped = {}   # one-off ingest: keep dropped_frames for the crawl's own bookkeeping
    r.flush()
    db.mark_best(cons['photometry'])
    db.propagate_headers(cons['photometry'])
    for c in list(cons.values()) + [state]:
        c.commit()
    state.execute("INSERT INTO runs (command, started, finished, n_new, n_updated, status, message) VALUES (?,?,?,?,?,?,?)",
                  ('ingest_archive_sweep', ts, db.now(), r.n_new, r.n_upd, 'ok',
                   f'offline from {a.sweep_dir}; 2010 -> 2020-07 cone sweep of AVA targets'))
    state.commit()
    print(f'inserted {r.n_new} new, refreshed {r.n_upd}. Next: python -m ava.lcodb link')


if __name__ == '__main__':
    main()
