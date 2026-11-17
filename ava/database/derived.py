"""
ava.database.derived — AGN properties derived from the curated catalogue values.

For every AGN in the ``agn`` table, from ``logm``, ``l_5100`` (or ``logl``) and
``redshift``:

* bolometric correction at 5100 Å, Netzer (2019, MNRAS 488, 5185):
  k_bol = c (L5100 / 10^42 erg s^-1)^d, with c = 40, d = -0.2;
* L_bol = k_bol L5100 (``lbol_source = "l_5100"``); without L5100 the curated
  ``agn.logl`` is used as it is (``lbol_source = "logl"``);
* Eddington ratio L_bol / L_Edd, L_Edd = 1.26e38 (M / M_sun) erg s^-1;
* theoretical continuum lags of a standard irradiated thin disc, Fausnaugh et al.
  (2016, ApJ 821, 56, eq. 2):

      tau(lambda) = (1/c) (X k lambda / h c)^(4/3)
                    [ (G M / 8 pi sigma) (L_Edd / eta c^2) (3 + kappa) mdot_Edd ]^(1/3)

  with X = 4.97 (Wien-law value, following Tie & Kochanek 2018; Fausnaugh+16 use
  the flux-weighted 2.49), evaluated at the rest wavelengths of the
  observed filters, lambda / (1 + z), and returned in the observed frame (x (1 + z)).
  The lag between two filters is tau(lambda_2) - tau(lambda_1).

Results go to the pipeline-owned table ``agn_derived`` (one row per data_id); the
curated ``agn`` columns are never modified (see :mod:`ava.database.update`).
All settings: ``derived`` in the AVA config.
"""

from __future__ import annotations

import math
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# cgs constants
G = 6.674e-8
C = 2.99792458e10
H = 6.62607e-27
K_B = 1.380649e-16
SIGMA_SB = 5.670374e-5
M_SUN = 1.98847e33
DAY = 86400.0


@dataclass
class DerivedSettings:
    kbol_c: float = 40.0
    kbol_d: float = -0.2
    ledd_per_msun: float = 1.26e38
    disc_X: float = 4.97
    disc_kappa: float = 1.0
    disc_eta: float = 0.1
    lag_pairs: list = field(default_factory=lambda: [["u", "g"], ["g", "z"]])

    @classmethod
    def from_config(cls, cfg) -> "DerivedSettings":
        raw = cfg._raw.get("derived", {}) or {}
        d = cls()
        for k in ("kbol_c", "kbol_d", "ledd_per_msun", "disc_X", "disc_kappa", "disc_eta"):
            if k in raw:
                setattr(d, k, float(raw[k]))
        if raw.get("lag_pairs"):
            d.lag_pairs = [list(p) for p in raw["lag_pairs"]]
        return d

    @property
    def method(self) -> str:
        return (f"kbol={self.kbol_c:g}(L/1e42)^{self.kbol_d:g}; LEdd={self.ledd_per_msun:.3g}M; "
                f"F16 X={self.disc_X:g} kappa={self.disc_kappa:g} eta={self.disc_eta:g}")


def kbol_5100(log_l5100: float, s: DerivedSettings) -> float:
    """Netzer (2019) bolometric correction for L5100 (erg/s, log10)."""
    return s.kbol_c * 10 ** (s.kbol_d * (log_l5100 - 42.0))


def disc_lag_days(log_m: float, edd_ratio: float, lam_obs_A: float, lam0_obs_A: float, z: float,
                  s: DerivedSettings) -> float:
    """Observed-frame lag (days) of ``lam_obs_A`` relative to ``lam0_obs_A`` (Fausnaugh+16 eq. 2)."""
    m = 10 ** log_m * M_SUN
    l_edd = s.ledd_per_msun * 10 ** log_m
    mdot = edd_ratio * l_edd / (s.disc_eta * C ** 2)                       # g/s
    core = (G * m * mdot * (3 + s.disc_kappa) / (8 * math.pi * SIGMA_SB)) ** (1 / 3)
    radius = lambda lam_A: (s.disc_X * K_B * lam_A * 1e-8 / (1 + z) / (H * C)) ** (4 / 3) * core  # noqa: E731
    return (1 + z) * (radius(lam_obs_A) - radius(lam0_obs_A)) / C / DAY


def derive(agn: pd.DataFrame, wavelengths: dict[str, float], s: DerivedSettings) -> pd.DataFrame:
    """One row per AGN (``agn`` needs data_id, logm, l_5100, logl, redshift)."""
    rows = []
    for r in agn.itertuples(index=False):
        num = lambda v: float(v) if v is not None and str(v).strip() not in ("", "nan") and _isnum(v) else None  # noqa: E731
        logm, l5100, logl, z = num(r.logm), num(r.l_5100), num(r.logl), num(r.redshift)
        row = {"data_id": r.data_id, "logm": logm, "log_l5100": None, "kbol": None,
               "log_lbol": None, "lbol_source": None, "log_ledd": None, "eddington_ratio": None}
        if l5100 is not None and l5100 > 30:
            row.update(log_l5100=l5100, kbol=kbol_5100(l5100, s), lbol_source="l_5100")
            row["log_lbol"] = l5100 + math.log10(row["kbol"])
        elif logl is not None and logl > 30:
            row.update(log_lbol=logl, lbol_source="logl")
        if logm is not None and logm > 3:
            row["log_ledd"] = math.log10(s.ledd_per_msun) + logm
            if row["log_lbol"] is not None:
                row["eddington_ratio"] = 10 ** (row["log_lbol"] - row["log_ledd"])
        for a, b in s.lag_pairs:
            key = f"lag_{a}{b}_days"
            ok = row["eddington_ratio"] is not None and a in wavelengths and b in wavelengths
            row[key] = disc_lag_days(logm, row["eddington_ratio"], wavelengths[b], wavelengths[a], z or 0.0, s) \
                if ok else None
        rows.append(row)
    return pd.DataFrame(rows)


def _isnum(v) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _ddl(lag_cols: list[str]) -> str:
    lags = "".join(f"    {c} REAL,\n" for c in lag_cols)
    return ("CREATE TABLE IF NOT EXISTS agn_derived (   -- pipeline-owned (ava.database.derived)\n"
            "    data_id TEXT PRIMARY KEY, logm REAL, log_l5100 REAL, kbol REAL, log_lbol REAL,\n"
            "    lbol_source TEXT, log_ledd REAL, eddington_ratio REAL,\n"
            f"{lags}    method TEXT, updated_utc TEXT\n);")


def update_derived(db: Path, wavelengths: dict[str, float], s: DerivedSettings | None = None,
                   dry_run: bool = False) -> pd.DataFrame:
    """Recompute ``agn_derived`` for every AGN in ``db`` (idempotent). Returns the table."""
    s = s or DerivedSettings()
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
        agn = pd.read_sql("SELECT data_id, logm, l_5100, logl, redshift FROM agn "
                          "WHERE data_id IS NOT NULL AND data_id != ''", con)
    out = derive(agn, wavelengths, s)
    if dry_run or out.empty:
        return out
    out["method"] = s.method
    out["updated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lag_cols = [c for c in out.columns if c.startswith("lag_")]
    with closing(sqlite3.connect(db, timeout=60)) as con:
        con.executescript(_ddl(lag_cols))
        have = {r[1] for r in con.execute("PRAGMA table_info(agn_derived)")}
        for c in lag_cols:                      # a new lag pair adds its column
            if c not in have:
                con.execute(f'ALTER TABLE agn_derived ADD COLUMN "{c}" REAL')
        cols = list(out.columns)
        con.executemany(f"INSERT OR REPLACE INTO agn_derived ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        [tuple(None if (isinstance(v, float) and not math.isfinite(v)) else v for v in row)
                         for row in out.itertuples(index=False)])
        con.commit()
    return out


def filter_wavelengths(filter_dict: Path) -> dict[str, float]:
    """Filter name → wavelength (Å) from filter_dict.txt."""
    fd = pd.read_csv(filter_dict)
    return {str(f): float(w) for f, w in zip(fd["Filter"], fd["wave"]) if _isnum(w)}


def update_from_config(cfg, dry_run: bool = False) -> pd.DataFrame:
    plots = cfg._raw.get("plots", {}) or {}
    wl = filter_wavelengths(cfg._resolve(plots.get("filter_dict") or "data/reference/filter_dict.txt"))
    return update_derived(cfg.db_path, wl, DerivedSettings.from_config(cfg), dry_run=dry_run)
