# Linux test day: checklist

Tick a step by changing `[ ]` to `[x]`, and add a short note under it (what it printed, what was decided).
Procedure: `docs/guides/linux_setup.md`. Decisions and context: `docs/notes/linux_test_day_handover.md`.
Steps tagged **LCO** contact the archive: run them only while the old pipeline is not downloading.

## Decisions for today

- Isolated test: AVA writes only under `/data3/jvhs1/ava`; `/data3/jvhs1/agn` and `/data2/jvhs1/agn` are only read.
- Real copies of the old catalogues (no `--link`; several TB free).
- Leave the old Anaconda alone: AVA lives in Miniforge (`~/miniforge3`), activated with `ava-env`.
- Clean-up stays a dry run; downloaded images are kept for now.
- Re-run `port_legacy.py --write` before each download batch, so nothing the old pipeline extracted is downloaded.
- No cron jobs today.

## 1 · Install (guide steps 1–9)

- [x] **1. Check SExtractor**
  - 2.25.0. Name for `binary:` in step 6: _to confirm_ (`command -v source-extractor sex`).
- [x] **2. Check conda**
  - `conda 23.1.0` → plan B (Miniforge beside it, no `conda init`).
- [ ] **2b. Install Miniforge** in `~/miniforge3`
  ```bash
  cd ~ && curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
  bash Miniforge3-Linux-x86_64.sh -b -p ~/miniforge3
  ~/miniforge3/bin/conda --version
  ```
- [ ] **3. Clone the code** into `~/code/AVA`
- [ ] **4. Create the data folders**
  ```bash
  mkdir -p /data3/jvhs1/ava/{archive,lcodb,config,logs,web,releases}
  ```
- [ ] **5. Python environment (plan B)**
  ```bash
  cd ~/code/AVA && ~/miniforge3/bin/conda env create -f environment.yml
  source ~/miniforge3/bin/activate ava && pip install -e .
  python -c "import ava, prefect; print(prefect.__version__)"
  ```
- [ ] **6. Config files, `AVA_CONFIG` / `LCODB_CONFIG`, `ava-env` alias**
  - Paths to `/data3/jvhs1/ava`, SExtractor name, `db_dir`. Download modes stay `"dry_run"`.
- [ ] **7. Copy the four databases from the Mac** (`sqlite3 .backup`, then `scp`; check the `agn` count)
- [ ] **8. LCO token** in `~/.lco_token` (`chmod 600`)
- [ ] **9. Install check: `READY: 0 FAIL`**
  ```bash
  cd ~/code/AVA && python scripts/check_install.py --tests
  ```

## 2 · Bring the archive up to date (steps 10–11)

- [ ] **10. Update the LCO archive tables** (LCO, listing requests only)
  ```bash
  python -m ava.lcodb daily
  ```
- [ ] **11. Target folders and Gaia reference stars**
  ```bash
  python scripts/run_pipeline.py -o -O
  ls /data3/jvhs1/ava/archive/photometry/*/reference_stars.csv | wc -l
  ```

## 3 · Copy the old catalogues and spectra (step 12)

- [ ] **12a. Dry run**
  ```bash
  python tools/port_legacy.py --photo-root /data3/jvhs1/agn --spec-root /data2/jvhs1/agn
  ```
- [ ] **12b. Review the summary and `port_legacy_not_placed.csv`**
- [ ] **12c. Copy**
  ```bash
  python tools/port_legacy.py --photo-root /data3/jvhs1/agn --spec-root /data2/jvhs1/agn --write
  ```

## 4 · Measure the gaps and calibrate (steps 13–14)

- [ ] **13. What is left** (note the TOTAL lines and any "cannot be calibrated" target)
  ```bash
  python tools/backfill_status.py --apertures 50 --csv /data3/jvhs1/ava/logs/backfill_status.csv
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
