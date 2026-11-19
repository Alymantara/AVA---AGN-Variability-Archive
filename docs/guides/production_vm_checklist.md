---
title: "AVA pipeline — production VM installation checklist"
subtitle: "Fresh install, step by step, with the lessons of the Linux test day (18 Nov 2026) built in — living document"
date: "Started 18 November 2026"
---

# How to use this checklist

Tick each box (`[ ]` → `[x]`) on a copy for the VM and write one line under it: what it printed, what was decided.
It is the production version of `docs/guides/linux_setup.md` (read that for background) and follows
`docs/guides/deployment_guide.md` (sizing, network, jobs). Everything marked **Lesson** went wrong, or nearly, on
the Linux test host on 18 Nov 2026 (`docs/notes/linux_test_day_checklist.md`, section "Lessons"). Keep this file
updated as we learn more.

Throughout, `$AVA` is the install root on the **data volume** (e.g. `/srv/ava`); code in `$AVA/AVA` (git checkout),
data in `$AVA/AVA/data` (git-ignored), Python in `$AVA/miniforge3`. Adjust to the VM.

**Rules that hold throughout**

- LCO archive: ≤ 5,000 requests/day per account (UI + API, all jobs and any other pipeline on the same account);
  blocks above ~4 requests/s. Downloads stay `dry_run` until step 14; print the expected request count first.
- The LCO token and any other password live only in a `chmod 600` file on a **local** disk (or an environment
  variable read from it) — never in a script, config file, command line or the repository.
- Every path and tunable comes from the config copies in `data/config/` (absolute paths).
- One long pipeline run at a time unless stated; never edit a script while it is running.

# A. Before installing

- [ ] **A1. VM resources** as in the deployment guide §3: 8 vCPU (16 during the backfill), 32 GB RAM, 1 TB data
  volume (+ 0.5–1 TB scratch for the backfill), outbound HTTPS to the hosts in §5.3.
- [ ] **A2. Every working folder is on a local disk.** `df -hT ~ $AVA` — the type must be ext4/xfs, **not**
  `cifs`/`nfs`/`smb`.
  **Lesson:** on the test host `~` was a CIFS share: conda crawled, case-insensitive names clashed, `chmod 600` had
  no effect (token readable by others), Prefect's SQLite timed out. On a network home, put Miniforge, the
  environments, `PREFECT_HOME`, secrets and data on the local data volume.
- [ ] **A3. Service user** that owns `$AVA`, runs cron and has a normal (local) home. Decide whether a human
  account or a dedicated `ava` user.
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

- [ ] **B1. Packages:** `sudo apt install -y git sqlite3 build-essential curl source-extractor expect`
  (`expect` only if plots are uploaded by FTP; web server packages in step P).
- [ ] **B2. SExtractor:** `command -v source-extractor sex` and `source-extractor --version` (≥ 2.25). Note the
  **full path** for the config (cron has a minimal `PATH`).
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
- [ ] **C2. Environment:**
  ```bash
  cd $AVA/AVA && $AVA/miniforge3/bin/conda env create -f environment.yml
  source $AVA/miniforge3/bin/activate ava && pip install -e .
  python -c "import ava, prefect; print(prefect.__version__)"     # 3.x
  ```
- [ ] **C3. Shell profile** of the service user (`~/.bashrc`):
  ```bash
  # --- AVA pipeline ---
  alias ava-env='unset PYTHONPATH; source $AVA/miniforge3/bin/activate ava'
  export AVA_CONFIG=$AVA/AVA/data/config/ava_config.yaml
  export LCODB_CONFIG=$AVA/AVA/data/config/lcodb_config.yaml
  export PREFECT_HOME=$AVA/AVA/data/prefect
  export PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS=90
  export DO_NOT_TRACK=1
  export LCO_TOKEN="$(cat $AVA/.secrets/lco_token 2>/dev/null)"
  ```
  (write the real path in place of `$AVA`). `mkdir -p $AVA/AVA/data/prefect`.
  **Lesson:** terminals opened before an edit do not see it — `source ~/.bashrc`; check with `echo $PREFECT_HOME`.

# D. banzai-floyds (FLOYDS reduction)

- [ ] **D1. Code at the pinned commit:** `cd $AVA && git clone https://github.com/Alymantara/banzai-floyds.git &&
  cd banzai-floyds && git checkout 3e8e796` (the commit in deployment guide §4.3; it ships the sky-flat order
  solutions).
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

# E. Configuration (copies outside git, absolute paths)

- [ ] **E1. Copy:** `mkdir -p $AVA/AVA/data/{archive,lcodb,config,logs,web,releases}` and copy
  `config/ava_config.yaml`, `config/lcodb_config.yaml` to `data/config/`.
- [ ] **E2. `ava_config.yaml`** — set, all absolute:
  `paths.archive_root`, `paths.database`, `paths.lcodb_config`, `paths.logs`, `web.data_dir`, `releases.dir`,
  `lco_usage.snapshots.file`; `photometry.sextractor.binary` = full path (B2);
  `spectroscopy.reduction.python` = `$AVA/miniforge3/envs/banzai/bin/python`, `.package` and
  `paths.floyds_pipeline` = `$AVA/banzai-floyds`, `.skyflats_dir` = `$AVA/banzai-floyds/banzai_floyds/data/orders/skyflats`;
  `photometry.reference.vizier_servers` = CDS, **`gea.esac.esa.int`**, CfA (in that order);
  `photometry.reference.fallback: ""` (Gaia only, user's decision 18 Nov);
  `pipeline.n_cores: 1` for the first big calibration (raise later, watching the files);
  `download.mode` and `spectroscopy.download.mode` stay `"dry_run"` for now.
  **Lesson:** CfA's copies of Gaia DR3 / GSPC can be incomplete, and the completeness check compares the mirror
  with itself — so ESA comes before CfA.
- [ ] **E3. `lcodb_config.yaml`** — `db_dir` **and** `ava.db`, `ava.csv`, `ava.overrides_csv` absolute
  (they are relative to the config file: the `link` step failed on the test host); `daily.include_regex` = the
  current key project(s) (test day: `'^KEY2026'`).
- [ ] **E4. Check:** `grep -n "\.\./\|/Users/" data/config/*.yaml` prints nothing outside comments.

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

- [ ] **G1. Databases** (`ava.db`, `photometry.sqlite`, `spectra.sqlite`, `state.sqlite`) from the machine that
  has the current ones (the Linux test host after 18 Nov), with `sqlite3 <db> ".backup <copy>"` then `scp`/`rsync`
  — never a plain copy of a database in use. Check `SELECT COUNT(*) FROM agn` matches (test day: 99, 91 `lco_active`).
- [ ] **G2-a. Route "carry over" (recommended once the test host is complete):** `rsync -a` the test host's
  `data/archive/` (catalogues, reference catalogues, `measurements.parquet`, PyTICS solutions, raw FLOYDS) to the VM.
  No re-port, no re-calibration. Then `tools/backfill_status.py` must give the same TOTAL lines as on the host.
- [ ] **G2-b. Route "from the old pipeline":** `tools/port_legacy.py` dry run → review `port_legacy_not_placed.csv`
  → `--write` (test day: 463,235 catalogues + 13,727 FLOYDS frames, ~1 h 15 min; old folders only read).

# H. Install check

- [ ] **H1.** `ava-env && cd $AVA/AVA && python scripts/check_install.py --tests` → `READY: 0 FAIL`.
  Expected WARN only for folders not yet made. **Check the SExtractor line says "16 apertures per source"**
  (Lesson: `default.param` once said `*_APER(12)` against 16 diameters).
- [ ] **H2. One real frame end to end** (≈ 15 archive requests):
  `python scripts/download.py --target Mrk_817 --kind phot --live --max-frames 1 --yes` then
  `python scripts/run_pipeline.py -e --target Mrk_817`; the newest `_cat.fits` has 16 apertures and an `APERDIAM`
  header 3…48 (test day: `ogg2m001-fs02-20200620-0049-e91`, 356 sources).

# I. Archive tables

- [ ] **I1.** `python -u -m ava.lcodb daily 2>&1 | tee data/logs/lcodb_daily_first.log` — only while no other
  job on the same LCO account is downloading. Check the log names only current proposals (`daily.include_regex`);
  older ones are crawled on request with `lcodb sync --proposal ID`.
- [ ] **I2.** Review the names `lcodb link` flagged: `sqlite3 data/lcodb/spectra.sqlite "SELECT * FROM target_link
  WHERE review IS NOT NULL"`; decisions go in `data/ava/ava_link_overrides.csv`.

# J. Target folders and reference catalogues

- [ ] **J1.** `python -u scripts/run_pipeline.py -o -O 2>&1 | tee data/logs/init.log` (skip on route G2-a if the
  catalogues came over).
- [ ] **J2. Every target is Gaia GSPC, from a complete source:**
  `grep -L "^method: gspc" data/archive/photometry/*/reference_stars_meta.yaml` prints nothing, and
  `grep -h "^catalogue:" data/archive/photometry/*/reference_stars_meta.yaml | sort | uniq -c` shows ESA (or CDS)
  only. Rebuild others: move `reference_stars.csv` + `_meta.yaml` aside, run `-o` again.

# K–N. Backfill and processing

- [ ] **K. What is left:** `python tools/backfill_status.py --apertures 50 --csv data/logs/backfill_status.csv`.
- [ ] **L. Downloads** (LCO; user's go-ahead per batch): one target at a time,
  `scripts/download.py --target T --kind phot --live --max-frames N --yes`, then `run_pipeline.py -e -c --target T`.
  Keep each day's total well under 5,000 requests including the daily jobs.
- [ ] **M. Calibration, PyTICS, plots:** `python -u scripts/run_pipeline.py -c -t -p` with `pipeline.n_cores: 1`
  first. **Lesson:** 4 targets × 4 workers sharing one SQLite `frame_qc` gave a worker `BrokenPipeError` and a
  silent log; judge progress by `measurements.parquet`, `agn_lightcurve*.csv` and `pytics/` timestamps.
- [ ] **N. Spectra:** `-D` (`select: "oldest"` for the backfill, then `"new"`), `-R`, `-P`.

# P. Website

- [ ] **P1.** `sudo apt install -y apache2 php libapache2-mod-php php-sqlite3`; `php -m | grep -i pdo_sqlite`.
- [ ] **P2.** `python scripts/run_pipeline.py -w`; Apache `DocumentRoot` = `web/`, `SetEnv AVA_WEB_DATA`,
  `AVA_WEB_DATA_URL`, `AllowOverride`; HTTPS certificate; domain/DNS.
- [ ] **P3.** Quick local test: `ln -sfn <web.data_dir> web/data && echo web/data >> .git/info/exclude &&
  php -S 127.0.0.1:8080 -t web`.
- [ ] **P4.** (If plots also go to the external site by FTP) password file as in F2; one-file upload test first.

# Q. Scheduled jobs

- [ ] **Q1. Cron does not read `~/.bashrc`:** every line sets `AVA_CONFIG`, `LCODB_CONFIG`, `PREFECT_HOME`,
  `PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS`, loads the token
  (`LCO_TOKEN=$(cat $AVA/.secrets/lco_token)`), calls the environment's Python by full path, and logs to
  `data/logs/`. Jobs as in deployment guide §7 (lcodb daily 01:00, pipeline 02:00, clean-up 05:00 **dry run**,
  LCO usage every 6 h), spaced so no two archive jobs overlap.
- [ ] **Q2.** First night: read every log the next morning before switching clean-up to `--live`.

# R. Backups and monitoring

- [ ] **R1.** Daily `sqlite3 .backup` of `ava.db` and the lcodb databases; weekly off-VM copy of catalogues,
  `measurements.parquet`, reduced spectra, `releases/` (~0.25 TB).
- [ ] **R2.** Alerts: cron exit codes, Prefect failed runs, data volume > 80 %, LCO HTTP 429, newest frame age per
  active target.

# S. Sign-off

| Check | Result | Date / who |
|---|---|---|
| `check_install.py --tests` READY 0 FAIL, 16 apertures | | |
| Reference catalogues: all GSPC, ESA/CDS | | |
| `backfill_status` TOTAL lines recorded | | |
| Mrk 817 light curve compared with the old pipeline | | |
| Website up, HTTPS | | |
| First nightly run clean; clean-up switched to live | | |
| Backups restored once as a test | | |
