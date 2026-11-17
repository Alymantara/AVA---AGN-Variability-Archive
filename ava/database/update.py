"""
ava.database.update — the pipeline's writes to the AVA database.

Only pipeline-owned columns can be written here (:data:`PIPELINE_COLUMNS`);
curated columns (names, coordinates, literature values) are changed by
reviewed migrations in ``tools/``, never by pipeline runs.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from ava.config import cfg

#: agn columns the pipeline may write.
#: ``ava`` only for its observing state (2), see :mod:`ava.database.activity`;
#: ``frac_<band>`` from the merged light curves, see :mod:`ava.photometry.variability`.
PIPELINE_COLUMNS = frozenset({"lco_active", "lt_active", "agn_gaia_dr3_id", "ava",
                              *(f"frac_{b}" for b in ("u", "B", "g", "V", "r", "i", "z"))})


def set_agn_fields(data_id: str, path: Path | None = None, **fields) -> None:
    """Update pipeline-owned ``agn`` columns for one source.

    Raises ``KeyError`` for a non-pipeline column and ``LookupError`` if
    ``data_id`` is not in the database.
    """
    bad = set(fields) - PIPELINE_COLUMNS
    if bad:
        raise KeyError(f"not pipeline-owned agn columns: {sorted(bad)}")
    if not fields:
        return
    assign = ", ".join(f'"{k}" = ?' for k in fields)
    with closing(sqlite3.connect(Path(path or cfg.db_path), timeout=30)) as con:
        cur = con.execute(f"UPDATE agn SET {assign} WHERE data_id = ?", (*fields.values(), data_id))
        if cur.rowcount != 1:
            raise LookupError(f"{data_id!r}: {cur.rowcount} agn rows matched (expected 1)")
        con.commit()


# ---------------------------------------------------------------------------
# Download state (daily incremental downloads)
# ---------------------------------------------------------------------------

_DOWNLOAD_STATE_DDL = """
CREATE TABLE IF NOT EXISTS download_state (   -- written by the pipeline download task
    data_id TEXT, kind TEXT,
    last_success_utc TEXT,     -- start of the last live run that finished without failures
    last_run_utc TEXT, last_status TEXT, n_downloaded INTEGER, n_missing INTEGER,
    PRIMARY KEY (data_id, kind)
)
"""


def get_download_state(data_id: str, kind: str, path: Path | None = None) -> dict | None:
    with closing(sqlite3.connect(Path(path or cfg.db_path), timeout=30)) as con:
        con.execute(_DOWNLOAD_STATE_DDL)
        con.row_factory = sqlite3.Row
        r = con.execute("SELECT * FROM download_state WHERE data_id=? AND kind=?", (data_id, kind)).fetchone()
        return dict(r) if r else None


def set_download_state(data_id: str, kind: str, *, run_utc: str, status: str, n_downloaded: int,
                       n_missing: int, success: bool, path: Path | None = None) -> None:
    """Record a live run; ``last_success_utc`` advances only when ``success``."""
    with closing(sqlite3.connect(Path(path or cfg.db_path), timeout=30)) as con:
        con.execute(_DOWNLOAD_STATE_DDL)
        con.execute(
            "INSERT INTO download_state (data_id, kind, last_success_utc, last_run_utc, last_status, "
            "n_downloaded, n_missing) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(data_id, kind) DO UPDATE SET "
            "last_success_utc = COALESCE(excluded.last_success_utc, download_state.last_success_utc), "
            "last_run_utc = excluded.last_run_utc, last_status = excluded.last_status, "
            "n_downloaded = excluded.n_downloaded, n_missing = excluded.n_missing",
            (data_id, kind, run_utc if success else None, run_utc, status, n_downloaded, n_missing))
        con.commit()
