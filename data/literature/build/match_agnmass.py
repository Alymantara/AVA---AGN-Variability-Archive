import json, sys
import pandas as pd
from astropy.coordinates import SkyCoord
import astropy.units as u
t = pd.read_csv(sys.argv[1]); a = json.load(open(sys.argv[2]))
ac = SkyCoord([o['ra'] for o in a], [o['dec'] for o in a], unit=(u.hourangle, u.deg))
t = t.copy(); ok = t.ra_deg.notna() & t.dec_deg.notna()
tc = SkyCoord(t.ra_deg.fillna(0).values * u.deg, t.dec_deg.fillna(-89.9).values * u.deg)
idx, sep, _ = tc.match_to_catalog_sky(ac)
t['agnmass_vid'] = [a[i]['vid'] if s.arcsec < 30 and k else None for i, s, k in zip(idx, sep, ok)]
t['agnmass_name'] = [a[i]['name'] if s.arcsec < 30 and k else None for i, s, k in zip(idx, sep, ok)]
t['agnmass_sep'] = [round(s.arcsec, 1) for s in sep]
t.to_csv(sys.argv[3], index=False)
print(t[['id', 'data_id', 'bentz_id', 'agnmass_vid', 'agnmass_name', 'agnmass_sep']].to_string(index=False))
