---
title: "AVA pipeline — setting up a Linux machine, step by step"
subtitle: "Fresh conda environment, databases, legacy data port and backfill (internal)"
date: "16 November 2026"
---

# Before you start

This guide sets up the **new** AVA pipeline on a Linux machine that already runs the old pipeline. The two run
side by side: the new pipeline uses its **own folders** and never writes into the old ones (it only reads
them, to copy the old catalogues and spectra).

**What you need**

- a terminal on the Linux machine (all commands are typed there, one block at a time, unless a step says
  "on the Mac");
- **SExtractor already installed** (it is, for the old pipeline; step 1 checks it);
- about **1 TB free** on the disk for the new archive (see `docs/guides/deployment_guide.md` §3.1), plus room for
  the photometry images that are downloaded before they are catalogued;
- your LCO API token (<https://observe.lco.global/accounts/profile/>);
- access to the Mac that holds the current databases (step 7).

**How to read the commands.** Type (or paste) each grey block into the terminal and press Enter. Lines starting
with `#` are comments. Wherever you see `/data3/jvhs1/ava`, use the folder you chose in step 4 if different.

**If something fails:** stop, copy the last ~20 lines of the terminal output, and ask.

# 1. Check SExtractor

```bash
source-extractor --version || sex --version
```

You should see a line like `SExtractor version 2.25.0`. Note **which name worked** (`source-extractor` or
`sex`): you need it in step 6.

If neither works, SExtractor is not on your `PATH`. Find it with `ls /usr/bin/sex* /usr/local/bin/sex*`, or
install it into the conda environment after step 5:
`conda install -n ava -c conda-forge astromatic-source-extractor` (the binary is then `source-extractor`).

# 2. Check conda

```bash
conda --version
```

What to do depends on the answer:

| `conda --version` says | Do this |
|---|---|
| `conda 23.10` or newer | Use it. Go to step 3 (step 5, plan A). |
| an older version (e.g. `conda 4.x`, `22.x`), or an Anaconda the old pipeline uses | Leave it alone and install Miniforge next to it (below), then use step 5, plan B. |
| `command not found` | Install Miniforge (below), then use step 5, plan B. |

**Do not update or add packages to the old Anaconda's `base`** (`conda update conda`, `conda install -n base ...`):
the old pipeline runs from it, and changing `base` can break it. A separate Miniforge keeps the two apart.

Install Miniforge (a small conda with the fast solver built in) into your home folder. It does **not** run
`conda init`, so your terminal and the old pipeline keep using the old conda; the new one is used only through
its own path:

```bash
cd ~
curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p ~/miniforge3
~/miniforge3/bin/conda --version
```

The last line should print `conda 2x.x`. If the machine cannot download from GitHub, use step 5, plan C.

# 3. Get the code

Choose where the code lives (here `~/code`), then download it from GitHub:

```bash
mkdir -p ~/code
cd ~/code
git clone https://github.com/Alymantara/AVA---AGN-Variability-Archive.git AVA
cd ~/code/AVA
```

Later, to get updates: `cd ~/code/AVA && git pull`.

# 4. Create the data folders

Choose a disk with ~1 TB free for the **new** archive. This guide uses `/data3/jvhs1/ava`. It must **not** be
one of the old pipeline's folders (`/data3/jvhs1/agn`, `/data2/jvhs1/agn`).

```bash
df -h /data3
mkdir -p /data3/jvhs1/ava/{archive,lcodb,config,logs,web,releases}
```

`df -h` shows the free space ("Avail") on that disk.

# 5. Create the Python environment

This takes 5–15 minutes the first time. Use **one** of the three plans, chosen in step 2. Each ends with
the same check: `python -c "import ava, prefect; print(prefect.__version__)"` prints `3.x`.

**Plan A: conda 23.10 or newer** (fast solver by default)

```bash
cd ~/code/AVA
conda env create -f environment.yml
conda activate ava
pip install -e .
```

The command that activates the environment is `conda activate ava`.

**Plan B: Miniforge in `~/miniforge3`** (old conda, or no conda)

```bash
cd ~/code/AVA
~/miniforge3/bin/conda env create -f environment.yml
source ~/miniforge3/bin/activate ava
pip install -e .
```

The command that activates the environment is `source ~/miniforge3/bin/activate ava`. It works whatever conda
the terminal already has, and touches nothing outside `~/miniforge3`. The environment's Python is
`~/miniforge3/envs/ava/bin/python` (used by the cron jobs in step 17).

**Plan C: no conda at all, a plain Python virtual environment** (if Miniforge cannot be downloaded).
Every dependency is on PyPI (`pyproject.toml`); this needs a system Python 3.10 or newer:

```bash
python3 --version
```

```bash
cd ~/code/AVA
python3 -m venv ~/venvs/ava
source ~/venvs/ava/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

The command that activates the environment is `source ~/venvs/ava/bin/activate`; its Python is
`~/venvs/ava/bin/python`. If `python3` is older than 3.10, look for a newer one (`ls /usr/bin/python3.1*`)
and use it in place of `python3`.

**If `conda env create` sits at "Solving environment" for more than ~5 minutes**, the conda in use is the old
one with the slow "classic" solver. Stop it with `Ctrl+C` and use plan B.

# 6. Configuration for this machine

Copy the two configuration files into the data folder (so `git pull` never overwrites your settings):

```bash
cp ~/code/AVA/config/ava_config.yaml /data3/jvhs1/ava/config/ava_config.yaml
cp ~/code/AVA/config/lcodb_config.yaml /data3/jvhs1/ava/config/lcodb_config.yaml
```

Tell AVA where they are, every time a terminal opens. This also adds a short command, `ava-env`, that
activates the AVA environment. The environment is **not** activated automatically, so a terminal used for the
old pipeline keeps its usual Python. Type `ava-env` in a terminal before running AVA commands.

Use the line for the plan you followed in step 5 (here plan B; for plan A write
`alias ava-env='conda activate ava'`, for plan C `alias ava-env='source ~/venvs/ava/bin/activate'`):

```bash
cat >> ~/.bashrc <<'EOF'
# --- AVA pipeline ---
alias ava-env='source ~/miniforge3/bin/activate ava'
export AVA_CONFIG=/data3/jvhs1/ava/config/ava_config.yaml
export LCODB_CONFIG=/data3/jvhs1/ava/config/lcodb_config.yaml
EOF
source ~/.bashrc
ava-env
```

The two `export` lines are harmless to the old pipeline: it does not read them.

Now edit the AVA configuration:

```bash
nano /data3/jvhs1/ava/config/ava_config.yaml
```

In `nano`, use the arrow keys to move, `Ctrl+W` to search, `Ctrl+O` then Enter to save, `Ctrl+X` to quit.
Change these lines (search for the text on the left; keep the indentation as it is):

| Search for | Set it to |
|---|---|
| `archive_root:` | `archive_root: "/data3/jvhs1/ava/archive"` |
| `database:` (under `paths:`) | `database: "/data3/jvhs1/ava/ava.db"` |
| `lcodb_config:` | `lcodb_config: "/data3/jvhs1/ava/config/lcodb_config.yaml"` |
| `binary: "sex"` | the name that worked in step 1, e.g. `binary: "source-extractor"` |
| `data_dir:` (under `web:`) | `data_dir: "/data3/jvhs1/ava/web"` |
| `dir: "releases"` (under `releases:`) | `dir: "/data3/jvhs1/ava/releases"` |
| `floyds_pipeline:`, and `python:`, `package:`, `skyflats_dir:` under `reduction:` | the banzai-floyds paths on this machine (see the deployment guide §4.3). Until banzai-floyds is installed, leave them: only the spectra **reduction** step needs them |

Leave `download.mode` and `spectroscopy.download.mode` at `"dry_run"` for now (nothing is downloaded until you
change them in step 12).

Then the archive-database configuration:

```bash
nano /data3/jvhs1/ava/config/lcodb_config.yaml
```

| Search for | Set it to |
|---|---|
| `db_dir:` | `db_dir: /data3/jvhs1/ava/lcodb` |

# 7. Copy the databases from the Mac

The databases are **not in GitHub**, so `git clone` (step 3) does not bring them. You have to take them
from the Mac and put them on the Linux machine yourself.

- `ava.db` is kept out on purpose: the pipeline writes to it.
- The two LCO archive databases are 440 MB and 250 MB, above GitHub's 100 MB file limit.

The small reference files (`data/reference/`, `data/literature/*.csv`, `data/ava/ava.csv`,
`data/ava/ava_link_overrides.csv`) **are** in GitHub and arrived with the clone.

## 7a. What to copy, and where it goes

| What | Size | Take it from (Mac) | Put it in (Linux) |
|------|------|--------------------|-------------------|
| AVA database (targets, properties, releases) | 0.4 MB | `/Users/juan/astro/AVA/data/ava.db` | `/data3/jvhs1/ava/ava.db` |
| LCO photometry frames | 440 MB | `/Users/juan/astro/AVA/data/lcodb/photometry.sqlite` | `/data3/jvhs1/ava/lcodb/photometry.sqlite` |
| LCO spectra frames | 250 MB | `/Users/juan/astro/AVA/data/lcodb/spectra.sqlite` | `/data3/jvhs1/ava/lcodb/spectra.sqlite` |
| LCO crawl state | 0.03 MB | `/Users/juan/astro/AVA/data/lcodb/state.sqlite` | `/data3/jvhs1/ava/lcodb/state.sqlite` |

The Linux paths are the ones the configuration points at (step 6): `paths.database` in `ava_config.yaml`
and `db_dir` in `lcodb_config.yaml`. If you chose other folders there, use those.

Do not copy the `-shm` / `-wal` files that sit next to the `.sqlite` files. Step 7b makes clean
single-file copies instead.

## 7b. Download: make clean copies on the Mac

Make sure nothing is running on the Mac first: no pipeline run, no `lcodb`, no `tools/` script.
Then open Terminal **on the Mac**:

```bash
cd /Users/juan/astro/AVA
```

```bash
mkdir -p ~/ava_dbs_transfer
```

```bash
sqlite3 data/ava.db ".backup $HOME/ava_dbs_transfer/ava.db"
```

```bash
for d in photometry spectra state; do sqlite3 data/lcodb/$d.sqlite ".backup $HOME/ava_dbs_transfer/$d.sqlite"; done
```

```bash
ls -lh ~/ava_dbs_transfer
```

You should see four files, about 0.4 MB, 440 MB, 250 MB and 0.03 MB.

## 7c. Upload: send them to the Linux machine

First, **on Linux**, make sure the target folders exist (step 4 already made them):

```bash
mkdir -p /data3/jvhs1/ava/lcodb
```

Then **on the Mac**, send the files. Replace `linux-machine` with the Linux machine's name or IP address,
the same one you use with `ssh`:

```bash
scp ~/ava_dbs_transfer/ava.db jvhs1@linux-machine:/data3/jvhs1/ava/ava.db
```

```bash
scp ~/ava_dbs_transfer/photometry.sqlite ~/ava_dbs_transfer/spectra.sqlite ~/ava_dbs_transfer/state.sqlite jvhs1@linux-machine:/data3/jvhs1/ava/lcodb/
```

If the Mac cannot reach the Linux machine directly (for example, it is only reachable from inside the
department network), do it in two hops:

1. Put the `~/ava_dbs_transfer` folder on a USB disk, or `scp` it to a machine that can reach the Linux
   machine.
2. From there, copy the files to the same Linux paths as in the table in 7a.

## 7d. Check on Linux

```bash
ls -lh /data3/jvhs1/ava/ava.db /data3/jvhs1/ava/lcodb/
```

```bash
sqlite3 /data3/jvhs1/ava/ava.db "SELECT COUNT(*) FROM agn"
```

The count should match the Mac's. Run `sqlite3 data/ava.db "SELECT COUNT(*) FROM agn"` there to compare.
Then delete the transfer copies **on the Mac**:

```bash
rm -r ~/ava_dbs_transfer
```

From this moment the **Linux copy is the one that matters**. Do not keep editing the Mac copies.

If you ever need to move them again, repeat 7b to 7d in the other direction, taking the copies on Linux
and sending them to the Mac. For example, after changing targets on the Mac before the switch-over, or
when moving to the production VM. Always use `.backup`, never a plain `cp` of a database that is in use.

# 8. LCO token

```bash
nano ~/.lco_token
```

Paste the token (only the token, one line), save (`Ctrl+O`, Enter) and quit (`Ctrl+X`). Then make it private:

```bash
chmod 600 ~/.lco_token
```

# 9. Check the installation

```bash
cd ~/code/AVA
python scripts/check_install.py --tests
```

Every line should say `OK`; the last line should be `READY: 0 FAIL`. `WARN` lines are fine for now (e.g.
banzai-floyds not installed yet, folders not created yet). The check also runs SExtractor on a small test
image with the AVA settings, and the offline test suite (~100 tests, no archive access). Fix any `FAIL`
before going on — the message says what is wrong.

# 10. Update the archive tables once

Brings the frame lists up to today (new frames since the Mac copy; a few minutes; listing requests only, no
image download):

```bash
cd ~/code/AVA
python -m ava.lcodb daily
```

# 11. Create every target's folders and reference stars

For every AGN in the database (73 with `lco_active = 1`), this creates the photometry and spectroscopy
folders and downloads the Gaia reference stars of each field (VizieR; a few minutes per target):

```bash
cd ~/code/AVA
python scripts/run_pipeline.py -o -O
```

Check that each target now has a reference catalogue:

```bash
ls /data3/jvhs1/ava/archive/photometry/*/reference_stars.csv | wc -l
```

# 12. Copy the old pipeline's catalogues and spectra

`tools/port_legacy.py` copies the old SExtractor catalogues (`/data3/jvhs1/agn/<folder>/sextractor_ava/`)
and raw FLOYDS frames (`/data2/jvhs1/agn/raw_data/<folder>_spec/` and `/data2/jvhs1/agn/all_standards/`)
into the new folders. It finds each file's target **from the frame name in the databases**, not from the old
folder name (old names like `1H1934-063` differ from the new `1H_1934-063`). The old folders are only read.

First a dry run (nothing copied) — it prints, per target, how many files it would copy and lists what it
cannot place:

```bash
cd ~/code/AVA
python tools/port_legacy.py --photo-root /data3/jvhs1/agn --spec-root /data2/jvhs1/agn
```

Look at the summary. Files "not placed" are listed in `port_legacy_not_placed.csv` (frames from proposals
the database does not cover, or not linked to an AVA target); they are not lost, just not copied. When it looks
right, copy:

```bash
python tools/port_legacy.py --photo-root /data3/jvhs1/agn --spec-root /data2/jvhs1/agn --write
```

If the old and new folders are on the **same disk**, add `--link` to make hard links instead of copies (no
extra space). Running it again later copies only what is new.

# 13. What is left to do

```bash
python tools/backfill_status.py --apertures 50 --csv /data3/jvhs1/ava/logs/backfill_status.csv
```

Per target: photometry frames in the database, catalogues already there, frames still to **download and
extract**, and the download size; FLOYDS spectra on disk, reduced, and still to download. `--apertures 50`
reads 50 catalogues per target and shows their aperture series: the calibration picks the science aperture
(10.5″) from each catalogue's own apertures (`APERDIAM` header, else the count: 10 = pre-2025 series, 12–16
= current series). A target flagged "cannot be calibrated" has catalogues with another aperture count — tell
the developers.

# 14. Calibrate the ported catalogues

The old catalogues have no images. Calibration takes their frame details (time, filter, exposure, airmass)
from the archive database and the saturation level / image size from
`photometry.calibration.camera_defaults` in the config (Sinistro filled in; MuSCAT and Spectral: copy
`SATURATE`, `NAXIS1`, `NAXIS2` from one of their images when you have one).

```bash
python scripts/run_pipeline.py -c
```

This is long the first time (~0.2 s per frame per core; `photometry.calibration.n_workers` cores per target,
`pipeline.n_cores` targets at once). It can be stopped and started again: it resumes where it stopped.

# 15. Download and extract the rest (backfill)

Only after steps 12–14, so nothing already catalogued is downloaded again. Switch downloading on:

```bash
nano /data3/jvhs1/ava/config/ava_config.yaml
```

Set `mode: "live"` under `download:` and under `spectroscopy:` → `download:`; for the spectra backfill also
set `select: "oldest"` there (back to `"new"` when the backfill is done).

Photometry, one target at a time, in batches (each run downloads at most `--max-frames` images; frames that
already have a catalogue are skipped):

```bash
python scripts/download.py --target Mrk_817 --kind phot --live --max-frames 2000 --yes
python scripts/run_pipeline.py -e -c --target Mrk_817
```

Repeat until `tools/backfill_status.py --target Mrk_817` shows nothing left to download. Images take ~38 MB
each: watch the free space with `df -h /data3`. Once images are catalogued and calibrated, the clean-up
(step 17) deletes them.

Spectra (all targets; repeat until nothing is left — each run fetches up to `max_frames_per_run` files):

```bash
python scripts/run_pipeline.py -D
```

**The old pipeline is still running.** Both pipelines use the LCO archive, which blocks clients for hours above
~4 requests per second. Run the backfill when the old pipeline is not downloading (e.g. during the day if the
old one runs at night).

# 16. Process and publish

```bash
python scripts/run_pipeline.py -t -p -R -P -w
```

PyTICS ensemble (`-t`), web plots (`-p`), spectra reduction (`-R`, needs banzai-floyds) and products
(`-P`), website data (`-w`).

# 17. Daily jobs

When the backfill is done, switch on the daily jobs (`docs/guides/deployment_guide.md` §7): edit your crontab with
`crontab -e` and add (times UTC, adjust the paths):

```bash
0 1 * * *  AVA_CONFIG=/data3/jvhs1/ava/config/ava_config.yaml LCODB_CONFIG=/data3/jvhs1/ava/config/lcodb_config.yaml AVA_PYTHON=$HOME/miniforge3/envs/ava/bin/python $HOME/code/AVA/scripts/lcodb_daily.sh
0 2 * * *  cd $HOME/code/AVA && AVA_CONFIG=/data3/jvhs1/ava/config/ava_config.yaml LCODB_CONFIG=/data3/jvhs1/ava/config/lcodb_config.yaml $HOME/miniforge3/envs/ava/bin/python scripts/run_pipeline.py -d -e -c -t -p -D -R -P -w >> /data3/jvhs1/ava/logs/daily.log 2>&1
0 5 * * *  cd $HOME/code/AVA && AVA_CONFIG=/data3/jvhs1/ava/config/ava_config.yaml LCODB_CONFIG=/data3/jvhs1/ava/config/lcodb_config.yaml $HOME/miniforge3/envs/ava/bin/python scripts/cleanup.py >> /data3/jvhs1/ava/logs/cleanup.log 2>&1
```

Also add the LCO time-usage plots, every 6 hours (`deployment_guide.md` §7.5):

```bash
0 */6 * * *  cd $HOME/code/AVA && AVA_CONFIG=/data3/jvhs1/ava/config/ava_config.yaml $HOME/miniforge3/envs/ava/bin/python scripts/lco_usage.py --live-snapshot >> /data3/jvhs1/ava/logs/lco_usage.log 2>&1
```

Each run asks LCO once for the time charged so far, adds it to the snapshot log, draws the plot and copies it to
the website folder. Before switching it on, set in `/data3/jvhs1/ava/config/ava_config.yaml`:

```yaml
lco_usage:
  snapshots:
    file: "/data3/jvhs1/ava/lco_usage/snapshots.csv"
```

The log then lives outside `~/code/AVA`, so `git pull` never touches it. The first run copies the starting
log from the repository there; after that it only grows on this machine and is not sent back to GitHub.

(The lines above use the plan B Python, `$HOME/miniforge3/envs/ava/bin/python`. For plan A or C use the
Python of your environment: find it with `ava-env && which python`.) Set `spectroscopy.download.select` back to `"new"`. The clean-up
line is a **dry run** (it only reports) until you add `--live`; do that once its log looks right.

# Keeping up to date

```bash
ava-env
cd ~/code/AVA
git pull
pip install -e .
python scripts/check_install.py
```

After a `git pull`, new settings may have been added to `config/ava_config.yaml`; compare with your copy:

```bash
diff ~/code/AVA/config/ava_config.yaml /data3/jvhs1/ava/config/ava_config.yaml
```
