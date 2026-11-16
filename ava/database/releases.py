"""
ava.database.releases — public data releases (DR1, DR2, ...) and which AGN have data in each.

The release files are made elsewhere (a release script, one per release); this module only *registers*
what is on disk, so the database says what can be downloaded and the website links to it.

Layout, under ``releases.dir`` of the AVA config (relative to ``paths.archive_root``)::

    <releases_dir>/<release>/release.yaml           metadata (below)
    <releases_dir>/<release>/<data_id>/<files>      the files of one AGN; sub-folders allowed
                                                    (e.g. photometry/, spectra/): the first one is the file's kind

``release.yaml``::

    title: "AVA Data Release 1"
    description: "LCO photometry and FLOYDS spectroscopy, 2020-08-01 to 2023-07-31"
    date_start: "2020-08-01"        # data covered (UTC dates)
    date_end: "2023-07-31"
    release_date: "2027-01-15"      # public from this date; null = not public yet (no links on the site)
    doi: ""                         # optional
    url: ""                         # optional (paper, Zenodo record, ...)

Tables (in ``paths.database``; pipeline-owned, the curated ``agn`` table is not touched):

* ``data_releases``  one row per release (the metadata above);
* ``agn_releases``   the per-AGN flag: one row per (data_id, release) with ``available`` = 1 when the AGN has
                     files in that release (0 = withheld: the files stay registered but are not linked);
* ``release_files``  every file: path relative to the release folder, kind, size, SHA-256.

The website shows an AGN's links when ``agn_releases.available = 1`` and the release is public
(``release_date`` set and not in the future); ``ava.web.publish`` copies exactly those files.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

DDL = """
CREATE TABLE IF NOT EXISTS data_releases (
    release TEXT PRIMARY KEY, title TEXT, description TEXT, date_start TEXT, date_end TEXT,
    release_date TEXT, doi TEXT, url TEXT, registered_utc TEXT);
CREATE TABLE IF NOT EXISTS agn_releases (
    data_id TEXT NOT NULL, release TEXT NOT NULL, available INTEGER NOT NULL DEFAULT 1,
    n_files INTEGER, bytes INTEGER, updated_utc TEXT, PRIMARY KEY (data_id, release));
CREATE TABLE IF NOT EXISTS release_files (
    release TEXT NOT NULL, data_id TEXT NOT NULL, path TEXT NOT NULL, kind TEXT, bytes INTEGER, sha256 TEXT,
    PRIMARY KEY (release, path));
"""
META_KEYS = ("title", "description", "date_start", "date_end", "release_date", "doi", "url")
SKIP = {"release.yaml", ".DS_Store"}


def releases_dir(cfg) -> Path:
    """``releases.dir`` (default ``releases``), relative to ``paths.archive_root`` (or ava_root without one)."""
    rc = getattr(cfg, "releases", None)
    d = (rc.get("dir") if rc is not None else None) or "releases"
    resolve = getattr(cfg, "_resolve_archive", cfg._resolve)     # archive_root-relative where the config has one
    return resolve(str(d))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@dataclass
class Scan:
    release: str
    meta: dict
    files: list[dict] = field(default_factory=list)       # data_id, path, kind, bytes, sha256
    unknown: list[str] = field(default_factory=list)      # folders that are not an AGN data_id

    @property
    def data_ids(self) -> list[str]:
        return sorted({f["data_id"] for f in self.files})


def scan(root: Path, release: str, known_ids: set[str] | None = None) -> Scan:
    """Read ``<root>/<release>/release.yaml`` and list every file under ``<root>/<release>/<data_id>/``."""
    rdir = Path(root) / release
    meta_file = rdir / "release.yaml"
    if not meta_file.is_file():
        raise FileNotFoundError(f"{meta_file}: every release folder needs a release.yaml")
    meta = yaml.safe_load(meta_file.read_text()) or {}
    meta = {k: (None if meta.get(k) in ("", None) else str(meta[k])) for k in META_KEYS}
    s = Scan(release, meta)
    for d in sorted(p for p in rdir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if known_ids is not None and d.name not in known_ids:
            s.unknown.append(d.name)
            continue
        for f in sorted(d.rglob("*")):
            if not f.is_file() or f.name in SKIP or f.name.startswith(".") or f.is_symlink():
                continue
            rel = f.relative_to(d)
            s.files.append({"data_id": d.name, "path": f.relative_to(rdir).as_posix(),
                            "kind": rel.parts[0] if len(rel.parts) > 1 else "data",
                            "bytes": f.stat().st_size, "sha256": _sha256(f)})
    return s


def register(db: Path, s: Scan, withhold: set[str] = frozenset()) -> dict:
    """Write a scanned release to the database: replaces that release's file list and flags.

    AGN in ``withhold`` (or withheld before, ``available = 0``) keep ``available = 0``; AGN that no longer have
    files lose their row.  Returns a summary."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(sqlite3.connect(db)) as con, con:
        con.executescript(DDL)
        known = {r[0] for r in con.execute("SELECT data_id FROM agn WHERE data_id IS NOT NULL")}
        missing = sorted(set(s.data_ids) - known)
        if missing:
            raise ValueError(f"{s.release}: folders that are not AGN data_ids in agn: {missing}")
        held = {r[0] for r in con.execute(
            "SELECT data_id FROM agn_releases WHERE release = ? AND available = 0", (s.release,))} | set(withhold)
        con.execute(f"INSERT OR REPLACE INTO data_releases (release, {', '.join(META_KEYS)}, registered_utc) "
                    f"VALUES (?, {', '.join('?' * len(META_KEYS))}, ?)",
                    (s.release, *[s.meta[k] for k in META_KEYS], now))
        con.execute("DELETE FROM release_files WHERE release = ?", (s.release,))
        con.executemany("INSERT INTO release_files (release, data_id, path, kind, bytes, sha256) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        [(s.release, f["data_id"], f["path"], f["kind"], f["bytes"], f["sha256"]) for f in s.files])
        con.execute("DELETE FROM agn_releases WHERE release = ?", (s.release,))
        for d in s.data_ids:
            fs = [f for f in s.files if f["data_id"] == d]
            con.execute("INSERT INTO agn_releases (data_id, release, available, n_files, bytes, updated_utc) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (d, s.release, 0 if d in held else 1, len(fs), sum(f["bytes"] for f in fs), now))
    return {"release": s.release, "agn": len(s.data_ids), "withheld": sorted(held & set(s.data_ids)),
            "files": len(s.files), "bytes": sum(f["bytes"] for f in s.files)}


def is_public(release_date: str | None, today: date | None = None) -> bool:
    """A release is public once its release_date is set and not in the future."""
    if not release_date:
        return False
    return date.fromisoformat(str(release_date)[:10]) <= (today or datetime.now(timezone.utc).date())


def public_files(db: Path, today: date | None = None) -> list[dict]:
    """Files the website may serve: registered, AGN flagged available, release public."""
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='release_files'").fetchone():
            return []
        rows = [dict(r) for r in con.execute(
            "SELECT f.*, r.release_date FROM release_files f "
            "JOIN agn_releases a ON a.release = f.release AND a.data_id = f.data_id AND a.available = 1 "
            "JOIN data_releases r ON r.release = f.release ORDER BY f.release, f.path")]
    return [r for r in rows if is_public(r.pop("release_date"), today)]
