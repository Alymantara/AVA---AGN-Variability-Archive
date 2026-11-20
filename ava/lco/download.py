"""
ava.lco.download — search the LCO archive for a target and download its frames.

Port of ``__old_pipeline__/download_data.py`` (lcogtDD; N. Espinoza, with
B. J. Fulton), keeping its reasoning:

* search the archive by **object name, proposal, date range and reduction
  level**;
* walk the result **page by page** (by ``offset``, until a short page: the
  archive's ``next`` is an estimate, B25), and download each
  page's frames before requesting the next page — download URLs are signed
  and expire (48 h), so they are always used fresh;
* save to ``<raw dir>/YYYYMMDD/<filename>``, skip files already on disk and
  ``_cat.fits`` products — and frames already processed whose image has been
  deleted (``done``: photometry frames with a catalogue).

Two entry points share it: backfill (``scripts/download.py``: a target,
proposals, dates, kind) and daily (pipeline ``-d``: from the target's last
successful update, kept in ``ava.db`` ``download_state``).

Changes from the legacy script
------------------------------
* every LCO spelling of the target (``ava.db`` ``lco_targets``) is searched;
* date **windows** (default 30 d) instead of one query per day;
* each file fetched **once** (the legacy script fetched it twice), into
  ``.part``, md5-checked against the archive value, then renamed;
* token auth through the shared rate-limited ``lcodb.api.Client``
  (429 back-off); a per-run cap on downloaded files;
* archive filter names are configurable (``download.archive_params``) —
  the API renamed some since the legacy ``OBJECT`` / ``PROPID`` / ``RLEVEL``.

Kinds: ``phot`` → BANZAI products (reduction level 91) in the configured
filters; ``spec`` → raw (level 0) FLOYDS frames of type SPECTRUM, ARC and
LAMPFLAT (the arcs and flats of a FLOYDS request carry the target's name).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator

KINDS = ("phot", "spec")

LOCAL_FILES_DDL = """
CREATE TABLE IF NOT EXISTS local_files (   -- frames downloaded by AVA (ava.lco.download)
    frame_id INTEGER PRIMARY KEY, kind TEXT, role TEXT, data_id TEXT,
    path TEXT, md5 TEXT, md5_ok INTEGER, bytes INTEGER, downloaded_utc TEXT
);
"""

#: Default archive query parameter names (current API, as used by lcodb ingest).
DEFAULT_PARAMS = {"object": "target_name", "proposal": "proposal_id", "rlevel": "reduction_level"}
DATEFMT = "%Y-%m-%d %H:%M:%S"


# ---------------------------------------------------------------------------
# Archive records
# ---------------------------------------------------------------------------

_QUERY = re.compile(r"\?[^\s'\"<>()]+")


def describe_error(exc: BaseException) -> str:
    """``Type: message`` for logs and ``failed`` lists, with every URL query string removed (C05): the
    signed S3 download URLs carry their signature in the query and stay valid for 48 h."""
    return _QUERY.sub("?<query removed>", f"{type(exc).__name__}: {exc}")


def frame_download_url(f: dict) -> str | None:
    """Signed URL: top-level ``url`` (legacy script) or ``version_set[0].url``."""
    if f.get("url"):
        return f["url"]
    return (f.get("version_set") or [{}])[0].get("url")


def frame_md5(f: dict) -> str | None:
    return f.get("md5") or (f.get("version_set") or [{}])[0].get("md5")


def frame_day(f: dict) -> str:
    """YYYYMMDD night of a frame: ``observation_day``, else parsed from the file
    name as the legacy script did (L91: ``site-cam-YYYYMMDD-...``; L90: ``..._YYYYMMDD_...``)."""
    day = f.get("observation_day") or f.get("day_obs")
    if day:
        return str(day).replace("-", "")[:8]
    name = f.get("filename") or f.get("basename") or ""
    for tok in name.replace("_", "-").split("-"):
        if len(tok) == 8 and tok.isdigit() and tok.startswith("20"):
            return tok
    raise ValueError(f"cannot tell the observing night of {name!r}")


def md5sum(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@dataclass
class Query:
    names: list[str]                    # every LCO OBJECT spelling of the target
    proposals: list[str]
    start: datetime
    end: datetime
    kind: str                           # "phot" | "spec"
    filters: list[str] | None = None    # phot: keep only these (primary_optical_element)
    cameras: list[str] | None = None    # camera prefixes kept: phot photometry.imaging_camera_prefixes,
                                        # spec the lcodb instruments.spectra (FLOYDS: en)
    camera_telescopes: dict | None = None   # phot: prefix -> telescope classes, e.g. {"kb": ["1m0"]}
    window_days: int = 365             # windows only bound each query; pagination does the rest
    page_size: int = 1000               # archive maximum with a token; URLs stay valid 48 h
    params: dict = field(default_factory=lambda: dict(DEFAULT_PARAMS))

    @property
    def rlevel(self) -> int:
        return 91 if self.kind == "phot" else 0

    def object_ok(self, f: dict) -> bool:
        """The frame's OBJECT must be one of the searched names — guards against
        the archive silently ignoring an unknown object-filter parameter."""
        obj = f.get("target_name", f.get("OBJECT"))
        return obj is None or obj in self.names

    def keep(self, f: dict) -> bool:
        name = str(f.get("filename") or "")
        if name.endswith("_cat.fits"):
            return False
        inst = str(f.get("instrument_id") or "").lower()
        if inst and self.cameras and not any(inst.startswith(str(c).lower()) for c in self.cameras):
            return False                # e.g. a SOAR Goodman spectrum under the same OBJECT name (C06)
        if self.kind == "spec":
            return f.get("configuration_type") in ("SPECTRUM", "ARC", "LAMPFLAT")
        if self.filters and f.get("primary_optical_element") not in self.filters:
            return False
        allowed = (self.camera_telescopes or {}).get(inst[:2])
        if inst and allowed and not any(str(f.get("telescope_id") or "").lower().startswith(t) for t in allowed):
            return False
        return f.get("configuration_type") in (None, "EXPOSE")


def windows(start: datetime, end: datetime, days: int) -> Iterator[tuple[datetime, datetime]]:
    t = start
    while t < end:
        t2 = min(end, t + timedelta(days=days))
        yield t, t2
        t = t2


def proposal_start(proposal: str, start: datetime) -> datetime:
    """No proposal has frames before its semester starts (lcodb's rule):
    search from max(start, semester start)."""
    from ava.lcodb.ingest import semester_start

    return max(start, semester_start(proposal))


def n_listing_requests(q: Query) -> int:
    """Minimum number of listing requests for ``q`` (one per name x proposal x window)."""
    return len(q.names) * sum(len(list(windows(proposal_start(p, q.start), q.end, q.window_days)))
                              for p in q.proposals)


def listing_pages(client, params: dict, page_size: int, stats: dict | None = None) -> Iterator[list[dict]]:
    """Yield every page of one archive ``/frames/`` listing, paged by ``offset`` with ``ordering=id``
    until a short page (B25).  The archive's ``next`` / ``count`` are estimates for some filters: following
    ``next`` stopped after the first page (ESO 511-30, 365-day windows: 4331 of 9151 frames), so ``next`` is
    ignored, as in ``lcodb.api.Client.frames``.  Each request adds 1 to ``stats["requests"]``."""
    from ava.lcodb import api

    params = dict(params, limit=page_size, offset=0, ordering="id")
    while True:
        d = client.get(f"{api.ARCHIVE}/frames/", dict(params))
        if stats is not None:
            stats["requests"] = stats.get("requests", 0) + 1
        res = d.get("results", []) or []
        yield res
        if len(res) < page_size:
            return
        params["offset"] += len(res)


def pages(client, q: Query, stats: dict) -> Iterator[list[dict]]:
    """Yield archive result pages for every (name, proposal, window); see ``listing_pages``."""
    p = q.params
    for name in q.names:
        for prop in q.proposals:
            for t0, t1 in windows(proposal_start(prop, q.start), q.end, q.window_days):
                params = {p["object"]: name, p["proposal"]: prop, p["rlevel"]: q.rlevel,
                          "start": t0.strftime(DATEFMT), "end": t1.strftime(DATEFMT),
                          "include_related_frames": "false"}
                yield from listing_pages(client, params, q.page_size, stats)


def lcodb_precheck(phot_db: Path | None, state_db: Path | None, q: Query, dest_dir: Path, *,
                   done: Callable[[str], bool] | None = None, now: datetime | None = None,
                   max_age_hours: float = 24.0) -> tuple[bool, str]:
    """Can the archive listing of ``q`` be skipped?  ``(True, why)`` when the lcodb photometry DB
    (``lcodb daily``, 01:00) was synced for every proposal of ``q`` within ``max_age_hours`` and
    lists no frame of ``q``'s names / proposals / level in [start, end) that ``q`` keeps and that is
    neither on disk nor already processed (``done``).  Anything else → ``(False, why)``: search the
    archive as usual.  Offline (local SQLite only).

    Safe because frames newer than the lcodb sync fall inside the next run's window as long as
    ``max_age_hours`` <= ``overlap_days`` x 24 (the task enforces it)."""
    if q.kind != "phot":
        return False, "only photometry is pre-checked"
    if not phot_db or not state_db or not Path(phot_db).exists() or not Path(state_db).exists():
        return False, "no lcodb DB"
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    oldest = (now - timedelta(hours=float(max_age_hours))).strftime("%Y-%m-%dT%H:%M:%S")
    props = list(q.proposals)
    ph = ",".join("?" * len(props))
    try:
        with closing(sqlite3.connect(f"file:{state_db}?mode=ro", uri=True)) as con:
            synced = dict(con.execute(f"SELECT proposal_id, synced_until FROM sync_state "
                                      f"WHERE proposal_id IN ({ph})", props).fetchall())
        stale = [pp for pp in props if not synced.get(pp) or str(synced[pp])[:19] < oldest]
        if stale:
            return False, f"lcodb not synced in the last {max_age_hours:g} h for {', '.join(stale)}"
        nh = ",".join("?" * len(q.names))
        with closing(sqlite3.connect(f"file:{phot_db}?mode=ro", uri=True)) as con:
            rows = con.execute(
                f"SELECT filename, basename, extension, day_obs, filter, instrument_id, telescope_id, obstype "
                f"FROM frames WHERE rlevel=? AND proposal_id IN ({ph}) AND object IN ({nh}) "
                f"AND date_obs >= ? AND date_obs < ?",
                (q.rlevel, *props, *q.names, q.start.strftime("%Y-%m-%dT%H:%M:%S"),
                 q.end.strftime("%Y-%m-%dT%H:%M:%S"))).fetchall()
    except sqlite3.Error as exc:
        return False, f"lcodb DB unreadable ({exc})"
    new = 0
    for fn, base, ext, day, filt, inst, tel, obstype in rows:
        f = {"filename": fn or f"{base}{ext or '.fits.fz'}", "observation_day": day, "primary_optical_element": filt,
             "instrument_id": inst, "telescope_id": tel, "configuration_type": obstype}
        if not q.keep(f):
            continue
        dest = Path(dest_dir) / frame_day(f) / f["filename"]
        if (dest.exists() and dest.stat().st_size > 0) or (done is not None and done(f["filename"])):
            continue
        new += 1
    if new:
        return False, f"lcodb lists {new} new frame(s)"
    return True, f"lcodb (synced for {', '.join(props)}) lists no new frame in the window"


# ---------------------------------------------------------------------------
# Run (search + download page by page)
# ---------------------------------------------------------------------------

_DOWNLOAD_LOCK = threading.Lock()   # one live download at a time per process


@dataclass
class RunResult:
    found: int = 0
    on_disk: int = 0
    missing: int = 0
    downloaded: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    capped: bool = False
    bytes: int = 0
    requests: int = 0
    other_objects: int = 0             # frames of other objects returned by the archive (filter ignored?)
    processed: int = 0                 # not on disk, but already processed (image deleted after processing)
    by_type: dict = field(default_factory=dict)


def fetch(url: str, dest: Path, limiter=None, timeout: float = 600.0) -> int:
    """Stream ``url`` to ``dest`` once (no auth header: the signed URL carries its own)."""
    import requests

    if limiter is not None:
        limiter.wait()
    n = 0
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
                n += len(chunk)
    return n


def fetch_checked(fetcher, url: str, dest: Path, md5: str | None, limiter=None) -> int:
    """Fetch ``url`` into ``dest.part``, md5-check it, rename it to ``dest``; bytes written.
    On any error the ``.part`` file is removed and the error raised.  Safe to run in threads."""
    part = dest.with_name(dest.name + ".part")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        n = fetcher(url, part, limiter)
        if md5 and md5sum(part) != md5:
            raise RuntimeError("md5 mismatch")
        part.replace(dest)
        return n
    except BaseException:
        part.unlink(missing_ok=True)
        raise


def fetch_many(fetcher, jobs: list, limiter=None, parallel: int = 1) -> Iterator[tuple]:
    """Run ``fetch_checked`` for every ``(key, url, dest, md5)`` of ``jobs``, ``parallel`` at a time
    (the signed URLs point at S3, not at the archive API: no archive request is spent).
    Yields ``(key, bytes, None)`` or ``(key, None, exception)`` in job order."""
    from concurrent.futures import ThreadPoolExecutor

    def one(job):
        key, url, dest, md5 = job
        try:
            return key, fetch_checked(fetcher, url, dest, md5, limiter), None
        except Exception as exc:  # noqa: BLE001 — reported per file
            return key, None, exc

    if max(1, int(parallel)) == 1 or len(jobs) < 2:
        yield from map(one, jobs)
        return
    with ThreadPoolExecutor(min(int(parallel), len(jobs))) as ex:
        yield from ex.map(one, jobs)


def run(client, q: Query, dest_dir: Path, *, live: bool, max_frames: int, data_id: str,
        verify_existing: bool = False, registry_db: Path | None = None, log=print,
        fetcher=None, done: Callable[[str], bool] | None = None, parallel: int = 1) -> RunResult:
    """Search the archive for ``q`` and, if ``live``, download missing frames
    (each page's files, ``parallel`` at a time, before the next page is requested), at most ``max_frames``.
    Not live: list only — no file is fetched (listing requests are still sent).
    ``done(filename)``: True for a frame already processed whose image was deleted
    (``ava.archive.cleanup``) — it is not downloaded again."""
    fetcher = fetcher or fetch   # looked up at call time (replaceable in tests)
    res, stats, seen, reg = RunResult(), {}, set(), []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    limiter = getattr(client, "limiter", None)
    with _DOWNLOAD_LOCK:
        try:
            for page in pages(client, q, stats):
                jobs, meta = [], {}
                for f in page:
                    fid = int(f["id"])
                    if not q.object_ok(f):
                        res.other_objects += 1
                        continue
                    if fid in seen or not q.keep(f):
                        continue
                    seen.add(fid)
                    res.found += 1
                    key = f.get("configuration_type") if q.kind == "spec" else f.get("primary_optical_element")
                    res.by_type[key] = res.by_type.get(key, 0) + 1
                    dest = Path(dest_dir) / frame_day(f) / f["filename"]
                    md5 = frame_md5(f)
                    if dest.exists() and dest.stat().st_size > 0 and not (
                            verify_existing and md5 and md5sum(dest) != md5):
                        res.on_disk += 1
                        continue
                    if done is not None and done(f["filename"]):
                        res.processed += 1
                        continue
                    res.missing += 1
                    if not live:
                        continue
                    if len(res.downloaded) + len(res.failed) + len(jobs) >= max_frames:
                        res.capped = True
                        continue
                    url = frame_download_url(f)
                    if not url:
                        res.failed[f["filename"]] = "RuntimeError: archive record has no download URL"
                        continue
                    jobs.append((fid, url, dest, md5))
                    meta[fid] = (f, dest, md5)
                for fid, n, exc in fetch_many(fetcher, jobs, limiter, parallel):
                    f, dest, md5 = meta[fid]
                    if exc is not None:
                        res.failed[f["filename"]] = describe_error(exc)
                        continue
                    res.downloaded.append(str(dest))
                    res.bytes += n
                    reg.append((fid, q.kind, f.get("configuration_type"), data_id, str(dest), md5,
                                1 if md5 else None, n, now))
                if res.capped:
                    log(f"reached the per-run cap of {max_frames} files — stopping the search")
                    break
        except Exception as exc:  # noqa: BLE001 — e.g. lcodb.api.Throttled
            res.failed["<search>"] = describe_error(exc)
            log(f"archive search stopped: {res.failed['<search>']}")
    res.requests = stats.get("requests", 0)
    if registry_db is not None and reg:
        with closing(sqlite3.connect(registry_db, timeout=60)) as con:
            con.executescript(LOCAL_FILES_DDL)
            con.executemany("INSERT OR REPLACE INTO local_files VALUES (?,?,?,?,?,?,?,?,?)", reg)
            con.commit()
    return res


# ---------------------------------------------------------------------------
# Spelling check (offline, from the lcodb DB if present)
# ---------------------------------------------------------------------------

def unlinked_names_near(db_path: Path, ra: float, dec: float, radius_arcmin: float = 10.0):
    """LCO OBJECT names linked to no AVA source within ``radius_arcmin`` of (ra, dec)."""
    import pandas as pd
    from astropy.coordinates import SkyCoord

    if not Path(db_path).exists():
        return pd.DataFrame(columns=["object", "n_phot", "n_spec", "sep_arcmin"])
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as con:
        t = pd.read_sql("SELECT object, obj_ra, obj_dec, n_phot, n_spec FROM target_link "
                        "WHERE ava_id IS NULL AND obj_ra IS NOT NULL", con)
    if t.empty:
        return t.assign(sep_arcmin=pd.Series(dtype=float))
    t["sep_arcmin"] = SkyCoord(t["obj_ra"].values, t["obj_dec"].values, unit="deg").separation(
        SkyCoord(ra, dec, unit="deg")).arcmin
    return t[t["sep_arcmin"] <= radius_arcmin].sort_values("n_phot", ascending=False).reset_index(drop=True)


def catalogued(catdir: Path) -> Callable[[str], bool]:
    """``done`` for photometry: the frame already has a SExtractor catalogue in ``catdir``."""
    def done(filename: str) -> bool:
        base = str(filename).split(".fits")[0]
        return (Path(catdir) / f"{base}_cat.fits").exists()
    return done
