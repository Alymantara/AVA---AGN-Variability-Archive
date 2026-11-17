"""Literature properties of the AVA AGN (table ``agn_literature``).

``data/literature/agn_properties.csv`` (one row per AGN, built from the AGN Black Hole Mass Database,
NED, Veron-Cetty & Veron 2010 and individual papers) is the source of truth; the table mirrors it.
Required columns::

    data_id, name, z, log_MBH, log_MBH_err, tau_hbeta_days, tau_hbeta_err, log_L5100, agn_type,
    key_reference, notes

Optional provenance columns (bibcodes unless stated): ``z_ref``, ``mbh_method``, ``mbh_ref``,
``tau_ref``, ``l5100_ref``, ``type_ref``.  Empty CSV cells are NULL — nothing is guessed.

:func:`import_literature` upserts the CSV into ``agn_literature`` (a row in the table is replaced
whole by its CSV row, so a value removed from the CSV is removed from the table).  With
``apply_to_agn`` it also copies z, log M_BH, log L5100 and the type into the curated ``agn`` columns
(``redshift``/``logm``/``l_5100``/``AGN_type`` with their ``*_cite``/``*_url``), only where the CSV has
a value and never over a non-AGN type (``NON_AGN_TYPES``).  Short citation text for ``*_cite``
comes from ``references.csv`` (bibcode, cite) next to the properties CSV; the same text is stored in
``agn_literature.<x>_cite`` for the website.  A reference that is not a bibcode (e.g. "SIMBAD otype")
is shown as plain text, without a link.
"""
from __future__ import annotations

import math
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REQUIRED = ["data_id", "name", "z", "log_MBH", "log_MBH_err", "tau_hbeta_days", "tau_hbeta_err",
            "log_L5100", "agn_type", "key_reference", "notes"]
OPTIONAL = ["z_ref", "mbh_method", "mbh_ref", "tau_ref", "l5100_ref", "type_ref"]
# short citation text stored next to each reference ("Kara et al. (2021)"), filled at import from references.csv
CITES = {"key_reference": "key_cite", "z_ref": "z_cite", "mbh_ref": "mbh_cite", "tau_ref": "tau_cite",
         "l5100_ref": "l5100_cite", "type_ref": "type_cite"}
REAL = {"z", "log_MBH", "log_MBH_err", "tau_hbeta_days", "tau_hbeta_err", "log_L5100"}
NON_AGN_TYPES = {"XRB"}          # keep in step with AVA_NON_AGN_TYPES (web/includes/config.php)

# literature column -> (agn value column, agn cite column, agn url column, reference column)
AGN_MAP = {
    "z": ("redshift", "red_cite", "red_url", "z_ref"),
    "log_MBH": ("logm", "logm_cite", "logm_url", "mbh_ref"),
    "log_L5100": ("l_5100", "l_5100_cite", "l_5100_url", "l5100_ref"),
}


def _ddl() -> str:
    cols = "".join(f'    "{c}" {"REAL" if c in REAL else "TEXT"},\n' for c in REQUIRED[1:] + OPTIONAL + list(CITES.values()))
    return ("CREATE TABLE IF NOT EXISTS agn_literature (   -- mirrors data/literature/agn_properties.csv\n"
            f'    data_id TEXT PRIMARY KEY,\n{cols}    imported_utc TEXT\n);')


def _val(v, real: bool):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if real:
        return float(v)
    s = str(v).strip()
    return s or None


def read_csv(path: Path) -> pd.DataFrame:
    """Read and validate the properties CSV (all cells as text; empty → NaN)."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    if df["data_id"].isna().any():
        raise ValueError(f"{path}: rows without data_id")
    dup = df["data_id"][df["data_id"].duplicated()].tolist()
    if dup:
        raise ValueError(f"{path}: duplicate data_id {dup}")
    for c in REAL & set(df.columns):
        bad = df[c].notna() & pd.to_numeric(df[c], errors="coerce").isna()
        if bad.any():
            raise ValueError(f"{path}: non-numeric {c} for {df.loc[bad, 'data_id'].tolist()}")
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in OPTIONAL:
        if c not in df.columns:
            df[c] = None
    return df[REQUIRED + OPTIONAL]


def is_bibcode(s) -> bool:
    return bool(re.match(r"^\d{4}\S{15}$", str(s or "").strip()))


def cite_of(ref, refs: dict[str, str]):
    """Short citation for a reference: references.csv text for a bibcode, else the text itself."""
    r = _val(ref, False)
    if r is None:
        return None
    return refs.get(r, r) if is_bibcode(r) else r


def read_references(path: Path) -> dict[str, str]:
    """bibcode → short citation text ("Kara et al. (2021)"), if ``references.csv`` exists."""
    if not path.exists():
        return {}
    r = pd.read_csv(path, dtype=str, keep_default_na=False)
    return {b.strip(): c.strip() for b, c in zip(r["bibcode"], r["cite"]) if b.strip() and c.strip()}


def plan_agn_updates(df: pd.DataFrame, agn: pd.DataFrame, refs: dict[str, str]) -> list[dict]:
    """Changes to the curated ``agn`` columns implied by the CSV: [{data_id, column, old, new}]."""
    cur = agn.set_index("data_id")
    out = []
    for r in df.itertuples(index=False):
        if r.data_id not in cur.index:
            continue
        a = cur.loc[r.data_id]
        new = {}
        for lit, (vcol, ccol, ucol, refcol) in AGN_MAP.items():
            v = getattr(r, lit)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            new[vcol] = float(v)
            ref = _val(getattr(r, refcol), False)
            if ref:
                new[ucol] = ref if is_bibcode(ref) else None
                new[ccol] = cite_of(ref, refs)
        t = _val(r.agn_type, False)
        if t and str(a.get("AGN_type") or "").strip() not in NON_AGN_TYPES:
            new["AGN_type"] = t
        for col, v in new.items():
            old = a.get(col)
            if v is None and (old is None or (isinstance(old, float) and math.isnan(old)) or old == ""):
                continue
            same = (isinstance(v, float) and old is not None and not (isinstance(old, float) and math.isnan(old))
                    and _isclose(old, v)) or (not isinstance(v, float) and str(old or "") == v)
            if not same:
                out.append(dict(data_id=r.data_id, column=col, old=old, new=v))
    return out


def _isclose(a, b) -> bool:
    try:
        return math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-9)
    except (TypeError, ValueError):
        return False


def import_literature(db: Path, csv: Path, apply_to_agn: bool = False, write: bool = False) -> dict:
    """Upsert ``csv`` into ``agn_literature`` (and optionally the curated ``agn`` columns).

    Returns {"rows", "unknown" (data_ids not in agn), "agn_updates" (planned/applied changes)}.
    Nothing is written unless ``write``.
    """
    df = read_csv(csv)
    refs = read_references(csv.parent / "references.csv")
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
        agn = pd.read_sql("SELECT data_id, redshift, red_cite, red_url, logm, logm_cite, logm_url, "
                          "l_5100, l_5100_cite, l_5100_url, AGN_type FROM agn WHERE data_id IS NOT NULL", con)
    unknown = sorted(set(df["data_id"]) - set(agn["data_id"]))
    df = df[~df["data_id"].isin(unknown)]
    updates = plan_agn_updates(df, agn, refs) if apply_to_agn else []
    if write:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cols = REQUIRED + OPTIONAL + list(CITES.values()) + ["imported_utc"]
        rows = [tuple(_val(getattr(r, c), c in REAL) for c in REQUIRED + OPTIONAL)
                + tuple(cite_of(getattr(r, c), refs) for c in CITES) + (now,)
                for r in df.itertuples(index=False)]
        with closing(sqlite3.connect(db, timeout=60)) as con:
            con.executescript(_ddl())
            have = {r[1] for r in con.execute("PRAGMA table_info(agn_literature)")}
            for c in cols:
                if c not in have:
                    con.execute(f'ALTER TABLE agn_literature ADD COLUMN "{c}" {"REAL" if c in REAL else "TEXT"}')
            q = ", ".join(f'"{c}"' for c in cols)
            set_ = ", ".join(f'"{c}" = excluded."{c}"' for c in cols[1:])
            con.executemany(f"INSERT INTO agn_literature ({q}) VALUES ({', '.join('?' * len(cols))}) "
                            f"ON CONFLICT(data_id) DO UPDATE SET {set_}", rows)
            for u in updates:
                con.execute(f'UPDATE agn SET "{u["column"]}" = ? WHERE data_id = ?', (u["new"], u["data_id"]))
            con.commit()
    return {"rows": len(df), "unknown": unknown, "agn_updates": updates}
