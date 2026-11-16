"""
ava.photometry.apertures — Aperture index resolution.

The SExtractor aperture series changed at MJD 60909 (2025-10-18): two smaller
diameters (3 px, 5 px) were prepended to the original 10-aperture series,
shifting all old indices by +2.  Using a fixed integer index across epochs
therefore samples different physical apertures, corrupting the light curves.

The correct solution is to look up the camera's known pixel scale and find the
aperture index whose physical diameter is closest to the configured science
aperture (default 5 arcsec radius = 10 arcsec diameter).

Aperture series
---------------
Old (pre-MJD 60909), 10 apertures, diameters in pixels:
  idx:  0    1    2    3    4    5    6    7    8    9
  px:   8   11   13   15   18   21   24   27   30   33

New (MJD 60909+), 12 apertures, diameters in pixels:
  idx:  0    1    2    3    4    5    6    7    8    9   10   11
  px:   3    5    8   11   13   15   18   21   24   27   30   33

Pixel scales by camera family
------------------------------
  Sinistro 1 m  (fa/fl):  0.389 arcsec/px
  Spectral 2 m  (fs):     0.304 arcsec/px
  MuSCAT3  2 m  (ep):     0.270 arcsec/px

Science aperture index for a 5 arcsec radius (10 arcsec diameter) target
-------------------------------------------------------------------------
  Sinistro, new series:  index  9  (27 px = 10.50 arcsec)
  Sinistro, old series:  index  7  (27 px = 10.50 arcsec)  <- same physical size
  Spectral, new series:  index 11  (33 px = 10.03 arcsec)
  Spectral, old series:  index  9  (33 px = 10.03 arcsec)  <- same physical size
  MuSCAT3,  new series:  index 11  (33 px =  8.91 arcsec)
  MuSCAT3,  old series:  index  9  (33 px =  8.91 arcsec)  <- same physical size

Usage
-----
    from ava.photometry.apertures import science_aperture_index, ApertureTable

    # By camera ID string (from FITS INSTRUME or lcodb instrument_id)
    idx = science_aperture_index('fa14', mjd=61000.0)
    idx = science_aperture_index('fs01', mjd=59000.0)

    # By camera type string
    idx = science_aperture_index('sinistro', mjd=61000.0)

    # With a custom target radius
    idx = science_aperture_index('fa14', mjd=61000.0, target_radius_arcsec=4.0)

    # Inspect the full table
    at = ApertureTable(mjd=61000.0)
    print(at)
    print(at.science_index('sinistro'))  # -> 9
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Aperture expansion epoch
# ---------------------------------------------------------------------------

#: MJD at which the 12-aperture series replaced the 10-aperture series.
#: Corresponds to 2025-10-18 UTC.
EXPANSION_MJD: float = 60909.0

# ---------------------------------------------------------------------------
# Aperture series (pixel diameters)
# ---------------------------------------------------------------------------

#: Old series (pre-MJD 60909), 10 aperture diameters in pixels.
OLD_DIAMETERS_PX: tuple[int, ...] = (8, 11, 13, 15, 18, 21, 24, 27, 30, 33)

#: New series (MJD 60909+), 12 aperture diameters in pixels.
NEW_DIAMETERS_PX: tuple[int, ...] = (3, 5, 8, 11, 13, 15, 18, 21, 24, 27, 30, 33)

# ---------------------------------------------------------------------------
# Camera pixel scales  (arcsec / pixel)
# ---------------------------------------------------------------------------

#: Pixel scale in arcsec/pixel for each camera family.
#: Keys: lowercase family name or instrument-id prefix.
PIXEL_SCALES: dict[str, float] = {
    # Sinistro — fa-series and old fl-series, 1 m telescopes
    "sinistro": 0.389,
    "fa":       0.389,
    "fl":       0.389,
    # Spectral — fs-series, 2 m Faulkes telescopes
    "spectral": 0.304,
    "fs":       0.304,
    # MuSCAT3 — ep-series, 2 m Haleakala
    "muscat3":  0.270,
    "muscat":   0.270,
    "ep":       0.270,
}


#: Science aperture radius (arcsec) when the caller gives none: photometry.science_aperture_radius_arcsec.
SCIENCE_RADIUS_ARCSEC: float = 5.25


def _load_config() -> None:
    """Take the aperture series, expansion epoch, pixel scales and science radius from the AVA config
    (``photometry.apertures.*``, ``photometry.pixel_scales``, ``photometry.science_aperture_radius_arcsec``);
    the module values above are the documented defaults.  Read once, at import."""
    global EXPANSION_MJD, OLD_DIAMETERS_PX, NEW_DIAMETERS_PX, SCIENCE_RADIUS_ARCSEC
    try:
        from ava.config import cfg

        ph = cfg._raw.get("photometry", {}) or {}
    except Exception:  # noqa: BLE001 — no config (e.g. a bare import): keep the defaults
        return
    ap = ph.get("apertures", {}) or {}
    if ap.get("expansion_mjd") is not None:
        EXPANSION_MJD = float(ap["expansion_mjd"])
    if ap.get("old_diameters_px"):
        OLD_DIAMETERS_PX = tuple(int(x) for x in ap["old_diameters_px"])
    if ap.get("new_diameters_px"):
        NEW_DIAMETERS_PX = tuple(int(x) for x in ap["new_diameters_px"])
    for k, v in (ph.get("pixel_scales") or {}).items():
        PIXEL_SCALES[str(k).lower()] = float(v)
    if ph.get("science_aperture_radius_arcsec") is not None:
        SCIENCE_RADIUS_ARCSEC = float(ph["science_aperture_radius_arcsec"])


_load_config()


def _pixscale_from_camera(camera: str) -> float:
    """Return the pixel scale (arcsec/px) for a camera ID or family name.

    Accepts the LCO instrument_id (e.g. ``'fa14'``, ``'fs01'``, ``'ep05'``),
    the camera family name (``'sinistro'``, ``'spectral'``, ``'muscat3'``),
    or a 2-character prefix (``'fa'``, ``'fs'``, ``'ep'``).

    Raises ``ValueError`` if the camera is not recognised.
    """
    c = camera.strip().lower()
    # Try exact match first (family names)
    if c in PIXEL_SCALES:
        return PIXEL_SCALES[c]
    # Try 2-character prefix (instrument IDs like 'fa14', 'fs01')
    prefix = c[:2]
    if prefix in PIXEL_SCALES:
        return PIXEL_SCALES[prefix]
    raise ValueError(
        f"Unrecognised camera {camera!r}.  Known cameras / prefixes: "
        + ", ".join(sorted(PIXEL_SCALES))
    )


def _diameter_series(mjd: float) -> tuple[int, ...]:
    """Return the correct diameter series for the given MJD."""
    return NEW_DIAMETERS_PX if mjd >= EXPANSION_MJD else OLD_DIAMETERS_PX


def default_sex_diameters() -> tuple[int, ...]:
    """PHOT_APERTURES of the versioned ``default.sex``
    (``photometry.sextractor.config_dir``); falls back to :data:`NEW_DIAMETERS_PX`.

    The series is APPEND-ONLY: larger apertures are added at the end, so the
    indices of existing apertures never change between extractions.
    """
    try:
        from ava.config import cfg
        path = cfg._resolve(cfg._raw["photometry"]["sextractor"]["config_dir"]) / "default.sex"
        for line in path.read_text().splitlines():
            parts = line.split("#", 1)[0].split()
            if len(parts) >= 2 and parts[0] == "PHOT_APERTURES":
                return tuple(int(float(x)) for x in "".join(parts[1:]).split(",") if x)
    except Exception:
        pass
    return NEW_DIAMETERS_PX


def diameter_series_for(n_apertures: int) -> tuple[int, ...]:
    """Aperture series of a catalogue from its number of apertures.

    * 10 apertures: the pre-2025 series (8 … 33 px);
    * otherwise: the first ``n_apertures`` of the current append-only
      ``default.sex`` series (12 = 3 … 33 px; more once apertures are appended).

    Prefer this (or the catalogue's ``APERDIAM`` header) over the MJD rule: a
    target re-extracted with the new default.sex has 12 apertures for ALL
    epochs (e.g. Mrk 817), and the MJD rule would then pick the wrong
    physical aperture for every pre-60909 frame.
    """
    if n_apertures == len(OLD_DIAMETERS_PX):
        return OLD_DIAMETERS_PX
    current = default_sex_diameters()
    if current[: len(NEW_DIAMETERS_PX)] != NEW_DIAMETERS_PX:
        raise ValueError("default.sex PHOT_APERTURES no longer starts with the 3…33 px series — "
                         "the series must be append-only")
    if len(NEW_DIAMETERS_PX) <= n_apertures <= len(current):
        return current[:n_apertures]
    raise ValueError(f"no known aperture series has {n_apertures} apertures "
                     f"(current default.sex has {len(current)})")


def configured_diameters_px(camera: str) -> tuple[int, ...]:
    """Aperture diameters (px) SExtractor uses for ``camera`` now:
    ``photometry.sextractor.camera_apertures_px`` (by 2-letter prefix, normally
    empty), else the ``default.sex`` series (:func:`default_sex_diameters`)."""
    try:
        from ava.config import cfg
        per = cfg._raw["photometry"]["sextractor"].get("camera_apertures_px") or {}
    except Exception:
        per = {}
    d = per.get(camera.strip().lower()[:2])
    return tuple(int(x) for x in d) if d else default_sex_diameters()


def science_aperture_index_for_catalog(
    camera: str,
    n_apertures: int,
    target_radius_arcsec: float | None = None,
    diameters_px: tuple | list | None = None,
) -> int:
    """Science aperture index for a catalogue.

    Uses the catalogue's own aperture diameters when known (``diameters_px``,
    from the ``APERDIAM`` header written by the SExtractor task), else the
    series implied by ``n_apertures`` (:func:`diameter_series_for`) — never
    the date.
    """
    if target_radius_arcsec is None:
        try:
            from ava.config import cfg
            target_radius_arcsec = float(cfg._raw["photometry"]["science_aperture_radius_arcsec"])
        except Exception:
            target_radius_arcsec = SCIENCE_RADIUS_ARCSEC
    target_diameter_px = 2.0 * target_radius_arcsec / _pixscale_from_camera(camera)
    diameters = tuple(diameters_px) if diameters_px else diameter_series_for(n_apertures)
    if len(diameters) != n_apertures:
        raise ValueError(f"{len(diameters)} aperture diameters for a catalogue with {n_apertures} apertures")
    # Only cameras listed in photometry.sextractor.extended_aperture_cameras may use the
    # appended (larger) apertures; the others keep their original choice among the first 12.
    if not _uses_extended_apertures(camera):
        diameters = diameters[: len(NEW_DIAMETERS_PX)]
    return int(np.argmin([abs(d - target_diameter_px) for d in diameters]))


def _uses_extended_apertures(camera: str) -> bool:
    try:
        from ava.config import cfg
        ext = cfg._raw["photometry"]["sextractor"].get("extended_aperture_cameras") or []
    except Exception:
        ext = []
    return camera.strip().lower()[:2] in [str(e).lower()[:2] for e in ext]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def science_aperture_index(
    camera: str,
    mjd: float,
    target_radius_arcsec: float | None = None,
) -> int:
    """Return the 0-based SExtractor aperture index closest to the target
    physical aperture for a given camera and observing epoch.

    Parameters
    ----------
    camera : str
        LCO instrument_id (e.g. ``'fa14'``, ``'fs01'``, ``'ep05'``) or
        camera family name (``'sinistro'``, ``'spectral'``, ``'muscat3'``).
    mjd : float
        Mid-exposure MJD.  Determines which aperture series applies:
        old 10-aperture series before MJD 60909, new 12-aperture series
        from MJD 60909 onward.
    target_radius_arcsec : float, optional
        Target aperture radius in arcsec.  Defaults to
        ``photometry.science_aperture_radius_arcsec`` from the AVA config
        (5.0 arcsec).

    Returns
    -------
    int
        0-based index into the aperture array stored in ``lco_latest.pkl``.

    Examples
    --------
    >>> science_aperture_index('fa14', mjd=61000.0)   # Sinistro, new series
    9
    >>> science_aperture_index('fs01', mjd=59000.0)   # Spectral, old series
    9
    >>> science_aperture_index('sinistro', mjd=61000.0)
    9
    """
    if target_radius_arcsec is None:
        try:
            from ava.config import cfg
            target_radius_arcsec = float(
                cfg._raw["photometry"]["science_aperture_radius_arcsec"]
            )
        except Exception:
            target_radius_arcsec = SCIENCE_RADIUS_ARCSEC

    pixscale = _pixscale_from_camera(camera)
    target_diameter_px = 2.0 * target_radius_arcsec / pixscale
    diameters = _diameter_series(mjd)
    diffs = [abs(d - target_diameter_px) for d in diameters]
    return int(np.argmin(diffs))


def physical_diameter_arcsec(
    camera: str,
    mjd: float,
    index: int,
) -> float:
    """Return the physical aperture diameter in arcsec for a given
    camera, epoch, and aperture index.

    Useful for auditing existing pkl files: pass the index stored in
    ``lco_latest.pkl`` to find out what physical aperture was actually used.

    Parameters
    ----------
    camera : str
        Camera ID or family name.
    mjd : float
        Mid-exposure MJD.
    index : int
        0-based aperture index stored in the photometry file.

    Returns
    -------
    float
        Physical aperture diameter in arcsec.
    """
    diameters = _diameter_series(mjd)
    if index < 0 or index >= len(diameters):
        raise IndexError(
            f"Index {index} out of range for the "
            f"{'new' if mjd >= EXPANSION_MJD else 'old'} aperture series "
            f"(0–{len(diameters) - 1})."
        )
    return diameters[index] * _pixscale_from_camera(camera)


def audit_aperture_index(
    stored_index: int,
    camera: str,
    mjd: float,
    target_radius_arcsec: float | None = None,
) -> dict:
    """Audit a stored aperture index from an existing pkl file.

    Returns a dict describing the physical aperture that was actually
    measured, the correct index for the target radius, and whether they
    agree.  Use this to identify frames that need re-extraction.

    Parameters
    ----------
    stored_index : int
        The aperture index as stored in ``lco_latest.pkl``.
    camera : str
        Camera ID or family name.
    mjd : float
        Mid-exposure MJD.
    target_radius_arcsec : float
        Intended aperture radius in arcsec.

    Returns
    -------
    dict with keys:
        stored_index, stored_diameter_arcsec,
        correct_index, correct_diameter_arcsec,
        target_diameter_arcsec, ok
    """
    correct = science_aperture_index(camera, mjd, target_radius_arcsec)
    stored_diam = physical_diameter_arcsec(camera, mjd, stored_index)
    correct_diam = physical_diameter_arcsec(camera, mjd, correct)
    return {
        "stored_index":           stored_index,
        "stored_diameter_arcsec": round(stored_diam, 3),
        "correct_index":          correct,
        "correct_diameter_arcsec": round(correct_diam, 3),
        "target_diameter_arcsec": 2.0 * target_radius_arcsec,
        "ok":                     stored_index == correct,
    }


# ---------------------------------------------------------------------------
# Aperture table helper
# ---------------------------------------------------------------------------

class ApertureTable:
    """Human-readable table of all aperture indices, pixel diameters, and
    physical diameters for each camera family.

    Parameters
    ----------
    mjd : float
        MJD determining which series applies (default: new series).
    """

    CAMERAS = ["sinistro", "spectral", "muscat3"]

    def __init__(self, mjd: float = EXPANSION_MJD):
        self.mjd = mjd
        self.diameters = _diameter_series(mjd)
        self.series = (
            f"new ({len(self.diameters)} apertures, MJD >= {EXPANSION_MJD})"
            if mjd >= EXPANSION_MJD
            else f"old ({len(self.diameters)} apertures, MJD < {EXPANSION_MJD})"
        )

    def science_index(
        self,
        camera: str,
        target_radius_arcsec: float | None = None,
    ) -> int:
        """Science aperture index for a camera at this epoch."""
        return science_aperture_index(camera, self.mjd, target_radius_arcsec)

    def __str__(self) -> str:
        cam_labels = ["Sinistro 1m", "Spectral 2m", "MuSCAT3 2m"]
        px_labels  = ["(0.389\"/px)", "(0.304\"/px)", "(0.270\"/px)"]
        header = (
            f"Aperture table  —  series: {self.series}\n"
            f"{'Index':>6}  {'Diam (px)':>10}  "
            + "  ".join(f"{c+' '+p:>26}" for c, p in zip(cam_labels, px_labels))
        )
        rows = []
        for i, d in enumerate(self.diameters):
            phys = "  ".join(
                f"{d * _pixscale_from_camera(cam):>26.2f}"
                for cam in self.CAMERAS
            )
            rows.append(f"{i:>6}  {d:>10}  {phys}")
        return header + "\n" + "\n".join(rows)

    def __repr__(self) -> str:
        return self.__str__()

    def to_latex(
        self,
        label: str = "tab:aper",
        caption: str | None = None,
        target_radius_arcsec: float | None = None,
    ) -> str:
        """Return a complete LaTeX table for inclusion in the pipeline manual.

        Rows matching the science aperture for each camera are marked bold.
        """
        if caption is None:
            series_label = "New" if self.mjd >= EXPANSION_MJD else "Old"
            mjd_cmp = r"MJD $\geq$" if self.mjd >= EXPANSION_MJD else r"MJD $<$"
            caption = f"{series_label} aperture series ({mjd_cmp} {EXPANSION_MJD:.0f})."

        sci_indices = {
            cam: science_aperture_index(cam, self.mjd, target_radius_arcsec)
            for cam in self.CAMERAS
        }

        cam_headers = " & ".join(
            [
                "\\makecell{Sinistro 1\\,m\\\\(0.389\\,\\arcsec/px)}",
                "\\makecell{Spectral 2\\,m\\\\(0.304\\,\\arcsec/px)}",
                "\\makecell{MuSCAT3 2\\,m\\\\(0.270\\,\\arcsec/px)}",
            ]
        )
        rows = []
        for i, d in enumerate(self.diameters):
            cells = []
            for cam in self.CAMERAS:
                val = f"{d * _pixscale_from_camera(cam):.2f}"
                cells.append(f"\\textbf{{{val}}}" if sci_indices[cam] == i else val)
            phys = " & ".join(cells)
            bold = any(sci_indices[cam] == i for cam in self.CAMERAS)
            bf_open = r"\textbf{" if bold else ""
            bf_close = r"}" if bold else ""
            row = f"    {bf_open}{i}{bf_close} & {d} & {phys} \\"
            rows.append(row)

        return (
            "\\begin{table}[h!]\n"
            "\\centering\n"
            "\\small\n"
            "\\begin{tabular}{rr rrr}\n"
            "\\toprule\n"
            " & & \\multicolumn{3}{c}{Physical diameter (arcsec)} \\\\\n"
            "\\cmidrule(lr){3-5}\n"
            f"Index & Diam (px) & {cam_headers} \\\\\n"
            "\\midrule\n"
            + "\n".join(rows)
            + "\n"
            "\\bottomrule\n"
            "\\end{tabular}\n"
            f"\\caption{{{caption}}}\n"
            f"\\label{{{label}}}\n"
            "\\end{table}"
        )
