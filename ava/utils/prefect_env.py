"""Prefect settings AVA needs on every machine, applied before Prefect is imported.

* ``PREFECT_SERVER_ANALYTICS_ENABLED=false`` and ``DO_NOT_TRACK=1``: at start-up the server's analytics write to its
  SQLite database at the same moment as the flow run, and every run printed ``sqlite3.OperationalError: database is
  locked`` (production VM, 19 Nov 2026).
* ``PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS=90``: the temporary server of a run can take longer than the
  default to start on a busy or small machine.
* ``PREFECT_HOME`` from ``pipeline.prefect.home`` (relative to ava_root), when set and the variable is not: the
  Prefect database then lives with the data (production: data/prefect) for cron jobs as for interactive runs.

Values already in the environment win, so a machine can still override any of them.
"""
from __future__ import annotations

import os

DEFAULTS = {"PREFECT_SERVER_ANALYTICS_ENABLED": "false", "DO_NOT_TRACK": "1",
            "PREFECT_SERVER_EPHEMERAL_STARTUP_TIMEOUT_SECONDS": "90"}


def prefect_home(cfg=None):
    """``pipeline.prefect.home`` as an absolute path, or None (Prefect's own default, ~/.prefect)."""
    try:
        if cfg is None:
            from ava.config import cfg
        home = (cfg._raw.get("pipeline", {}).get("prefect", {}) or {}).get("home")
        return str(cfg._resolve(home)) if home else None
    except Exception:  # noqa: BLE001 - no config: leave Prefect's default
        return None


def apply(cfg=None) -> dict:
    """Set the defaults that are not set yet; returns what is now in effect."""
    for k, v in DEFAULTS.items():
        os.environ.setdefault(k, v)
    if not os.environ.get("PREFECT_HOME"):
        home = prefect_home(cfg)
        if home:
            os.environ["PREFECT_HOME"] = home
    return {k: os.environ.get(k) for k in [*DEFAULTS, "PREFECT_HOME"]}
