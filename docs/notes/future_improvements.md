# AVA — future improvements

Deferred work, collected while building the Prefect pipeline (Nov 2026).
Newest decisions first within each section.

## Database (`data/ava.db` is the source of truth)

- **`ava-db` command-line tool** for viewing and editing the database:
  - `show <data_id>` — a target with its pointings and LCO statistics
  - `set <data_id> field=value … --reason "..."` — validated edits (coordinate ranges, optional Gaia
    position check, types)
  - `add` — new AGN (requires name, data_id, coordinates)
  - `import changes.csv` — batch edits, dry run first
  - `export` — the reference CSVs
  - every write: automatic backup + a row in an `agn_changes` audit table (old/new value, reason, time)
- **Targets only in `targets.yaml`** (38, mostly the `sdssrm*` fields) — decide whether they become
  `agn` rows; resolve spelling mismatches (`MCG_04-22-042` vs `MCG+04-22-042`, `J2107-3754` vs
  `J21079-3754`) during the download step.  `lco_active` is NULL for the 7 DB-only sources until then.
- **Rows left unchanged on purpose:** SDSS-RM201, SDSS-RM562 (sexagesimal only; RM562 has
  `simbad_name = "SDSS RM201"`), RX J22198-0935 (stored Dec +09:20:27 contradicts the name, −09:35).
- **`ava/database/models.py` / `migrate.py`** describe a schema that does not match the real database;
  update or remove.
- **First real run** of `lcodb link` + `tools/ava_crossmatch.py` (in-place mode) on the production machine
  (`--dry-run` first).
- Gaia DR4 renumbers some sources: `star_id` / `agn_gaia_dr3_id` are DR3 ids.

## Photometry: apertures and extraction (decided Nov 2026)

- **Aperture series is append-only.** `data/reference/sextractor/default.sex` PHOT_APERTURES is now
  3,5,8,11,13,15,18,21,24,27,30,33 **+ 36,39,43,48** px: new extractions (all cameras) get 16 apertures and
  indices 0–11 never change.  Future enlargements: append again, never insert or reorder (the code checks
  that the series still starts with 3…33).
- **Science aperture = 10.5" diameter** (`science_aperture_radius_arcsec: 5.25`, = Sinistro's 27 px):
  Sinistro 27 px (index 9), Spectral 33 px = 10.0" (index 11), **MuSCAT 39 px = 10.53" (index 13) when the
  catalogue has the appended apertures**, else 33 px = 8.9".  Only cameras in
  `photometry.sextractor.extended_aperture_cameras` (= `ep`) may pick an appended aperture, so Sinistro and
  Spectral numbers never change.
- **TODO (later date): re-extract the existing MuSCAT catalogues** on the production machine so they get the
  39 px aperture: set `photometry.sextractor.reextract_on_aperture_change: true` (restricted to
  `reextract_cameras: [ep]`) and run `-e`.  Mrk 817 alone has ~2,700 MuSCAT frames.  Sinistro and Spectral
  are not re-extracted.
  *Why:* curves of growth from 59 same-night, seeing-matched MuSCAT/Sinistro pairs of Mrk 817: MuSCAT's old
  maximum aperture (33 px = 8.9") misses 23 / 29 / 34 mmag of stellar light vs Sinistro's 10.5"
  (seeing < 2.2" / 2.2–2.5" / > 2.5"), 45–70 mmag at 3.3–3.5" — seeing-dependent, so PyTICS per-telescope
  offsets cannot absorb it (more for the AGN + host).
- Catalogues carry `APERDIAM` (aperture diameters, px); legacy catalogues without it are read from their
  aperture count (10 = pre-2025 series, otherwise the first n of the current series) — never the date
  (Mrk 817 was re-extracted with the 12-aperture series for all epochs, so the `EXPANSION_MJD` rule in
  `apertures.py` / config is wrong for it).
- Sinistro's curve of growth still rises ~9 % from 7" to 12.8": 10.5" is not total flux on any camera —
  fine as long as every camera uses the same physical aperture.
- SExtractor no longer runs on FLOYDS (`en`) frames (the legacy glob extracted 45 for Mrk 817).

## Photometric calibration

- **Calibrate step (built Nov 2026; `ava.photometry.process` / `calibration` / `store`)** — storage:
  `frame_qc` table in the photometry DB (every frame-level number: time, filter, camera, true airmass,
  seeing, background, ellipticity, WCS, aperture, ZP, QC flags), `<phot_dir>/measurements.parquet`
  (all matched stars + the AGN at the 10.5" aperture; PyTICS input via `store.load_pytics`),
  `<phot_dir>/agn_lightcurve.parquet/.csv`.  Nothing frame-level is duplicated in the Parquet files.
  Mrk 817 legacy `lco_latest_stan.pkl` (173 MB / 681 MB in memory) → 17–26 MB Parquet.
- **Legacy `ava_calibrate.py` equation problems (fixed in the new code):** aperture correction applied to the
  standards only → AGN magnitudes seeing-dependent (−12 to −24 mmag per arcsec in all of u B g V r i, r = −0.53…−0.80, robust 3σ-clipped fits; Mrk 817); AGN not
  excluded from its own standards, no flag/saturation cut (`MAG_LIM` unused); AGN colour term used Fairall 9's
  catalogue colours for every target; MuSCAT post-60909 aperture index 12 out of range and the `66909` typo;
  two inconsistent ZP estimates; `airmass` stored as X−1.  New calibration: same aperture for AGN and stars,
  weighted clipped ZP, no aperture/airmass/AGN-colour terms → AGN repeatability ~2× better in every band
  (e.g. g 3.1 vs 6.4 mmag, r 1.6 vs 4.4 mmag).  Figures: `docs/figures/mrk817_calibration_vs_legacy.png`,
  `mrk817_frame_qc.png`, `mrk817_agn_lightcurve_2021Q1.png`.
- **Full Mrk 817 run (local test, metadata from the legacy pickle):** 21,573 frames in 13 min 15 s on 6 workers
  (~27 frames/s; 4,080 CPU-s ≈ 190 ms/frame; peak 0.94 GB).  Outputs: frame_qc 7.7 MB, measurements.parquet
  2.23 M rows / 47 MB, AGN light curve 21,511 points; 81 % pass QC (Sinistro 80 %, MuSCAT 90 %).  Results are
  now written in chunks of 2,000 frames (progress, resumable).  Figures: `docs/figures/mrk817_agn_lightcurve_full.png`,
  `mrk817_frame_qc.png`.
- **Check on the production machine:** saturation (`SATURATE`) and frame-edge cuts use the raw SCI header —
  untested locally (no raw frames).
- **MuSCAT vs Sinistro AGN offset:** on the same nights MuSCAT's AGN (8.9" aperture) is 0.07–0.08 mag fainter
  than Sinistro's (10.5") in g r i z (40–43 nights, scatter 0.008–0.02) — 3–4× the stellar aperture loss, i.e.
  host-galaxy light.  Another reason for the MuSCAT 39 px re-extraction; meanwhile PyTICS per-telescope
  offsets absorb the constant part.
- **MuSCAT zero points come from only ~5–9 Gaia GSPC stars** (9' field; median 9 matched) — QC uses
  `per_camera.ep.min_matched: 5`; expect noisier MuSCAT zero points.
- **QC thresholds** (`photometry.qc`, per-filter overrides) are first guesses (~2× typical); tune with
  `ava.photometry.process.requalify` (re-evaluates flags from `frame_qc` without recalibrating).
- **z_s / Y zero-point scatter** (0.07 / 0.16 mag vs 0.03 in B–i) comes from the GSPC SDSS-z / PS1-y vs LCO
  filter mismatch — needs the colour terms below.
- Legacy Mrk 817 magnitudes are offset by −0.27…+0.20 mag (band-dependent) from the new Gaia-based ones —
  the legacy APASS file's zero points (it disagrees with SDSS by similar amounts).

- **Colour terms** LCO natural system ↔ GSPC reference systems (SDSS u g r i z, JKC B V R I, PS1 y):
  - empirical: fit `m_ref − m_star = ZP_target,f + C_f·(g−i)` with C_f shared across targets (per filter,
    possibly per camera family), from PyTICS star means of several fields; replaces `C_t` in
    `lco_ext_coefficients.csv`
  - synthetic cross-check once the stellar tracks are re-downloaded: spectra (Teff, log g, [M/H]; or an
    empirical library) through LCO total-throughput curves and SDSS/JKC/PS1 curves (SVO)
- **Zero-point step after PyTICS**: per target and filter, against `reference_stars.csv` (join on
  `star_id`), colour term held fixed; cache until the star ensemble changes.
- **Quick-look light curves** before PyTICS: per-frame ZP = median(reference − instrumental) over matched
  stars → approximate AB AGN magnitude for the daily web plot.
- **PyTICS integration**: use Gaia `star_id` as the star identifier (not APASS row numbers).
- **Legacy 1 m aperture bug**: `ava_calibrate.py` compared `mjd > 66909` (should be 60909), so 1 m frames
  after the 2025 aperture expansion used the wrong aperture — recalibrate affected `lco_latest.pkl`.
- **u band**: the old model extrapolation was 0.07–0.29 mag too faint (field dependent); GSPC fixes this.
  Confirm the AGN u scale against Swift/UVOT U.
- **APASS DR10 file check**: the legacy Mrk 817 DR10 file disagrees with SDSS by g +0.14, r −0.16,
  i −0.19 — compare a raw AAVSO download's column order on the production machine.
- **Absolute-calibration accuracy (18 Nov 2026; report `docs/reports/abscal/report_abscal.md`, PDF `docs/reports/report_abscal.pdf`,
  scripts `tools/abscal_validation/`)**:
  - Stars (Mrk 817 field): AVA = GSPC to ≲ 3 mmag; vs SDSS DR16 / PS1 DR2 g r i z ≲ 3 mmag (z −7 vs SDSS), u −3 ± 8;
    B/V only checkable to ~20–25 mmag (Jordi transforms). No trends with magnitude, airmass, seeing, season or camera
    above ~5 mmag; the `absolute_*` settings move the ZP ≤ 3–5 mmag (keep defaults). APASS DR9 is off by
    +0.03…+0.17 mag, so the `apass_model` fallback is not a precise zero point.
  - **AGN: stellar colour terms at the AGN colour do not give its SDSS/Landolt magnitude.** From 166 fringe-corrected
    FLOYDS spectra (shape only), true − AVA in mmag:
    - Mrk 817: B −26, g −31, V +47, **r +138**, i +4;
    - NGC 4151: B −24, g −45, **V +78**, **r −48**, i 0;
    - Fairall 9: B −28, g −25, V +27, **r +181**, i 0.

    Causes: Hα at the LCO r′ (6925 Å) / SDSS r (6730 Å) red edges, [O III] at the LCO V / Landolt V blue edges,
    and the non-stellar continuum. Stable to 1–10 mmag from epoch to epoch; depends on z (figure: redshift scan)
    and weakly on AGN state. Same-night photometry confirms the r term (r−i). u and z not reliable yet.
  - **Decide (before DR1):** publish AGN magnitudes in the LCO natural AB system (zero point from GSPC; passbands
    published); offer reference-system fluxes as a derived product with per-target / per-season spectral
    corrections; add a pipeline step after the spectroscopy products.
  - **Before that:** per-camera passbands (MuSCAT, SBIG, Spectral; mirrors); resolve the B/V/i synthetic-vs-empirical
    colour-term mismatch (70–90 Å equivalent shifts); redo with all spectra reduced (the scripts find every target).
  - **FLOYDS:** use the fringe-corrected `EXTRACTED` orders for photometry, never the merged `SPECTRUM` (not
    fringe-corrected). Against same-night photometry, Mrk 817 spectra are 0.11 mag too blue between g/V and r/i
    (not an order-splice step: overlap ratio 1.00). Check every night with both spectrum and photometry.
  - **Website page** `web/calibration.php` (18 Nov 2026; Data › Photometric calibration, linked from the Data page's
    filter and file-format sections): stars accuracy, LCO vs reference passbands, each AGN's spectrum with the
    passbands, per-target corrections and the redshift scan, from `calibration.json` (`export_web.py` →
    `web.calibration_src` → `-w`). Its status box says the natural-system switch is *under review*; update it with
    the decision.
  - **Anchors in all 38 test fields (19 Nov 2026; `tools/abscal_validation/{field_inventory,anchor_stars,anchor_sweep}.py`).**
    - **GSPC validity sets a bright limit:** SDSS u g r i z and PS1 y anchors exist only for G ≳ 14.2 (u 14.5); JKC B V
      reach G ≈ 10.8. The colour term needs g−i, so every anchor must be fainter than G ≈ 14.2. Not hard-coded in
      AVA, and absent from the old pipeline, which gave every APASS star model magnitudes in all bands.
    - **Failures it causes:** the ZP only uses PyTICS comparison stars (the brightest `star_lim` = 100) with raw scatter
      `rms_star` < 0.05. In Y only bright stars are that quiet. So Fairall 9 and NGC 4151 have 2 anchors and
      **ZP = NaN (no calibrated Y light curve)**; Mrk 509 has 3. In a dense field (MCG 08-11-011, 2247 quality stars)
      the 100 comparison stars are all brighter than G 14.3: 0–1 anchors, **no absolute ZP in any band**.
    - **Bug:** the merged CSV still exports those Y rows with empty flux/mag (Fairall 9: 1414 rows, NGC 4151: 1011).
    - **Tested fix (offline):** anchors from *all* stars in the frames, put on the ensemble scale with the stored
      DMAGT/DMAGS/CK. Keep stars detected in ≥ 90 % of epochs with per-epoch scatter ≤ 0.2 mag, and judge
      variability by the scatter *in excess of* stars of the same brightness. On the 192 field-bands that work now
      it agrees with the current ZP (median 0, MAD 2–5 mmag; u −7 ± 11). It gives Y 23–53 anchors (Fairall 9 ±7 mmag,
      Mrk 509 ±4, NGC 4151 9 anchors ±18) and MCG 95–805 anchors per band. In a few fields it finds fewer stars than
      now (NGC 4395, NGC 5548 u), so take the union with the comparison stars.
    - **Implemented (user OK, 19 Nov 2026):** `ensemble.anchor_stars` + `absolute_zp(stars=...)`, config
      `ensemble.absolute_all_stars` (default true), `absolute_min_coverage` 0.9, `absolute_max_scatter` 0.2,
      `absolute_trend_degree` 2. The typical scatter is a clipped quadratic in log(scatter) vs magnitude; a running
      median was biased low at the faint end. Checked offline on every stored solution (no products rewritten):
      192 working field-bands move by +1.1 mmag median (MAD 1.5, max 12.5). MCG 08-11-011 gets a ZP in all 7 bands
      (95–805 anchors). Y: Fairall 9 36 anchors (±8 mmag), NGC 4151 21 (±8), Mrk 509 53 (±4, −18 mmag vs 3 stars),
      Mrk 817 44 (+30 ± 15; only 10 Y frames). Bands without a ZP are already dropped from the merged CSV and plots
      (qc-bugs B02/B12). **To do on turgon:** `--pytics-full` once for all targets.
    - **Still open:** u bands with 7–9 anchors (Mrk 1044, Mrk 590, NGC 4151) are a catalogue problem (QC-0003),
      not a star-selection one. PS1 DR2 y for 12.5 < G < 14.2 (dec > −30°) could add bright Y anchors.
  - **Merged light-curve products (user, 19 Nov 2026).** The zero-point error was never in the per-epoch errors
    (right for lags and F_var) but was missing from the shareable CSV. The merged CSV now has a `#` header, keeps
    only the total per-epoch errors and adds `zp_err_mag`. The random (epoch-to-epoch) errors and the other QC
    terms moved to `<target>_LCO_merged_lightcurve_qc.csv` (every epoch, not published). Readers use
    `comment="#"`. Website Data and calibration pages updated. The photometry manual (LaTeX, user's) still
    describes the old columns.

- **PyTICS error bars: pair test on all 36 AGN (19 Nov 2026; `docs/reports/pytics_update/pair_test_all_agn.md`,
  `tools/pytics_validation/pair_scatter_*.py`, figures `docs/figures/pytics_errors/`).**
  - The core is Gaussian. The PyTICS random error has the right mean width (0.95) but the wrong shape;
    the fitted model (k 1.07, β 0.11, s₀ 1.1 mmag) gives width 1.00, held out across nights.
  - Tails: 1.7 % beyond 3σ (Gaussian 0.27 %).
    - **28 %** from bright epochs: the ~1.1 mmag floor PyTICS lacks plus outliers, not non-linearity on Sinistro.
    - **12 %** from MuSCAT, SBIG and Spectral.
    - **The rest** are isolated single-frame events at 1.1 %.
  - **NGC 4151 MuSCAT is saturated** (2024–25, after the mirror realuminisation). Fixed: `camera_defaults.ep`
    and the `agn_saturated` QC flag (`photometry.qc.max_agn_peak_frac` 0.8). Needs `-c` then `--pytics-full`
    on turgon.
  - **Done (user, 19 Nov 2026): the floor is part of the model.** `ensemble.error_model: fitted` is the default;
    the fallbacks and the MuSCAT "scale" fit use `error_model_default` (k 1.07, β 0.11, s0 1.1 mmag), not the
    PyTICS form; `error_model_min_floor` 1 mmag.
  - **Decide:**
    - the floor s₀ from star pairs too (1.0–1.2 mmag in quiet frames, 1.5 for the brightest);
    - a larger s_cam in B and z (cross-camera pairs 1.45 within 1 h);
    - the peak cut for comparison stars.

## Reference catalogue

- Mirror reliability: `vizier.cfa.harvard.edu` lacks GSPC + APASS DR9 around NGC 5548; CDS (first in
  `vizier_servers`) is expected to work from St Andrews — confirm.
- Rebuild the stellar-atmosphere grid (log g, [M/H] dimensions) if the `apass_model` fallback is kept.

## PyTICS ensemble (Nov 2026 overnight run; report `docs/notes/pytics_report.md`)

- **Done:** `ava/photometry/ensemble.py` (faithful vectorised PyTICS port, bit-identical to Astroberta/PyTICS
  `Filter.Corr`, 40–75× faster), incremental `update`, absolute ZP + colour term, `ava/photometry/intercal.py`
  (flux-flux additive offsets), Prefect stage `ensemble` (`run_pipeline.py -t` / `--pytics-full`),
  config section `ensemble:`, tests `tests/test_ensemble.py`.
- **Decide:** refit policy — currently auto-refit when an update flags a new camera, >10 % updated epochs or
  rising rms_t; a weekly full refit is cheap (~1 min/target) and would also do.
- **AGN colour for the colour term** is one mean value (g−i = 0.34 for Mrk 817). The AGN gets bluer when
  brighter; per-epoch colour would change the ZP by C·Δ(g−i) ≲ 4 mmag in g. Implement if it matters.
- **Per-camera colour terms**: Sinistro cameras show ±(0.5–2) % AGN offsets vs each other that correlate
  (r ≈ 0.5) with their star × camera colour slopes — fit a colour slope per scope inside PyTICS (as in the
  PyTICS paper) instead of one DMAGS per scope.
- **1m006-fa08** has DMAGS +0.5 mag in g and rms_sc 25 mmag (g) / 16 mmag (V) — check this camera
  (and why u/B frames from it fail QC entirely).
- **MuSCAT additive offset** is now corrected (b, a ≡ 1) on matched nights. After the 39 px re-extraction
  re-run `intercal` — b should shrink to the 10.5"-vs-10.5" level.
- **Y band**: 10 frames only; absolute ZP scatter 68 mmag (PS1-y vs LCO Y) — not trustworthy yet.
- **u-band new camera**: after a new scope appears, u-band updates disagree with a refit by ~6 mmag rms
  until the refit (auto-refit handles it).
- **Base Python env**: `/opt/anaconda3` cannot write Parquet (pyarrow 11 binary vs pandas 2.2.1; conda
  lists pandas 1.5.3 / pyarrow 12 from pip). Use a clean env (environment.yml) for the pipeline.
- The CALI `merge` stub stays; PyTICS + intercal may make CALI unnecessary for the photometry — decide.
- **Per-camera colour terms (16 Nov 2026, done):** `fit(colours=…)` adds CK_k·(g−i) per telescope+camera; on for
  u B g V (`ensemble.scope_colour_terms`), off for r i z (slopes ≲ 2 mmag/mag, no gain). Sinistro AGN offsets
  −30…45 % in B g V. Remaining 0.3–0.75 % camera-to-camera offsets look seeing/host-related — candidate next term.
  Stopping rule now also stops on a stationary gauge-free solution (`atol`), and floors rms errors at 1 mmag
  (`rms_err_floor`); both 0 = exact PyTICS.
- **16 Nov 2026:** colour terms now decided automatically per target/filter (`scope_colour_terms: auto`); all
  ensemble parameters in the config; shareable `<target>_LCO_merged_lightcurve.csv` (mJy); `mag_err_rand`.
  Material for the manual (user writes it): `docs/notes/pytics_algorithm_changes.md`, `docs/figures/pytics/pytics_workflow.pdf`.
  Open: detector-position residual (−4 mmag at y edges in u/z) — candidate position term; webplot stage (-p) still
  plots the per-frame light curve, the PyTICS merged plots come from the ensemble stage.

## PyTICS error model from the AGN pair test (Nov 2026, `tools/pytics_validation/storm2_figs.py`, fig. pytics_21)
- Same-camera AGN pairs < 1 h: robust σ_z with `mag_err_rand` is 0.65–1.03 overall, but it falls steeply with the
  quoted error: the best epochs (1–2 mmag) are under-estimated by 1.2–1.6×, the worst over-estimated (0.3–0.6).
  Suggests a per-filter noise floor (~1–2 mmag) and a smaller weight on rms_t. MuSCAT i/z errors are 16–27 % too small.
- Different-camera pairs < 6 h need the total error (rms_sc): σ_z ≈ 1 in g, V, i (Sinistro–Sinistro), but
  B 1.37, u 1.26, z 1.6–1.9 — camera-dependent offsets left in B and z.
- STORM 2 same-night camera-to-camera σ: per-frame ZP (Sinistro only) is lower than PyTICS in u/B/V (0.44/0.63/0.43 %
  vs 0.50/0.95/0.54 %) — to be understood before the error model is changed.
- **Update:** an empirical error model is implemented as opt-in (`error_model: fitted`, `ava/photometry/errors.py`) and
  verified on held-out halves (pytics_23). It stays off until it has been checked on other AGN.
- **MuSCAT step between seasons** (pytics_22, `tools/pytics_validation/muscat_drift.py`). MuSCAT − Sinistro AGN flux:

  | Band | 2021 | 2022 | Trend within 2021 |
  |---|---|---|---|
  | z | −0.8 % | +1.1 % | about −2 % per 100 d |
  | r | −0.4 % | +0.6 % | |
  | i | −0.2 % | +1.1 % | |
  | g | 0 | 0 | |

  - Every Sinistro camera sees the same step, so it is MuSCAT (or its host-light term) that changes.
  - It is not a slope a ≠ 1: the mean flux barely changes between seasons.
  - There is no clear dependence on seeing.
  - Candidate fix: a MuSCAT additive offset per season (or a smooth one in time).

## MuSCAT season step: per-season option and seeing check (Nov 2026)

**It is not seeing.** In the matched MuSCAT–Sinistro data:
- MuSCAT FWHM is the same in both seasons (z 1.50″ / 1.50″, r 1.90″ / 1.83″).
- A FWHM slope explains ≤ 0.6 % per arcsec. A season term explains 1–1.4 % and reduces the r scatter from 0.85 % to 0.39 %.
- The MuSCAT aperture is unchanged: 33 px = 8.9″ diameter in both seasons. Sinistro uses 10.5″.

**Option:** `ensemble.intercal_per_season` (default false), with seasons split at gaps > `intercal_season_gap_days` (60). With it on (Mrk 817):

| Band | b1, 2021 (mJy) | b1, 2022 (mJy) | MuSCAT–Sinistro pair scatter < 6 h (mmag) |
|---|---|---|---|
| g | −0.47 | −0.47 | 7.2 → 7.2 |
| r | −0.84 | −0.75 | 10.9 → 6.5 |
| i | −1.01 | −0.93 | 12.6 → 10.1 |
| z | −1.12 | −0.93 | 19.4 → 14.0 |

The z drift within 2021 (about −2 % per 100 d) remains. Figure: `pytics_24_muscat_per_season.png`.

**To do: re-extract MuSCAT with a larger aperture** that matches Sinistro (10.5″).
- If the step is host light that depends on the aperture, it should shrink or disappear, and the additive term with it.
- Re-run `tools/pytics_validation/muscat_drift.py` before and after.
- The append-only aperture series and `extended_aperture_cameras: ["ep"]` already allow this.

Open question: what changed in MuSCAT between the seasons (focus or pointing of the AGN on the detector, flat fields, an instrument intervention)?

## Spectroscopy: sky flats belong in the reduction package (user, 16 Nov 2026)
- The sky flats are essential: they set the order trace at each site. They must ship with the improved banzai-floyds fork, not be fetched or registered by hand.
- What the fork has today:
  - `banzai_floyds/data/orders/skyflats.dat` lists the frames (site, frame id, slit, validity window);
  - `banzai_floyds_offline skyflats` processes them from a local folder;
  - the FITS files themselves are **not** in the package.
- To decide at the install step: ship the processed order solutions (small tables) as package data, or ship the raw sky flats.
  - Either way, `banzai_floyds_offline setup-db` should register them with no download.

## Spectroscopy reduction stage: first run (16 Nov 2026)

The `-R` stage (`spec-reduce`) ran banzai-floyds `rm-improvements@8897b99` on 3 Mrk 817 OGG nights in about 2 minutes: 21 frames, no failures, 9 rows written to `spec_qc`.

**Comparison with the archive** (`tools/spec_validation/compare_archive.py` → `<spec>/Mrk_817/plots/compare_archive.png`):

| Measure | Ours (EXTRACTED) | Archive (1.0.1) |
|---|---|---|
| Red fringing, 7700–8500 Å | 3.0–4.3 % | 8.5–15.8 % |
| [O III] 5007 offset from redshift | −1.9 to −3.2 Å | −8 to −11 Å |
| Flux level | reference | 1.9–2.3× higher (archive exposure-time bug) |

**Fork bug.** `extract.CombinedExtractor` rebuilds the merged `SPECTRUM` table from the 2-d binned data. With `FRINGE_METHOD='harmonic'` that data is never fringe-corrected; only the `EXTRACTED` 1-d table is. So the merged spectrum keeps 7–14 % fringes.
- Fix in the fork: build `SPECTRUM` from the corrected `EXTRACTED` orders.
- Until then, AVA should read `EXTRACTED`.

**Other open points:**
- Spikes are left beyond 9000 Å: the known open problem of the red-end telluric correction.
- The flux grey factor among the 3 standards is 2.9 (`L1FLXGRY`): only 2″ standards exist, so this needs checking on more nights.
- The banzai work folder is 459 MB for 3 nights. The fork's lean policy (`lean_2d.py`) should become an option.

## Spectroscopy website products (16 Nov 2026; `-P`, `ava/spectroscopy/{lines,products}.py`)

**Products:**
- `lco_latest_<t>_spec`: the latest spectrum, blue and red arm panels.
- `lco_latest_<t>_hbeta`: broad Hβ and the 5100 Å continuum, with the g band when photometry exists.
- `<t>_FLOYDS_Hbeta_lightcurve.csv`: nightly values.
- Database records: `spec_lines` (spectra DB) and `line_variability` (AVA DB).

**Fit choices:**
- **One broad Gaussian.** Same-night exposure pairs were used to compare methods. A free 2-Gaussian broad component trades flux with the continuum: 12–19 % pair scatter for Mrk 817, 9 % rms for NGC 4151. One Gaussian gives 0.5 / 1.5 / 4 % for Mrk 817 / NGC 4151 / Fairall 9.
- **Cross-check.** The flux integrated above the continuum is stored as `flux_integrated`.
- **[O III] calibration.** Each spectrum is scaled to the median [O III] 5007 of the QC-OK spectra. It removes the grey factors: the raw Hβ of Fairall 9 has F_var 18 % and F_max/F_min 4.4; calibrated, 2.2 % and 1.26.
- **Nights** are grouped by LCO DAY-OBS. At COJ, MJD − 0.5 splits the night.

**Results:**

| Target | Nights | Hβ F_var | Continuum F_var |
|---|---|---|---|
| NGC 4151 | 28 | 7.8 ± 0.5 % | 8.2 % |
| Fairall 9 | 47 | 2.2 ± 0.9 % | 4.3 % |
| Mrk 817 | 3 | 3.8 ± 1.8 % | |

**Still to do:**
- Fe II is not modelled (fine for these three; Fe II-strong AGN will need a template).
- The g band comes from the merged photometry CSV only (Mrk 817 in the test archive).

## Mean / RMS spectrum and incremental spectroscopy products (16 Nov 2026)

**New plot:** `lco_latest_<t>_spec_avg` (website "Mean spectrum" slot). It is the [O III]-calibrated mean and RMS of the nightly spectra, in the rest frame, both arms.
- One night: mean only, with a note.
- No spectra: no file (the site hides the tab).

**Alignment:**
- Each arm gets an offset by cross-correlation against a stored template. Blue arm: [O III]. Red arm: [O I] and [S II], with Hα + [N II] masked, because Hα–[N II] 6583 = 20.5 Å is an alias the correlation otherwise locks onto.
- The correlation runs at whole-pixel lags with a parabolic peak. Quarter-pixel linear interpolation biased shifts ~4× low (pixel locking).
- Then all nights are smoothed to the 90th-percentile [O III] width. With a 6″ slit the seeing sets the width.
- Spectra flagged CRLINE are left out of the mean/RMS.

**Narrow-line residual in the RMS** (RMS at the line / nearby continuum):

| Line | Before | After |
|---|---|---|
| NGC 4151 [O III] | 14.7 | 6.6 (likely its extended NLR; mapspec-style kernels would do better) |
| NGC 4151 Hα | 24 | 5.7 (now the real variability) |
| Fairall 9 [O III] | 1.9 | 1.8 |
| Fairall 9 Hα | 5.9 | 5.9 (real) |

**Incremental updates:**
- `-R` with no nights reduces only nights with unreduced science frames.
- `-P` keeps `<spec_dir>/hbeta_fits.parquet` (per-spectrum fits; refit only new or changed files, or on new settings) and `spec_offsets.csv` + `spec_align_template.npz` (one cross-correlation per new spectrum).
- A fully cached `-P` for Fairall 9 (100 spectra) takes 14 s.

## AVA target table additions (16 Nov 2026, `tools/add_ava_targets.py`, `tools/new_targets/2026-11-16.yaml`)

**Added (ids 72–81):** 3C 382, Ark 564, 1H 1934-063, NGC 1566, PHL 1811, Mrk 1018, Kaz 102, Kaz 163, RX J1755.0+6519 and IRAS 09149-6206.
- Positions come from SIMBAD via Sesame (SIMBAD's TAP service and astroquery 0.4.6 both fail) and are replaced by the Gaia DR3 nucleus within 2″.
- Redshifts come from SIMBAD, or NED for Kaz 102/163. E(B−V) is SF11 from IRSA. The literature values are as supplied.

**Corrected:** id 30 is RX J2219.8**+**0935, not "RX J22198-0935": the declination is +09°35′ (SIMBAD, LCO frames). On 17 Nov 2026 its data_id became `J22198+0935` as well (`tools/db_migrate_20261117.py`, also in the lcodb links); the LCO OBJECT name stays "J22198-0935".

**LCO spellings:** all are linked by `lcodb link`, including 3C 382/3c382, Ark 564/Ark564, NGC 1566/NGC1566, PHL 1811/PHL1811, Mrk 1018/Mrk1018, RX J1755+65/RX J1755.0+6519, and "IRAS 09149-6202" (an LCO typo for 09149-6206).

**To do:**
- ~~**Kaz 163**: check which nucleus is the AGN.~~ Done 17 Nov 2026 (`tools/db_migrate_20261117.py`): the AGN is the southern nucleus, 2MASS J17465953+6836303 = Gaia DR3 1634665450507168000 (G = 16.3, quasar probability 1.00); position and `agn_gaia_dr3_id` set to it. The old position was the VII Zw 742 pair centre, near the northern galaxy; LCO frames are still linked (the field covers both), but photometry apertures must use the new position.
- **Redshift disagreements, SIMBAD vs NED:** 3C 382 0.0579 vs 0.0556; RX J1755 0.0785 vs 0.0806; PHL 1811 0.192 vs 0.194.
- **ADS bibcodes:** add them in `*_url` for the new literature values (only the citation names were supplied).
- **Vmag** is not maintained by the pipeline: only the original import set it. After the merge (PyTICS / intercalibration), the photometry package should update `agn.Vmag` (or a g-band equivalent) from the merged light curve.

## Data releases (16 Nov 2026: groundwork, no release content yet)

- **Database:** `data_releases` (one row per release), `agn_releases` (the per-AGN flag: `available` 1/0) and `release_files` (path, kind, size, SHA-256), all in `ava.db`, written by `tools/register_release.py <DR> --write` (dry run by default; backup first). `--withhold <data_id>` registers an AGN with the flag at 0, and a withhold sticks on re-registration.
- **Files:** made by a release script, still to be written. Layout: `<releases.dir>/<DR>/release.yaml` (title, description, date range, `release_date`, DOI, URL) plus `<releases.dir>/<DR>/<data_id>/[<kind>/]<files>`; the first sub-folder is the file's kind.
- **Website:** `-w` copies exactly the public files (flag 1, `release_date` passed, SHA-256 unchanged since registration) into `<web.data_dir>/releases/` and removes anything else. The target page shows a "Data releases" section with links only then (`web/includes/releases.php`).
- **To do:** the DR1 release script (contents, file formats, README per AGN); a per-AGN zip; a release list on the Data & Access page; a DOI.
- **Test archive demo:** `data/test_archive/releases/DR1` (Mrk 817 merged light curve, Mrk 817 and NGC 4151 Hβ light curves) is registered in the test-archive database only.

## Production storage: photometry images are not kept (decided 16 Nov 2026)

- **Decision (user):** photometry images (BANZAI e91 `.fits.fz`, ~38 MB per Sinistro frame) are deleted
  after they are catalogued and calibrated, after a short retention period. Catalogues, FLOYDS raw frames,
  reduced spectra and all products are kept. Storage ≈ 0.24 TB now, +30 GB/yr (keeping images would be
  ~19 TB + 2.7 TB/yr). Details: `docs/guides/deployment_guide.md` §3.1, §7.4.
- **Built (16 Nov 2026):** `scripts/cleanup.py` / `ava/archive/cleanup.py` (dry run by default; `cleanup:` config):
  photometry image deleted once catalogued + `frame_qc` at the current version + older than `retention_days`;
  FLOYDS night once every spectrum has its -1d, `spec_qc` row and `hbeta_fits` row; standards night once no target
  night on disk needs it.  `frame_qc` now also stores SATURATE and the image size (all a recalibration needs from the
  image; old rows completed from the image before deletion) and calibration falls back to it; downloads skip frames that have a catalogue; deletions marked in `local_files`.
  **Still to do:** switch `cleanup.mode: live` in production; MuSCAT re-extraction before its images go.
- **lcodb headers (16 Nov 2026):** only the FLOYDS slit width (APERWID) is used from the fetched headers
  (arc/flat + standard matching).  `headers.spectra.since: 2021-09-01` — the 14k-frame 2014–2021 backlog is not
  fetched (matched by block, then time).  Unused header columns (weather, moon, L1 stats, ...) are only exposed
  through `ava.lcodb.query`.
- New targets of 16 Nov 2026 (ids 72–81) are linked in both lcodb databases (sync of 16 Nov), but nothing
  is downloaded, catalogued or calibrated yet, and they are not in `data/test_archive/ava.db`.

## Linux set-up and legacy port (16 Nov 2026; `docs/guides/linux_setup.md`)

- `scripts/check_install.py` (machine check incl. a SExtractor test run), `tools/port_legacy.py` (old catalogues +
  raw FLOYDS -> new layout, placed by frame name via lcodb), `tools/backfill_status.py` (what is left; aperture
  survey).  `environment.yml` / `pyproject.toml` fixed (Prefect 3; build backend was invalid).
- Legacy catalogues have no images: calibration metadata from the archive listing + `camera_defaults`.
  **To do:** MuSCAT / Spectral `camera_defaults` from a real header; listing time is ~12 s later than MJD-OBS.
- Aperture choice verified per catalogue (APERDIAM, else count 10 / 12-16); other counts -> frame_qc
  `error:ValueError` (visible in `backfill_status.py --apertures`).

## LCO time-usage plots (17 Nov 2026; `ava/lco/usage.py`, `scripts/lco_usage.py`)

- Port of the legacy `ava_lco_update.py`. **The legacy script was not available on the Mac** (only opened over
  rsub from a remote host). The figure was rebuilt from two saved legacy outputs (`~/lco_usage_2024A.png`,
  `~/lco_usage_2024B.png`) and the Live Updates page text: one `lco_usage_<semester>.png` per semester,
  cumulative hours per instrument class, each axis scaled to its allocation, dashed even-pace line. Check against
  the script if it turns up.
- **Input format (decided by Claude, to confirm):** one CSV per proposal, `mjd` + **one column per LCO
  instrument class** (`1M0-SCICAM-SINISTRO`, `2M0-FLOYDS-SCICAM`, `2M0-SCICAM-MUSCAT`, ...), hours charged per
  row (not cumulative). Classes rather than telescopes, because FLOYDS and MuSCAT3 share the 2-m telescopes but
  have separate allocations and curves. Spec: `data/lco_usage/README.md`.
- **Daily curves estimated from the lcodb databases (user's idea, 17 Nov 2026):** daily exposure hours per
  proposal and instrument class (each exposure once: `exp_key` across reduction levels, MuSCAT channels merged;
  FLOYDS arcs/flats included) times charged/exposure per (proposal, semester, class) from `allocations.json`.
  Rewritten every run (`lco_usage.estimate_from_lcodb`), `data/lco_usage/estimated/` + `factors.txt`.
  Factors since 2018B are stable (1-m 1.55–1.65, FLOYDS 1.45–1.5, MuSCAT 0.6–1.2); 2014–2018A swing (0.7–7.6):
  the database is incomplete there, so the shapes of those semesters are rough (end points are exact).
  Check against the legacy 2024B plot (17 Oct 2024): 1-m ≈ 315 h vs 320 h, FLOYDS 48 % vs 47 %.
  Exposures in a semester with nothing charged to that proposal/class are dropped (e.g. KEY2018B-001 frames in
  2018A); 1-m MuSCAT frames (ep60, 2026B) are counted as 1-m time.
- **Dummy data:** `data/lco_usage/dummy/` (random split of the semester totals) is no longer used; kept as an
  example of the format. Dummy plots are watermarked and not published unless `lco_usage.publish_dummy`.
- **Publishing:** every run copies changed plots to `<web.data_dir>/usage/` (`lco_usage.publish: true`), and
  `web.usage_src` points at `data/lco_usage/plots` so `-w` copies them too.
- **Snapshots (user's idea, 17 Nov 2026; built offline, dry run):** each live run records the portal's charged
  totals (`timeallocation_set`, std + rr + tc, as the report) in `data/lco_usage/snapshots.csv`; the differences
  between runs are LCO's own charges per 6 h (overheads, failed blocks, refunds as negative rows). They take over
  from each key's first snapshot; the estimate before it is rescaled to that total. Charges recorded after a
  semester's end are drawn on its last minute. Allocations from the latest snapshot. Live only with
  `lco_usage.snapshots.mode: live` or `--live-snapshot` (one paged GET of `/api/proposals/`; `ava.lcodb.api.Client`).
  **Not yet run live:** check the first live snapshot against the report numbers before relying on it.
- **Snapshot log: seed in git, live log on the VM (user, 17 Nov 2026; daily push dropped the same day):**
  `data/lco_usage/snapshots.csv` is tracked only as the seed for the first deployment (the report's totals of
  14 Nov 2026 22:38 UTC, 81 rows, = allocations.json). The user decided against pushing it back from the VM
  (`scripts/push_lco_snapshots.sh` and its cron job removed; no deploy key with write access needed): it was only
  wanted for the first download, and the VM keeps it up to date. Production sets `lco_usage.snapshots.file` on
  the data volume, outside the checkout; the first live snapshot copies the seed there (`seed_snapshots`), so
  `git pull` never touches or conflicts with the live log, and the VM's copy diverges from git as expected.
  Chosen over keeping it in the checkout untracked or `skip-worktree` (fragile: easy to lose or commit by
  mistake). CSV, not JSON or SQLite: append-only lines, readable, cheap to append.
  Only rows of the semester in progress or changed rows are written (~0.6 MB/yr). The estimate now fills the
  time after the last snapshot (before production starts it carries 2026B on from 14 Nov), and its scaling uses
  the latest snapshot's totals and time (not the allocations file's modification time, which git loses).
- **New semester:** the current semester is always drawn (new plot from the first run after the boundary); the
  previous one is redrawn during the first `finalise_days` (7) of the new one, then frozen.
- **Overhead model (fitted 17 Nov 2026; `lco_usage.overheads`):** charged = a·exposure hours + b·exposures +
  c·blocks per instrument class, non-negative least squares over the (proposal, semester) points since 2020B
  (database complete from then; 2018B–2020A points were off by up to 2.5x), refitted every run, written to
  `estimated/overheads.txt`. Each day's weight is the model; each semester is still scaled to its charged total
  (factors now 0.93–1.10, were 1.4–1.6). Fit on 17 Nov 2026 (leave-one-out RMS, model vs flat factor):
  | Class | n | a | b (s/exposure) | c (min/block) | LOO model | LOO flat |
  |---|---|---|---|---|---|---|
  | 1-m Sinistro | 15 | 1.164 | 25.5 | 0.15 | 5.3 % | 7.4 % |
  | 2-m FLOYDS | 20 | 0.822 | 0 | 10.3 | 6.2 % | 7.6 % |
  | 2-m MuSCAT3 | 10 | 0.356 | 0 | 4.2 | 13.2 % | 22.0 % |
  Spectral (4 points) and classes with < 6 semesters use exposure hours. **Caveats:** on the 1-m, exposures and
  blocks are nearly proportional (~13 exposures per block), so only b + 13c is constrained (fitted from 2018B:
  17.5 s + 3.4 min); FLOYDS a < 1 because arcs and flats are counted as exposure time; MuSCAT a = 0.36 is
  unexplained (charging per request?). The coefficients are empirical weights, not LCO's overhead table.
  Check against the legacy 2024B plot of 17 Oct 2024: 1-m 314.8 h (flat 313.0, legacy 320.1), FLOYDS 45.1 h
  (flat 46.2, legacy 45.5). MuSCAT exposures now counted at the longest channel.
- **Plot style (user, 17 Nov 2026):** `lco_usage.style: percent`: every curve on one axis, % of its allocation,
  calendar dates, no MJD axis, legend outside the plot with used/allocated hours, website fonts and axis colours.
  Curve colours: the legacy ones (user: "keep the original colours"). The legacy layout (one y axis per class) and
  `panels` remain as options. The key project's filler programmes (`KEY....f`; legacy "New" curves) are labelled
  "(filler)" and drawn dashed.

- **LCO token (user, 17 Nov 2026):** the `lco.api_token` config key and its fallback in `ava/config.py` are removed;
  a token is never read from the config file. Sources: `LCO_API_TOKEN` / `LCO_TOKEN` env var, then `lco.token_file`
  (`~/.lco_token`).

## LCO archive: frames missing from the lcodb mirror (18 Nov 2026; 23 read-only archive requests)

- **SBIG (`kb*`) cameras were dropped by the crawl.** `config/lcodb_config.yaml` had `kb` under
  `instruments.ignore`, and ignored prefixes are not counted in `unknown_instruments`, so the loss left no trace.
  In 2014–16 many LCOGT 1 m telescopes imaged with SBIG cameras. Measured for the priority IBRM campaigns (cone
  search, levels 90/91):
  - NGC 5548 (AGN STORM 1, 2014-05-01 → 08-06): KEY2014A-002 kb 1 m, ugriz, 379 L90 (37 nights) + 130 L91.
  - NGC 4593 (2016-05-31 → 08-12): KEY2014A-002 kb 1 m, 668 L91 + 15 L90 frames on 49 nights. This roughly doubles
    the 707 frames in the mirror.
  - NGC 4151 (2016-01-08/09): KEY2014A-002 kb, 18 L91 frames (2 nights).
  - Mrk 509 (2016-06 → 2018-01): nothing missing.
  Fix and backfill are handed to a separate session (prompt `prompt_sbig_kb_recovery.md` in the side-session notes).
  The user agreed this is an oversight (18 Nov). Still open: keep the 0.4 m SBIG frames as well as the 1 m ones?
- **Non-KEY proposal with IBRM data: `LCO2014A-001`** (NGC 5548, V band only). It has 1 m SBIG frames
  (122 L90 / 61 L91, 67 nights) and early-Sinistro `fl` frames (75 L90, 52 nights), 2014-05-01 → 08-06, all public.
  Ingest it by adding the id to `proposals.ids` in the lcodb config. Not done yet; needs the user's OK.
- **The archive has no NGC 5548 frames before 2014-05-01** (cone and name searches from 2013-11 agree), so the
  Dec 2013 – Apr 2014 part of STORM 1 was not observed by LCOGT, or is not in the archive.
- Other hits were only engineering and EPO frames (`LCOEngineering`, `LCOEPO2014B-006`, `ENG2014A-003` FLOYDS
  calibrations): not useful.
- Filter rule (user, 18 Nov): only u B V g r i z Y imaging (`up B V gp rp ip zs Y`) goes into the photometry database. Other filters may be listed by the crawl but are dropped in post-processing.
- **All-target sweep, done (18 Nov 2026):** cone search of every AVA target, 2010 → 2020-07, levels 90/91,
  about 330 requests in total. After July 2020 everything is Sinistro and coverage is dense: not searched (user decision).
  - Report (private artifact): https://claude.ai/artifact/8rKKfr2fLY5t8E6QeAgvbw
  - Data: `missing_summary_pre2020-07.csv` / `missing_frames_pre2020-07.csv` in the side-session notes.
- **Ingested offline (user OK, 18 Nov 2026):** `tools/ingest_archive_sweep.py` fed the sweep's frame records
  through `ingest.Router` (cbe50d5 rules: SBIG 1 m only, u B V g r i z Y). Result: **11,996 new photometry frames**
  (6,728 KEY2014A-002 SBIG, 183 + 75 LCO2014A-001, the rest from about 55 other programmes), 0 spectra.
  - Left out: focus, engineering, calibration, pointing and EPO proposals.
  - Afterwards: `mark_best`, `lcodb airmass`, `link` and `stats` were run.
  - Backups: `data/lcodb/backups/*_20261118T102433Z_before_archive_sweep.sqlite`.
  - Linking: 11,141 frames link to AVA targets. The unlinked 855 are pointings at other objects with the AGN in the
    field (`TIC 121338379` near NGC 2617, `2016itd`, `161018`) plus `PG1302-102_ury` (18 frames). The last one
    probably wants a row in `ava_link_overrides.csv`.
  - Biggest additions: NGC 1566 (2,280; ASASSN-14ha 2014 and the 2018 outburst), PG 1302-102 (837),
    NGC 5548 2014 (803), Mrk 1048, NGC 4593 2016 (683), NGC 3783 (404; NOAO 2017 + 2020 V band).
- **Not searched: 19 northern targets.** Cone queries return HTTP 500, between RA 8h and 16h: NGC 4151, Mrk 110,
  Mrk 1220, Mrk 142, Mrk 876, Mrk 817, Mrk 279, PG 0844+349, PG 0923+201, PG 0804+761, NGC 4395, Arp 151,
  NGC 3227, NGC 4051, Mrk 704, MCG+04-22-042, SBS 1518+593, NGC 3516, NGC 5273.
  - Their KEY2014A-002 SBIG frames come in with a re-crawl, e.g.
    `lcodb sync --proposal KEY2014A-002 --since 2014-01-01 --until 2017-01-01`.
  - Other programmes for them would need name searches.
- **KEY2014A-002 re-crawl, done (user OK, 18 Nov 2026):**
  `lcodb sync --proposal KEY2014A-002 --since 2014-01-01 --until 2017-01-01 --no-standards`, 157 requests.
  Backup first: `data/lcodb/backups/*_20261118T112515Z_before_key2014_recrawl.sqlite`. Then airmass, link and stats.
  - Added 13,414 SBIG 1 m photometry frames and 9 spectra.
  - Linked: 2,559. The northern targets got NGC 3227 (881 frames, 81 nights, 2014-06 → 2016-02, V g r i),
    Arp 151 (758, 2014-11 → 2015-07), Mrk 1220 (719, 2015-04 → 06), NGC 4051 (100, 2014-05),
    NGC 4151 (36, 2016-01) and MCG+04-22-042 (9).
  - The other 13 northern targets have no SBIG frames in KEY2014A-002; their 2014–16 KEY data was Sinistro and
    is already in the mirror. Their non-KEY programmes are still unsearched.
  - 10,855 frames (61 LCO names) belong to KEY2014A-002 targets that are not in AVA: K2 fields, `1435+02`,
    `Q1133+0039`, `HS0817+1315`, `J08265+1310`, … They are candidates for the "obscure targets" review.
- Archive requests on 18 Nov 2026 for this work: about 490, of the 5000/day limit.

### SBIG 1 m frames: pipeline support (18 Nov 2026; code done, backfill not run)

- **1 m only** (user, 18 Nov). The 0.4 m SBIG cameras share the `kb` prefix but have another pixel scale.
  - lcodb: `instruments.telescopes: {kb: [1m0]}`;
  - pipeline: `photometry.camera_telescopes: {kb: [1m0]}`, applied to download, extraction and calibration
    (`ava.photometry.process.imaging_frame_ok`).
- **Camera numbers.** The header of `elp1m008-kb74-20140608-0035-e91` (NGC 5548, `KEY2014A-002`; 2 archive
  requests) gives 0.467″/px, 2×2 binning, 2045×2048, `SATURATE` 64400, read noise 13.5 e⁻, BANZAI 0.9.4, and
  a WCS. lco.global gives 0.464″/px nominal, a 15.8′ field and gain 1.4 (the header gain is 1.0 after BANZAI).
  - `pixel_scales.kb: 0.467`;
  - `camera_defaults.kb` = {64000, 2045, 2048};
  - `qc.per_camera.kb.min_matched: 15`, because the field is a third of the Sinistro field. Check this on
    NGC 5548.
- **Aperture: no SBIG override (revised 18 Nov 2026).** The old pipeline already made SBIG catalogues (e.g. NGC
  4593 2016, `kb69`) with the pre-MJD 60909 series of 10 apertures (8 … 33 px) and no `APERDIAM`. An extra
  22 px aperture for new catalogues would have split SBIG into 9.81″ (old) and 10.27″ (new), a host-light
  step inside one camera. With the default series and `kb` not in `extended_aperture_cameras`, the old
  10-aperture, 12-aperture and current 16-aperture catalogues all pick **21 px = 9.81″** (tested). The 0.7″
  difference from Sinistro's 10.5″ is left to the intercalibration. To match 10.5″ instead, every SBIG
  catalogue would have to be re-extracted from its image, old ones included.
  - Still to check on Linux: whether any legacy SBIG catalogue was made from 1×1-binned images (0.232″/px,
    4096 px wide); the 0.467″/px scale would then be wrong. `frame_qc.naxis1` will show it.
  - The legacy port now uses the same camera and telescope rule, so 0.4 m SBIG catalogues are reported and
    not copied.
- **Intercalibration.**
  - Reference cameras are now `fa` + `fl`. Before this, the Sinistro data of 2014 – Sep 2018 (`fl`) was not
    in the reference.
  - `kb` is added to the corrected cameras, like MuSCAT.
  - NGC 4593 2016 overlaps Sinistro well.
  - NGC 5548 2014 overlaps Sinistro only in V (`LCO2014A-001` `fl`), so u, g, r, i, z rely on the matched
    aperture; check the V offset.
- **Spectral (`fs`, both 2 m telescopes) checked the same way (18 Nov 2026).** It was already a kept imaging
  camera. The mirror has `fs02` at `ogg` (11,153 frames, 2014-08 → 2020-06) and `fs01`/`fs03` at `coj`
  (1,627 frames), over 17 AVA targets (Mrk 1044, NGC 4151 2016, NGC 4395, Mrk 876, Mrk 335, …).
  - **Camera numbers.** Two headers (NGC 4593 2016; 2 archive requests): `fs02` and `fs01` are both 2×2
    binned, 0.301 / 0.304″/px, with a WCS. Sizes are 2009×2009 and 2045×2013. `SATURATE` is 500000 /
    512006 e⁻, and `fs01` also has `MAXLIN` 62900. BANZAI version 0.7.9.
  - **lco.global:** 0.152″/px unbinned, 0.304″/px at the default 2×2, a 10.5′ field, gain 7.7, read noise
    10.5, and a nonlinear gain.
  - **Aperture:** consistent. Old (10), 12 and 16-aperture catalogues all pick 33 px = 10.03″ (tested).
  - **QC:** it would have rejected nearly every Spectral frame. A 10.5′ field matches about 15–20 stars against
    the general `min_matched: 30`. Added `qc.per_camera.fs.min_matched: 5`, like MuSCAT; no `fs` frame has been
    processed yet.
  - **No-image settings:** added `camera_defaults.fs` = {500000, 2009, 2009}.
  - **Intercalibration:** `fs` is added to `intercal_correct_cameras` (10.03″ vs 10.5″). Each scope, meaning
    each telescope and camera, gets its own offset. A camera with fewer than `intercal_min_pairs` (10) nights
    overlapping Sinistro gets no fit and stays calibrated by the stars only. This applies, for example, to
    SBIG on NGC 5548 in 2014 outside V.
  - Still to check on real frames: the nonlinear gain near saturation (bright comparison stars), and whether
    any 1×1-binned Spectral frame exists (`frame_qc.naxis1` ≈ 4000).
- **Nothing is dropped silently.** Frames the crawl lists but does not store (ignored prefix, telescope,
  filter) are counted in `state.sqlite` `dropped_frames`, and `lcodb stats` reports them.
- **Filter rule enforced.**
  - lcodb `photometry_filters: [up, B, V, gp, rp, ip, zs, Y]`.
  - `photometry.filters`, the download list, was `up gp rp ip zs B V R I`: it skipped Y and fetched R and I.
    It is now the same 8 filters.
  - The mirror still holds 841 older rows in U, R, I, air and `zs*diffuser`. Deleting them needs the user's OK.
- **`LCO2014A-001`** is added to `proposals.ids`.
- **Next, after a backup and the user's OK:**
  - re-list `KEY2014A-002` for 2014-01 → 2017-12 and `LCO2014A-001`, then `lcodb link`;
  - download, extract and calibrate NGC 5548, NGC 4593 and NGC 4151.
  - Budget: the archive allows 5000 requests a day per user. Listing pages hold 1000 rows, so the re-list
    is about 10–50 requests; each file download counts as one request (~1300 frames).

## Linux install: old Anaconda contingency (18 Nov 2026)

- The Linux host's Anaconda is old and runs the old pipeline. Decision: **never touch its `base`** (no
  `conda update`, no `conda-libmamba-solver` install there). `linux_setup.md` steps 2/5/6 now offer three plans:
  A) conda ≥ 23.10 as is; B) Miniforge in `~/miniforge3` **without `conda init`**, activated by path;
  C) a plain `python3 -m venv` + `pip install -e ".[dev]"` (all deps are on PyPI) if Miniforge cannot be downloaded.
- `~/.bashrc` no longer auto-activates the AVA environment: it defines an `ava-env` alias, so terminals used for
  the old pipeline keep their Python. `AVA_CONFIG` / `LCODB_CONFIG` are still exported (the old pipeline ignores them).

## Linux host: code and data in one folder (18 Nov 2026, test day)

- **PyTICS crashed on filters without frames** (pandas 3 / pyarrow 26): `store.load_pytics` passed an empty list to
  `read_parquet(filters=[("frame", "in", [])])`, which pyarrow rejects (`ArrowTypeError: large_string vs null`).
  Fixed 18 Nov: empty table returned directly (the fit loop then skips the filter). Test added.
- **PyTICS first full fit wrote `pytics/absolute_zp_stars.parquet` before `pytics/` existed** (the folder was made
  later by `Solution.save`). Fixed 18 Nov (mkdir). End-to-end test of `run_target` on a fresh folder added — the PyTICS
  step had never run to the end on a new target before the host run.
- **PyTICS on a target without catalogues** raised `FileNotFoundError` (measurements.parquet); the ensemble task now
  skips it (fixed 18 Nov, test added).
- **QC `min_matched: 30` cannot be met in sparse fields** (PG_2304+043: 57 GSPC stars, median 15.5 matched per frame,
  0 % pass; Mrk_1298: median 32). Make it scale with the field (fraction of reference stars in the footprint) or per
  target. **u band:** fields with few GSPC u stars (MR_2251-178: 10) get no u zero point at all (QC-0001).

- Decision (user): everything lives in `/data2/jvhs1/AVA`. Code is the git checkout there (in place of `~/code/AVA`);
  the data folder is `/data2/jvhs1/AVA/data` (in place of `/data3/jvhs1/ava`), already git-ignored (`data/*`), with
  `archive/`, `lcodb/`, `config/`, `logs/`, `web/`, `releases/`. `/data2` has 2.7 TB free.
- The old pipeline's data (`/data3/jvhs1/agn`, `/data2/jvhs1/agn`) is **copied** by `port_legacy.py`, never moved:
  the old pipeline keeps running.
- `linux_setup.md` is unchanged (it is written for any machine, with `~/code` and `/data3/jvhs1/ava` as examples);
  the checklist and hand-over carry the substitutions. `CLAUDE.md` updated.
- Miniforge goes in `/data2/jvhs1/miniforge3`, not `~/miniforge3`: the home folder is a CIFS network share
  (`//cfs.st-andrews.ac.uk/users/jvhs1`), where the install crawled and hit case-insensitive name clashes
  (`ncurses` terminfo). **To do:** `linux_setup.md` steps 2/5 could tell the reader to check `df -h ~` and use a
  local disk if home is a network mount. The shell also has `PYTHONPATH` set (old pipeline); `ava-env` should not
  inherit it.
- **SExtractor output columns now 16 apertures** (user, 18 Nov 2026): `data/reference/sextractor/default.param` had
  `FLUX_APER(12)` / `FLUXERR_APER(12)` / `MAG_APER(12)` / `MAGERR_APER(12)` although `default.sex` lists 16 diameters
  (36,39,43,48 appended), so SExtractor silently dropped the 4 largest while `APERDIAM` recorded 16 (found by
  `check_install.py`: "12 apertures per source"). Changed to `(16)`. Affects new extractions only;
  `reextract_on_aperture_change` stays off, ported catalogues are untouched. **To do:** `check_install.py` could
  fail when the `default.param` vector size is smaller than the `default.sex` series.
- **banzai-floyds on the Linux host** (user, 18 Nov 2026): fork `rm-improvements@3e8e796` (not the pinned `8897b99`)
  because the sky-flat order solutions now ship with the package (`11f8ce4`); that settles "Sky flats belong in the
  reduction package" above. Checkout `/data2/jvhs1/banzai-floyds`, conda env `banzai` (Python 3.12, torch 2.15.0+cpu,
  banzai 1.36.2) in `/data2/jvhs1/miniforge3`; `/data2/jvhs1/benv` runs commands in a clean shell. Config:
  `spectroscopy.reduction.{python,package,skyflats_dir}` and `paths.floyds_pipeline` set; `skyflats_dir` = the
  shipped folder. **To check at the first `-R` run:** `ava.spectroscopy.reduce.ensure_calibration_db` still runs the
  old `skyflats` step after `setup-db` (now optional, re-registers the shipped files), and `clean_env` sets
  `CC=/usr/bin/clang` (Mac); harmless unless something compiles at run time, but both should become optional.
- **`lcodb daily` crawls only the current proposals** (user, 18 Nov 2026). The first daily run on the host also
  crawled KEY2023B-001/-001f (the portal still marks them active), KEY2018B-001 and KEY2014A-002 (`proposals.ids`
  were forced active) and LCO2014A-001 from 2013 (new in `ids`, never crawled). Now: `ids` take their active flag
  from the portal (an id it does not list is inactive), and `lcodb daily` keeps only the standards sources plus the
  active proposals matching `daily.include_regex` (`'^KEY2026'` in `lcodb_config.yaml`); others are crawled on
  request with `lcodb sync --proposal ID`. The standards-by-name and COJ/OGG calibration crawls stay in the daily
  run (last `overlap_days` only): the spectra reduction needs the new standards. Test:
  `test_daily_crawls_only_active_matching_proposals`. **To do:** extend the regex when a new key project starts.
- **Prefect on the host:** `PREFECT_HOME` must be on a local disk (`/data2/jvhs1/AVA/data/prefect`): with the
  default `~/.prefect` on the CIFS home the ephemeral API server timed out at start (SQLite on a network share).
  Also `PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS=90`.
- **Reference catalogues: ESA Gaia Archive as a third source** (18 Nov 2026). CDS VizieR's query service answered 404
  all afternoon (`/viz-bin/votable`, `/viz-bin/asu-tsv`; home page up), the CfA mirror lacks Gaia DR3 / GSPC / parts of
  APASS DR9, and the other mirrors do not answer from the host: 39 of 91 reference catalogues failed (`-o`). Now
  `photometry.reference.vizier_servers` may list `gea.esac.esa.int`: `ava.photometry.reference.vizier_query` then
  runs an ADQL query on the ESA archive (async, no row cap) for `I/355/gaiadr3`, `I/355/paramp` and `I/360/syntphot`
  and returns the VizieR column names, so the GSPC builder is unchanged; the catalogue metadata records the source.
  APASS is not on ESA (the `apass_model` fallback still needs VizieR, or `apass_source: aavso`).
  Test: `test_esa_gaia_fallback_gives_vizier_columns`. **To check:** a GSPC catalogue built from ESA matches the
  VizieR one for a field built earlier today (same Gaia DR3 data; expect identical rows).

## QC-0002: reference positions rounded to 6 significant figures (18 Nov 2026; fixed in 0d3024f)

- **Bug.** `reference_stars.csv` was written with `float_format="%.6g"`: RA ≥ 100° kept 3 decimals, so stars were
  up to ±1.8″ off, against `photometry.matching.max_sep_arcsec` 1.5″. Evidence (turgon, write-up in
  `AVA_QC/tests/QC-0002_…`):
  - MR 2251-178's AGN row was 1.64″ from its Gaia DR3 position, so only 1,335 of 9,016 frames (14.8 %) matched
    the AGN; the rest were `agn_missing`.
  - Field stars of Mrk 110, Mrk 1298 and PG 2304+043 matched at medians of 0.6–0.9″, not the ~0.2–0.3″ the LCO WCS
    gives, so stars near the limit were lost (`few_matched`).
- **Fix.**
  - The reference task writes `%.10g` (≤ 0.4 mas). The meta YAML already kept full precision.
  - The FLOYDS nightly light curve writes MJD to 1e-6 d. `%.6g` had rounded it to 0.1 d.
  - `tools/target_list_crossmatch.py` (`gaia_ra`/`gaia_dec`) and `tools/spec_validation/hbeta_arms.py` (MJD) were
    fixed the same way.
  - Round-trip tests are in `tests/test_reference.py` and `tests/test_spec_lines.py`.
  - The other CSV writers use `%.4f`–`%.6f`, which is enough for MJD.
- **To do on turgon (not run yet).** Existing catalogues are still rounded.
  1. **MR 2251-178 first.** Rebuild its reference catalogue with `reference_catalog.fn("MR_2251-178", force=True)`.
     The flow never passes `force`. This queries Gaia GSPC on VizieR, not the LCO archive. `star_id` is the Gaia
     source id, so ids do not change and stored measurements stay compatible. Then re-run matching and calibration
     with `calibrate.fn("MR_2251-178", force=True)`; `force` is needed because the frames are already at the
     current `PIPELINE_VERSION`. Check that:
     - the AGN-matched fraction goes from ~15 % to ≳ 97 %;
     - field-star separations drop to ~0.2–0.3″.
  2. **Then every target with RA ≥ 100°.** Rebuilding all catalogues is cheap (one VizieR cone per target). The
     forced recalibration costs about 190 ms CPU per frame (Mrk 817 benchmark): roughly 1 CPU-hour per 20,000
     frames, and it rewrites `frame_qc` and `measurements.parquet`. Then re-run PyTICS for those targets. Agree the
     scope with the user before starting. Targets with RA < 100° kept ≥ 4 decimals (≤ 0.36″) and can wait.
  3. **Afterwards**, re-check the `few_matched` and `agn_missing` rates per target.

## B01/B09: archive requests on server errors; headers reduced to the slit width (19 Nov 2026)

- **Bug (B01).** HTTP 500/502/503/504 were retried 7 times with backoff. The header step then marked the frame
  failed and moved on, so a server-wide outage ran through the whole backlog: about 12,800 requests a day with 4
  workers, over the 5000/day account limit.
- **Bug (B09).** A run of short 429s made `Client.get` return `None`.
- **Fix:**
  - A 5xx is retried `server_error_retries` times (1).
  - After `server_error_limit` (3) consecutive failed requests, the client refuses to send and raises
    `ServerError`.
  - `headers.fetch` stops on `ServerError` as on a long 429 and leaves the frames pending.
  - The 429 path raises `Throttled` instead of falling through.
- **Decision (user, 19 Nov 2026): headers only for the slit width.**
  - One request per exposure: `pending` picks one frame per `exp_key`, and the twins inherit the value.
  - Only `aperwid` is written (`headers.columns`), and full headers are no longer stored (`store_full: false`).
  - `lcodb purge-headers [--live]` deletes the stored ones after a backup (Mac copy: 42,061 headers, 253 → 68 MB;
    all 42,037 slit widths kept).
  - Cost: about 8 header requests a day (4412 exposures since June 2025).
- **Not done:** getting the slit width without any header request. It is in the observation portal's request
  (`instrument_configs[].optical_elements.slit`), one request per observing request instead of per exposure. But
  the portal only shows our own proposals, not the calibration programmes' standards, so headers are still
  needed for those.
- Tests: `tests/test_lcodb_requests.py`.

## B02: ensemble task crashed when no camera gets an intercal fit (19 Nov 2026)

- **Bug.** `intercalibrate` returned a table with no columns when no scope could be fitted, so
  `intercal_lightcurve` failed with `KeyError: 'scope'`. This happens with a single camera, fewer than
  `intercal_min_pairs` overlapping nights, or MuSCAT only (a lone reference scope is never fitted). By then
  `run_target` had already rewritten `agn_lightcurve_pytics.parquet` without `mag_ic` / `F_ic`, and the merged
  CSV and plots were never made. Such a target failed every night.
- **Fix.** The intercal table always has its columns (`intercal.TABLE_COLUMNS`, also for the per-season table).
  With no fits nothing is corrected (`F_ic = F`), and `intercal.csv` is written with a header only. Also, the
  error model no longer warns on an empty table (`errors.sigma_rand`).
- Checked: the whole ensemble task on a synthetic single-camera target (merged CSV and the six web plots).
  Tests: `test_intercal_with_no_camera_fitted` (Sinistro only, MuSCAT only, with and without per-season offsets).

## B12 / B4ₚ / C08: a filter without an absolute zero point (19 Nov 2026)

- **Bugs.**
  - `agn_zero_points` started the AGN colour from the median `c0` of *all* filters. A failed fit (no stars) has
    `c0 = 0`, and a NaN g or i ZP made `c_agn` NaN. Since `NaN × 0 = NaN`, that turned the ZP of every filter into
    NaN, even filters without a colour term (B12).
  - The NaN `mag_ic` of a filter without a ZP then reached the error model, and `fit_s_cam` raised in `brentq`
    ("f(0) is NaN"). This hit Fairall 9 and NGC 4151 in the test-archive run, through Y with 2 stars (B4ₚ).
  - `brentq` also raised when even 0.5 mag of camera term was not enough (C08).
- **Fix.**
  - The AGN colour starts from the fits that worked and keeps the last finite value.
  - A filter with `C = 0` (or with no AGN colour) gets its plain ZP.
  - Only the failed filter stays NaN.
  - `errors.pairs` skips non-finite magnitudes.
  - `fit_s_cam` returns 0 when it cannot be computed and caps at `s_max` (0.5 mag) instead of raising.
- Not covered here: B5ₚ, dense fields where none of the 100 PyTICS stars has GSPC g and i, which gives a NaN ZP
  in every filter (MCG+08-11-011). That needs a colour-free fallback or a different star selection, and is a
  science decision.
- Tests: `test_agn_zero_points_one_failed_filter_does_not_spoil_the_others`,
  `test_error_model_ignores_filter_without_zero_point`, `test_fit_s_cam_caps_instead_of_raising`.

## B03: standards from another night were never staged for banzai-floyds (19 Nov 2026)

- **Bug.**
  - `spectrum_standards` picks the standard for each science spectrum: same slit, then 2″, then nearest,
    within 30 d. In the spectra DB that standard is on another night for 3601 of 9160 AGN science spectra
    (39 %).
  - The download files a standard (with its arc and flat) under its *own* night, `<spec_raw>/standards/<night>/`.
    But `reduce.stage` only linked `standards/<science night>`, so the chosen standard was downloaded and then
    never given to `banzai_floyds_offline chain`.
  - The flux calibration then silently used whatever standard the calibration DB already held, or none.
- **Fix (following legacy `ava_floyds_sort.py`, which copied the nearest standard into the night's folder).**
  `reduce.chosen_standards` rebuilds the download plan for the nights being reduced (offline, from the spectra
  DB) and returns the standard frames at their download paths. `spec_reduce` stages them with the nights' own
  frames, and logs any that are not on disk.
- **Still open.**
  - Nights reduced before this fix may have been flux-calibrated with another standard. `spec_qc` does not
    record which standard was used. Re-reducing them (`-R` with the nights) is a decision for later.
  - C04: cleanup frees a standard only by its own night name, so it can delete a standard that an unreduced
    night elsewhere still needs.
- Tests: `tests/test_spec_stage_standards.py`.

## B05: a run without new frames re-did the colour check against itself (19 Nov 2026)

- **Bug.** `run_target` took the filters to refit from `sol.meta["mode"] == "full"`. `update()` with no new frames
  returns the stored solution unchanged, and its meta still says `"full"`. So every quiet run went through step 2
  again: it fitted a colour-term solution and compared it with the stored one, which already had colour terms. The
  gain came out about 0, and `colour_check.use = False` was written while the terms stayed on. The absolute ZP was
  refitted for nothing, and each filter cost an extra fit per run. This is where the stale Mrk 817 record found on
  18 Nov came from.
- **Fix.** "Refitted" now means fully fitted in this run (`report[f]["mode"]` is `full` or `update->full`).
- Test: `test_rerun_without_new_frames_keeps_colour_check`. The synthetic cameras get colour slopes (±0.06 mag per
  mag), so the first run turns the terms on (gain +93 %). Before the fix, the rerun rewrote this to −4 %, `use=False`.

## B06 / B07: spectroscopy products crashed at higher redshift (19 Nov 2026)

- **B06.** At z ≈ 0.095–0.114 (e.g. PG 0804+761, z = 0.102), the Hβ fit window is covered but 5100 Å is not, so
  `cont5100` is NaN in every spectrum. `lines.nightly` then returned a table with no columns, and
  `hbeta_series` crashed on `cont.columns[2]` (`IndexError`) before any product was written.
  - Fix: `nightly` always returns its columns, and the merge uses the column names. The nightly Hβ light curve is
    kept, with `cont5100` NaN.
- **B07.** For z > ~0.19, FLOYDS' blue arm (to ~5606 Å observed) does not reach 4720 Å rest. `latest_hbeta_fit`
  then took `nanmax` of an empty selection (`ValueError`), and `spec_products` aborted for PG 0923+201, PKS 2004,
  PG 1302-102, RX J1438, J0132-0027 and SMSS J1144-43.
  - Fix: the plot is skipped (`[]`) when the blue arm has no data in the window, and the other products are made.
  - The Hβ fit itself is not done for these targets either (B08: the line is in the red arm). That is still open.
- Tests: `tests/test_spec_products_redshift.py` (all three fail on the previous commit).

## B19 / B20 / B21 / B08: FLOYDS standards, repeat reductions, sky flats, red arm (19 Nov 2026)

Found by downloading and reducing PG 0804+761 (z = 0.102) and PG 0923+201 (z = 0.193) in the Mac test archive
(31 archive requests for the frames, 6 for the headers that gave the standard positions).

- **B19, flux standards.**
  - banzai-floyds knew 7 standards, but `spectrum_standards` chose from about 40. About half of the AGN spectra
    were paired with a star banzai treats as a science target, and in a fresh calibration DB such a night gave no
    spectra.
  - Fix, in two parts:
    1. Five reference spectra added to the fork (`banzai_floyds/data/standards/`): GD 71 (X-shooter), HZ 44 and
       G191-B2B (HST), Feige 66 (Oke, extended to 11000 Å like Feige 67), CD-32 9927 (CTIO). The positions are the
       LCO catalogue positions (CAT-RA/DEC of a FLOYDS frame).
    2. lcodb matches only standards within `standards.usable_radius_arcsec` (300″) of a reference file's RA/DEC
       (`standards.reference_dir`). A FLOYDS footprint centre is about 165″ from the target, so the radius is wide;
       no two standards are that close.
  - Result in the spectra DB: 8959 of 9160 AGN spectra (98 %) get a usable standard, against about 46 % before.
    The median |Δt| goes from 0.21 to 0.29 d. L745-46A and EG 21 are not added (no good fluxed spectrum).
- **B20, repeat reductions.** `chain` rebuilt the residual templates from every standard in the calibration DB and
  raised on standards from earlier runs, which had been reduced with a template. So every second reduction in a
  work folder failed.
  - Fix, in the fork (`fringe_masters.keep_template_free`): after pass 1 the template-free -1d/-2d of each standard
    is kept as `*-notpl`, and the templates are built from those. Older standards without a copy are skipped with
    a message.
  - Checked: two targets reduced one after the other in the shared test-archive folder.
- **B21, sky flats.** COJ nights before Dec 2025 had no sky flat ("Master SKYFLAT does not exist").
  - Cause: on the Mac, `spectroscopy.reduction.skyflats_dir` pointed at a private folder with 8 of the 31 sky
    flats. The fork ships all 31 in `banzai_floyds/data/orders/skyflats/`, as the deployment guide (§4.3) says.
  - The 23 missing raw COJ sky flats were fetched into that folder (`fetch-skyflats`, 46 public requests). On a
    host, follow the guide.
- **B08+, red arm.** `spectroscopy.products.hbeta_arm: auto` measures Hβ and 5100 Å in the red arm above
  `hbeta_red_arm_above_z` (0.09), one arm per target.
  - Results: PG 0923+201 gets Hβ (red arm, 2 of 2 spectra; 0 of 2 in the blue). For PG 0804+761 the red-arm Hβ is
    6–13 % above the blue-arm value, the blue/red offset the calibration study also saw.
  - The blue arm keeps its fit-cache key.
- **B23, new.** The COJ arcs of April 2021 are marked bad without a message, even in a fresh DB, so those nights
  still give no spectra. This is in the fork's wavelength step.
- The Hβ-fit plot's residual axis is now labelled χ.

## FLOYDS: sensitivity to the standard star, and a calibration model (19 Nov 2026)

- **Test.** PG 0804+761, two OGG nights, each reduced twice with a single standard (G191-B2B against BD+28 4211,
  same night against 13–15 d away). Spectroscopy manual, "Sensitivity to the choice of standard star".
  - The grey factor differs by 0.58–0.84.
  - The shape agrees within 2–4 % in the blue arm. The red arm has a 5 % tilt and telluric structure.
  - Hβ/[O III] changes by −1.3 to +2.8 %, within the fit errors.
- **Idea (user, 19 Nov 2026): a model of the flux calibration from all the standards.** Per site, arm and slit:
  - a smooth response in wavelength and time;
  - extinction per site;
  - a grey term per night;
  - a telluric template scaled with airmass and water vapour.

  Each science spectrum would then be calibrated with the model at its own time and airmass, not with one
  standard. This should reduce the night-to-night scatter, give a consistent red end, quantify the absolute flux
  error, and tie the blue and red arms together.

## B10 / B13: `lcodb sync --proposal` (19 Nov 2026)

- **B10.** `sync --proposal A B` kept only the proposals that discovery listed. It fell back to the bare ids only
  when *none* was listed, so B was dropped without a message when A was listed (B not in `proposals.ids`, no
  `include_regex` match, or the portal was down).
  - Fix: every named proposal is crawled. The discovered ones keep their title and active flag, and the others
    are logged and crawled as named.
- **B13.** `sync --proposal ID` skipped an inactive proposal whose full crawl was done. Yet `lcodb_config.yaml`
  says inactive proposals are crawled on request with exactly that command, so the only ways left were `--full`
  (a full recrawl) or `--since`.
  - Fix: a named proposal is always crawled, from `synced_until − overlap_days`. A plain `sync` still skips it.
- Tests: `test_sync_named_proposals_not_listed_are_still_crawled`, `test_sync_named_inactive_complete_proposal_is_crawled`,
  `test_sync_plain_still_skips_inactive_complete`.
