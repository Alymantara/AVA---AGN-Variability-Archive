---
title: "AVA pipeline — production VM installation checklist"
subtitle: "Fresh install, step by step, with the lessons of the Linux test day (18 Nov 2026) built in — living document"
date: "Started 18 November 2026 — updated 19 November 2026 (night run, QC-0002, PyTICS fixes, first VM install)"
---

# How to use this checklist

Tick each box (`[ ]` → `[x]`) on a copy for the VM and write one line under it: what it printed, what was decided.
It is the production version of `docs/guides/linux_setup.md` (read that for background) and follows
`docs/guides/deployment_guide.md` (sizing, network, jobs). Everything marked **Lesson** went wrong, or nearly, on
the Linux test host on 18 Nov 2026 (`docs/notes/linux_test_day_checklist.md`, section "Lessons"). Keep this file
updated as we learn more.

Throughout, `$AVA` is the install root on the **data volume** (production VM `l-pipeline`: `/data/ava`); code in
`$AVA/AVA` (git checkout), data in `$AVA/AVA/data` (git-ignored), Python in `$AVA/miniforge3`, banzai-floyds in
`$AVA/banzai-floyds`. This layout is the config template's default, so `tools/make_config.py` (E1) needs no paths.

**Pasting commands.** Start `tmux new -s ava` on a line of its own: pasted together with the next commands, those
are lost. Never paste a `<placeholder>` literally; replace it first.

**Rules that hold throughout**

- LCO archive: ≤ 5,000 requests/day per account (UI + API, all jobs and any other pipeline on the same account);
  blocks above ~4 requests/s. Downloads stay `dry_run` until step 14; print the expected request count first.
- The LCO token and any other password live only in a `chmod 600` file on a **local** disk (or an environment
  variable read from it) — never in a script, config file, command line or the repository.
- Every path and tunable comes from the config copies in `data/config/` (absolute paths).
- One long pipeline run at a time unless stated; never edit a script while it is running.
- **Re-read every script on the host before launching it** (`cat` it there, not the copy you edited elsewhere).
  Lesson (18 Nov): a stale copy of the overnight script ran a copy step that had been removed.
- Long runs log with `python -u … 2>&1 | tee` — otherwise the log is buffered and looks stalled (18 Nov).

# A. Before installing

- [ ] **A1. VM resources** as in the deployment guide §3: 8 vCPU (16 during the backfill), 32 GB RAM, 1 TB data
  volume (+ 0.5–1 TB scratch for the backfill), outbound HTTPS to the hosts in §5.3. Record the real size
  (`nproc; free -g; df -h /data`). The first VM had 2 vCPU and 7.8 GB, below spec: `pipeline.n_cores: 1` (the
  template's default) and one long job at a time.
- [ ] **A2. Every working folder is on a local disk.** `df -hT ~ $AVA` — the type must be ext4/xfs, **not**
  `cifs`/`nfs`/`smb` — and the data volume is mounted at boot: `findmnt --fstab /data` prints one line.
  **Lesson:** on the test host `~` was a CIFS share: conda crawled, case-insensitive names clashed, `chmod 600` had
  no effect (token readable by others), Prefect's SQLite timed out. On a network home, put Miniforge, the
  environments, `PREFECT_HOME`, secrets and data on the local data volume.
- [ ] **A3. Service user** `ava` that owns `$AVA`, runs cron and has a local home (no password, no sudo):
  ```bash
  sudo useradd -m -d /home/ava -s /bin/bash ava
  sudo mkdir -p /data/ava && sudo chown ava: /data/ava      # the admin makes $AVA, before B3
  sudo -iu ava                                              # work as ava from here
  ```
  If the site's accounts get a network home that does not mount on this VM, the local `/home/ava` above avoids it.
- [ ] **A4. Admin rights** (`sudo`) for steps B1 and the web server, or someone who has them.
- [ ] **A5. Reachability test** (each should print 200):
  ```bash
  for u in https://archive-api.lco.global/ https://observe.lco.global/ \
    "https://gea.esac.esa.int/tap-server/tap/sync?REQUEST=doQuery&LANG=ADQL&FORMAT=csv&QUERY=SELECT+TOP+1+source_id+FROM+gaiadr3.synthetic_photometry_gspc" \
    "https://vizier.cds.unistra.fr/viz-bin/votable?-source=I/355/gaiadr3&-c=12.0+30.0&-c.rs=60&-out.max=1" \
    https://github.com/ https://conda.anaconda.org/ https://download.pytorch.org/whl/cpu/; do
    printf "%s  %s\n" "$(curl -s -o /dev/null -m 30 -w '%{http_code}' "$u")" "$u"; done
  ```
  **Lesson:** CDS VizieR's query service answered 404 for a whole afternoon; the ESA Gaia Archive is now in
  `vizier_servers` and must be reachable.

# B. System software

- [ ] **B1. Packages:** `sudo apt install -y git sqlite3 build-essential curl source-extractor tmux time expect`
  (`time` gives `/usr/bin/time`, not installed by default; `expect` only if plots are uploaded by FTP; web
  server packages in step P).
- [ ] **B2. SExtractor:** `command -v source-extractor sex` and `source-extractor --version` (≥ 2.25; VM:
  `/usr/bin/source-extractor` 2.28.2). The template's `photometry.sextractor.binary` is `source-extractor`, and
  `sex` is tried as well.
- [ ] **B3. Miniforge on the data volume, no `conda init`:**
  ```bash
  cd $AVA && curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
  bash Miniforge3-Linux-x86_64.sh -b -p $AVA/miniforge3 && $AVA/miniforge3/bin/conda --version
  ```
  If the installer warns that `PYTHONPATH` is set, note it: the `ava-env` alias (C3) clears it.

# C. AVA code and environment

- [ ] **C1. Clone:** `cd $AVA && git clone https://github.com/Alymantara/AVA---AGN-Variability-Archive.git AVA`
  (into an empty folder; if it already holds files: `git init -b main`, `git remote add origin …`, `git fetch`,
  `git checkout -t origin/main`).
- [ ] **C1b. The clone has the test-day fixes** (pushed from the laptop on 19 Nov):
  ```bash
  git log --oneline | grep -E "QC-0002|PyTICS: three crashes|ESA Gaia Archive"     # three or more lines
  grep -n 'FLOAT_FORMAT = "%.10g"' ava/pipeline/tasks/reference.py               # one line
  ```
  Without these: reference positions are rounded (QC-0002, AGN unmatched for RA ≥ 100°), PyTICS crashes on
  filters without frames and on a first full fit, and there is no ESA fallback when CDS is down.
- [ ] **C2. Environment:**
  ```bash
  cd $AVA/AVA && $AVA/miniforge3/bin/conda env create -f environment.yml
  source $AVA/miniforge3/bin/activate ava && pip install -e .
  python -c "import ava, prefect; print(prefect.__version__)"     # 3.x
  ```
- [ ] **C3. Shell profile** of the service user (`~/.bashrc`):
  ```bash
  # --- AVA pipeline ---
  export AVA=/data/ava
  export PATH="$HOME/.local/bin:$PATH"
  export TMPDIR=$AVA/tmp                      # /tmp is RAM (tmpfs) on the VM; big temporary files go to the disk
  alias ava-env='unset PYTHONPATH; source $AVA/miniforge3/bin/activate ava'
  export AVA_CONFIG=$AVA/AVA/data/config/ava_config.yaml
  export LCODB_CONFIG=$AVA/AVA/data/config/lcodb_config.yaml
  export PREFECT_HOME=$AVA/AVA/data/prefect
  export PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS=90
  export PREFECT_SERVER_ANALYTICS_ENABLED=false
  export DO_NOT_TRACK=1
  ```
  The token is **not** exported. Every job, in a shell or under cron, reads it from `$AVA/.secrets/lco_token` (F1),
  the file both config templates name (`token_file`). One lookup for the whole package (`ava.lco.token`):
  `$LCO_API_TOKEN` (the one documented variable; `$LCO_TOKEN` is still accepted), then `lco.token_file`, then lcodb's
  `token_file`, then `~/.lco_token`. **Lesson (19 Nov):** with the token only in `$LCO_TOKEN` from `.bashrc`, the
  pipeline worked by hand but failed under cron ("No LCO API token"), because cron has no environment.
  Then `mkdir -p $AVA/tmp $AVA/AVA/data/prefect`, and check that a login shell reads `~/.bashrc` (`sudo -iu ava`
  starts one): `grep bashrc ~/.profile` prints a line. The Prefect settings are also applied by the code
  (`ava.utils.prefect_env`, 19 Nov), so a missing line here no longer locks Prefect's database.
  **Lesson:** terminals opened before an edit do not see it — `source ~/.bashrc`; check with `echo $PREFECT_HOME`.

# D. banzai-floyds (FLOYDS reduction)

- [ ] **D1. Code at the pinned commit** (deployment guide §4.3):
  ```bash
  cd $AVA && git clone https://github.com/Alymantara/banzai-floyds.git
  ```
  ```bash
  cd $AVA/banzai-floyds && git checkout 0271697 && git log --oneline -1
  ```
  `0271697` is on branch `rm-improvements` (five more flux standards, fringe templates that survive repeat runs,
  rejection of misidentified arc lines). **Never use `origin/main`:** it lacks `offline.py`, the shipped sky flats
  and ~8,100 lines of the fork.
- [ ] **D2. Environment + clean-shell wrapper:**
  ```bash
  $AVA/miniforge3/bin/conda create -y -n banzai python=3.12 pip
  cat > $AVA/benv <<EOF
  #!/bin/sh
  exec env -i HOME="\$HOME" PATH="$AVA/miniforge3/envs/banzai/bin:/usr/bin:/bin" OPENTSDB_PYTHON_METRICS_TEST_MODE=True "\$@"
  EOF
  chmod +x $AVA/benv
  $AVA/benv python -m pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU torch FIRST
  $AVA/benv python -m pip install -e "$AVA/banzai-floyds[test]"
  ```
- [ ] **D3. Checks:** import (`banzai 1.36.2`, torch `+cpu`, `cuda False`); tests
  `cd $AVA/banzai-floyds && $AVA/benv python -m pytest banzai_floyds/tests --deselect banzai_floyds/tests/test_e2e.py -q`
  (test day: 199 passed); `$AVA/benv python -m banzai_floyds.offline setup-db --db-address sqlite:////tmp/f.db`
  → "sky flats registered: 31".

# E. Configuration (this machine's overrides on top of the templates)

Since 19 Nov 2026 a machine's config files hold **only what differs** from the repository's templates. They start
with `base: <template>`, and AVA and lcodb load the template first, so settings added to it later arrive with
`git pull` and nothing is merged by hand. The template's defaults are the production layout above.

- [ ] **E1. Write them:** `mkdir -p $AVA/AVA/data/{archive,lcodb,logs}`, then
  ```bash
  cd $AVA/AVA && python tools/make_config.py init --token-file $AVA/.secrets/lco_token
  ```
  (`--token-file` only if the token is not at the default `$AVA/.secrets/lco_token`.)
  It writes `data/config/ava_config.yaml` and `data/config/lcodb_config.yaml`:
  - the lcodb paths as absolute paths;
  - `web.data_dir` `data/web` and `pipeline.prefect.home` `data/prefect`;
  - the **live** LCO-usage log at `data/live/lco_usage/snapshots.csv`;
  - the token file's path (never the token).

  Anything else: `--set key=value` (e.g. `--set pipeline.n_cores=2`, `--set lcodb:daily.include_regex='^KEY2026'`).
- [ ] **E2. A machine that has a full copy from before 19 Nov** (the first VM):
  `python tools/make_config.py diff data/config/ava_config.yaml` lists every key it changes. Keep this machine's
  real values as `--set`, then `init --force`; the stale values disappear (e.g. the old `nightly_steps` and
  `schedule_cron`). **Move the live LCO-usage log off the tracked seed:** if `lco_usage.snapshots.file` pointed at
  `data/lco_usage/snapshots.csv` (the repository's seed), `git status` shows it modified and `git pull` fails:
  `mkdir -p data/live/lco_usage && cp data/lco_usage/snapshots.csv data/live/lco_usage/ && git checkout data/lco_usage/snapshots.csv`.
- [ ] **E3. Settings to keep as they are** (template defaults): `lco.token_file` and lcodb `token_file` =
  `$AVA/.secrets/lco_token` (F1); `photometry.reference.vizier_servers` = CDS,
  **`gea.esac.esa.int`**, CfA; `photometry.reference.fallback: ""` (Gaia only, 18 Nov); `pipeline.n_cores: 1`;
  `download.mode` and `spectroscopy.download.mode` = `"dry_run"` until step L. lcodb `daily.include_regex` =
  `'^KEY2026'` (the key project runs for years). **Lesson:** CfA's copies of Gaia DR3 / GSPC can be incomplete,
  and the completeness check compares the mirror with itself — so ESA comes before CfA.
- [ ] **E4. Check:** `python tools/make_config.py check` → no FAIL. It catches another machine's paths
  (`/Users/`, `/data2/`, `/data3/` that do not exist here) and missing folders. `python tools/make_config.py show`
  prints the merged config in use.

# F. Secrets

- [ ] **F1. LCO token**, without echo or shell history:
  ```bash
  mkdir -p $AVA/.secrets && chmod 700 $AVA/.secrets
  read -rs -p "LCO token: " T && printf '%s\n' "$T" > $AVA/.secrets/lco_token && unset T && echo
  chmod 600 $AVA/.secrets/lco_token && ls -l $AVA/.secrets     # -rw-------
  ```
- [ ] **F2. Other passwords** (website FTP, if used) the same way; scripts read the file at run time.
- [ ] **F3. Git push** (if this machine commits): a fine-grained GitHub token (this repo, Contents read/write),
  kept in memory only: `git config credential.helper 'cache --timeout=28800'`.

# G. Databases and data

Choose one route and record it.

- [ ] **G1. The four databases** (`ava.db`, `photometry.sqlite`, `spectra.sqlite`, `state.sqlite`) from the
  machine that has the current ones. Make the copies with `linux_setup.md` step 7b: `sqlite3 <db> ".backup <copy>"`,
  never a plain copy of a database in use. Step 7b then empties, in the copies, the bookkeeping that describes the
  other machine's files (`spec_qc`, `local_files`, `spec_lines`, `download_state`); the VM rebuilds it (decided
  19 Nov). `ava` has no SSH keys, so copy as the admin user to `/tmp`, then install with the right owner:
  ```bash
  sha256sum /tmp/ava_dbs/*                       # compare with the same command on the source machine
  ```
  ```bash
  sudo install -o ava -g ava -m 644 /tmp/ava_dbs/ava.db $AVA/AVA/data/ava.db
  ```
  ```bash
  for d in photometry spectra state; do sudo install -o ava -g ava -m 644 /tmp/ava_dbs/$d.sqlite $AVA/AVA/data/lcodb/; done
  ```
  ```bash
  for f in $AVA/AVA/data/ava.db $AVA/AVA/data/lcodb/*.sqlite; do echo "$f $(sqlite3 $f 'PRAGMA integrity_check')"; done
  ```
  Every line ends in `ok`, and `SELECT COUNT(*) FROM agn` matches the source; then delete `/tmp/ava_dbs`.
- [ ] **G2-a. Route "carry over" (recommended once the test host is complete):** `rsync -a` the test host's
  `data/archive/` (catalogues, reference catalogues, `measurements.parquet`, PyTICS solutions, raw FLOYDS) to the VM.
  No re-port, no re-calibration. Then `tools/backfill_status.py` must give the same TOTAL lines as on the host.
  **Lesson (QC-0002, 18–19 Nov):** every reference catalogue built on the test host before the fix has
  positions rounded to 6 significant figures (up to 1.8″ off for RA ≥ 100°), and the measurements calibrated
  against them miss the AGN (MR 2251-178: 15 % matched). Carry over only after the host has rebuilt them
  (`reference_catalog.fn(T, force=True)`) and recalibrated (`calibrate.fn(T, force=True)`) — or do both on the
  VM before step M. J3 below checks it.
- [ ] **G2-b. Route "from the old pipeline":** `tools/port_legacy.py` dry run → review `port_legacy_not_placed.csv`
  → `--write` (test day: 463,235 catalogues + 13,727 FLOYDS frames, ~1 h 15 min; old folders only read).

# H. Install check

- [ ] **H1.** `ava-env && cd $AVA/AVA && python scripts/check_install.py --tests` → `READY: 0 FAIL`. The token line
  says "LCO API token (as cron sees it): from <file>": it ignores the environment variables, as cron will.
  Expected WARN only for folders not yet made. **Check the SExtractor line says "16 apertures per source"**
  (Lesson: `default.param` once said `*_APER(12)` against 16 diameters).
- [ ] **H2. One real frame end to end** (≈ 15 archive requests):
  `python scripts/download.py --target Mrk_817 --kind phot --live --max-frames 1 --yes` then
  `python scripts/run_pipeline.py -e --target Mrk_817`; the newest `_cat.fits` has 16 apertures and an `APERDIAM`
  header 3…48 (test day: `ogg2m001-fs02-20200620-0049-e91`, 356 sources).
- [ ] **H3. One FLOYDS night end to end.** On a fresh install `spectroscopy.download.select: "new"` finds no night
  (empty `download_state`), so name one:
  `python scripts/run_pipeline.py -D --spec-nights YYYYMMDD --spec-mode live --target Mrk_817`, then
  `-R --spec-nights YYYYMMDD --target Mrk_817`, then `-P --target Mrk_817`. First VM: 81 s for the night,
  1.1 GB peak memory.

# I. Archive tables

- [ ] **I1.** `python -u -m ava.lcodb daily 2>&1 | tee data/logs/lcodb_daily_first.log` — only while no other
  job on the same LCO account is downloading. Check the log names only current proposals (`daily.include_regex`);
  older ones are crawled on request with `lcodb sync --proposal ID`.
- [ ] **I2.** Review the names `lcodb link` flagged: `sqlite3 data/lcodb/spectra.sqlite "SELECT * FROM target_link
  WHERE review IS NOT NULL"`; decisions go in `data/ava/ava_link_overrides.csv`.

# J. Target folders and reference catalogues

- [ ] **J0. One target first:** `python -u scripts/run_pipeline.py -o -O --target Mrk_817`, and check its
  `reference_stars_meta.yaml` (J2) before running all.
- [ ] **J1.** `python -u scripts/run_pipeline.py -o -O 2>&1 | tee data/logs/init.log` (skip on route G2-a if the
  catalogues came over).
- [ ] **J2. Every target is Gaia GSPC, from a complete source:**
  `grep -L "^method: gspc" data/archive/photometry/*/reference_stars_meta.yaml` prints nothing, and
  `grep -h "^catalogue:" data/archive/photometry/*/reference_stars_meta.yaml | sort | uniq -c` shows ESA (or CDS)
  only. Rebuild others: move `reference_stars.csv` + `_meta.yaml` aside, run `-o` again.
- [ ] **J3. Positions at full precision (QC-0002):** prints nothing:
  ```bash
  python - <<'PY'
  import glob, numpy as np, pandas as pd
  for f in sorted(glob.glob("data/archive/photometry/*/reference_stars.csv")):
      ra = pd.read_csv(f, usecols=["ra"])["ra"] * 1e5
      if (np.abs(ra - ra.round()) < 1e-6).all(): print("rounded:", f)
  PY
  ```
  Every RA with ≤ 5 decimals means the old `%.6g` writer. (On 19 Nov all 39 calibrated test-host catalogues
  were flagged.)

# K–N. Backfill and processing

- [ ] **K. What is left:** `python tools/backfill_status.py --apertures 50 --csv data/logs/backfill_status.csv`.
- [ ] **L. Downloads** (LCO; user's go-ahead per batch): one target at a time,
  `scripts/download.py --target T --kind phot --live --max-frames N --yes`, then `run_pipeline.py -e -c --target T`.
  Keep each day's total well under 5,000 requests including the daily jobs.
- [ ] **M. Calibration, PyTICS, plots:** `python -u scripts/run_pipeline.py -c -t -p` with `pipeline.n_cores: 1`
  first. **Lesson:** 4 targets × 4 workers sharing one SQLite `frame_qc` gave a worker `BrokenPipeError` and a
  silent log; judge progress by `measurements.parquet`, `agn_lightcurve*.csv` and `pytics/` timestamps.
  **Lesson (night of 18 Nov):** the overnight stage was killed with exit 137 (out of memory) with 4 targets ×
  4 workers. Before a long run: `free -g`; after any silent stop: `journalctl -k --since today | grep -iE
  "out of memory|killed process"`. The largest targets (Mrk 509, Fairall 9, MCG+08-11-011: 160–220 MB of
  compressed `measurements.parquet`, ~50,000 frames) set the memory need; raise `n_cores` only with headroom.
- [ ] **M2. PyTICS end to end on one target first** (needs C1b): `run_pipeline.py -t -p --target Mrk_817`.
  First VM, ~80 frames: extraction ~0.7 s/frame, calibration ~0.06 s/frame, PyTICS + plots ~20 s per target;
  expect `pytics/absolute_zp_stars.parquet`, `agn_lightcurve_pytics.csv` and `Mrk_817_LCO_merged_lightcurve.csv`.
  Lessons (18 Nov, all three fixed): a filter with no passing frames (Y, often u) crashed with pyarrow
  `ArrowTypeError`; the first full fit failed writing into a missing `pytics/`; a target without
  `measurements.parquet` raised instead of being skipped. PyTICS reads only `measurements.parquet`,
  `reference_stars.csv` and `frame_qc` (in `photometry.sqlite`) — not `ava.db`.
- [ ] **M3. QC rates per target** after calibration: `agn_missing` and `few_matched` fractions. Known open items:
  `qc.min_matched: 30` is unreachable in sparse fields (PG 2304+043: 0 % pass); fields with few GSPC u stars get
  no u zero point (MR 2251-178, QC-0001). Record them; do not lower thresholds on the VM ad hoc.
- [ ] **N. Spectra:** `-D` (`select: "oldest"` for the backfill, then `"new"`; a fresh install finds no "new"
  night until the first download, H3), `-R`, `-P`.

# P. Website

- [ ] **P1.** `sudo apt install -y apache2 php libapache2-mod-php php-sqlite3`; `php -m | grep -i pdo_sqlite`.
- [ ] **P2.** `python scripts/run_pipeline.py -w`; Apache `DocumentRoot` = `web/`, `SetEnv AVA_WEB_DATA`,
  `AVA_WEB_DATA_URL`, `AllowOverride`; HTTPS certificate; domain/DNS.
- [ ] **P3.** Quick local test: `ln -sfn <web.data_dir> web/data && echo web/data >> .git/info/exclude &&
  php -S 127.0.0.1:8080 -t web`.
- [ ] **P4.** (If plots also go to the external site by FTP) password file as in F2; one-file upload test first.

# Q. Scheduled jobs

- [ ] **Q0. The machine runs in UTC:** `timedatectl` shows `UTC` (else `sudo timedatectl set-timezone UTC`).
  Debian's cron ignores `CRON_TZ`, so the schedule is in the machine's time zone.
- [ ] **Q1. Test every job once** (deployment guide §7.0), from `ava-env` with the C3 variables set (they are copied
  into the crontab; cron reads no `~/.bashrc`, and the token comes from `token_file`). First the probe, which runs
  under `env -i` and the crontab's variables exactly as cron will (token file, configs, SExtractor, banzai-floyds,
  writable folders, imports), and installs only if it passes:
  ```bash
  python scripts/make_crontab.py --test --check --install
  ```
  An hour later `tail -40 data/logs/daily_check_test.log` ends in `PASSED`; any failed job shows its log's end.
- [ ] **Q2. Mail:** `MAILTO` needs a mail server. The first VM has `mail` but no `sendmail`: install one, or a
  relay to the department's server (e.g. `sudo apt install msmtp-mta`), then `echo test | mail -s "AVA test" <address>`
  must arrive.
- [ ] **Q3. Production:** `python scripts/make_crontab.py --production --mailto <address> --install`
  (01:00 lcodb daily, 02:00 pipeline, 05:00 clean-up **dry run**, every 6 h LCO usage, 07:00 health check).
- [ ] **Q4.** After the first nights: read `data/logs/cleanup.log` (what it would delete) and
  `data/logs/daily_check.log`, then switch clean-up to live:
  `python scripts/make_crontab.py --production --mailto <address> --cleanup-live --install`.

# R. Backups and monitoring

- [ ] **R1.** Daily `sqlite3 .backup` of `ava.db` and the lcodb databases; weekly off-VM copy of catalogues,
  `measurements.parquet`, reduced spectra, `releases/` (~0.25 TB). (Job 5, still to build.)
- [ ] **R2.** Alerts: the 07:00 health check (`scripts/daily_check.py`: missing or failed jobs, stale archive
  tables) mails on failure (Q2); still to add: data volume > 80 %, LCO HTTP 429.

# S. Sign-off

| Check | Result | Date / who |
|---|---|---|
| `check_install.py --tests` READY 0 FAIL, 16 apertures | | |
| Code includes QC-0002, PyTICS and ESA fixes (C1b) | | |
| Reference catalogues: all GSPC, ESA/CDS, full-precision positions (J3) | | |
| MR 2251-178 AGN-matched fraction ≥ 97 % | | |
| PyTICS end to end on Mrk 817, merged CSV written (M2) | | |
| Long run: memory headroom checked, no OOM in `journalctl -k` | | |
| `backfill_status` TOTAL lines recorded | | |
| Mrk 817 light curve compared with the old pipeline | | |
| Website up, HTTPS | | |
| `make_crontab.py --test`: daily_check_test PASSED | | |
| First nightly run clean; clean-up switched to live (Q4) | | |
| Backups restored once as a test | | |
