"""
ava.pipeline — Prefect orchestration for the AVA photometry pipeline.

Replaces the legacy ``__old_pipeline__/ava_update.py`` orchestrator, which
wrote one shell script per target and launched it with ``nohup``.  Here each
target is a Prefect subflow (:func:`~ava.pipeline.flows.ava_target_flow`) whose
steps run in sequence, and the top-level flow
(:func:`~ava.pipeline.flows.ava_pipeline`) runs all targets concurrently.

Step order per target (each step optional, controlled by CLI flags):

    initialise  ->  download  ->  sextract  ->  calibrate  ->  webplot  ->  merge

Prefect is an optional dependency: ``pip install -e .[pipeline]``.
"""

from ava.utils import prefect_env as _prefect_env

_prefect_env.apply()          # before Prefect is imported: analytics off, start-up timeout, PREFECT_HOME

from ava.pipeline.flows import ava_pipeline, ava_target_flow, load_targets  # noqa: E402

__all__ = ["ava_pipeline", "ava_target_flow", "load_targets"]
