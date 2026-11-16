"""
ava.pipeline.tasks — one Prefect task per pipeline step.

Every task takes the target slug (the per-target directory name, e.g.
``"fairall_9"``) as its first argument and resolves all paths through
``ava.config.cfg``.  Tasks return a small summary (a dict) so that the
flow run records what each step produced.
"""

from ava.pipeline.tasks.calibrate import calibrate
from ava.pipeline.tasks.download import download
from ava.pipeline.tasks.ensemble import ensemble
from ava.pipeline.tasks.initialise import initialise
from ava.pipeline.tasks.merge import merge
from ava.pipeline.tasks.reference import reference_catalog
from ava.pipeline.tasks.sextract import sextract
from ava.pipeline.tasks.webplot import webplot

__all__ = ["initialise", "reference_catalog", "download", "sextract", "calibrate", "ensemble", "webplot", "merge"]
