"""
Publish task — refresh the website's own copy of the pipeline outputs.

Runs once at the end of ``ava_pipeline`` (or of a single-target run) when the
``-w/--web`` step is selected; see :mod:`ava.web.publish` for what is copied.
First refreshes the derived AGN properties (:mod:`ava.database.derived`: k_bol,
L_bol, Eddington ratio, theoretical disc lags), so newly ingested AGN get them
before the database is snapshotted for the site, and the observing flag ``agn.ava``
(:mod:`ava.database.activity`: 2 = LCO data in the last 30 days), and the per-band
fractional variability of every merged light curve (:mod:`ava.photometry.variability`).
Settings: ``web.data_dir``, ``web.usage_src``, ``web.prune`` in the AVA config.
"""

from __future__ import annotations

from prefect import get_run_logger, task

from ava.config import cfg


@task(name="publish-web", retries=1, retry_delay_seconds=60)
def publish_web(targets: list[str] | None = None) -> dict:
    """Snapshot ava.db and copy changed plots for ``targets`` (default: all) into the web data folder."""
    from ava.database.derived import update_from_config
    from ava.web.publish import publish_from_config

    log = get_run_logger()
    try:
        d = update_from_config(cfg)
        lag = [c for c in d.columns if c.startswith("lag_")]
        log.info("derived properties: %d AGN, %d with lags", len(d), int(d[lag[0]].notna().sum()) if lag else 0)
    except Exception as exc:  # noqa: BLE001 — never block the publish on this
        log.warning("derived properties not updated (%s: %s)", type(exc).__name__, exc)
    try:
        from ava.database.activity import update_from_config as update_observing

        ch = update_observing(cfg)
        log.info("observing flag: %d change(s)%s", len(ch), "".join(f"; {d} {o}->{w}" for d, o, w, _ in ch))
    except Exception as exc:  # noqa: BLE001
        log.warning("observing flag not updated (%s: %s)", type(exc).__name__, exc)
    try:   # F_var of the merged light curves → photometry_variability + agn.frac_<band> in the main database
        from ava.photometry.variability import update_from_config as update_fvar

        fv = update_fvar(cfg)
        log.info("fractional variability: %d target(s) from merged light curves", len(fv))
    except Exception as exc:  # noqa: BLE001
        log.warning("fractional variability not updated (%s: %s)", type(exc).__name__, exc)
    s = publish_from_config(cfg, targets=targets)
    log.info("website data → %s: %d catalogue entries, %d plot(s) updated for %d target(s), %d pruned, %d usage plot(s), "
             "%d manual(s)", s.dest, s.agn, s.plots_copied, s.targets_with_plots, s.plots_pruned, s.usage_copied,
             s.manuals_copied)
    from ava.web.releases import publish_releases_from_config     # data releases (ava.database.releases)

    r = publish_releases_from_config(cfg)
    log.info("data releases: %d public file(s), %d copied, %d removed", r["release_files"], r["copied"], r["pruned"])
    for p in r["problems"]:
        log.warning("data release: %s", p)
    return {**s.as_dict(), "releases": r}
