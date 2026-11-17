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

## Reference catalogue

- Mirror reliability: `vizier.cfa.harvard.edu` lacks GSPC + APASS DR9 around NGC 5548; CDS (first in
  `vizier_servers`) is expected to work from St Andrews — confirm.
- Rebuild the stellar-atmosphere grid (log g, [M/H] dimensions) if the `apass_model` fallback is kept.

## PyTICS ensemble (Nov 2026 overnight run; report `docs/pytics_report.md`)

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
  Material for the manual (user writes it): `docs/pytics_algorithm_changes.md`, `docs/figures/pytics/pytics_workflow.pdf`.
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

**Corrected:** id 30 is RX J2219.8**+**0935, not "RX J22198-0935": the declination is +09°35′ (SIMBAD, LCO frames). Its data_id `J22198-0935` is kept.

**LCO spellings:** all are linked by `lcodb link`, including 3C 382/3c382, Ark 564/Ark564, NGC 1566/NGC1566, PHL 1811/PHL1811, Mrk 1018/Mrk1018, RX J1755+65/RX J1755.0+6519, and "IRAS 09149-6202" (an LCO typo for 09149-6206).

**To do:**
- **Kaz 163** (a galaxy pair) has no Gaia source within 2″ of NED's position. The nearest is G = 20.3 at 2.8″, which coincides with the LCO pointing. Check which nucleus is the AGN before setting `agn_gaia_dr3_id`.
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
  ~19 TB + 2.7 TB/yr). Details: `docs/deployment_guide.md` §3.1, §7.4.
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

## Linux set-up and legacy port (16 Nov 2026; `docs/linux_setup.md`)

- `scripts/check_install.py` (machine check incl. a SExtractor test run), `tools/port_legacy.py` (old catalogues +
  raw FLOYDS -> new layout, placed by frame name via lcodb), `tools/backfill_status.py` (what is left; aperture
  survey).  `environment.yml` / `pyproject.toml` fixed (Prefect 3; build backend was invalid).
- Legacy catalogues have no images: calibration metadata from the archive listing + `camera_defaults`.
  **To do:** MuSCAT / Spectral `camera_defaults` from a real header; listing time is ~12 s later than MJD-OBS.
- Aperture choice verified per catalogue (APERDIAM, else count 10 / 12-16); other counts -> frame_qc
  `error:ValueError` (visible in `backfill_status.py --apertures`).

