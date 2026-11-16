#!/usr/bin/env python
"""
Backfill: search the LCO archive for one target and download its frames.

Same reasoning as ``__old_pipeline__/download_data.py`` (target, proposals,
dates, reduction level; page by page following ``next``), via
:mod:`ava.lco.download`.  Every LCO spelling of the target in ``ava.db`` is
searched unless ``--name`` is given.

    # what is there? (listing requests only, no file fetched)
    python scripts/download.py --target fairall_9 --kind phot --proposal KEY2020B-006 \\
        --start 2020-07-01 --end 2022-07-01
    # fetch it
    python scripts/download.py ... --live
    # raw FLOYDS spectra (SPECTRUM + ARC + LAMPFLAT)
    python scripts/download.py --target fairall_9 --kind spec --start 2020-07-01

Kinds: phot = BANZAI L91 → cfg.phot_raw(target);  spec = raw L0 → cfg.spec_raw(target).
Does not touch the daily update state.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ava.config import cfg  # noqa: E402

#: Ask for --yes above this many (minimum) archive listing requests.
CONFIRM_REQUESTS = 50


def _date(s):
    return datetime.strptime(s, "%Y-%m-%d") if s else None


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--target", required=True, metavar="DATA_ID", help="AVA data_id, e.g. fairall_9.")
@click.option("--kind", type=click.Choice(["phot", "spec"]), default="phot", show_default=True)
@click.option("--proposal", "proposals", multiple=True,
              help="Proposal ID (repeatable) [default: lco.proposals in the config].")
@click.option("--start", default="2014-01-01", show_default=True, help="YYYY-MM-DD (inclusive).")
@click.option("--end", default=None, help="YYYY-MM-DD (exclusive) [default: tomorrow].")
@click.option("--name", "names", multiple=True,
              help="LCO OBJECT name to search (repeatable) [default: all spellings in ava.db].")
@click.option("--filter", "filters", multiple=True, help="phot: filters to keep [default: photometry.filters].")
@click.option("--live", is_flag=True, help="Download (default: list only).")
@click.option("--max-frames", default=1000, show_default=True, help="Max files downloaded this run.")
@click.option("--window-days", default=None, type=int, help="Search window [default: download.window_days].")
@click.option("--verify-existing", is_flag=True, help="md5-check files already on disk.")
@click.option("--yes", is_flag=True, help=f"Skip the confirmation above {CONFIRM_REQUESTS} listing requests.")
def main(target, kind, proposals, start, end, names, filters, live, max_frames, window_days,
         verify_existing, yes):
    """Search (and with --live, download) LCO frames of TARGET."""
    from ava.lco import download as dl
    from ava.pipeline.tasks.download import archive_client, lcodb_path, make_query, raw_dir

    entry = cfg.target_by_data_id(target)
    if entry is None:
        raise click.ClickException(f"{target!r} is not a known data_id")
    if names:
        entry = {**entry, "lco_names": list(names)}
    if not entry.get("lco_names"):
        raise click.ClickException(f"{target}: no LCO OBJECT names in the database; pass --name")
    t0 = _date(start)
    t1 = _date(end) or datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    q = make_query(entry, kind, proposals or list(cfg.lco.proposals), t0, t1)
    if filters:
        q.filters = list(filters)
    if window_days:
        q.window_days = window_days

    n_min = dl.n_listing_requests(q)
    dest = raw_dir(target, kind)
    click.echo(f"[AVA] {target} {kind} ({'LIVE' if live else 'list only'}): {q.start.date()} .. {q.end.date()}")
    click.echo(f"      names {q.names}; proposals {q.proposals}; level {q.rlevel}; -> {dest}")
    click.echo(f"      at least {n_min} archive listing request(s) ({len(q.names)} name(s) x "
               f"{len(q.proposals)} proposal(s), {q.window_days}-day windows from each proposal's start), "
               f"at {cfg.download.rate_per_s} /s")
    if n_min > CONFIRM_REQUESTS and not yes:
        click.confirm("Proceed?", abort=True)

    res = dl.run(archive_client(), q, dest, live=live, max_frames=max_frames, data_id=target,
                 verify_existing=verify_existing, registry_db=lcodb_path(kind), log=click.echo)
    click.echo(f"[AVA] found {res.found} {res.by_type}; on disk {res.on_disk}; missing {res.missing}")
    if live:
        click.echo(f"[AVA] downloaded {len(res.downloaded)} ({res.bytes / 1e6:.1f} MB); failed {len(res.failed)}"
                   + ("; stopped at --max-frames" if res.capped else ""))
        for name, why in list(res.failed.items())[:20]:
            click.echo(f"      failed {name}: {why}")
    if res.other_objects:
        click.echo(f"[AVA] WARNING: the archive returned {res.other_objects} frame(s) of OTHER objects "
                   f"(ignored) — check download.archive_params.object ({q.params['object']!r})")
    click.echo(f"[AVA] {res.requests} archive request(s) sent")
    sys.exit(1 if res.failed else 0)


if __name__ == "__main__":
    main()
