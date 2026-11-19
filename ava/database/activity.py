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

Recent cadence (table ``observing_recent``, shown in the website's target table): per source and kind
(imaging / FLOYDS), the distinct observing nights in the last ``windows[0]`` days (default 30) and their mean
spacing, ``(last - first) / (n - 1)``. With fewer than 2 nights there, the next window (default 60) is used.
Rebuilt in full by :func:`update_recent_cadence` on the same runs as the flag.
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


def recent_nights(lcodb: Iterable[tuple[str, Path]], since: str) -> dict[int, dict[str, list[str]]]:
    """``ava_id -> {kind: sorted distinct science-frame nights >= since}`` from the given (kind, path) DBs."""
    out: dict[int, dict[str, list[str]]] = {}
    for kind, path in lcodb:
        if path is None or not Path(path).is_file():
            continue
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)) as con:
            for i, d in con.execute(
                    "SELECT DISTINCT ava_id, substr(day_obs, 1, 10) FROM frames "
                    "WHERE ava_id IS NOT NULL AND obstype = ? AND day_obs >= ?", (SCIENCE_OBSTYPES[kind], since)):
                out.setdefault(int(i), {}).setdefault(kind, []).append(str(d))
    for kinds in out.values():
        for k in kinds:
            kinds[k] = sorted(set(kinds[k]))
    return out


def cadence(nights: list[str], today: date, windows: tuple[int, ...] = (30, 60)) -> tuple[int, float | None, int]:
    """``(n_nights, mean spacing in days or None, window used)``: the first window with >= 2 nights, else the last."""
    n, w = 0, windows[-1]
    for w in windows:
        cut = (today - timedelta(days=w)).isoformat()
        sel = [d for d in nights if d >= cut]
        n = len(sel)
        if n >= 2:
            span = (date.fromisoformat(sel[-1]) - date.fromisoformat(sel[0])).days
            return n, round(span / (n - 1), 2), w
    return n, None, w


RECENT_SCHEMA = """CREATE TABLE IF NOT EXISTS observing_recent (   -- recent LCO cadence (ava.database.activity)
    data_id TEXT PRIMARY KEY,
    phot_nights INTEGER, phot_cadence REAL, phot_window INTEGER, phot_last TEXT,
    spec_nights INTEGER, spec_cadence REAL, spec_window INTEGER, spec_last TEXT,
    updated_utc TEXT)"""


def update_recent_cadence(db: Path, nights: dict[int, dict[str, list[str]]], windows: tuple[int, ...] = (30, 60),
                          today: date | None = None, dry_run: bool = False) -> list[tuple]:
    """Rebuild ``observing_recent`` (one row per source with a science night in the longest window); returns the rows."""
    from datetime import datetime, timezone

    today = today or date.today()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    with closing(sqlite3.connect(Path(db), timeout=60)) as con:
        ids = dict(con.execute("SELECT id, data_id FROM agn WHERE data_id IS NOT NULL"))
        rows = []
        for i, kinds in sorted(nights.items()):
            if i not in ids:
                continue
            row = [ids[i]]
            for k in ("photometry", "spectra"):
                ns = kinds.get(k, [])
                n, cad, w = cadence(ns, today, windows)
                row += [n, cad, w, ns[-1] if ns else None]
            rows.append(tuple(row) + (stamp,))
        if not dry_run:
            con.execute(RECENT_SCHEMA)
            con.execute("DELETE FROM observing_recent")
            con.executemany("INSERT INTO observing_recent VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
            con.commit()
    return rows


def update_from_lcodb(db: Path, lcodb_config: Path, days: int = 30, today: date | None = None,
                      dry_run: bool = False, windows: tuple[int, ...] = (30, 60)) -> list[tuple[str, object, object, str]]:
    """:func:`update_observing` and :func:`update_recent_cadence` with the frame registries in the lcodb config."""
    from ava.lcodb.config import load_config

    lc = load_config(lcodb_config)
    dbs = [(k, lc.db_path(k)) for k in SCIENCE_OBSTYPES]
    today = today or date.today()
    update_recent_cadence(db, recent_nights(dbs, (today - timedelta(days=max(windows))).isoformat()),
                          windows, today, dry_run)
    return update_observing(db, last_frames(dbs), days, today, dry_run)


def update_from_config(cfg, dry_run: bool = False):
    """Pipeline entry point: paths and windows from the AVA config (``web.observing_days``, default 30;
    ``web.cadence_windows``, default [30, 60])."""
    web = cfg._raw.get("web", {}) or {}
    days = int(web.get("observing_days") or 30)
    windows = tuple(int(w) for w in (web.get("cadence_windows") or (30, 60)))
    return update_from_lcodb(cfg.db_path, cfg.lcodb_config_path, days, dry_run=dry_run, windows=windows)
