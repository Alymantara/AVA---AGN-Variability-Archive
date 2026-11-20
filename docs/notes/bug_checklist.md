# AVA bug checklist

This is the single list of every known bug, in the order to work through them. Tick an item by changing `[ ]` to `[x]`
and adding the commit hash. Details, evidence and failure scenarios for B01–B18 and the C items are in
[bug_sweep_2026-11-18.md](bug_sweep_2026-11-18.md). The QC items are described in
[future_improvements.md](future_improvements.md).

**Owner:** *main* = this session (pipeline bug sweep); *QC* = the "Fix frame QC bugs" session.
**Done means:** an offline test reproduces the bug, the fix makes it pass, the full suite passes, and there is a
line in `future_improvements.md`.

## 1. High: fix first

- [x] **B01** (main, lcodb; fixed in `797debc`; also: headers reduced to the slit width, stored headers purged on the Mac): a repeated HTTP 500 is retried 7×, and the header step never stops. This could exceed
  the 5000 requests/day limit. `ava/lcodb/api.py:96`, `ava/lcodb/headers.py:43`.
- [x] **B02** (main, ensemble; fixed 19 Nov, see the B02 commit; = B3ₚ of the PyTICS test-archive run): the ensemble task crashes when no camera gets an intercalibration fit (single camera,
  fewer than 10 overlap nights, MuSCAT only). `ava/pipeline/tasks/ensemble.py:46`.

## 2. Medium

- [x] **B03** (main, spectroscopy; fixed 19 Nov, see the B03 commit; earlier reductions not redone): standards from another night are downloaded but never staged (39 % of spectra).
  `spectroscopy/download.py:117`, `reduce.py:109`.
- [ ] **B04** (QC): the `zp_offset` check uses the median ZP per camera *family*, not per camera, and drops all
  173 fa08 B frames. Needs a decision on fa08. `photometry/process.py:141`.
- [x] **B05** (main, ensemble; fixed 19 Nov, see the B05 commit): a run with no new frames re-runs the colour check against itself and writes a stale
  record. `photometry/ensemble.py:472`, `:699`.
- [x] **B06** (main, spectroscopy; fixed 19 Nov, B06/B07 commit): `spec_products` crashes when 5100 Å is not covered (z ≈ 0.095–0.114).
  `spectroscopy/products.py:126`.
- [x] **B07** (main, spectroscopy; fixed 19 Nov, B06/B07 commit; Hβ itself is B08+): the latest-Hβ web plot crashes for z > 0.19 (6 targets). `spectroscopy/webplots.py:157`.
- [x] **B08** (main, spectroscopy; fixed by B08+, `05fc389`): Hβ is always fitted in the blue arm, so there is no Hβ for Mrk 876, 3C 273 or
  PDS 456 (z ≳ 0.11). `spectroscopy/lines.py:79`, `products.py:84`.
- [x] **B09** (main, lcodb; fixed in `797debc` with B01): a run of short 429s makes `Client.get` return `None`. `lcodb/api.py:85`.
- [x] **B10** (main, lcodb; fixed 19 Nov, B10/B13 commit): `sync --proposal A B` silently drops B when discovery doesn't list it. `lcodb/ingest.py:196`.
- [x] **B11** (QC; fixed 19 Nov, B11 commit; no change on Mrk 817): `MAG_APER = 99` rows go into `measurements.parquet` and PyTICS. `photometry/catalogs.py:228`,
  `process.py:91`.

## 3. Low

- [x] **B12** (main, ensemble; fixed 19 Nov with B4ₚ, same commit as B02): a failed g or i absolute ZP makes the ZP of every filter NaN.
  `photometry/ensemble.py:845`.
- [x] **B13** (main, lcodb; fixed 19 Nov, B10/B13 commit): `sync --proposal ID` skips an inactive proposal that was already crawled. `lcodb/ingest.py:215`.
- [x] **B14** (main, photometry; fixed 19 Nov; never happened in the 39 test catalogues): a GSPC star within 2″ can be relabelled as the AGN. `photometry/reference.py`
  (`assign_star_ids`).
- [x] **B15** (main, photometry; fixed 19 Nov, B15 commit; R/I/U now not calibrated at all): R/I frames with an APASS-fallback catalogue raise `KeyError 'lco_R'`.
  `photometry/calibration.py:41`.
- [x] **B16** (QC; fixed 19 Nov, B16 commit): a NaN `saturate`/`naxis` rejects every standard, so the frame silently gets `no_zp`.
  `photometry/calibration.py:76`.
- [x] **B17** (QC; fixed 19 Nov, B17 commit): frames that raised an exception are never retried. `photometry/process.py:227`.
- [x] **B18** (main, photometry; fixed 19 Nov, B18 commit): "newest first" in SExtractor sorts by site, not by date. `pipeline/tasks/sextract.py:56`.

## 3b. Found on 19 Nov (high-z spectra download and reduction test)

- [x] **B19** (fixed 19 Nov, fork `9e34c07` + AVA: 5 reference spectra added to the fork, and lcodb matches only standards with one; 98 % of AGN spectra get a usable standard) (spectroscopy + banzai-floyds data): banzai-floyds knows only 7 flux standards (Feige 110, Feige 34,
  GD 153, GD 108, EG 274, Feige 67, BD+28 4211), but `spectrum_standards` picks from about 40. About half of the
  9160 AGN spectra are paired with a standard banzai cannot use (GD 71, HZ 44, Feige 66, L745-46A, CD-32 9927,
  G191-B2B, ...). banzai classifies it as science; in a fresh calibration DB the night gives no spectra
  ("Master STANDARD does not exist"). Decision: add reference spectra to banzai, or restrict the choice to the 7.
- [x] **B20** (fixed 19 Nov in the fork, `9e34c07`: template-free copies of standards kept; older ones skipped) (banzai-floyds fork): `chain` rebuilds the residual templates from every standard in the calibration
  DB, and raises on standards from earlier runs (`fringe_masters.py:157`, "processed with a residual template").
  A second reduction run in the same work folder fails, which breaks incremental reduction.
- [x] **B21** (fixed 19 Nov: the 23 missing COJ sky flats fetched, 46 public requests) (banzai-floyds data): COJ sky flats only from 2025-12-08 (OGG from 2019-03-29). COJ nights before
  then get "Master SKYFLAT does not exist" and no spectra. Fetch older COJ sky flats.
- [x] **B08+** (fixed 19 Nov: `products.hbeta_arm: auto`, red above z = 0.09) (main, spectroscopy): use the red arm for Hβ and 5100 Å per target when the blue arm does not reach
  them (z ≳ 0.09). The red arm starts at 4524 Å (COJ) / 4893 Å (OGG). One arm per target, because of the blue/red
  offset found by the calibration study. Measured today: the PG 0804+761 (z = 0.102) OGG blue arm ends at 5090 Å
  rest, so 5100 Å comes from about 10 Å at the window edge.

- [ ] **B23** (banzai-floyds fork): the COJ arcs of April 2021 (PG 0923+201) are marked bad without any log message,
  also in a fresh calibration DB, so those nights give no spectra ("Master ARC does not exist"). Probably the wavelength
  priors / LSF history tuned on recent data. Found 19 Nov while testing B21.

## 3c. From the PyTICS test-archive run (QC test session, 19 Nov)

- [x] **B1ₚ** (`93ce9f5`): `tasks/calibrate.frame_db_path` resolved a relative `photometry.calibration.frame_db` from
  `ava_root` instead of `archive_root`. A missing frame-QC DB then read as "0 frames" in every filter; the ensemble
  task now warns and skips.
- [x] **B2ₚ** (`93ce9f5`): with no filter reaching `min_epochs`, the ensemble task raised `FileNotFoundError` on
  `agn_lightcurve_pytics.parquet` (NGC 3783, NGC 7469, PG 2304+043). It now skips.
- [x] **B3ₚ** = B02 (`8ded558`).
- [x] **B4ₚ** library side = B12 (`8ded558`). Task side (`93ce9f5`): NaN `mag_ic` from a filter without an absolute
  ZP crashed the merged plots and reached the merged CSV (Fairall 9, NGC 4151). Those epochs are dropped with a
  warning.
- [ ] **B5ₚ**: `ensemble.absolute_zp` needed finite GSPC g and i for every star, even with the colour term off. In
  dense fields the 100 brightest PyTICS stars are brighter than GSPC's g/i limit (G ≲ 13), so the ZP is NaN in
  every filter (MCG+08-11-011). Recheck MCG+08-11-011 after `5f45417` ("absolute ZP from all stars").
- [x] **B22** (fixed 19 Nov, B22 commit; no other file has a SyntaxWarning): `ava/plots/webplots.py:41` SyntaxWarning, invalid escape `'\ '` in a docstring.

## 3d. Production operations: to do first (user, 19 Nov)

- [ ] **O01: ready-to-install cron / service files.** *(19 Nov: `scripts/make_crontab.py` (`--test` / `--production` / `--install`) and `scripts/cron_job.sh` committed (0337d2d, 3e6e2fb, b19df08), `--check` / `--run-now` (48be80c). Open: the weekly backup. Fresh-install round, 19 Nov: overrides config + make_config, Prefect env, dry cleanup, UTC.)* The scripts exist (`scripts/lcodb_daily.sh`, `scripts/deploy.py`
  for the Prefect flow, `scripts/cleanup.py --live`, `scripts/lco_usage.py --live-snapshot`), but the crontab is
  only written out in `deployment_guide.md` §7, with `/opt/ava` example paths. To do:
  - a `deploy/` folder with `crontab.example` and systemd units for the Prefect server and worker;
  - `AVA_CONFIG` / `LCODB_CONFIG` and log redirection on every line;
  - one consistent timetable. Today they disagree: the guide has `lcodb daily` at 01:00 and the flow at 02:00,
    while `pipeline.prefect.schedule_cron` is 10:30, with a comment saying `lcodb daily` runs at 09:30;
  - production `nightly_steps` set (C01: no `pytics`, `spec_*` now);
  - the weekly backup (job 5, "TO BUILD").
- [x] **O02: daily health check.** *(19 Nov: `scripts/daily_check.py`, not committed.)* Nothing reports whether the daily update ran. `lcodb status` prints
  sync state and the last runs (table `runs`), but by hand only. To do: `scripts/daily_check.py`, run by cron
  after the daily jobs. It checks:
  - the last `lcodb daily` run (status, age);
  - `synced_until` of the active proposals;
  - the newest frame in the databases;
  - per-target `download_state`;
  - the newest `frame_qc.processed_utc`;
  - the last Prefect flow run;
  - the cleanup and LCO-usage logs.

  It prints one summary and exits non-zero when anything is stale or failed, so cron mail / alerting fires.

- [x] **B24** (VM cron test, 19 Nov): no LCO token under cron (three lookups; token only in an exported variable).
  Fixed: one lookup `ava.lco.token`, templates point at `<install root>/.secrets/lco_token`, `check_install` and
  `make_crontab.py --check` test it as cron sees it.

## 3e. From the Turgon backfill pilot (ESO 511-30, 20 Nov)

Evidence and fixes: `fixer_bug_list_20261120.md` (repo root; item numbers in brackets). Turgon runs the weekend
backfill with workarounds for B25–B30, so fixes must not change on-disk formats (`frame_qc`, `measurements.parquet`,
`reference_stars.csv`, `pytics/`) or existing config keys, and must not change any QC threshold. When a fix is in
`main`, say which workaround it retires.

**High: wrong results or silently incomplete data**

- [ ] **B25** [1]: the archive search reads only the first page of each window: `ava/lco/download.py::pages()` follows
  `next`, which is an estimate for some filters (365-day windows found 4331 frames, 90-day windows 9151). Page by
  `offset` + `ordering='id'` until a short page, as `lcodb.api.Client.frames()` does. Workaround: `--window-days` per
  target, < 800 frames per window.
- [ ] **B26** [2]: filler proposals are never searched (300 ESO 511-30 frames under `KEY2023B-001f`); only
  `lco.proposals` is used. Default to the lcodb proposals of the target's LCO names ∪ `lco.proposals`. Workaround:
  `backfill_helpers.py proposals T`.
- [ ] **B27** [3]: a capped spectra download exits 0, its "missing" count is from before the download, and the
  chained `spec_reduce` reduces nights whose standard or calibrations are not on disk
  (`pipeline/tasks/spec_download.py`). Report missing after the run, fail when capped or incomplete, and skip and list
  incomplete nights in `spec_reduce`. Workaround: repeat `-D` until `0 missing`.
- [ ] **B28** [4]: the QC-0002 recipe (`reference_catalog.fn(T, force=True)`) raises `MissingContextError` outside a
  flow, and `run_pipeline.py` cannot force a catalogue rebuild or recalibration. Add `--force-refcat` /
  `--force-calibrate` through `ava_target_flow`, and correct the docs. Workaround: `backfill_helpers.py refcat|recal T`.

**Medium: the backfill needs hand-set overrides**

- [ ] **B29** [5]: no backfill mode. A full-dataset run needs `spectroscopy.download.select: oldest` and larger
  `max_frames_per_run` (spectra, SExtractor) set by hand, plus B25–B26. Add `--backfill` / a `backfill:` block for
  that run only.
- [ ] **B30** [6]: `make_config.py init --force` must be given every override again. Add `set key=value` / `unset key`
  (backup first, then `check`).
- [ ] **B31** [7]: `tools/export_web_bundle.sh` hard-codes `$REPO/web/data` and ignores `web.data_dir` (production
  layout `data/web`). Workaround: override `web.data_dir=web/data`.
- [ ] **B32** [8]: `tools/upload_web_bundle.py` has no subset upload, and reads settings / `.netrc` only from `$HOME`
  (CIFS home on Turgon, where `chmod` does nothing). Add `--only PREFIX`, `--settings` / `--netrc` (or env vars),
  `--mark-sent`. Workaround: `HOME=…/.secrets/ftp_home`, `seed_staging_manifest.py`.
- [ ] **B33** [9]: `tools/relocate_paths.py` for the VM transfer (needed Monday 23 Nov): rewrite `local_files.path`
  and `spec_qc.path_1d/path_2d` (`/data2/jvhs1/AVA` → `/data/ava/AVA`), `--dry-run` default.
- [ ] **B34** [10]: `config/lcodb_config.yaml` `standards.reference_dir` is a machine-specific `~/astro/floyds/…` path.
  Derive it from `paths.floyds_pipeline`.

**Low: reporting and usability**

- [ ] **B35** [11]: `backfill_status.py` FLOYDS table counts science frames only (showed `to_download 0` with 263
  standards/arcs/flats missing).
- [ ] **B36** [12]: `backfill_status.py` photometry counts all filters (9339 vs 9151 in `photometry.filters`).
- [ ] **B37** [13]: no progress output during spectra reduction; log one line per finished night (n of N).
- [ ] **B38** [14]: `local_files` misses the files ported from the old pipeline (175 raw spectra). Register them, or
  document that it covers AVA downloads only.
- [ ] **B39** [15]: "To be processed" (`agn.ava = 0`) stays after a full backfill until `tools/set_archived.py T
  --write`. Decide whether the backfill sets Archived itself.

**Design decisions (next week, with the user)**

- [ ] **B40** [16]: the QC gate before PyTICS (`photometry/store.py::load_pytics`, `qc_pass = 1`) drops 34.4 % of
  ESO 511-30 frames. Diagnosis 20 Nov (session "Why PyTICS QC drops many ESO 511 frames"):
  - `agn_flagged` is SExtractor FLAGS = 2 (deblended from the barred host), not saturation: no frame has FLAGS 4,
    `agn_saturated` = 0, peak/SATURATE ≤ 0.15. Flagged and clean frames of the same night agree to 0.3–2 mmag.
    The comparison stars use `bad_flags` 28 (4|8|16).
  - z `zp_scatter`: the field's median is 0.123 against a 0.12 limit, in every camera and year; the per-frame ZP has
    no colour term. PyTICS does not use that ZP.
  - u `zp_offset`: the median is per family, so the per-camera u ZP spread (±0.6 mag, fa08 −2.36) is flagged; a
    per-camera median cuts 350 flags to 69 (same as B04).

  Proposal (no threshold value changes): the AGN flag mask = `bad_flags` (28); gate PyTICS on measurement flags only
  (`seeing`, `few_matched`, `agn_missing`); `zp_dev` median per camera. Drops 34.4 % → 4.4 %.
- [ ] **B41** [17]: distant standards: 12 of 180 ESO 511-30 science spectra matched to a standard more than 3 days
  away (up to 714 h). Flag them in `spec_qc` and check them after the [O III] calibration.

- [x] **B42** (user, 20 Nov; fixed 20 Nov: no white marker edge, markers ~30 % smaller (g 5, Hβ 6, [O III] 4.5, 5100 Å 5), [O III] 4959 orange `#E69F00` instead of pink, which deuteranopes could hardly tell from the green; checked on a synthetic 400-night series): Juan did not like the Hβ light-curve web plot
  (`ava/spectroscopy/webplots.py::hbeta_lightcurve`): the points have a white edge (`mec="white"`) and are a bit too
  big (`ms` 6–9 in the g-band, Hβ, line and 5100 Å panels). It looks fine with few points, but messy when they bunch
  together (e.g. intensive campaigns). Remove the white edge and make the markers smaller; perhaps scale the marker
  size with the number of points so sparse light curves keep their look. Check on a dense target (Mrk 817).

Not code, from the same pilot: DR1 release files missing on Turgon (Mrk 817 merged LC and Hβ, NGC 4151 Hβ); no SSH
route to the VM for `ava` / `jvhs1` (transfers by hand on Monday; a permanent route needs IT).

## 4. QC items already opened by the QC session

- [ ] **QC-0001** (QC): sparse fields fail `min_matched: 30` (PG 2304+043: 0 % pass); fields with few GSPC u
  stars get no u zero point (MR 2251-178).
- [x] **QC-0002** (QC): reference positions rounded to 6 significant figures. Fixed in `0d3024f`; turgon
  follow-up `a1f6fed`.
- [ ] **QC-0003** (QC): model u for GSPC stars without a validated u. **On hold (user, 18 Nov)**: the commit was
  undone on purpose and the changes are uncommitted in the working tree. Waits for updated model atmospheres.
- [ ] **QC test** (QC): frame QC on the PyTICS input, running in its own session (Test frame QC on PyTICS input).

## 5. To confirm (decision or unverified; tick when decided)

- [x] **C01** (decided 19 Nov: the full production list; `schedule_cron` 02:00 UTC): `nightly_steps` has no `pytics`, so the scheduled run never updates the ensemble light curves.
  Intended? `config/ava_config.yaml:578`.
- [ ] **C02**: `merge` (`-m`/`-s`) raises `NotImplementedError`. Remove the flags or port the step?
- [x] **C03** (fixed 19 Nov, 6baad1e/48be80c: `lcodb_config_path` honours `LCODB_CONFIG`, then `data/config/`, then the template): AVA ignored `LCODB_CONFIG` (`ava/config.py:248`).
- [x] **C04** (fixed 20 Nov, rule agreed with the user: a raw standard night goes only when every AVA science spectrum in the lcodb spectra DB that uses its standard, arc or flat is reduced (`spec_qc`), covering all targets and the backfill, AND it is older than the matching window (lcodb `standards.max_dt_days` 60 d + look-back), so no new night can pick it; no spectra DB: nothing freed; a spectrum whose reduction fails keeps its standard): cleanup can delete a standard that an unreduced night elsewhere still needs (`archive/cleanup.py:291`).
  Fix together with B03.
- [x] **C05** (fixed 20 Nov: `ava.lco.download.describe_error` removes URL query strings from every recorded download failure and log line, photometry and spectra): signed S3 URLs (valid 48 h) appeared in download error logs.
- [x] **C06** (fixed 20 Nov: `Query.keep` checks the camera prefix for spectra too, from the lcodb `instruments.spectra` (en); the night-based spectra download reads the lcodb spectra DB, which holds FLOYDS only, so it was already safe): the spectra download filter had no instrument check (a SOAR spectrum with the same target name would be kept).
- [x] **C07** (fixed 20 Nov: the template stores its settings (windows, masks, max shift, red range, high-pass); a change rebuilds the template and every offset, like a change of z. Existing templates are rebuilt once on the next run): `arm_offsets` kept stale offsets after the `align_*` settings changed.
- [x] **C08** (fixed with B12: capped at 0.5 mag): `errors.fit_s_cam` (`brentq` up to 0.5 mag) can raise.
- [x] **C09** (fixed 20 Nov: `colour_term_check` gets `intercal_min_pairs`; the colour of every colour term is `ensemble.colour_bands` (default `[g, i]`, so results unchanged); after changing it run mode full): `colour_term_check` ignored `intercal_min_pairs`; `run_target` hard-coded `g − i`.
- [ ] **C10**: fa08 `up` gets no zero point (0 of 172 frames). Hardware or a U/up label? (Look at it together with B04.)
- [x] **C11** (fixed 20 Nov: `quality_ok` needs a known RUWE when built, and `read_reference` applies it to existing catalogues, so no rebuild; 0–13 stars per field, ~0.5 %): stars with NaN RUWE passed `quality_ok`.
- [x] **C12** (fixed 20 Nov: images, spectra and the first date now use `ava_target_filter_sql()`, like the target count; on the current site 514 602 images instead of 514 608, spectra and start year unchanged): the website's `ava_stats()` summed over all targets, without the target filter.

## 6. PyTICS error bars and calibration: decisions from the pair test (19 Nov 2026)

Evidence: `docs/reports/pytics_update/pair_test_all_agn.md` and
`docs/reports/abscal/report_abscal.md`. Done in `6b7dc5e`: the floor is part of the error model,
`error_model: fitted` is the default, MuSCAT saturation is set, and there is an AGN peak check.

- [ ] **E01** (turgon, action): recalibrate (`-c`) so frames get `agn_peak` and the `agn_saturated` flag (NGC 4151
  MuSCAT 2024–25), then `--pytics-full` for every target (new anchors, error model, file format).
- [ ] **E02**: a per-epoch floor. $s_0$ follows the conditions: 1.5 mmag at ≤ 30 s against 0.95 at ≥ 60 s,
  1.1 → 1.7 from airmass 1.2 to 1.7, 1.0 → 1.7 from 1.5″ to 3.5″ seeing, 0.4 mmag night to night. Model it as
  scintillation (Young: D, airmass, exposure) plus a seeing term? Needs `exptime` / `airmass` / seeing per epoch.
- [ ] **E03**: the camera-to-camera term `s_cam` is too small in B and z (cross-camera pairs within 1 h: width
  1.45). Raise it, or fit it per camera family.
- [ ] **E04**: the peak cut for the comparison stars too (`measurements.parquet` needs the peak). The bright-star tail
  is the same as the AGN's.
- [ ] **E05**: fit the floor on star pairs as well (8 M pairs; per camera: fa08 1.5 mmag against 0.9–1.2 elsewhere).
- [ ] **E06**: check MuSCAT `saturate` (118000, from catalogue pile-up) and Spectral (2016 headers) against a current
  e91 header.
- [ ] **E07**: the AGN magnitude system. Publish in the LCO natural AB system, with reference-system fluxes as a
  derived product (emission lines: up to 0.18 mag in r)? See the calibration report.
- [ ] **E08**: per-camera passbands (mirrors; MuSCAT, SBIG, Spectral) and the B/V/i synthetic-vs-empirical colour-term
  mismatch, before relying on B, V, i, u at the 1 % level.
- [ ] **E09**: PS1 DR2 y anchors for 12.5 < G < 14.2 (dec > −30°), so Y has bright anchors.

## Already fixed elsewhere (for reference)

- [x] PyTICS crashes from the first host run: empty pyarrow filter, missing `pytics/` folder, a target without
  photometry (`f1adb46`).
- [x] Stale `meta.colour_check` on Mrk 817, refreshed by a full refit (18 Nov). B05 is the cause and is still open.
