"""
ava.pipeline.flows — Prefect flows for the AVA photometry pipeline.

UI structure
------------
Every run is tagged so the Prefect dashboard can be filtered by:

  - target name   (e.g. "fairall_9", "mrk_817")
  - instrument    ("photometry", "spectroscopy")
  - stage         ("housekeeping", "download", "extraction",
                   "calibration", "plotting", "intercalibration")
  - run type      ("daily", "on-demand", "test")

Flow hierarchy visible in the UI
---------------------------------
ava-pipeline [daily | on-demand]          <- top-level, one per invocation
  └── ava-target: <name> [<target>]       <- one subflow per AGN, run in parallel
        └── tasks appear as task runs:
              initialise   [housekeeping]
              reference-catalog [housekeeping | catalogues]   (part of init / -o)
              download     [photometry | download]
              sextract     [photometry | extraction]
              calibrate    [photometry | calibration]
              ensemble     [photometry | calibration | pytics]   (PyTICS; full or incremental)
              webplot      [photometry | plotting]
              merge        [photometry | intercalibration]
  └── publish-web [website | publish]     <- once, after all targets (-w)

Flow-run names (visible in the UI run list)
-------------------------------------------
  ava-pipeline/daily-2026-11-15
  ava-target/fairall_9
  ava-target/mrk_817
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from prefect import flow, get_run_logger, task
from prefect.task_runners import ThreadPoolTaskRunner

from ava.config import cfg
from ava.pipeline.tasks import (
    calibrate,
    download,
    ensemble,
    initialise,
    merge,
    publish_web,
    reference_catalog,
    sextract,
    spec_download,
    spec_initialise,
    spec_products,
    spec_reduce,
    webplot,
)


# ---------------------------------------------------------------------------
# Stage → tag mapping (shown in the Prefect UI)
# ---------------------------------------------------------------------------

STAGE_TAGS: dict[str, list[str]] = {
    "init":        ["housekeeping", "initialisation"],
    "download":    ["photometry",   "download"],
    "sextract":    ["photometry",   "extraction"],
    "calibrate":   ["photometry",   "calibration"],
    "ensemble":    ["photometry",   "calibration", "pytics"],
    "webplot":     ["photometry",   "plotting"],
    "merge":       ["photometry",   "intercalibration"],
    "spec_init":     ["spectroscopy", "initialisation"],
    "spec_download": ["spectroscopy", "download"],
    "spec_reduce":   ["spectroscopy", "reduction"],
    "spec_products": ["spectroscopy", "plotting"],
    "publish":       ["website",      "publish"],
}


def _target_tags(target: str, extra: list[str] | None = None) -> list[str]:
    """Build the base tag set for a target subflow."""
    tags = ["ava", f"target:{target}"]
    if extra:
        tags += extra
    return tags


# ---------------------------------------------------------------------------
# Target list loading
# ---------------------------------------------------------------------------

def load_targets(
    path: Path | None = None,
    active_only: bool = True,
) -> list[str]:
    """Return target data_id slugs from the target list YAML.

    Parameters
    ----------
    path : Path, optional
        Alternative target-list YAML; defaults to ``pipeline.target_list``.
    active_only : bool
        Keep only entries with ``lco_active: true`` (default True).
    """
    if path is None:
        entries = cfg.load_targets()
    else:
        with open(path) as f:
            entries = (yaml.safe_load(f) or {}).get("targets", [])
    return [
        t["data_id"] for t in entries
        if not active_only or t.get("lco_active", False)
    ]


# ---------------------------------------------------------------------------
# Per-target subflow
# ---------------------------------------------------------------------------

@flow(
    name="ava-target",
    flow_run_name="ava-target/{target}",
    log_prints=True,
    description=(
        "Run one or more pipeline stages for a single AGN target. "
        "Stages execute strictly in order: init → download → sextract → "
        "calibrate → ensemble → webplot → merge."
    ),
)
def ava_target_flow(
    target: str,
    init: bool = False,
    download_data: bool = False,
    download_mode: str | None = None,
    extract: bool = False,
    calibrate_data: bool = False,
    pytics: bool = False,
    pytics_mode: str | None = None,
    plot: bool = False,
    merge_data: bool = False,
    save: bool = False,
    spec_init: bool = False,
    spec_download_data: bool = False,
    spec_nights: list[str] | None = None,
    spec_mode: str | None = None,
    spec_reduce_data: bool = False,
    spec_products_data: bool = False,
    publish: bool = False,
    run_type: str = "on-demand",
) -> dict:
    """Run the selected pipeline steps for one target, strictly in sequence.

    Parameters
    ----------
    target : str
        Target ``data_id`` slug (e.g. ``"fairall_9"``).
    init, download_data, extract, calibrate_data, pytics, plot, merge_data, save : bool
        Which stages to execute (``pytics``: the PyTICS ensemble stage).
    pytics_mode : str
        ``"auto"`` (update the stored solution with new frames; refit if needed)
        or ``"full"`` (recalibrate the whole data set).
        Which stages to execute.
    publish : bool
        Finally refresh the website data folder for this target (``publish-web``).
        ``ava_pipeline`` passes False and publishes once after all targets.
    run_type : str
        ``"daily"``, ``"on-demand"``, or ``"test"`` — added as a tag so the
        dashboard can filter by trigger type.

    Returns
    -------
    dict
        Mapping of executed stage name to that task's summary dict.
    """
    logger = get_run_logger()

    # Resolve the human-readable name for log messages
    t_entry = cfg.target_by_data_id(target)
    display = t_entry["name"] if t_entry else target

    stages_requested = [
        s for s, flag in [
            ("init", init), ("download", download_data), ("sextract", extract),
            ("calibrate", calibrate_data), ("ensemble", pytics), ("webplot", plot),
            ("merge", merge_data or save), ("spec_init", spec_init), ("spec_download", spec_download_data), ("spec_reduce", spec_reduce_data), ("spec_products", spec_products_data),
            ("publish", publish),
        ] if flag
    ]
    logger.info(
        "▶  %s  (%s)  —  stages: %s",
        display, target, ", ".join(stages_requested) or "none",
    )

    results: dict[str, dict] = {}

    if init:
        results["init"] = initialise.with_options(
            tags=_target_tags(target, STAGE_TAGS["init"]),
        )(target)
        results["reference_catalog"] = reference_catalog.with_options(
            tags=_target_tags(target, STAGE_TAGS["init"] + ["catalogues"]),
        )(target)

    if download_data:
        results["download"] = download.with_options(
            tags=_target_tags(target, STAGE_TAGS["download"]),
        )(target, mode=download_mode)                     # None: download.mode from the config

    if extract:
        results["sextract"] = sextract.with_options(
            tags=_target_tags(target, STAGE_TAGS["sextract"]),
        )(target)

    if calibrate_data:
        results["calibrate"] = calibrate.with_options(
            tags=_target_tags(target, STAGE_TAGS["calibrate"]),
        )(target)

    if pytics:
        results["ensemble"] = ensemble.with_options(
            tags=_target_tags(target, STAGE_TAGS["ensemble"]),
        )(target, mode=pytics_mode)

    if plot:
        results["webplot"] = webplot.with_options(
            tags=_target_tags(target, STAGE_TAGS["webplot"]),
        )(target)

    if merge_data or save:
        results["merge"] = merge.with_options(
            tags=_target_tags(target, STAGE_TAGS["merge"]),
        )(target, intercalibrate=merge_data, save=save)

    if spec_init:
        results["spec_init"] = spec_initialise.with_options(
            tags=_target_tags(target, STAGE_TAGS["spec_init"]),
        )(target)

    if spec_download_data:
        results["spec_download"] = spec_download.with_options(
            tags=_target_tags(target, STAGE_TAGS["spec_download"]),
        )(target, nights=spec_nights, mode=spec_mode)

    if spec_reduce_data:
        results["spec_reduce"] = spec_reduce.with_options(
            tags=_target_tags(target, STAGE_TAGS["spec_reduce"]),
        )(target, nights=spec_nights)

    if spec_products_data:
        results["spec_products"] = spec_products.with_options(
            tags=_target_tags(target, STAGE_TAGS["spec_products"]),
        )(target)

    if publish:
        results["publish"] = publish_web.with_options(
            tags=_target_tags(target, STAGE_TAGS["publish"]),
        )(targets=[target])

    logger.info(
        "✓  %s  finished  —  %s",
        display, ", ".join(results) or "no stages run",
    )
    return results


# ---------------------------------------------------------------------------
# Wrapper task so subflows can run concurrently inside the top-level flow
# ---------------------------------------------------------------------------

@task(name="run-target", log_prints=True)
def _run_target(target: str, steps: dict[str, bool], run_type: str) -> dict:
    """Submit ``ava_target_flow`` as a child run (enables concurrency)."""
    return ava_target_flow(target, **steps, run_type=run_type)


# ---------------------------------------------------------------------------
# Top-level pipeline flow
# ---------------------------------------------------------------------------

@flow(
    name="ava-pipeline",
    task_runner=ThreadPoolTaskRunner(max_workers=int(cfg._raw.get("pipeline", {}).get("n_cores") or 4)),
    log_prints=True,
    description=(
        "Run the full AVA photometric pipeline across all (or selected) AGN targets. "
        "Each target runs as a concurrent subflow. A target failure does not stop "
        "the others; the pipeline is marked failed if any target fails."
    ),
)
def ava_pipeline(
    targets: list[str] | None = None,
    init: bool = False,
    download_data: bool = False,
    download_mode: str | None = None,
    extract: bool = False,
    calibrate_data: bool = False,
    pytics: bool = False,
    pytics_mode: str | None = None,
    plot: bool = False,
    merge_data: bool = False,
    save: bool = False,
    spec_init: bool = False,
    spec_download_data: bool = False,
    spec_nights: list[str] | None = None,
    spec_mode: str | None = None,
    spec_reduce_data: bool = False,
    spec_products_data: bool = False,
    publish: bool = False,
    run_type: str = "on-demand",
) -> dict:
    """Run ``ava_target_flow`` for every target in parallel.

    Parameters
    ----------
    targets : list of str, optional
        Target ``data_id`` slugs; defaults to all ``lco_active`` targets.
    init, download_data, extract, calibrate_data, pytics, plot, merge_data, save : bool
        Which stages to execute (``pytics``: the PyTICS ensemble stage).
    pytics_mode : str
        ``"auto"`` (update the stored solution with new frames; refit if needed)
        or ``"full"`` (recalibrate the whole data set).
        Which stages to run on each target.
    publish : bool
        After all targets, refresh the website data folder once (database
        snapshot + every target's plots). Runs even if some targets failed,
        so the site shows the targets that did update.
    run_type : str
        ``"daily"`` (scheduled), ``"on-demand"`` (manual), or ``"test"``.

    Returns
    -------
    dict
        ``{"succeeded": [...], "failed": {target: error_message}}``.
    """
    logger = get_run_logger()

    if targets is None:
        targets = load_targets()

    stages = dict(
        init=init,
        download_data=download_data,
        download_mode=download_mode,
        extract=extract,
        calibrate_data=calibrate_data,
        pytics=pytics,
        pytics_mode=pytics_mode,
        plot=plot,
        merge_data=merge_data,
        save=save,
        spec_init=spec_init,
        spec_download_data=spec_download_data,
        spec_nights=spec_nights,
        spec_mode=spec_mode,
        spec_reduce_data=spec_reduce_data,
        spec_products_data=spec_products_data,
    )
    active_stages = [k for k, v in stages.items()
                     if v and k not in ("pytics_mode", "spec_nights", "spec_mode", "download_mode")]
    stage_tags = []
    for s in active_stages:
        stage_tags += STAGE_TAGS.get(s, STAGE_TAGS.get(s.removesuffix("_data"), []))
    stage_tags = sorted(set(stage_tags))

    logger.info(
        "AVA pipeline  |  %d targets  |  stages: %s  |  run type: %s",
        len(targets), ", ".join(active_stages + (["publish"] if publish else [])) or "none", run_type,
    )

    # Submit all targets concurrently
    futures = {
        t: _run_target.with_options(
            tags=["ava", f"target:{t}", run_type] + stage_tags,
        ).submit(t, stages, run_type)
        for t in targets
    }

    succeeded, failed = [], {}
    for target, future in futures.items():
        try:
            future.result()
            succeeded.append(target)
        except Exception as exc:  # noqa: BLE001
            failed[target] = f"{type(exc).__name__}: {exc}"
            logger.error("✗  %s  failed:  %s", target, failed[target])

    logger.info(
        "Pipeline complete — %d succeeded, %d failed",
        len(succeeded), len(failed),
    )

    published = None
    if publish:
        try:
            published = publish_web.with_options(
                tags=["ava", run_type] + STAGE_TAGS["publish"],
            )(targets=targets)
        except Exception as exc:  # noqa: BLE001
            failed["publish-web"] = f"{type(exc).__name__}: {exc}"
            logger.error("✗  website publish failed:  %s", failed["publish-web"])

    if failed:
        raise RuntimeError(
            f"{len(failed)} target(s) failed: {', '.join(failed)}"
        )
    return {"succeeded": succeeded, "failed": failed, "published": published}
