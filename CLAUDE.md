# AVA — notes for Claude

AVA (AGN Variability Archive): a Prefect 3 + SQLite pipeline for LCO photometry (SExtractor → calibration →
PyTICS ensemble) and FLOYDS spectra, plus the website (`web/`). Overview: `README.md`. Install and operation:
`docs/guides/linux_setup.md` (step by step), `docs/guides/deployment_guide.md`, `docs/guides/deployment_checklist.md`.
Running decisions and to-do list: `docs/notes/future_improvements.md`.

## LCO archive: be very careful

- The archive blocks clients for hours above ~4 requests/s and caps logged-in users at 5000 requests/day (UI + API,
  shared with the daily `lcodb` sync and all downloads). Stay far below that.
- Downloads are **dry run by default** (`download.mode: "dry_run"`, `--live` flags). Make live requests only when the
  user asks, scoped to the minimum; print the expected request count first; pause between batches of a sweep.
- A repeated HTTP 500 is not transient: do not retry in a loop.
- The token comes only from `~/.lco_token` or `LCO_API_TOKEN` / `LCO_TOKEN`. Never write it into a file, config or
  command line, and never write passwords anywhere.
- Test download and search code offline (the test suite blocks the network).

## Rules of work

- Every path and tunable comes from `config/ava_config.yaml` / `config/lcodb_config.yaml` (on a host, the copies
  pointed at by `AVA_CONFIG` / `LCODB_CONFIG`). Do not hard-code them.
- `ava.db` is the source of truth for targets ("DB is king"); curated fields change only through reviewed scripts in
  `tools/` with a backup first.
- Do a few things at a time; explain why a long job is needed before running it (prefer a subset first).
- When porting, follow the reasoning of the legacy scripts in `__old_pipeline__/` rather than redesigning.
- Never edit `.tex` files (the user writes the manuals). Markdown guides may be edited; rebuild a guide's PDF after
  changing it (pandoc + xelatex, with an fvextra `breaklines` header for code blocks).
- Record decisions in `docs/notes/future_improvements.md`; keep `docs/guides/deployment_guide.md` up to date with
  any new dependency, setting, job or path.
- Git: work on `main`, no branches. Commit or push only when asked. Checkouts may be shared with other sessions:
  stage only your own files.

## On the Linux host (runs the old pipeline too)

- The code is in `/data2/jvhs1/AVA`; the new pipeline writes only under its own data folder there
  (`/data2/jvhs1/AVA/data`, git-ignored). The old pipeline's folders
  (`/data3/jvhs1/agn`, `/data2/jvhs1/agn`) are read-only for AVA; `tools/port_legacy.py` only reads them.
- Leave the old Anaconda's `base` alone; AVA has its own environment (`ava-env` alias, guide steps 2, 5 and 6).
- Both pipelines share one LCO account: run AVA downloads only while the old pipeline is not downloading.
- `scripts/cleanup.py` stays a dry run unless the user asks for `--live`.
