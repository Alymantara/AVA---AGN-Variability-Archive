"""
Download task — daily: new LCO frames of one target since its last update.

Replaces ``ava_update.py -d`` → ``__old_pipeline__/download_data.py``; the
search and download logic is :mod:`ava.lco.download` (same reasoning as the
legacy script: archive search by object / proposal / dates / level, page by
page following ``next``).  For a whole-history backfill use
``scripts/download.py``.

Per kind in ``download.daily_kinds`` (``phot``: BANZAI L91 → ``cfg.phot_raw``;
``spec``: raw L0 FLOYDS SPECTRUM/ARC/LAMPFLAT → ``cfg.spec_raw``):

* search from the last successful update (``ava.db`` ``download_state``)
  minus ``overlap_days`` — or ``initial_lookback_days`` the first time — to
  tomorrow, over ``daily_proposals`` and every LCO spelling of the target;
* ``mode: dry_run`` (default): report found / on disk / missing (listing
  requests only — no file fetched);  ``mode: live``: also fetch up to
  ``max_frames_per_run`` files, and advance the update date only if the run
  had no failures and was not capped (otherwise the same range is searched
  again next time).

Also warns about unlinked LCO OBJECT names near the AGN (spelling check, from
the lcodb DB, offline).

Returns ``{"target", "mode", "<kind>": {found, on_disk, missing, downloaded,
failed, requests, ...}, "unlinked_nearby": [...]}``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from prefect import get_run_logger, task

from ava.config import cfg

_CLIENT = None  # process-wide archive client: one rate limiter / 429 state for all targets


def archive_client():
    global _CLIENT
    if _CLIENT is None:
        from ava.lcodb import api
        from ava.lcodb.api import Client

        lco = cfg._raw.get("lco", {}) or {}
        api.set_urls(lco.get("archive_url"), lco.get("base_url"))
        from ava.lco.token import require_token

        token = require_token(ava_cfg=cfg)        # the error lists every place looked at
        dl = cfg.download
        _CLIENT = Client(token=token, rate_per_s=float(dl.rate_per_s),
                         server_error_retries=int(dl.get("server_error_retries", 1)),
                         server_error_limit=int(dl.get("server_error_limit", 3)))
    return _CLIENT


def lcodb_path(kind: str):
    """lcodb DB of a kind (photometry / spectra), or None if not configured / absent."""
    try:
        from ava.lcodb.config import load_config

        p = load_config(cfg.lcodb_config_path).db_path("photometry" if kind == "phot" else "spectra")
        return p if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def raw_dir(target: str, kind: str):
    return cfg.phot_raw(target) if kind == "phot" else cfg.spec_raw(target)


def make_query(entry: dict, kind: str, proposals, start, end):
    from ava.lco.download import Query
    from ava.photometry.process import camera_telescopes, imaging_prefixes

    dc = cfg.download
    return Query(
        names=list(entry.get("lco_names") or []), proposals=list(proposals), start=start, end=end, kind=kind,
        filters=list(cfg.photometry.filters) if kind == "phot" else None,
        cameras=list(imaging_prefixes()) if kind == "phot" else None,
        camera_telescopes=camera_telescopes() if kind == "phot" else None,
        window_days=int(dc.window_days), page_size=int(dc.page_size),
        params=dict(vars(dc.archive_params)),
    )


@task(name="download", tags=["lco-archive"])
def download(target: str, mode: str | None = None, kinds: list[str] | None = None) -> dict:
    """Daily download of ``target``'s new frames (see module docstring)."""
    from ava.database.update import get_download_state, set_download_state
    from ava.lco import download as dl

    logger = get_run_logger()
    dc = cfg.download
    mode = mode or dc.mode
    if mode not in ("dry_run", "live"):
        raise ValueError(f"download.mode must be 'dry_run' or 'live', not {mode!r}")
    entry = cfg.target_by_data_id(target)
    if entry is None:
        raise ValueError(f"{target!r} is not a known data_id")
    out = {"target": target, "mode": mode}

    db = lcodb_path("phot")
    if db is not None:
        ra, dec = cfg.agn_position(entry)
        near = dl.unlinked_names_near(db, ra, dec, float(dc.unlinked_radius_arcmin))
        out["unlinked_nearby"] = near["object"].tolist()
        if len(near):
            logger.warning("%s: unlinked LCO OBJECT name(s) near the AGN — check spelling / overrides: %s",
                           target, "; ".join(f"{r.object!r} ({r.n_phot} phot, {r.sep_arcmin:.1f}')"
                                             for r in near.itertuples()))

    if not entry.get("lco_names"):
        logger.warning("%s: no LCO OBJECT names linked in the database — nothing to search", target)
        return out

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    failures = []
    for kind in (kinds or list(dc.daily_kinds)):
        state = get_download_state(target, kind)
        if state and state.get("last_success_utc"):
            start = datetime.fromisoformat(state["last_success_utc"]) - timedelta(days=int(dc.overlap_days))
        else:
            start = now - timedelta(days=int(dc.initial_lookback_days))
        q = make_query(entry, kind, dc.daily_proposals, start, now + timedelta(days=1))
        logger.info("%s %s: searching %s .. %s, names %s, proposals %s (%s)", target, kind,
                    start.date(), q.end.date(), q.names, q.proposals, mode)
        res = dl.run(archive_client(), q, raw_dir(target, kind), live=(mode == "live"),
                     max_frames=int(dc.max_frames_per_run), data_id=target,
                     verify_existing=bool(dc.verify_existing), registry_db=lcodb_path(kind), log=logger.warning,
                     done=dl.catalogued(cfg.sextractor_dir(target)) if kind == "phot" else None)
        out[kind] = dict(found=res.found, on_disk=res.on_disk, processed=res.processed, missing=res.missing,
                         downloaded=len(res.downloaded), failed=len(res.failed), capped=res.capped,
                         bytes=res.bytes, requests=res.requests, by_type=res.by_type)
        logger.info("%s %s: %d found (%s), %d on disk, %d already processed, %d missing; %d downloaded (%.1f MB), "
                    "%d failed; %d archive request(s)%s", target, kind, res.found, res.by_type, res.on_disk,
                    res.processed, res.missing,
                    len(res.downloaded), res.bytes / 1e6, len(res.failed), res.requests,
                    " — capped" if res.capped else "")
        for name, why in list(res.failed.items())[:10]:
            logger.warning("  failed %s: %s", name, why)
        if mode == "live":
            ok = not res.failed and not res.capped
            set_download_state(target, kind, run_utc=now.isoformat(timespec="seconds"),
                               status="ok" if ok else ("capped" if res.capped and not res.failed else "failures"),
                               n_downloaded=len(res.downloaded), n_missing=res.missing - len(res.downloaded),
                               success=ok)
        if res.failed:
            failures.append(f"{kind}: {len(res.failed)}")
    if failures:
        raise RuntimeError(f"{target}: download failures ({', '.join(failures)}); "
                           "successful files were kept and the range is retried next run")
    return out
