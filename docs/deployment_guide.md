---
title: "AVA pipeline — deployment guide (internal)"
subtitle: "What a software engineering team needs to deploy and run the AGN Variability Archive pipeline"
date: "Started 16 November 2026 — living document"
---

# 1. Purpose and status

This is the **internal** reference for deploying the AVA pipeline (LCO photometry and FLOYDS spectroscopy →
calibrated light curves, spectral products → public website). It is kept up to date as deployment
requirements are found; the per-setting audit is in `docs/deployment_checklist.md` and the open science
work in `docs/future_improvements.md`.

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
  Deploy a **fixed commit** (currently `8897b99`); the version is recorded in every product.
- Python 3.12, own environment (e.g. `/opt/ava/env-banzai`). The fork has a `Dockerfile` that can be
  used instead.
- Data: the sky flats of both FLOYDS sites (`spectroscopy.reduction.skyflats_dir`), registered once.
- AVA calls it as an external process; configure `spectroscopy.reduction.python`, `.package`,
  `.skyflats_dir` and `paths.floyds_pipeline` (currently `/Users/juan/...` paths — **must change**).

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
| `releases.dir` | `releases` | on the data volume |

## 5.2 Secrets

- **LCO API token** only in `~/.lco_token` of the service user (`chmod 600`), or the `LCO_API_TOKEN` /
  `LCO_TOKEN` environment variable. Never in the repository or the config.
- No other credentials are needed (all other services are public).

## 5.3 Outbound network access

| Host | Used for |
|---|---|
| `archive-api.lco.global`, `observe.lco.global` | frame lists, headers, downloads (signed URLs to LCO's S3 storage — allow its download host) |
| `cds.unistra.fr`, `vizier.cds.unistra.fr` (+ mirrors in `photometry.reference.vizier_servers`) | Gaia DR3 / GSPC reference stars, SIMBAD/Sesame names |
| `irsa.ipac.caltech.edu`, `ned.ipac.caltech.edu` | extinction, redshifts (when adding targets) |
| `catalogs.mast.stsci.edu`, SDSS SkyServer | Pan-STARRS / SDSS comparison photometry |
| `ui.adsabs.harvard.edu` | publications page (optional) |
| `github.com`, `pypi.org`, `conda.anaconda.org` | installation only |

**LCO rate limits:** the archive blocks clients for hours above ~4 requests/s. The code limits itself
(`download.rate_per_s: 1`, lcodb `header_rate_per_s: 4`, `sync_rate_per_s`). Do not raise these, and do
not run several archive jobs at the same time (the cron times in section 7 are spaced for that).

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

## 7.2 Job 2 — download (02:00)

**How the pipeline decides what to download** (checked in the code, 16 Nov 2026):

- **Photometry** (`ava/pipeline/tasks/download.py` → `ava/lco/download.py`): for each AVA target, the
  live LCO archive is searched (every LCO spelling of the name, `download.daily_proposals`, reduction level
  91, the configured filters), from the target's **last successful download date minus
  `overlap_days` (2)** to tomorrow (first run: the last 30 days). The date is kept in `ava.db`
  `download_state` and advances only after a run with no failures and no cap. A frame is downloaded
  **only if its file is not on disk** (`raw_data/<target>/YYYYMMDD/<file>`, non-empty; md5 optional). Each
  download is md5-checked and recorded in `local_files` (lcodb photometry DB).
  - Because images are deleted after processing (job 4), the file being absent does not mean the frame
    is new: both the daily download and the backfill (`scripts/download.py`) also **skip frames that already
    have a SExtractor catalogue** (reported as "already processed").
- **Spectroscopy** (`ava/pipeline/tasks/spec_download.py`): planned **offline from `spectra.sqlite`**
  (hence job 1 must run first): the new nights of each target (after the last successful run minus
  `overlap_days`), with each night's science spectra, arc and lamp flat, **and the night's flux standard
  with its own arc and flat**. Only missing files are fetched (one URL request per file).

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

Production `nightly_steps` (to set): `download_data, extract, calibrate_data, pytics, plot,
spec_download_data, spec_reduce_data, spec_products_data, publish`. Download and processing can be split
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

# 9. First-time setup and backfill

Step-by-step commands (for a Linux machine already running the old pipeline): **`docs/linux_setup.md`**.
In short:

1. conda environment, configuration outside the repository (`AVA_CONFIG`, `LCODB_CONFIG`), LCO token,
   `scripts/check_install.py --tests`;
2. copy `ava.db` and the lcodb databases from the development machine (`sqlite3 .backup`, then `scp`; they
   are not in git: 440 + 250 MB, above GitHub's file limit), then `lcodb daily`;
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
