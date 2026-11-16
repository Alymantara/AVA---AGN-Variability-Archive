# Deployment checklist: paths and tunables (audit of 16 Nov 2026)

The whole pipeline was audited: `ava/`, `scripts/` and `tools/`, plus the web config. Three passes were made:
photometry, archive/database/web/scripts, and spectroscopy.

**Rule:** every path and every tunable comes from `config/ava_config.yaml` (or `config/lcodb_config.yaml`).
Code defaults are only fallbacks that equal the documented config values.

## Fixed in this pass

### Paths and deployment

- **Validation tools** (`tools/*_validation/`):
  - they find the repository from their own location, not `/Users/juan/...`;
  - they take data paths from the config (`AVA_CONFIG`) and the target from `AVA_TARGET` (default Mrk_817).
- **`ava.config`**:
  - the `lcodb_config` default is the repository's `config/lcodb_config.yaml`, not the old floyds folder;
  - YAML `null` path keys no longer turn into the string "None";
  - both `LCO_API_TOKEN` and `LCO_TOKEN` are accepted, in both configs;
  - the science-radius fallback is 5.25″, as in the config.
- **`get_archive()`**: resolves the lcodb config against `ava_root`. It broke outside the repository folder.
- **`Archive`** (lcodb query): reads the AVA database from `ava.db`. It used to look for `data/ava/ava.sqlite`,
  which doesn't exist, and silently returned no targets.
- **LCO API roots** are set from `lco.archive_url` / `lco.base_url` (AVA) or `archive_url` / `portal_url` (lcodb),
  through `ava.lcodb.api.set_urls`.
- **`scripts/lcodb_daily.sh`**:
  - uses bash and `cd`s into the repository;
  - uses `AVA_PYTHON` (default `python3`);
  - logs next to the databases (`db_dir`).
- **`scripts/deploy.py`**:
  - the nightly steps come from `pipeline.prefect.nightly_steps`;
  - it has spectroscopy flags (`-O -D -R -P`);
  - it deploys the repository's code (not `ava_root`);
  - it passes `AVA_CONFIG` to the worker.

### Behaviour that ignored the config

- `ensemble.mode` is used. Before, `"auto"` was always passed; `--pytics-full` still forces `full`.
- `pipeline.n_cores` caps how many targets run at the same time (Prefect thread pool). Before, there was no limit.
- `sync_rate_per_s` (lcodb) rate-limits the archive crawls.
- The lcodb `position_radius_arcsec` default is 120″, as in the config.

### Science tunables now in the config

- **`photometry`**:
  - `apertures.{old,new}_diameters_px` and `expansion_mjd` were in the YAML but ignored;
  - `pixel_scales`;
  - `imaging_camera_prefixes`;
  - `matching.{max_sep_arcsec, min_matches, recentre_radii_arcsec, min_recentre_stars}`;
  - `reference.agn_match_arcsec`;
  - the u anchor uses `reference.max_ruwe`.
- **`ensemble`**: `absolute_clip`, `absolute_floor`, `absolute_max_rms_star`, `refit_rms_floor`.
- **`plots`**: `season_gap_days`, which the code already read but the YAML didn't have.
- **`spectroscopy.products`**:
  - every Hβ fit setting (`hbeta.*`: windows, width limits, loss, coverage, integral window);
  - mean/RMS `align_windows`, `align_mask`, `highpass_A`;
  - the red-arm limits come from `latest_spectrum.red_range` everywhere;
  - the arm dispersions are measured, not hard-coded.
- **`spectroscopy.reduction.cleanup.min_good_fraction`**.

**Verified:**
- the PyTICS light curve is unchanged (≤ 3×10⁻¹¹ mag);
- the spectroscopy products and database check pass;
- 81 tests pass.

### Found after the audit: plotting in parallel targets

- **Matplotlib is not thread-safe**, and `pipeline.n_cores` runs targets in parallel threads:
  - concurrent spectroscopy plots failed with random mathtext `ParseException`s;
  - one module's `rcParams` (the bigger spectroscopy fonts) could leak into another's figure;
  - the photometry plots used the macOS GUI backend, which refuses to draw off the main thread.
- **Fix:** every website plot function is wrapped by `ava.plots.webplots.serialized`. It holds one lock per figure,
  inside `plt.rc_context()`, on the Agg backend.
- **Verified:** three parallel `-P` runs and a `-p -P` run are clean; `line_variability` is unchanged.

## Must be set per host (values, not code)

- **`paths` in `ava_config.yaml`:** `spectra_root`, `photometry_root`, `swift_db` and `template_dir` (`/data2`, `/data3`).
- **`floyds_pipeline` and `spectroscopy.reduction`:** `python`, `package` and `skyflats_dir` (currently `~/astro/floyds`).
- **Token:** `lco.token_file` (`~/.lco_token`), or the `LCO_API_TOKEN` environment variable.
- **`db_dir` in `lcodb_config.yaml`:** `../data/lcodb`.
- **Prefect:** a work pool or `--serve`, plus the cron for `scripts/lcodb_daily.sh` (09:30 UTC, before the pipeline at 10:30).

## Still hard-coded (left for a decision; none blocks a deployment)

### Science or behaviour

- **WCS repair** (`catalogs.solve_wcs_from_patterns`): pattern tries, a scale window of 0.9–1.1, a 2′ margin,
  1.5″ matching and a stop at 20 matches.
- **Colour-term check** (`ensemble.colour_term_check`):
  - same-night pairs are < 0.4 d and it needs ≥ 10 of them;
  - `intercalibrate` there uses `min_pairs=10`, not `ensemble.intercal_min_pairs`.
- **Intercalibration fit:** a 4σ clip, 10 iterations and 0.3 d nearest-epoch matching. `additive_only=True` is fixed in the task.
- **Per-frame zero point** (`calibration.py`): 10 iterations, a MAD floor of 0.005, and a colour slope that needs
  ≥ 5 stars and a colour range > 0.3.
- **Catalogues:** the VizieR IDs (`I/355/gaiadr3`, `I/360/syntphot`, `II/336/apass9`, `I/355/paramp`), a 120 s timeout,
  GSPC completeness `0.8 n_xp` and a +0.5′ Gaia cone padding.
- **SExtractor:** a 600 s timeout, the `*e91.fits.fz` frame glob, and the assumption that legacy catalogues have 12 apertures.
- **Error model:** Student-t ν = 4, cross-camera pairs up to 3 neighbours, and a 0.5 mag `brentq` bound.
- **APASS fallback:** the SED fit starts at 6000 K with bounds 500–70000 K.
- **lcodb `spectrum_standards` view:** the 30-day window (720 h) and the 2″ slit preference are fixed in the SQL;
  `standards.preferred_dt_days` is only documented.
- **lcodb ingest:** starts in 2014-01-01, uses a 31-day margin before the semester, and falls back to the camera list
  `en05/en06/en12`. `db.CAMERA_TYPES` duplicates the instrument list.

### Robustness and performance

- **Spectra-only targets:** `-p` (`webplot`) fails with `FileNotFoundError` when a target has no
  `agn_lightcurve.parquet` (Fairall 9 and NGC 4151 in the test archive). It should skip them.

- **API client:** `max_wait_s` 900, backoff `min(300, 3·2^n)` and Retry-After 60. The download client's timeout,
  retries and max wait have no config keys. `fetch` has a 600 s timeout.
- **`query.new_in_archive`:** rate 2/s, 2 retries and `page_size=1000`, all fixed.
- **Chunk sizes and timeouts:** calibration chunk sizes (2000 / 20), a `load_pytics` 50 000-frame cutoff,
  SQLite timeouts (30–120 s), `headers.commit_every` / `batch`.
- **Publish:** the task retries once after 60 s.

### File and folder names (fixed by convention)

- `sextractor_ava`, `ava_merging`, `UVOT`, `pytics/`, `reference_stars.csv`, `measurements.parquet`,
  `agn_lightcurve*.parquet/.csv`, `intercal.csv`, `error_model.csv`, `<t>_LCO_merged_lightcurve.csv`.
- Spectroscopy: `prepspec/`, `reduced/`, `archive/`, `banzai/`, and the cache files.

### Config keys no code reads (delete or wire)

- `photometry.seeing_limit_arcsec`. QC uses `qc.max_fwhm_arcsec`.
- `photometry.min_standards: 3`. The code uses `calibration.min_standards: 5`.
- `photometry.extinction_coefficients` and `photometry.colour_correction`.
- `database.engine/host/port/name/user/password`. SQLite is always used.
- `web.host/port/debug/secret_key`. The site is PHP.
- `pipeline.overwrite`, `verbose`, `log_level`.
- `paths.logs`, `project.contact`.
- `spectroscopy.instrument`, `default_slit_arcsec`, `wavelength_range_angstrom`.
- The `intercalibration.*` keys: `merge.py` is a stub.

### Web

- `web/includes/config.php` repeats the key projects and LCO filters that the YAML holds.
