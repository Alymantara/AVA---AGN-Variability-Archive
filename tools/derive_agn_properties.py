"""Recompute the derived AGN properties (table agn_derived) from the curated catalogue.

k_bol (Netzer 2019), L_bol, Eddington ratio and the theoretical thin-disc lags
(Fausnaugh et al. 2016, X = 4.97: Wien-law value, following Tie & Kochanek 2018) for every AGN in ava.db —
run after ingesting new AGN or changing their mass / L5100. The pipeline's publish
step (-w) runs the same code daily. Settings: ``derived`` in the AVA config.

Usage:
    python tools/derive_agn_properties.py --dry-run          # print, write nothing
    python tools/derive_agn_properties.py                    # update ava.db (cfg.db_path)
    python tools/derive_agn_properties.py --db path/to/ava.db
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from ava.config import cfg  # noqa: E402
from ava.database.derived import DerivedSettings, filter_wavelengths, update_derived  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", help="AVA database (default: cfg.db_path)")
    ap.add_argument("--dry-run", action="store_true", help="compute and print only")
    a = ap.parse_args()
    db = Path(a.db).resolve() if a.db else cfg.db_path
    plots = cfg._raw.get("plots", {}) or {}
    wl = filter_wavelengths(cfg._resolve(plots.get("filter_dict") or "data/reference/filter_dict.txt"))
    s = DerivedSettings.from_config(cfg)
    out = update_derived(db, wl, s, dry_run=a.dry_run)
    lag_cols = [c for c in out.columns if c.startswith("lag_")]
    with pd.option_context("display.max_rows", None, "display.width", 160):
        print(out[["data_id", "logm", "log_lbol", "lbol_source", "eddington_ratio", *lag_cols]].round(3).to_string(index=False))
    n = out[lag_cols[0]].notna().sum() if lag_cols else 0
    print(f"{'[dry-run] ' if a.dry_run else ''}{len(out)} AGN, {n} with lags; {s.method}"
          + ("" if a.dry_run else f" → {db} (agn_derived)"))


if __name__ == "__main__":
    main()
