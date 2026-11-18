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

## Action plan after lunch (written 14:15)

1. **Step 11 again** (Prefect fix): add `PREFECT_HOME` / timeout to `~/.bashrc`, `source ~/.bashrc && ava-env`, re-run
   `python -u scripts/run_pipeline.py -o -O 2>&1 | tee data/logs/step11_init.log` (VizieR only, a few hours).
2. **Check** `lcodb_daily_first.log` (step 10) and `port_legacy_write.log` (12c, expected done ~15:15–15:30).
3. **Commit** today's changes (user, in `/data2/jvhs1/AVA`; only our files):
   `git add ava/lcodb/ingest.py ava/lcodb/cli.py config/lcodb_config.yaml tests/test_lcodb.py data/reference/sextractor/default.param CLAUDE.md docs/notes/ docs/guides/deployment_guide.md docs/guides/deployment_guide.pdf && git commit` (then `git push`).
4. **Re-run the port** (`--write`) after step 10, to pick up the 257 catalogues of 16–17 Nov.
5. **Step 13** (`tools/backfill_status.py --apertures 50 --csv data/logs/backfill_status.csv`), then **step 14** (`-c`).
6. Token: move `~/.lco_token` to a `chmod 600` file on `/data2` and export `LCO_TOKEN` (still open).

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

- [ ] **10. Update the LCO archive tables** (LCO, listing requests only)
  - Started 14:06 (`data/logs/lcodb_daily_first.log`, alongside the port). It also crawled proposals that are not
    current (KEY2023B-001/-001f, KEY2018B-001, KEY2014A-002, and LCO2014A-001 from 2013: ~150 listing requests).
  - **Fixed (user's request, 14:10):** `lcodb daily` now crawls only the standards sources and active proposals
    matching `daily.include_regex: '^KEY2026'` (`ava/lcodb/ingest.py`, `cli.py`, `config/lcodb_config.yaml`, and the
    host copy `data/config/lcodb_config.yaml`; test added, `tests/test_lcodb.py` 19 passed). Takes effect from the
    next run; this first run finishes as it started. **Commit pending** (user runs it, see the plan below).
  ```bash
  python -m ava.lcodb daily
  ```
- [ ] **11. Target folders and Gaia reference stars**
  - 14:08 first try failed: `Timed out while attempting to connect to ephemeral Prefect API server` (`~/.prefect` on
    the CIFS home). Fix: `PREFECT_HOME=/data2/jvhs1/AVA/data/prefect` and
    `PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS=90` in `~/.bashrc`, then re-run.
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
- [ ] **12c. Copy**
  - Started 18 Nov ~13:45 (log `data/logs/port_legacy_write.log`).
  ```bash
  python tools/port_legacy.py --photo-root /data3/jvhs1/agn --spec-root /data2/jvhs1/agn --write
  ```

## 4 · Measure the gaps and calibrate (steps 13–14)

- [ ] **13. What is left** (note the TOTAL lines and any "cannot be calibrated" target)
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
- **Prefect state (`PREFECT_HOME`) on a local disk**, not the network home, else the ephemeral server times out.
- **`lcodb daily` scope**: check `daily.include_regex` before the first run; a first run on a new host crawls every
  proposal in `ids` that it has not seen.
- **SExtractor binary** as a full path (`/usr/local/bin/sex`) so cron finds it.
- **banzai-floyds on Linux**: CPU-only torch first (else pip pulls GPU builds), install from a clean shell; the
  sky flats ship with the fork from `11f8ce4`.
