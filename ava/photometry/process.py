"""
ava.photometry.process — one catalogue -> one frame_qc row + measurement rows.

Steps: read the SExtractor catalogue, match detections to the reference
(``star_id``; WCS re-solved from star patterns if needed), pick the science
aperture from the catalogue's own aperture list, compute the zero point and
AGN magnitude (:mod:`ava.photometry.calibration`), and the frame QC numbers.
Frame metadata (time, filter, exposure, airmass, saturation, image size) comes
from the raw frame's SCI header (:func:`header_meta`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ava.photometry.apertures import _pixscale_from_camera, diameter_series_for
from ava.photometry.calibration import ZPSettings, calibrate_frame
from ava.photometry.catalogs import match_to_reference, measurements, read_catalog

PIPELINE_VERSION = "2026.11"


def header_meta(raw_path: Path) -> dict:
    """Frame metadata from the BANZAI SCI header of the raw (.fits.fz) frame."""
    from astropy.io import fits

    with fits.open(raw_path, memmap=False) as h:
        hd = (h["SCI"] if "SCI" in h else h[1]).header
        exptime = float(hd.get("EXPTIME", np.nan))
        mjd = float(hd.get("MJD-OBS", np.nan))
        return dict(
            filter=str(hd.get("FILTER", "")).replace("zs*diffuser", "zs").strip(),
            exptime=exptime, mjd_mid=mjd + exptime / 86400.0 / 2.0,
            day_obs=str(hd.get("DAY-OBS", "")), airmass=_num(hd.get("AIRMASS")),
            seeing_hdr=_num(hd.get("L1FWHM")), saturate=_num(hd.get("SATURATE")),
            naxis1=_num(hd.get("NAXIS1") or hd.get("ZNAXIS1")), naxis2=_num(hd.get("NAXIS2") or hd.get("ZNAXIS2")),
            site=str(hd.get("SITEID", "")))


def _num(v):
    try:
        x = float(v)
        return x if np.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def process_catalog(cat_path: Path, ref: pd.DataFrame, meta: dict, data_id: str,
                    settings: ZPSettings | None = None) -> tuple[dict, pd.DataFrame]:
    """Returns (frame_qc row, measurement rows incl. the AGN)."""
    cat_path = Path(cat_path)
    frame = cat_path.name[: -len("_cat.fits")]
    parts = frame.split("-")
    cam = parts[1]
    row = dict(frame=frame, data_id=data_id, camera=cam, tel=parts[0][-5:], site=meta.get("site") or parts[0][:3],
               **{k: meta.get(k) for k in ("mjd_mid", "day_obs", "filter", "exptime", "airmass", "seeing_hdr",
                                           "saturate", "naxis1", "naxis2")},
               pipeline_version=PIPELINE_VERSION,
               processed_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    cat = read_catalog(cat_path)
    if cat is None:
        row.update(n_detections=0, n_matched=0, qc_flags="empty_catalogue", qc_pass=0)
        return row, pd.DataFrame()
    ps = _pixscale_from_camera(cam)
    k = cat.science_index(cam)
    diam = (cat.diameters_px or diameter_series_for(cat.n_apertures))[k]
    m, info = match_to_reference(cat, ref, pixscale=ps, **MATCH_KW)
    meas = measurements(cat, m, k)
    t = cat.table
    clean = m["star_id"].notna() & (t["sex_flags"] == 0)
    row.update(n_detections=info["n_detections"], n_matched=info["n_matched"],
               wcs_offset_arcsec=float(np.hypot(info["offset_ra_arcsec"], info["offset_dec_arcsec"]))
               if np.isfinite(info["offset_ra_arcsec"]) else np.nan,
               wcs_repaired=int(info["wcs_repaired"]), n_apertures=cat.n_apertures, aperture_index=k,
               aperture_px=float(diam), aperture_arcsec=float(diam * ps),
               fwhm_arcsec=float(np.median(t.loc[clean, "fwhm_px"]) * ps) if clean.any() else np.nan,
               background=float(np.median(t.loc[clean, "background"])) if clean.any() else np.nan,
               ellipticity=float(np.median(1 - 1 / t.loc[clean, "elongation"])) if clean.any() else np.nan,
               agn_matched=int(info["agn_matched"]))
    cal, zp, agn = calibrate_frame(meas, ref, filt=meta.get("filter", ""), exptime=float(meta.get("exptime") or 1.0),
                                   saturate=meta.get("saturate"), naxis1=meta.get("naxis1"),
                                   naxis2=meta.get("naxis2"), settings=settings)
    row.update(zp=zp.zp, zp_err=zp.zp_err, zp_scatter=zp.zp_scatter, zp_chi2nu=zp.chi2_nu, n_zp=zp.n_used,
               n_zp_candidates=zp.n_candidates, colour_slope=zp.colour_slope,
               agn_flags=agn.get("sex_flags") if agn else None)
    cal["frame"] = frame
    out = cal[["frame", "star_id", "is_agn", "mag_inst", "magerr", "x", "y", "sex_flags", "sep_arcsec",
               "used_in_zp"]].copy()
    return row, out


def _qc_for(q: dict, filt, camera=None) -> dict:
    """Thresholds for one frame: photometry.qc, then per_filter[filt], then
    per_camera[2-letter camera prefix] on top."""
    def _get(key, name):
        d = q.get(key) or {}
        d = vars(d) if hasattr(d, "__dict__") else d
        o = d.get(name) or {}
        return vars(o) if hasattr(o, "__dict__") else o
    base = {k: v for k, v in q.items() if k not in ("per_filter", "per_camera")}
    return {**base, **_get("per_filter", filt), **_get("per_camera", (camera or "")[:2])}


def qc_flags(row: dict, q: dict) -> list[str]:
    """Frame-level QC reasons from the stored frame values (empty list = pass).
    ``q``: photometry.qc thresholds (per-filter overrides applied here)."""
    if str(row.get("qc_flags") or "").startswith(("empty_catalogue", "error:")):
        return [row["qc_flags"]]
    q = _qc_for(q, row.get("filter"), row.get("camera"))
    num = lambda k: row.get(k) if row.get(k) is not None and np.isfinite(row.get(k)) else np.nan  # noqa: E731
    f = []
    if not np.isfinite(num("zp")):
        f.append("no_zp")
    if (row.get("n_matched") or 0) < q["min_matched"]:
        f.append("few_matched")
    if not row.get("agn_matched"):
        f.append("agn_missing")
    elif row.get("agn_flags") not in (0, None) and np.isfinite(num("agn_flags")):
        f.append("agn_flagged")
    if num("zp_scatter") > q["max_zp_scatter"]:
        f.append("zp_scatter")
    if num("fwhm_arcsec") > q["max_fwhm_arcsec"]:
        f.append("seeing")
    if abs(num("zp_dev")) > q["max_zp_dev"]:
        f.append("zp_offset")
    return f


def requalify(frame_db: Path, data_id: str, q: dict) -> pd.DataFrame:
    """Recompute every frame's QC flags from the stored frame_qc values (no
    recalibration) — run after changing photometry.qc thresholds."""
    from ava.photometry import store

    fq = store.read_frame_qc(frame_db, data_id)
    if fq.empty:
        return fq
    fq["zp_dev"] = fq["zp"] - fq.groupby([fq["camera"].str[:2], "filter"])["zp"].transform("median")
    upd = []
    for r in fq.to_dict("records"):
        flags = ",".join(qc_flags(r, q))
        if flags != (r["qc_flags"] or "") or int(not flags) != r["qc_pass"]:
            r["qc_flags"], r["qc_pass"] = flags, int(not flags)
            upd.append(r)
    store.write_frame_qc(frame_db, upd)
    return store.read_frame_qc(frame_db, data_id)


# ---------------------------------------------------------------------------
# Whole target
# ---------------------------------------------------------------------------

def imaging_prefixes() -> tuple[str, ...]:
    """Camera-name prefixes of the imaging cameras (photometry.imaging_camera_prefixes)."""
    try:
        from ava.config import cfg

        v = (cfg._raw.get("photometry", {}) or {}).get("imaging_camera_prefixes")
    except Exception:  # noqa: BLE001
        v = None
    return tuple(v) if v else ("fa", "fl", "fs", "ep")


IMAGING_PREFIXES = imaging_prefixes()


def camera_telescopes() -> dict[str, tuple[str, ...]]:
    """Camera prefix -> telescope classes it is used on (photometry.camera_telescopes), e.g. SBIG kb -> 1m0:
    the 0.4 m SBIG cameras share the prefix but have another pixel scale, so they are never extracted."""
    try:
        from ava.config import cfg

        v = (cfg._raw.get("photometry", {}) or {}).get("camera_telescopes") or {}
    except Exception:  # noqa: BLE001
        v = {}
    return {str(k).lower(): tuple(str(t).lower() for t in ts) for k, ts in v.items()}


def imaging_frame_ok(name: str, telescope: str | None = None, prefixes=None, telescopes=None) -> bool:
    """True if a frame belongs to the photometry: imaging camera prefix and, for cameras restricted in
    ``photometry.camera_telescopes``, the right telescope class. ``name`` is an LCO basename
    (``elp1m008-kb74-20140608-0035-e91``, telescope class taken from it) or an instrument id (``kb74``,
    then ``telescope`` = the archive ``telescope_id``, e.g. ``1m0a``)."""
    prefixes = IMAGING_PREFIXES if prefixes is None else tuple(prefixes)
    telescopes = camera_telescopes() if telescopes is None else telescopes
    parts = str(name).split("-")
    inst = (parts[1] if len(parts) > 1 else parts[0]).lower()
    if inst[:2] not in prefixes:
        return False
    allowed = telescopes.get(inst[:2])
    if not allowed:
        return True
    tel = (telescope or (parts[0][3:6] if len(parts) > 1 else "")).lower()
    return any(tel.startswith(t) for t in allowed)


def match_settings() -> dict:
    """Catalogue-to-reference matching (photometry.matching): max_sep_arcsec, min_matches (below it the WCS is
    re-solved), recentre_radii_arcsec (wider searches for the frame offset), min_recentre_stars."""
    try:
        from ava.config import cfg

        m = dict((cfg._raw.get("photometry", {}) or {}).get("matching") or {})
    except Exception:  # noqa: BLE001
        m = {}
    out = {}
    for k, cast in (("max_sep_arcsec", float), ("min_matches", int), ("min_recentre_stars", int)):
        if m.get(k) is not None:
            out[k] = cast(m[k])
    if m.get("recentre_radii_arcsec"):
        out["recentre_radii_arcsec"] = tuple(float(x) for x in m["recentre_radii_arcsec"])
    return out


MATCH_KW = match_settings()


def _work(args):
    cat_path, ref, meta, data_id, settings, q = args
    try:
        row, meas = process_catalog(cat_path, ref, meta, data_id, settings)
    except Exception as exc:  # noqa: BLE001 — one bad catalogue must not stop the target
        frame = Path(cat_path).name[: -len("_cat.fits")]
        return dict(frame=frame, data_id=data_id, qc_flags=f"error:{type(exc).__name__}", qc_pass=0,
                    pipeline_version=PIPELINE_VERSION), pd.DataFrame()
    flags = qc_flags(row, q)            # provisional; requalify() adds the target-level checks
    row["qc_flags"], row["qc_pass"] = ",".join(flags), int(not flags)
    return row, meas


def calibrate_target(data_id: str, *, catdir: Path, phot_dir: Path, ref: pd.DataFrame, frame_db: Path,
                     meta_provider, settings: ZPSettings, q: dict, force: bool = False,
                     max_frames: int | None = None, frames: list[str] | None = None,
                     n_workers: int = 1, chunk_size: int = 2000, log=print) -> dict:
    """Calibrate every (new) catalogue of a target; update frame_qc, measurements, AGN light curve.

    ``meta_provider(frame) -> dict | None`` gives frame metadata (normally
    :func:`header_meta` of the raw frame); None skips the frame.
    """
    from ava.photometry import store

    done = store.read_frame_qc(frame_db, data_id)
    done = set(done.loc[done["pipeline_version"] == PIPELINE_VERSION, "frame"]) if not force else set()
    cats = sorted(p for p in Path(catdir).glob("*_cat.fits") if imaging_frame_ok(p.name))
    if frames is not None:
        keep = set(frames)
        cats = [p for p in cats if p.name[: -len("_cat.fits")] in keep]
    todo = [p for p in cats if p.name[: -len("_cat.fits")] not in done][: max_frames]
    jobs, skipped = [], 0
    for p in todo:
        meta = meta_provider(p.name[: -len("_cat.fits")])
        if meta is None:
            skipped += 1
            continue
        jobs.append((p, ref, meta, data_id, settings, q))
    log(f"{data_id}: {len(cats)} catalogues, {len(done)} already calibrated, {len(jobs)} to do"
        + (f", {skipped} without metadata" if skipped else ""))
    if not jobs:
        return dict(catalogues=len(cats), processed=0)
    # Process in chunks; each chunk is written (frame_qc + measurements) as soon as it is done,
    # so a long run shows progress and an interrupted run resumes where it stopped.
    from contextlib import nullcontext
    from multiprocessing import get_context

    n_done, n_rows = 0, 0
    ctx = get_context("spawn").Pool(n_workers) if n_workers > 1 else nullcontext()
    with ctx as pool:
        for start in range(0, len(jobs), chunk_size):
            chunk = jobs[start:start + chunk_size]
            results = pool.map(_work, chunk, chunksize=20) if pool else [_work(j) for j in chunk]
            rows = [r for r, _ in results]
            parts = [m for _, m in results if len(m)]
            store.write_frame_qc(frame_db, rows)
            if parts:
                n_rows = store.update_measurements(Path(phot_dir) / "measurements.parquet",
                                                   pd.concat(parts, ignore_index=True))
            n_done += len(rows)
            log(f"{data_id}: {n_done}/{len(jobs)} frames calibrated")

    # all QC flags from the stored values, incl. ZP vs the camera/filter median (clouds, focus)
    requalify(frame_db, data_id, q)
    lc = store.write_agn_lightcurve(phot_dir, frame_db, data_id)
    fq = store.read_frame_qc(frame_db, data_id)
    out = dict(catalogues=len(cats), processed=n_done, measurement_rows=n_rows,
               qc_pass=int(fq["qc_pass"].sum()), frames_total=len(fq), agn_points=len(lc))
    log(f"{data_id}: processed {n_done}; frame_qc {len(fq)} frames ({out['qc_pass']} pass); "
        f"measurements.parquet {n_rows} rows; AGN light curve {len(lc)} points")
    return out
