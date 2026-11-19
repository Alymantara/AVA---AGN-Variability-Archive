"""
SExtractor task — build source catalogues for one target's frames.

Port of ``__old_pipeline__/ava_sextractor.py`` (run by ``ava_update.py -e``).
Runs on the production machine only (needs the ``sex`` binary).

Behaviour
---------
For every ``cfg.phot_raw(target) / YYYYMMDD / *-e91.fits.fz`` without a
``<frame>_cat.fits`` in ``cfg.sextractor_dir(target)`` (non-empty frames,
newest first, at most ``photometry.sextractor.max_frames_per_run``):

1. write the SCI extension to a uniquely named temporary file (deleted
   afterwards; the legacy fixed ``temp_sextractor_file.fits`` would collide
   between parallel targets);
2. run SExtractor with the versioned configuration in
   ``photometry.sextractor.config_dir`` (``default.sex`` — 12-aperture
   series 3…33 px — ``default.param``, ``default.conv``, ``default.nnw``),
   ``-GAIN`` from the header, no check-image / XML;
3. ``-PHOT_APERTURES`` = the append-only ``default.sex`` series (or a
   per-camera override, none in use), and the diameters used are written to
   the catalogue header ``APERDIAM``;
4. move the catalogue into place atomically.

With ``reextract_on_aperture_change`` (off by default), catalogues whose
``APERDIAM`` differs from the current series are re-extracted — e.g. MuSCAT
once larger apertures have been appended (scheduled for a later date).

Dropped from the legacy script: the astrometry.net ``solve-field`` call — its
output (``.new``) was never the file SExtractor ran on.  Frames whose BANZAI
WCS is off are caught and, when possible, re-solved from star patterns when
catalogues are matched to the reference (``ava.photometry.catalogs``).

Inputs:  target (data_id), dry_run (list only).
Outputs: dict — frames on disk, catalogues present, to extract, extracted, failed.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from prefect import get_run_logger, task

from ava.config import cfg


from ava.photometry.process import imaging_frame_ok  # noqa: E402  (imaging_camera_prefixes, camera_telescopes)


def newest_first_key(name: str) -> tuple:
    """Sort key for 'newest first': the observing date and frame number in the LCO name
    (``<site><tel>-<camera>-<YYYYMMDD>-<NNNN>-e91``), then the name. Sorting by name alone ordered by site and
    telescope (B18), so a capped run (``max_frames_per_run``) extracted whole sites before recent frames."""
    parts = name.split("-")
    date = parts[2] if len(parts) > 3 and parts[2].isdigit() else ""
    num = parts[3] if len(parts) > 3 and parts[3].isdigit() else ""
    return date, num, name


#: SExtractor's executable names: Debian/Ubuntu package `source-extractor`; `sex` from source / conda-forge
SEXTRACTOR_NAMES = ("source-extractor", "sex")


def sextractor_binary(configured: str | None) -> str | None:
    """The configured SExtractor (a path or a name on PATH), else whichever of its usual names is installed."""
    for name in ([configured] if configured else []) + [n for n in SEXTRACTOR_NAMES if n != configured]:
        found = shutil.which(name)
        if found:
            return found
    return None


def frames_to_extract(target: str) -> tuple[list[Path], int, int]:
    """(frames without a catalogue, newest first; n frames; n catalogues)."""
    raw, catdir = cfg.phot_raw(target), cfg.sextractor_dir(target)
    frames = sorted(raw.glob("2*/*e91.fits.fz"), key=lambda p: newest_first_key(p.name), reverse=True)
    # imaging cameras only (Sinistro fa/fl, Spectral fs, MuSCAT ep, SBIG kb on the 1 m) — FLOYDS (en) products
    # are handled by the spectroscopy pipeline; the legacy glob extracted them too.
    frames = [f for f in frames if imaging_frame_ok(f.name)]
    have = {p.name[: -len("_cat.fits")] for p in catdir.glob("*_cat.fits")} if catdir.exists() else set()
    todo = [f for f in frames if f.name[: -len(".fits.fz")] not in have and f.stat().st_size > 0]
    # Re-extract catalogues made with a different aperture series than now configured for their
    # camera (e.g. MuSCAT before camera_apertures_px).  Legacy catalogues without APERDIAM are
    # assumed to use the default.sex series.  Only cameras with their own series are checked.
    if cfg.photometry.sextractor.get("reextract_on_aperture_change", False):
        from ava.photometry.apertures import configured_diameters_px, diameter_series_for
        from ava.photometry.catalogs import catalog_aperdiam

        cams = [str(c)[:2] for c in (cfg.photometry.sextractor.get("reextract_cameras") or [])]
        for f in frames:
            base = f.name[: -len(".fits.fz")]
            cam = f.name.split("-")[1]
            if cams and cam[:2] not in cams:
                continue
            want = configured_diameters_px(cam)
            if base in have:
                got = catalog_aperdiam(catdir / f"{base}_cat.fits") or diameter_series_for(12)
                if tuple(got) != tuple(want):
                    todo.append(f)
    return todo, len(frames), len(have)


def extract_one(frame: Path, catdir: Path, binary: str, confdir: Path, timeout: float = 600.0) -> Path:
    """Run SExtractor on one frame; returns the catalogue path.

    The SCI image goes to a uniquely named temporary file next to the
    catalogue (deleted afterwards), so parallel targets never collide.
    """
    from astropy.io import fits

    from ava.photometry.apertures import configured_diameters_px
    from ava.photometry.catalogs import APERDIAM_KEY, format_aperdiam

    catdir.mkdir(parents=True, exist_ok=True)
    out = catdir / (frame.name[: -len(".fits.fz")] + "_cat.fits")
    diameters = configured_diameters_px(frame.name.split("-")[1])
    with tempfile.NamedTemporaryFile(suffix=".fits", prefix="sex_", dir=catdir, delete=True) as tmp:
        with fits.open(frame, memmap=False) as h:
            sci = h["SCI"] if "SCI" in h else h[1]
            hdr = sci.header.copy()
            for k in ("XTENSION", "PCOUNT", "GCOUNT", "ZIMAGE", "ZBITPIX", "ZNAXIS", "ZNAXIS1", "ZNAXIS2",
                      "ZTILE1", "ZTILE2", "ZCMPTYPE", "ZQUANTIZ", "ZDITHER0"):
                hdr.pop(k, None)
            fits.PrimaryHDU(data=sci.data, header=hdr).writeto(tmp.name, overwrite=True)
            gain = hdr.get("GAIN", 1.0)
        part = out.with_suffix(".fits.part")
        cmd = [binary, tmp.name, "-c", str(confdir / "default.sex"),
               "-PARAMETERS_NAME", str(confdir / "default.param"),
               "-FILTER_NAME", str(confdir / "default.conv"),
               "-STARNNW_NAME", str(confdir / "default.nnw"),
               "-CATALOG_NAME", str(part), "-CATALOG_TYPE", "FITS_1.0", "-GAIN", str(gain),
               "-PHOT_APERTURES", format_aperdiam(diameters),
               "-CHECKIMAGE_TYPE", "NONE", "-WRITE_XML", "N", "-VERBOSE_TYPE", "QUIET"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0 or not part.exists():
        part.unlink(missing_ok=True)
        raise RuntimeError(f"SExtractor failed ({r.returncode}): {r.stderr.strip()[-300:]}")
    fits.setval(part, APERDIAM_KEY, value=format_aperdiam(diameters), ext=0,
                comment="aperture diameters (px) used by SExtractor")
    part.replace(out)
    return out


@task(name="sextract", tags=["sextractor"])
def sextract(target: str, dry_run: bool = False) -> dict:
    """Run SExtractor on un-catalogued frames of ``target``."""
    logger = get_run_logger()
    sc = cfg.photometry.sextractor
    todo, n_frames, n_cats = frames_to_extract(target)
    todo = todo[: int(sc.max_frames_per_run)]
    out = dict(target=target, frames=n_frames, catalogues=n_cats, to_extract=len(todo), extracted=0, failed=0)
    logger.info("%s: %d frames on disk, %d catalogues, %d to extract (this run)", target, n_frames, n_cats, len(todo))
    if dry_run or not todo:
        return out
    binary = sextractor_binary(sc.binary)
    if binary is None:
        raise RuntimeError(f"SExtractor binary {sc.binary!r} not found on this machine (also tried "
                           f"{' / '.join(SEXTRACTOR_NAMES)}; photometry.sextractor.binary)")
    confdir = cfg._resolve(sc.config_dir)
    failed = {}
    for f in todo:
        try:
            extract_one(f, cfg.sextractor_dir(target), binary, confdir)
            out["extracted"] += 1
        except Exception as exc:  # noqa: BLE001 — keep going, report at the end
            failed[f.name] = f"{type(exc).__name__}: {exc}"
    out["failed"] = len(failed)
    logger.info("%s: extracted %d, failed %d", target, out["extracted"], len(failed))
    for name, why in list(failed.items())[:10]:
        logger.warning("  failed %s: %s", name, why)
    if failed:
        raise RuntimeError(f"{target}: {len(failed)} frame(s) failed SExtractor")
    return out
