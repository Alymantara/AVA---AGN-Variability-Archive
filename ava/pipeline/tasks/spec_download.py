"""
Spectroscopy download task — the FLOYDS frames a reduction needs, per observing night.

Mirrors the photometry ``download`` task (same modes, state tracking and file registry), but the
frame set is planned offline from the lcodb spectra DB (:mod:`ava.spectroscopy.download`): the
target's science spectra with their arc and lamp flat, the night's flux standard with its own arc
and flat, and (``archive_products``) the archive's BANZAI -1d/-2d for comparison.

Settings: ``spectroscopy.download`` in the AVA config.

* ``mode: dry_run`` (default): plan and report on disk / missing — **no archive request**;
  ``mode: live``: fetch the missing files, at most ``max_frames_per_run``; their signed URLs
  come from one archive listing per observing request (``request_id``), not one request per file.
* nights: ``nights`` (explicit list) or ``select``: ``new`` (nights after the last successful
  run, minus ``overlap_days``; the daily mode), ``latest`` / ``oldest``; at most ``max_nights``.
* tracking: ``ava.db`` ``download_state`` (kind ``spec``: last run, status, counts; the date
  advances only after a live run with no failures and no cap) and the lcodb ``local_files``
  table (one row per downloaded frame: role, path, md5).

The spectra DB must be current (``lcodb daily``) for new nights to appear.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from prefect import get_run_logger, task

from ava.config import cfg


def spec_download_settings():
    s = cfg._raw.get("spectroscopy", {}).get("download", {}) or {}
    return dict(mode=s.get("mode", "dry_run"), select=s.get("select", "new"), nights=s.get("nights") or [],
                max_nights=s.get("max_nights"), archive_products=s.get("archive_products", True),
                max_frames_per_run=int(s.get("max_frames_per_run", 100)),
                overlap_days=int(s.get("overlap_days", 2)), initial_lookback_days=int(s.get("initial_lookback_days", 30)),
                verify_existing=bool(s.get("verify_existing", False)),
                parallel_fetches=int(s.get("parallel_fetches") or cfg.download.get("parallel_fetches", 1)))


@task(name="spec-download", tags=["spectroscopy", "download", "lco-archive"])
def spec_download(target: str, mode: str | None = None, nights: list[str] | None = None,
                  max_nights: int | None = None) -> dict:
    """Plan (and in live mode fetch) the FLOYDS frames of ``target``'s nights."""
    from ava.database.update import get_download_state, set_download_state
    from ava.pipeline.tasks.download import archive_client, lcodb_path
    from ava.spectroscopy import download as SD

    logger = get_run_logger()
    s = spec_download_settings()
    mode = mode or s["mode"]
    if mode not in ("dry_run", "live"):
        raise ValueError(f"spectroscopy.download.mode must be 'dry_run' or 'live', not {mode!r}")
    entry = cfg.target_by_data_id(target)
    if entry is None:
        raise ValueError(f"{target!r} is not a known data_id")
    db = lcodb_path("spec")
    if db is None:
        raise RuntimeError("no lcodb spectra DB (config/lcodb_config.yaml → data/lcodb/spectra.sqlite)")

    nights = nights or s["nights"]
    max_nights = max_nights if max_nights is not None else s["max_nights"]
    since = None
    if not nights and s["select"] == "new":
        st = get_download_state(target, "spec")
        if st and st.get("last_success_utc"):
            since = (datetime.fromisoformat(st["last_success_utc"]) - timedelta(days=s["overlap_days"])).date().isoformat()
        else:
            since = (datetime.now(timezone.utc) - timedelta(days=s["initial_lookback_days"])).date().isoformat()
    select = "oldest" if s["select"] == "new" else s["select"]
    chosen = SD.science_nights(db, int(entry["ava_id"]), since=since, nights=nights, select=select,
                               max_nights=max_nights)
    p = SD.plan(db, int(entry["ava_id"]), chosen, archive_products=s["archive_products"])
    logger.info("%s spec: %d night(s) %s → %d frames %s (%s)", target, len(chosen), chosen, len(p),
                p.role.value_counts().to_dict() if len(p) else {}, mode)
    live = mode == "live"
    res = SD.run(archive_client() if live else None, p, spec_raw_root=cfg.spec_raw(target).parent,
                 spec_root=cfg.spec_root, target=target, live=live, max_frames=s["max_frames_per_run"],
                 registry_db=db, verify_existing=s["verify_existing"], log=logger.warning,
                 parallel=s["parallel_fetches"])
    logger.info("%s spec: %d planned, %d on disk, %d missing; %d downloaded (%.1f MB), %d failed; "
                "%d archive request(s)%s", target, res.planned, res.on_disk, res.missing, len(res.downloaded),
                res.bytes / 1e6, len(res.failed), res.requests, " — capped" if res.capped else "")
    for name, why in list(res.failed.items())[:10]:
        logger.warning("  failed %s: %s", name, why)
    if live:
        ok = not res.failed and not res.capped
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
        set_download_state(target, "spec", run_utc=now,
                           status="ok" if ok else ("capped" if res.capped and not res.failed else "failures"),
                           n_downloaded=len(res.downloaded), n_missing=res.missing - len(res.downloaded), success=ok)
    out = {"target": target, "mode": mode, "nights": chosen,
           "spec": dict(planned=res.planned, on_disk=res.on_disk, missing=res.missing,
                        downloaded=len(res.downloaded), failed=len(res.failed), capped=res.capped,
                        bytes=res.bytes, requests=res.requests, by_role=res.by_role)}
    if res.failed:
        raise RuntimeError(f"{target}: {len(res.failed)} spectroscopy download failure(s); "
                           "files already fetched were kept, the rest are retried next run")
    return out
