"""
ava.photometry.catalogs — read SExtractor catalogues and tag detections with ``star_id``.

Each per-frame catalogue (``<frame>_cat.fits``, ``default.param`` columns,
``FITS_1.0``) is cross-matched by position to the target's reference
catalogue (``reference_stars.csv``, built once by ``-o``); every matched
detection gets that star's ``star_id`` (Gaia DR3 ``source_id``; the AGN row
has ``is_agn``).  ``star_id`` is the only identifier downstream (PyTICS,
zero points).

Matching
--------
1. nearest reference star within ``max_sep_arcsec`` (default 1.5");
2. the median RA/Dec offset of those matches is removed and the match
   repeated — absorbs small WCS shifts frame by frame;
3. one detection per star (the nearest wins), one star per detection.

Apertures
---------
The aperture series is read from the catalogue (number of apertures), not
inferred from the date — see
:func:`ava.photometry.apertures.science_aperture_index_for_catalog`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

#: Scalar SExtractor columns carried into the detections table.
SCALAR_COLS = {
    "NUMBER": "number", "ALPHA_J2000": "ra", "DELTA_J2000": "dec", "X_IMAGE": "x", "Y_IMAGE": "y",
    "FWHM_IMAGE": "fwhm_px", "FLAGS": "sex_flags", "ELONGATION": "elongation", "BACKGROUND": "background",
    "FLUX_MAX": "flux_max", "MAG_AUTO": "mag_auto", "MAGERR_AUTO": "magerr_auto",
}


#: Primary-header keyword with the aperture diameters (px) a catalogue was extracted with.
APERDIAM_KEY = "APERDIAM"


#: SExtractor magnitudes / errors at or above this are its "no measurement" value (99)
SEX_NO_MAG = 90.0

def format_aperdiam(diameters) -> str:
    return ",".join(str(int(d)) for d in diameters)


def parse_aperdiam(value) -> tuple | None:
    if not value:
        return None
    return tuple(int(x) for x in str(value).split(","))


def catalog_aperdiam(path: Path) -> tuple | None:
    """APERDIAM of a catalogue (None for legacy catalogues without it)."""
    from astropy.io import fits

    if not Path(path).exists():
        return None
    return parse_aperdiam(fits.getheader(path, 0).get(APERDIAM_KEY))


@dataclass
class Catalog:
    table: pd.DataFrame          # one row per detection (SCALAR_COLS, renamed)
    mag_aper: np.ndarray         # (n_detections, n_apertures)
    magerr_aper: np.ndarray
    n_apertures: int
    path: Path
    diameters_px: tuple | None = None   # from the APERDIAM header (None: legacy catalogue)

    def science_index(self, camera: str, target_radius_arcsec: float | None = None) -> int:
        from ava.photometry.apertures import science_aperture_index_for_catalog
        return science_aperture_index_for_catalog(camera, self.n_apertures, target_radius_arcsec,
                                                  diameters_px=self.diameters_px)


def read_catalog(path: Path) -> Catalog | None:
    """Read a SExtractor FITS_1.0 catalogue; None if it has no table / no rows."""
    from astropy.io import fits

    with fits.open(path, memmap=False) as h:
        diam = parse_aperdiam(h[0].header.get(APERDIAM_KEY))
        if len(h) < 2 or h[1].data is None or len(h[1].data) == 0:
            return None
        d = h[1].data
        names = d.columns.names
        table = pd.DataFrame({new: np.asarray(d[old]).astype(float if old != "FLAGS" else int)
                              for old, new in SCALAR_COLS.items() if old in names})
        mag = np.atleast_2d(np.asarray(d["MAG_APER"], dtype=float))
        err = np.atleast_2d(np.asarray(d["MAGERR_APER"], dtype=float))
    if mag.shape[0] != len(table):
        mag, err = mag.T, err.T
    return Catalog(table, mag, err, mag.shape[1], Path(path), diam)


def match_to_reference(cat: Catalog, ref: pd.DataFrame, max_sep_arcsec: float = 1.5,
                       recentre: bool = True, pixscale: float | None = None,
                       repair_wcs: bool = True, min_matches: int = 10,
                       recentre_radii_arcsec=(5.0, 15.0), min_recentre_stars: int = 5) -> tuple[pd.DataFrame, dict]:
    """Tag each detection with the reference ``star_id`` it matches (or <NA>).

    If fewer than ``min_matches`` stars match and ``pixscale`` (arcsec/px) is
    given, the frame's WCS is re-solved from star patterns
    (:func:`solve_wcs_from_patterns`) and the match repeated.

    Returns (table with star_id / is_agn / sep_arcsec, info: n_matched,
    offset_ra_arcsec, offset_dec_arcsec, agn_matched, wcs_repaired).
    """
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    t = cat.table.copy()
    det = SkyCoord(t["ra"].values * u.deg, t["dec"].values * u.deg)
    refc = SkyCoord(ref["ra"].values * u.deg, ref["dec"].values * u.deg)
    off_ra = off_dec = 0.0

    def _match(det):
        idx, d2d, _ = det.match_to_catalog_sky(refc)
        return idx, d2d.arcsec

    idx, sep = _match(det)
    ok = sep <= max_sep_arcsec
    if recentre:
        # Estimate the frame's WCS offset from the nearest matches, widening the
        # search when the WCS is off by more than max_sep (a few frames are).
        for r0 in (max_sep_arcsec, *recentre_radii_arcsec):
            near = sep <= r0
            if near.sum() >= min_recentre_stars:
                dra, ddec = det[near].spherical_offsets_to(refc[idx[near]])
                off_ra, off_dec = float(np.median(dra.arcsec)), float(np.median(ddec.arcsec))
                break
        if np.hypot(off_ra, off_dec) > 0.05:
            det = det.spherical_offsets_by(off_ra * u.arcsec, off_dec * u.arcsec)
            idx, sep = _match(det)
            ok = sep <= max_sep_arcsec

    # WCS repair: too few matches -> solve pixel -> sky from star patterns
    wcs_repaired = False
    if repair_wcs and pixscale and ok.sum() < min_matches:
        solved = solve_wcs_from_patterns(cat, ref, pixscale)
        if solved is not None:
            det2 = solved
            idx2, sep2 = _match(det2)
            if (sep2 <= max_sep_arcsec).sum() > ok.sum():
                det, idx, sep = det2, idx2, sep2
                ok = sep <= max_sep_arcsec
                wcs_repaired = True
                off_ra = off_dec = np.nan   # replaced by a full solution

    # one detection per reference star: keep the nearest
    cand = pd.DataFrame({"det": np.flatnonzero(ok), "ref": idx[ok], "sep": sep[ok]})
    cand = cand.sort_values("sep").drop_duplicates("ref", keep="first")
    t["star_id"] = pd.array([pd.NA] * len(t), dtype="Int64")
    t["is_agn"] = False
    t["sep_arcsec"] = np.nan
    t.loc[cand["det"].values, "star_id"] = ref["star_id"].values[cand["ref"].values]
    t.loc[cand["det"].values, "is_agn"] = ref["is_agn"].values[cand["ref"].values]
    t.loc[cand["det"].values, "sep_arcsec"] = cand["sep"].values
    info = dict(n_detections=len(t), n_matched=len(cand), offset_ra_arcsec=off_ra, offset_dec_arcsec=off_dec,
                agn_matched=bool(t["is_agn"].any()), wcs_repaired=wcs_repaired,
                median_sep_arcsec=float(np.median(cand["sep"])) if len(cand) else np.nan)
    return t, info


def solve_wcs_from_patterns(cat: Catalog, ref: pd.DataFrame, pixscale: float,
                            tries=((40, 80), (30, 120), (50, 150), (25, 60))):
    """Sky positions of all detections from a pattern (asterism) match of
    their pixel positions against the reference stars — a workaround for
    frames whose WCS failed, without astrometry.net or index files.

    1. Reference stars within the frame's footprint (around where the
       catalogue claims to point, + 2' margin) are projected on a tangent
       plane in pixel units (camera ``pixscale``).
    2. ``astroalign`` matches triangles of the brightest clean detections
       (pixel positions — independent of the WCS) to the brightest reference
       stars and fits a similarity transform (shift, rotation, scale).
       Several (n_detections, n_reference) sizes and both image parities are
       tried; the solution matching most stars within 1.5" wins.
    Returns a SkyCoord per detection, or None.  Validated on a good Mrk 817
    frame: recovers scale 1.002 and rotation -0.3 deg.
    """
    try:
        import astroalign
    except ImportError:
        return None
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    t = cat.table
    clean = (t["sex_flags"] == 0) if "sex_flags" in t else pd.Series(True, index=t.index)
    order = np.argsort(t["mag_auto"].where(clean, np.inf).to_numpy())
    xy = np.column_stack([t["x"].to_numpy(), t["y"].to_numpy()])
    centre = SkyCoord(np.nanmedian(t["ra"]) * u.deg, np.nanmedian(t["dec"]) * u.deg)
    half_diag = np.hypot(np.ptp(t["x"]), np.ptp(t["y"])) / 2 * pixscale / 60.0
    r = ref.dropna(subset=["ra", "dec"])
    r = r.sort_values("gaia_g") if "gaia_g" in r else r
    rsky = SkyCoord(r["ra"].values * u.deg, r["dec"].values * u.deg)
    r_in = rsky[rsky.separation(centre).arcmin <= half_diag + 2.0]
    if len(r_in) < 10 or clean.sum() < 10:
        return None
    frame = centre.skyoffset_frame()
    rc = r_in.transform_to(frame)
    tp = np.column_stack([rc.lon.to_value(u.arcsec), rc.lat.to_value(u.arcsec)]) / pixscale
    best, best_n = None, 0
    for n_src, n_ref in tries:
        src = xy[order[:n_src]]
        for parity in (-1.0, 1.0):          # LCO frames: parity -1 (x runs west)
            dst = tp[:n_ref] * np.array([parity, 1.0])
            try:
                T, _ = astroalign.find_transform(src, dst, max_control_points=max(n_src, n_ref))
            except Exception:  # noqa: BLE001 — no solution for this setup
                continue
            if not 0.9 < T.scale < 1.1:     # the pixel scale is known: reject wild solutions
                continue
            p = T(xy)
            sky = SkyCoord(parity * p[:, 0] * pixscale * u.arcsec, p[:, 1] * pixscale * u.arcsec,
                           frame=frame).icrs
            n = int((sky.match_to_catalog_sky(rsky)[1].arcsec <= 1.5).sum())
            if n > best_n:
                best, best_n = sky, n
        if best_n >= 20:
            break
    return best


def measurements(cat: Catalog, matched: pd.DataFrame, aperture_index: int) -> pd.DataFrame:
    """Matched detections in long form for PyTICS: one row per (frame, star).

    Columns: star_id, is_agn, mag, magerr (science aperture), sep_arcsec,
    x, y, fwhm_px, flags, ... ; plus the frame basename.
    """
    m = matched["star_id"].notna().to_numpy(copy=True)   # writable: pandas 3 (copy-on-write) gives a read-only view
    mag, err = cat.mag_aper[:, aperture_index], cat.magerr_aper[:, aperture_index]
    # SExtractor writes 99 for the magnitude and its error when the aperture flux is <= 0: no measurement (B11)
    m &= np.isfinite(mag) & np.isfinite(err) & (mag < SEX_NO_MAG) & (err < SEX_NO_MAG)
    out = matched.loc[m].copy()
    out["mag"] = mag[m]
    out["magerr"] = err[m]
    out.insert(0, "frame", cat.path.name.replace("_cat.fits", ""))
    return out.reset_index(drop=True)
