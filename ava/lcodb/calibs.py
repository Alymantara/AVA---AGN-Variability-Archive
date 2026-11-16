"""Associate every raw FLOYDS spectrum (science and standards) with its arcs and lamp flats.

Per spectrum and per type (ARC, LAMPFLAT), candidates are raw frames on the same spectrograph
within calibs.max_dt_days, ranked by: same observing block, then same slit width (APERWID),
then |dt|. The best calibration is rank 1; calibs.n_nearest are kept per type.
Rebuilt on every run.
"""
import bisect
from collections import defaultdict

CALIB_TYPES = ('ARC', 'LAMPFLAT')


def rebuild(con, n_nearest=3, max_dt_days=7):
    cols = 'id, instrument_id, mjd_obs, block_id, aperwid'
    specs = con.execute(f"""SELECT {cols} FROM frames WHERE rlevel=0 AND obstype='SPECTRUM'
        AND mjd_obs IS NOT NULL""").fetchall()
    cal = defaultdict(list)
    for r in con.execute(f"""SELECT {cols}, obstype FROM frames WHERE rlevel=0
            AND obstype IN ('ARC','LAMPFLAT') AND mjd_obs IS NOT NULL ORDER BY mjd_obs"""):
        cal[(r[1], r[5])].append(tuple(r)[:5])
    times = {k: [c[2] for c in v] for k, v in cal.items()}

    rows = []
    for s in specs:
        sid, inst, t, blk, wid = tuple(s)
        for typ in CALIB_TYPES:
            cand = cal.get((inst, typ))
            if not cand:
                continue
            tt = times[(inst, typ)]
            lo, hi = bisect.bisect_left(tt, t - max_dt_days), bisect.bisect_right(tt, t + max_dt_days)

            def key(c):
                same_blk = blk is not None and c[3] == blk
                same_slit = wid is not None and c[4] is not None and abs(wid - c[4]) < 0.1
                return (not same_blk, not same_slit, abs(c[2] - t))
            for rank, c in enumerate(sorted(cand[lo:hi], key=key)[:n_nearest], 1):
                same_slit = None if (wid is None or c[4] is None) else int(abs(wid - c[4]) < 0.1)
                rows.append((sid, c[0], typ, rank, (c[2] - t) * 24.0,
                             int(blk is not None and c[3] == blk), same_slit, c[4]))
    con.execute('DELETE FROM calib_match')
    con.executemany('INSERT INTO calib_match VALUES (?,?,?,?,?,?,?,?)', rows)
    con.commit()
    return len(specs), len(rows)
