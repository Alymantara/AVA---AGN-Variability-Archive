#!/usr/bin/env python
"""
Register ``ava_pipeline`` as a Prefect deployment on a daily schedule.

Schedule, deployment name and work pool come from ``pipeline.prefect`` in the
AVA config (default: daily at 09:30 UTC).  Which steps the scheduled run
performs is set with the same flags as ``run_pipeline.py``; the default is the
nightly update ``-d -e -c -p``.

Two modes:

    # Register against a work pool (needs a running worker):
    prefect work-pool create ava-process --type process
    python scripts/deploy.py
    prefect worker start --pool ava-process

    # Or serve the deployment from this process (no worker needed):
    python scripts/deploy.py --serve
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ava.config import cfg  # noqa: E402

_PREFECT = cfg.pipeline.prefect


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-o", "--open", "init", is_flag=True, help="Include initialise step.")
@click.option("-d", "--download", "download_data", is_flag=True, help="Include download step.")
@click.option("-e", "--extract", is_flag=True, help="Include SExtractor step.")
@click.option("-c", "--calibrate", "calibrate_data", is_flag=True, help="Include calibration.")
@click.option("-t", "--pytics", is_flag=True, help="Include PyTICS ensemble calibration (incremental).")
@click.option("-p", "--plot", is_flag=True, help="Include web plots.")
@click.option("-m", "--merge", "merge_data", is_flag=True, help="Include CALI inter-calibration.")
@click.option("-s", "--save", is_flag=True, help="Include saving CALI products.")
@click.option("--name", default=_PREFECT.deployment_name, show_default=True,
              help="Deployment name.")
@click.option("--work-pool", default=_PREFECT.work_pool, show_default=True,
              help="Prefect work pool (ignored with --serve).")
@click.option("--cron", default=_PREFECT.schedule_cron, show_default=True,
              help="Cron schedule.")
@click.option("--timezone", "tz", default=_PREFECT.schedule_timezone, show_default=True,
              help="Timezone for the cron schedule.")
@click.option("--serve", is_flag=True,
              help="Serve the deployment from this process instead of using a work pool.")
def main(init, download_data, extract, calibrate_data, pytics, plot, merge_data, save,
         name, work_pool, cron, tz, serve):
    """Deploy the AVA pipeline with a daily schedule."""
    from prefect.client.schemas.schedules import CronSchedule

    from ava.pipeline.flows import ava_pipeline

    steps = dict(
        init=init,
        download_data=download_data,
        extract=extract,
        calibrate_data=calibrate_data,
        pytics=pytics,
        plot=plot,
        merge_data=merge_data,
        save=save,
    )
    if not any(steps.values()):
        # Default nightly update, equivalent to `ava_update.py -d -e -c -p`.
        steps.update(download_data=True, extract=True, calibrate_data=True, plot=True)

    schedule = CronSchedule(cron=cron, timezone=tz)
    enabled = ", ".join(k for k, v in steps.items() if v)
    click.echo(f"[AVA] deployment '{name}': {cron} ({tz}); steps: {enabled}")

    if serve:
        ava_pipeline.serve(name=name, schedules=[schedule], parameters=steps)
        return

    entrypoint = Path(sys.modules[ava_pipeline.fn.__module__].__file__).relative_to(cfg.root)
    ava_pipeline.from_source(
        source=str(cfg.root),
        entrypoint=f"{entrypoint}:{ava_pipeline.fn.__name__}",
    ).deploy(
        name=name,
        work_pool_name=work_pool,
        schedules=[schedule],
        parameters=steps,
    )


if __name__ == "__main__":
    main()
