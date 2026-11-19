# Linux test day: hand-over for Claude on the Linux host (18 Nov 2026)

You are helping the user set up and test the **new** AVA pipeline on this Linux machine, side by side with the
old pipeline (which keeps running). Read `CLAUDE.md` first, then `docs/guides/linux_setup.md` (steps 1–17): it is
the procedure. Work through it with the user one step at a time; run a command only after saying what it does.
Ask before anything that contacts the LCO archive.

If the guide is wrong or unclear on this machine, fix `docs/guides/linux_setup.md`, rebuild its PDF if pandoc and
xelatex are available here (otherwise say so), record the decision in `docs/notes/future_improvements.md`, and
tell the user. Commit only when asked.

## Decisions already made

- **Isolated test.** AVA writes only under `/data2/jvhs1/AVA/data`. `/data3/jvhs1/agn` and `/data2/jvhs1/agn` are
  only read (copied, never moved).
- **One folder (decided 18 Nov, on the host).** Code in `/data2/jvhs1/AVA` (not `~/code/AVA`), data in
  `/data2/jvhs1/AVA/data` (not `/data3/jvhs1/ava`). Read the guide with those two substitutions.
- **Miniforge on the local disk (decided 18 Nov, on the host).** Home (`~`) is a CIFS network share: slow and
  case-insensitive. Miniforge is in `/data2/jvhs1/miniforge3`; read `~/miniforge3` in the guide as that path. The
  `ava` environment's Python is `/data2/jvhs1/miniforge3/envs/ava/bin/python`.
- **Old Anaconda.** Do not update or install into its `base`. Use plan B of step 5 (Miniforge in `~/miniforge3`,
  no `conda init`), or plan C (venv) if GitHub downloads fail. `~/.bashrc` gets the `ava-env` alias, not
  auto-activation.
- **Legacy catalogues and spectra.** `tools/port_legacy.py` with **real copies** (no `--link`; there are several TB
  free). Dry run first, show the user the summary and `port_legacy_not_placed.csv`, then `--write`.
- **Clean-up** (`scripts/cleanup.py`) stays a dry run: downloaded images are kept until the pipeline is trusted.
- **One LCO account for both pipelines.** Backfill downloads (step 15) only while the old pipeline is not
  downloading. Before each download batch, re-run `port_legacy.py --write` (it copies only new catalogues), so
  frames the old pipeline already extracted are not downloaded again.
- **No cron jobs today** (step 17 after the backfill).

## Plan for the day

1. Install, guide steps 1–9. Done when `python scripts/check_install.py --tests` ends with `READY: 0 FAIL`.
   Step 7 (copying `ava.db`, `photometry.sqlite`, `spectra.sqlite`, `state.sqlite`) is done **from the Mac** by the
   user; check the result with the commands in step 7d.
2. Bring the archive up to date, steps 10–11 (`python -m ava.lcodb daily`: listing requests only; then
   `run_pipeline.py -o -O`).
3. Port the old data, step 12 (dry run → review → `--write`).
4. Measure the gaps and calibrate, steps 13–14 (`tools/backfill_status.py --apertures 50 --csv ...`, then
   `run_pipeline.py -c`). Report the TOTAL lines and any target flagged "cannot be calibrated".
5. Fill the missing frames, step 15: agree the target order (Mrk_817 first), batch size (`--max-frames 2000`
   ≈ 76 GB) and download window with the user; one target at a time; repeat until `backfill_status` shows
   nothing left. Spectra with `run_pipeline.py -D`.
6. Process and publish, step 16 (`-t -p -P -w`; `-R` only once banzai-floyds is installed). Compare the Mrk 817
   light curve with the old pipeline's.

## State at hand-over

**The checklist is `docs/notes/linux_test_day_checklist.md`.** When a step finishes, tick it there (`[x]`) and add
a one-line note (what it printed, what was decided). Commit it only when the user asks.

Progress (updated 18 Nov 2026 15:25, end of the first Linux session; details in the checklist):

- **Layout:** code `/data2/jvhs1/AVA` (git checkout, `main`), data `/data2/jvhs1/AVA/data` (git-ignored), configs
  `data/config/{ava,lcodb}_config.yaml` (absolute paths), Miniforge `/data2/jvhs1/miniforge3` (env `ava`; env
  `banzai` = banzai-floyds `rm-improvements@3e8e796` in `/data2/jvhs1/banzai-floyds`, run via `/data2/jvhs1/benv`).
  Home (`~`) is a CIFS network share: keep environments, Prefect state and secrets off it.
  `~/.bashrc`: `ava-env` alias (clears `PYTHONPATH`), `AVA_CONFIG`, `LCODB_CONFIG`, `PREFECT_HOME`
  (`data/prefect`), `PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS=90`. A terminal opened before an edit
  needs `source ~/.bashrc`.
- **Done:** steps 1–10, 9b (banzai-floyds, tests pass), 12a–c (462,978 + 257 catalogues and 13,727 FLOYDS raw
  frames copied), 13 (40,943 frames / 1.51 TB and 6,371 spectra to download; re-run it, it predates the 257).
- **Step 11:** all 91 target folders. Reference catalogues: user wants **Gaia GSPC only** (`fallback: ""` on the
  host). CDS VizieR's query service was down (404) all afternoon; the CfA mirror's Gaia copies are incomplete in
  some fields (NGC 7469: 34 stars), so the ESA Gaia Archive was added (`gea.esac.esa.int` in `vizier_servers`,
  order CDS → ESA → CfA). Catalogues built from CfA are being moved aside (`*.cfa_bak`) and rebuilt from ESA;
  check each target's `reference_stars_meta.yaml` (`catalogue:` names the source). APASS catalogues kept as
  `*.apass_bak`.
- **Code changes today** (committed and pushed by the user unless noted): `lcodb daily` crawls only active
  proposals matching `daily.include_regex: '^KEY2026'`; SExtractor `default.param` 16 apertures; ESA Gaia
  fallback in `ava/photometry/reference.py`; deployment guide (banzai pin, Prefect, daily scope).
- **Next:** finish the ESA rebuild; step 14 (`-c`, test on Mrk_817 first); step 15 downloads (ask first, LCO);
  website test (needs PHP: `sudo apt install php-cli php-sqlite3`); move the LCO token off the network home;
  review the 3 `target_link` names flagged by `lcodb link`; fold the checklist's "Lessons" into `linux_setup.md`.
- Claude in this session can read/write files in `/data2/jvhs1/AVA` but cannot run commands on the host: the
  user runs them (and git).
