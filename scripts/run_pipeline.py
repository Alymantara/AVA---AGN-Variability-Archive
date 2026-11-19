#!/usr/bin/env python
"""
AVA pipeline CLI — run the Prefect flows locally.

Same step flags as the legacy ``__old_pipeline__/ava_update.py``:

    python scripts/run_pipeline.py -dec              # download, extract, calibrate all targets
    python scripts/run_pipeline.py -o --target fairall_9
    python scripts/run_pipeline.py -m -s
    python scripts/run_pipeline.py -p -w             # replot, then publish to the website

All targets run concurrently (``ava_pipeline``); ``--target`` runs a single
``ava_target_flow``.  The target list is ``pipeline.target_list`` in the AVA
config unless ``--targets-file`` is given.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

# Allow running from a checkout without `pip install -e .`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ava.config import cfg  # noqa: E402


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-o", "--open", "init", is_flag=True,
              help="Open/initialise target folders and build the reference catalogue.")
@click.option("-d", "--download", "download_data", is_flag=True,
              help="Download new data from the LCO archive.")
@click.option("--download-mode", type=click.Choice(["dry_run", "live"]), default=None,
              help="Photometry download: override download.mode for this run (dry_run: search only, fetch nothing).")
@click.option("-e", "--extract", is_flag=True,
              help="Extract source catalogues with SExtractor.")
@click.option("-c", "--calibrate", "calibrate_data", is_flag=True,
              help="Perform photometric calibration.")
@click.option("-t", "--pytics", is_flag=True,
              help="PyTICS ensemble calibration (incremental: new frames only).")
@click.option("--pytics-full", is_flag=True,
              help="PyTICS: recalibrate the whole data set (implies -t).")
@click.option("-p", "--plot", is_flag=True,
              help="Plot light curves for the AVA website.")
@click.option("-m", "--merge", "merge_data", is_flag=True,
              help="Inter-calibrate data with CALI.")
@click.option("-s", "--save", is_flag=True,
              help="Save inter-calibrated data from CALI.")
@click.option("-O", "--spec-open", "spec_init", is_flag=True,
              help="Spectroscopy: create the target's FLOYDS folders and summarise its spectra (lcodb DB).")
@click.option("-D", "--spec-download", "spec_download_data", is_flag=True,
              help="Spectroscopy: plan/download the FLOYDS frames (science, arcs, flats, standard, "
                   "archive products) of the selected nights; mode from spectroscopy.download.")
@click.option("-R", "--spec-reduce", "spec_reduce_data", is_flag=True,
              help="Spectroscopy: reduce the downloaded nights with the improved banzai-floyds; QC → spectra DB.")
@click.option("-P", "--spec-products", "spec_products_data", is_flag=True,
              help="Spectroscopy: website products (latest spectrum, Hbeta light curve) and Hbeta records.")
@click.option("--spec-nights", default=None, metavar="YYYYMMDD[,..]",
              help="Spectroscopy download: these nights instead of spectroscopy.download.select.")
@click.option("--spec-mode", type=click.Choice(["dry_run", "live"]), default=None,
              help="Spectroscopy download: override spectroscopy.download.mode for this run.")
@click.option("-w", "--web", "publish", is_flag=True,
              help="Publish to the website: snapshot ava.db and copy changed plots into web.data_dir "
                   "(once, after all targets).")
@click.option("--target", default=None, metavar="DATA_ID",
              help="Run a single target (its data_id, e.g. fairall_9) instead of the full list.")
@click.option("--targets-file", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=None, help="Override the target list YAML from the config.")
def main(init, download_data, download_mode, extract, calibrate_data, pytics, pytics_full, plot, merge_data, save,
         spec_init, spec_download_data, spec_nights, spec_mode, spec_reduce_data, spec_products_data, publish, target,
         targets_file):
    """AGN Variability Archive — update the archive with new data."""
    steps = dict(
        init=init,
        download_data=download_data,
        download_mode=download_mode,
        extract=extract,
        calibrate_data=calibrate_data,
        pytics=pytics or pytics_full,
        pytics_mode="full" if pytics_full else None,      # None: ensemble.mode from the config
        plot=plot,
        merge_data=merge_data,
        save=save,
        spec_init=spec_init,
        spec_download_data=spec_download_data,
        spec_nights=spec_nights.split(",") if spec_nights else None,
        spec_mode=spec_mode,
        spec_reduce_data=spec_reduce_data,
        spec_products_data=spec_products_data,
        publish=publish,
    )
    if not any(v for k, v in steps.items() if k not in ("pytics_mode", "spec_nights", "spec_mode", "download_mode")):
        raise click.UsageError("Nothing to do: specify at least one step flag (-o -d -e -c -t -p -m -s -O -D -R -P -w).")

    # Imported here so `--help` works without Prefect installed.
    from ava.pipeline.flows import ava_pipeline, ava_target_flow, load_targets

    click.echo(f"[AVA] config: {cfg._path}")
    if target:
        ava_target_flow(target, **steps)
    else:
        targets = load_targets(targets_file) if targets_file else load_targets()
        ava_pipeline(targets=targets, **steps)


if __name__ == "__main__":
    main()
