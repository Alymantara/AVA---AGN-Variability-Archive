"""
ava.photometry.reference — reference-star catalogue for absolute calibration.

Two methods, chosen by ``photometry.reference.method`` (see
:func:`build_reference_catalog`):

``gspc`` (default)
    Gaia DR3 Synthetic Photometry Catalogue (VizieR I/360) used directly:
    all-sky, standardised to SDSS / Johnson-Kron-Cousins / PS1, and agrees with
    SDSS DR16 to 0.01-0.02 mag (Mrk 817, PG 0844+349; Nov 2026), where APASS
    is off by 0.05-0.10.  :func:`build_gspc_catalog`.

``apass_model`` (fallback, e.g. G > 17.6-only fields)
    The legacy approach below, :func:`build_apass_model_catalog`.

GSPC -> LCO band mapping (no colour terms yet; LCO vs SDSS/JKC/PS1 filter
differences are a few 0.01 mag and will come from the rebuilt model grid or
from the calibration's own colour terms):

    LCO u <- SDSS u     LCO g, r, i <- SDSS g, r, i     LCO z(s) <- SDSS z
    LCO Y <- PS1 y      LCO B, V, R, I <- JKC B, V, R, I (Vega -> AB)

apass_model method
------------------
Merges ``__old_pipeline__/ava_initialise.py`` and ``ava_zp_pytics.py``:

1. **APASS** field stars around the AGN (:func:`fetch_apass`), cleaned to a
   tidy schema (:data:`APASS_BANDS`, :func:`clean_apass_dr10`).
2. **Gaia DR3** cross-match (:func:`fetch_gaia`, :func:`match_gaia`) for
   parallaxes, GSP-Phot parameters and GSPC synthetic SDSS-u (diagnostics).
3. **Per-star extinction** (:func:`star_ebv`): the line-of-sight
   E(B-V) (Schlafly & Finkbeiner 2011 = 0.86 x SFD) scaled by the fraction of
   an exponential dust layer in front of the star.  The legacy code applied
   the full column to every star, over-reddening nearby dwarfs.
4. **Synthetic LCO photometry** (:func:`synthetic_photometry`): fit a reddened
   atmosphere model (Teff, normalisation) to APASS B g V r i and integrate it
   through the LCO filters (from the precomputed grid
   :class:`AtmosphereGrid`), with errors from draws of the fit covariance.

Identifiers
-----------
Every row is keyed by ``star_id`` = Gaia DR3 ``source_id`` (stable across
rebuilds; the SExtractor step tags detections with it).  The AGN always has a
row (``is_agn``); ``star_id = -1`` if Gaia DR3 has no source at the nucleus.
See :func:`assign_star_ids`.  Note: Gaia DR4 renumbers some sources — these
are DR3 ids.

apass_model output schema (one row per APASS star with a Gaia match)
--------------------------------------------------------------------
star_id, ra, dec, agn_sep_arcsec, is_agn, ra_err, dec_err,
apass_<b>, apass_<b>_err, apass_<b>_nobs       for b in V B u g r i z Y
gaia_source_id, gaia_sep_arcsec, gaia_g, gaia_bp_rp, gaia_parallax,
gaia_parallax_err, gaia_ruwe, gaia_teff, gaia_logg, gaia_mh, gaia_dist_pc,
gspc_<b>, gspc_<b>_err, gspc_<b>_flag         Gaia GSPC u g r i z (SDSS), y (PS1)
dist_pc, ebv                                   (extinction used in the fit)
fit_teff, fit_teff_err, fit_norm, fit_redchi, fit_ok
lco_<b>, lco_<b>_err                           for b in u B g V r i z Y (AB)
lco_u_model, lco_u_model_err                   u before the GSPC anchor

u band
------
``lco_u`` is tied to Gaia GSPC u by one per-field offset (:func:`anchor_u`);
the other bands are the model prediction.  See ``meta["u_anchor"]``.

Photometric systems
-------------------
APASS B, V are Vega; APASS u g r i z (Sloan primes) are AB.  The fit converts
B, V to AB with ``VEGA_TO_AB`` (legacy values).  All ``lco_*`` output is AB.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

C_ANGSTROM_S = 2.99792458e18  # speed of light, Å/s
_trapz = getattr(np, "trapezoid", None) or np.trapz  # numpy < 2 compatibility

# ---------------------------------------------------------------------------
# APASS schema
# ---------------------------------------------------------------------------

#: APASS bands in the order of the AAVSO DR10 CSV (after the 4 astrometry cols).
APASS_BANDS: tuple[str, ...] = ("V", "B", "u", "g", "r", "i", "z", "Y")

#: Loose sanity tokens for each raw AAVSO column (substring, case-insensitive).
_RAW_TOKENS = ["ra", "ra", "dec", "dec"] + [b.lower() for b in APASS_BANDS for _ in range(3)]

#: Bands used in the SED fit, their legacy effective wavelengths (Å) — no
#: APASS filter curves are available, so these stay nominal — and the
#: Vega→AB offsets applied to the APASS magnitudes (legacy values).
FIT_BANDS: tuple[str, ...] = ("B", "g", "V", "r", "i")
FIT_WAVE = {"B": 4361.0, "g": 4770.0, "V": 5468.0, "r": 6215.0, "i": 7545.0}
VEGA_TO_AB = {"B": -0.09, "g": 0.0, "V": 0.02, "r": 0.0, "i": 0.0}

#: LCO output bands (grid column suffix in ava_atmo_models.csv is lower-case).
LCO_BANDS: tuple[str, ...] = ("u", "B", "g", "V", "r", "i", "z", "Y")


def clean_apass_dr10(raw: str | bytes | Path) -> pd.DataFrame:
    """Parse the AAVSO APASS DR10 CSV into the clean schema.

    The AAVSO export has 28 columns (RA, RA err, Dec, Dec err, then
    mag / err / nobs for V B u g r i z Y) with awkward headers.  Columns are
    mapped by position and each header is checked against the expected band.
    """
    if isinstance(raw, Path) or (isinstance(raw, str) and "\n" not in raw):
        raw = Path(raw).read_bytes()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    df = pd.read_csv(io.StringIO(raw), comment="#", na_values=["NA", "na", "", " "])
    if df.shape[1] != len(_RAW_TOKENS):
        raise ValueError(
            f"Unexpected APASS DR10 format: {df.shape[1]} columns, expected "
            f"{len(_RAW_TOKENS)}. Header: {list(df.columns)}"
        )
    for col, tok in zip(df.columns, _RAW_TOKENS):
        if tok not in str(col).lower():
            raise ValueError(f"APASS column {col!r} does not look like {tok!r}; format changed?")

    names = ["ra", "ra_err", "dec", "dec_err"]
    for b in APASS_BANDS:
        names += [f"apass_{b}", f"apass_{b}_err", f"apass_{b}_nobs"]
    df.columns = names
    return _finish_apass(df)


def clean_apass_dr9_vizier(table) -> pd.DataFrame:
    """Convert a VizieR II/336 (APASS DR9) table into the clean schema."""
    t = table.to_pandas() if hasattr(table, "to_pandas") else table
    df = pd.DataFrame({
        "ra": t["RAJ2000"], "ra_err": t["e_RAJ2000"],
        "dec": t["DEJ2000"], "dec_err": t["e_DEJ2000"],
    })
    vz = {"V": "Vmag", "B": "Bmag", "g": "g'mag", "r": "r'mag", "i": "i'mag"}
    # Some astropy versions sanitise the VOTable names (g'mag -> g_mag).
    vz = {b: (c if c in t else c.replace("'", "_")) for b, c in vz.items()}
    for b in APASS_BANDS:
        if b in vz:
            df[f"apass_{b}"] = t[vz[b]].astype(float)
            df[f"apass_{b}_err"] = t["e_" + vz[b]].astype(float)
            df[f"apass_{b}_nobs"] = t["nobs"]
        else:
            df[f"apass_{b}"] = np.nan
            df[f"apass_{b}_err"] = np.nan
            df[f"apass_{b}_nobs"] = 0
    return _finish_apass(df)


def _finish_apass(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for b in APASS_BANDS:  # APASS uses 0 / negative errors for "missing"
        bad = ~(df[f"apass_{b}_err"] > 0)
        df.loc[bad, [f"apass_{b}", f"apass_{b}_err"]] = np.nan
        df[f"apass_{b}_nobs"] = df[f"apass_{b}_nobs"].fillna(0).astype(int)
    df = df.dropna(subset=["ra", "dec"]).sort_values("dec").reset_index(drop=True)
    df.insert(0, "id", np.arange(len(df)))
    return df


# ---------------------------------------------------------------------------
# Remote queries
# ---------------------------------------------------------------------------

def fetch_apass_dr10_aavso(ra: float, dec: float, radius_arcmin: float, url: str) -> bytes:
    """Download APASS DR10 CSV from the AAVSO form (the legacy scraper)."""
    from mechanize import Browser

    br = Browser()
    br.set_handle_robots(False)
    br.addheaders = [("User-agent", "Firefox")]
    br.open(url)
    br.select_form(nr=1)
    br.form["ra"] = str(ra)
    br.form["dec"] = str(dec)
    br.form["radius"] = str(radius_arcmin / 60.0)  # form takes degrees
    out = br.find_control("outtype")
    out.items[0].selected = False
    out.items[1].selected = True                     # CSV
    return br.submit().read()


def _vizier(server: str, columns=("**",)):
    from astroquery.vizier import Vizier

    v = Vizier(row_limit=-1, columns=list(columns), timeout=120)
    v.VIZIER_SERVER = server
    # astroquery < 0.4.7 builds http:// URLs; mirrors that 301-redirect to
    # https (vizier.cfa.harvard.edu) turn the POST into a body-less GET and
    # return an empty TableList, which looked like an "incomplete mirror".
    v._server_to_url = lambda return_type="votable": f"https://{server}/viz-bin/{return_type}"
    return v


def _servers(server) -> list[str]:
    return [server] if isinstance(server, str) else list(server)


def vizier_query(servers, coord, radius, catalog: str, columns=("**",), accept=None):
    """Query ``catalog`` on each VizieR mirror in turn; return (table, server).

    ``accept(table) -> str | None`` returns a rejection reason (e.g. the mirror
    copy is incomplete) or None to accept.  Default: reject empty results.
    Raises ``RuntimeError`` listing every mirror's failure.
    """
    accept = accept or (lambda t: None if len(t) else "no rows")
    errors = []
    for server in _servers(servers):
        try:
            res = _vizier(server, columns).query_region(coord, radius=radius, catalog=[catalog])
            table = res[0] if len(res) else []
        except Exception as exc:  # noqa: BLE001 — try the next mirror
            errors.append(f"{server}: {type(exc).__name__}")
            continue
        why = accept(table)
        if why is None:
            return table, server
        errors.append(f"{server}: {why}")
    raise RuntimeError(f"VizieR {catalog}: " + "; ".join(errors))


def fetch_apass_dr9_vizier(ra: float, dec: float, radius_arcmin: float, server: str):
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    table, _ = vizier_query(server, SkyCoord(ra, dec, unit="deg"), radius_arcmin * u.arcmin,
                            "II/336/apass9")
    return table


def fetch_gaia(ra: float, dec: float, radius_arcmin: float, server: str) -> pd.DataFrame:
    """Gaia DR3 source + GSP-Phot parameters + GSPC SDSS-u for the field (VizieR)."""
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    c = SkyCoord(ra, dec, unit="deg")
    r = radius_arcmin * u.arcmin
    src = vizier_query(server, c, r, "I/355/gaiadr3")[0].to_pandas()
    gaia = pd.DataFrame({
        "gaia_source_id": src["Source"], "gaia_ra": src["RA_ICRS"], "gaia_dec": src["DE_ICRS"],
        "gaia_g": src["Gmag"], "gaia_bp_rp": src["BP-RP"],
        "gaia_parallax": src["Plx"], "gaia_parallax_err": src["e_Plx"], "gaia_ruwe": src["RUWE"],
    })
    try:
        par = vizier_query(server, c, r, "I/355/paramp")[0].to_pandas()
        par = par.rename(columns={"Source": "gaia_source_id", "Teff": "gaia_teff",
                                  "logg": "gaia_logg", "[Fe/H]": "gaia_mh", "__Fe_H_": "gaia_mh",
                                  "Dist": "gaia_dist_pc"})  # __Fe_H_: sanitised by some astropy
        gaia = gaia.merge(par[["gaia_source_id", "gaia_teff", "gaia_logg", "gaia_mh", "gaia_dist_pc"]],
                          on="gaia_source_id", how="left")
    except RuntimeError:
        pass
    try:
        sp = vizier_query(server, c, r, "I/360/syntphot")[0].to_pandas()
        cols = {"gaia_source_id": sp["Source"]}
        for name, (mag, flux, flag) in GSPC_BANDS.items():
            cols[name] = sp[mag]
            cols[f"{name}_err"] = 1.0857 * sp["e_" + flux] / sp[flux]
            cols[f"{name}_flag"] = sp[flag]
        gaia = gaia.merge(pd.DataFrame(cols), on="gaia_source_id", how="left")
    except RuntimeError:
        pass
    extra = [f"{n}{s}" for n in GSPC_BANDS for s in ("", "_err", "_flag")]
    for col in ["gaia_teff", "gaia_logg", "gaia_mh", "gaia_dist_pc"] + extra:
        if col not in gaia:
            gaia[col] = np.nan
    return gaia


#: GSPC (Gaia DR3 synthetic photometry, VizieR I/360) bands kept in the
#: catalogue: name -> (mag column, flux column, validity-flag column).
#: SDSS mags are on the SDSS system (u_AB = u - 0.04, z_AB = z + 0.02);
#: PS1 y is AB.
GSPC_BANDS = {
    "gspc_u_sdss": ("umag", "Fu", "uFlag"),
    "gspc_g_sdss": ("gmag", "Fg", "gFlag"),
    "gspc_r_sdss": ("rmag", "Fr", "rFlag"),
    "gspc_i_sdss": ("imag", "Fi", "iFlag"),
    "gspc_z_sdss": ("zmag", "Fz", "zFlag"),
    "gspc_y_ps1": ("ymag", "Fy", "yFlag"),
}


def match_gaia(stars: pd.DataFrame, gaia: pd.DataFrame, max_sep_arcsec: float) -> pd.DataFrame:
    """Attach the nearest Gaia source (within ``max_sep_arcsec``) to each star."""
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    out = stars.copy()
    cols = [c for c in gaia.columns if c not in ("gaia_ra", "gaia_dec")]
    for c in cols:
        out[c] = np.nan
    out["gaia_sep_arcsec"] = np.nan
    if len(gaia) == 0 or len(stars) == 0:
        return out
    s = SkyCoord(stars["ra"].values, stars["dec"].values, unit="deg")
    g = SkyCoord(gaia["gaia_ra"].values, gaia["gaia_dec"].values, unit="deg")
    idx, d2d, _ = s.match_to_catalog_sky(g)
    ok = d2d.arcsec <= max_sep_arcsec
    for c in cols:
        if c != "gaia_source_id":
            out.loc[ok, c] = gaia[c].values[idx[ok]]
    out.loc[ok, "gaia_sep_arcsec"] = d2d.arcsec[ok]
    # Never via float64: 19-digit source_ids lose their last ~3 digits there.
    src = pd.array([pd.NA] * len(out), dtype="Int64")
    src[ok] = gaia["gaia_source_id"].to_numpy(dtype="int64")[idx[ok]]
    out["gaia_source_id"] = src
    return out


def field_ebv_sf11(ra: float, dec: float) -> float:
    """Line-of-sight E(B-V) from IRSA (Schlafly & Finkbeiner 2011 = 0.86 SFD)."""
    from astropy.coordinates import SkyCoord
    from astroquery.ipac.irsa.irsa_dust import IrsaDust

    t = IrsaDust.get_query_table(SkyCoord(ra, dec, unit="deg"), section="ebv")
    return float(t["ext SandF mean"][0])


def field_nh_hi4pi(ra: float, dec: float, timeout: float = 60) -> float | None:
    """Galactic N_H (cm^-2) from the HEASARC nH tool, HI4PI map (HI4PI Collaboration 2016): weighted
    average within 0.1 deg of (ra, dec) [deg, J2000]; None if the service gives no value."""
    import re

    import requests

    r = requests.get("https://heasarc.gsfc.nasa.gov/cgi-bin/Tools/w3nh/w3nh.pl",
                     params={"Entry": f"{ra:.6f},{dec:.6f}", "NR": "GRB/SIMBAD+Sesame/NED", "CoordSys": "Equatorial",
                             "equinox": "2000", "radius": "0.1", "usemap": "0"}, timeout=timeout)
    r.raise_for_status()
    m = re.search(r"HI4PI\.fits\s*&gt;&gt;\s*Weighted average nH \(cm\*\*-2\)\s*([0-9.Ee+-]+)", r.text)
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Extinction
# ---------------------------------------------------------------------------

def star_ebv(ebv_los: float, dist_pc: np.ndarray, gal_b_deg: float, scale_height_pc: float) -> np.ndarray:
    """E(B-V) in front of each star for an exponential dust layer.

    ``dist_pc`` NaN (no usable parallax) -> full line-of-sight value.
    """
    d = np.asarray(dist_pc, dtype=float)
    z = d * abs(np.sin(np.radians(gal_b_deg)))
    frac = 1.0 - np.exp(-z / scale_height_pc)
    return np.where(np.isfinite(d), ebv_los * frac, ebv_los)


def unred(wave, flux, ebv, R_V=3.1):
    """Fitzpatrick (1999) dereddening (negative ``ebv`` reddens).

    Verbatim port of the optical/UV branch used in ``ava_zp_pytics.py``.
    """
    from scipy import interpolate

    x = 10000.0 / np.atleast_1d(np.asarray(wave, dtype=float))
    curve = x * 0.0
    x0, gamma = 4.596, 0.99
    c3, c4 = 3.23, 0.41
    c2 = -0.824 + 4.717 / R_V
    c1 = 2.030 - 3.007 * c2
    xcutuv = np.array([10000.0 / 2700.0])
    xspluv = 10000.0 / np.array([2700.0, 2600.0])
    iuv = np.where(x >= xcutuv)[0]
    iopir = np.where(x < xcutuv)[0]
    xuv = np.concatenate((xspluv, x[iuv])) if len(iuv) else xspluv
    yuv = c1 + c2 * xuv
    yuv = yuv + c3 * xuv**2 / ((xuv**2 - x0**2) ** 2 + (xuv * gamma) ** 2)
    yuv = yuv + c4 * (0.5392 * (np.maximum(xuv, 5.9) - 5.9) ** 2
                      + 0.05644 * (np.maximum(xuv, 5.9) - 5.9) ** 3)
    yuv = yuv + R_V
    yspluv = yuv[0:2]
    if len(iuv):
        curve[iuv] = yuv[2:]
    xsplopir = np.concatenate(([0], 10000.0 / np.array([26500.0, 12200.0, 6000.0, 5470.0, 4670.0, 4110.0])))
    ysplir = np.array([0.0, 0.26469, 0.82925]) * R_V / 3.1
    ysplop = np.array((
        np.polyval([-4.22809e-01, 1.00270, 2.13572e-04][::-1], R_V),
        np.polyval([-5.13540e-02, 1.00216, -7.35778e-05][::-1], R_V),
        np.polyval([7.00127e-01, 1.00184, -3.32598e-05][::-1], R_V),
        np.polyval([1.19456, 1.01707, -5.46959e-03, 7.97809e-04, -4.45636e-05][::-1], R_V),
    ))
    ysplopir = np.concatenate((ysplir, ysplop))
    if len(iopir):
        tck = interpolate.splrep(np.concatenate((xsplopir, xspluv)),
                                 np.concatenate((ysplopir, yspluv)), s=0)
        curve[iopir] = interpolate.splev(x[iopir], tck)
    return flux * 10.0 ** (0.4 * curve * ebv)


# ---------------------------------------------------------------------------
# Atmosphere grid and filters
# ---------------------------------------------------------------------------

def pivot_wavelength(filter_file: Path) -> float:
    """Pivot wavelength (Å) of a transmission curve (λ, T columns)."""
    w, t = np.loadtxt(filter_file, unpack=True, usecols=(0, 1))
    return float(np.sqrt(_trapz(t * w, w) / _trapz(t / w, w)))


@dataclass
class AtmosphereGrid:
    """Precomputed band-averaged f_λ of model atmospheres vs Teff.

    ``ava_atmo_models.csv`` columns: ``temp``, ``flux_<band>_aavso``,
    ``flux_<band>_lco`` (band in u B V g r i z y).  Single track:
    BT-Settl / BT-NextGen, log g = 4.5, [M/H] = 0.
    """

    temp: np.ndarray
    flux: dict  # (system, band) -> array over temp

    @classmethod
    def load(cls, path: Path) -> "AtmosphereGrid":
        g = pd.read_csv(path).sort_values("temp")
        flux = {}
        for col in g.columns:
            if col.startswith("flux_"):
                _, band, system = col.split("_")
                flux[(system, "Y" if band == "y" else band)] = g[col].to_numpy(float)
        return cls(g["temp"].to_numpy(float), flux)

    def __call__(self, teff, system: str, bands) -> np.ndarray:
        """f_λ in ``bands`` at ``teff`` (scalar or array) — linear in Teff."""
        teff = np.asarray(teff, dtype=float)
        return np.stack([np.interp(teff, self.temp, self.flux[(system, b)]) for b in bands], axis=-1)


# ---------------------------------------------------------------------------
# SED fit and synthetic photometry
# ---------------------------------------------------------------------------

def synthetic_photometry(
    stars: pd.DataFrame,
    grid: AtmosphereGrid,
    lco_pivot: dict,
    n_draws: int = 1000,
    seed: int = 42,
) -> pd.DataFrame:
    """Fit Teff + normalisation per star and predict LCO AB magnitudes.

    Requires all of APASS B g V r i with positive errors (legacy rule).
    Uses ``stars["ebv"]`` per star.  Adds the ``fit_*`` and ``lco_*`` columns.
    """
    from lmfit import Parameters, minimize

    rng = np.random.default_rng(seed)
    out = stars.copy()
    for b in LCO_BANDS:
        out[f"lco_{b}"] = np.nan
        out[f"lco_{b}_err"] = np.nan
    for c in ("fit_teff", "fit_teff_err", "fit_norm", "fit_redchi"):
        out[c] = np.nan
    out["fit_ok"] = False

    w_fit = np.array([FIT_WAVE[b] for b in FIT_BANDS])
    w_lco = np.array([lco_pivot[b] for b in LCO_BANDS])
    vega_ab = np.array([VEGA_TO_AB[b] for b in FIT_BANDS])

    for k, star in out.iterrows():
        mag = np.array([star[f"apass_{b}"] for b in FIT_BANDS], dtype=float)
        err = np.array([star[f"apass_{b}_err"] for b in FIT_BANDS], dtype=float)
        if not (np.all(np.isfinite(mag)) and np.all(err > 0)):
            continue
        ebv = float(star["ebv"])
        # Observed AB mags -> f_λ at the nominal APASS wavelengths.
        f_obs = 10 ** (-(mag + vega_ab + 48.6) / 2.5) * C_ANGSTROM_S / w_fit**2
        f_err = err * f_obs / 1.0857

        red_fit = unred(w_fit, np.ones_like(w_fit), -ebv)

        def resid(p):
            model = 10 ** p["fac"].value * grid(p["teff"].value, "aavso", FIT_BANDS) * red_fit
            return (model - f_obs) / f_err

        p = Parameters()
        p.add("fac", value=float(np.log10(f_obs[2] / grid(6000.0, "aavso", ["V"])[0])))
        p.add("teff", value=6000.0, min=500.0, max=70000.0)
        try:
            res = minimize(resid, p)
        except Exception:  # noqa: BLE001 — a bad star must not stop the field
            continue
        if res.covar is None or not res.success:
            continue

        mean = np.array([res.params["fac"].value, res.params["teff"].value])
        draws = rng.multivariate_normal(mean, res.covar, n_draws)
        draws[:, 1] = np.clip(draws[:, 1], grid.temp[0], grid.temp[-1])
        red_lco = unred(w_lco, np.ones_like(w_lco), -ebv)
        f_lam = 10 ** draws[:, :1] * grid(draws[:, 1], "lco", LCO_BANDS) * red_lco
        mags = -2.5 * np.log10(f_lam * w_lco**2 / C_ANGSTROM_S) - 48.6

        for j, b in enumerate(LCO_BANDS):
            out.at[k, f"lco_{b}"] = np.nanmedian(mags[:, j])
            out.at[k, f"lco_{b}_err"] = np.nanstd(mags[:, j])
        out.at[k, "fit_teff"] = mean[1]
        out.at[k, "fit_teff_err"] = res.params["teff"].stderr
        out.at[k, "fit_norm"] = mean[0]
        out.at[k, "fit_redchi"] = res.redchi
        out.at[k, "fit_ok"] = True
    return out


def anchor_u(
    stars: pd.DataFrame,
    sdss_u_ab_offset: float = -0.04,
    min_stars: int = 10,
    max_ruwe: float = 1.4,
    clip_sigma: float = 3.0,
) -> tuple[pd.DataFrame, dict]:
    """Shift synthetic ``lco_u`` so its field median matches Gaia GSPC u.

    The model extrapolation to u is biased (about +0.2 mag too faint for
    Fairall 9), while g..Y agree with GSPC to ~0.03 mag.  Until the grid is
    rebuilt, u is tied to GSPC SDSS u (converted to AB) by a single per-field
    offset; no colour term is applied (LCO u' vs SDSS u is ~0.03 mag for
    solar-type stars by the current grid).  ``lco_u_model`` keeps the raw
    prediction.  With fewer than ``min_stars`` usable stars nothing changes.
    """
    out = stars.copy()
    out["lco_u_model"] = out["lco_u"]
    out["lco_u_model_err"] = out["lco_u_err"]
    use = (
        out["fit_ok"] & ~out["is_agn"]
        & (out["gspc_u_sdss_flag"] == 1)
        & out["gspc_u_sdss"].notna() & out["lco_u"].notna()
        & ~(out["gaia_ruwe"] > max_ruwe)
    )
    d = (out.loc[use, "lco_u"] - (out.loc[use, "gspc_u_sdss"] + sdss_u_ab_offset)).to_numpy()
    for _ in range(5):  # iterative sigma clip around the median
        if len(d) == 0:
            break
        med = np.median(d)
        sig = 1.4826 * np.median(np.abs(d - med))
        keep = np.abs(d - med) <= clip_sigma * max(sig, 1e-3)
        if keep.all():
            break
        d = d[keep]
    n = int(len(d))
    meta = {"applied": False, "n_stars": n, "min_stars": min_stars}
    if n < min_stars:
        return out, meta
    offset = float(np.median(d))
    scatter = float(1.4826 * np.median(np.abs(d - offset)))
    offset_err = float(1.253 * scatter / np.sqrt(n))
    out["lco_u"] = out["lco_u_model"] - offset
    out["lco_u_err"] = np.sqrt(out["lco_u_model_err"] ** 2 + offset_err**2)
    meta.update(applied=True, offset_mag=round(offset, 4), offset_err_mag=round(offset_err, 4),
                scatter_mag=round(scatter, 4), reference="Gaia DR3 GSPC SDSS u (AB = u - 0.04)")
    return out, meta


# ---------------------------------------------------------------------------
# Star identifiers
# ---------------------------------------------------------------------------

#: ``star_id`` of an AGN with no Gaia DR3 counterpart.
NO_GAIA_ID = -1


def assign_star_ids(
    cat: pd.DataFrame,
    ra: float,
    dec: float,
    gaia_ids: np.ndarray,
    gaia_ra: np.ndarray,
    gaia_dec: np.ndarray,
    agn_match_arcsec: float = 1.5,
    log=print,
) -> tuple[pd.DataFrame, dict]:
    """Key the catalogue on Gaia DR3 ``source_id`` and guarantee an AGN row.

    ``cat`` must have ``gaia_source_id`` (NaN where unmatched), ``ra``, ``dec``.
    ``gaia_*`` describe *all* Gaia DR3 sources in the field (any magnitude).

    * The AGN is the Gaia source nearest (ra, dec) within ``agn_match_arcsec``.
      Its row is marked ``is_agn``; if the catalogue has none (e.g. the nucleus
      is fainter than the GSPC limit) a row is added at the Gaia position, or at
      (ra, dec) with ``star_id = -1`` if Gaia has no source there.
    * Non-AGN rows without a Gaia id are dropped; duplicate ids keep the
      closest match.
    * ``gaia_source_id`` becomes ``star_id`` (first column); any row-number
      ``id`` column is removed — row numbers change between rebuilds.
    """
    from astropy.coordinates import SkyCoord

    cat = cat.copy()
    target = SkyCoord(ra, dec, unit="deg")
    agn_gid, agn_ra, agn_dec = NO_GAIA_ID, ra, dec
    if len(gaia_ids):
        sep = SkyCoord(gaia_ra, gaia_dec, unit="deg").separation(target).arcsec
        j = int(np.argmin(sep))
        if sep[j] <= agn_match_arcsec:
            agn_gid, agn_ra, agn_dec = int(gaia_ids[j]), float(gaia_ra[j]), float(gaia_dec[j])

    cat["is_agn"] = False
    hit = cat.index[cat["gaia_source_id"] == agn_gid] if agn_gid != NO_GAIA_ID else []
    if len(hit) == 0:
        # A catalogue row at the nucleus without that Gaia id (APASS, unmatched)?
        d = SkyCoord(cat["ra"].values, cat["dec"].values, unit="deg").separation(
            SkyCoord(agn_ra, agn_dec, unit="deg")).arcsec
        near = np.flatnonzero(d <= 2.0)
        if len(near):
            hit = [cat.index[near[np.argmin(d[near])]]]
            cat.loc[hit[0], "gaia_source_id"] = agn_gid
    if len(hit):
        cat.loc[hit[0], "is_agn"] = True
        added = False
    else:
        row = {c: np.nan for c in cat.columns}
        row.update(gaia_source_id=agn_gid, ra=agn_ra, dec=agn_dec, is_agn=True)
        if "ref_method" in cat:
            row["ref_method"] = cat["ref_method"].iat[0] if len(cat) else None
        cat = pd.concat([cat, pd.DataFrame([row])], ignore_index=True)
        added = True

    for col in ("is_agn", "quality_ok", "fit_ok", "gaia_neighbour"):
        if col in cat:
            cat[col] = cat[col].astype("boolean").fillna(False).astype(bool)

    keep = cat["is_agn"] | cat["gaia_source_id"].notna()
    n_drop = int((~keep).sum())
    cat = cat[keep]
    order = ["is_agn"] + (["gaia_sep_arcsec"] if "gaia_sep_arcsec" in cat else [])
    cat = cat.sort_values(order, ascending=[False] + [True] * (len(order) - 1))
    n_dup = int(cat.duplicated("gaia_source_id").sum())
    cat = cat.drop_duplicates("gaia_source_id", keep="first")

    cat["agn_sep_arcsec"] = SkyCoord(cat["ra"].values, cat["dec"].values, unit="deg").separation(
        target).arcsec
    cat = cat.drop(columns=[c for c in ("id",) if c in cat]).rename(columns={"gaia_source_id": "star_id"})
    cat["star_id"] = cat["star_id"].astype("int64")
    front = ["star_id", "ra", "dec", "agn_sep_arcsec", "is_agn"]
    cat = cat[front + [c for c in cat.columns if c not in front]]
    cat = cat.sort_values("dec").reset_index(drop=True)

    agn_row = cat[cat["is_agn"]].iloc[0]
    has_phot = bool(np.isfinite(agn_row[[c for c in cat.columns
                                         if c.startswith("lco_") and not c.endswith("_err")]]
                                .astype(float)).any())
    info = {
        "agn_star_id": int(agn_row["star_id"]),
        "agn_gaia_match": agn_gid != NO_GAIA_ID,
        "agn_sep_arcsec": round(float(agn_row["agn_sep_arcsec"]), 3),
        "agn_row_added": added,
        "agn_has_reference_photometry": has_phot,
        "dropped_no_gaia_id": n_drop,
        "dropped_duplicate_id": n_dup,
    }
    if agn_gid == NO_GAIA_ID:
        log(f"AGN: no Gaia DR3 source within {agn_match_arcsec}\" -> star_id {NO_GAIA_ID} "
            "at the target coordinates")
    else:
        log(f"AGN: Gaia DR3 {agn_gid} ({agn_row['agn_sep_arcsec']:.2f}\" from target)"
            + (" — added (no reference photometry)" if added else ""))
    if n_drop or n_dup:
        log(f"Dropped {n_drop} stars without a Gaia id and {n_dup} duplicate matches")
    return cat, info


# ---------------------------------------------------------------------------
# GSPC method
# ---------------------------------------------------------------------------

#: AB - Vega for Johnson-Kron-Cousins (Blanton & Roweis 2007; B, V as legacy).
JKC_VEGA_TO_AB = {"U": 0.79, "B": -0.09, "V": 0.02, "R": 0.21, "I": 0.45}
#: SDSS -> AB (u_AB = u - 0.04, z_AB = z + 0.02); PS1 is AB.
SDSS_TO_AB = {"u": -0.04, "g": 0.0, "r": 0.0, "i": 0.0, "z": 0.02}

#: LCO band -> (VizieR I/360 mag, flux, flag column, AB offset, reference system)
GSPC_TO_LCO = {
    "u": ("umag", "Fu", "uFlag", SDSS_TO_AB["u"], "SDSS u"),
    "B": ("Bmag", "FB", "BFlag", JKC_VEGA_TO_AB["B"], "JKC B"),
    "g": ("gmag", "Fg", "gFlag", SDSS_TO_AB["g"], "SDSS g"),
    "V": ("Vmag", "FV", "VFlag", JKC_VEGA_TO_AB["V"], "JKC V"),
    "r": ("rmag", "Fr", "rFlag", SDSS_TO_AB["r"], "SDSS r"),
    "R": ("Rmag", "FR", "RFlag", JKC_VEGA_TO_AB["R"], "JKC R"),
    "i": ("imag", "Fi", "iFlag", SDSS_TO_AB["i"], "SDSS i"),
    "I": ("Imag", "FI", "IFlag", JKC_VEGA_TO_AB["I"], "JKC I"),
    "z": ("zmag", "Fz", "zFlag", SDSS_TO_AB["z"], "SDSS z"),
    "Y": ("ymag", "Fy", "yFlag", 0.0, "PS1 y"),
}


def build_gspc_catalog(
    ra: float,
    dec: float,
    *,
    radius_arcmin: float,
    vizier_server: str | list[str],
    max_ruwe: float = 1.4,
    neighbour_arcsec: float = 3.0,
    neighbour_dmag: float = 2.5,
    agn_match_arcsec: float = 1.5,
    agn_ra: float | None = None,
    agn_dec: float | None = None,
    log=print,
) -> tuple[pd.DataFrame, dict]:
    """Reference stars from Gaia DR3 GSPC, mapped to LCO bands (AB).

    One row per GSPC source.  ``lco_<b>`` is NaN where the GSPC validity flag
    for that band is 0.  ``quality_ok`` = RUWE <= ``max_ruwe`` and no Gaia
    neighbour within ``neighbour_arcsec`` brighter than G + ``neighbour_dmag``
    (XP spectra of such stars are contaminated).
    """
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    c = SkyCoord(ra, dec, unit="deg")
    r = radius_arcmin * u.arcmin
    src, _ = vizier_query(vizier_server, c, r + neighbour_arcsec * u.arcsec, "I/355/gaiadr3")
    src = src.to_pandas()
    in_r = SkyCoord(src["RA_ICRS"].values, src["DE_ICRS"].values, unit="deg").separation(c) <= r
    n_xp = int(((src["XPcont"] == 1) & in_r).sum())

    def complete(t):
        # Some mirrors hold incomplete copies of I/360 (e.g. the NGC 5548
        # field on vizier.cfa.harvard.edu, Nov 2026): require most of the
        # Gaia sources with XP spectra to be present.
        if len(t) == 0 and n_xp == 0:
            return "no rows (and no Gaia XP sources)"
        return None if len(t) >= 0.8 * n_xp else f"incomplete ({len(t)} rows for {n_xp} Gaia XP sources)"

    table, server = vizier_query(vizier_server, c, r, "I/360/syntphot", accept=complete)
    sp = table.to_pandas()
    log(f"GSPC from {server}: {len(sp)} rows ({n_xp} Gaia sources with XP spectra)")

    cat = pd.DataFrame({"gaia_source_id": sp["Source"].astype("int64"),
                        "ra": sp["RA_ICRS"], "dec": sp["DE_ICRS"]})
    for b, (mag, flux, flag, ab, _) in GSPC_TO_LCO.items():
        ok = sp[flag] == 1
        cat[f"lco_{b}"] = np.where(ok, sp[mag] + ab, np.nan)
        cat[f"lco_{b}_err"] = np.where(ok, 1.0857 * sp["e_" + flux] / sp[flux], np.nan)
    cat["gspc_c_star"] = sp["E(BP/RP)corr"]

    g = src[["Source", "Gmag", "BP-RP", "Plx", "e_Plx", "RUWE", "RA_ICRS", "DE_ICRS"]].rename(columns={
        "Source": "gaia_source_id", "Gmag": "gaia_g", "BP-RP": "gaia_bp_rp", "Plx": "gaia_parallax",
        "e_Plx": "gaia_parallax_err", "RUWE": "gaia_ruwe", "RA_ICRS": "_ra", "DE_ICRS": "_dec"})
    g["gaia_source_id"] = g["gaia_source_id"].astype("int64")
    cat = cat.merge(g.drop(columns=["_ra", "_dec"]), on="gaia_source_id", how="left")

    # Contaminating neighbours (any Gaia source, not just GSPC ones)
    allc = SkyCoord(g["_ra"].values, g["_dec"].values, unit="deg")
    me = SkyCoord(cat["ra"].values, cat["dec"].values, unit="deg")
    i_me, i_all, sep, _ = allc.search_around_sky(me, neighbour_arcsec * u.arcsec) if len(cat) else ([], [], [], [])
    bad = np.zeros(len(cat), bool)
    gmag_all = g["gaia_g"].to_numpy()
    for a, b_ in zip(np.asarray(i_me), np.asarray(i_all)):
        if g["gaia_source_id"].iat[b_] == cat["gaia_source_id"].iat[a]:
            continue
        if gmag_all[b_] < cat["gaia_g"].iat[a] + neighbour_dmag:
            bad[a] = True
    cat["gaia_neighbour"] = bad
    cat["quality_ok"] = ~bad & ~(cat["gaia_ruwe"] > max_ruwe)

    cat["ref_method"] = "gspc"
    cat, agn_info = assign_star_ids(
        cat, ra if agn_ra is None else agn_ra, dec if agn_dec is None else agn_dec,
        g["gaia_source_id"].to_numpy(), g["_ra"].to_numpy(), g["_dec"].to_numpy(),
        agn_match_arcsec=agn_match_arcsec, log=log)
    cat.loc[cat["is_agn"], "quality_ok"] = False   # never a comparison star

    n_band = {b: int((cat[f"lco_{b}"].notna() & cat["quality_ok"] & ~cat["is_agn"]).sum()) for b in GSPC_TO_LCO}
    log(f"Gaia GSPC: {len(cat)} sources within {radius_arcmin:.1f}'; "
        f"{int(cat['quality_ok'].sum())} pass RUWE/neighbour cuts; usable per band: "
        + ", ".join(f"{b}={n}" for b, n in n_band.items()))

    meta = {
        "method": "gspc",
        "catalogue": "Gaia DR3 GSPC (VizieR I/360/syntphot)",
        "radius_arcmin": radius_arcmin,
        "n_stars": int(len(cat)),
        "n_quality_ok": int(cat["quality_ok"].sum()),
        "n_usable_per_band": n_band,
        **agn_info,
        "band_map": {b: f"{v[4]} {'(Vega->AB %+.2f)' % v[3] if v[4].startswith('JKC') else ('AB %+.2f' % v[3] if v[3] else 'AB')}"
                     for b, v in GSPC_TO_LCO.items()},
        "colour_terms": "none (identity); LCO vs reference filters differ by a few 0.01 mag",
        "quality_cuts": {"max_ruwe": max_ruwe, "neighbour_arcsec": neighbour_arcsec,
                         "neighbour_dmag": neighbour_dmag},
    }
    return cat, meta


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

def build_reference_catalog(ra: float, dec: float, *, method: str = "gspc",
                            fallback: str | None = "apass_model",
                            min_stars: int = 20, log=print, gspc: dict | None = None,
                            apass_model: dict | None = None,
                            agn_ra: float | None = None,
                            agn_dec: float | None = None) -> tuple[pd.DataFrame, dict]:
    """Build the reference catalogue with ``method``, falling back if needed.

    (ra, dec) is the field (pointing) centre used for the cone search;
    (agn_ra, agn_dec), if given, is the nucleus used to identify the AGN —
    they differ for offset pointings such as NGC 4395.

    ``gspc`` / ``apass_model`` hold the keyword arguments for
    :func:`build_gspc_catalog` / :func:`build_apass_model_catalog`.  The GSPC
    result is used if at least ``min_stars`` quality stars have g, r and i;
    otherwise (or on error) ``fallback`` is tried and the reason recorded.
    """
    gspc, apass_model = gspc or {}, apass_model or {}
    agn = dict(agn_ra=agn_ra, agn_dec=agn_dec)
    builders = {"gspc": lambda: build_gspc_catalog(ra, dec, log=log, **agn, **gspc),
                "apass_model": lambda: build_apass_model_catalog(ra, dec, log=log, **agn, **apass_model)}
    if method not in builders:
        raise ValueError(f"Unknown reference method {method!r}")
    try:
        cat, meta = builders[method]()
        meta["field_centre_deg"] = [ra, dec]
        meta["agn_position_deg"] = [ra if agn_ra is None else agn_ra, dec if agn_dec is None else agn_dec]
        if method == "gspc":
            n = min(meta["n_usable_per_band"][b] for b in ("g", "r", "i"))
            if n < min_stars:
                raise RuntimeError(f"only {n} usable GSPC stars in g/r/i (< {min_stars})")
        return cat, meta
    except Exception as exc:  # noqa: BLE001
        if not fallback or fallback == method:
            raise
        log(f"{method} failed ({exc}); falling back to {fallback}")
        cat, meta = builders[fallback]()
        meta["field_centre_deg"] = [ra, dec]
        meta["agn_position_deg"] = [ra if agn_ra is None else agn_ra, dec if agn_dec is None else agn_dec]
        meta["fallback_reason"] = f"{method}: {exc}"
        return cat, meta

def build_apass_model_catalog(
    ra: float,
    dec: float,
    *,
    apass_source: str,
    radius_arcmin: float,
    grid_path: Path,
    filters_dir: Path,
    apass_url: str = "",
    vizier_server: str | list[str] = ("vizier.cds.unistra.fr", "vizier.cfa.harvard.edu"),
    use_gaia: bool = True,
    dust_scale_height_pc: float = 125.0,
    min_parallax_snr: float = 5.0,
    gaia_match_arcsec: float = 1.5,
    n_draws: int = 1000,
    seed: int = 42,
    u_anchor: bool = True,
    u_anchor_min_stars: int = 10,
    u_anchor_max_ruwe: float = 1.4,
    raw_out: Path | None = None,
    agn_ra: float | None = None,
    agn_dec: float | None = None,
    log=print,
) -> tuple[pd.DataFrame, dict]:
    """Fallback method: APASS + atmosphere-model synthetic photometry.

    Returns ``(catalogue, meta)``.  ``raw_out``, if given, receives the raw
    APASS download (DR10 CSV) for provenance.
    """
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    # 1. APASS
    if apass_source == "aavso":
        raw = fetch_apass_dr10_aavso(ra, dec, radius_arcmin, apass_url)
        if raw_out is not None:
            Path(raw_out).write_bytes(raw)
        stars = clean_apass_dr10(raw)
        release = "APASS DR10 (AAVSO)"
    elif apass_source == "vizier":
        stars = clean_apass_dr9_vizier(fetch_apass_dr9_vizier(ra, dec, radius_arcmin, vizier_server))
        release = "APASS DR9 (VizieR II/336)"
    else:
        raise ValueError(f"Unknown apass_source {apass_source!r}")
    log(f"{release}: {len(stars)} stars within {radius_arcmin:.1f}'")

    agn = SkyCoord(ra, dec, unit="deg")
    stars["is_agn"] = False   # set properly by assign_star_ids below

    # 2. Gaia (required: Gaia DR3 source_id is the star identifier)
    if not use_gaia:
        raise ValueError("photometry.reference.gaia must be true: stars are keyed on Gaia DR3 source_id")
    gaia = fetch_gaia(ra, dec, radius_arcmin + 0.5, vizier_server)
    stars = match_gaia(stars, gaia, gaia_match_arcsec)
    log(f"Gaia DR3: {stars['gaia_source_id'].notna().sum()}/{len(stars)} matched")
    stars["ref_method"] = "apass_model"
    stars, agn_info = assign_star_ids(
        stars, ra if agn_ra is None else agn_ra, dec if agn_dec is None else agn_dec,
        gaia["gaia_source_id"].to_numpy(), gaia["gaia_ra"].to_numpy(),
        gaia["gaia_dec"].to_numpy(), agn_match_arcsec=gaia_match_arcsec, log=log)

    # 3. Extinction
    ebv_los = field_ebv_sf11(ra, dec)
    gal_b = agn.galactic.b.deg
    plx = stars["gaia_parallax"].astype(float)
    good = (plx / stars["gaia_parallax_err"].astype(float) >= min_parallax_snr) & (plx > 0)
    # Gaia DR3 parallax zero point (Lindegren+2021 global): -0.017 mas
    stars["dist_pc"] = np.where(good, 1000.0 / (plx + 0.017), np.nan)
    stars["ebv"] = star_ebv(ebv_los, stars["dist_pc"], gal_b, dust_scale_height_pc)
    log(f"E(B-V)_SF11 = {ebv_los:.4f} (b = {gal_b:.1f} deg); "
        f"{int(good.sum())} stars with parallax S/N >= {min_parallax_snr:g}")

    # 4. Synthetic photometry
    grid = AtmosphereGrid.load(grid_path)
    pivots = {b: pivot_wavelength(Path(filters_dir) / f"lco_{b}.txt") for b in LCO_BANDS}
    stars = synthetic_photometry(stars, grid, pivots, n_draws=n_draws, seed=seed)
    log(f"Synthetic photometry: {int(stars['fit_ok'].sum())}/{len(stars)} stars fitted")

    # 5. u-band anchor to Gaia GSPC
    if u_anchor and use_gaia:
        stars, u_meta = anchor_u(stars, min_stars=u_anchor_min_stars, max_ruwe=u_anchor_max_ruwe)
        if u_meta["applied"]:
            log(f"u anchored to GSPC: model - GSPC = {u_meta['offset_mag']:+.3f} "
                f"+/- {u_meta['offset_err_mag']:.3f} mag (n={u_meta['n_stars']}, "
                f"scatter {u_meta['scatter_mag']:.3f})")
        else:
            log(f"u NOT anchored: only {u_meta['n_stars']} usable GSPC u stars "
                f"(< {u_meta['min_stars']}); lco_u is the raw model prediction")
    else:
        u_meta = {"applied": False, "reason": "disabled"}

    meta = {
        "method": "apass_model",
        "apass_release": release,
        "radius_arcmin": radius_arcmin,
        "n_stars": int(len(stars)),
        "n_fitted": int(stars["fit_ok"].sum()),
        **agn_info,
        "ebv_sf11_los": ebv_los,
        "galactic_b_deg": float(gal_b),
        "dust_scale_height_pc": dust_scale_height_pc,
        "lco_pivot_angstrom": {b: round(v, 1) for b, v in pivots.items()},
        "atmosphere_grid": str(grid_path),
        "u_anchor": u_meta,
    }
    return stars, meta
