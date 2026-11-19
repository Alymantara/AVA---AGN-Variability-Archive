# Linux test day: checklist

Tick a step by changing `[ ]` to `[x]`, and add a short note under it (what it printed, what was decided).
Procedure: `docs/guides/linux_setup.md`. Decisions and context: `docs/notes/linux_test_day_handover.md`.
Steps tagged **LCO** contact the archive: run them only while the old pipeline is not downloading.

## Decisions for today

- Isolated test: AVA writes only under `/data2/jvhs1/AVA` (code) and `/data2/jvhs1/AVA/data` (data, git-ignored);
  `/data3/jvhs1/agn` and `/data2/jvhs1/agn` are only read (copied, never moved).
- Real copies of the old catalogues (no `--link`; several TB free).
- Leave the old Anaconda alone: AVA lives in Miniforge (`/data2/jvhs1/miniforge3`, local disk), activated with `ava-env`.
- Clean-up stays a dry run; downloaded images are kept for now.
- Re-run `port_legacy.py --write` before each download batch, so nothing the old pipeline extracted is downloaded.
- No cron jobs today.
- Everything in one folder (decided 18 Nov): wherever the guide says `~/code/AVA`, use `/data2/jvhs1/AVA`;
  wherever it says `/data3/jvhs1/ava`, use `/data2/jvhs1/AVA/data`.

## Where we are (updated 15:26) — overnight run

**Done:** install 1–9, banzai-floyds (9b), archive update (10), port 12a–c, step 13, step 11 folders (91).
**Overnight script** `data/overnight_20261118.sh` (log `data/logs/overnight_20261118.log`, stage logs and
`STATUS.txt` in `data/logs/overnight/`), started by the user ~15:30:
1. moves aside every reference catalogue whose metadata names VizieR (CfA mirror) and rebuilds it from ESA (`-o`);
2. re-ports new old-pipeline catalogues;
3. **no downloads** (user, 15:24: not yet). Planned for next time: Mrk_817 (376), fairall_9 (1,048), NGC_4151
   (first 1,000).
   **SExtractor tested on a real frame first (15:27, user's request):** `scripts/download.py --target Mrk_817 --live
   --max-frames 1` (14 archive requests, 9.3 MB: `ogg2m001-fs02-20200620-0049-e91`, Spectral 2 m), then
   `run_pipeline.py -e --target Mrk_817`: extracted 1, failed 0; catalogue 356 sources, **16 apertures**, `APERDIAM`
   3…48. Only a harmless astropy "Card is too long, comment will be truncated" warning (the `APERDIAM` comment).
4. `-c -t -p` for **all targets** (calibration, PyTICS, plots);
5. collects plots, `agn_lightcurve_pytics.csv` and `pytics/intercal.csv` into `data/review/2026-11-18/` + `SUMMARY.txt`;
6. `backfill_status` again.
The CALI merge (`-m`) is not ported yet: the PyTICS light curve is the "merged" one.
Started 15:29. **Flat copy (user, 15:33):** `data/copy_to_temp_plots_20261118.sh` waits for the run, then copies every
plot (`*.png`), light curve / intercal table (`*.csv`) and `SUMMARY.txt` into `/data2/jvhs1/AVA/temp_plots/` (no
subfolders; added to `.git/info/exclude`). The copy to `/data3/jvhs1/agn/ava_lcs` was dropped (old folders stay read-only).
**Run log:** 15:45 restarted (v3, no waiting); reference catalogues **91, all from ESA** (NGC_7469 has 34 GSPC stars on
ESA too: a sparse field, not a CfA gap); port OK; stage 08 (`-c -t -p`, 4 targets at once) started 15:49 and **stalled
at 15:52** after fairall_9's first 2,000 frames: a pool worker `BrokenPipeError` + "leaked semaphores", no log or
`measurements.parquet` change afterwards. Suspects: memory (4 targets x 4 spawn workers) or SQLite contention on the
shared lcodb `frame_qc`. Host config `pipeline.n_cores: 4 -> 1`; restart needed (user, from a terminal).
**16:15 status:** stage 08 is alive despite the 15:52 worker error (its log has been silent since): new
`measurements.parquet` batches for fairall_9 (16:10) and Mrk_817 (16:04); **PG_0844+349 calibrated at 15:59**
(3,682 frames, `agn_lightcurve.csv`; plotted for the user: coherent variability in all 7 filters) but no `pytics/`
output yet at 16:15 (expected ~1 min after calibration). MCG_08-11-011: no calibration output yet. If PG_0844+349
has no PyTICS output by ~17:15, re-run `-t -p` for it (and any stuck target) with `n_cores: 1` (host config already 1).
File names: light curves are collected as `<target>_agn_lightcurve_pytics.csv`, plots carry the target
(`lco_latest_<target>…`), so nothing collides; the upload replaces same-name files in `v2_plots` (user: fine).
**17:00 status (last check today):** **PyTICS never produced output** for the two targets that finished calibrating —
PG_0844+349 (calibrated 15:59) and MCG_08-11-011 (calibrated 16:16; 7,086 frames, crowded field: 2,462 reference
stars, 166 MB `measurements.parquet`, 30–44 % of r/i/z frames QC-rejected — check the QC thresholds there). Their
slots stay occupied, so no new target has started; fairall_9 (~22,000 of 51,878 by 16:55) and Mrk_817 (~9,000 of
22,312 by 16:46) still calibrate and will most likely stall at PyTICS too. Overall ~8 % of the 463k catalogues.
**Tomorrow:** stop the run (`pkill -f overnight_20261118.sh; pkill -9 -f scripts/run_pipeline.py`), run PyTICS in the
foreground on one target to see where it hangs (`python -u scripts/run_pipeline.py -t -p --target PG_0844+349`), fix,
then `-c -t -p` for all with `n_cores: 1`. Calibrated frames are kept (skipped on re-run). Copy/upload never ran.
Quick-look plots of PG_0844+349 and MCG_08-11-011 (per-frame calibration) shown to the user; the pipeline's own web
plots keep their format (user: house style is for display images only).
**18:20 correction — PyTICS does not hang, it fails:** the stage-08 log was only buffered. Every target's
PyTICS fits converge (seconds per filter), then `load_pytics` asks for a filter with no passing frame (Y for most
targets), pyarrow rejects the empty `in` filter (`ArrowTypeError: … large_string vs null`), and the target's flow
fails; the run moves on, so **calibration continues for all targets** tonight. **Fixed** (`ava/photometry/store.py`:
empty table when a filter has no frames; test `test_load_pytics_filter_without_frames`, fails before / passes after;
written to the host 18:25, not yet committed). By 18:17: 9 targets calibrated (PG_0844+349, MCG_08-11-011, Mrk_279,
MR_2251-178, 1Zw1, Mrk_817, Mrk_142, Mrk_876, NGC_5548), fairall_9 ~85 %, Mrk_509 / Mrk_110 / NGC_4593 started.
**MR_2251-178: only 435 of 9,108 frames pass QC** — look at its flags. **Tomorrow:** once stage 08 ends, run
`python -u scripts/run_pipeline.py -t -p` (PyTICS + plots for all; minutes), then collect / copy / upload.
**19:15 — second PyTICS bug, fixed; per-target QC review.** Mrk_817 and fairall_9 (which have Y frames) got past
the first bug and failed writing `pytics/absolute_zp_stars.parquet` before `pytics/` existed (`OSError`). Fixed in
`ava/photometry/ensemble.py` (mkdir). New end-to-end test `test_run_target_end_to_end_first_full_fit` (fresh folder, a
filter without frames): fails with each old file (OSError / ArrowTypeError), passes with both fixes; full suite here
164 passed (2 need Prefect, not installed in Claude's workspace). Written to the host 19:20, not yet committed.
Progress 19:10: 14 targets calibrated (170,442 frames) + Mrk_509, NGC_4151, PG_1119+120, 3C273 in progress
(≈ 200k of 463k, ≈ 43 %). QC pass rates mostly 65–80 %. **To look at:**
- **MR_2251-178:** AGN measured in only 1,335 of 9,108 frames (15 %): `agn_missing` (Gaia match of the AGN at
  1.29", limit 1.5"). 13 frames to inspect sent to the user (`MR_2251-178_frames_to_inspect.csv`).
- **Mrk_110:** 19 % pass; 3,771 of 5,753 frames `agn_flagged` (SExtractor flags on the AGN: saturation or blending?).
- **z band** passes poorly in some fields (3C120 36 %, Mrk_110 11 %); u band ~45–60 % (few GSPC u stars).
- **3C120** has Bessell `U` frames among the ported catalogues (U is not in `photometry.filters`); harmless for PyTICS
  (filters list), but the port could skip filters outside the list.
- **NGC_4593:** AGN measured in 86 % of frames (others 96–98 %).
- **PG_2304+043: 0 % pass** — 996 of 998 frames `few_matched`: the field has only 57 GSPC stars (high latitude), so
  `qc.min_matched: 30` can never be met. **Mrk_1298:** 35 % pass (95 GSPC stars; 118 `few_matched`). The threshold
  should scale with the field (e.g. a fraction of the reference stars in the footprint) or be set per target.
- 19:58: 22 targets calibrated (224,220 frames) + 3C273, Mrk_335, Mrk_1044, NGC_4395 in progress (≈ 51 %).
  PyTICS fixes not yet committed (user will commit).
- 20:17: 28 targets calibrated (246,383 frames) + Mrk_335, NGC_4395, Mrk_590, NGC_7469 in progress (≈ 56 %).
  **Third PyTICS issue, fixed:** targets with no catalogues (Mrk_1220; 28 targets have none) failed in PyTICS with
  `FileNotFoundError: measurements.parquet`; `ava/pipeline/tasks/ensemble.py` now skips them like webplot does
  (test `test_ensemble_skips_target_without_photometry`, fails before / passes after; suite here 167 passed).
  Also lower than usual: NGC_2617 (64 % pass, AGN 84 %), J1421+3855 (AGN 79 %), PKS_2004 (AGN 75 %).
  **Commit for the PyTICS fixes now covers 5 files:** `ava/photometry/store.py`, `ava/photometry/ensemble.py`,
  `ava/pipeline/tasks/ensemble.py`, `tests/test_ensemble.py`, `tests/test_webplots.py`.
**Night result (read 22:45):** stage 08 was **killed at 21:06:51, exit 137 (SIGKILL; most likely the OOM killer:
4 large targets x 4 workers)**; the log was flushed late, so a 21:30 status read it as still running (wrong).
The script then collected nothing (no PyTICS output), ran backfill_status and the upload found nothing to send.
`backfill_status_after_overnight`: 462,673 catalogues, **309,961 calibrated (67 %)**, 152,712 to calibrate,
40,685 frames (1.5 TB) to download. **Error (Claude):** the deployed script still had the step copying
`data/review/2026-11-18` to `/data3/jvhs1/agn/ava_lcs/new_pipeline_2026-11-18` (dropped by the user at 15:33; an older
version of the file reached the host at 15:43 and was not re-checked). It created that new subfolder with
`SUMMARY.txt` and two empty folders; nothing of the old pipeline was overwritten. Remove:
`rm -r /data3/jvhs1/agn/ava_lcs/new_pipeline_2026-11-18`. Lesson: re-read the deployed copy of every script.
**Next:** check memory (`journalctl -k`, `free -h`); `-c` for the rest with `n_cores: 1`; then `-t -p`; collect; upload.
**Upload (user, 15:35):** `data/upload_temp_plots_20261118.sh` waits for the copy, then FTPs `temp_plots/*.png` to
`www.alymantara.com:/public_html/ava/v2_plots` (`expect`; password read from `/data2/jvhs1/.secrets/ftp_alymantara`,
chmod 600, never in a script). One-file test `data/upload_test_20261118.sh` passed 15:39. **To do:** change the FTP
password (it was pasted in chat) and prefer FTPS/SFTP if the host offers it.

**Next session:** read `STATUS.txt` / `SUMMARY.txt`; check the SExtractor result (stage 04); look at the plots;
compare Mrk 817 with the old pipeline; then more downloads (NGC_4151 has ~6,400 left), spectra (`-D`, `-R`),
website (PHP), token, the 3 flagged link names.

## 1 · Install (guide steps 1–9)

- [x] **1. Check SExtractor**
  - 2.25.0. `command -v source-extractor sex` -> `/usr/local/bin/sex` (set as `binary:` in step 6, full path for cron).
- [x] **2. Check conda**
  - `conda 23.1.0` → plan B (Miniforge beside it, no `conda init`).
- [x] **2b. Install Miniforge** in `/data2/jvhs1/miniforge3` (not in home: it is a network share)
  - Done 18 Nov: `conda 26.9.4`. First try in `~` (CIFS share `//cfs.st-andrews.ac.uk/users/jvhs1`) was very slow and
    hit case-clash warnings, so it was deleted and reinstalled on the local disk. Installer warned that `PYTHONPATH` is set.
  ```bash
  cd /data2/jvhs1 && curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
  bash Miniforge3-Linux-x86_64.sh -b -p /data2/jvhs1/miniforge3
  /data2/jvhs1/miniforge3/bin/conda --version
  ```
- [x] **3. Clone the code** into `/data2/jvhs1/AVA` (folder already holds `CLAUDE.md` and the hand-over, so clone in place)
  - Done 18 Nov: `main` tracks `origin/main`, cloned in place.
  ```bash
  cd /data2/jvhs1/AVA && mv CLAUDE.md ~/CLAUDE.md.bak
  git init -b main && git remote add origin https://github.com/Alymantara/AVA---AGN-Variability-Archive.git
  git fetch origin && git checkout -t origin/main
  git status --short
  ```
- [x] **4. Create the data folders**
  - Done 18 Nov: `/data2/jvhs1/AVA/data/{archive,lcodb,config,logs,web,releases}`; `/data2` has 2.7 TB free (of 11 TB).
  ```bash
  df -h /data2
  mkdir -p /data2/jvhs1/AVA/data/{archive,lcodb,config,logs,web,releases}
  ```
- [x] **5. Python environment (plan B)**
  - Done 18 Nov 13:33: `ava` env in `/data2/jvhs1/miniforge3/envs/ava`, `ava-0.1.0` installed (`pip install -e .`), Prefect 3.9.3.
  ```bash
  cd /data2/jvhs1/AVA && /data2/jvhs1/miniforge3/bin/conda env create -f environment.yml
  ava-env && pip install -e .
  python -c "import ava, prefect; print(prefect.__version__)"
  ```
- [x] **6. Config files, `AVA_CONFIG` / `LCODB_CONFIG`, `ava-env` alias**
  - 18 Nov: Claude wrote `data/config/ava_config.yaml` and `data/config/lcodb_config.yaml` (paths under
    `/data2/jvhs1/AVA/data`, `binary: /usr/local/bin/sex`, downloads `dry_run`).
    `~/.bashrc` block added: `AVA_CONFIG` / `LCODB_CONFIG` under `data/config/`, and
    `alias ava-env='unset PYTHONPATH; source /data2/jvhs1/miniforge3/bin/activate ava'` (the shell sets `PYTHONPATH`
    for the old pipeline; the alias clears it in AVA terminals only).
  - Paths to `/data2/jvhs1/AVA/data`, SExtractor name, `db_dir`. Download modes stay `"dry_run"`.
- [x] **7. Copy the four databases from the Mac** (`sqlite3 .backup`, then `scp`; check the `agn` count)
  - Done 18 Nov: `data/ava.db` (0.4 MB, 99 `agn` rows), `data/lcodb/` photometry 441 MB, spectra 242 MB, state 36 KB.
- [x] **8. LCO token** in `~/.lco_token` (`chmod 600`)
  - Done 18 Nov by the user.
- [x] **9. Install check: `READY: 0 FAIL`**
  - Done 18 Nov 13:35: `READY: 0 FAIL, 4 WARN`; 162 tests passed; lcodb 539,513 phot frames (to 2026-11-16), 56,128 spectra
    (to 2026-11-15); 99 AGN. WARNs: photometry/spectroscopy roots not created yet (step 11); banzai-floyds Python is the Mac
    path (`-R` only); `~/.lco_token` readable by others (home is a network share, `chmod` may not apply: to resolve).
  - Found: SExtractor test run gives **12 apertures**: `default.param` has `*_APER(12)` while `default.sex` lists 16
    (36,39,43,48 appended). Matters for new extractions (step 15, MuSCAT index 13), not the port. Fixed (user's OK, 13:39):
    `default.param` -> `*_APER(16)`; re-check gives "3 sources, 16 apertures per source". New extractions only.
  ```bash
  cd /data2/jvhs1/AVA && python scripts/check_install.py --tests
  ```

- [x] **9b. banzai-floyds (FLOYDS reduction, needed for `-R`)** — done early, in parallel with the port
  - 18 Nov: fork `rm-improvements@3e8e796` (user's choice over the pinned `8897b99`: sky flats ship with it) cloned to
    `/data2/jvhs1/banzai-floyds`; conda env `banzai` (Python 3.12) in `/data2/jvhs1/miniforge3`; CPU-only torch first;
    `/data2/jvhs1/benv` = clean-shell wrapper. Import check OK: banzai 1.36.2, torch 2.15.0+cpu, no CUDA.
  - AVA config set: `spectroscopy.reduction.{python,package,skyflats_dir}`, `paths.floyds_pipeline`.
    Deployment guide §4.3 updated (pin `3e8e796`), PDF rebuilt.
  ```bash
  cd /data2/jvhs1/banzai-floyds && /data2/jvhs1/benv python -m pytest banzai_floyds/tests --deselect banzai_floyds/tests/test_e2e.py -q
  /data2/jvhs1/benv python -m banzai_floyds.offline setup-db --db-address sqlite:////tmp/floyds_test.db
  ```
  - Done 14:10: **199 passed**, 8 deselected (6 min; newer commits add tests); `setup-db` registered **31 sky flats**, no
    download. ERFA "dubious year" warnings are harmless.

## 2 · Bring the archive up to date (steps 10–11)

- [x] **10. Update the LCO archive tables** (LCO, listing requests only)
  - Started 14:06 (`data/logs/lcodb_daily_first.log`, alongside the port). It also crawled proposals that are not
    current (KEY2023B-001/-001f, KEY2018B-001, KEY2014A-002, and LCO2014A-001 from 2013: ~150 listing requests).
  - **Fixed (user's request, 14:10):** `lcodb daily` now crawls only the standards sources and active proposals
    matching `daily.include_regex: '^KEY2026'` (`ava/lcodb/ingest.py`, `cli.py`, `config/lcodb_config.yaml`, and the
    host copy `data/config/lcodb_config.yaml`; test added, `tests/test_lcodb.py` 19 passed). Takes effect from the
    next run; this first run finishes as it started. Committed by the user 14:30, pushed 14:37 (with the checklist commit).
  - Finished 14:28: 560 new + 1,866 refreshed frames, 76 spectra headers, airmass for 546 frames, standards and arc/flat
    matches done; then **`link` failed: "unable to open database file"**. Cause: the `ava:` paths in the host copy of
    `lcodb_config.yaml` (`../data/ava.db`, CSVs) are relative to the config file, wrong once it lives in `data/config/`.
    Fixed 14:31 (absolute paths). Re-run the two last parts only (offline): `python -m ava.lcodb link` and
    `python -m ava.lcodb stats`.
  - Done 14:35: `link` 277 LCO targets, 151 linked to AVA, **3 flagged for review** (`target_link.review`); observing
    flag 0 changes; `stats` refreshed `agn_lco` / `lco_targets` / `agn_full` (backup `data/backups/ava_20261118T143505Z_pre-crossmatch.db`).
  ```bash
  python -m ava.lcodb daily
  ```
- [ ] **11. Target folders and Gaia reference stars**
  - 14:08 first try failed: `Timed out while attempting to connect to ephemeral Prefect API server` (`~/.prefect` on
    the CIFS home). Fix: `PREFECT_HOME=/data2/jvhs1/AVA/data/prefect` and
    `PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS=90` in `~/.bashrc`, then re-run.
  - 14:16 re-run: folders and spectroscopy summaries fine. Reference catalogues: by 14:24, 18 written (14 gspc,
    4 apass_model fallback: MCG_08-11-011, 3C273, Mrk_1298, NGC_4395), 13 failed. Cause: the CDS VizieR query service
    answers 404 (`/viz-bin/votable` and `/viz-bin/asu-tsv`; the CDS home page is up); the CfA mirror answers but lacks
    Gaia DR3 / GSPC / parts of APASS; IUCAA, NAO, Cambridge and `vizier.u-strasbg.fr` do not answer from turgon (000).
  - Finished 14:37: **91 targets initialised** (folders); **52 reference catalogues** (47 gspc, 5 apass_model fallback:
    MCG_08-11-011, 3C273, Mrk_1298, NGC_4395, Mrk_841); **39 failed**, all on VizieR (CDS 404; APASS DR9 / Gaia DR3 not
    on the CfA mirror) — incl. Mrk_817. Their spectroscopy summary (`-O`) was skipped too; the re-run does both.
  - 15:04 (user): **Gaia only.** Host config `photometry.reference.fallback: ""` (no APASS fallback: a target without
    enough GSPC stars fails). The 5 APASS catalogues are moved aside (`*.apass_bak`) and rebuilt from Gaia.
  - 15:00: **ESA Gaia Archive added as a third source** (`gea.esac.esa.int` in `vizier_servers`, host and repo
    config; `ava/photometry/reference.py`; test added, 11 passed). Not yet tried live: quick check, then re-run `-o -O`.
  - **Then:** re-run `-o -O` when CDS answers again (only missing catalogues are built). Decide whether to rebuild the
    5 APASS fallbacks with gspc (move their `reference_stars.csv` + metadata aside first).
  ```bash
  python scripts/run_pipeline.py -o -O
  ls /data2/jvhs1/AVA/data/archive/photometry/*/reference_stars.csv | wc -l
  ```

## 3 · Copy the old catalogues and spectra (step 12)

- [x] **12a. Dry run**
  - Done 18 Nov 13:42 (log `data/logs/port_legacy_dryrun.log`, ran before steps 10–11: the port needs only the lcodb
    DBs). Photometry: **462,978 catalogues for 68 targets**, 1,459 not placed. FLOYDS: **13,727 raw frames** (19 targets +
    7,243 standards), 155 not placed. 1,668 old `.tar.gz` downloads not unpacked (Mrk_1044, Mrk_142, Mrk_509, Mrk_876,
    PG_1119+120, all_standards): those frames would be downloaded again in step 15e.
    User (13:45): leave the `.tar.gz` as they are. 3C279 (685 catalogues) is not an AVA target: noted, no action.
  ```bash
  python tools/port_legacy.py --photo-root /data3/jvhs1/agn --spec-root /data2/jvhs1/agn
  ```
- [x] **12b. Review the summary and `port_legacy_not_placed.csv`** (`data/logs/`, 1,614 rows)
  - Photometry not in the DB (317): 257 are from 16–17 Nov 2026 (newer than the Mac copy; step 10 + re-port picks them up),
    60 are IGR_J17062-6143 (Aug 2022). Not linked to an AVA target (750): 3C279 (685) and `sdssrm*` fields. Not an imaging
    camera (392): FLOYDS acquisition/guide catalogues (`en06`/`en12` `a91`/`w91`) and 230 `h_e_*` files in SDSS_J2353.
  - Spectra: 110 not in the spectra DB (104 in `all_standards`, 2017–2022), 45 standards not linked. Folder renames
    resolved by frame name: `IRAS_09149-6202` -> `IRAS_09149-6206`, `NGC_5723_spec` -> `NGC_5273`, `RXJ1755+65` -> `RXJ1755.0+6519`.
- [x] **12c. Copy**
  - Started 18 Nov ~13:45 (log `data/logs/port_legacy_write.log`).
  - Done ~15:00: **462,978 catalogues** and **13,727 FLOYDS raw frames** copied, none failed (~1 h 15 min).
  ```bash
  python tools/port_legacy.py --photo-root /data3/jvhs1/agn --spec-root /data2/jvhs1/agn --write
  ```

## 4 · Measure the gaps and calibrate (steps 13–14)

- [x] **13. What is left** (note the TOTAL lines and any "cannot be calibrated" target)
  - Done 15:03 (`data/logs/backfill_status.log`, `backfill_status_{phot,spec}.csv`; run before the port re-run).
    **Photometry:** 503,358 frames; 462,415 catalogued; **40,943 to download (1.51 TB)**; 0 calibrated. Biggest gaps:
    NGC_4151 7,387 (279 GB), NGC_7469 3,300, NGC_4395 2,715, Mrk_1220 2,658 (none ported), 3C_382 1,525, J21079-3754 1,517.
    Mrk_817: 22,307 catalogued, 376 to download (14 GB). 28 targets have no old catalogues at all.
    **FLOYDS:** 9,168 spectra in 4,726 target-nights; 2,797 raw on disk; **6,371 to download**; 0 reduced.
    No target flagged "cannot be calibrated". Old catalogues: 12 apertures (count; no APERDIAM), as expected.
  ```bash
  python tools/backfill_status.py --apertures 50 --csv /data2/jvhs1/AVA/data/logs/backfill_status.csv
  ```
- [ ] **14. Calibrate the ported catalogues**
  ```bash
  python scripts/run_pipeline.py -c
  ```

## 5 · Fill the missing frames (step 15)

- [ ] **15a. Decide target order, batch size and download window** (Mrk_817 first)
- [ ] **15b. Switch downloads to live in the config** (`download.mode`, `spectroscopy.download.mode`, `select: "oldest"`)
- [ ] **15c. Mrk_817: re-port, download a batch, extract and calibrate** (LCO)
  ```bash
  python tools/port_legacy.py --photo-root /data3/jvhs1/agn --spec-root /data2/jvhs1/agn --only photo --write
  python scripts/download.py --target Mrk_817 --kind phot --live --max-frames 2000 --yes
  python scripts/run_pipeline.py -e -c --target Mrk_817
  python tools/backfill_status.py --target Mrk_817
  ```
- [ ] **15d. Other targets, same loop** (LCO)
- [ ] **15e. FLOYDS spectra backfill**, repeat until nothing is left (LCO)
  ```bash
  python scripts/run_pipeline.py -D
  ```

## 6 · Process and publish (step 16)

- [ ] **16. PyTICS, web plots, products, website data** (`-R` only once banzai-floyds is installed)
  ```bash
  python scripts/run_pipeline.py -t -p -P -w
  ```
- [ ] **16b. Compare the Mrk 817 light curve with the old pipeline's**

## 7 · Daily jobs (step 17) — later, after the backfill

- [ ] **17. Crontab**: lcodb daily, pipeline, clean-up (dry run), LCO usage plots

## Lessons for the deployment reinstall (collected today; fold into `linux_setup.md` / `deployment_checklist.md`)

- **Check where `~` lives first** (`df -h ~`). Here home is a CIFS network share: conda there crawled and hit
  case-clash warnings, and `chmod 600` has no effect, so `~/.lco_token` stayed world-readable. Put Miniforge,
  the environments and the token file on a local disk.
- **Token:** if home is a network share, keep the token in a `chmod 600` file on a local disk and export `LCO_TOKEN`
  from it in `~/.bashrc` (cron must load it too).
- **`PYTHONPATH` set by the old pipeline** leaks into new environments: `ava-env` clears it; banzai-floyds runs via
  `env -i` (`benv`).
- **SExtractor `default.param` must match the `default.sex` aperture series** (it had `*_APER(12)` against 16
  apertures). `check_install.py` should fail on a mismatch.
- **Code and data in one folder works**: data under `<checkout>/data/` is git-ignored, and the repo's default relative
  paths (`data/ava.db`, `data/lcodb`) already match; configs still go to `data/config/` with absolute paths
  (`lcodb_config.yaml`'s `db_dir` is relative to the config file).
- **Clone in place** when the target folder already has files: `git init` + `remote add` + `fetch` + `checkout -t`.
- **Port before steps 10–11**: `port_legacy.py` needs only the lcodb databases; re-run after step 10 for newer frames.
  Run it with `python -u ... | tee` so the log is readable while it runs.
- **`lcodb_config.yaml` paths are relative to the config file**: when the config is copied to `data/config/`, set
  `db_dir` **and** `ava.db`, `ava.csv`, `ava.overrides_csv` to absolute paths (the `link` step failed otherwise).
- **Git push from the host**: GitHub needs a personal access token (fine-grained, this repo, Contents read/write);
  keep it in memory only (`git config credential.helper 'cache --timeout=28800'`), never `store` or an SSH key in the
  network home (readable by others; `chmod` has no effect there).
- **Prefect state (`PREFECT_HOME`) on a local disk**, not the network home, else the ephemeral server times out.
- **`lcodb daily` scope**: check `daily.include_regex` before the first run; a first run on a new host crawls every
  proposal in `ids` that it has not seen.
- **Calibrating 4 targets at once** (4 x `n_workers` 4, one shared lcodb SQLite for `frame_qc`) gave a worker
  `BrokenPipeError` and a silent log; start a big calibration with `pipeline.n_cores: 1`–`2` and watch the files.
- **Unattended runs**: a stopped (Ctrl+Z) or orphaned `run_pipeline.py` blocks scripts that wait for it; use
  `pgrep -af run_pipeline.py` / `pkill -9` before a long run. Never edit a bash script while it runs.
- **Memory:** 4 targets x 4 calibration workers on large fields got the run killed (exit 137). Size `n_cores` x
  `n_workers` to the RAM; 1 target at a time for the backfill.
- **SExtractor binary** as a full path (`/usr/local/bin/sex`) so cron finds it.
- **banzai-floyds on Linux**: CPU-only torch first (else pip pulls GPU builds), install from a clean shell; the
  sky flats ship with the fork from `11f8ce4`.
