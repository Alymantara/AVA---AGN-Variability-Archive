# LCO time usage — input files

Read by `scripts/lco_usage.py` (`ava/lco/usage.py`), which draws `lco_usage_<semester>.png` for the website's
Live Updates page every 6 hours. Settings: `lco_usage:` in `config/ava_config.yaml`.

| Path | What |
|---|---|
| `proposals/<PROPOSAL>.csv` | **Real** usage, one file per LCO proposal (to be provided). |
| `estimated/<PROPOSAL>.csv` | **Used now** (`lco_usage.estimate_from_lcodb: true`; `# estimated: true`). Rewritten every run from the lcodb databases: each day's exposure hours per proposal and instrument class (each exposure counted once; FLOYDS arcs and flats included), multiplied per semester by charged / exposure from `allocations.json`. So each semester ends at the charged total, and the in-progress semester keeps growing with the daily lcodb sync. `estimated/factors.txt` lists the factors (≈1.6 on the 1-m, ≈1.5 for FLOYDS since 2018B; before that the database is incomplete and the factors swing). Exposures in a semester where the proposal was charged nothing are dropped. Until 2018A the 2-m time, FLOYDS included, is charged as Spectral time. |
| `dummy/<PROPOSAL>.csv` | **DUMMY** files (`# dummy: true`): the semester totals spread over the days at random by `tools/make_lco_usage_dummy.py`. Kept as examples; not used. |
| `snapshots.csv` | **In git.** Append-only log of LCO's charged totals: `utc, mjd, proposal, semester, instrument, alloc, used` (hours). The first 81 rows are the totals the LCO usage report fetched on 14 Nov 2026 22:38 UTC (= `allocations.json`). The production job (`scripts/lco_usage.py --live-snapshot`, every 6 h; one read-only portal request) appends the semester in progress and any changed row; `scripts/push_lco_snapshots.sh` pushes it to GitHub daily. The change between two snapshots of a proposal, semester and class is the time charged in that window (overheads, failed blocks and refunds included). It replaces the estimate between a curve's first and last snapshot; the estimate before the first is rescaled to end at its total, and after the last it fills in. A charge recorded after its semester ended is drawn on the semester's last minute. Allocations come from the latest snapshot. Do not edit by hand; append only on the production VM. |
| `allocations.json` | Allocated and charged (`used`) hours per proposal, semester and instrument class (copied from the LCO usage report, `docs/reports/lco_usage/tables/allocations.json`, 16 Nov 2026). Sets the 100 % line and scales the estimates. Update it each semester. |
| `plots/` | Output: `lco_usage_<semester>.png`, copied to `<web.data_dir>/usage/` each run. |

## Per-proposal file format

CSV, one file per proposal, named `<PROPOSAL>.csv` (e.g. `KEY2026B-007.csv`):

```
# proposal: KEY2026B-007
# units: hours charged per row (not cumulative)
mjd,1M0-SCICAM-SINISTRO,2M0-FLOYDS-SCICAM,2M0-SCICAM-MUSCAT
61254.0,4.1030,0.0000,0.0000
61255.0,0.0000,1.0500,0.2500
```

- Optional `# key: value` lines at the top (metadata). `proposal` overrides the file name;
  `dummy: true` marks synthetic data (the plot is watermarked "DUMMY DATA", and `--publish` skips it).
- First column `mjd`: when the time was charged. Normally one row per UT day, the MJD of 00:00 UT.
  Rows need not be daily or sorted. Repeated MJDs are added together.
- Every other column is one **LCO instrument class**, as the observation portal names it in allocations:
  `1M0-SCICAM-SINISTRO`, `2M0-FLOYDS-SCICAM`, `2M0-SCICAM-MUSCAT`, `2M0-SCICAM-SPECTRAL` (2014–2018).
  Values: **hours charged in that row** (not cumulative), ≥ 0. Empty cells count as 0, and a class that is
  not used can be left out. Names are not case-sensitive.
- The filler programme of a key project (proposal ending in `f`, e.g. `KEY2026B-007f`) has its own file.
  It is drawn as its own curve, labelled "(filler)" (the legacy plot called it "2m-Floyds-New").

A file with a bad header, a non-numeric or out-of-range MJD (outside 50000–80000; a JD or a date is
rejected), or negative hours stops the run with an error naming the file.
