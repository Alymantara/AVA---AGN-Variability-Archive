"""
Initialise task — create the working directories for one target.

Port of the directory part of ``__old_pipeline__/ava_initialise.py`` (run by
``ava_update.py -o``), plus the ``sextractor_ava`` / ``ava_merging`` folders
the legacy orchestrator created lazily in its ``-e`` and ``-m`` branches.

Behaviour
---------
1. Look the target up in the target list (``cfg.target_by_data_id``); an
   unknown ``data_id`` is an error, so typos never create stray folders.
2. Create, if missing (idempotent, never deletes or overwrites):

   ======================================  ===============================
   ``cfg.phot_dir(target)``                 photometry products
   ``cfg.phot_raw(target)``                 raw LCO frames (``YYYYMMDD/``)
   ``cfg.sextractor_dir(target)``           SExtractor catalogues
   ``cfg.merging_dir(target)``              CALI inter-calibration
   ``cfg.phot_dir(target) / "UVOT"``        Swift/UVOT catalogues
   ======================================  ===============================

3. Write ``cfg.phot_dir(target) / "target.yaml"`` (once) recording the
   target-list entry and when the folder was initialised, so each working
   directory is self-describing.

Reference catalogue (second half of ``-o``)
------------------------------------------
Implemented in :mod:`ava.pipeline.tasks.reference` /
:mod:`ava.photometry.reference`.  Original merge plan, for the record:
``ava_initialise.py`` and ``__old_pipeline__/ava_zp_pytics.py`` are being
merged: both created these folders and downloaded APASS, and
``ava_zp_pytics.py`` supersedes the SDSS / Pan-STARRS / UVOT patching in
``ava_initialise.py`` (dropped).  The merged step, to run after this task:

1. Fetch APASS DR9 around the AGN (legacy: 15 arcmin, scraped from the AAVSO
   web form with ``mechanize`` — port to astroquery,
   ``cfg.photometry.reference_catalog``) → ``apass_<target>.csv``.
2. Synthetic photometry: per star, fit a reddened atmosphere model (Teff,
   norm; E(B-V) fixed to 0.86 × SFD) to APASS B, g, V, r, i and integrate it
   through the LCO filter curves → ``u_lco … Y_lco`` (+ errors from 1000
   covariance draws) in ``cfg.phot_dir(target) / "apass_pytics.csv"``.
3. Record the AGN's row in that catalogue as ``agn_field_id``.

Inputs
------
target : str
    Target ``data_id`` (directory slug), e.g. ``"fairall_9"``.

Outputs
-------
dict
    ``{"target", "name", "created": [paths], "existing": [paths]}``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import yaml
from prefect import get_run_logger, task

from ava.config import cfg

#: Name of the per-target metadata file written into cfg.phot_dir(target).
TARGET_META = "target.yaml"


def target_dirs(target: str) -> list:
    """All directories a fully initialised target has."""
    return [
        cfg.phot_dir(target),
        cfg.phot_raw(target),
        cfg.sextractor_dir(target),
        cfg.merging_dir(target),
        cfg.phot_dir(target) / "UVOT",
    ]


@task(name="initialise", tags=["filesystem"])
def initialise(target: str) -> dict:
    """Create the working directories for ``target`` (idempotent)."""
    logger = get_run_logger()

    entry = cfg.target_by_data_id(target)
    if entry is None:
        raise ValueError(f"{target!r} is not a known data_id (target source: "
                         f"{cfg._raw.get('pipeline', {}).get('target_source', 'database')})")

    created, existing = [], []
    for d in target_dirs(target):
        if d.is_dir():
            existing.append(str(d))
        else:
            d.mkdir(parents=True, exist_ok=True)
            created.append(str(d))
            logger.info("Created %s", d)

    meta = cfg.phot_dir(target) / TARGET_META
    if meta.exists():
        existing.append(str(meta))
    else:
        record = {
            **entry,
            "initialised_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "config": str(cfg._path),
        }
        # DB entries may hold numpy scalars / NaN; round-trip through JSON for plain types.
        import json
        record = json.loads(json.dumps(
            record, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
        meta.write_text(yaml.safe_dump(record, sort_keys=False))
        created.append(str(meta))

    logger.info("Initialised %s (%s): %d created, %d already present",
                target, entry["name"], len(created), len(existing))
    return {"target": target, "name": entry["name"], "created": created, "existing": existing}
