"""Publish pipeline outputs into the website's data folder (web/data/) by hand.

Same as the pipeline's ``-w/--web`` step (ava.web.publish); paths come from the
``web`` section of the AVA config unless overridden here.

Usage:
    python tools/publish_web.py                    # everything, from config
    python tools/publish_web.py --dry-run          # list what would change
    python tools/publish_web.py --target Mrk_817   # one target's plots (+ DB)
    # local test with explicit sources:
    python tools/publish_web.py --db data/ava.db --plots-src 'docs/figures/webplots_{target}'
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ava.config import cfg  # noqa: E402
from ava.web.publish import publish_from_config  # noqa: E402


def _abs(p: str) -> Path:
    q = Path(p).expanduser()
    return q if q.is_absolute() else REPO / q


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", action="append", help="only this data_id's plots (repeatable)")
    ap.add_argument("--dest", help="website data folder (default: web.data_dir)")
    ap.add_argument("--db", help="source ava.db (default: cfg.db_path)")
    ap.add_argument("--filter-dict", help="source filter_dict.txt (default: plots.filter_dict)")
    ap.add_argument("--plots-src", help="plot folder template with {target} (default: cfg.target_plots_dir)")
    ap.add_argument("--usage-src", help="folder with lco_usage_<semester>.png (default: web.usage_src)")
    ap.add_argument("--prune", action="store_true", default=None, help="remove plots no longer produced")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    s = publish_from_config(
        cfg, targets=a.target, dry_run=a.dry_run,
        dest=_abs(a.dest) if a.dest else None,
        db=_abs(a.db) if a.db else None,
        filter_dict=_abs(a.filter_dict) if a.filter_dict else None,
        plots_dir_for=(lambda t: _abs(a.plots_src.replace("{target}", t))) if a.plots_src else None,
        usage_src=a.usage_src,
        prune=a.prune,
    )
    for c in s.changes:
        print(("[dry-run] " if a.dry_run else "") + c)
    print(f"{'[dry-run] ' if a.dry_run else ''}published to {s.dest}: {s.agn} AGN, "
          f"{s.plots_copied} plot(s) updated for {s.targets_with_plots} target(s), "
          f"{s.plots_pruned} pruned, {s.usage_copied} usage plot(s)")


if __name__ == "__main__":
    main()
