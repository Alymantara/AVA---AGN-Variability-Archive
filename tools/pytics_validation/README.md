Scripts behind `docs/pytics_report.md` (Nov 2026), kept for reproducibility. `<work>` is any scratch folder.

1. `make_subset.py gp 59945 60125 <work>/g2023.parquet` — PyTICS input subset from the test archive
2. `run_original.py <PyTICS clone> <work>/g2023.parquet <work>/orig_g2023 200` — the published PyTICS
   (github.com/Astroberta/PyTICS, commit 003bcbd); writes `_stars` / `_agn` parquet
3. `validate.py <work>/g2023.parquet <work>/orig_g2023` — port vs original
4. `incr.py <work>/incr` — incremental-update experiments A (last 60 d) and B (new camera)
5. `report_figs.py <work>` — figures in `docs/figures/pytics/` (after a full `ensemble` run)
