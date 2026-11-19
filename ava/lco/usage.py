"""
ava.lco.usage — LCO time-usage plots (port of the legacy ``ava_lco_update.py``).

The legacy script ran every 6 hours and drew one figure per semester, ``lco_usage_<semester>.png``, shown on the
website's Live Updates page (``web/live.php``; published from ``web.usage_src``).  The legacy script itself was
not available for the port; this module reproduces its figures (two saved outputs, 2024A and 2024B):

* x: MJD from the start to the end of the semester;
* one curve per instrument class, the **cumulative hours charged**, each on its own y axis whose top is that
  class's allocation (1-m on the left axis, the others on extra axes on the right);
* a dashed black line from (start, 0) to (end, allocation): the even pace.  As every axis is scaled to its
  allocation, the one line serves every class;
* a marker at the last point of each curve; the title gives the elapsed days and, per class, used / allocated
  hours; the semester name inside the axes and "Last updated" at the bottom.

The filler programme of a key project (proposal ``KEY....f``) is drawn as its own curve, "(filler)" (legacy
"2m-Floyds-New").

Styles (``lco_usage.style``): ``percent`` (default: every curve on one axis, % of its allocation, calendar
dates), ``legacy`` (the layout above) and ``panels`` (one panel per class, in hours).

Input: per-proposal usage files
-------------------------------
One CSV file per LCO proposal, ``<input_dir>/<PROPOSAL>.csv`` (format documented in ``data/lco_usage/README.md``)::

    # proposal: KEY2026B-007
    # dummy: false
    # units: hours charged
    mjd,1M0-SCICAM-SINISTRO,2M0-FLOYDS-SCICAM,2M0-SCICAM-MUSCAT
    61285.0,3.2150,0.0000,0.0000
    61286.0,4.0100,1.0500,0.0000

* ``mjd``: time of the charge (normally the start of the UT day: one row per day);
* one column per LCO instrument class (the names the observation portal uses for allocations): hours charged
  in that row, **not** cumulative.  A missing class is 0; empty cells are 0; negative values are rejected.
* ``#`` lines before the header are metadata (``key: value``).  ``dummy: true`` marks synthetic files: plots
  drawn from them say so, and ``--publish`` refuses them.

Allocations (hours per proposal, semester and instrument class) come from ``lco_usage.allocations``
(``allocations.json``, the table of the LCO usage report).
"""

from __future__ import annotations

import filecmp
import json
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

MJD0 = date(1858, 11, 17)
MJD_RANGE = (50000.0, 80000.0)        # 1995 .. 2077: anything outside is a format error

# Website palette (web/assets/css/ava.css): Abyss, Ink, Gold, Sky, Aurora, Copper; plots sit on a white card.
SITE = dict(abyss="#0A1628", ink="#1A3A5C", gold="#D4A017", sky="#2D6A9F", aurora="#3A9E6E", copper="#C85A00",
            muted="#5B7189", grid="#E3E8EE")

# Curve colours: the legacy plot's (1-m green, FLOYDS red, MuSCAT3 purple, filler FLOYDS orange); fillers dashed.
DEFAULT_SERIES = [
    dict(instrument="1M0-SCICAM-SINISTRO", filler=False, label="1m", color="#6aa84f", marker="s"),
    dict(instrument="2M0-FLOYDS-SCICAM", filler=False, label="2m/Floyds", color="#e06666", marker="o"),
    dict(instrument="2M0-SCICAM-MUSCAT", filler=False, label="2m/MuSCAT3", color="#8e44ad", marker="^"),
    dict(instrument="2M0-SCICAM-SPECTRAL", filler=False, label="2m/Spectral", color="#3d85c6", marker="v"),
    dict(instrument="2M0-FLOYDS-SCICAM", filler=True, label="2m/Floyds (filler)", color="#f1a10f", marker="D",
         ls="--"),
    dict(instrument="1M0-SCICAM-SINISTRO", filler=True, label="1m (filler)", color="#38761d", marker="P",
         ls="--"),
]


# ---------------------------------------------------------------------------
# Semesters and dates
# ---------------------------------------------------------------------------

def mjd_of(d: date | datetime) -> float:
    if isinstance(d, datetime):
        d = d.astimezone(timezone.utc) if d.tzinfo else d
        return (d.date() - MJD0).days + (d.hour + d.minute / 60 + d.second / 3600) / 24
    return float((d - MJD0).days)


def semester_of(d: date | datetime) -> str:
    """LCO semester: A = Feb-Jul, B = Aug-Jan (January belongs to the previous year's B); 2017AB as one."""
    if date(2017, 2, 1) <= (d.date() if isinstance(d, datetime) else d) < date(2018, 2, 1):
        return "2017AB"
    if d.month == 1:
        return f"{d.year - 1}B"
    return f"{d.year}{'A' if d.month <= 7 else 'B'}"


def semester_bounds(sem: str) -> tuple[float, float]:
    """(start, end) MJD of a semester; end is exclusive (00:00 UT of the next semester's first day).

    A: 1 Feb - 31 Jul; B: 1 Aug - 31 Jan; 2017AB (the one long LCO semester): 1 Feb 2017 - 31 Jan 2018.
    """
    y, part = int(sem[:4]), sem[4:].upper()
    if part == "A":
        a, b = date(y, 2, 1), date(y, 8, 1)
    elif part == "B":
        a, b = date(y, 8, 1), date(y + 1, 2, 1)
    elif part == "AB":
        a, b = date(y, 2, 1), date(y + 1, 2, 1)
    else:
        raise ValueError(f"not an LCO semester: {sem!r}")
    return mjd_of(a), mjd_of(b)


def previous_semester(sem: str) -> str:
    y, part = int(sem[:4]), sem[4:].upper()
    if sem == "2018A":
        return "2017AB"
    if part == "B":
        return f"{y}A"
    return f"{y - 1}B"


def is_filler(proposal: str) -> bool:
    return proposal.lower().endswith("f")


# ---------------------------------------------------------------------------
# Usage files
# ---------------------------------------------------------------------------

@dataclass
class UsageFile:
    proposal: str
    data: pd.DataFrame                      # long: mjd, instrument, hours
    meta: dict = field(default_factory=dict)

    @property
    def dummy(self) -> bool:
        return str(self.meta.get("dummy", "false")).strip().lower() in ("true", "yes", "1")


def read_usage_file(path: Path) -> UsageFile:
    """Read one per-proposal usage file (format in the module docstring). Raises ValueError on a bad file."""
    path = Path(path)
    meta = {}
    with open(path) as f:
        for line in f:
            if not line.startswith("#"):
                break
            k, sep, v = line[1:].partition(":")
            if sep:
                meta[k.strip().lower()] = v.strip()
    df = pd.read_csv(path, comment="#", skipinitialspace=True)
    df.columns = [str(c).strip() for c in df.columns]
    if not len(df.columns) or df.columns[0].lower() != "mjd":
        raise ValueError(f"{path}: the first column must be 'mjd' (got {list(df.columns)[:1]})")
    df = df.rename(columns={df.columns[0]: "mjd"})
    inst = [c for c in df.columns[1:]]
    if not inst:
        raise ValueError(f"{path}: no instrument-class columns after 'mjd'")
    df.columns = ["mjd"] + [c.upper() for c in inst]
    if df.columns.duplicated().any():
        raise ValueError(f"{path}: repeated column names")
    df["mjd"] = pd.to_numeric(df["mjd"], errors="coerce")
    if df["mjd"].isna().any():
        raise ValueError(f"{path}: non-numeric or empty mjd")
    lo, hi = MJD_RANGE
    if ((df["mjd"] < lo) | (df["mjd"] > hi)).any():
        raise ValueError(f"{path}: mjd outside {lo:.0f}-{hi:.0f} (is it a JD or a date?)")
    for c in df.columns[1:]:
        v = pd.to_numeric(df[c], errors="coerce")
        bad = v.isna() & df[c].notna() & (df[c].astype(str).str.strip() != "")
        if bad.any():
            raise ValueError(f"{path}: non-numeric hours in column {c}")
        if (v < 0).any():
            raise ValueError(f"{path}: negative hours in column {c}")
        df[c] = v.fillna(0.0)
    long = df.melt(id_vars="mjd", var_name="instrument", value_name="hours")
    long = long[long["hours"] > 0].sort_values(["instrument", "mjd"]).reset_index(drop=True)
    proposal = meta.get("proposal") or path.stem
    return UsageFile(proposal=proposal, data=long, meta=meta)


def write_usage_file(path: Path, proposal: str, wide: pd.DataFrame, meta: dict | None = None) -> Path:
    """Write a usage file: ``wide`` has 'mjd' plus one column of hours per instrument class."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    head = {"proposal": proposal, "units": "hours charged per row (not cumulative)", **(meta or {})}
    cols = ["mjd"] + sorted(c for c in wide.columns if c != "mjd")
    with open(path, "w") as f:
        for k, v in head.items():
            f.write(f"# {k}: {v}\n")
        wide[cols].sort_values("mjd").to_csv(f, index=False, float_format="%.4f")
    return path


def load_usage(input_dir: Path, estimated: set | None = None) -> tuple[pd.DataFrame, set[str]]:
    """All ``*.csv`` usage files of a folder → (long table: proposal, mjd, instrument, hours; dummy proposals).

    ``estimated``, if given, collects the proposals whose file is marked ``estimated: true``.
    """
    frames, dummy = [], set()
    for p in sorted(Path(input_dir).glob("*.csv")):
        u = read_usage_file(p)
        frames.append(u.data.assign(proposal=u.proposal))
        if u.dummy:
            dummy.add(u.proposal)
        if estimated is not None and str(u.meta.get("estimated", "")).lower() == "true":
            estimated.add(u.proposal)
    if not frames:
        return pd.DataFrame(columns=["proposal", "mjd", "instrument", "hours"]), dummy
    return pd.concat(frames, ignore_index=True)[["proposal", "mjd", "instrument", "hours"]], dummy


def load_allocations(path: Path) -> pd.DataFrame:
    """allocations.json → proposal, semester, instrument, alloc, used (hours)."""
    rows = json.loads(Path(path).read_text())
    a = pd.DataFrame(rows)
    a["instrument"] = a["instrument"].str.upper()
    for c in ("alloc", "used"):
        a[c] = pd.to_numeric(a.get(c, 0.0), errors="coerce").fillna(0.0)
    return a[["proposal", "semester", "instrument", "alloc", "used"]]


# ---------------------------------------------------------------------------
# Dummy files (until the real daily breakdown exists)
# ---------------------------------------------------------------------------

def make_dummy(allocations: pd.DataFrame, out_dir: Path, until_mjd: float, seed: int = 2026,
               note: str = "") -> list[Path]:
    """Synthetic per-proposal files whose semester totals equal ``allocations.used``.

    Each (proposal, semester, instrument class) total is spread over the days of the semester up to
    ``until_mjd`` (the date the totals were taken): about 60 % of nights observe on the 1-m, 25 % on the 2-m,
    with gamma-distributed hours, normalised to the total (to 1e-4 h).  Deterministic for a given ``seed``.
    Files carry ``# dummy: true``.
    """
    rng = np.random.default_rng(seed)
    out = []
    for prop, ap in allocations.groupby("proposal", sort=True):
        rows = []
        for (sem, inst), g in ap.groupby(["semester", "instrument"], sort=True):
            total = float(g["used"].sum())
            if total <= 0:
                continue
            start, end = semester_bounds(sem)
            stop = min(end, np.floor(until_mjd) + 1)
            days = np.arange(start, stop)
            if not len(days):
                continue
            p_obs = 0.6 if inst.startswith("1M0") else 0.25
            w = (rng.random(len(days)) < p_obs) * rng.gamma(2.0, 1.0, len(days))
            if w.sum() == 0:
                w[rng.integers(len(days))] = 1.0
            h = np.round(w / w.sum() * total, 4)
            h[np.argmax(h)] += round(total - h.sum(), 4)
            rows.append(pd.DataFrame({"mjd": days, "instrument": inst, "hours": h}))
        if not rows:
            continue
        long = pd.concat(rows)
        wide = (long.pivot_table(index="mjd", columns="instrument", values="hours", aggfunc="sum", fill_value=0.0)
                .reset_index())
        wide = wide[wide.drop(columns="mjd").sum(axis=1) > 0]
        meta = {"dummy": "true",
                "note": note or "SYNTHETIC daily split of the semester totals (allocations.json); "
                                "replace with the real daily breakdown"}
        out.append(write_usage_file(Path(out_dir) / f"{prop}.csv", prop, wide, meta))
    return out


# ---------------------------------------------------------------------------
# Estimated files from the lcodb databases (exposure times, scaled to the charged totals)
# ---------------------------------------------------------------------------

def _tel_class(telescope_id: str) -> str:
    return str(telescope_id or "")[:3].upper()          # "1m0a" -> "1M0", "2m0a" -> "2M0"


def exposures_from_lcodb(photometry_db: Path | None, spectra_db: Path | None,
                         proposal_regex: str = r"^KEY") -> pd.DataFrame:
    """Open-shutter hours, exposures and blocks per proposal, UT day and instrument class, from the lcodb
    databases (read only).

    Each exposure is counted once: frames of several reduction levels share ``exp_key``, and the four MuSCAT
    channels of one exposure differ only in the camera (``ep01..ep04``; the longest channel is kept, as LCO
    charges the longest).  FLOYDS counts every frame (spectra, arcs, lamp flats).  A block (``block_id``: one
    scheduled observation, one slew and acquisition) is counted on the day of its first exposure.
    Class names: ``<1M0|2M0>-SCICAM-<SINISTRO|MUSCAT|SPECTRAL>`` and ``2M0-FLOYDS-SCICAM``.
    Returns proposal, mjd (start of the UT day), instrument, hours, n_exp, n_blocks.
    """
    import re
    import sqlite3
    from contextlib import closing

    cols = ["proposal", "mjd", "instrument", "hours", "n_exp", "n_blocks"]
    rx = re.compile(proposal_regex)
    frames = []
    if photometry_db is not None and Path(photometry_db).exists():
        with closing(sqlite3.connect(f"file:{photometry_db}?mode=ro", uri=True)) as con:
            f = pd.read_sql("SELECT proposal_id, exp_key, basename, camera_type, telescope_id, mjd_obs, exptime, "
                            "block_id FROM frames WHERE obstype = 'EXPOSE' AND exptime > 0", con)
        f["key"] = f["exp_key"].fillna(f["basename"]).str.replace(r"-ep\d\d-", "-ep-", regex=True)
        f["instrument"] = f["telescope_id"].map(_tel_class) + "-SCICAM-" + f["camera_type"].str.upper()
        frames.append(f)
    if spectra_db is not None and Path(spectra_db).exists():
        with closing(sqlite3.connect(f"file:{spectra_db}?mode=ro", uri=True)) as con:
            f = pd.read_sql("SELECT proposal_id, exp_key, basename, mjd_obs, exptime, block_id FROM frames "
                            "WHERE exptime > 0", con)
        f["key"] = "floyds:" + f["exp_key"].fillna(f["basename"])
        f["instrument"] = "2M0-FLOYDS-SCICAM"
        frames.append(f)
    if not frames:
        return pd.DataFrame(columns=cols)
    f = pd.concat(frames, ignore_index=True)
    f = f[f["proposal_id"].fillna("").map(lambda p: bool(rx.search(p))) & f["mjd_obs"].notna()]
    f = f.sort_values("exptime").drop_duplicates("key", keep="last")      # longest MuSCAT channel
    f["mjd"] = np.floor(f["mjd_obs"].astype(float))
    f["block"] = f["block_id"].astype("Int64").astype(str).where(f["block_id"].notna(), "k:" + f["key"])
    first = f.sort_values("mjd_obs").drop_duplicates(["proposal_id", "instrument", "block"])
    g = ["proposal_id", "mjd", "instrument"]
    out = f.groupby(g).agg(hours=("exptime", "sum"), n_exp=("key", "size"))
    out["hours"] /= 3600.0
    out["n_blocks"] = first.groupby(g).size().reindex(out.index, fill_value=0)
    return out.reset_index().rename(columns={"proposal_id": "proposal"})[cols]


def _fold_class(inst: str, allocated: list[str]) -> str:
    """Map a measured class onto the classes allocated to that proposal and semester.

    Unchanged if allocated; otherwise the allocated class on the same telescope class (the largest allocation
    first in ``allocated``).  So FLOYDS time folds into 2M0-SCICAM-SPECTRAL in 2014-2018 (the portal charged the
    2-m time to the Spectral camera then), and a MuSCAT on a 1-m into the 1-m class.
    """
    if inst in allocated:
        return inst
    same = [a for a in allocated if a[:3] == inst[:3]]
    return same[0] if same else inst


def _keyed(exposures: pd.DataFrame, allocations: pd.DataFrame, totals_mjd: float) -> list[tuple[dict, pd.DataFrame]]:
    """(key, daily rows) per (proposal, semester, class) of the proposals in ``allocations``; classes folded onto
    the allocated ones (:func:`_fold_class`).  Key: proposal, semester, instrument, used (charged at
    ``totals_mjd``; NaN if the totals do not list the semester) and the exposure hours / exposures / blocks
    before ``totals_mjd`` (exposure, n_exp, n_blocks)."""
    ex = exposures[exposures["proposal"].isin(set(allocations["proposal"]))].copy()
    for c in ("n_exp", "n_blocks"):
        if c not in ex:
            ex[c] = 0
    ex["semester"] = [semester_of(date.fromordinal(MJD0.toordinal() + int(m))) for m in ex["mjd"]]
    out = []
    for (prop, sem), g in ex.groupby(["proposal", "semester"]):
        a = allocations[(allocations["proposal"] == prop) & (allocations["semester"] == sem)]
        a = a.sort_values("alloc", ascending=False)
        allocated = list(dict.fromkeys(a["instrument"]))
        g = g.assign(instrument=[_fold_class(i, allocated) for i in g["instrument"]])
        for inst, gi in g.groupby("instrument"):
            b = gi[gi["mjd"] < totals_mjd]
            out.append((dict(proposal=prop, semester=sem, instrument=inst,
                             used=float(a.loc[a["instrument"] == inst, "used"].sum()) if len(a) else np.nan,
                             exposure=float(b["hours"].sum()), n_exp=int(b["n_exp"].sum()),
                             n_blocks=int(b["n_blocks"].sum())), gi))
    return out


def _model_hours(df: pd.DataFrame, inst: str, coefs: dict | None) -> np.ndarray:
    """Overhead model a·hours + b·exposures + c·blocks (``coefs[inst]`` = (a, b, c), b and c in hours), or the
    exposure hours alone for a class without a fit."""
    c = (coefs or {}).get(inst)
    h = df["hours"].to_numpy(float)
    if c is None:
        return h
    n = df["n_exp"].to_numpy(float) if "n_exp" in df else np.zeros(len(df))
    k = df["n_blocks"].to_numpy(float) if "n_blocks" in df else np.zeros(len(df))
    return c[0] * h + c[1] * n + c[2] * k


def fit_overheads(exposures: pd.DataFrame, allocations: pd.DataFrame, totals_mjd: float, since: str = "2020B",
                  min_points: int = 6) -> pd.DataFrame:
    """Fit charged = a·exposure hours + b·exposures + c·blocks per instrument class (non-negative least squares).

    One point per (proposal, semester) from ``since`` on (the lcodb databases are complete from 2020B), with
    something charged and something exposed before ``totals_mjd``.  Classes with fewer than ``min_points`` are not
    fitted (the estimate then uses charged / exposure hours).  Returns instrument, n, a, b_s (seconds per
    exposure), c_min (minutes per block), and the leave-one-out RMS of the model and of the flat factor (hours
    and fraction).
    """
    from scipy.optimize import nnls

    pts = pd.DataFrame([k for k, _ in _keyed(exposures, allocations, totals_mjd)])
    rows = []
    if pts.empty:
        return pd.DataFrame(columns=["instrument", "n", "a", "b_s", "c_min", "loo_model", "loo_flat",
                                     "loo_model_frac", "loo_flat_frac"])
    pts = pts[(pts["used"] > 0) & (pts["exposure"] > 0)
              & pts["semester"].map(lambda x: x != "2017AB" and x >= since)]
    for inst, g in pts.groupby("instrument"):
        if len(g) < min_points:
            continue
        X, y = g[["exposure", "n_exp", "n_blocks"]].to_numpy(float), g["used"].to_numpy(float)
        coef = nnls(X, y)[0]
        lm, lf = [], []
        for i in range(len(g)):
            m = np.arange(len(g)) != i
            lm.append(X[i] @ nnls(X[m], y[m])[0] - y[i])
            lf.append(y[m].sum() / X[m, 0].sum() * X[i, 0] - y[i])
        lm, lf = np.array(lm), np.array(lf)
        rows.append(dict(instrument=inst, n=len(g), a=coef[0], b_s=coef[1] * 3600, c_min=coef[2] * 60,
                         loo_model=np.sqrt(np.mean(lm ** 2)), loo_flat=np.sqrt(np.mean(lf ** 2)),
                         loo_model_frac=np.sqrt(np.mean((lm / y) ** 2)), loo_flat_frac=np.sqrt(np.mean((lf / y) ** 2))))
    return pd.DataFrame(rows)


def overhead_coefs(fit: pd.DataFrame) -> dict:
    """``fit_overheads`` table → {instrument: (a, b, c)} with b, c in hours per exposure / block."""
    return {r.instrument: (r.a, r.b_s / 3600, r.c_min / 60) for r in fit.itertuples()}


def estimate_charged(exposures: pd.DataFrame, allocations: pd.DataFrame, totals_mjd: float,
                     fallback_factor: dict | None = None,
                     coefs: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily charged hours, scaled so each (proposal, semester, class) adds up to its charged total.

    Each day's weight is the overhead model of its class (``coefs``: a·exposure hours + b·exposures + c·blocks,
    from :func:`fit_overheads`), or its exposure hours for a class without a fit.  The weights are then multiplied
    by charged / weight of that (proposal, semester, class), so the totals are exact and the shape follows the
    model (with the model the factor is ~1).
    ``allocations.used`` is the time charged up to ``totals_mjd`` (the date the totals were taken), so the factor
    of the semester in progress uses only days before it, and later days get the same factor.
    Only proposals in ``allocations`` are kept.  Days of a (proposal, semester) that the totals list with
    nothing charged to that class are dropped (factor 0: e.g. frames taken before a proposal's first semester).
    A (proposal, semester) missing from the totals (a semester newer than the table) gets the median factor of
    the class over all semesters (``fallback_factor`` overrides).
    Returns (long table: proposal, mjd, instrument, hours; factor table).
    """
    rows = []
    for key, gi in _keyed(exposures, allocations, totals_mjd):
        w = _model_hours(gi, key["instrument"], coefs)
        wsum = float(w[(gi["mjd"] < totals_mjd).to_numpy()].sum())
        used = key["used"]
        if not np.isfinite(used):
            k = np.nan                                  # semester not in the totals: median factor
        elif used <= 0:
            k = 0.0                                     # nothing charged here: drop
        else:
            k = used / wsum if wsum > 0 else np.nan
        rows.append((dict(proposal=key["proposal"], semester=key["semester"], instrument=key["instrument"],
                          used=0.0 if not np.isfinite(used) else used, exposure=key["exposure"], weight=wsum,
                          factor=k), gi.assign(hours=w)))
    fac = pd.DataFrame([r for r, _ in rows])
    med = fac[fac["factor"] > 0].groupby("instrument")["factor"].median().to_dict() if len(fac) else {}
    med.update(fallback_factor or {})
    out = []
    for i, (r, gi) in enumerate(rows):
        k = r["factor"] if np.isfinite(r["factor"]) else med.get(r["instrument"], np.nan)
        if not np.isfinite(k):
            k = 1.0
        fac.loc[i, "applied"] = k
        if k > 0:
            out.append(gi.assign(hours=gi["hours"] * k))
    est = pd.concat(out, ignore_index=True) if out else exposures.iloc[0:0]
    return est[["proposal", "mjd", "instrument", "hours"]], fac


def write_estimated(est: pd.DataFrame, out_dir: Path, note: str) -> list[Path]:
    """One file per proposal (``# estimated: true``) from :func:`estimate_charged`."""
    paths = []
    for prop, g in est.groupby("proposal"):
        wide = g.pivot_table(index="mjd", columns="instrument", values="hours", aggfunc="sum",
                             fill_value=0.0).reset_index()
        paths.append(write_usage_file(Path(out_dir) / f"{prop}.csv", prop, wide,
                                      {"dummy": "false", "estimated": "true", "note": note}))
    return paths


def update_estimated(cfg, out_dir: Path, totals_date: date | None = None, log=print) -> list[Path]:
    """Rewrite the estimated per-proposal files from the lcodb databases (read only; no LCO request).

    With ``lco_usage.overheads.model: fit`` the daily shape uses the fitted overhead model (:func:`fit_overheads`,
    written to ``overheads.txt``).  Also writes ``factors.txt`` (CSV: charged / exposure per proposal, semester and class) next to them.
    """
    from ava.lcodb.config import load_config
    st = settings(cfg)
    lc = load_config(cfg.lcodb_config_path)
    phot, spec = lc.db_path("photometry"), lc.db_path("spectra")
    alloc = load_allocations(st["allocations"])
    snaps = read_snapshots(st["snapshot_file"])
    if totals_date is not None:
        t = mjd_of(totals_date)
    elif len(snaps):                    # charged totals of the latest snapshot, and its time
        alloc, t = merge_allocations(alloc, snaps), float(snaps["mjd"].max())
    else:
        t = mjd_of(datetime.fromtimestamp(st["allocations"].stat().st_mtime, timezone.utc))
    d = date.fromordinal(MJD0.toordinal() + int(t))
    ex = exposures_from_lcodb(phot, spec)
    fit = None
    if st["overhead_model"] == "fit":
        fit = fit_overheads(ex, alloc, totals_mjd=t, since=st["overhead_since"], min_points=st["overhead_min_points"])
        for r in fit.itertuples():
            log(f"overheads {r.instrument}: {r.a:.3f} x exposure + {r.b_s:.1f} s/exposure + {r.c_min:.2f} min/block "
                f"(n={r.n}; leave-one-out {100 * r.loo_model_frac:.1f}% vs {100 * r.loo_flat_frac:.1f}% flat)")
    est, fac = estimate_charged(ex, alloc, totals_mjd=t, coefs=overhead_coefs(fit) if fit is not None else None)
    out_dir = Path(out_dir)
    for old in out_dir.glob("*.csv"):
        old.unlink()
    files = write_estimated(est, out_dir, note=f"ESTIMATED: daily exposure hours from {phot.name} / {spec.name}, "
                                               f"scaled per semester to the charged totals of "
                                               f"{st['allocations'].name} (taken {d})")
    fac.round(4).to_csv(out_dir / "factors.txt", index=False)
    if fit is not None:
        fit.round(4).to_csv(out_dir / "overheads.txt", index=False)
    log(f"estimated usage from lcodb: {len(files)} proposal file(s) in {out_dir}")
    return files


# ---------------------------------------------------------------------------
# Snapshots of the charged totals (observation portal), differenced between runs
# ---------------------------------------------------------------------------
# Each live run appends the portal's charged total per (proposal, semester, instrument class) to a log
# (``lco_usage.snapshots.file``).  The change between two snapshots is the time charged in that window, so the
# curve after the first snapshot is LCO's own accounting, overheads included, in 6-hour steps; before it the
# estimate (or a file) is kept, rescaled to end at the first snapshot's total.  Allocations come from the latest
# snapshot, so a new semester needs no edit of allocations.json.

SNAPSHOT_COLS = ["utc", "mjd", "proposal", "semester", "instrument", "alloc", "used"]
PORTAL_PROPOSALS = "https://observe.lco.global/api/proposals/"
_KEYS = ["proposal", "semester", "instrument"]


def parse_proposals(proposals: list[dict], prefix: str = "KEY") -> list[dict]:
    """Observation-portal proposal records → rows proposal, semester, instrument, alloc, used (hours).

    Same reading as the LCO usage report (``timeallocation_set``; used = std + rr + tc time used, alloc = std +
    rr + tc allocation).
    """
    rows = []
    for prop in proposals:
        pid = str(prop.get("id", ""))
        if not pid.startswith(prefix):
            continue
        for t in prop.get("timeallocation_set") or []:
            inst = t.get("instrument_type") or (t.get("instrument_types") or ["?"])[0]
            rows.append(dict(
                proposal=pid, semester=str(t.get("semester", "")), instrument=str(inst).upper(),
                alloc=float(sum(t.get(k) or 0 for k in ("std_allocation", "rr_allocation", "tc_allocation"))),
                used=float(sum(t.get(k) or 0 for k in ("std_time_used", "rr_time_used", "tc_time_used")))))
    return rows


def append_snapshot(path: Path, rows: list[dict], when: datetime, keep_all: bool = False) -> int:
    """Append one snapshot (rows stamped ``when``) to the log. Returns the number of rows written.

    To keep the log small only these rows are written, unless ``keep_all``: every row of the
    semester in progress at ``when`` (the record that the run happened), and any other row that is new or whose
    alloc / used changed since the last time it was logged (late charges or refunds of a past semester).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=SNAPSHOT_COLS[2:])
    if not keep_all and len(df):
        last = read_snapshots(path)
        if len(last):
            last = last.groupby(_KEYS, as_index=False).last()[_KEYS + ["alloc", "used"]]
            m = df.merge(last, on=_KEYS, how="left", suffixes=("", "_last"))
            changed = (m["used_last"].isna() | ((m["used"] - m["used_last"]).abs() > 1e-6)
                       | ((m["alloc"] - m["alloc_last"]).abs() > 1e-6))
            df = df[(changed | (m["semester"] == semester_of(when))).to_numpy()]
    df.insert(0, "mjd", round(mjd_of(when), 5))
    df.insert(0, "utc", when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    df.to_csv(path, mode="a", header=not path.exists() or path.stat().st_size == 0, index=False,
              float_format="%.4f")
    return len(df)


def read_snapshots(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=SNAPSHOT_COLS)
    s = pd.read_csv(path)
    missing = set(SNAPSHOT_COLS) - set(s.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    s["instrument"] = s["instrument"].str.upper()
    s["semester"] = s["semester"].astype(str)
    return s.sort_values(["mjd"] + _KEYS).reset_index(drop=True)


def snapshot_increments(snaps: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(increments: proposal, semester, instrument, mjd, hours — the change since the previous snapshot of the
    same key, refunds negative, zeros dropped, kept inside the key's semester; anchors: proposal, semester,
    instrument, t0, used0, t_last — the first snapshot of each key and the time of its last)."""
    if snaps.empty:
        return (pd.DataFrame(columns=_KEYS + ["mjd", "hours"]),
                pd.DataFrame(columns=_KEYS + ["t0", "used0", "t_last"]))
    s = snaps.sort_values(_KEYS + ["mjd"])
    s = s.assign(hours=s.groupby(_KEYS)["used"].diff())
    # a charge recorded after the semester ended (late accounting) stays in its own semester: last minute of it
    s["mjd"] = [min(m, semester_bounds(sem)[1] - 1 / 1440) for m, sem in zip(s["mjd"], s["semester"])]
    inc = s[s["hours"].notna() & (s["hours"].abs() > 1e-9)][_KEYS + ["mjd", "hours"]]
    first = s.groupby(_KEYS, as_index=False).first()
    anchors = first.rename(columns={"mjd": "t0", "used": "used0"})[_KEYS + ["t0", "used0"]]
    anchors["t_last"] = s.groupby(_KEYS)["mjd"].max().reindex(pd.MultiIndex.from_frame(anchors[_KEYS])).to_numpy()
    return inc.reset_index(drop=True), anchors


def join_snapshots(usage: pd.DataFrame, snaps: pd.DataFrame) -> pd.DataFrame:
    """Usage (proposal, mjd, instrument, hours) with the snapshots taking over between their first and last one.

    For each (proposal, semester, class) with snapshots: rows before the first snapshot ``t0`` are rescaled to
    add up to the charged total at ``t0`` (or, if there are none, that total is one row at ``t0``); rows from
    ``t0`` to the last snapshot are replaced by the snapshot increments; rows after the last snapshot are kept
    (the estimate fills the time since, e.g. before production starts).  Keys without snapshots are unchanged.
    """
    if snaps.empty:
        return usage
    inc, anchors = snapshot_increments(snaps)
    u = usage.copy()
    u["semester"] = [semester_of(date.fromordinal(MJD0.toordinal() + int(m))) for m in u["mjd"]]
    keep, add = np.ones(len(u), bool), []
    for a in anchors.itertuples(index=False):
        m = ((u["proposal"] == a.proposal) & (u["semester"] == a.semester) & (u["instrument"] == a.instrument)).to_numpy()
        before = m & (u["mjd"] < a.t0).to_numpy()
        keep &= ~(m & ~before & (u["mjd"] < a.t_last).to_numpy())   # replaced by the increments
        total = float(u.loc[before, "hours"].sum())
        if total > 0:
            u.loc[before, "hours"] *= a.used0 / total
        elif a.used0 > 0:
            add.append(dict(proposal=a.proposal, mjd=a.t0, instrument=a.instrument, hours=a.used0))
    out = pd.concat([u[keep].drop(columns="semester"), pd.DataFrame(add, columns=["proposal", "mjd", "instrument",
                                                                                  "hours"]),
                     inc[["proposal", "mjd", "instrument", "hours"]]], ignore_index=True)
    return out[out["hours"] != 0].sort_values(["proposal", "instrument", "mjd"]).reset_index(drop=True)


def merge_allocations(alloc: pd.DataFrame, snaps: pd.DataFrame) -> pd.DataFrame:
    """Allocations with the latest snapshot's alloc / used for every key it has (new semesters added)."""
    if snaps.empty:
        return alloc
    last = snaps.sort_values("mjd").groupby(_KEYS, as_index=False).last()[_KEYS + ["alloc", "used"]]
    rest = alloc.merge(last[_KEYS], on=_KEYS, how="left", indicator=True)
    rest = rest[rest["_merge"] == "left_only"].drop(columns="_merge")
    return pd.concat([rest, last], ignore_index=True)[_KEYS + ["alloc", "used"]]


SNAPSHOT_SEED = Path(__file__).resolve().parents[2] / "data" / "lco_usage" / "snapshots.csv"


def seed_snapshots(path: Path, seed: Path | None = None, log=print) -> bool:
    """Start a missing snapshot log from the repository's copy (the seed in git). Returns True if it copied.

    In production the live log sits outside the checkout (``lco_usage.snapshots.file`` on the data volume), so
    ``git pull`` never touches it; the first live snapshot copies the seed there, and the log grows on the VM only.
    """
    path, seed = Path(path), Path(seed or SNAPSHOT_SEED)
    if path.exists() or not seed.exists() or path.resolve() == seed.resolve():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(seed, path)
    log(f"snapshot: started {path} from the seed {seed}")
    return True


def take_snapshot(cfg, live: bool = False, now: datetime | None = None, log=print) -> int:
    """One snapshot of the charged totals: ONE paged GET of the portal's proposal list (read only).

    Dry run (default) only says what it would request.  Live: token from ``ava.lco.token`` (the token file, or
    the env var), the lcodb client (rate limit, retries); rows appended to ``lco_usage.snapshots.file``.
    """
    st = settings(cfg)
    now = now or datetime.now(timezone.utc)
    if not live:
        log(f"snapshot (dry run): would GET {PORTAL_PROPOSALS}?limit=200 (one paged request, read only) and append "
            f"the {st['snapshot_prefix']}* charged totals to {st['snapshot_file']}; nothing requested")
        return 0
    from ava.lcodb.api import Client
    from ava.lco.token import require_token

    token = require_token(ava_cfg=cfg)
    rows = parse_proposals(Client(token).proposals(), prefix=st["snapshot_prefix"])
    seed_snapshots(st["snapshot_file"], log=log)
    n = append_snapshot(st["snapshot_file"], rows, now)
    log(f"snapshot: {n} row(s) appended to {st['snapshot_file']}")
    return n


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

@dataclass
class Series:
    label: str
    color: str
    marker: str
    alloc: float
    mjd: np.ndarray            # step points (cumulative)
    cum: np.ndarray
    ls: str = "-"

    @property
    def used(self) -> float:
        return float(self.cum[-1]) if len(self.cum) else 0.0


def semester_series(usage: pd.DataFrame, allocations: pd.DataFrame, sem: str,
                    series_cfg: list[dict] | None = None, now_mjd: float | None = None) -> list[Series]:
    """Cumulative curves of one semester, one per configured class with an allocation or any use."""
    start, end = semester_bounds(sem)
    stop = end if now_mjd is None else min(end, now_mjd)
    u = usage[(usage["mjd"] >= start) & (usage["mjd"] < end)].copy()
    u["filler"] = u["proposal"].map(is_filler)
    a = allocations[allocations["semester"] == sem].copy()
    a["filler"] = a["proposal"].map(is_filler)
    out = []
    for s in series_cfg or DEFAULT_SERIES:
        inst, fill = str(s["instrument"]).upper(), bool(s.get("filler", False))
        alloc = float(a.loc[(a["instrument"] == inst) & (a["filler"] == fill), "alloc"].sum())
        g = u[(u["instrument"] == inst) & (u["filler"] == fill)].groupby("mjd")["hours"].sum().sort_index()
        if alloc <= 0 and g.empty:
            continue
        x = np.concatenate([[start], g.index.to_numpy(float)])
        y = np.concatenate([[0.0], np.cumsum(g.to_numpy(float))])
        if x[-1] < stop:                                 # flat to "now" (or the end of a past semester)
            x, y = np.append(x, stop), np.append(y, y[-1])
        out.append(Series(s.get("label", inst), s.get("color", "k"), s.get("marker", "o"), alloc, x, y,
                          s.get("ls", "-")))
    return out


STYLES = ("legacy", "percent", "panels")


ESTIMATED_NOTE = ("Daily curve estimated from the exposure times in the archive database, "
                  "scaled to the time charged by LCO")


def plot_semester(series: list[Series], sem: str, out: Path, now: datetime | None = None,
                  dummy: bool = False, formats=("png",), style: str = "percent",
                  note: str | None = None) -> list[Path]:
    """One semester's usage figure.  Returns the files written.

    ``style``: ``percent`` (default: one axis, % of each class's allocation used, calendar dates); ``legacy``
    (one y axis per class, each scaled to its allocation, as the old script); ``panels`` (one panel per class
    in hours, with its allocation and pace lines).
    """
    from ava.plots.webplots import serialized
    fn = {"legacy": _plot_semester, "percent": _plot_percent, "panels": _plot_panels}.get(style)
    if fn is None:
        raise ValueError(f"lco_usage.style must be one of {STYLES}, not {style!r}")
    return serialized(fn)(series, sem, Path(out), now or datetime.now(timezone.utc), dummy, formats, note)


def _mjd_dates(ax, start, end, mjd_top: bool = True):
    """Calendar dates on the bottom axis (MJD on the top one if ``mjd_top``)."""
    import matplotlib.dates as mdates
    epoch = np.datetime64("1858-11-17")
    to_d = lambda m: mdates.date2num(epoch + (np.asarray(m) * 86400).astype("timedelta64[s]"))  # noqa: E731
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    if not mjd_top:
        return to_d
    top = ax.secondary_xaxis("top", functions=(lambda d: d - to_d(0.0), lambda m: m + to_d(0.0)))
    top.set_xlabel("MJD", fontsize=12)
    top.tick_params(labelsize=11)
    return to_d


def _finish(fig, ax, sem, title, now, dummy, out, formats, note=None):
    import matplotlib.pyplot as plt
    if title:
        fig.suptitle(title, fontsize=17, y=0.995)
    fig.text(0.99, 0.005, f"Last updated: {now:%Y-%m-%d %H:%M} UTC", ha="right", va="bottom", fontsize=10,
             color=SITE["muted"])
    if note:
        fig.text(0.01, 0.005, note, ha="left", va="bottom", fontsize=10, color=SITE["muted"])
    if dummy:
        fig.text(0.5, 0.5, "DUMMY DATA", ha="center", va="center", rotation=30, fontsize=56, color="0.5",
                 alpha=0.25, zorder=10)
    out.parent.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in formats:
        p = out.with_suffix(f".{ext}")
        fig.savefig(p, dpi=150 if ext == "png" else None, bbox_inches="tight")
        paths.append(p)
    plt.close(fig)
    return paths


def _elapsed(sem, now):
    start, end = semester_bounds(sem)
    n = end - start
    e = float(np.clip(mjd_of(now) - start, 0, n))
    return start, end, n, e


def _site_style(size=13):
    """The website's look: Inter (else a plain sans-serif), Abyss text, Ink axes, ticks as the other web plots."""
    import matplotlib.pyplot as plt
    from ava.plots.webplots import _style
    _style()
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Inter", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": size, "text.color": SITE["abyss"], "axes.labelcolor": SITE["abyss"],
        "axes.edgecolor": SITE["ink"], "xtick.color": SITE["ink"], "ytick.color": SITE["ink"],
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
        "xtick.minor.visible": False, "xtick.top": False,
    })


def _plot_percent(series, sem, out, now, dummy, formats, note=None):
    _site_style(14)
    import matplotlib.pyplot as plt
    start, end, n, e = _elapsed(sem, now)
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    to_d = _mjd_dates(ax, start, end, mjd_top=False)
    ax.set_xlim(to_d(start), to_d(end))
    ax.grid(axis="y", color=SITE["grid"], lw=0.8)
    ax.set_axisbelow(True)
    ax.plot(to_d([start, end]), [0, 100], ls=":", color=SITE["ink"], lw=2, label="even pace")
    ax.axhline(100, color=SITE["gold"], lw=1.6, label="allocation")
    if e < n:
        ax.axvline(to_d(start + e), color=SITE["muted"], lw=1, ls="-", alpha=0.6)
        ax.text(to_d(start + e), 1.01, "today", transform=ax.get_xaxis_transform(), ha="center", va="bottom",
                fontsize=11, color=SITE["muted"])
    ymax, missing = 110.0, []
    for s in series:
        if s.alloc <= 0:
            missing.append(f"{s.label}: {s.used:.1f} h, no allocation")
            continue
        pct = 100 * s.cum / s.alloc
        ymax = max(ymax, pct.max() + 8)
        ax.step(to_d(s.mjd), pct, where="post", color=s.color, ls=s.ls, lw=2.6,
                label=f"{s.label}: {s.used:.1f} / {s.alloc:.0f} h ({pct[-1]:.0f}%)")
        ax.plot(to_d(s.mjd[-1]), pct[-1], s.marker, ms=9, mfc="white", mec=s.color, mew=2.2, zorder=4, clip_on=False)
    ax.set_ylim(0, ymax)
    ax.set_ylabel("Allocation used (%)")
    leg = ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=12, frameon=False,
                    title="Hours used / allocated", title_fontsize=12)
    leg._legend_box.align = "left"
    ax.set_title(f"Semester {sem}", loc="left", fontsize=18, fontweight="bold", color=SITE["abyss"], pad=24)
    sub = f"Day {e:.0f} of {n:.0f} ({100 * e / n:.0f}% of the semester)"
    if missing:
        sub += "  ·  " + "; ".join(missing)
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=13, color=SITE["muted"], va="bottom")
    return _finish(fig, ax, sem, None, now, dummy, out, formats, note)


def _plot_panels(series, sem, out, now, dummy, formats, note=None):
    _site_style(13)
    import matplotlib.pyplot as plt
    start, end, n, e = _elapsed(sem, now)
    k = max(len(series), 1)
    fig, axes = plt.subplots(k, 1, figsize=(10, 1.9 * k + 1.2), sharex=True, squeeze=False)
    axes = axes[:, 0]
    to_d = _mjd_dates(axes[0], start, end)
    for ax, s in zip(axes, series):
        top = max(s.alloc, s.used) * 1.12 or 1.0
        ax.set_ylim(0, top)
        if s.alloc > 0:
            ax.plot(to_d([start, end]), [0, s.alloc], "k--", lw=1.4)
            ax.axhline(s.alloc, color="0.6", lw=1)
        if e < n:
            ax.axvline(to_d(start + e), color="0.75", lw=1, ls=":")
        ax.step(to_d(s.mjd), s.cum, where="post", color=s.color, ls=s.ls, lw=2.6)
        ax.plot(to_d(s.mjd[-1]), s.used, s.marker, ms=9, mfc="white", mec=s.color, mew=2)
        txt = (f"{s.label}: {s.used:.1f} / {s.alloc:.0f} h ({100 * s.used / s.alloc:.0f}%)" if s.alloc > 0
               else f"{s.label}: {s.used:.1f} h (no allocation)")
        ax.text(0.01, 0.92, txt, transform=ax.transAxes, va="top", color=s.color, fontsize=13)
        ax.set_ylabel("h")
        ax.grid(axis="y", color="0.92")
    axes[-1].set_xlim(to_d(start), to_d(end))
    fig.subplots_adjust(hspace=0.08)
    return _finish(fig, axes[0], sem, f"{sem}: day {e:.0f} of {n:.0f} ({100 * e / n:.0f}% of the semester)",
                   now, dummy, out, formats, note)


def _plot_semester(series, sem, out, now, dummy, formats, note=None):
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
                         "mathtext.fontset": "dejavuserif", "font.size": 22, "axes.linewidth": 1.5})
    start, end = semester_bounds(sem)
    now_mjd = mjd_of(now)
    n_days = end - start
    elapsed = float(np.clip(now_mjd - start, 0, n_days))

    n_extra = max(len(series) - 1, 0)
    fig = plt.figure(figsize=(8 + 2.6 * n_extra, 9))
    width = 0.42 * 8 / (8 + 2.6 * n_extra) * 1.55
    ax = fig.add_axes([0.12 * 8 / (8 + 2.6 * n_extra) * 1.3, 0.12, width, 0.58])
    ax.set_xlim(start, end)
    ax.set_xlabel("MJD")
    ax.plot([start, end], [0, 1], "k--", lw=2.5, transform=ax.get_xaxis_transform(), zorder=5)

    title = [f"Elapsed Time: {elapsed:.0f}/{n_days:.0f} days ({100 * elapsed / n_days:.1f}%)"]
    for i, s in enumerate(series):
        a = ax if i == 0 else ax.twinx()
        if i > 1:
            a.spines["right"].set_position(("axes", 1.0 + 0.36 * (i - 1)))
        top = s.alloc if s.alloc > 0 else max(s.used * 1.1, 1.0)
        a.set_ylim(0, top)
        a.step(s.mjd, s.cum, where="post", color=s.color, lw=5, alpha=0.85)
        a.plot(s.mjd[-1], min(s.used, top), s.marker, ms=20, mfc="none", mec=s.color, mew=3, clip_on=False)
        a.set_ylabel(f"{s.label.replace('/', '-')} Observed / hr", color=s.color)
        a.tick_params(axis="y", colors=s.color)
        a.spines["left" if i == 0 else "right"].set_color(s.color)
        pct = 100 * s.used / s.alloc if s.alloc > 0 else float("nan")
        title.append(f"{s.label}: {s.used:5.1f}/{s.alloc:.0f} hr ({pct:4.1f}%)" if s.alloc > 0
                     else f"{s.label}: {s.used:5.1f} hr (no allocation)")
    if not series:
        ax.set_ylim(0, 1)
        title.append("no allocation or usage recorded")
    ax.set_title("\n".join(title), fontsize=24)
    ax.text(0.03, 0.88, sem, transform=ax.transAxes, fontsize=26)
    ax.text(0.97, 0.06, f"Last updated: {now:%Y-%m-%d %H:%M:%S} UTC", transform=ax.transAxes,
            ha="right", fontsize=14)
    if dummy:
        ax.text(0.5, 0.5, "DUMMY DATA", transform=ax.transAxes, ha="center", va="center", rotation=35,
                fontsize=48, color="0.5", alpha=0.35, zorder=10)
    out.parent.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in formats:
        p = out.with_suffix(f".{ext}")
        fig.savefig(p, dpi=150 if ext == "png" else None, bbox_inches="tight")
        paths.append(p)
    plt.close(fig)
    return paths


# ---------------------------------------------------------------------------
# Settings and the job
# ---------------------------------------------------------------------------

def settings(cfg) -> dict:
    c = cfg._raw.get("lco_usage", {}) or {}
    return dict(
        input_dir=cfg._resolve(c.get("input_dir") or "data/lco_usage/proposals"),
        allocations=cfg._resolve(c.get("allocations") or "data/lco_usage/allocations.json"),
        plots_dir=cfg._resolve(c.get("plots_dir") or "data/lco_usage/plots"),
        series=c.get("series") or DEFAULT_SERIES,
        formats=list(c.get("formats") or ["png"]),
        style=str(c.get("style") or "percent"),
        publish=bool(c.get("publish", True)),
        estimate_from_lcodb=bool(c.get("estimate_from_lcodb", False)),
        overhead_model=str((c.get("overheads") or {}).get("model") or "fit"),
        overhead_since=str((c.get("overheads") or {}).get("fit_since") or "2020B"),
        overhead_min_points=int((c.get("overheads") or {}).get("min_points") or 6),
        snapshot_mode=str((c.get("snapshots") or {}).get("mode") or "dry_run"),
        snapshot_file=cfg._resolve((c.get("snapshots") or {}).get("file") or "data/lco_usage/snapshots.csv"),
        snapshot_prefix=str((c.get("snapshots") or {}).get("prefix") or "KEY"),
        finalise_days=float(c.get("finalise_days", 7)),
        publish_dummy=bool(c.get("publish_dummy", False)),
    )


def run(cfg, semesters: list[str] | None = None, all_semesters: bool = False, input_dir: Path | None = None,
        plots_dir: Path | None = None, publish: bool | None = None, allow_dummy: bool | None = None,
        now: datetime | None = None, style: str | None = None, snapshot_live: bool | None = None,
        log=print) -> dict:
    """Read the usage files, draw ``lco_usage_<sem>.png`` for the chosen semesters, optionally publish them.

    First a snapshot of the charged totals is taken if ``snapshot_live`` (default: ``lco_usage.snapshots.mode``
    is ``live``; otherwise a dry-run line), and the snapshot log, if any, takes over from its first snapshot
    (:func:`join_snapshots`); its allocations replace allocations.json for the keys it has.

    Default semesters: the current one, and also the previous one during the first ``finalise_days`` of a new
    semester (its last charges are drawn and published; then it stays as it is).  ``all_semesters``: every
    semester with an allocation or any usage.
    ``publish`` (default ``lco_usage.publish``, true) copies changed PNGs to ``<web.data_dir>/usage/``, which the
    website's Live Updates page shows; a plot drawn from any dummy file is published only if ``allow_dummy``
    (default ``lco_usage.publish_dummy``).
    """
    st = settings(cfg)
    now = now or datetime.now(timezone.utc)
    take_snapshot(cfg, live=(st["snapshot_mode"] == "live") if snapshot_live is None else snapshot_live,
                  now=now, log=log)
    if st["estimate_from_lcodb"] and input_dir is None:
        update_estimated(cfg, st["input_dir"], log=log)
    publish = st["publish"] if publish is None else publish
    allow_dummy = st["publish_dummy"] if allow_dummy is None else allow_dummy
    in_dir, out_dir = Path(input_dir or st["input_dir"]), Path(plots_dir or st["plots_dir"])
    if not in_dir.is_dir():
        raise FileNotFoundError(f"LCO usage input folder not found: {in_dir}")
    est_props: set = set()
    usage, dummy_props = load_usage(in_dir, est_props)
    alloc = load_allocations(st["allocations"]) if st["allocations"].exists() else \
        pd.DataFrame(columns=["proposal", "semester", "instrument", "alloc", "used"])
    if not st["allocations"].exists():
        log(f"warning: no allocations file {st['allocations']}: axes scaled to the usage")
    log(f"{len(usage)} usage rows from {in_dir} ({len(set(usage['proposal']))} proposal(s); "
        f"dummy: {', '.join(sorted(dummy_props)) or 'none'})")
    snaps = read_snapshots(st["snapshot_file"])
    if not snaps.empty:
        usage = join_snapshots(usage, snaps)
        alloc = merge_allocations(alloc, snaps)
        log(f"{snaps['utc'].nunique()} snapshot(s) in {st['snapshot_file']} "
            f"({snaps['utc'].min()} .. {snaps['utc'].max()})")

    if all_semesters:
        sems = set(alloc["semester"])
        sems |= {semester_of(date.fromordinal(MJD0.toordinal() + int(m))) for m in usage["mjd"]}
        sems = sorted(s for s in sems if semester_bounds(s)[0] <= mjd_of(now))
    elif semesters:
        sems = list(semesters)
    else:
        sems = [semester_of(now)]
        prev = previous_semester(sems[0])
        if mjd_of(now) - semester_bounds(sems[0])[0] < st["finalise_days"]:
            log(f"new semester {sems[0]}: starting its plot; finalising {prev} "
                f"(first {st['finalise_days']:g} days)")
            sems.insert(0, prev)

    written, published = [], []
    for sem in sems:
        start, end = semester_bounds(sem)
        ser = semester_series(usage, alloc, sem, st["series"], now_mjd=mjd_of(now))
        props = set(usage.loc[(usage["mjd"] >= start) & (usage["mjd"] < end), "proposal"])
        is_dummy = bool(props & dummy_props)
        note = ESTIMATED_NOTE if props & est_props else None
        sn = snaps[snaps["semester"] == sem] if not snaps.empty else snaps
        if len(sn):
            note = f"LCO charged time, every 6 h since {sn['utc'].min()[:10]}" + \
                   ("; earlier days estimated from exposure times" if props & est_props else "")
        files = plot_semester(ser, sem, out_dir / f"lco_usage_{sem}", now=now, dummy=is_dummy, formats=st["formats"], style=style or st["style"], note=note)
        written += files
        log(f"{sem}: " + ", ".join(f"{s.label} {s.used:.1f}/{s.alloc:.0f} h" for s in ser)
            + (" [DUMMY]" if is_dummy else "") + f" -> {files[0]}")
        if publish:
            png = out_dir / f"lco_usage_{sem}.png"
            if is_dummy and not allow_dummy:
                log(f"{sem}: not published (drawn from dummy data; lco_usage.publish_dummy / --allow-dummy)")
            elif png.exists():
                dest = cfg._resolve(cfg._raw.get("web", {}).get("data_dir") or "web/data") / "usage" / png.name
                if not (dest.exists() and filecmp.cmp(png, dest, shallow=False)):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    tmp = dest.with_suffix(".png.tmp")
                    shutil.copy2(png, tmp)
                    tmp.replace(dest)
                    published.append(dest)
                    log(f"{sem}: published {dest}")
    return dict(semesters=sems, written=written, published=published, dummy=sorted(dummy_props))
