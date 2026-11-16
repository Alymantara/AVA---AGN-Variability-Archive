"""
ava.spectroscopy.products — website products of the FLOYDS spectra of one target.

1. ``arms``: the two arms of a spectrum (fringe-corrected EXTRACTED orders); figures in
   :mod:`ava.spectroscopy.webplots`.
2. ``hbeta_series``: Hβ fit of every reduced spectrum (:mod:`ava.spectroscopy.lines`), [O III] calibration when
   there is a series, nightly light curve; ``g_band``: the photometric g band over the same dates.
3. ``record``: per-exposure fits → ``spec_lines`` (lcodb spectra DB); nightly light curve → CSV; flux and
   variability summary → ``line_variability`` (AVA database).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ava.spectroscopy import lines as L

#: rest wavelengths marked on the spectrum plot


def arms(path) -> dict[str, pd.DataFrame]:
    """{'blue', 'red'}: observed-frame arm spectra (good bins) from EXTRACTED."""
    from astropy.io import fits

    d = fits.getdata(path, "EXTRACTED")
    out = {}
    for name, order in (("blue", 2), ("red", 1)):
        m = (d["order"] == order) & (d["mask"] == 0) & np.isfinite(d["flux_optimal"])
        w = np.asarray(d["wavelength"][m], float)
        o = np.argsort(w)
        out[name] = pd.DataFrame({"w": w[o], "f": np.asarray(d["flux_optimal"][m], float)[o],
                                  "e": np.asarray(d["fluxerror_optimal"][m], float)[o]})
    return out


def reduced_files(spec_dir: Path) -> list[Path]:
    return sorted(Path(spec_dir, "reduced").glob("*/*-e91-1d.fits*"))


def _header(path) -> dict:
    from astropy.io import fits

    h = fits.getheader(path)
    keys = ("DATE-OBS", "MJD-OBS", "OBJECT", "SITEID", "TELESCOP", "AIRMASS", "APERWID", "EXPTIME", "L1QSN1",
            "L1QSN2", "L1QSEE1", "L1QFLAGS")
    return {k: h.get(k) for k in keys}


def hbeta_series(files, z: float, settings: L.FitSettings | None = None, qc_good=("OK",),
                 min_series: int = 3, scale_limits=(0.2, 5.0)) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Per-exposure fits (+ [O III] calibration) and the nightly light curve."""
    s = settings or L.FitSettings()
    rows = []
    for f in files:
        h = _header(f)
        sp = L.blue_arm(f, z)
        r = L.fit_hbeta(sp, s)
        row = {"basename": Path(f).name.split("-e91")[0] + "-e00", "path": str(f), "MJD": h["MJD-OBS"],
               "night": Path(f).name.split("-")[2],          # LCO DAY-OBS (site-aware observing night)
               "qc": h["L1QFLAGS"], **{k: v for k, v in r.items() if k != "params"}}
        row["hb_integrated"] = L.integrated_hbeta(sp, r, s) if r.get("ok") else np.nan
        row["params_json"] = json.dumps({k: float(v) for k, v in r.get("params", {}).items()})
        rows.append(row)
    t = pd.DataFrame(rows)
    if t.empty:
        return t, pd.DataFrame(), {"n_spectra": 0}
    for c in ("hb_broad", "hb_broad_err", "oiii5007", "oiii5007_err", "cont5100", "cont5100_err"):
        if c not in t:
            t[c] = np.nan
    t["ok"] = t["ok"].fillna(False).astype(bool)
    good_qc = t["qc"].astype(str).isin(qc_good)
    t, ref = L.oiii_calibrate(t, good=good_qc, min_spectra=min_series, scale_limits=scale_limits)
    cal = bool(t["oiii_calibrated"].any())
    col = "hb_broad_cal" if cal else "hb_broad"
    night = L.nightly(t, col, f"{col}_err").rename(columns={col: "hb", f"{col}_err": "hb_err"})
    cont = L.nightly(t, "cont5100_cal" if cal else "cont5100", ("cont5100_cal" if cal else "cont5100") + "_err")
    if len(night):
        night = night.merge(cont.rename(columns={cont.columns[2]: "cont5100", cont.columns[3]: "cont5100_err"})
                            [["night", "cont5100", "cont5100_err"]], on="night", how="left")
    meta = {**ref, "oiii_calibrated": cal, "n_spectra": len(t), "n_good": int(t["good"].sum()),
            "n_nights": len(night)}
    return t, night, meta


def g_band(phot_dir: Path, target: str, mjd_range=None) -> pd.DataFrame:
    """Nightly g-band flux (mJy) from the shareable merged photometry CSV, if it exists."""
    f = Path(phot_dir) / f"{target}_LCO_merged_lightcurve.csv"
    if not f.exists():
        return pd.DataFrame()
    p = pd.read_csv(f)
    p = p[p["filter"] == "g"]
    if mjd_range is not None:
        p = p[p.MJD.between(*mjd_range)]
    if p.empty:
        return p
    p = p.assign(night=np.floor(p.MJD - 0.5).astype(int), w=1 / p.flux_err_random_mJy ** 2)
    g = p.groupby("night").apply(lambda h: pd.Series({
        "MJD": h.MJD.mean(), "flux": np.sum(h.w * h.flux_mJy) / h.w.sum(), "err": np.sqrt(1 / h.w.sum())}),
        include_groups=False).reset_index()
    return g


SPEC_LINES_DDL = """
CREATE TABLE IF NOT EXISTS spec_lines (     -- Hβ-region fit of each reduced spectrum (ava.spectroscopy.lines)
    basename TEXT, line TEXT, data_id TEXT, mjd REAL, frame_id INTEGER,
    flux REAL, flux_err REAL, flux_cal REAL, flux_cal_err REAL, flux_integrated REAL,
    oiii5007 REAL, oiii5007_err REAL, oiii_scale REAL, oiii_scale_err REAL,
    cont5100 REAL, cont5100_err REAL, cont5100_cal REAL, cont5100_cal_err REAL,
    fwhm_kms REAL, oiii_shift_A REAL, oiii_sigma_A REAL, chi2nu REAL, snr REAL,
    ok INTEGER, good INTEGER, qc TEXT, method TEXT, fitted_utc TEXT, params_json TEXT,
    PRIMARY KEY (basename, line)
);
"""

LINE_VAR_DDL = """
CREATE TABLE IF NOT EXISTS line_variability (   -- spectroscopic variability summary per target and line
    data_id TEXT, line TEXT, quantity TEXT,      -- quantity: flux ([O III]-calibrated if so) / cont5100
    n_spectra INTEGER, n_nights INTEGER, mjd_first REAL, mjd_last REAL,
    mean REAL, mean_err REAL, rms REAL, fvar REAL, fvar_err REAL, rmax REAL, snr_median REAL,
    oiii_calibrated INTEGER, oiii_ref REAL, fwhm_kms_median REAL, updated_utc TEXT, method TEXT,
    PRIMARY KEY (data_id, line, quantity)
);
"""


def record(t: pd.DataFrame, night: pd.DataFrame, meta: dict, data_id: str, spectra_db: Path, ava_db: Path,
           csv_path: Path, method: str) -> dict:
    """spec_lines (spectra DB), line_variability (AVA DB) and the nightly CSV."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(sqlite3.connect(f"file:{spectra_db}?mode=ro", uri=True)) as con:
        ids = dict(con.execute("SELECT basename, id FROM frames WHERE rlevel=0 AND basename IN (%s)"
                               % ",".join("?" * len(t)), list(t.basename)).fetchall()) if len(t) else {}
    g = lambda r, k: (None if k not in r or pd.isna(r[k]) else float(r[k]))  # noqa: E731
    rows = [(r.basename, "Hbeta_broad", data_id, g(r, "MJD"), ids.get(r.basename), g(r, "hb_broad"),
             g(r, "hb_broad_err"), g(r, "hb_broad_cal"), g(r, "hb_broad_cal_err"), g(r, "hb_integrated"),
             g(r, "oiii5007"), g(r, "oiii5007_err"), g(r, "oiii_scale"), g(r, "oiii_scale_err"), g(r, "cont5100"),
             g(r, "cont5100_err"), g(r, "cont5100_cal"), g(r, "cont5100_cal_err"), g(r, "hb_fwhm_kms"),
             g(r, "oiii_shift_A"), g(r, "oiii_sigma_A"), g(r, "chi2nu"), g(r, "hb_snr"), int(bool(r.ok)),
             int(bool(r.good)), r.qc, method, now, r.params_json) for _, r in t.iterrows()]
    with closing(sqlite3.connect(spectra_db, timeout=60)) as con:
        con.executescript(SPEC_LINES_DDL)
        con.executemany(f"INSERT OR REPLACE INTO spec_lines VALUES ({','.join('?' * 29)})", rows)
        con.commit()
    summ = {}
    for q, f, e in (("flux", "hb", "hb_err"), ("cont5100", "cont5100", "cont5100_err")):
        v = L.variability(night[f], night[e]) if len(night) else {"n": 0}
        summ[q] = v
    with closing(sqlite3.connect(ava_db, timeout=60)) as con:
        con.executescript(LINE_VAR_DDL)
        for q, v in summ.items():
            con.execute(f"INSERT OR REPLACE INTO line_variability VALUES ({','.join('?' * 19)})", (
                data_id, "Hbeta_broad", q, meta.get("n_spectra"), v.get("n"),
                float(night.MJD.min()) if len(night) else None, float(night.MJD.max()) if len(night) else None,
                v.get("mean"), v.get("mean_err"), v.get("rms"), v.get("fvar"), v.get("fvar_err"), v.get("rmax"),
                v.get("snr_median"), int(bool(meta.get("oiii_calibrated"))), meta.get("oiii_ref"),
                float(t.loc[t.good, "hb_fwhm_kms"].median()) if t.good.any() else None, now, method))
        con.commit()
    if len(night):
        out = night.rename(columns={"hb": "hbeta_flux", "hb_err": "hbeta_flux_err"}).assign(target=data_id)
        out["oiii_calibrated"] = bool(meta.get("oiii_calibrated"))
        out = out[["target", "MJD", "night", "n_exp", "hbeta_flux", "hbeta_flux_err", "cont5100", "cont5100_err",
                   "oiii_calibrated"]]
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w") as fh:
            fh.write(f"# {data_id}: FLOYDS broad Hbeta (erg/s/cm2) and 5100 A continuum (erg/s/cm2/A), nightly means;"
                     f" [O III]-calibrated: {bool(meta.get('oiii_calibrated'))}; method {method}; {now}\n")
            out.to_csv(fh, index=False, float_format="%.6g")
    return summ


# ---------------------------------------------------------------------------
# PrepSpec export (legacy ava_floyds_calibrate.py → PrepSpec_ava/)
# ---------------------------------------------------------------------------

def prepspec_name(target: str, path, arm: str) -> str:
    """Stable file name from the frame: <target>_<YYYYMMDD>_<site>_<frame>_<arm>.dat (does not change when
    new spectra arrive, unlike the legacy running index)."""
    parts = Path(path).name.split("-")          # ogg2m001-en06-20260915-0002-e91-1d.fits.fz
    return f"{target}_{parts[2]}_{parts[0][:3]}_{parts[3]}_{arm}.dat"


def export_prepspec(files, target: str, out_dir: Path, *, red_min_wavelength: float = 5300.0,
                    blue_max_wavelength: float | None = None, exclude_flags=()) -> dict:
    """Write every reduced spectrum as PrepSpec text files: one file per arm with three columns
    (wavelength Å, flux, error in erg/s/cm²/Å; the flux-calibrated, fringe-corrected EXTRACTED orders,
    not [O III]-scaled), and per arm a ``<target>_<arm>.hjd`` list of ``name MJD`` (mid-exposure), in time
    order.  The folder is rewritten each time: stale spectra are removed."""
    from astropy.io import fits

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = {"blue": [], "red": []}
    written, skipped = set(), []
    for f in files:
        h = fits.getheader(f)
        flags = str(h.get("L1QFLAGS", "OK"))
        if any(x in flags.split(",") for x in exclude_flags):
            skipped.append((Path(f).name, flags))
            continue
        mjd = float(h["MJD-OBS"]) + float(h.get("EXPTIME", 0.0)) / 2 / 86400.0
        a = arms(f)
        for arm, s in a.items():
            if arm == "red":
                s = s[s.w >= red_min_wavelength]
            elif blue_max_wavelength:
                s = s[s.w <= blue_max_wavelength]
            if len(s) < 50:
                skipped.append((Path(f).name, f"{arm}: {len(s)} bins"))
                continue
            name = prepspec_name(target, f, arm)
            head = (f"Spectrum for {target}: {h.get('OBJECT')} {h.get('SITEID')} {h.get('DATE-OBS')} "
                    f"(MJD mid {mjd:.5f}), {arm} arm, slit {h.get('APERWID')}\", QC {flags}\n"
                    f"source {Path(f).name} (EXTRACTED order {2 if arm == 'blue' else 1}, flux_optimal)\n"
                    "Column 1: Wavelength - Ang\nColumn 2: Flux - erg/s/cm^2/Ang\nColumn 3: Error - erg/s/cm^2/Ang")
            np.savetxt(out_dir / name, np.c_[s.w, s.f, s.e], fmt=("%.3f", "%.6e", "%.6e"), header=head)
            entries[arm].append((mjd, name))
            written.add(name)
    for arm, e in entries.items():
        with open(out_dir / f"{target}_{arm}.hjd", "w") as fh:
            for mjd, name in sorted(e):
                fh.write(f"{name} {mjd:.5f}\n")
    stale = [p for p in out_dir.glob(f"{target}_*.dat") if p.name not in written]
    for p in stale:
        p.unlink()
    return {"dir": str(out_dir), "blue": len(entries["blue"]), "red": len(entries["red"]),
            "skipped": skipped, "removed": len(stale)}
