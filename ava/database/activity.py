"""
ava.database.activity — the observing flag ``agn.ava`` from the LCO frame registry.

``agn.ava`` (legacy flag, shown on the website):

  2  Observing        an LCO science frame (imaging or FLOYDS) in the last ``days`` days
  1  Archived         all available data processed and archived      (set by hand)
  0  to be processed  observed, not yet archived
  NULL                not scheduled / no data

Only the observing state is automatic: a source with a science frame (photometry
``EXPOSE`` or spectroscopy ``SPECTRUM``) whose ``day_obs`` is within ``days`` of
today becomes 2; a source at 2 whose last frame is older drops to 0 until it is
archived. An archived source (1) that is observed again becomes 2. Sources with no
linked frames are left alone.

Run after every ingest of new frames: ``lcodb daily`` / ``lcodb link`` and the
pipeline's daily publish step call :func:`update_from_lcodb`.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

#: science obstype per lcodb kind
SCIENCE_OBSTYPES = {"photometry": "EXPOSE", "spectra": "SPECTRUM"}

OBSERVING, ARCHIVED, PENDING = 2, 1, 0


def last_frames(lcodb: Iterable[tuple[str, Path]]) -> dict[int, str]:
    """``ava_id -> latest day_obs`` (YYYY-MM-DD) over science frames in the given (kind, path) DBs."""
    last: dict[int, str] = {}
    for kind, path in lcodb:
        if path is None or not Path(path).is_file():
            continue
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)) as con:
            for i, d in con.execute(
                    "SELECT ava_id, MAX(day_obs) FROM frames WHERE ava_id IS NOT NULL AND obstype = ? GROUP BY ava_id",
                    (SCIENCE_OBSTYPES[kind],)):
                if d and (int(i) not in last or str(d)[:10] > last[int(i)]):
                    last[int(i)] = str(d)[:10]
    return last


def new_flag(current, last: str | None, cutoff: str):
    """The ``ava`` value for one source given its last frame date and the cutoff date."""
    if not last:
        return current
    if last >= cutoff:
        return OBSERVING
    if current is not None and int(current) == OBSERVING:
        return PENDING
    return current


def update_observing(db: Path, last: dict[int, str], days: int = 30, today: date | None = None,
                     dry_run: bool = False) -> list[tuple[str, object, object, str]]:
    """Apply :func:`new_flag` to every AGN; returns the changes as (data_id, old, new, last_day_obs)."""
    cutoff = ((today or date.today()) - timedelta(days=days)).isoformat()
    with closing(sqlite3.connect(Path(db), timeout=60)) as con:
        rows = con.execute("SELECT id, data_id, ava FROM agn").fetchall()
        changes = []
        for i, data_id, cur in rows:
            new = new_flag(cur, last.get(int(i)), cutoff)
            if new != cur and not (cur is not None and new is not None and int(cur) == int(new)):
                changes.append((data_id, cur, new, last.get(int(i))))
                if not dry_run:
                    con.execute("UPDATE agn SET ava = ? WHERE id = ?", (new, i))
        if not dry_run:
            con.commit()
    return changes


def update_from_lcodb(db: Path, lcodb_config: Path, days: int = 30, today: date | None = None,
                      dry_run: bool = False) -> list[tuple[str, object, object, str]]:
    """:func:`update_observing` with the frame registries named in the lcodb config."""
    from ava.lcodb.config import load_config

    lc = load_config(lcodb_config)
    return update_observing(db, last_frames((k, lc.db_path(k)) for k in SCIENCE_OBSTYPES), days, today, dry_run)


def update_from_config(cfg, dry_run: bool = False):
    """Pipeline entry point: paths and the window (``web.observing_days``, default 30) from the AVA config."""
    days = int(((cfg._raw.get("web", {}) or {}).get("observing_days")) or 30)
    return update_from_lcodb(cfg.db_path, cfg.lcodb_config_path, days, dry_run=dry_run)
