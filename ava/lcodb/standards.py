"""Match each science spectrum to the flux standards nearest in time.

Rules (raw frames, same spectrograph `instrument_id`):
  1. a standard taken in the same observing block comes first;
  2. then by |dt|, within standards.max_dt_days;
  keep standards.n_nearest for each slit width (APERWID), so 2" and 6" standards are both kept;
  `same_slit` says whether it matches the science slit. Pick e.g. `same_slit=1 ORDER BY rank`.
The table is rebuilt every run (cheap), so standards taken after a spectrum are picked up.
"""
import bisect
import math
from collections import defaultdict


def flag_by_position(con, radius_arcsec=60.0):
    """Raw spectra pointed at a known flux standard (median position of the frames already flagged
    is_standard, by name) are flagged is_standard too, whatever their target name. Targets linked to
    an AVA source are never flagged. Returns the number of frames newly flagged."""
    pos = defaultdict(list)
    for obj, ra, dec in con.execute("""SELECT object, ra, dec FROM frames WHERE is_standard=1 AND rlevel=0
                                       AND obstype IN ('SPECTRUM','STANDARD') AND ra IS NOT NULL"""):
        pos[obj].append((ra, dec))
    ref = []
    for obj, v in pos.items():
        v = sorted(v)
        ref.append((obj, v[len(v) // 2][0], sorted(d for _, d in v)[len(v) // 2]))
    cand = con.execute("""SELECT id, ra, dec FROM frames WHERE is_standard=0 AND rlevel IN (0, 91)
                          AND obstype IN ('SPECTRUM','STANDARD') AND ra IS NOT NULL AND ava_id IS NULL""").fetchall()
    hits = []
    for fid, ra, dec in cand:
        for obj, sra, sdec in ref:
            if abs(dec - sdec) * 3600 > radius_arcsec:
                continue
            r1, d1, r2, d2 = map(math.radians, (ra, dec, sra, sdec))
            c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
            if math.degrees(math.acos(min(1.0, max(-1.0, c)))) * 3600 <= radius_arcsec:
                hits.append((fid,))
                break
    con.executemany('UPDATE frames SET is_standard=1 WHERE id=?', hits)
    con.commit()
    return len(hits)


def reference_positions(folder):
    """(name, ra, dec) of the flux standards the reduction can use: the RA/DEC header of every reference spectrum
    in ``folder`` (banzai-floyds ``banzai_floyds/data/standards/*.fits``). None when the folder is not set or
    missing (no restriction)."""
    import glob
    import os

    if not folder or not os.path.isdir(os.path.expanduser(str(folder))):
        return None
    from astropy.io import fits

    out = []
    for f in sorted(glob.glob(os.path.join(os.path.expanduser(str(folder)), '*.fits'))):
        h = fits.getheader(f, 0)
        if 'RA' in h and 'DEC' in h:
            out.append((os.path.basename(f).split('.')[0], float(h['RA']), float(h['DEC'])))
    return out


def _near(ra, dec, positions, radius_arcsec):
    if ra is None or dec is None:
        return False
    for _, sra, sdec in positions:
        if abs(dec - sdec) * 3600 > radius_arcsec:
            continue
        r1, d1, r2, d2 = map(math.radians, (ra, dec, sra, sdec))
        c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
        if math.degrees(math.acos(min(1.0, max(-1.0, c)))) * 3600 <= radius_arcsec:
            return True
    return False


def rebuild(con, n_nearest=5, max_dt_days=30, usable=None, usable_radius_arcsec=300.0):
    """``usable``: (name, ra, dec) of the standards the reduction has reference spectra for
    (:func:`reference_positions`); other standards are never matched (B19: banzai-floyds treats a star it does not
    know as a science target and the night gets no flux calibration). None = every flagged standard."""
    cols = 'id, instrument_id, mjd_obs, block_id, aperwid, object, proposal_id, COALESCE(airmass, airmass_calc)'
    stds = con.execute(f"""SELECT {cols}, ra, dec FROM frames WHERE rlevel=0 AND is_standard=1
        AND obstype IN ('SPECTRUM','STANDARD') AND mjd_obs IS NOT NULL""").fetchall()
    if usable is not None:
        stds = [s for s in stds if _near(s[8], s[9], usable, usable_radius_arcsec)]
    stds = [tuple(s)[:8] for s in stds]
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
