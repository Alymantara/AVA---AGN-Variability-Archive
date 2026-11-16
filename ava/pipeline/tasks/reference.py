"""
Reference-catalogue task — LCO-band magnitudes of field stars.

Method from ``photometry.reference.method``: Gaia DR3 GSPC (default) or the
legacy APASS + atmosphere-model fit (fallback).

Second half of ``-o`` (runs right after :mod:`~ava.pipeline.tasks.initialise`).
Replaces the catalogue part of ``__old_pipeline__/ava_initialise.py`` and all
of ``ava_zp_pytics.py``; the SDSS / Pan-STARRS / UVOT patching is dropped.
The science lives in :mod:`ava.photometry.reference`; settings come from
``photometry.reference`` in the config.

Inputs
------
target : str
    Target ``data_id``.
force : bool
    Rebuild even if the catalogue already exists.

Outputs (in ``cfg.phot_dir(target)``)
-------------------------------------
reference_stars.csv         one row per star, keyed by star_id = Gaia DR3 source_id
                            (schema in ava.photometry.reference)
reference_stars_meta.yaml   provenance: release, radius, E(B-V), AGN row, pivots
apass_dr10_raw.csv          raw AAVSO download (DR10 source only)

Returns ``{"target", "catalogue", "skipped", **meta}``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import yaml
from prefect import get_run_logger, task

from ava.config import cfg

CATALOGUE = "reference_stars.csv"
META = "reference_stars_meta.yaml"
RAW_DR10 = "apass_dr10_raw.csv"


def _plain(obj):
    """Convert numpy scalars inside nested dicts/lists to plain Python for YAML."""
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj.item() if hasattr(obj, "item") else obj


@task(name="reference-catalog", retries=1, retry_delay_seconds=60, tags=["catalogues"])
def reference_catalog(target: str, force: bool = False) -> dict:
    """Build ``reference_stars.csv`` for ``target``."""
    from ava.photometry.reference import build_reference_catalog

    logger = get_run_logger()
    out_dir = cfg.phot_dir(target)
    cat_path, meta_path = out_dir / CATALOGUE, out_dir / META
    if cat_path.exists() and meta_path.exists() and not force:
        logger.info("%s exists; skipping (force=True to rebuild)", cat_path)
        return {"target": target, "catalogue": str(cat_path), "skipped": True}

    entry = cfg.target_by_data_id(target)
    if entry is None:
        raise ValueError(f"{target!r} is not a known data_id")
    rc = cfg.photometry.reference

    # Cone: centred on the nucleus, widened to cover every LCO pointing that
    # has frames (offset fields such as NGC 4395 sit 4.4' from the AGN).
    agn_ra, agn_dec = cfg.agn_position(entry)
    radius = float(rc.radius_arcmin)
    if entry.get("pointings"):
        from ava.database.query import field_radius_arcmin
        radius = field_radius_arcmin(entry, radius)
        centre = (agn_ra, agn_dec)
    else:  # YAML entry: ra_deg/dec_deg is the pointing
        centre = (entry["ra_deg"], entry["dec_deg"])
    common = dict(radius_arcmin=radius, vizier_server=list(rc.vizier_servers))
    stars, meta = build_reference_catalog(
        *centre,
        agn_ra=agn_ra, agn_dec=agn_dec,
        method=rc.get("method", "gspc"),
        fallback=rc.get("fallback") or None,
        min_stars=int(rc.get("min_stars", 20)),
        log=logger.info,
        gspc=dict(
            **common,
            max_ruwe=float(rc.get("max_ruwe", 1.4)),
            neighbour_arcsec=float(rc.get("neighbour_arcsec", 3.0)),
            neighbour_dmag=float(rc.get("neighbour_dmag", 2.5)),
        ),
        apass_model=dict(
            **common,
            apass_source=rc.apass_source,
            grid_path=cfg._resolve(rc.atmosphere_grid),
            filters_dir=cfg._resolve(rc.lco_filters),
            apass_url=rc.apass_url,
            use_gaia=bool(rc.gaia),
            dust_scale_height_pc=float(rc.dust_scale_height_pc),
            min_parallax_snr=float(rc.min_parallax_snr),
            gaia_match_arcsec=float(rc.gaia_match_arcsec),
            n_draws=int(rc.n_draws),
            seed=int(rc.random_seed),
            u_anchor=bool(rc.get("u_anchor", True)),
            u_anchor_min_stars=int(rc.get("u_anchor_min_stars", 10)),
            raw_out=out_dir / RAW_DR10,
        ),
    )

    # star_id (Gaia DR3 source_id) is the key every later step joins on.
    if stars["star_id"].duplicated().any():
        raise RuntimeError(f"duplicate star_id in {target} reference catalogue")
    if int(stars["is_agn"].sum()) != 1:
        raise RuntimeError(f"{target}: expected exactly one AGN row, got {int(stars['is_agn'].sum())}")
    meta.update(target=target, built_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    # Write both to temp files, then rename: a failure never leaves a
    # catalogue without its metadata (which would be skipped on retry).
    tmp_cat, tmp_meta = cat_path.with_suffix(".csv.tmp"), meta_path.with_suffix(".yaml.tmp")
    stars.to_csv(tmp_cat, index=False, float_format="%.6g")
    tmp_meta.write_text(yaml.safe_dump(_plain(meta), sort_keys=False))
    tmp_cat.replace(cat_path)
    tmp_meta.replace(meta_path)
    # Record the AGN's Gaia DR3 id in the database (the source of truth).
    if cfg._raw.get("pipeline", {}).get("target_source", "database") == "database":
        from ava.database.update import set_agn_fields
        gid = meta.get("agn_star_id")
        set_agn_fields(target, agn_gaia_dr3_id=gid if gid not in (None, -1) else None)

    logger.info("Wrote %s (%s, %d rows; AGN star_id %s)",
                cat_path, meta["method"], len(stars), meta.get("agn_star_id"))
    return {"target": target, "catalogue": str(cat_path), "skipped": False, **meta}
