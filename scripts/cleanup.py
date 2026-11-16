#!/usr/bin/env python
"""
Delete downloaded raw frames that AVA has finished with (``ava.archive.cleanup``).

Photometry images go once they are catalogued (with their frame metadata) and calibrated; FLOYDS nights once
every spectrum is reduced and in the final products; standard-star nights once no target night needs them.
Everything must also be older than ``cleanup.retention_days``.  Dry run unless ``--live`` (or ``cleanup.mode:
live``).

    python scripts/cleanup.py                       # dry run: what would go, and why the rest stays
    python scripts/cleanup.py --live                # delete
    python scripts/cleanup.py --target Mrk_817 --photometry-only

Cron (after the daily pipeline), e.g.:
    0 5 * * *  cd /opt/ava/AVA && /opt/ava/env/bin/python scripts/cleanup.py --live >> /srv/ava/logs/cleanup.log 2>&1
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ava.config import cfg  # noqa: E402


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--live", is_flag=True, help="Delete (default: cleanup.mode, normally dry run).")
@click.option("--retention-days", type=float, default=None, help="Override cleanup.retention_days.")
@click.option("--target", "targets", multiple=True, help="Only these data_ids (repeatable).")
@click.option("--photometry-only", is_flag=True)
@click.option("--spectra-only", is_flag=True)
def main(live, retention_days, targets, photometry_only, spectra_only):
    from ava.archive import cleanup

    live = live or cleanup.settings(cfg)["mode"] == "live"
    click.echo(f"--- {datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} cleanup ({'LIVE' if live else 'dry run'})")
    out = cleanup.run(cfg, live=live, retention_days=retention_days, targets=list(targets) or None,
                      photometry=False if spectra_only else None, spectra=False if photometry_only else None,
                      log=click.echo)
    p, s = out.get("photometry"), out.get("spectra")
    verb = "deleted" if live else "would delete"
    if p:
        click.echo(f"photometry: {verb} {p['files']} image(s), {p['gb']:.2f} GB")
    if s:
        click.echo(f"spectra: {verb} {s['files']} file(s), {s['mb']:.1f} MB")
    if not live:
        click.echo("(dry run: nothing deleted; add --live)")


if __name__ == "__main__":
    main()
