"""
ava.spectroscopy.download — the FLOYDS frames a reduction needs, chosen from the lcodb spectra DB.

Follows the reasoning of ``__old_pipeline__/ava_floyds_sort.py``: for every science night
of a target, gather the AGN spectra with their arc and lamp flat, and the flux standard
of that night with *its* arc and lamp flat (the legacy ``all_standards/<night>`` folder).

Unlike the photometry download (an archive search by object name), the set is planned
**offline from the spectra DB** (``ava/lcodb``, kept current by ``lcodb daily``): the DB
already pairs every raw spectrum with its calibrations (view ``spectrum_calibs``) and its
standard (view ``spectrum_standards``: same slit > 2" > nearest, same block first, within
30 d).  So a dry run sends **no** archive request; a live run asks the archive only for the
signed download URLs of the missing frames, then fetches each file from its signed URL (S3, not
the archive API), md5-checks it against the DB value and registers it in ``local_files``.

URL lookup (decided 20 Nov 2026, to save archive requests): **one listing per observing request**
(``GET /frames/?request_id=R``, page of up to 1000; a FLOYDS request holds its spectra, arc, lamp
flat and their BANZAI products, 5 frames on average, 79 at most), done the first time a missing
frame of that request is met, so its URLs are used within minutes.  A frame with no
``request_id`` in the DB, or absent from its request's listing, falls back to one detail request
(``GET /frames/<id>/``).  A night with one target request and one standard request thus costs
2 archive requests instead of ~10.

Roles (column ``role``): ``science``, ``arc``, ``flat``, ``standard``, ``std_arc``,
``std_flat``; with ``archive_products`` also the archive's BANZAI ``-1d`` / ``-2d`` of the
science (``archive_1d``/``archive_2d``) and of the standard (``std_archive_1d``/``_2d``),
for comparison with our own reduction.

Layout (legacy-like):
  <spec_raw>/<target>/<YYYYMMDD>/                 science + its arcs / flats (raw, e00/a00/w00)
  <spec_raw>/standards/<YYYYMMDD>/                standards + their arcs / flats (shared by targets)
  <spec_root>/<target>/archive/<YYYYMMDD>/        archive -1d/-2d of the science
  <spec_root>/standards/archive/<YYYYMMDD>/       archive -1d/-2d of the standards
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ava.lco.download import LOCAL_FILES_DDL, fetch, fetch_many, md5sum

RAW_ROLES = ("science", "arc", "flat", "standard", "std_arc", "std_flat")
PRODUCT_ROLES = ("archive_1d", "archive_2d", "std_archive_1d", "std_archive_2d")


def _ro(db: Path):
    return closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True))


def science_nights(db: Path, ava_id: int, *, since: str | None = None, until: str | None = None,
                   nights: list[str] | None = None, select: str = "latest",
                   max_nights: int | None = None) -> list[str]:
    """Observing nights (YYYY-MM-DD, ``day_obs``) with raw science spectra of ``ava_id``.

    ``nights``: explicit list; otherwise those in [since, until], ``select="latest"`` (most
    recent first) or ``"oldest"``, at most ``max_nights``."""
    with _ro(db) as con:
        d = pd.read_sql("SELECT DISTINCT day_obs FROM frames WHERE ava_id=? AND rlevel=0 AND "
                        "obstype='SPECTRUM' AND COALESCE(is_standard,0)=0 AND day_obs IS NOT NULL "
                        "ORDER BY day_obs", con, params=(int(ava_id),))["day_obs"].tolist()
    if nights:
        want = {n if "-" in n else f"{n[:4]}-{n[4:6]}-{n[6:8]}" for n in map(str, nights)}
        return [n for n in d if n in want]
    if since:
        d = [n for n in d if n >= since[:10]]
    if until:
        d = [n for n in d if n <= until[:10]]
    if select == "latest":
        d = d[::-1]
    return d[:max_nights] if max_nights else d


def plan(db: Path, ava_id: int, nights: list[str], *, archive_products=True) -> pd.DataFrame:
    """One row per frame to have on disk for these nights: frame_id, basename, role, rlevel,
    day_obs, md5, request_id, filename, sci_id (the science spectrum it serves; a shared calibration
    keeps the first).  ``archive_products``: True (-1d and -2d), "1d", "2d" or False."""
    if not nights:
        return pd.DataFrame(columns=["frame_id", "basename", "filename", "role", "rlevel", "day_obs",
                                     "md5", "request_id", "sci_id", "side"])
    q = ",".join("?" * len(nights))
    with _ro(db) as con:
        sci = pd.read_sql(
            f"SELECT s.id AS sci_id, c.arc_id, c.flat_id, st.std_id, sc.arc_id AS std_arc_id, "
            f"sc.flat_id AS std_flat_id FROM frames s "
            f"LEFT JOIN spectrum_calibs c ON c.spec_id = s.id "
            f"LEFT JOIN spectrum_standards st ON st.sci_id = s.id "
            f"LEFT JOIN spectrum_calibs sc ON sc.spec_id = st.std_id "
            f"WHERE s.ava_id=? AND s.rlevel=0 AND s.obstype='SPECTRUM' AND COALESCE(s.is_standard,0)=0 "
            f"AND s.day_obs IN ({q}) ORDER BY s.date_obs", con, params=(int(ava_id), *nights))
        rows = []
        for r in sci.itertuples():
            for role, fid in (("science", r.sci_id), ("arc", r.arc_id), ("flat", r.flat_id),
                              ("standard", r.std_id), ("std_arc", r.std_arc_id), ("std_flat", r.std_flat_id)):
                if pd.notna(fid):
                    rows.append((int(fid), role, int(r.sci_id)))
        p = pd.DataFrame(rows, columns=["frame_id", "role", "sci_id"]).drop_duplicates("frame_id")
        if archive_products and len(p):
            raw = p[p.role.isin(["science", "standard"])]
            ids = ",".join(map(str, raw.frame_id))
            prod = pd.read_sql(f"SELECT id AS frame_id, raw_id, basename FROM frames WHERE rlevel=91 "
                               f"AND raw_id IN ({ids})", con)
            kinds = ("-1d", "-2d") if archive_products is True else (f"-{archive_products}",)
            prod = prod[prod.basename.str.endswith(kinds)]
            m = prod.merge(raw[["frame_id", "role", "sci_id"]].rename(columns={"frame_id": "raw_id"}), on="raw_id")
            m["role"] = (m.role.map({"science": "archive", "standard": "std_archive"}) + "_"
                         + m.basename.str[-2:])
            p = pd.concat([p, m[["frame_id", "role", "sci_id"]]], ignore_index=True).drop_duplicates("frame_id")
        ids = ",".join(map(str, p.frame_id)) or "NULL"
        has_req = "request_id" in {r[1] for r in con.execute("PRAGMA table_info(frames)")}
        req = "request_id" if has_req else "NULL AS request_id"
        f = pd.read_sql(f"SELECT id AS frame_id, basename, filename, extension, rlevel, day_obs, md5, obstype, "
                        f"{req} FROM frames WHERE id IN ({ids})", con)
    out = p.merge(f, on="frame_id", how="left")
    out["filename"] = out["filename"].fillna(out["basename"] + out["extension"].fillna(".fits.fz"))
    out["side"] = out.role.map(lambda r: "standard" if r.startswith("std") or r == "standard" else "target")
    order = {r: i for i, r in enumerate(RAW_ROLES + PRODUCT_ROLES)}
    return out.sort_values(["day_obs", "role"], key=lambda s: s.map(order) if s.name == "role" else s
                           ).drop(columns=["extension"]).reset_index(drop=True)


def destination(row, *, spec_raw_root: Path, spec_root: Path, target: str) -> Path:
    """Where a planned frame lives (see module docstring)."""
    night = str(row.day_obs).replace("-", "")
    product = row.role in PRODUCT_ROLES
    if row.side == "standard":
        base = (spec_root / "standards" / "archive") if product else (spec_raw_root / "standards")
    else:
        base = (spec_root / target / "archive") if product else (spec_raw_root / target)
    return base / night / row.filename


@dataclass
class SpecRunResult:
    planned: int = 0
    on_disk: int = 0
    missing: int = 0
    downloaded: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    capped: bool = False
    bytes: int = 0
    requests: int = 0
    by_role: dict = field(default_factory=dict)


def frame_url(client, frame_id: int) -> tuple[str, str | None]:
    """Signed download URL (and md5) of one archive frame: one archive request."""
    from ava.lcodb import api

    d = client.get(f"{api.ARCHIVE}/frames/{int(frame_id)}/")
    url = d.get("url") or (d.get("version_set") or [{}])[0].get("url")
    md5 = d.get("md5") or (d.get("version_set") or [{}])[0].get("md5")
    if not url:
        raise RuntimeError("archive record has no download URL")
    return url, md5


def request_urls(client, request_id: int, stats: dict | None = None) -> dict[int, tuple[str, str | None]]:
    """Signed URLs (and md5) of every frame of one observing request: one archive listing
    (more only if a request ever held over 1000 frames), ``{frame_id: (url, md5)}``."""
    from ava.lco.download import frame_download_url, frame_md5
    from ava.lcodb import api

    out = {}
    url = f"{api.ARCHIVE}/frames/"
    params = {"request_id": int(request_id), "limit": 1000, "include_related_frames": "false"}
    while url:
        d = client.get(url, params)
        if stats is not None:
            stats["requests"] = stats.get("requests", 0) + 1
        for f in d.get("results", []):
            u = frame_download_url(f)
            if u:
                out[int(f["id"])] = (u, frame_md5(f))
        url, params = d.get("next"), None      # `next` carries the query
    return out


def run(client, p: pd.DataFrame, *, spec_raw_root: Path, spec_root: Path, target: str, live: bool,
        max_frames: int, registry_db: Path | None = None, verify_existing: bool = False,
        fetcher=None, log=print, parallel: int = 1) -> SpecRunResult:
    """Download the missing frames of plan ``p`` (live) or only count them (dry run: no request).
    Live: first the signed URLs (one listing per request, see the module docstring), then the
    files, ``parallel`` at a time (S3, no archive request)."""
    fetcher = fetcher or fetch
    res = SpecRunResult(planned=len(p), by_role=p.role.value_counts().to_dict())
    reg, jobs, rows = [], [], {}
    by_request: dict[int, dict] = {}   # request_id -> {frame_id: (url, md5)}, listed on first need
    stats: dict = {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    for k, row in enumerate(p.itertuples()):
        dest = destination(row, spec_raw_root=spec_raw_root, spec_root=spec_root, target=target)
        if dest.exists() and dest.stat().st_size > 0 and not (verify_existing and row.md5
                                                              and md5sum(dest) != row.md5):
            res.on_disk += 1
            continue
        res.missing += 1
        if not live:
            continue
        if len(res.failed) + len(jobs) >= max_frames:
            res.capped = True
            continue
        try:
            rid = getattr(row, "request_id", None)
            hit = None
            if rid is not None and pd.notna(rid):
                rid = int(rid)
                if rid not in by_request:
                    by_request[rid] = None          # a failed listing is not repeated for its other frames
                    by_request[rid] = request_urls(client, rid, stats)
                if by_request[rid] is None:
                    raise RuntimeError(f"archive listing of request {rid} failed")
                hit = by_request[rid].get(int(row.frame_id))
            if hit is None:                     # no request id, or not in its listing: one detail request
                stats["requests"] = stats.get("requests", 0) + 1
                hit = frame_url(client, row.frame_id)
            url, md5 = hit
            md5 = row.md5 or md5
            jobs.append((k, url, dest, md5))
            rows[k] = (row, dest, md5)
        except Exception as exc:  # noqa: BLE001 — record, go on with the next frame
            res.failed[row.filename] = f"{type(exc).__name__}: {exc}"
            if type(exc).__name__ == "Throttled":
                log(f"archive throttled — stopping: {exc}")
                break
    for k, n, exc in fetch_many(fetcher, jobs, getattr(client, "limiter", None), parallel):
        row, dest, md5 = rows[k]
        if exc is not None:
            res.failed[row.filename] = f"{type(exc).__name__}: {exc}"
            continue
        res.downloaded.append(str(dest))
        res.bytes += n
        reg.append((int(row.frame_id), "spec", row.role, target if row.side == "target" else "standards",
                    str(dest), md5, 1 if md5 else None, n, now))
    res.requests = stats.get("requests", 0)
    if res.capped:
        log(f"reached the per-run cap of {max_frames} files")
    if registry_db is not None and reg:
        with closing(sqlite3.connect(registry_db, timeout=60)) as con:
            con.executescript(LOCAL_FILES_DDL)
            con.executemany("INSERT OR REPLACE INTO local_files VALUES (?,?,?,?,?,?,?,?,?)", reg)
            con.commit()
    return res
