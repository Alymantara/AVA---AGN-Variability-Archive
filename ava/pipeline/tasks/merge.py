"""
Merge task — inter-calibrate telescopes/filters with CALI.

Replaces the ``-m/--merge`` and ``-s/--save`` branches of
``__old_pipeline__/ava_update.py`` (``ava_merge.py -obj <target> -m|-p``).

Planned behaviour
-----------------
1. Ensure ``cfg.merging_dir(target)`` exists.
2. ``intercalibrate=True`` (``-m``): split ``lco_latest.pkl`` into one light
   curve per telescope/filter and run the CALI MCMC inter-calibration
   (``cfg.intercalibration.mcmc_steps``; extend by
   ``cfg.intercalibration.mcmc_retry_steps`` until converged).
3. ``save=True`` (``-s``): write the merged light curves and figures, copying
   the figures to ``cfg.plots_dir`` (and the web server, as in
   :mod:`ava.pipeline.tasks.webplot`).

Inputs
------
target : str
    Target slug.
intercalibrate : bool
    Run the CALI fit.
save : bool
    Save / publish the inter-calibrated products.

Outputs
-------
dict
    ``{"target", "converged", "products"}``.

Side effects
------------
Writes into ``cfg.merging_dir(target)`` and ``cfg.plots_dir``.
"""

from __future__ import annotations

from prefect import task


@task(name="merge", tags=["cali"])
def merge(target: str, intercalibrate: bool = True, save: bool = False) -> dict:
    """Inter-calibrate ``target``'s light curves with CALI."""
    raise NotImplementedError("merge task not yet ported")
