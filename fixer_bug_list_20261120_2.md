# AVA — bug list from the Turgon backfill (pilot ESO 511-30 + weekend run), 20–21 Nov 2026

**Prompt for the pipeline fixer.** You work in the AVA repository (`main`, at `5188bb4` on 20 Nov; pull first) and,
for item 25, in the banzai-floyds checkout (pinned at `0271697`). Follow `CLAUDE.md`: the LCO token is never written
to a file; downloads stay `dry_run` unless the user asks; old pipeline folders are read-only; commit only when the user
asks; record decisions in `docs/notes/future_improvements.md`.

1. Add each item below to `docs/notes/bug_checklist.md` with the next free ID (keep the numbers here as a cross-reference).
2. Fix them in priority order: **High**, then **Medium**, then **Low**. Items 16–17 are design decisions for the
   user: write a proposal, do not implement.
3. Each fix needs a test that runs offline (mock the archive; synthetic SQLite / parquet / FITS).
4. Do **not** change any QC threshold.
5. Turgon is still running the weekend backfill with workarounds and uncommitted hot-fixes (listed at the end), so
   nothing may change the on-disk formats (`frame_qc`, `measurements.parquet`, `reference_stars.csv`, `pytics/`,
   `spec_qc`, the FLOYDS product names) or config keys that already exist; new keys are fine.
6. When a fix lands in `main`, say which Turgon workaround or hot-fix it retires. For the four hot-fixes (items 20,
   24, 25, 26), start from the Turgon code given here, keep its behaviour and add tests; don't rewrite it.
7. Finish with a short report: per item, commit/branch, test name, and what is still open.

Evidence: the Section A checklist doc "AVA Turgon — Section A checklist (20 Nov 2026)" (results log and hourly
table), logs in `/data2/jvhs1/AVA/data/logs/` (`pilot_*.log`, `backfill/backfill.log`, `backfill/summary.tsv`,
`backfill/<T>_{phot,spec}_*.log`), banzai logs in `data/archive/spectroscopy/banzai/logs/`, and the git-ignored
scripts `data/backfill_weekend.sh`, `data/backfill_helpers.py`, `data/publish_staging.sh`,
`data/seed_staging_manifest.py`, `data/ftp_transfer.py` (ask the user for copies if you need them).

---

## High — wrong results, crashes or silently incomplete data

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
- **Workaround:** `backfill_helpers.py refcat|recal T` wrap the tasks in a one-off `@flow`; `refcat` skips the
  rebuild when the catalogue is already full precision and only clears the `.qc0002_pending` marker.

### 18. Exposures with no object in the slit make the whole reduction "incomplete"
- ESO 511-30: 4 of 180 science spectra (2024-03-23, 2025-01-05) where banzai-floyds logs "No object was detected in the
  slit … nothing to extract". `spec_reduce` counts them as missing products and raises `reduction incomplete`, so
  `-P` never runs for the target.
- **Fix:** record them in `spec_qc` with a flag (e.g. `NOOBJECT`), do not count them as incomplete; products run on the
  rest. Only frames banzai-floyds actually reports as "No object was detected" qualify (see items 23, 24).

### 20. PyTICS crashes for targets without FLOYDS spectra (hot-fixed on Turgon, uncommitted)
- `ava/pipeline/tasks/webplot.py::spectroscopy_epochs`: `floyds_end` is NaN for targets never observed with FLOYDS;
  `if end:` is true for NaN and `Time("nan")` raises, which fails the ensemble task after the CSV export but before
  the plots (3C 445, 20 Nov 14:52, exit 51).
- **Hot-fix on Turgon (commit to `main`):** skip empty/NaN/None/NaT values and catch `ValueError`:
  ```python
  if end is not None and str(end).strip().lower() not in ("", "nan", "none", "nat"):
      try:
          last = float(Time(str(end)[:10]).mjd)
      except ValueError:
          last = None
  ```
  Add a test with `floyds_end = NaN`. 3C 445 re-run with the hot-fix 20 Nov 15:00 (exit 0, on staging).

### 23. 2014–2016 FLOYDS data give no products at all
- **Evidence:** Mrk 352, all FLOYDS data from Aug 2014 (21 nights, `ogg2m001-en06`): 84 files downloaded (21 science,
  21 arc, 21 flat, 7 standard + 14 standard calibrations); `-R`: `chain exit 0; 0 frames ok, 0 failed; 0
  science/standard products`. The chain's first line in `data/archive/spectroscopy/banzai/logs/Mrk_352.log` is
  `{'arcs': 0, 'flats': 0, 'standards': 0, 'science': 0}`. Same on NPM1G+27.0587, Arp 151, RXJ2044.0+2833 and the
  other targets whose FLOYDS data are from 2014–2016. Data from 2018 on reduce (e.g. RXJ1755.0+6519, 2025 night →
  2 spectra, Hβ fits, PrepSpec, 21 Nov 05:30).
- **Fix:** find why these frames are not ingested (compare a 2014–2016 raw header with a 2020+ one: `OBSTYPE`,
  `CONFMODE`, `INSTRUME`, `OBJECT`/`SITEID`, file-name pattern, compression) and make the chain take them — or, if
  they genuinely can't be reduced, list them as unsupported in `spec_qc` and say so in the summary.
- **Weekend effect:** before 21 Nov 00:42, Mrk 352, NPM1G+27.0587 and Arp 151 were marked Archived with no spectra;
  since then such runs end with spec exit 31 (item 24). Raw spectra stay on disk.

### 24. `spec_reduce` outcome rules: partial products, zero-frame runs (hot-fixed on Turgon, uncommitted)
- **Problem:** (a) one failed night stopped products for the whole target ("reduction incomplete"), although the user
  wants products made from whatever reduced, with the failures flagged for reprocessing; (b) a run where banzai
  processed **no** frame looked like a clean exit (exit 0, 0 failed), so it was accepted.
- **Hot-fix on Turgon** (`ava/pipeline/tasks/spec_reduce.py`, v3 21 Nov 00:42; original kept as
  `.bak_20261120_1910`):
  - incomplete reduction with ≥ 1 **science** product (standards don't count) → warning
    `PARTIAL: continuing with N science products`, `out["partial"]=True`, products go on, and the target and missing
    nights are appended to `<spec_dir>/REPROCESS_NEEDED.txt`;
  - no science product but some frames ok → raises (`…; no science product`);
  - no frame processed at all → raises `reduction processed no frames (chain exit …)`.
- **Fix:** commit with tests for the three outcomes; put the missing nights in `spec_qc` too (not only the text file);
  make `-P` and the status tools read the partial state. **Check with the user** before merging: this changes the
  daily run's behaviour as well.

### 25. AVA's clean-up strips `BINNED2D` from standards and breaks every later banzai-floyds run (banzai side hot-fixed)
- **Evidence:** 20 Nov 15:49, after J1421+3855's complete reduction, `spec_reduce`'s clean-up (`drop_binned`)
  removed the `BINNED2D` extension from its two 2020-07-08 standards' `-2d-notpl` files, with no `TRACE` table added.
  Every later run rebuilds the residual fringe templates from **all** processed standards
  (`banzai_floyds/fringe_masters.py::make_residual_templates`), hit those files with `KeyError: 'BINNED2D'` and
  stopped before extracting any science (15:49–21:55: Mrk 376, Mrk 662, Mrk 926, J0132-0027, SBS 1518+593, NGC 5273,
  Mrk 684, Mrk 1392, Mrk 9, IRAS 09149-6206, RBS 1303).
- **Hot-fix on Turgon** (banzai-floyds, backup `.bak_20261120_2205`; confirmed on NPM1G+27.0587 22:24):
  ```python
  frames = []
  for one_d, two_d in ([] if strip else groups[name]):
      try:
          frames.append(_standard_frame(one_d, two_d)[:3])
      except KeyError as error:
          print(f'residual templates: {os.path.basename(one_d)} skipped ({error})', flush=True)
  ```
- **Fix:** (a) AVA: the clean-up must not slim standards (or must write a `TRACE` table like banzai's own slimming) —
  each complete run otherwise removes more standards from the templates; (b) banzai-floyds: commit the hot-fix on a
  branch with a test, re-pin AVA (Turgon and VM); (c) a tool or recipe to restore slimmed standards (re-reduce the
  night).

### 26. Photometry fails when a target has no reference catalogue
- **Evidence:** J21368-6438 (21 Nov 05:12) had no `reference_stars.csv`; `-e -c` failed. The run only builds a
  catalogue with `-o`, and nothing tells you it is missing until calibration fails.
- **Fix:** `calibrate` (or `-c`) builds the catalogue when it is missing (logged), or fails up front with a clear
  "no reference catalogue — run -o" message; `backfill_status` lists targets without one. Test both paths.
- **Workaround:** `backfill_helpers.py rounded` (v5, 21 Nov 05:50) returns True for a missing catalogue, so the loop
  builds it (confirmed on SDSS J2353, 06:07).

### 27. Plot step crashes when no frame passes QC
- **Evidence:** PG_2304+043, 21 Nov 05:12–05:24, phot exit 51: 0 frames pass QC, then the light-curve plot crashes on
  NaN axis limits (log: `data/logs/backfill/PG_2304+043_phot_20261121_0512.log`).
- **Fix:** with an empty or all-NaN light curve, skip the plot with a warning (or draw an empty "no frames pass QC"
  panel) and let the run finish; report the count. Test with an all-NaN band. (Why nothing passes QC is for the user
  to review — don't touch thresholds.)

---

## Medium — the backfill needs hand-set overrides or hand-written scripts

### 5. No backfill mode
- **Evidence:** a full-dataset run of one target needed, by hand: `spectroscopy.download.select: oldest`,
  `spectroscopy.download.max_frames_per_run` 100 → 5000, `photometry.sextractor.max_frames_per_run` 2000 → 100000,
  plus items 1–2. The daily-run defaults are right for the nightly job; they silently truncate a backfill.
- **Fix:** a `--backfill` flag on `run_pipeline.py` (and `download.py`) or a `backfill:` config block that applies these
  together for that run only, logged at start. Document in the deployment guide.

### 6. `make_config.py init --force` must be given every override again
- **Evidence:** six `init` runs on Turgon, each repeating all previous `--set` values.
- **Fix:** `make_config.py set key=value [...]` / `unset key` that edit the existing override files (backup first),
  then run `check`.

### 7. Web export ignores `web.data_dir`
- **Where:** `tools/export_web_bundle.sh` hard-codes `$REPO/web/data`; `make_config.py init` (production layout)
  sets `web.data_dir: data/web`. On such a machine `-w` publishes to `data/web/` and the export finds nothing.
- **Fix:** read `web.data_dir` from the merged config and mirror that into `OUT/data/`. Test with a temp repo.
- **Workaround:** Turgon override `web.data_dir=web/data`.

### 8. Upload tool: no subset upload, credentials only under `$HOME`
- **Where:** `tools/upload_web_bundle.py`.
- **Evidence:** (a) staging already had the site files; Turgon (no manifest) would resend all 158 — only the database
  and science outputs were wanted. (b) Settings and `.netrc` are read only from `$HOME`; Turgon's home is a CIFS mount
  where `chmod` has no effect (Python refuses a world-readable `.netrc`).
- **Fix:** `--only PREFIX` (repeatable), `--settings PATH` / `--netrc PATH` (or env `AVA_WEB_UPLOAD_SETTINGS`,
  `NETRC`), optional `--mark-sent PREFIX` to seed the manifest. Tests with a fake FTP.
- **Workaround:** `HOME=/data2/jvhs1/.secrets/ftp_home` and `data/seed_staging_manifest.py`.

### 9. `tools/relocate_paths.py` (needed Monday for the VM transfer)
- Rewrite absolute paths in `local_files.path` (both lcodb DBs) and `spec_qc.path_1d/path_2d`
  (`/data2/jvhs1/AVA` → `/data/ava/AVA`), `--dry-run` default, report rows changed and files missing after the
  rewrite. (Backfill checklist C4, decision D3.)

### 10. lcodb template has a machine-specific path
- `config/lcodb_config.yaml`: `standards.reference_dir: '~/astro/floyds/banzai-floyds/banzai_floyds/data/standards'`.
  Derive it from the banzai-floyds checkout (`paths.floyds_pipeline`) like the sky flats, or make it relative.

### 21. Clean-up cannot run during a backfill
- `scripts/cleanup.py --retention-days 0` is refused: "retention_days (0) must be longer than the download look-back
  (overlap_days 2)". A backfill download already skips frames that have a catalogue.
- **Fix:** let the clean-up delete photometry images whose catalogue and `frame_qc` row exist regardless of age when
  the daily download is configured to skip catalogued frames (or add `--backfill`).

### 28. No daily archive-request budget or HTTP 429 handling
- **Evidence:** an earlier full run made ~42,000 archive requests in a day and was blocked with HTTP 429; the weekend
  run has to count requests itself (3,499 over 20–21 Nov so far, budget 8,000/day).
- **Fix:** count archive requests per UTC day in one place (e.g. `state.sqlite`), a config key for the daily budget,
  stop cleanly (resumable) when it is reached, and on HTTP 429 honour `Retry-After` / stop for the day instead of
  retrying. Tests with a mocked archive.
- **Workaround:** `backfill_helpers.py requests` counts "N archive request(s)" log lines, reads
  `data/backfill_budget.txt`, and treats any HTTP 429 of the day as "budget full" (loop sleeps to 00:05 UTC).

### 29. A supported backfill runner (replaces `data/backfill_weekend.sh`)
- The weekend run depends on a git-ignored bash loop plus `backfill_helpers.py`. Needed in the repo (could share the
  item 5 flag): per-step wall-clock `timeout`; the target list re-read between targets so targets can be reordered or
  inserted without a restart (PG 0923+201 could not be moved up on 20 Nov); per-target summary (phot/spec exit,
  times); acceptance rules from item 24 (Archived only with ≥ 1 science product, never on a zero-frame run); and a
  prebuild log that does not print an old "Error" line when the catalogue was written (13 false "failures" on 20 Nov).

---

## Low — reporting and usability

### 11. `backfill_status.py` FLOYDS table counts science frames only
- ESO 511-30 showed `to_download 0` while 263 standard/arc/flat files were missing. Add standards and calibrations
  (from `std_match` / `calib_match`).

### 12. `backfill_status.py` photometry counts all filters
- 9,339 frames vs 9,151 in the pipeline's filters; count per `photometry.filters` (and show the rest separately).

### 13. No progress output during spectra reduction
- 12 min after the start of `-R`, `reduced/` was empty and the log silent. Log one line per finished night (n of N).

### 14. `local_files` misses ported files
- The 175 raw spectra ported from the old pipeline are on disk but not in `local_files`. Either register ported files
  (port tool) or document that `local_files` covers AVA downloads only.

### 15. "To be processed" stays after a full backfill
- `agn.ava = 0` until `tools/set_archived.py T --write` by hand. Decide whether the backfill should set Archived itself
  (with item 24's rules).

### 19. Host page cache serves stale target pages on the staging site
- alymantara.com/ava2 kept serving ESO 511-30's page from before the spectra upload. **Fix:** send
  `Cache-Control: no-cache` (or a short max-age) from the PHP pages.

### 30. FLOYDS nights listed for a target with no FLOYDS folder
- MCG+04-22-042: the status table lists 2 FLOYDS nights but there is no `data/archive/spectroscopy/MCG+04-22-042/`
  on Turgon and the spec track did nothing. Find whether the nights belong to another name (`target_link`) or the
  download skipped them; make status and download agree.

---

## For next week (design decision with the user, not now)

### 16. QC gate before PyTICS drops usable frames
- `ava/photometry/store.py::load_pytics` keeps only `qc_pass = 1`. ESO 511-30 lost 32.8 % of frames: `agn_flagged`
  r 514 / i 297 / g 129, `zp_scatter` z 663 / i 173, `zp_offset` u 350, `seeing` ~20/band, `no_zp` u 60. The
  zero-point flags test the reference zero point, which PyTICS does not use. Proposal to discuss: gate PyTICS on
  measurement flags only. (Juan has PyTICS changes on his laptop; pull them into `main` first.)

### 17. Distant standards
- ESO 511-30: 12 of 180 science spectra matched to a standard more than 3 days away (max 714 h). Flag them in
  `spec_qc` and check whether they stand out after the [O III] calibration.

---

## Notes (not code)
- **Gaia ESA Archive** down from 25 Nov 12:00 CET (DR4 on 2 Dec): `gaia_utils` falls back CDS → CfA → ESA; decide the
  production `vizier_servers` order with the user. After DR4: `star_id` is the DR3 `source_id`; keep querying DR3
  tables until a decision.
- DR1 release files missing on Turgon: `releases/DR1/Mrk_817/photometry/Mrk_817_LCO_merged_lightcurve.csv`,
  `…/Mrk_817/spectroscopy/Mrk_817_FLOYDS_Hbeta_lightcurve.csv`, `…/NGC_4151/spectroscopy/NGC_4151_FLOYDS_Hbeta_lightcurve.csv`.
- VM access: `ava` cannot log in over SSH; `jvhs1` needs a password for `sudo -u ava`; Turgon accepts no SSH.
  Transfers to the VM go by hand; a permanent route needs IT.

## Uncommitted changes on Turgon (each with a backup next to it)
| File | Item | Backup |
|---|---|---|
| `ava/pipeline/tasks/webplot.py` | 20 | — |
| `ava/pipeline/tasks/spec_reduce.py` (v3) | 24 | `.bak_20261120_1910` |
| banzai-floyds `banzai_floyds/fringe_masters.py` | 25 | `.bak_20261120_2205` |
| `data/backfill_helpers.py` (git-ignored) | 4, 26, 28 | `.bak_20261120_1758`, `_1925`, `_2020`, `.bak_20261121_0550` |
| `data/backfill_budget.txt` (= 8000; delete after the backfill) | 28 | — |
