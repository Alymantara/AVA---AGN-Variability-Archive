#!/usr/bin/env python
"""
LCO time-usage plots, ``lco_usage_<semester>.png`` (``ava.lco.usage``; port of the legacy ``ava_lco_update.py``).

Reads the per-proposal usage files (``lco_usage.input_dir``; format in ``data/lco_usage/README.md``; estimated
from the lcodb databases while ``lco_usage.estimate_from_lcodb``) and the allocations, joins the snapshot log of
LCO's charged totals if there is one, and draws the current semester (plus the previous one in the first days of a
new semester), chosen semesters, or all of them.  The only LCO request is the snapshot, and only when
``lco_usage.snapshots.mode: live`` or ``--live-snapshot`` (one read-only GET of the portal's proposal list).

    python scripts/lco_usage.py                         # current semester; copied to the website (lco_usage.publish)
    python scripts/lco_usage.py --semester 2026A --semester 2026B
    python scripts/lco_usage.py --all                   # every semester with an allocation or usage
    python scripts/lco_usage.py --no-publish            # draw only, do not copy to <web.data_dir>/usage/
    python scripts/lco_usage.py --live-snapshot         # also record LCO's charged totals (one portal request)

Cron (every 6 hours), e.g.:
    0 */6 * * *  cd /opt/ava/AVA && /opt/ava/env/bin/python scripts/lco_usage.py >> /srv/ava/logs/lco_usage.log 2>&1
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ava.config import cfg  # noqa: E402


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--semester", "semesters", multiple=True, metavar="2026B",
              help="Semester to draw (repeatable; default: the current one).")
@click.option("--all", "all_semesters", is_flag=True, help="Draw every semester with an allocation or usage.")
@click.option("--input-dir", type=click.Path(file_okay=False, path_type=Path), default=None,
              help="Override lco_usage.input_dir.")
@click.option("--out-dir", type=click.Path(file_okay=False, path_type=Path), default=None,
              help="Override lco_usage.plots_dir.")
@click.option("--style", type=click.Choice(["legacy", "percent", "panels"]), default=None,
              help="Override lco_usage.style.")
@click.option("--live-snapshot", is_flag=True, default=None,
              help="Take a LIVE snapshot of the charged totals (one read-only portal request). Default: "
                   "lco_usage.snapshots.mode (dry_run: only says what it would request).")
@click.option("--publish/--no-publish", default=None,
              help="Copy changed PNGs to <web.data_dir>/usage/ (website). Default: lco_usage.publish (on).")
@click.option("--allow-dummy", is_flag=True, default=None,
              help="Also publish plots drawn from dummy files (default: lco_usage.publish_dummy).")
def main(semesters, all_semesters, input_dir, out_dir, style, live_snapshot, publish, allow_dummy):
    from ava.lco import usage

    click.echo(f"--- {datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} lco_usage")
    usage.run(cfg, semesters=list(semesters) or None, all_semesters=all_semesters, input_dir=input_dir,
              plots_dir=out_dir, style=style, snapshot_live=live_snapshot or None, publish=publish, allow_dummy=allow_dummy or None, log=click.echo)


if __name__ == "__main__":
    main()
