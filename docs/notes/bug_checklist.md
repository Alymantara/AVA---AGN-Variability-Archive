# AVA bug checklist

The single list of every known bug, open action and pending decision, sorted by priority (reorganised 20 Nov 2026).
Work through **High** first. Tick an item by changing `[ ]` to `[x]`, adding the commit hash, and moving it to
**Done** at the end.

- **High:** wrong results or silently incomplete data, or needed for a fixed date.
- **Medium:** the backfill or production needs hand-set overrides; science accuracy at the 1–2 % level.
- **Low:** reporting, usability, polish, and longer-term studies.

Each item says what it is: *bug*, *action* (something to run), or *decision* (Juan decides).

**Sources.**
- B01–B18 and C items: details, evidence and failure scenarios in [bug_sweep_2026-11-18.md](bug_sweep_2026-11-18.md).
- QC items: [future_improvements.md](future_improvements.md).
- B25–B41: the Turgon backfill pilot on ESO 511-30, with item numbers in brackets from
  `fixer_bug_list_20261120.md` (repo root). Turgon runs the weekend backfill with workarounds for B25–B30.
  - Fixes must not change on-disk formats (`frame_qc`, `measurements.parquet`, `reference_stars.csv`, `pytics/`).
  - Fixes must not change existing config keys or any QC threshold.
  - When a fix is in `main`, say which workaround it retires.

**Done means:** an offline test reproduces the bug, the fix makes it pass, the full suite passes, and there is a
line in `future_improvements.md`.

---

## High

- [ ] **B26** [2] *bug*: filler proposals are never searched. 300 ESO 511-30 frames are under `KEY2023B-001f`, but only
  `lco.proposals` is used.
  - Fix: default to the lcodb proposals of the target's LCO names ∪ `lco.proposals`; `--proposal` still overrides.
    Test with a synthetic lcodb.
  - Workaround: `backfill_helpers.py proposals T`.
- [ ] **B27** [3] *bug*: a capped spectra download exits 0, its "missing" count is from before the download, and the
  chained `spec_reduce` reduces nights whose standard or calibrations are not on disk
  (`pipeline/tasks/spec_download.py`).
  - Fix: report the missing count after the run; fail when capped or incomplete; `spec_reduce` skips and lists
    incomplete nights.
  - Workaround: repeat `-D` until `0 missing`.
- [ ] **B28** [4] *bug*: the QC-0002 recipe (`reference_catalog.fn(T, force=True)`) raises `MissingContextError` outside
  a flow, and `run_pipeline.py` cannot force a catalogue rebuild or recalibration.
  - Fix: `--force-refcat` / `--force-calibrate` through `ava_target_flow`, and correct the docs.
  - Workaround: `backfill_helpers.py refcat|recal T`.
- [ ] **B33** [9] *bug/tool*, **needed Monday 23 Nov** for the VM transfer: `tools/relocate_paths.py`.
  - Rewrite `local_files.path` (both lcodb DBs) and `spec_qc.path_1d/path_2d` (`/data2/jvhs1/AVA` → `/data/ava/AVA`).
  - `--dry-run` by default; report rows changed and files missing after the rewrite.

## Medium

**Backfill and production**

- [ ] **B29** [5] *bug*: no backfill mode. A full-dataset run needs these set by hand:
  `spectroscopy.download.select: oldest`, and larger `max_frames_per_run` for spectra and SExtractor.
  - Fix: `--backfill`, or a `backfill:` block applied for that run only and logged at the start.
- [ ] **B30** [6] *bug*: `make_config.py init --force` must be given every override again.
  - Fix: `set key=value` / `unset key`, with a backup first, then `check`.
- [ ] **B31** [7] *bug*: `tools/export_web_bundle.sh` hard-codes `$REPO/web/data` and ignores `web.data_dir`
  (production layout: `data/web`).
  - Workaround: override `web.data_dir=web/data`.
- [ ] **B32** [8] *bug*: `tools/upload_web_bundle.py` has no subset upload, and reads the settings and `.netrc` only
  from `$HOME`. Turgon's home is a CIFS mount, where `chmod` does nothing.
  - Fix: `--only PREFIX`, `--settings` / `--netrc` (or environment variables), `--mark-sent`.
  - Workaround: `HOME=…/.secrets/ftp_home`, `seed_staging_manifest.py`.
- [ ] **B34** [10] *bug*: `config/lcodb_config.yaml` `standards.reference_dir` is a machine-specific `~/astro/floyds/…`
  path. Derive it from `paths.floyds_pipeline`.
- [ ] **O01** *action*: the weekly backup, job 5 "TO BUILD", the last open part of the cron set. The rest is done:
  `make_crontab.py` with `--test`, `--production`, `--install`, `--check` and `--run-now`, plus `cron_job.sh`
  (0337d2d, 3e6e2fb, b19df08, 48be80c).
- [ ] **E01** *action*, on Turgon: recalibrate (`-c`) so frames get `agn_peak` and the `agn_saturated` flag (NGC 4151
  MuSCAT 2024–25), then `--pytics-full` for every target (new anchors, error model, file format and QC gate).

**Science accuracy**

- [ ] **B43** *bug/decision* (Mrk 817 external comparison, 20 Nov): Sinistro AGN camera offsets of 1–2 % in r and z
  are not applied.
  - Offsets: z fa11 +1.3 %, 1m014-fa20 −1.9 %; r fa08 +2.4 %.
  - AVA measures them in `pytics/intercal.csv`, but `intercal_correct_cameras` lists MuSCAT only.
  - Applying AVA's own numbers removes them: χ² 55 → 8 in r, 28 → 2 in z.
  - Report: `docs/reports/mrk817_external/mrk817_external_comparison.md`.
- [ ] **E03** *bug*: the camera-to-camera term `s_cam` is too small in B and z (cross-camera pairs within 1 h: width
  1.45). Raise it, or fit it per camera family.
- [ ] **B5ₚ** *action*: recheck MCG+08-11-011 after `5f45417` ("absolute ZP from all stars").
  - The problem: `ensemble.absolute_zp` needed finite GSPC g and i for every star. In dense fields the 100 brightest
    PyTICS stars are brighter than the GSPC limit, so the ZP was NaN in every filter.
- [ ] **QC-0001** *bug*: sparse fields fail `min_matched: 30` (PG 2304+043: 0 % pass), and fields with few GSPC u stars
  get no u zero point (MR 2251-178).
- [ ] **C10** *decision*: fa08 `up` gets no zero point (0 of 172 frames). Hardware, or a U/up label?
  - Includes the fa08 part of B04: the per-camera `zp_offset` is in `c5b79eb`; decide whether fa08 B is usable.
- [ ] **B23** *bug* (banzai-floyds fork): the COJ arcs of April 2021 (PG 0923+201) are marked bad with no log message,
  even in a fresh calibration DB, so those nights give no spectra ("Master ARC does not exist"). Probably the
  wavelength priors or LSF history are tuned on recent data.
- [ ] **B41** [17] *bug*: distant standards. 12 of 180 ESO 511-30 science spectra are matched to a standard more than
  3 days away (up to 714 h). Flag them in `spec_qc`, and check them after the [O III] calibration.
- [ ] **E07** *decision*: the AGN magnitude system. Publish in the LCO natural AB system, with reference-system fluxes
  as a derived product (emission lines: up to 0.18 mag in r)? See the calibration report.

## Low

**Reporting and usability**

- [ ] **B35** [11] *bug*: the `backfill_status.py` FLOYDS table counts science frames only. It showed `to_download 0`
  while 263 standards, arcs and flats were missing.
- [ ] **B36** [12] *bug*: the `backfill_status.py` photometry table counts all filters (9339 vs 9151 in
  `photometry.filters`).
- [ ] **B37** [13] *bug*: no progress output during spectra reduction. Log one line per finished night (n of N).
- [ ] **B38** [14] *bug*: `local_files` misses the files ported from the old pipeline (175 raw spectra). Register them,
  or document that it covers AVA downloads only.
- [ ] **B39** [15] *decision*: "To be processed" (`agn.ava = 0`) stays after a full backfill until
  `tools/set_archived.py T --write`. Should the backfill set Archived itself?
- [ ] **C02** *decision*: `merge` (`-m`/`-s`) raises `NotImplementedError`. Remove the flags, or port the step?

**Longer-term studies (PyTICS error bars and calibration, pair test of 19 Nov)**

Evidence: `docs/reports/pytics_update/pair_test_all_agn.md` and `docs/reports/abscal/report_abscal.md`.

- [ ] **E02**: a per-epoch floor. $s_0$ follows the observing conditions:
  - exposure: 1.5 mmag at ≤ 30 s against 0.95 at ≥ 60 s;
  - airmass: 1.1 → 1.7 from 1.2 to 1.7;
  - seeing: 1.0 → 1.7 from 1.5″ to 3.5″;
  - night to night: 0.4 mmag.

  Model it as scintillation (Young: D, airmass, exposure) plus a seeing term? This needs `exptime`, `airmass` and
  seeing per epoch.
- [ ] **E04**: the peak cut for the comparison stars too (`measurements.parquet` needs the peak).
- [ ] **E05**: fit the floor on star pairs as well (8 M pairs; per camera, fa08 1.5 mmag against 0.9–1.2 elsewhere).
- [ ] **E06**: check MuSCAT `saturate` (118000, from catalogue pile-up) and Spectral (2016 headers) against a current
  e91 header.
- [ ] **E08**: per-camera passbands (mirrors; MuSCAT, SBIG, Spectral) and the B/V/i synthetic-vs-empirical colour-term
  mismatch, before relying on B, V, i and u at the 1 % level.
- [ ] **E09**: PS1 DR2 y anchors for 12.5 < G < 14.2 (dec > −30°), so Y has bright anchors.

**On hold or running elsewhere**

- [ ] **QC-0003**: model u for GSPC stars without a validated u. **On hold (user, 18 Nov)**: the changes are
  uncommitted in the working tree; plan in `future_improvements.md`.
- [ ] **QC test**: frame QC on the PyTICS input (its own session, "Test frame QC on PyTICS input").

**Not code (for the record)**

- DR1 release files are missing on Turgon: the Mrk 817 merged light curve and Hβ, and NGC 4151 Hβ.
- There is no SSH route to the VM for `ava` / `jvhs1`. Transfers go by hand on Monday; a permanent route needs IT.

---

## Done

**20 Nov 2026**
- [x] **B25** [1] (B25 commit): the archive search read only the first page of each window, because it followed
  `next`, which is an estimate for some filters (ESO 511-30, 365-day windows: 4331 of 9151 frames).
  - Now `ava.lco.download.listing_pages` pages by `offset` + `ordering='id'` until a short page, for photometry
    windows and spectra request listings.
  - Retires the Turgon workaround of `--window-days` per target (< 800 frames per window).
- [x] **B40** [16] (`c5b79eb`): the QC gate before PyTICS dropped 34.4 % of ESO 511-30 frames.
  - `agn_flagged` now uses FLAGS 4|8|16 only.
  - The zero-point flags no longer gate PyTICS.
  - `zp_offset` is measured per camera.
  - The Sinistro AGN peak cut is 1.0.
  - Frames into PyTICS: 66 % → 96 %.
- [x] **B04** (`c5b79eb`): `zp_offset` used the median ZP per camera family; it is now per camera. The fa08 question
  is in C10.
- [x] **B42** (`fd6d040`): Hβ light-curve plot: no white marker edge, smaller markers, [O III] 4959 orange (colour-blind
  safe next to the green).
- [x] **C04** (`5188bb4`): a raw standard night is deleted only when every AVA science spectrum using its standard, arc
  or flat is reduced, and it is older than the matching window plus the look-back.
- [x] **C05** (`a2e86ed`): signed S3 URLs are removed from download error logs (`describe_error`).
- [x] **C06** (`4c4f8f1`): the spectra download checks the instrument prefix (FLOYDS `en`).
- [x] **C07** (`226ea62`): the spectra alignment template is rebuilt when its settings change.
- [x] **C09** (`53ba092`): the colour check uses `intercal_min_pairs`; the colour comes from `ensemble.colour_bands`.
- [x] **C11** (`3869531`): stars with NaN RUWE fail `quality_ok` (also applied on read).
- [x] **C12** (`974fa44`): the website's `ava_stats()` uses the target filter.

**19 Nov 2026**
- [x] **B01** (`797debc`): a repeated HTTP 500 was retried 7× and the header step never stopped. Headers are now
  reduced to the slit width.
- [x] **B02** = B3ₚ (`8ded558`): the ensemble task crashed when no camera got an intercalibration fit.
- [x] **B03**: standards from another night were downloaded but never staged (39 % of spectra). Earlier reductions
  were not redone.
- [x] **B05**: a run with no new frames re-ran the colour check against itself.
- [x] **B06 / B07**: `spec_products` crashed when 5100 Å was not covered; the latest-Hβ plot crashed for z > 0.19.
- [x] **B08 / B08+** (`05fc389`): Hβ and 5100 Å come from the red arm above z = 0.09 (`products.hbeta_arm: auto`).
- [x] **B09** (`797debc`): a run of short 429s made `Client.get` return `None`.
- [x] **B10 / B13**: `sync --proposal` dropped undiscovered proposals and skipped inactive crawled ones.
- [x] **B11**: `MAG_APER = 99` rows reached `measurements.parquet` and PyTICS.
- [x] **B12** = B4ₚ (`8ded558`, `93ce9f5`): a failed g or i absolute ZP made every filter's ZP NaN; NaN `mag_ic` epochs
  are dropped.
- [x] **B14**: a GSPC star within 2″ could be relabelled as the AGN.
- [x] **B15**: R/I frames with an APASS-fallback catalogue raised `KeyError`.
- [x] **B16**: a NaN `saturate`/`naxis` rejected every standard.
- [x] **B17**: frames that raised an exception were never retried.
- [x] **B18**: "newest first" in SExtractor sorted by site, not by date.
- [x] **B19** (fork `9e34c07`): 5 reference spectra added to banzai-floyds; lcodb matches only standards with one
  (98 % of AGN spectra get a usable standard).
- [x] **B20** (fork `9e34c07`): a second reduction run in the same work folder failed on residual templates.
- [x] **B21**: the 23 missing COJ sky flats before 2025-12-08 were fetched.
- [x] **B22**: SyntaxWarning in `ava/plots/webplots.py`.
- [x] **B24**: no LCO token under cron. There is now one lookup (`ava.lco.token`), checked by `make_crontab.py --check`.
- [x] **B1ₚ / B2ₚ** (`93ce9f5`): a relative `frame_db` resolved from the wrong root; with no filter reaching
  `min_epochs`, the ensemble task raised.
- [x] **C01**: `nightly_steps` is the full production list; `schedule_cron` is 02:00 UTC.
- [x] **C03** (6baad1e, 48be80c): `LCODB_CONFIG` is honoured.
- [x] **C08** (with B12): `errors.fit_s_cam` is capped at 0.5 mag.
- [x] **O02**: daily health check, `scripts/daily_check.py`.
- [x] **QC-0002** (`0d3024f`, Turgon `a1f6fed`): reference positions were rounded to 6 significant figures.
- [x] PyTICS crashes from the first host run (`f1adb46`): empty pyarrow filter, missing `pytics/` folder, a target
  without photometry.
