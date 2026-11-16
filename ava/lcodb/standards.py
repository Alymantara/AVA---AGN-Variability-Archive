"""Match each science spectrum to the flux standards nearest in time.

Rules (raw frames, same spectrograph `instrument_id`):
  1. a standard taken in the same observing block comes first;
  2. then by |dt|, within standards.max_dt_days;
  keep standards.n_nearest for each slit width (APERWID), so 2" and 6" standards are both kept;
  `same_slit` says whether it matches the science slit. Pick e.g. `same_slit=1 ORDER BY rank`.
The table is rebuilt every run (cheap), so standards taken after a spectrum are picked up.
"""
import bisect
from collections import defaultdict


def rebuild(con, n_nearest=5, max_dt_days=30):
    cols = 'id, instrument_id, mjd_obs, block_id, aperwid, object, proposal_id, COALESCE(airmass, airmass_calc)'
    stds = con.execute(f"""SELECT {cols} FROM frames WHERE rlevel=0 AND is_standard=1
        AND obstype IN ('SPECTRUM','STANDARD') AND mjd_obs IS NOT NULL""").fetchall()
    sci = con.execute(f"""SELECT {cols} FROM frames WHERE rlevel=0 AND is_standard=0
        AND obstype='SPECTRUM' AND mjd_obs IS NOT NULL""").fetchall()
    by_inst = defaultdict(list)
    for s in stds:
        by_inst[s[1]].append(tuple(s))
    for v in by_inst.values():
        v.sort(key=lambda s: s[2])
    times = {k: [s[2] for s in v] for k, v in by_inst.items()}

    rows = []
    for s in sci:
        sid, inst, t, blk, wid = s[0], s[1], s[2], s[3], s[4]
        cand = by_inst.get(inst)
        if not cand:
            continue
        tt = times[inst]
        lo = bisect.bisect_left(tt, t - max_dt_days)
        hi = bisect.bisect_right(tt, t + max_dt_days)
        ordered = sorted(cand[lo:hi], key=lambda c: (c[3] != blk or blk is None, abs(c[2] - t)))
        per_slit, near = defaultdict(int), []
        for c in ordered:                       # keep n_nearest for EACH slit width
            key = None if c[4] is None else round(c[4], 1)
            if per_slit[key] < n_nearest:
                per_slit[key] += 1
                near.append(c)
        for rank, c in enumerate(near, 1):
            same_slit = None if (wid is None or c[4] is None) else int(abs(wid - c[4]) < 0.1)
            rows.append((sid, c[0], rank, (c[2] - t) * 24.0, int(blk is not None and c[3] == blk),
                         same_slit, c[5], c[6], c[4], c[7]))
    con.execute('DELETE FROM std_match')
    con.executemany('INSERT INTO std_match VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
    con.commit()
    return len(sci), len(rows)
