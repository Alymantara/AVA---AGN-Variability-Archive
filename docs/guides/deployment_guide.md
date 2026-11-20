---
title: "AVA pipeline — deployment guide (internal)"
subtitle: "What a software engineering team needs to deploy and run the AGN Variability Archive pipeline"
date: "Started 16 November 2026 — living document"
---

# 1. Purpose and status

This is the **internal** reference for deploying the AVA pipeline (LCO photometry and FLOYDS spectroscopy →
calibrated light curves, spectral products → public website). It is kept up to date as deployment
requirements are found; the per-setting audit is in `docs/guides/deployment_checklist.md` and the open science
work in `docs/notes/future_improvements.md`.

- **Target platform:** a Linux virtual machine (Ubuntu 24.04 LTS or 22.04 LTS assumed below).
- **State (16 Nov 2026):** the pipeline runs end-to-end on a development Mac against a small test archive
  (`data/test_archive`). The production machine has not been set up. Items marked **TO BUILD** do not
  exist yet; items marked **CHECK** have not been tested in production conditions.

# 2. Summary of what has to be deployed

| Component | What it is | Section |
|---|---|---|
| AVA code | this repository (`ava/`, `scripts/`, `tools/`, `config/`), Python 3.12 environment | 4 |
| banzai-floyds (fork) | FLOYDS reduction, separate Python environment (PyTorch) | 4.3 |
| SExtractor | source catalogues for every photometry frame (system binary) | 4.2 |
| LCO archive databases | `photometry.sqlite`, `spectra.sqlite`, `state.sqlite` (`ava.lcodb`) | 6 |
| AVA database | `ava.db` (targets, derived properties, releases; "the database is king") | 6 |
| Prefect | orchestration of the daily pipeline (server + worker or `--serve`) | 7 |
| Cron jobs | daily archive update, daily pipeline, raw-image clean-up | 7 |
| Web server | Apache + PHP (`web/`), reads a copy of the data (`web.data_dir`) | 8 |

# 3. Virtual machine sizing

## 3.1 Storage

Decision (16 Nov 2026): **photometry images are not kept**. They are downloaded, catalogued and
calibrated, then deleted after a short retention period (section 7.4). Catalogues, spectra (raw and
reduced) and all science products are kept permanently.

Sizes below are for the frames already linked to AVA targets on 16 Nov 2026: **497,929 photometry
frames** (Sinistro 436,642; old Sinistro 41,313; Spectral 9,489; MuSCAT 10,485) and **4,658 AGN
spectroscopy nights** (+ 4,363 standard-star site-nights). Growth uses the 2025 rate (~72,900 photometry
frames and ~630 AGN spectroscopy nights per year).

| Data | Unit size (how known) | Now | Growth / year |
|---|---|---|---|
| SExtractor catalogues (`*_cat.fits`, 16 apertures) | Sinistro 87 kB, MuSCAT 30 kB (measured, 22,356 Mrk 817 catalogues, 12 apertures; +25 % for 16) | **55 GB** | 8 GB |
| Calibrated photometry (`measurements.parquet`, `frame_qc`) | 2.6 kB / frame (measured, Mrk 817) | 1.3 GB | 0.2 GB |
| Light curves, PyTICS solutions, plots | ~20 MB / AGN | 2 GB | small |
| Raw FLOYDS frames (science + arc + flat, and standards) | 2.5 MB / AGN-night, 1.9 MB / standard night (measured) | 20 GB | 3 GB |
| Reduced spectra (banzai-floyds, cleaned-up, 1-d + 2-d) | ~10 MB / night (measured) | **90 GB** | 16 GB |
| LCO archive databases | measured (0.7 GB) + full spectra headers | 2 GB | 0.3 GB |
| AVA database, backups, logs, Prefect DB | | 5 GB | 2 GB |
| Website data copy (`web.data_dir`: DB snapshot, plots, data releases) | | 5 GB | 1 GB |
| **Rolling buffer of photometry images** (daily) | 37.8 MB / Sinistro frame (measured, 98 files); ~200 frames / day; 7-day retention | 55 GB | — |
| **Total (persistent)** | | **~0.24 TB** | **~30 GB** |

**Recommendation**

- **Data volume: 1 TB** (ext4 or XFS), mounted for example at `/srv/ava`, holding `paths.archive_root`,
  the databases and the website data. This leaves room for 10+ years of growth and for keeping the 2-d
  spectra.
- **Scratch volume for the one-off backfill: 0.5–1 TB** (section 9). The historical photometry has to be
  downloaded once to build the catalogues: 498k frames × 38 MB ≈ **18.9 TB of transfer**, processed in
  batches (download → catalogue → calibrate → delete). A 0.5 TB scratch volume holds ~13,000 frames per
  batch. It can be released after the backfill.
- **Backups:** off-VM copies of the databases, catalogues and reduced spectra (~0.25 TB; section 10).
- For reference, keeping every photometry image instead would need **~19 TB now + ~2.7 TB/year**.

Uncertain unit sizes (factor ~1.5): MuSCAT, old-Sinistro and Spectral image sizes (only Sinistro
measured), reduced standard stars, and the effect of 16 apertures on catalogue size. They do not change
the recommendation.

## 3.2 CPU, memory, network

| Resource | Recommendation | Basis |
|---|---|---|
| vCPU | 8 (16 during backfill) | calibration 190 ms/frame/CPU (21,573 Mrk 817 frames in 13 min on 6 workers); banzai-floyds `workers: 4`; `pipeline.n_cores` targets in parallel |
| RAM | 32 GB | calibration peak 0.94 GB (6 workers, Mrk 817); banzai-floyds (PyTorch) several GB per worker — **CHECK** |
| GPU | not needed | banzai-floyds runs PyTorch on CPU |
| Network | outbound HTTPS only (list in section 5.3); ≥ 1 Gbit/s for the backfill | |

Daily volumes are small: ~200 photometry frames (~8 GB) and ~2 spectroscopy nights per day.

# 4. Software

## 4.1 Operating-system packages

| Package | Why | Notes |
|---|---|---|
| `git` | code deployment, banzai-floyds fork | |
| `sqlite3` (CLI, ≥ 3.35) | inspection, scripts | databases are SQLite files (WAL mode) |
| `source-extractor` (SExtractor 2.25+) | catalogues (`-e` step) | Ubuntu package `source-extractor`; the binary is `source-extractor`, so set `photometry.sextractor.binary: "source-extractor"` (default `sex`) |
| `cron` (or systemd timers) | scheduling | section 7 |
| Apache 2.4 + PHP 8.1+ with `pdo_sqlite` | website (`web/`) | `.htaccess` files are used (`AllowOverride`) |
| build tools (`build-essential`), `curl` | some pip wheels; health checks | |
| Miniforge / conda (or `uv`) | the two Python environments | |
| TeX Live (optional) | only to rebuild the manuals / this PDF | not needed to run the pipeline |

## 4.2 AVA Python environment

- **Python 3.12** (`environment.yml`; `pyproject.toml` requires ≥ 3.10). Install with
  `conda env create -f environment.yml` then `pip install -e ".[pipeline]"`.
- Versions the test suite last passed with (Nov 2026; pin these in production):

| Package | Version | Package | Version |
|---|---|---|---|
| prefect | 3.9.3 | numpy | 2.4.6 |
| astropy | 8.0.2 | scipy | 1.17.1 |
| astroquery | 0.4.11 | pandas | 3.1.1 |
| pyarrow | 26.0.1 | numba | 0.68.1 |
| astroalign | 2.6.2 | scikit-image | 0.26.0 |
| matplotlib | 3.11.2 | requests | 2.34.2 |
| PyYAML | 6.0.3 | click | 8.5.1 |
| SQLAlchemy | 2.1.8 | | |

- `environment.yml` / `pyproject.toml` (fixed 16 Nov 2026): Prefect 3, conda-forge only, the packages the
  code imports (incl. `lmfit`, `pillow`), banzai-floyds and the unused Flask/web extra removed, and a valid
  build backend (`pip install -e .` failed before). Generate a lock file (`conda env export`) from the
  production environment once it passes `scripts/check_install.py --tests`.
- **`scripts/check_install.py`** checks a machine: package versions, config paths, LCO token, databases,
  the SExtractor binary and a SExtractor test run with the AVA configuration, banzai-floyds, and (`--tests`)
  the offline test suite.
- Matplotlib uses the non-interactive `Agg` backend (set by the code); no display is needed.
- Tests: `PYTHONPATH=. pytest -q` (all offline; no archive access).

## 4.3 banzai-floyds environment (FLOYDS reduction)

- Fork: `https://github.com/Alymantara/banzai-floyds` (based on LCO's banzai-floyds; depends on
  `lco-banzai` 1.36.2 from GitHub, `torch`, `astroscrappy`, `scikit-image`, `scikit-learn`, `alembic`, …).
  Deploy a **fixed commit** (currently `0271697` on `rm-improvements`, 19 Nov 2026: five more flux standards,
  fringe templates that survive repeat runs, rejection of misidentified arc lines; was `3e8e796`). **Never
  `origin/main`:** it lacks `offline.py`, the shipped sky flats and ~8,100 lines of the fork. Clone, then
  `git checkout 0271697`. The version is
  recorded in every product. Install notes: the fork's `docs/INSTALL_RM.md`.
- Python 3.12, own environment (e.g. `/opt/ava/env-banzai`). The fork has a `Dockerfile` that can be
  used instead.
  On Linux: install CPU-only PyTorch first (`pip install torch --index-url https://download.pytorch.org/whl/cpu`),
  then `pip install -e ".[test]"`, from a clean shell (`env -i`, no `PYTHONPATH`).
- Data: the sky-flat order solutions of both FLOYDS sites ship with the fork since `11f8ce4` (`banzai_floyds/data/orders/skyflats/`,
  registered by `setup-db`); `spectroscopy.reduction.skyflats_dir` points at that folder.
- AVA calls it as an external process. The config template's defaults are the production layout, relative to
  the checkout: `paths.floyds_pipeline` and `spectroscopy.reduction.package` = `../banzai-floyds`, `.python` =
  `../miniforge3/envs/banzai/bin/python`, `.skyflats_dir` = the shipped sky flats. A machine with another
  layout sets them in its `data/config/ava_config.yaml` (`tools/make_config.py init --set ...`).
- **Flux standards (19 Nov 2026).** The fork has reference spectra for 12 standards
  (`banzai_floyds/data/standards/`). Set lcodb `standards.reference_dir` to that folder on each host. lcodb then
  matches science spectra only to those standards, within `standards.usable_radius_arcsec` (300″). A missing
  folder lifts the restriction, with a warning.
- **Arm for Hβ / 5100 Å.** `spectroscopy.products.hbeta_arm` (`auto`, `blue` or `red`). `auto` uses the red arm
  above `hbeta_red_arm_above_z` (0.09), one arm per target.
- **Repeat reductions** in the same work folder need the fork with `keep_template_free` (19 Nov 2026). It keeps
  `*-notpl` copies of the standards in the processed tree; do not delete them.

# 5. Configuration, secrets and network

## 5.1 Configuration files

| File | Role |
|---|---|
| `config/ava_config.yaml` | every pipeline path and tunable (`AVA_CONFIG` env var points to another copy) |
| `config/lcodb_config.yaml` | LCO archive databases: location (`db_dir`), proposals, rate limits (`LCODB_CONFIG` overrides) |
| `config/targets.yaml`, `data/reference/` | reference copies and fixed inputs (SExtractor configs, filter dictionary) |

Settings to change for production (all in `config/ava_config.yaml` unless noted):

| Setting | Development value | Production |
|---|---|---|
| `paths.archive_root` | `data/test_archive` | the data volume, e.g. `/srv/ava/archive` |
| `paths.database` | `data/ava.db` | on the data volume |
| `db_dir` (lcodb config) | `data/lcodb` | on the data volume |
| `download.mode` | `dry_run` | `live` |
| `download.daily_proposals` | `[KEY2026B-007]` | the active AVA proposals |
| `spectroscopy.download.mode` | `dry_run` | `live` |
| `spectroscopy.download.archive_products` | test archive: `true` | `false` |
| `spectroscopy.reduction.*`, `paths.floyds_pipeline` | `/Users/juan/...` | section 4.3 |
| `photometry.sextractor.binary` | `sex` | `source-extractor` |
| `pipeline.n_cores` | | number of targets in parallel (≈ vCPU / 2) |
| `pipeline.prefect.*` | `schedule_cron: "30 10 * * *"` | section 7 |
| `web.data_dir` | | the website's data folder (section 8) |
| `lco_usage.snapshots.file` | `data/lco_usage/snapshots.csv` (the seed) | on the data volume, e.g. `/srv/ava/lco_usage/snapshots.csv` (section 7.5) |
| `releases.dir` | `releases` | on the data volume |

**Prefect** keeps its state in `PREFECT_HOME` (default `~/.prefect`). Put it on a local disk (e.g. the data
volume): on a network-mounted home the ephemeral API server times out at start. Set
`PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS=90` as well.

## 5.2 Secrets

- **LCO API token** only in `~/.lco_token` of the service user (`chmod 600`), or the `LCO_API_TOKEN` /
  `LCO_TOKEN` environment variable. Never in the repository or the config.
- No other credentials are needed (all other services are public).

## 5.3 Outbound network access

| Host | Used for |
|---|---|
| `archive-api.lco.global`, `observe.lco.global` | frame lists, headers, downloads (signed URLs to LCO's S3 storage — allow its download host); charged-time snapshots (job 6) |
| `cds.unistra.fr`, `vizier.cds.unistra.fr` (+ mirrors in `photometry.reference.vizier_servers`) | Gaia DR3 / GSPC reference stars, SIMBAD/Sesame names |
| `irsa.ipac.caltech.edu`, `ned.ipac.caltech.edu` | extinction, redshifts (when adding targets) |
| `catalogs.mast.stsci.edu`, SDSS SkyServer | Pan-STARRS / SDSS comparison photometry |
| `ui.adsabs.harvard.edu` | publications page (optional) |
| `github.com` | installation and updates (`git pull`; read only) |
| `pypi.org`, `conda.anaconda.org` | installation only |

**LCO rate limits:** the archive blocks clients for hours above ~4 requests/s. The code limits itself
(`download.rate_per_s: 1`, lcodb `header_rate_per_s: 4`, `sync_rate_per_s`). Do not raise these, and do
not run several archive jobs at the same time (the cron times in section 7 are spaced for that).

**What counts as an archive request (20 Nov 2026).** Only calls to `archive-api.lco.global`: listing pages,
frame details, headers. Image files come from signed S3 URLs handed out with each listing and do not count.
The photometry download searches a target only when the lcodb photometry DB (job 1, synced within
`download.lcodb_max_age_hours`, 24) lists a new frame of it (`download.lcodb_precheck: true`;
if lcodb is stale the target is searched as before), and the spectra download gets its URLs with one listing
per observing request instead of one request per file. A night costs about 15 photometry listings and 2 per
spectra night, rather than ~145 and ~11.
Listings use pages of 1000 frames (`download.page_size`, the archive maximum with a token), and the files are
fetched `download.parallel_fetches` (4) at a time from S3 (about 3x faster in the 20 Nov test; it adds no
archive request). Lower it to 1 if the host's network is shared with something that needs the bandwidth.

**Server errors stop a job (19 Nov 2026).** An HTTP 5xx is not treated as transient: one request is retried at
most `server_error_retries` times (default 1), and after `server_error_limit` consecutive failed requests
(default 3) the client sends nothing more and the step stops. The frames it had not reached stay pending for the
next run. The settings are in `lcodb_config.yaml` and in `download:` in `ava_config.yaml`.

**Headers: slit width only (19 Nov 2026).** The header step fetches one header per new FLOYDS exposure (about 8 a
day), keeps only `APERWID` (`headers.columns: [aperwid]`) and no longer stores full headers (`store_full: false`).
To delete full headers stored earlier (103 MB on the Mac copy), run `lcodb purge-headers` (a dry run that prints
the count), then `lcodb purge-headers --live`. That backs the database up to `<db_dir>/backups/` first, then
deletes the headers and VACUUMs.

# 6. Databases and data layout

| Database | Default location | Written by | Contents |
|---|---|---|---|
| `photometry.sqlite` | lcodb `db_dir` | `lcodb` (daily), calibrate step | every LCO imaging frame of the AVA proposals, links to AVA targets, `local_files`, **`frame_qc`** (per-frame QC and zero points) |
| `spectra.sqlite` | lcodb `db_dir` | `lcodb` (daily), spectroscopy steps | FLOYDS frames + headers, standard-star and arc/flat matches, spectral QC and line measurements |
| `state.sqlite` | lcodb `db_dir` | `lcodb` | proposal crawl state, run log |
| `ava.db` | `paths.database` | pipeline, `tools/` scripts | AGN targets (source of truth), derived properties, variability statistics, data releases, download state |

Files (under `paths.archive_root`): `photometry/<data_id>/` (catalogues `sextractor_ava/`,
`measurements.parquet`, light curves, `pytics/`, plots), `photometry/raw_data/<data_id>/YYYYMMDD/`
(temporary images), `spectroscopy/raw_data/…`, `spectroscopy/<data_id>/reduced/YYYYMMDD/` (kept),
`spectroscopy/banzai/` (reduction work folder), `releases/<DR>/`.

All writes to `ava.db` curated fields go through scripts in `tools/` that back the database up first.

## 6.1 Literature properties (on demand, not scheduled)

Published AGN properties (redshift, black-hole mass, rest-frame Hβ lag, L5100, AGN type, each with its ADS
bibcode) live in **`data/literature/`**. This folder is not in git (it is under `data/`), so copy it to the VM
with `ava.db`.

| File | Contents |
|---|---|
| `agn_properties.csv` | one row per AGN, the source of truth; empty cell = no published value |
| `references.csv` | bibcode → short citation ("Lu et al. (2021)") shown on the website |
| `mass_conflicts.csv` | campaigns whose masses disagree (> 0.3 dex), for review |
| `build/`, `cache/` | the scripts and cached NED/SIMBAD/Véron-Cetty/AGNmass/literature results that produce the CSV |

Rules used when building the CSV:
- **z** comes from NED.
- **Type** comes from Véron-Cetty & Véron (2010), else the literature.
- **Mass** comes from the newest Hβ reverberation campaign that reports one (`MASS_POLICY` and
  `MASS_CAMPAIGN` in `build/build_csv.py`). The AGN Black Hole Mass Database mean is kept in the notes.
- **Lag** comes from the newest well-sampled campaign.

Import, then recompute the derived properties, then publish:

```
python tools/import_literature.py --apply-to-agn            # dry run: lists every change
python tools/import_literature.py --apply-to-agn --write    # backup in backups/, then write
python tools/derive_agn_properties.py                       # agn_derived: L_bol, Eddington ratio, disc lags
python scripts/run_pipeline.py -w                           # or tools/publish_web.py: website copy
```

- `--write` upserts the CSV into the table **`agn_literature`**. A value removed from the CSV is removed from
  the table.
- `--apply-to-agn` also copies z, log M_BH, log L5100 and the type, with their citations, into the curated
  `agn` columns the website shows (`redshift`, `logm`, `l_5100`, `AGN_type` and their `*_cite` / `*_url`).
- It only writes where the CSV has a value, and never changes a non-AGN type (`XRB`).
- Use `--db` to run it on another database, e.g. the test archive: `--db data/test_archive/ava.db`.

**When new AGN are added:**
1. Append them to `cache/targets.csv`.
2. Re-run `build/match_agnmass.py` and `build/catalogs.py` (it resumes and only queries new targets).
3. Add the literature search results as a new `cache/lit/batch_<X>.json`.
4. Run `python build/build_csv.py .` in `data/literature/`.
5. Import as above.

The searches use NED, SIMBAD, VizieR (Harvard mirrors) and the ADS API; the ADS token is in
`~/.ads/dev_key` and is never printed.

**Identity fixes** to existing targets (position, `data_id` rename) are one-off migration tools, e.g.
`tools/db_migrate_20261117.py`. Each is a dry run by default; `--write` backs up first. A `data_id` rename
also updates the lcodb links (`frames.ava_data_id`, `target_link.ava_data_id`).

# 7. Scheduled jobs (production)

All times UTC. Run everything as one unprivileged service user (e.g. `ava`), with
`AVA_CONFIG` / `LCODB_CONFIG` set in the crontab and logs on the data volume.

| Time | Job | Exists? |
|---|---|---|
| 01:00 daily | **1. Update the LCO archive tables** — `scripts/lcodb_daily.sh` | yes |
| 02:00 daily | **2. Download** new photometry images and FLOYDS frames | yes (Prefect steps `-d`, `-D`) |
| after 2 | **3. Process and publish** — catalogues, calibration, PyTICS, spectra reduction and products, database updates, website | yes (Prefect steps) |
| 05:00 daily | **4. Delete raw frames AVA has finished with** (photometry images, FLOYDS nights) | yes (`scripts/cleanup.py`) |
| weekly | 5. Back up databases and products (section 10) | **TO BUILD** |
| 07:00 daily | **7. Health check**: did every job run and succeed (`scripts/daily_check.py`) | yes |
| every 6 h | **6. LCO time-usage plots** (website Live Updates page): snapshot of LCO's charged totals, plot, publish | yes (`scripts/lco_usage.py --live-snapshot`) |

## 7.0 Installing the schedule: test first, then production

`scripts/make_crontab.py` writes the crontab for the machine it runs on, with its own Python, repository,
`AVA_CONFIG` / `LCODB_CONFIG` (taken from the environment it is run in) and log folder (`paths.logs`). Every
line goes through `scripts/cron_job.sh`, which logs to `<logs>/<job>.log` and appends one line per run (job,
start, end, exit code) to `<logs>/cron_runs.tsv`. `scripts/daily_check.py` reads that record.

**1. Test (safe):** every job runs once, a few minutes apart, with nothing downloaded or deleted. `--check` first
runs a probe under `env -i` and the crontab's variables, exactly as cron will. It checks the LCO token from its
file, both configs, SExtractor, banzai-floyds, the writable log folder and `PREFECT_HOME`, and the pipeline imports.
Nothing is installed if it fails. `--run-now` instead runs every test job immediately, the same way, then the check.

```bash
python scripts/make_crontab.py --test --check --install
```

| Test job | What it runs |
|---|---|
| `lcodb_daily_test` | `lcodb daily`: the real incremental crawl, a few hundred listing requests at most. `--no-archive` swaps in `lcodb status` (no request). |
| `pipeline_test` | `run_pipeline.py --target <first active target>` with the nightly steps; `--download-mode dry_run --spec-mode dry_run` (search only); no publish (`--with-publish` adds it). |
| `cleanup_test` | `cleanup.py` in dry run. |
| `lco_usage_test` | `lco_usage.py` without the live snapshot, without publishing. |
| `daily_check_test` | `daily_check.py` for the four test jobs, 60 min after the first (`--check-after`). |

The pipeline test starts 15 min after the archive crawl (`--pipeline-after`; the crawl takes ~11 min and the two
never share the lcodb databases); the check runs an hour after the first job (`--check-after`). The command prints
when the jobs will run. Afterwards, read `<logs>/daily_check_test.log`: it ends in `PASSED`
or `FAILED`, and for a failed job it shows the end of that job's log. Each job's full output is in
`<logs>/<job>_test.log`. The test lines have a fixed day and month, so they do not repeat, but replace them
anyway.

**2. Production**, once the test passes:

```bash
python scripts/make_crontab.py --production --mailto <address> --install
```

This sets: 01:00 `lcodb_daily`, 02:00 `pipeline` (`run_pipeline.py` with `pipeline.prefect.nightly_steps`, all
targets), 05:00 `cleanup` (**dry run** until `--cleanup-live`: read the first nights' `cleanup.log`, then re-run
the command with `--cleanup-live`), every 6 h `lco_usage --live-snapshot`, and 07:00 `daily_check`.
- `daily_check` exits non-zero when a job did not run in time or failed, or when the archive tables are older
  than 30 h, so cron mails its output to `MAILTO`.
- **Run the machine in UTC** (`timedatectl`; `sudo timedatectl set-timezone UTC`): cron reads the times in the
  machine's zone and Debian's cron ignores `CRON_TZ`, so none is written; `make_crontab.py` warns otherwise.
- **Mail needs a mail server.** `MAILTO` only works if the machine can send mail. `mail` alone is not enough; the
  first VM had no `sendmail`. Install one, or a relay to the department's server (e.g. `msmtp-mta`), and test it
  with `echo test | mail -s "AVA test" <address>`.
- The crontab carries the jobs' whole environment: the Python, `AVA_CONFIG` / `LCODB_CONFIG`, `PREFECT_HOME` and
  the Prefect settings (`ava.utils.prefect_env`: analytics off, they locked Prefect's database), and `TMPDIR`.
  Cron jobs read the LCO token from its file: one lookup for the whole package (`ava.lco.token`): `$LCO_API_TOKEN`,
  then `lco.token_file`, then lcodb's `token_file`, then `~/.lco_token`. Both templates' `token_file` default to
  `<install root>/.secrets/lco_token`. Do not rely on an exported variable: cron has none (19 Nov: the pipeline
  failed under cron with the token only in `$LCO_TOKEN`). `check_install.py` checks the token as cron sees it.
- The `pipeline` line replaces the Prefect deployment of section 7.3; use one or the other.
- `--install` replaces only the block between the AVA markers in the user's crontab, and saves the previous
  crontab to `<logs>/crontab.before.<time>`. `--remove` takes the block out again.

Run the health check by hand at any time:

```bash
python scripts/daily_check.py
```

## 7.1 Job 1 — update the archive tables (01:00)

```
0 1 * * *  AVA_PYTHON=/opt/ava/env/bin/python /opt/ava/AVA/scripts/lcodb_daily.sh
```

`lcodb daily` runs, in order:

1. `sync` — new frames of the AVA proposals since the last run (per-proposal state in `state.sqlite`):
   BANZAI-calibrated imaging frames (reduction level 91) into `photometry.sqlite`, FLOYDS spectra, arcs,
   flats and standard stars (level 0 and 91) into `spectra.sqlite`; plus flux standards observed under any
   proposal and the FLOYDS calibration programmes;
2. `headers` — FITS headers of the new spectra, for one value: the **slit width** (`APERWID`), which the
   archive listing does not give and which the arc/flat and standard-star matching uses (same slit
   preferred). Nothing else from the headers is used: airmass is computed when missing, target linking works
   from the archive footprint and the name, and the photometry calibration reads its frame values from the
   images (or the catalogues; section 7.4). Photometry headers are switched off;
3. `airmass` — computed where the header has none;
4. `match` — for each science spectrum, its **flux standard star** and its arc and lamp flat;
5. `link` — LCO object names → AVA targets, and the "observing" flag (`agn.ava = 2`, data in the last 30
   days).
6. `stats` — the per-AGN LCO statistics in the AVA database (`agn_lco`: frames, visits, cadence, date spans,
   FLOYDS epochs) recomputed from the linked frames by `tools/ava_crossmatch.py`, after a backup to
   `data/backups/`. These are the frame and spectra counts shown on the website (after the next publish).

Run time today: ~11 minutes. Log: `<db_dir>/daily.log`.

**Header backlog (decided 16 Nov 2026): not fetched.** 14,058 spectra frames from 2014 to August 2021 have
no header. `config/lcodb_config.yaml` → `headers.spectra.since: "2021-09-01"` limits the header step to
newer frames (a few dozen a day), so no backlog is fetched; those old spectra are matched by observing block,
then nearest time. `tools/headers_backfill.sh` is no longer needed.

**What the crawl keeps (18 Nov 2026).**
- Imaging cameras: Sinistro (`fa`, `fl`), Spectral (`fs`), MuSCAT (`ep`), and SBIG (`kb`, 2014–16) on the
  1 m only.
- Imaging filters: u B V g r i z Y only (`photometry_filters`).
- Everything else that is listed but not stored is counted in `state.sqlite` `dropped_frames`, and `lcodb
  stats` reports it.
- **Request budget:** the LCO archive allows **5000 requests per day per user**, UI and API together. Every
  listing page, header and file download counts. The daily jobs use a few hundred at most; plan any
  backfill around this limit.

- `lcodb daily` looks for new frames only in the proposals the portal marks active whose id matches
  `daily.include_regex` in `lcodb_config.yaml` (now `'^KEY2026'`; extend it when a new key project starts), plus the
  standards sources. Older proposals are crawled on request: `lcodb sync --proposal ID`.

## 7.2 Job 2 — download (02:00)

**How the pipeline decides what to download** (checked in the code, 16 Nov 2026):

- **Photometry** (`ava/pipeline/tasks/download.py` → `ava/lco/download.py`): for each AVA target with a
  new frame in the lcodb photometry DB (`download.lcodb_precheck`; every target if lcodb is older than 24 h), the
  live LCO archive is searched (every LCO spelling of the name, `download.daily_proposals`, reduction level
  91, the configured filters), from the target's **last successful download date minus
  `overlap_days` (2)** to tomorrow (first run: the last 30 days). The date is kept in `ava.db`
  `download_state` and advances only after a run with no failures and no cap. A frame is downloaded
  **only if its file is not on disk** (`raw_data/<target>/YYYYMMDD/<file>`, non-empty; md5 optional). Each
  download is md5-checked and recorded in `local_files` (lcodb photometry DB).
  - Because images are deleted after processing (job 4), the file being absent does not mean the frame
    is new: both the daily download and the backfill (`scripts/download.py`) also **skip frames that already
    have a SExtractor catalogue** (reported as "already processed").
- **First spectra download on a fresh install:** `select: "new"` starts from the last successful download in
  `download_state`, which is empty on a new machine (the transferred databases have it cleared), so the first run
  finds no night. Name the nights (`run_pipeline.py -D --spec-nights YYYYMMDD,...`) or set `select: "oldest"`
  for the backfill; from then on "new" continues from there.
- **Spectroscopy** (`ava/pipeline/tasks/spec_download.py`): planned **offline from `spectra.sqlite`**
  (hence job 1 must run first): the new nights of each target (after the last successful run minus
  `overlap_days`), with each night's science spectra, arc and lamp flat, **and the night's flux standard
  with its own arc and flat**. Only missing files are fetched; their URLs come from one archive listing per
  observing request (`request_id`), not one request per file.

The processing steps check their own outputs: SExtractor skips frames that already have a catalogue;
calibration skips frames already in `frame_qc` with the current pipeline version; spectra reduction
processes new nights only.

## 7.3 Job 3 — process, calibrate, update databases, publish

Run as the Prefect deployment (`scripts/deploy.py`, schedule from `pipeline.prefect`). Steps (same
letters as `scripts/run_pipeline.py`):

| Step | Flag | Output |
|---|---|---|
| download photometry | `-d` | images in `raw_data/` |
| SExtractor | `-e` | `*_cat.fits` |
| calibrate | `-c` | `frame_qc` (QC quantities), `measurements.parquet`, AGN light curve |
| PyTICS ensemble (incremental) | `-t` | merged light curve, per-band variability in `ava.db` |
| web plots | `-p` | light-curve and diagnostic figures |
| download spectra | `-D` | raw FLOYDS + standards |
| reduce spectra | `-R` | banzai-floyds 1-d/2-d products, `spec_qc` |
| spectroscopy products | `-P` | Hβ / [O III] fits, line light curves, mean/RMS spectra, variability in `ava.db` |
| publish | `-w` | derived properties, observing flag, website data copy, public data releases |

PyTICS absolute zero point (`-t`): anchored to Gaia GSPC stars, which exist only for G of about 14.2 and fainter in u g r i z y.
Since 19 Nov 2026 the fit uses every star in the frames, not only the comparison stars
(`ensemble.absolute_all_stars`, `absolute_min_coverage`, `absolute_max_scatter`, `absolute_trend_degree`).
Without it, dense fields and Y had no usable anchors. After upgrading, run a full PyTICS refit
(`--pytics-full`) once, so every target's zero point is recomputed.

Saturated AGN (19 Nov 2026): calibration stores the AGN's peak counts (`frame_qc.agn_peak`), and frame QC flags
`agn_saturated` above `photometry.qc.max_agn_peak_frac` (0.8) × the frame's saturation level. Frames without
their image take that level from `photometry.calibration.camera_defaults`, which now includes MuSCAT (`ep`).
Existing frames need a recalibration (`-c`) to get `agn_peak`.

Error bars (19 Nov 2026): the products use the fitted error model by default (`ensemble.error_model: fitted`,
`ava/photometry/errors.py`). It always includes a floor: `ensemble.error_model_default` (k 1.07, β 0.11,
s0 1.1 mmag) where a fit is not possible, and `ensemble.error_model_min_floor` (1 mmag). Evidence:
`docs/reports/pytics_update/pair_test_all_agn.md`.

PyTICS products per target (`-t`; `ensemble.export_csv`, `ensemble.export_qc_csv`):
- `<target>_LCO_merged_lightcurve.csv`: the **shareable** light curve, published as a download. It has a `#`
  header describing every column; read it with `comment="#"`. Columns: target, MJD, filter, telescope, camera,
  flux_mJy, flux_err_mJy, mag_AB, mag_AB_err (total per-epoch errors), zp_err_mag (the band's zero-point
  uncertainty, a systematic common to all epochs and not added to the per-epoch errors), frame.
- `<target>_LCO_merged_lightcurve_qc.csv`: **not published**. Every epoch, good or not, with the QC terms:
  random (epoch-to-epoch) errors, rms_t, rms_sc, n_stars, ensemble offsets, intercal a/b, airmass and seeing.
  F_var with `ensemble.fvar_error: random` and the spectroscopy g-band comparison read the random errors from here.

Production `nightly_steps` (set 19 Nov 2026): `download_data, extract, calibrate_data, pytics, plot,
spec_download_data, spec_reduce_data, spec_products_data, publish`, at 02:00 UTC (`schedule_cron`, and the
`pipeline` line of `scripts/make_crontab.py --production`). The spectra reduction (`-R`) needs the banzai-floyds
environment (`spectroscopy.reduction.python`, section 4.3) on the machine, or the run fails. Download and processing can be split
into two deployments (02:00 and 03:00) if preferred; the single flow already runs them in order.

```
prefect server start                      # or Prefect Cloud
prefect work-pool create ava-process --type process
python scripts/deploy.py --cron "0 2 * * *" -d -e -c -t -p -D -R -P -w
prefect worker start --pool ava-process   # as a systemd service
```

Run the Prefect server and worker as **systemd services** (restart on failure). Expected daily run time:
minutes (≈200 frames); **CHECK** on the VM.

## 7.4 Job 4 — delete raw frames AVA has finished with (05:00)

```
0 5 * * *  cd /opt/ava/AVA && /opt/ava/env/bin/python scripts/cleanup.py --live >> /srv/ava/logs/cleanup.log 2>&1
```

`scripts/cleanup.py` (`ava/archive/cleanup.py`; settings `cleanup:` in the AVA config) is a **dry run by
default**: it lists what it would delete and, for everything kept, why. `--live` (or `cleanup.mode: live`)
deletes. A file is deleted only when all its checks pass:

| Raw data | Deleted when |
|---|---|
| Photometry image `raw_data/<target>/YYYYMMDD/<frame>.fits.fz` | its SExtractor catalogue exists; the frame has a `frame_qc` row at the current calibration version (calibrated; QC, AGN measurement and the image's header values stored); file older than `retention_days` |
| FLOYDS night `raw_data/<target>/YYYYMMDD/` (spectra, arcs, flats together) | every science spectrum has its reduced `-1d` and a `spec_qc` row, **and** is in the final products (`hbeta_fits.parquet`: line fits, light curves); all files older than `retention_days` |
| Standard-star night `raw_data/standards/YYYYMMDD/` | no target night that may need it is still on disk; every standard has a `spec_qc` row; older than `retention_days` |

- **Frame metadata outlives the image, in the database.** Every header value calibration needs (exposure
  time, mid-exposure time, filter, night, airmass, header seeing, site, and since 16 Nov 2026 `SATURATE` and
  the image size) is stored in the frame's `frame_qc` row when it is first calibrated. Calibration reads the
  image when it is on disk, otherwise `frame_qc`, so a later recalibration needs no image. Rows written
  before `saturate`/`naxis1`/`naxis2` existed are completed from the image just before it is deleted.
- Catalogues, reduced spectra and products are never deleted. Each deleted file is marked in the lcodb
  `local_files` table (`deleted_utc`; path and md5 kept).
- `retention_days` (default 7) must be longer than the downloads' `overlap_days`; the job refuses to run
  otherwise.
- A re-reduction of old spectra or a re-extraction of old images needs a new download (spectra ~2.5 MB per
  night). **Do the MuSCAT re-extraction with the larger apertures during the backfill**, before the MuSCAT
  images are deleted.

## 7.5 Job 6 — LCO time-usage plots (every 6 hours)

```
0 */6 * * *  cd /opt/ava/AVA && /opt/ava/env/bin/python scripts/lco_usage.py --live-snapshot >> /srv/ava/logs/lco_usage.log 2>&1
```

`scripts/lco_usage.py` (`ava/lco/usage.py`, settings `lco_usage:` in the AVA config; port of the legacy
`ava_lco_update.py`) does three things on each run (~15 s):

1. **Snapshot** (`--live-snapshot`): **one read-only request** to the observation portal (`GET /api/proposals/`,
   paged; token from `~/.lco_token`). It appends every `KEY*` proposal's charged and allocated hours per
   semester and instrument class to the snapshot log (`lco_usage.snapshots.file`). To keep the log small, each run writes the
   rows of the semester in progress, plus any other row that changed (late charges, refunds).
2. **Curves**: the change between two snapshots is the time LCO charged in those 6 hours, overheads included.
   Before a curve's first snapshot, and after its last, the daily curve is **estimated** from the lcodb
   databases (`lco_usage.estimate_from_lcodb`; read only). Each day is weighted by an overhead model fitted
   every run (charged ≈ a·exposure hours + b·exposures + c·blocks per instrument class, semesters since 2020B;
   `lco_usage.overheads`; fit in `data/lco_usage/estimated/overheads.txt`), then scaled so the curve meets the
   charged totals. scipy is needed (already in the environment). Allocations come from the latest snapshot, so a new semester needs no
   manual update.
3. **Plot and publish**: `lco_usage_<semester>.png` for the current semester: hours charged so far per
   instrument class (1-m, 2-m FLOYDS, 2-m MuSCAT3, and the key project's filler programmes), as a percentage of
   the allocation, against an even pace. Changed plots are copied to `<web.data_dir>/usage/` on every run
   (`lco_usage.publish`) for the Live Updates page. The `-w` publish step also copies them (`web.usage_src`).
   `--all` redraws every semester (once, after installing).

- **The snapshot log lives on the VM, not in git.** `data/lco_usage/snapshots.csv` in the repository is only
  the **seed**: the totals the LCO usage report fetched on 14 Nov 2026 (22:38 UTC; the same numbers as
  `allocations.json`). In the production config set `lco_usage.snapshots.file` to a path on the data volume,
  outside the checkout (e.g. `/srv/ava/lco_usage/snapshots.csv`). The first live snapshot copies the seed
  there, and from then on the log grows on the VM only. It is **not pushed back to GitHub**, so after deployment
  the VM's log and the repository's seed diverge. That is expected: because the live log is outside the
  checkout, `git pull` never touches it and never conflicts. Back it up with the other data (section 10). To
  look at it elsewhere, copy it from the VM (`scp`). **Append only on the VM:** do not run `--live-snapshot`
  on other machines (they run in dry run and only log the request they would make), and do not edit the log
  by hand. (If the setting is left at the repository path, the job would append to the tracked seed, and
  `git pull` would then fail on a modified file.)
- **Dry run elsewhere.** `lco_usage.snapshots.mode` stays `dry_run` in the repository's config; only the
  production cron line passes `--live-snapshot`. The request is a single paged GET and does not compete
  with the archive jobs' rate limits.
- **New semester:** the job always draws the current semester, so the first run after 1 Feb / 1 Aug (00:00 UT)
  starts the new plot. During the first `finalise_days` (7) it also redraws the previous semester, which picks
  up its last charges, and then leaves it. The website lists the semesters itself (`web/includes/live.php`).
- **Format of the log and of optional per-proposal usage files:** `data/lco_usage/README.md`.
  `allocations.json` (the report's numbers) is only a fallback for semesters with no snapshot.

# 8. Website

- `web/` is plain PHP (no framework) reading **a copy** of the data: the publish step (`-w`) writes a
  snapshot of `ava.db`, the plots and the public data-release files to `web.data_dir`
  (`ava/web/publish.py`, `ava/web/releases.py`).
- Apache virtual host with `DocumentRoot` = `web/`; set `AVA_WEB_DATA` (data folder) and
  `AVA_WEB_DATA_URL` (its public URL) as environment variables (`SetEnv`), and `AllowOverride` for the
  `.htaccess` files (data releases: downloads allowed, no directory listings).
- The web server only needs read access to `web.data_dir`; the pipeline user writes it.
- HTTPS certificate (e.g. Let's Encrypt), and the university domain / DNS — **to arrange**.
- The website can run on the same VM or another host that receives `web.data_dir` (e.g. `rsync`).
- **Photometric calibration page** (`web/calibration.php`, linked from the Data page; breadcrumb Data ›
  Photometric calibration). It reads `<web.data_dir>/calibration/calibration.json`, which the `-w` publish step
  copies from `web.calibration_src` (default `data/products/calibration/calibration.json`). The page shows
  only its static text until that file exists. Build or refresh the file **on demand** (not scheduled) after
  new FLOYDS spectra are reduced, in the `stenv`-style environment (pandas + pyarrow + astropy + scipy) with
  the synphot data tree for the Pickles library:

  ```
  export PYSYN_CDBS=/path/to/synphot/trds
  python tools/abscal_validation/agn_sed_corrections.py --out <work>      # every target with reduced spectra
  python tools/abscal_validation/abscal_ps1_apass.py <work>/ext          # star table (one ESA Gaia-archive query)
  python tools/abscal_validation/export_web.py --sed <work> --ext <work>/ext
  python scripts/run_pipeline.py -w                                      # or tools/publish_web.py
  ```

  The technical report `docs/reports/report_abscal.pdf` is in `web.manuals` and is linked from the page.

# 9. First-time setup and backfill

Step-by-step commands (for a Linux machine already running the old pipeline): **`docs/guides/linux_setup.md`**.
For the production VM (fresh install), tick through **`docs/guides/production_vm_checklist.md`**, which builds in the
lessons of the Linux test day (18 Nov 2026).
In short:

1. conda environment, configuration outside the repository (`AVA_CONFIG`, `LCODB_CONFIG`), LCO token,
   `scripts/check_install.py --tests`;
2. copy `ava.db` and the lcodb databases from the development machine (`sqlite3 .backup`, then `scp`;
   step 7 of `linux_setup.md` lists every file with its source and destination path). They are not in git:
   `ava.db` because the pipeline writes to it, and the lcodb databases (440 + 250 MB) because they exceed
   GitHub's file limit. The small reference files (`data/reference/`, `data/literature/*.csv`,
   `data/ava/ava.csv`, `data/ava/ava_link_overrides.csv`) are in git. Then run `lcodb daily`;
3. `run_pipeline.py -o -O` — folders and Gaia reference stars for every `lco_active` target;
4. **`tools/port_legacy.py`** — copies the old pipeline's SExtractor catalogues and raw FLOYDS frames into
   the new layout, placing each file by its frame name through the lcodb databases (old folder names differ
   from the new `data_id`s); dry run by default;
5. **`tools/backfill_status.py`** — per target: frames still to download / extract / calibrate, spectra to
   download / reduce, and (`--apertures N`) the aperture series of the catalogues;
6. `run_pipeline.py -c` on the ported catalogues: they have no images, so frame metadata comes from the
   archive listing (lcodb) plus `photometry.calibration.camera_defaults` (saturation level, image size; the
   listing time is ~12 s later than the header `MJD-OBS`, negligible);
7. backfill the rest in batches (`scripts/download.py ... --live`, then `-e -c`), spectra with `-D`
   (`select: oldest`), then `-t -p -R -P -w`, and only then the daily jobs and the clean-up.

Download volume: 498k photometry frames × 38 MB ≈ 18.9 TB if nothing were ported; the legacy catalogues
(80–90 % of the photometry) cut this to the remaining 10–20 %. The archive rate limit is shared with the old
pipeline while both run: schedule the backfill away from its downloads.

# 10. Backups and monitoring

- **Back up:** `ava.db` (before every curated change the tools already make a copy in `backups/`), the
  lcodb databases, the catalogues, `measurements.parquet`/`frame_qc`, reduced spectra, `releases/`.
  Use SQLite's online backup (`sqlite3 db ".backup file"`), not a file copy of a database in use. Weekly
  off-VM copy (~0.25 TB), daily for the databases.
- **Monitor:** non-zero exit of the cron jobs (mail or alerting), Prefect failed flow runs,
  `<db_dir>/daily.log`, free space on the data volume (alert at 80 %), LCO HTTP 429 messages
  (archive throttling), age of the newest frame per active target.

# 11. Open items

| Item | Section |
|---|---|
| Switch `cleanup.mode` to `live` once the first production runs are checked | 7.4 |
| MuSCAT re-extraction during the backfill (before images are deleted) | 7.4, 9 |
| `camera_defaults` for MuSCAT (ep) and Spectral (fs): SATURATE / NAXIS from one of their images | 9 |
| Remove `/Users/juan/...` paths from the config | 4.3, 5.1 |
| Backup job | 10 |
| Measure SExtractor time, banzai-floyds memory, and daily run time on the VM | 3.2, 7.3 |
| Website hosting, domain and HTTPS | 8 |
| LCO usage snapshots: set `lco_usage.snapshots.file` on the data volume; check the first live snapshot against the report | 5.1, 7.5 |
