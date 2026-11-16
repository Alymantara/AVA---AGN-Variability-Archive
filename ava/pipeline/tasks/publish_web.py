"""
Publish task — refresh the website's own copy of the pipeline outputs.

Runs once at the end of ``ava_pipeline`` (or of a single-target run) when the
``-w/--web`` step is selected; see :mod:`ava.web.publish` for what is copied.
Settings: ``web.data_dir``, ``web.usage_src``, ``web.prune`` in the AVA config.
"""

from __future__ import annotations

from prefect import get_run_logger, task

from ava.config import cfg


@task(name="publish-web", retries=1, retry_delay_seconds=60)
def publish_web(targets: list[str] | None = None) -> dict:
    """Snapshot ava.db and copy changed plots for ``targets`` (default: all) into the web data folder."""
    from ava.web.publish import publish_from_config

    log = get_run_logger()
    s = publish_from_config(cfg, targets=targets)
    log.info("website data → %s: %d AGN, %d plot(s) updated for %d target(s), %d pruned, %d usage plot(s)",
             s.dest, s.agn, s.plots_copied, s.targets_with_plots, s.plots_pruned, s.usage_copied)
    return s.as_dict()
