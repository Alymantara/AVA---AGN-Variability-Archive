"""
Spectroscopy products task — website products of a target's reduced FLOYDS spectra.

1. ``lco_latest_<target>_spec``: the latest spectrum, blue and red arm panels (red to ``red_range``);
   ``lco_latest_<target>_hbeta_fit``: the Hβ-region fit of that spectrum (reference);
   ``lco_latest_<target>_spec_avg``: [O III]-calibrated mean and RMS spectrum (one night: mean only);
2. ``lco_latest_<target>_hbeta``: broad-Hβ light curve (Gaussian fit, [O III]-calibrated when there is a
   series), 5100 Å continuum, and the g-band light curve over the same dates when one exists;
3. records: per-exposure fits → ``spec_lines`` (lcodb spectra DB); flux and variability → ``line_variability``
   (AVA DB); nightly light curve → ``<spec_dir>/<target>_FLOYDS_Hbeta_lightcurve.csv`` (copied to the target plots folder);
4. PrepSpec input: ``<spec_dir>/prepspec/`` — one 3-column text file per spectrum and arm, and
   ``<target>_blue.hjd`` / ``<target>_red.hjd`` (file name, mid-exposure MJD).

Settings: ``spectroscopy.products``.  Figures go to ``cfg.target_plots_dir(target)`` (published by ``-w``) like the photometry plots.
"""

from __future__ import annotations

import shutil

from prefect import get_run_logger, task

from ava.config import cfg


@task(name="spec-products", tags=["spectroscopy", "plotting", "lines"])
def spec_products(target: str) -> dict:
    from ava.pipeline.tasks.download import lcodb_path
    from ava.spectroscopy import lines as L
    from ava.plots import webplots as wpl
    from ava.spectroscopy import products as P
    from ava.spectroscopy import webplots as W

    logger = get_run_logger()
    entry = cfg.target_by_data_id(target)
    if entry is None:
        raise ValueError(f"{target!r} is not a known data_id")
    pc = cfg._raw.get("spectroscopy", {}).get("products", {}) or {}
    hb = pc.get("hbeta", {}) or {}
    z = float(entry.get("redshift") or 0.0)
    files = P.reduced_files(cfg.spec_dir(target))
    if not files:
        logger.warning("%s: no reduced spectra in %s", target, cfg.spec_dir(target) / "reduced")
        return {"target": target, "spectra": 0}
    formats = list(cfg.plots.formats)
    plot_dir = cfg.target_plots_dir(target)
    plot_dir.mkdir(parents=True, exist_ok=True)
    out = {"target": target, "spectra": len(files), "plots": []}

    s = L.settings_from_config(hb)              # every FitSettings field can be set in spectroscopy.products.hbeta
    arm = L.hbeta_arm(z, str(pc.get("hbeta_arm", "auto")), float(pc.get("hbeta_red_arm_above_z", 0.09)))
    lp = pc.get("latest_spectrum", {}) or {}
    red_range = tuple(lp.get("red_range", (5300.0, 9050.0)))
    t, night, meta = P.hbeta_series(files, z, s, qc_good=tuple(hb.get("oiii_reference_qc", ["OK"])),
                                    min_series=int(hb.get("min_series", 3)),
                                    scale_limits=tuple(hb.get("scale_limits", (0.2, 5.0))),
                                    cache=cfg.spec_dir(target) / "hbeta_fits.parquet", arm=arm)
    logger.info("%s: Hβ fits: %d new, %d from the cache (%s)", target, meta.get("n_fitted", 0),
                meta.get("n_cached", 0), cfg.spec_dir(target) / "hbeta_fits.parquet")
    method = f"gauss{s.broad_components}b+oiii{'w' if s.oiii_wing else ''}"
    # 1. latest spectrum (two arms) and its Hβ fit (reference)
    latest = max(files, key=lambda f: P._header(f)["MJD-OBS"])
    hdr = P._header(latest)
    out["latest"] = str(latest)
    out["plots"] += W.latest_spectrum(P.arms(latest), hdr, entry["name"], z, plot_dir / f"lco_latest_{target}_spec",
                                      formats, red_range=red_range)
    sp = L.arm_spectrum(latest, z, arm)
    fit = L.fit_hbeta(sp, s)
    out["plots"] += W.latest_hbeta_fit(sp, fit, s, hdr, entry["name"], z, plot_dir / f"lco_latest_{target}_hbeta_fit",
                                       formats, arm=arm)
    # mean and RMS spectrum ([O III]-calibrated when there is a series; one spectrum is fine too)
    if len(t):
        mp = pc.get("mean_rms", {}) or {}
        good = t[t["good"]] if t["good"].any() else t
        off = P.arm_offsets(good, z, cfg.spec_dir(target), max_shift=float(mp.get("max_shift_A", 6.0)),
                            windows=mp.get("align_windows"), masks=mp.get("align_mask"), red_range=red_range,
                            highpass_A=float(mp.get("highpass_A", 60.0)))
        bad = off[off[["shift_blue_A", "shift_red_A"]].isna().any(axis=1)]
        for r in bad.itertuples():
            logger.warning("  %s: no plausible wavelength offset in some arm (left out of that arm's mean/RMS)",
                           r.basename)
        logger.info("%s: arm offsets (Å) blue median %+.2f σ %.2f, red median %+.2f σ %.2f → %s", target,
                    off.shift_blue_A.median(), off.shift_blue_A.std(), off.shift_red_A.median(), off.shift_red_A.std(),
                    cfg.spec_dir(target) / "spec_offsets.csv")
        excl = tuple(mp.get("exclude_flags", ["CRLINE"]) or [])
        tm = t[~t["qc"].astype(str).str.split(",").map(lambda f: any(x in excl for x in f))] if excl else t
        if len(tm) < len(t):
            logger.info("%s: mean/RMS without %d spectra flagged %s", target, len(t) - len(tm), list(excl))
        mr = P.mean_rms(tm, z, red_min_observed=red_range[0], red_max_observed=red_range[1], offsets=off,
                        match_resolution=bool(mp.get("match_resolution", True)),
                        resolution_percentile=float(mp.get("resolution_percentile", 90.0)))
        span = f"MJD {t.MJD.min():.0f}–{t.MJD.max():.0f}" if t.MJD.max() - t.MJD.min() > 0.5 else f"MJD {t.MJD.min():.1f}"
        out["plots"] += W.mean_rms_spectrum(mr, entry["name"], z, plot_dir / f"lco_latest_{target}_spec_avg", formats,
                                            date_range=span)
    csv = cfg.spec_dir(target) / f"{target}_FLOYDS_Hbeta_lightcurve.csv"
    summ = P.record(t, night, meta, target, lcodb_path("spec"), cfg.db_path, csv, method)
    if csv.exists():
        shutil.copy2(csv, plot_dir / csv.name)
    if len(night) >= 2:
        lo, hi = night.MJD.min(), night.MJD.max()
        pad = max(5.0, 0.03 * (hi - lo))
        g = P.g_band(cfg.phot_dir(target), target, (lo - pad, hi + pad))
        fd = wpl.load_filter_dict(cfg._resolve(cfg.plots.filter_dict))
        gcol = next((r.color for r in fd.itertuples() if r.lco == "gp"), "#008000")
        out["plots"] += W.hbeta_lightcurve(night, meta, summ["flux"], entry["name"], g,
                                           plot_dir / f"lco_latest_{target}_hbeta", formats, g_colour=gcol)
        out["g_band_nights"] = len(g)
    v = summ["flux"]
    logger.info("%s: %d spectra (%d good) on %d nights, [O III]-calibrated %s; Hβ mean %.3g, F_var %s, F_max/F_min %s",
                target, meta["n_spectra"], meta.get("n_good", 0), meta.get("n_nights", 0), meta.get("oiii_calibrated"),
                v.get("mean", float("nan")), f"{100 * v['fvar']:.1f}%" if v.get("fvar") == v.get("fvar") and "fvar" in v
                else "n/a", f"{v.get('rmax', float('nan')):.2f}")
    bad = t[~t["good"]] if len(t) else t
    for r in bad.itertuples():
        logger.warning("  not used: %s (%s)", r.basename, getattr(r, "reason", "") or f"scale {r.oiii_scale:.2f}")
    ps = pc.get("prepspec", {}) or {}
    if ps.get("enabled", True):
        out["prepspec"] = P.export_prepspec(files, target, cfg.spec_dir(target) / ps.get("folder", "prepspec"),
                                            red_min_wavelength=float(ps.get("red_min_wavelength", 5300.0)),
                                            exclude_flags=tuple(ps.get("exclude_flags", []) or []))
        logger.info("%s: PrepSpec files → %s (%d blue, %d red; %d skipped, %d stale removed)", target,
                    out["prepspec"]["dir"], out["prepspec"]["blue"], out["prepspec"]["red"],
                    len(out["prepspec"]["skipped"]), out["prepspec"]["removed"])
    out.update(meta=meta, variability=summ, csv=str(csv))
    return out
