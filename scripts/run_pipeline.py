#!/usr/bin/env python
"""
AVA pipeline CLI — run the Prefect flows locally.

Same step flags as the legacy ``__old_pipeline__/ava_update.py``:

    python scripts/run_pipeline.py -dec              # download, extract, calibrate all targets
    python scripts/run_pipeline.py -o --target fairall_9
    python scripts/run_pipeline.py -m -s

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
@click.option("--target", default=None, metavar="DATA_ID",
              help="Run a single target (its data_id, e.g. fairall_9) instead of the full list.")
@click.option("--targets-file", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=None, help="Override the target list YAML from the config.")
def main(init, download_data, extract, calibrate_data, pytics, pytics_full, plot, merge_data, save,
         target, targets_file):
    """AGN Variability Archive — update the archive with new data."""
    steps = dict(
        init=init,
        download_data=download_data,
        extract=extract,
        calibrate_data=calibrate_data,
        pytics=pytics or pytics_full,
        pytics_mode="full" if pytics_full else "auto",
        plot=plot,
        merge_data=merge_data,
        save=save,
    )
    if not any(v for k, v in steps.items() if k != "pytics_mode"):
        raise click.UsageError("Nothing to do: specify at least one step flag (-o -d -e -c -t -p -m -s).")

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
