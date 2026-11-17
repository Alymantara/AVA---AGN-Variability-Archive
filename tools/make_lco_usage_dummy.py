#!/usr/bin/env python
"""
Make DUMMY per-proposal LCO usage files from the semester totals (``ava.lco.usage.make_dummy``).

Until the real daily breakdown of the time charged exists, this spreads each (proposal, semester, instrument
class) total of ``lco_usage.allocations`` (``used``, hours) over the days of the semester, so the usage plots
can be drawn.  Files carry ``# dummy: true``; plots drawn from them are watermarked and not published.

    python tools/make_lco_usage_dummy.py                       # -> data/lco_usage/dummy/<PROPOSAL>.csv
    python tools/make_lco_usage_dummy.py --until 2026-11-16    # date the totals were taken (current semester)
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ava.config import cfg  # noqa: E402


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--out-dir", type=click.Path(file_okay=False, path_type=Path), default=None,
              help="Default: data/lco_usage/dummy.")
@click.option("--until", default=None, metavar="YYYY-MM-DD",
              help="Date the totals were taken (default: the allocations file's modification date).")
@click.option("--seed", type=int, default=2026, show_default=True)
def main(out_dir, until, seed):
    from ava.lco import usage

    st = usage.settings(cfg)
    alloc_path = st["allocations"]
    alloc = usage.load_allocations(alloc_path)
    d = date.fromisoformat(until) if until else datetime.fromtimestamp(alloc_path.stat().st_mtime).date()
    out = Path(out_dir or cfg._resolve("data/lco_usage/dummy"))
    files = usage.make_dummy(alloc, out, until_mjd=usage.mjd_of(d), seed=seed,
                             note=f"SYNTHETIC daily split of the semester totals in {alloc_path.name} "
                                  f"(taken {d}); replace with the real daily breakdown")
    for f in files:
        click.echo(f"wrote {f}")


if __name__ == "__main__":
    main()
