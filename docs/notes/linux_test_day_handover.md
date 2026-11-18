# Linux test day: hand-over for Claude on the Linux host (18 Nov 2026)

You are helping the user set up and test the **new** AVA pipeline on this Linux machine, side by side with the
old pipeline (which keeps running). Read `CLAUDE.md` first, then `docs/guides/linux_setup.md` (steps 1–17): it is
the procedure. Work through it with the user one step at a time; run a command only after saying what it does.
Ask before anything that contacts the LCO archive.

If the guide is wrong or unclear on this machine, fix `docs/guides/linux_setup.md`, rebuild its PDF if pandoc and
xelatex are available here (otherwise say so), record the decision in `docs/notes/future_improvements.md`, and
tell the user. Commit only when asked.

## Decisions already made

- **Isolated test.** AVA writes only under `/data3/jvhs1/ava`. `/data3/jvhs1/agn` and `/data2/jvhs1/agn` are only
  read.
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

Nothing has been run on Linux yet. The user expects an old conda (step 2 decides the plan). The user keeps a
tickable copy of this plan on a claude.ai page; you cannot update it from here, so tell the user which step
finished.
