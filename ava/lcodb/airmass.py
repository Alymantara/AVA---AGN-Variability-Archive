"""Airmass from site, footprint centre and mid-exposure time, for every frame.

The header AIRMASS (start of exposure) is used when present; this fills the gaps instantly
for frames whose header was not downloaded.
"""
import numpy as np


def fill(con, sites, batch=50000):
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time

    locs = {k: EarthLocation(lat=v['lat'] * u.deg, lon=v['lon'] * u.deg, height=v['height'] * u.m)
            for k, v in sites.items()}
    total = 0
    for site, loc in locs.items():
        while True:
            rows = con.execute("""SELECT id, ra, dec, mjd_obs, COALESCE(exptime, 0) FROM frames
                WHERE airmass_calc IS NULL AND site_id=? AND ra IS NOT NULL AND mjd_obs IS NOT NULL
                LIMIT ?""", (site, batch)).fetchall()
            if not rows:
                break
            a = np.array([tuple(r)[1:] for r in rows], float)
            t = Time(a[:, 2] + a[:, 3] / 2 / 86400.0, format='mjd', scale='utc')
            altaz = SkyCoord(a[:, 0] * u.deg, a[:, 1] * u.deg).transform_to(AltAz(obstime=t, location=loc))
            alt = altaz.alt.deg
            # Pickering (2002); valid down to the horizon. Below it -> -1 (flags a bad footprint).
            am = np.where(alt > 0, 1.0 / np.sin(np.radians(alt + 244.0 / (165.0 + 47.0 * np.maximum(alt, 0) ** 1.1))), -1.0)
            con.executemany('UPDATE frames SET airmass_calc=? WHERE id=?',
                            [(float(x), r[0]) for x, r in zip(am, rows)])
            con.commit()
            total += len(rows)
    return total
