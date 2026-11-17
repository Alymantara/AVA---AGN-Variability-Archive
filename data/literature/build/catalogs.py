"""NED (TAP), SIMBAD (Harvard mirror TAP) and Veron-Cetty & Veron 2010 (VizieR) cone queries per target.
Resumable: appends one JSON line per target to the output file."""
import sys, time, io, json, math, urllib.request, urllib.parse
from pathlib import Path
import pandas as pd
t = pd.read_csv(sys.argv[1])
# position fixes: the DB holds IC 4329 (elliptical) for the AGN IC 4329A
t.loc[t.data_id == 'IC_4329', ['ra_deg', 'dec_deg']] = [207.33025, -30.30944]
outp = Path(sys.argv[2])
done = {json.loads(l)['id'] for l in outp.read_text().splitlines()} if outp.exists() else set()
def get(url, data=None):
    for k in range(3):
        try: return urllib.request.urlopen(url, data, timeout=60).read().decode()
        except Exception as e: err = e; time.sleep(3)
    raise err
def tap(url, q):
    return pd.read_csv(io.StringIO(get(url, urllib.parse.urlencode(dict(REQUEST='doQuery', LANG='ADQL', FORMAT='csv', QUERY=q)).encode())))
def clean(v):
    return None if (v is None or (isinstance(v, float) and math.isnan(v))) else (v.item() if hasattr(v, 'item') else v)
for r in t.itertuples():
    if r.id in done: continue
    rec = dict(id=r.id, data_id=r.data_id); rd = 10 / 3600; cd = math.cos(math.radians(r.dec_deg))
    try:
        n = tap('https://ned.ipac.caltech.edu/tap/sync', f"SELECT prefname, ra, dec, prefphytype, z, zunc, zflag, z_bibcode FROM NEDTAP.objdir WHERE CONTAINS(POINT('J2000',ra,dec),CIRCLE('J2000',{r.ra_deg},{r.dec_deg},{rd}))=1")
        if len(n):
            n['sep'] = (((n.ra - r.ra_deg) * cd) ** 2 + (n.dec - r.dec_deg) ** 2) ** .5 * 3600
            nz = n[n.z.notna() & ~n.prefname.str.contains(r' ABS\d', regex=True)].sort_values('sep')  # skip absorber entries
            b = (nz if len(nz) else n.sort_values('sep')).iloc[0]
            rec.update(ned_name=b.prefname, ned_type=b.prefphytype, ned_z=b.z, ned_zunc=b.zunc, ned_zflag=b.zflag, ned_zbib=b.z_bibcode, ned_sep=round(b.sep, 2))
    except Exception as e: rec['ned_err'] = str(e)[:120]
    try:
        s = tap('https://simbad.harvard.edu/simbad/sim-tap/sync', f"SELECT main_id, otype, sp_type, rvz_redshift, rvz_bibcode, DISTANCE(POINT('ICRS',ra,dec),POINT('ICRS',{r.ra_deg},{r.dec_deg}))*3600 AS sep FROM basic WHERE CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{r.ra_deg},{r.dec_deg},{rd}))=1 ORDER BY sep")
        if len(s):
            agn = s[s.otype.isin(['Sy1', 'Sy2', 'SyG', 'QSO', 'AGN', 'Bla', 'BLL', 'LIN', 'XB*', 'LXB'])]
            b = (agn if len(agn) else s).iloc[0]
            rec.update(sim_id=b.main_id, sim_otype=b.otype, sim_sp=b.sp_type, sim_z=b.rvz_redshift, sim_zbib=b.rvz_bibcode, sim_sep=round(b.sep, 2))
    except Exception as e: rec['sim_err'] = str(e)[:120]
    try:
        c = f"{r.ra_deg}%20{r.dec_deg:+}".replace("+", "%2B")
        txt = get(f'https://vizier.cfa.harvard.edu/viz-bin/asu-tsv?-source=VII/258/vv10&-c={c}&-c.rs=15&-out.all&-sort=_r')
        lines = [l for l in txt.splitlines() if l and not l.startswith('#')]
        if len(lines) >= 4:
            v = pd.read_csv(io.StringIO('\n'.join([lines[0]] + lines[3:])), sep='\t'); b = v.iloc[0]
            rec.update(vcv_name=str(b.Name).strip(), vcv_sp=str(b.Sp).strip(), vcv_z=b.z, vcv_sep=b._r)
    except Exception as e: rec['vcv_err'] = str(e)[:120]
    with outp.open('a') as fh: fh.write(json.dumps({k: clean(v) for k, v in rec.items()}) + '\n')
    print(r.id, rec.get('ned_name'), rec.get('ned_z'), rec.get('sim_otype'), rec.get('vcv_sp'), flush=True)
    time.sleep(0.3)
