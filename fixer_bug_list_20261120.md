# AVA — bug list from the Turgon backfill pilot (ESO 511-30), Fri 20 Nov 2026

**Prompt for the pipeline fixer.** You work in the AVA repository (`main`, currently `5188bb4`), following
`CLAUDE.md` (the LCO token is never written to a file; downloads stay `dry_run` unless the user asks; old pipeline
folders are read-only; commit only when the user asks; record decisions in `docs/notes/future_improvements.md`).
Add each item below to `docs/notes/bug_checklist.md` with the next free ID, then fix them in the priority order given,
each with a test (offline: mock the archive, synthetic SQLite / parquet). Do **not** change any QC threshold.
Turgon is running the weekend backfill with workarounds for items 1–6, so nothing here may change the on-disk formats
(`frame_qc`, `measurements.parquet`, `reference_stars.csv`, `pytics/`) or config keys that already exist; new keys are
fine. When a fix is in `main`, say which workaround it retires.

Evidence: Turgon log of 20 Nov (Section A checklist doc "AVA Turgon — Section A checklist (20 Nov 2026)", results
log), files in `/data2/jvhs1/AVA/data/logs/` (`pilot_*.log`), and the scripts `data/backfill_weekend.sh`,
`data/backfill_helpers.py`, `data/publish_staging.sh`, `data/seed_staging_manifest.py`, `data/ftp_transfer.py`
(git-ignored; ask the user for copies if you need them).

---

## High — wrong results or silently incomplete data

### 1. Archive search reads only the first page of each window (photometry and spectra downloads)
- **Where:** `ava/lco/download.py::pages()` follows the archive's `next` link.
- **Evidence:** ESO 511-30, 365-day windows: `found 4331` with exactly the minimum 34 listing requests; with
  `--window-days 90`: `found 9151`, matching `backfill_status` (9,339 incl. non-pipeline filters). The archive's
  `next`/`count` are estimates for some filters — already documented in `ava/lcodb/api.py::frames()`, which pages by
  `offset` with `ordering='id'` until a short page.
- **Fix:** page the same way as `lcodb.api.frames()` (offset + `ordering='id'`, stop on a short page). Keep the
  request count in `stats`. Test: a mocked archive returning 2,500 frames in one window with `next=None` must yield
  all 2,500.
- **Workaround on Turgon:** `--window-days` chosen per target so every window holds < 800 frames
  (`backfill_helpers.py window`).

### 2. Filler proposals are never searched
- **Where:** `lco.proposals` (config) is the only proposal list for `download.py` / `make_query`.
- **Evidence:** ESO 511-30 has 300 frames under `KEY2023B-001f`, which is not in the list.
- **Fix:** default the proposal list to the proposals lcodb holds for the target's LCO names (`frames.proposal_id`
  via `target_link`), unioned with `lco.proposals`; `--proposal` still overrides. Test with a synthetic lcodb.
- **Workaround:** `backfill_helpers.py proposals T` passed as `--proposal …`.

### 3. A capped spectra download reports success, and reduction then runs with missing standards
- **Where:** `ava/pipeline/tasks/spec_download.py` (`max_frames_per_run`), then `spec_reduce`.
- **Evidence:** run 1: `616 planned, 353 on disk, 263 missing; 100 downloaded … — capped`, exit 0; the chained `-R`
  started and warned `63 chosen standard frame(s) not on disk`. The summary's "missing" is the count **before** the
  download, so "0 missing" never appears in the run that completes the set.
- **Fix:** (a) report `missing after this run` in the summary line; (b) return a non-zero status / failed state from
  the flow when the run is capped or files remain missing; (c) `spec_reduce` refuses (or explicitly skips and lists)
  nights whose chosen standard or calibrations are not on disk, instead of reducing them. Tests for each.
- **Workaround:** the weekend script repeats `-D` until a run reports `0 missing`.

### 4. QC-0002 recipe does not work as documented; no CLI to force a catalogue rebuild or a recalibration
- **Where:** `ava/pipeline/tasks/reference.py::reference_catalog`, `calibrate.py::calibrate` call `get_run_logger()`,
  so `reference_catalog.fn(T, force=True)` (the recipe in `future_improvements.md`, QC-0002 follow-up, and the
  backfill checklist D1) raises `MissingContextError` outside a flow. `run_pipeline.py` never passes `force`.
- **Fix:** add `--force-refcat` and `--force-calibrate` (or one `--qc0002`) to `run_pipeline.py`, passed through
  `ava_target_flow`; correct the docs. Test that the flags reach the tasks.
- **Workaround:** `backfill_helpers.py refcat|recal T` wrap the tasks in a one-off `@flow`.

---

## Medium — the backfill needs hand-set overrides

### 5. No backfill mode
- **Evidence:** a full-dataset run of one target needed, by hand: `spectroscopy.download.select: oldest`,
  `spectroscopy.download.max_frames_per_run` 100 → 5000, `photometry.sextractor.max_frames_per_run` 2000 → 100000,
  plus items 1–2. The daily-run defaults are right for the nightly job; they silently truncate a backfill.
- **Fix:** a `--backfill` flag on `run_pipeline.py` (and `download.py`) or a `backfill:` config block that applies these
  together for that run only, logged at start. Document in the deployment guide.

### 6. `make_config.py init --force` must be given every override again
- **Evidence:** six `init` runs on Turgon today, each repeating all previous `--set` values.
- **Fix:** `make_config.py set key=value [...]` / `unset key` that edit the existing override files (backup first),
  then run `check`.

### 7. Web export ignores `web.data_dir`
- **Where:** `tools/export_web_bundle.sh` hard-codes `$REPO/web/data`; `make_config.py init` (production layout)
  sets `web.data_dir: data/web`. On such a machine `-w` publishes to `data/web/` and the export finds nothing
  (fails on the `ava.db` check, or ships a stale copy).
- **Fix:** read `web.data_dir` (via the merged config, e.g. `python -c` with `ava.config`) and mirror that into
  `OUT/data/`. Test with a temp repo.
- **Workaround:** Turgon override `web.data_dir=web/data`.

### 8. Upload tool: no subset upload, credentials only under `$HOME`
- **Where:** `tools/upload_web_bundle.py`.
- **Evidence:** (a) the staging site already had the site files from the Mac; Turgon (no manifest) would resend all
  158 — the user wanted only the database and science outputs. (b) Settings and `.netrc` are read only from `$HOME`;
  Turgon's home is a CIFS mount where `chmod` has no effect (Python refuses a world-readable `.netrc`).
- **Fix:** `--only PREFIX` (repeatable, e.g. `data/`), and `--settings PATH` / `--netrc PATH` (or env
  `AVA_WEB_UPLOAD_SETTINGS`, `NETRC`). Optional `--mark-sent PREFIX` to seed the manifest. Tests with a fake FTP.
- **Workaround:** `HOME=/data2/jvhs1/.secrets/ftp_home` and `data/seed_staging_manifest.py`.

### 9. `tools/relocate_paths.py` (needed Monday for the VM transfer)
- Rewrite absolute paths in `local_files.path` (both lcodb DBs) and `spec_qc.path_1d/path_2d`
  (`/data2/jvhs1/AVA` → `/data/ava/AVA`), `--dry-run` default, report rows changed and files missing after the
  rewrite. (Backfill checklist C4, decision D3.)

### 10. lcodb template has a machine-specific path
- `config/lcodb_config.yaml`: `standards.reference_dir: '~/astro/floyds/banzai-floyds/banzai_floyds/data/standards'`.
  Derive it from the banzai-floyds checkout (`paths.floyds_pipeline`) like the sky flats, or make it relative.

---

## Low — reporting and usability

### 11. `backfill_status.py` FLOYDS table counts science frames only
- ESO 511-30 showed `to_download 0` while 263 standard/arc/flat files were missing. Add standards and calibrations
  (from `std_match` / `calib_match`) to the table.

### 12. `backfill_status.py` photometry counts all filters
- 9,339 frames vs 9,151 in the pipeline's filters; count per `photometry.filters` (and show the rest separately).

### 13. No progress output during spectra reduction
- 12 min after the start of `-R`, `reduced/` was empty and the log silent (banzai-floyds writes to
  `spectroscopy/banzai/processed/` first). Log one line per finished night (n of N).

### 14. `local_files` misses ported files
- The 175 raw spectra ported from the old pipeline are on disk but not in `local_files`, so queries joining it report
  0 standards on disk. Either register ported files (port tool) or document that `local_files` covers AVA downloads only.

### 15. "To be processed" stays after a full backfill
- `agn.ava = 0` until `tools/set_archived.py T --write` by hand. Decide whether the backfill (all frames calibrated,
  all nights reduced) should set Archived itself. (Turgon's weekend script does it per target.)

---

## For next week (design decision with the user, not now)

### 16. QC gate before PyTICS drops usable frames
- `ava/photometry/store.py::load_pytics` keeps only `qc_pass = 1`. ESO 511-30 lost 32.8 % of frames: `agn_flagged`
  r 514 / i 297 / g 129 (nucleus > 80 % of saturation), `zp_scatter` z 663 / i 173, `zp_offset` u 350, `seeing`
  ~20/band, `no_zp` u 60. The per-frame zero-point flags (`zp_scatter`, `zp_offset`, `no_zp`) test the reference
  zero point, which PyTICS does not use (it solves epoch zero points from the ensemble); `agn_flagged` and `seeing`
  test the measurement. Proposal to discuss: gate PyTICS on measurement flags only, keep the zero-point flags for
  the per-frame absolute light curve. Frames stay in `measurements.parquet` / `frame_qc`, so a PyTICS re-run recovers
  them.

### 17. Distant standards
- ESO 511-30: 12 of 180 science spectra matched to a standard more than 3 days away (max 714 h). Flag them in
  `spec_qc` and check whether they stand out after the [O III] calibration.

---

## Not code (for the record)
- DR1 release files missing on Turgon: `releases/DR1/Mrk_817/photometry/Mrk_817_LCO_merged_lightcurve.csv`,
  `…/Mrk_817/spectroscopy/Mrk_817_FLOYDS_Hbeta_lightcurve.csv`, `…/NGC_4151/spectroscopy/NGC_4151_FLOYDS_Hbeta_lightcurve.csv`.
- VM access: `ava` cannot log in over SSH (sshd allows groups `systems`, `lobbysshjump` only); `jvhs1` has no home on
  the VM and needs a password for `sudo -u ava`; Turgon accepts no SSH. Transfers to the VM go on Monday by hand;
  a permanent route needs IT.
