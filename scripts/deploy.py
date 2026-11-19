#!/usr/bin/env python
"""
Register ``ava_pipeline`` as a Prefect deployment on a daily schedule.

Schedule, deployment name, work pool and the nightly steps come from
``pipeline.prefect`` in the AVA config (``schedule_cron``, ``nightly_steps``).
Flags (same letters as ``run_pipeline.py``) replace ``nightly_steps`` for this
deployment.  The deployment runs the code in this repository; ``AVA_CONFIG`` (if
set) is passed to the worker so it reads the same config.

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

from ava.utils import prefect_env  # noqa: E402

prefect_env.apply(cfg)        # before Prefect is imported (analytics off, start-up timeout, PREFECT_HOME)

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
@click.option("-O", "--spec-open", "spec_init", is_flag=True, help="Include spectroscopy initialisation.")
@click.option("-D", "--spec-download", "spec_download_data", is_flag=True, help="Include FLOYDS download.")
@click.option("-R", "--spec-reduce", "spec_reduce_data", is_flag=True, help="Include FLOYDS reduction (new nights).")
@click.option("-P", "--spec-products", "spec_products_data", is_flag=True, help="Include spectroscopy products.")
@click.option("-w", "--web", "publish", is_flag=True, help="Include publishing to the website (web.data_dir).")
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
def main(init, download_data, extract, calibrate_data, pytics, plot, merge_data, save, spec_init,
         spec_download_data, spec_reduce_data, spec_products_data, publish, name, work_pool, cron, tz, serve):
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
        spec_init=spec_init,
        spec_download_data=spec_download_data,
        spec_reduce_data=spec_reduce_data,
        spec_products_data=spec_products_data,
        publish=publish,
    )
    if not any(steps.values()):
        # nightly update from the config (pipeline.prefect.nightly_steps)
        nightly = list(_PREFECT.get("nightly_steps") or
                       ["download_data", "extract", "calibrate_data", "plot", "publish"])
        unknown = [s for s in nightly if s not in steps]
        if unknown:
            raise click.UsageError(f"pipeline.prefect.nightly_steps: unknown step(s) {unknown}; known: {list(steps)}")
        steps.update({s: True for s in nightly})

    schedule = CronSchedule(cron=cron, timezone=tz)
    enabled = ", ".join(k for k, v in steps.items() if v)
    click.echo(f"[AVA] deployment '{name}': {cron} ({tz}); steps: {enabled}")

    if serve:
        ava_pipeline.serve(name=name, schedules=[schedule], parameters=steps)
        return

    import os

    repo = Path(__file__).resolve().parents[1]               # the code, wherever the data root is
    entrypoint = Path(sys.modules[ava_pipeline.fn.__module__].__file__).resolve().relative_to(repo)
    env = {k: os.environ[k] for k in ("AVA_CONFIG",) if os.environ.get(k)}
    ava_pipeline.from_source(
        source=str(repo),
        entrypoint=f"{entrypoint}:{ava_pipeline.fn.__name__}",
    ).deploy(
        name=name,
        work_pool_name=work_pool,
        schedules=[schedule],
        parameters=steps,
        job_variables={"env": env} if env else None,
    )


if __name__ == "__main__":
    main()
