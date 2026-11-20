"""
Ensemble task — PyTICS intercalibration of the calibrated photometry.

Runs after ``calibrate`` (needs ``frame_qc`` + ``measurements.parquet``) and
writes, in ``cfg.phot_dir(target)``:

  pytics/<filter>/{stars,scopes,epochs,star_scope}.parquet + meta.json
                                    the stored solution (read back by updates)
  pytics/absolute_zp_stars.parquet  star means vs reference_stars.csv
  pytics/intercal.csv               flux-flux fit of every scope vs the Sinistro reference
  agn_lightcurve_pytics.parquet/.csv
                                    AGN: ensemble-calibrated, absolute (AB), with the
                                    additive camera correction in mag_ic / F_ic (mJy)
  <target>_LCO_merged_lightcurve.csv
                                    shareable product (``#`` header): good epochs, total errors, zp_err_mag
  <target>_LCO_merged_lightcurve_qc.csv
                                    every epoch with the QC columns (``ensemble.export_qc_csv``)

``mode="full"`` refits the whole data set on demand (~1 min for Mrk 817,
21k frames, 8 filters); ``mode="auto"`` (daily) adds only the new frames to
the stored solution (tens of ms per filter) and refits when the update says
so.  Merged light-curve figures go to ``cfg.target_plots_dir(target)`` as
``lco_latest_<obj>_merged[_last6|_season]``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from prefect import get_run_logger, task

from ava.config import cfg


def _matches(scope: str, prefixes) -> bool:
    cam = scope.split("-", 1)[-1]
    return any(cam.startswith(p) for p in prefixes)


def intercal_lightcurve(phot: Path, ec) -> pd.DataFrame:
    """Flux-flux fit vs the reference cameras; correct the configured cameras."""
    from ava.photometry import intercal as IC

    lc = pd.read_parquet(phot / "agn_lightcurve_pytics.parquet")
    scopes = sorted(lc["scope"].unique())
    ref = [s for s in scopes if _matches(s, ec.intercal_reference_cameras)]
    table = IC.intercalibrate(lc, ref, max_gap=float(ec.intercal_max_gap_days),
                              min_pairs=int(ec.get("intercal_min_pairs", 10)))
    table["corrected"] = table["scope"].map(lambda s: _matches(s, ec.intercal_correct_cameras))
    fix = [s for s in scopes if _matches(s, ec.intercal_correct_cameras)]
    if ec.get("intercal_per_season", False):
        # one additive offset per observing season for the corrected cameras (MuSCAT step
        # between seasons, docs/notes/future_improvements.md); the all-data fit fills seasons
        # with too few pairs
        lc["season"] = IC.seasons(lc["MJD"], float(ec.get("intercal_season_gap_days", 60.0)))
        ts = IC.intercalibrate_by_season(lc, ref, fix, max_gap=float(ec.intercal_max_gap_days),
                                         min_pairs=int(ec.get("intercal_min_pairs", 10)))
        table = pd.concat([table.assign(season=-1), ts.assign(corrected=True)], ignore_index=True)
    table.to_csv(phot / "pytics" / "intercal.csv", index=False)
    out = IC.apply_intercal(lc, table, scopes=fix, additive_only=True)
    out = add_error_model(out, phot, ec)
    out.to_parquet(phot / "agn_lightcurve_pytics.parquet", compression="zstd", index=False)
    out.to_csv(phot / "agn_lightcurve_pytics.csv", index=False, float_format="%.6f")
    return out


def add_error_model(lc: pd.DataFrame, phot: Path, ec) -> pd.DataFrame:
    """Fit the empirical error model (ava.photometry.errors) on the AGN pairs and add
    mag_err_model[_rand] / Ferr_model[_rand]; always computed, used for the products when
    ``error_model: fitted`` (the default since 19 Nov 2026: it has the floor the PyTICS errors lack)."""
    from ava.photometry import errors as ER

    d = ec.get("error_model_default")
    d = vars(d) if hasattr(d, "__dict__") else d
    default = {k: float(v) for k, v in (d or ER.DEFAULT).items()}
    table = ER.fit_error_model(lc, mag="mag_ic", max_dt=float(ec.get("error_model_max_dt_hours", 1.0)) / 24,
                               max_dt_cross=float(ec.get("error_model_cross_dt_days", 0.25)),
                               min_pairs=int(ec.get("error_model_min_pairs", 150)),
                               min_cross_pairs=int(ec.get("error_model_min_cross_pairs", 30)),
                               min_error_range=float(ec.get("error_model_min_error_range", 2.5)),
                               default=default, min_floor=float(ec.get("error_model_min_floor", 0.0)))
    table.to_csv(phot / "pytics" / "error_model.csv", index=False)
    out = ER.apply_error_model(lc, table, default)
    k = out["F_ic"] * np.log(10) / 2.5
    out["Ferr_model"] = k * out["mag_err_model"]
    out["Ferr_model_rand"] = k * out["mag_err_model_rand"]
    return out


#: filter_dict names for the shareable CSV
FILTER_NAMES = {"up": "u", "B": "B", "gp": "g", "V": "V", "rp": "r", "ip": "i", "zs": "z", "Y": "Y",
                "R": "R", "I": "I", "U": "U"}


#: columns of the shareable merged CSV (what users download); the QC columns go to the ``_qc`` file
MERGED_COLUMNS = ["target", "MJD", "filter", "telescope", "camera", "flux_mJy", "flux_err_mJy", "mag_AB",
                  "mag_AB_err", "zp_err_mag", "frame"]
#: columns of ``<target>_LCO_merged_lightcurve_qc.csv`` (every epoch, for quality control)
QC_COLUMNS = ["target", "MJD", "filter", "telescope", "camera", "frame", "good", "flux_mJy", "flux_err_mJy",
              "flux_err_random_mJy", "mag_AB", "mag_AB_err", "mag_AB_err_random", "zp_err_mag", "mag_ensemble",
              "mag_err_ensemble", "mag_inst", "magerr_phot", "rms_t", "rms_sc", "n_stars", "DMAGT", "DMAGS",
              "CKterm", "intercal_a", "intercal_b", "airmass", "seeing"]


def qc_path_for(path: Path) -> Path:
    """``<target>_LCO_merged_lightcurve.csv`` -> ``<target>_LCO_merged_lightcurve_qc.csv``."""
    path = Path(path)
    return path.with_name(path.stem + "_qc" + path.suffix)


def _merged_table(lc: pd.DataFrame, target: str, error_model: str) -> pd.DataFrame:
    """Every epoch with all product and QC columns (the merged CSV and the QC file are views of it)."""
    g = lc.copy()
    if error_model == "fitted":
        e_tot, e_rand = g["mag_err_model"], g["mag_err_model_rand"]
        f_tot, f_rand = g["Ferr_model"], g["Ferr_model_rand"]
    else:
        e_tot, e_rand = g["mag_ic_err"], g["mag_err_rand"]
        f_tot, f_rand = g["Ferr_ic"], g["F_ic"] * g["mag_err_rand"] * np.log(10) / 2.5 / g["ic_a"]
    col = lambda c, default=np.nan: g[c] if c in g else default  # noqa: E731
    return pd.DataFrame({
        "target": target, "MJD": g["MJD"].round(6), "filter": g["Filter"].map(FILTER_NAMES).fillna(g["Filter"]),
        "telescope": g["telid"], "camera": g["camera"], "frame": g["frame"], "good": g["good"].astype(bool),
        "flux_mJy": g["F_ic"], "flux_err_mJy": f_tot, "flux_err_random_mJy": f_rand,
        "mag_AB": g["mag_ic"], "mag_AB_err": e_tot, "mag_AB_err_random": e_rand, "zp_err_mag": col("zp_err"),
        "mag_ensemble": col("mag"), "mag_err_ensemble": col("mag_err"), "mag_inst": col("mag_inst"),
        "magerr_phot": col("magerr"), "rms_t": col("rms_t"), "rms_sc": col("rms_sc"), "n_stars": col("n_stars"),
        "DMAGT": col("DMAGT"), "DMAGS": col("DMAGS"), "CKterm": col("CKterm"), "intercal_a": col("ic_a", 1.0),
        "intercal_b": col("ic_b", 0.0), "airmass": col("airmass"), "seeing": col("seeing"),
    }).sort_values(["filter", "MJD"])


#: band order in headers (wavelength)
BAND_ORDER = ["u", "U", "B", "g", "V", "r", "R", "i", "I", "z", "Y"]


def _band_zp_errors(t: pd.DataFrame) -> str:
    z = t.groupby("filter")["zp_err_mag"].median().dropna()
    z = z.reindex(sorted(z.index, key=lambda b: (BAND_ORDER.index(b) if b in BAND_ORDER else 99, b)))
    return ", ".join(f"{b} {v:.3f}" for b, v in z.items()) or "n/a"


def _target_name(target: str) -> str:
    """Display name of ``target`` from the AVA database (read-only), else the data_id."""
    import sqlite3
    from contextlib import closing

    try:
        with closing(sqlite3.connect(f"file:{cfg.db_path}?mode=ro", uri=True)) as con:
            r = con.execute("SELECT name FROM agn WHERE data_id = ?", (target,)).fetchone()
        return str(r[0]) if r and r[0] else target
    except Exception:  # noqa: BLE001  (no database: the header still works)
        return target


def _merged_header(target: str, t: pd.DataFrame, error_model: str, name: str | None = None) -> list[str]:
    from datetime import datetime, timezone

    errs = ("the empirical error model fitted to same-night AGN pairs (ava.photometry.errors)"
            if error_model == "fitted" else
            "photometric error (+) ensemble epoch scatter rms_t (+) per-camera systematic rms_sc (PyTICS)")
    return [
        f"AVA - AGN Variability Archive: merged LCO light curve of {name or target} (data_id {target})",
        f"Made {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by the AVA pipeline {_version()}. Licence CC BY-SA 4.0.",
        "Please cite AVA and PyTICS (Vieliute et al. 2025, RASTI, doi:10.1093/rasti/rzaf021).",
        "All LCO telescopes and cameras on one scale (PyTICS ensemble + camera intercalibration);",
        "only epochs that pass quality control. 1 mJy = AB 16.4.",
        "Absolute scale: Gaia DR3 synthetic photometry (GSPC) of the field stars, with a stellar colour",
        "term evaluated at the AGN colour (SDSS u g r i z, Johnson B V, PS1 y; AB). Emission lines can make",
        "an AGN differ from those systems by up to ~0.2 mag in some bands: see 'Photometric calibration'",
        "on the AVA website, which also gives the LCO filter curves.",
        "Columns ((+) = added in quadrature):",
        "  target        AVA identifier (data_id)",
        "  MJD           Modified Julian Date, mid-exposure (days)",
        "  filter        band: u B g V r i z Y",
        "  telescope     LCO telescope (e.g. 1m004); camera: LCO camera code (fa Sinistro, ep MuSCAT, ...)",
        "  flux_mJy      flux density (mJy); flux_err_mJy: its total per-epoch error",
        "  mag_AB        AB magnitude; mag_AB_err: its total per-epoch error",
        f"                total per-epoch error = {errs}",
        "  zp_err_mag    absolute zero-point uncertainty of the band (mag), the same for every epoch.",
        "                A systematic common to all points of a band: do NOT add it to the per-epoch errors",
        "                (it does not affect lags or variability); add it in quadrature only when using",
        "                absolute fluxes or magnitudes (SEDs, comparison with other data).",
        f"                Per band: {_band_zp_errors(t)}",
        "  frame         LCO frame name, to trace any point back to the LCO archive",
    ]


def _version() -> str:
    v = (cfg._raw.get("project", {}) or {}).get("version")
    return f"v{v}" if v else ""


def _write_with_header(df: pd.DataFrame, path: Path, header: list[str]) -> None:
    path = Path(path)
    with open(path, "w") as fh:
        fh.writelines(f"# {line}\n" for line in header)
        df.to_csv(fh, index=False, float_format="%.5f")


def export_merged_csv(lc: pd.DataFrame, path: Path, target: str, error_model: str = "pytics",
                      qc_path: Path | None = None, name: str | None = None) -> pd.DataFrame:
    """The shareable merged light curve: good epochs only, intercalibrated, AB mag and mJy.

    Written with a ``#`` header that explains every column (read it with ``pd.read_csv(path, comment="#")``).
    Columns (:data:`MERGED_COLUMNS`): target, MJD, filter, telescope, camera, flux_mJy, flux_err_mJy and
    mag_AB, mag_AB_err (total per-epoch errors: PyTICS σ_phot ⊕ rms_t ⊕ rms_sc, or the empirical model when
    ``error_model="fitted"``), zp_err_mag (the band's absolute zero-point uncertainty, a systematic common to
    all epochs, not included in the per-epoch errors), frame.  1 mJy = AB 16.4.

    ``qc_path``: also write every epoch (good or not) with the QC columns (:data:`QC_COLUMNS`: random
    epoch-to-epoch errors, rms_t, rms_sc, n_stars, ensemble terms, intercal a/b, airmass, seeing).

    Returns the good-epoch table with the random-error columns too (F_var can use them)."""
    t = _merged_table(lc, target, error_model)
    # good epochs with a magnitude: a filter without an absolute ZP (e.g. Y with 2 reference stars) has NaN mag_AB
    good = t[t["good"] & np.isfinite(t["mag_AB"].to_numpy(float))]
    _write_with_header(good[MERGED_COLUMNS], path, _merged_header(target, good, error_model, name))
    if qc_path is not None:
        head = [f"AVA quality-control table for {name or target} (data_id {target}), AVA pipeline {_version()}:",
                "every PyTICS epoch of the merged light curve, good or not (column good), with the terms behind",
                f"the errors ((+) = added in quadrature). Not a science product: use {Path(path).name}.",
                "  flux_err_random_mJy, mag_AB_err_random: epoch-to-epoch part of the error",
                "                     (photometric (+) rms_t), without the per-camera systematic rms_sc",
                "  mag_ensemble, mag_err_ensemble: PyTICS magnitude before the camera intercalibration",
                "  mag_inst, magerr_phot: instrumental magnitude and photometric (SExtractor) error",
                "  rms_t         scatter of the comparison stars in that epoch (ensemble QC; good needs rms_t < max)",
                "  rms_sc        per-camera (telescope+camera) systematic of the ensemble",
                "  n_stars       comparison stars measured in that epoch",
                "  DMAGT, DMAGS, CKterm: ensemble epoch offset, camera offset, per-camera colour term",
                "  intercal_a, intercal_b: camera intercalibration F' = (F - b)/a (mJy)",
                "  airmass, seeing (arcsec); zp_err_mag as in the merged light curve"]
        _write_with_header(t[QC_COLUMNS], qc_path, head)
    return good


def _record_fvar(target: str, lc: pd.DataFrame, merged: pd.DataFrame | None, error_model: str, ec, logger) -> dict:
    """Per-band F_var of the merged light curve → ``photometry_variability`` + ``agn.frac_<band>``
    (ava.photometry.variability).  Settings: ``ensemble.fvar_error`` ("total" | "random"),
    ``ensemble.fvar_min_epochs``.  A failure here is logged, never fatal to the ensemble step."""
    from ava.photometry import variability as PV

    try:
        if merged is None:      # CSV export disabled: same good-epoch table, not written to disk
            merged = export_merged_csv(lc, Path("/dev/null"), target, error_model=error_model)
        error = str(ec.get("fvar_error", "total"))
        bv = PV.band_variability(merged, error=error, min_epochs=int(ec.get("fvar_min_epochs", 10)))
        out = PV.record_band_variability(cfg.db_path, target, bv, f"{error_model}/{error}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: F_var not recorded (%s: %s)", target, type(exc).__name__, exc)
        return {}
    logger.info("%s: F_var %s", target, ", ".join(
        f"{b} {100 * f:.1f}%" if f == f else f"{b} n/a" for b, f in out.items()) or "no band with enough epochs")
    return out


@task(name="ensemble", tags=["pytics"])
def ensemble(target: str, mode: str | None = None, plot: bool = True) -> dict:
    """PyTICS calibration of ``target`` (full on demand, incremental daily); all settings from
    ``cfg.ensemble``."""

    from ava.photometry import ensemble as E
    from ava.pipeline.tasks.calibrate import frame_db_path

    logger = get_run_logger()
    ec = cfg.ensemble
    phot = cfg.phot_dir(target)
    if not (phot / "measurements.parquet").exists():
        # no calibrated photometry (no catalogues yet, or a spectroscopy-only target): skip, like webplot
        logger.info("%s: no measurements.parquet (nothing calibrated yet) — PyTICS skipped", target)
        return {"target": target, "skipped": "no photometry"}
    db = frame_db_path()
    if not db.exists():
        # frame_qc decides which frames PyTICS sees; a wrong path would read as "0 frames" in every filter
        logger.warning("%s: frame_qc database %s not found (photometry.calibration.frame_db) — PyTICS skipped",
                       target, db)
        return {"target": target, "skipped": f"no frame_qc database ({db})"}
    sct = ec.get("scope_colour_terms", "auto")
    sct = list(sct) if isinstance(sct, (list, tuple)) else (sct if sct == "auto" else bool(sct))
    report = E.run_target(
        phot, db, target, list(ec.filters), mode=mode or ec.mode,
        min_epochs=int(ec.min_epochs), absolute=bool(ec.absolute), colour_term=bool(ec.colour_term),
        scope_colour_terms=sct, colour_check_min_gain=float(ec.get("colour_check_min_gain", 0.05)),
        ref_cameras=tuple(ec.intercal_reference_cameras), intercal_max_gap=float(ec.intercal_max_gap_days),
        intercal_min_pairs=int(ec.get("intercal_min_pairs", 10)),
        colour_bands=tuple(ec.get("colour_bands", ["g", "i"]) or ["g", "i"]),
        auto_refit=bool(ec.auto_refit), log=logger.info,
        ignore_qc_flags=tuple(ec.get("pytics_ignore_qc_flags", ["no_zp", "zp_scatter", "zp_offset"]) or ()),
        update_kw=dict(refit_fraction=float(ec.get("refit_fraction", 0.1)),
                       refit_rms_factor=float(ec.get("refit_rms_factor", 2.0)),
                       refit_rms_floor=float(ec.get("refit_rms_floor", 0.002)), bad_flags=int(ec.bad_flags)),
        zp_kw=dict(clip=float(ec.get("absolute_clip", 3.0)), floor=float(ec.get("absolute_floor", 0.01)),
                   max_rms_star=float(ec.get("absolute_max_rms_star", 0.05))),
        anchor_kw=dict(min_coverage=float(ec.get("absolute_min_coverage", 0.9)),
                       max_scatter=float(ec.get("absolute_max_scatter", 0.2)),
                       trend_degree=int(ec.get("absolute_trend_degree", 2)), bad_flags=int(ec.bad_flags))
        if ec.get("absolute_all_stars", True) else None,
        apply_kw=dict(max_rms_t=float(ec.get("max_rms_t", 0.05)), min_stars=int(ec.get("min_stars", 5))),
        max_loops=int(ec.max_loops), safe=float(ec.safe), frac=float(ec.frac), tiny=float(ec.get("tiny", 1e-4)),
        star_lim=int(ec.star_lim), bad_ids=tuple(ec.get("bad_ids", []) or []), bad_flags=int(ec.bad_flags),
        rms_err_floor=float(ec.get("rms_err_floor", 1e-3)), atol=float(ec.get("atol", 1e-5)))
    if not report:
        # every filter below min_epochs passing frames (no frame_qc rows yet, or none pass QC): no light curve
        logger.info("%s: no filter with %d passing frames — PyTICS skipped", target, int(ec.min_epochs))
        return {"target": target, "skipped": "no filter with enough passing frames"}
    lc = intercal_lightcurve(phot, ec)
    files = []
    error_model = str(ec.get("error_model", "fitted"))
    merged_csv = None
    if ec.get("export_csv", True):
        csv = phot / f"{target}_LCO_merged_lightcurve.csv"
        merged_csv = export_merged_csv(lc, csv, target, error_model=error_model,
                                       qc_path=qc_path_for(csv) if ec.get("export_qc_csv", True) else None,
                                       name=_target_name(target))
        files.append(str(csv))
    fvar = _record_fvar(target, lc, merged_csv, error_model, ec, logger)
    no_zp = [f for f, r in report.items() if r.get("zp") is not None and not np.isfinite(r["zp"])]
    if no_zp:
        # too few reference stars with the band (and the g-i colour) among the PyTICS stars: no absolute
        # magnitudes for these filters, so they are left out of the CSV and the plots
        logger.warning("%s: no absolute zero point for %s — left out of the merged light curve",
                       target, ", ".join(no_zp))
    if plot and not np.isfinite(lc["mag_ic"].to_numpy(float)).any():
        logger.warning("%s: no filter with absolute magnitudes — merged plots skipped", target)
    elif plot:
        from ava.pipeline.tasks.webplot import spectroscopy_epochs
        from ava.plots import webplots as wp

        fd = wp.load_filter_dict(cfg._resolve(cfg.plots.filter_dict))
        merged = pd.DataFrame({"mjd_mid": lc["MJD"], "filter": lc["Filter"], "mag": lc["mag_ic"],
                               "mag_err": lc["mag_err_model" if ec.get("error_model", "fitted") == "fitted" else "mag_ic_err"],
                               "qc_pass": lc["good"].astype(int)})
        merged = merged[np.isfinite(merged["mag"].to_numpy(float))]     # no absolute ZP -> NaN mag: not plotted
        spec, last = spectroscopy_epochs(target)
        plot_dir = cfg.target_plots_dir(target)
        plot_dir.mkdir(parents=True, exist_ok=True)
        base = plot_dir / f"lco_latest_{target}_merged"
        kw = dict(spec_mjd=spec, last_spec_mjd=last, label="Merged by PyTICS", formats=list(cfg.plots.formats))
        files += wp.plot_lightcurves(merged, fd, base, **kw)
        files += wp.plot_lightcurves(merged, fd, Path(f"{base}_last6"), recent_days=float(cfg.plots.recent_days), **kw)
        files += wp.plot_lightcurves(merged, fd, Path(f"{base}_season"), last_season=True,
                                     season_gap_days=float(cfg.plots.get("season_gap_days", 60.0)), **kw)
    logger.info("%s: ensemble %s", target, {f: (r["mode"], r["n_epochs"], r.get("colour_terms")) for f, r in report.items()})
    return {"target": target, "filters": report, "plots": files, "fvar": fvar}
