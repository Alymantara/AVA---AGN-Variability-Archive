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


def fit_key(s: L.FitSettings, z: float, arm: str = "blue") -> str:
    """Identifies the fit settings (redshift, arm) a cached fit was made with; the blue arm keeps the key it had
    before the arm became a setting, so existing caches stay valid."""
    from dataclasses import asdict

    extra = {} if arm == "blue" else {"arm": arm}
    return json.dumps({**asdict(s), "z": round(float(z), 7), "measures": 4, **extra}, sort_keys=True, default=list)   # 4: + the [O III] lines


def _file_stamp(f) -> tuple[int, int]:
    st = Path(f).stat()
    return int(st.st_size), int(st.st_mtime)


def hbeta_series(files, z: float, settings: L.FitSettings | None = None, qc_good=("OK",),
                 min_series: int = 3, scale_limits=(0.2, 5.0),
                 cache: Path | None = None, arm: str = "blue") -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Per-exposure fits (+ [O III] calibration) and the nightly light curve.

    ``cache``: a per-target table (parquet) of the per-spectrum fits (fluxes, [O III] flux and wavelength
    offset, parameters).  A spectrum whose file (size, mtime) and fit settings are unchanged is taken from it;
    only new or changed spectra are fitted, so a daily update costs one fit per new spectrum.  The [O III]
    reference, scale factors and nightly light curve are always recomputed from the whole series."""
    s = settings or L.FitSettings()
    key = fit_key(s, z, arm)
    cached = {}
    if cache is not None and Path(cache).exists():
        try:
            c = pd.read_parquet(cache)
            cached = {r["path"]: r for r in c.to_dict("records") if r.get("fit_key") == key}
        except Exception:  # noqa: BLE001 — an unreadable cache is rebuilt
            cached = {}
    rows, n_fit = [], 0
    for f in files:
        size, mtime = _file_stamp(f)
        hit = cached.get(str(f))
        if hit is not None and hit.get("file_size") == size and hit.get("file_mtime") == mtime:
            rows.append(hit)
            continue
        n_fit += 1
        h = _header(f)
        sp = L.arm_spectrum(f, z, arm)
        r = L.fit_hbeta(sp, s)
        row = {"basename": Path(f).name.split("-e91")[0] + "-e00", "path": str(f), "MJD": h["MJD-OBS"],
               "night": Path(f).name.split("-")[2],          # LCO DAY-OBS (site-aware observing night)
               "qc": h["L1QFLAGS"], **{k: v for k, v in r.items() if k != "params"}}
        row["hb_integrated"] = L.integrated_hbeta(sp, r, s) if r.get("ok") else np.nan
        row.update(L.narrow_line_fluxes(sp, r, s) if r.get("ok") else L.narrow_line_fluxes(sp, {}, s))
        row["params_json"] = json.dumps({k: float(v) for k, v in r.get("params", {}).items()})
        row.update(file_size=size, file_mtime=mtime, fit_key=key)
        rows.append(row)
    t = pd.DataFrame(rows)
    if cache is not None and len(t):
        keep = [c for c in t.columns if not c.startswith(("oiii_scale", "hb_broad_cal", "cont5100_cal", "good",
                                                             "oiii_calibrated"))]
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
        t[keep].to_parquet(cache, index=False)
    t = t[[c for c in t.columns if not c.startswith(("oiii_scale", "hb_broad_cal", "cont5100_cal", "good",
                                                     "oiii_calibrated"))]]
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
    ccol = "cont5100_cal" if cal else "cont5100"
    cont = L.nightly(t, ccol, f"{ccol}_err")    # empty when 5100 Å is never covered (z ≈ 0.095–0.114, B06)
    if len(night):
        night = night.merge(cont.rename(columns={ccol: "cont5100", f"{ccol}_err": "cont5100_err"})
                            [["night", "cont5100", "cont5100_err"]], on="night", how="left")
    for key in ("oiii5007_int", "oiii4959_int"):       # [O III] lines as measured (not calibrated: they set it)
        if key in t and len(night):
            o = L.nightly(t.assign(**{f"{key}_err": t[f"{key}_err"].where(t[f"{key}_err"] > 0)}), key, f"{key}_err")
            if len(o):
                night = night.merge(o[["night", key, f"{key}_err"]], on="night", how="left")
    meta = {**ref, "arm": arm, "oiii_calibrated": cal, "n_spectra": len(t), "n_good": int(t["good"].sum()),
            "n_nights": len(night), "n_fitted": n_fit, "n_cached": len(t) - n_fit}
    return t, night, meta


def g_band(phot_dir: Path, target: str, mjd_range=None) -> pd.DataFrame:
    """Nightly g-band flux (mJy) from the shareable merged photometry CSV, if it exists."""
    f = Path(phot_dir) / f"{target}_LCO_merged_lightcurve.csv"
    if not f.exists():
        return pd.DataFrame()
    p = pd.read_csv(f, comment="#")
    qc = f.with_name(f.stem + "_qc" + f.suffix)
    if "flux_err_random_mJy" not in p and qc.is_file():
        # weights from the epoch-to-epoch error, kept in the QC file since Nov 2026 (the CSV has total errors)
        p = p.merge(pd.read_csv(qc, comment="#", usecols=["frame", "flux_err_random_mJy"]), on="frame", how="left")
    if "flux_err_random_mJy" not in p:
        p["flux_err_random_mJy"] = p["flux_err_mJy"]
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
        write_lightcurve_csv(out, csv_path,
                             f"{data_id}: FLOYDS broad Hbeta (erg/s/cm2) and 5100 A continuum (erg/s/cm2/A), nightly "
                             f"means; [O III]-calibrated: {bool(meta.get('oiii_calibrated'))}; method {method}; {now}")
    return summ


def write_lightcurve_csv(out: pd.DataFrame, csv_path: Path, header: str) -> None:
    """Nightly light-curve CSV: MJD to 1e-6 d, fluxes to 6 significant figures ("%.6g" alone rounded
    MJD 60123.456 to 60123.5; QC-0002)."""
    out = out.copy()
    out["MJD"] = out["MJD"].map(lambda x: f"{x:.6f}" if np.isfinite(x) else "")
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w") as fh:
        fh.write(f"# {header}\n")
        out.to_csv(fh, index=False, float_format="%.6g")


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


# ---------------------------------------------------------------------------
# Per-arm wavelength offsets (cached) and [O III]-calibrated mean and RMS spectra
# ---------------------------------------------------------------------------

#: rest-frame windows with narrow lines used to align each arm ([O III]; [O I] 6300 and [S II] 6716/6731), and
#: ranges masked inside them: the Hα + [N II] complex (strong, variable, sometimes clipped; Hα–[N II] 6583 is
#: 20.5 Å, an alias the correlation otherwise locks onto)
ALIGN_WINDOWS = {"blue": (4900.0, 5050.0), "red": (6250.0, 6800.0)}
ALIGN_MASK = {"blue": (), "red": ((6450.0, 6650.0),)}


def _highpass(f, k):
    from scipy.ndimage import median_filter

    return f - median_filter(f, k, mode="nearest")


def _xshift(ref, f, step, max_shift=6.0, weight=None):
    """Shift (Å) that best aligns ``f`` to ``ref`` (both on one grid of bin ``step``), searched within
    ±``max_shift``; ``weight`` (0/1 per bin) masks ranges.  Correlation at whole-pixel lags (no interpolation:
    shifting by fractions of a pixel with linear interpolation smooths the spectrum and biases the peak towards
    whole pixels) with a parabola through the peak for the sub-pixel part.
    aligned(λ) = f(λ + shift), i.e. correct wavelengths as λ − shift."""
    n = len(ref)
    wt = np.ones(n) if weight is None else np.asarray(weight, float)
    max_pix = max(int(np.ceil(max_shift / step)), 1)
    lags = np.arange(-max_pix, max_pix + 1)
    cc = []
    for lag in lags:          # sum_i ref[i] * f[i + lag] over the overlap
        if lag >= 0:
            cc.append(np.sum((wt * ref)[: n - lag] * f[lag:]))
        else:
            cc.append(np.sum((wt * ref)[-lag:] * f[: n + lag]))
    cc = np.asarray(cc)
    i = int(np.argmax(cc))
    d = 0.0
    if 0 < i < len(cc) - 1:
        den = cc[i - 1] - 2 * cc[i] + cc[i + 1]
        d = 0.5 * (cc[i - 1] - cc[i + 1]) / den if den != 0 else 0.0
    return float((lags[i] + d) * step)


def arm_dispersion(paths, arm: str) -> float:
    """Median observed bin width (Å) of an arm, from the first readable spectrum."""
    for p in paths:
        s = arms(p)[arm]
        if len(s) > 10:
            return float(np.median(np.diff(s.w.to_numpy())))
    raise ValueError(f"no {arm}-arm data to measure the dispersion")


def _align_weight(w, mask_ranges):
    wt = np.ones(len(w))
    for lo, hi in mask_ranges:
        wt[(w > lo) & (w < hi)] = 0.0
    return wt


def _arm_on_grid(path, arm, z, grid, red_min_observed=5300.0, red_max_observed=9050.0):   # limits: products.latest_spectrum.red_range
    s = arms(path)[arm]
    if arm == "red":
        s = s[(s.w >= red_min_observed) & (s.w <= red_max_observed)]
    w = s.w.to_numpy() / (1 + z)
    if len(w) < 20 or w.min() > grid[0] or w.max() < grid[-1]:
        return None, None
    return np.interp(grid, w, s.f.to_numpy()), np.interp(grid, w, s.e.to_numpy())


def arm_offsets(t: pd.DataFrame, z: float, spec_dir: Path, max_shift: float = 6.0, rebuild: bool = False,
                windows: dict | None = None, masks: dict | None = None, red_range=(5300.0, 9050.0),
                highpass_A: float = 60.0) -> pd.DataFrame:
    """Wavelength offset of every spectrum in each arm (Å, rest frame), by cross-correlating the high-passed
    narrow-line window (``ALIGN_WINDOWS``) with a stored reference template.

    Files in ``spec_dir``: ``spec_align_template.npz`` (the template: median of the aligned spectra, built once
    from the series, again with ``rebuild``, or when ``z`` or the alignment settings change) and ``spec_offsets.csv`` (one row per spectrum: shift_blue_A,
    shift_red_A, file size/mtime).  A new spectrum costs one cross-correlation; unchanged ones are read back.
    |shift| > ``max_shift`` → NaN (that arm of that spectrum is left out of the mean/RMS)."""
    spec_dir = Path(spec_dir)
    windows = {k: tuple(v) for k, v in (windows or ALIGN_WINDOWS).items()}
    masks = {k: tuple(tuple(x) for x in v) for k, v in (masks or ALIGN_MASK).items()}
    rmin, rmax = red_range
    tpl_f, off_f = spec_dir / "spec_align_template.npz", spec_dir / "spec_offsets.csv"
    # the settings the template and offsets depend on: a change rebuilds both (C07); a template written
    # before they were stored is rebuilt once
    import json
    settings = json.dumps({"windows": {k: list(v) for k, v in sorted(windows.items())},
                           "masks": {k: [list(x) for x in v] for k, v in sorted(masks.items())},
                           "max_shift": float(max_shift), "red_range": [float(rmin), float(rmax)],
                           "highpass_A": float(highpass_A)}, sort_keys=True)
    tpl = None
    if tpl_f.exists() and not rebuild:
        d = np.load(tpl_f)
        tpl = {k: d[k] for k in d.files}
        if abs(float(tpl.get("z", z)) - z) > 1e-6 or str(tpl.get("settings", "")) != settings:
            tpl = None
    grids, steps = {}, {}
    for arm, (lo, hi) in windows.items():
        steps[arm] = arm_dispersion(t["path"], arm) / (1 + z)        # measured bin width, rest Å
        grids[arm] = np.arange(lo - highpass_A, hi + highpass_A, steps[arm])
    if tpl is None:                                   # build the template: median, aligned twice
        tpl = {"z": np.array(z), "settings": np.array(settings)}
        for arm, g in grids.items():
            k = max(int(highpass_A / steps[arm]) | 1, 5)
            H = [_highpass(f, k) for f, _ in (_arm_on_grid(p, arm, z, g, rmin, rmax) for p in t["path"]) if f is not None]
            if len(H) == 0:
                continue
            H = np.array(H)
            m = (g > windows[arm][0]) & (g < windows[arm][1])
            wt = _align_weight(g[m], masks.get(arm, ()))
            ref = np.median(H, axis=0)
            for _ in range(2):
                sh = np.array([_xshift(ref[m], h[m], steps[arm], max_shift, wt) for h in H])
                sh = np.where(np.abs(sh) >= max_shift - steps[arm] / 4, 0.0, sh)
                ref = np.median([np.interp(g, g - x, h) for h, x in zip(H, sh)], axis=0)
            tpl[f"grid_{arm}"], tpl[f"ref_{arm}"] = g, ref
        spec_dir.mkdir(parents=True, exist_ok=True)
        np.savez(tpl_f, **tpl)
        old = pd.DataFrame()
    else:
        old = pd.read_csv(off_f) if off_f.exists() else pd.DataFrame()
    known = {r["path"]: r for r in old.to_dict("records")} if len(old) else {}
    rows = []
    for p in t["path"]:
        size, mtime = _file_stamp(p)
        k = known.get(str(p))
        if k is not None and k.get("file_size") == size and k.get("file_mtime") == mtime:
            rows.append(k)
            continue
        row = {"basename": Path(p).name.split("-e91")[0] + "-e00", "path": str(p), "file_size": size, "file_mtime": mtime}
        for arm in ("blue", "red"):
            g = tpl.get(f"grid_{arm}")
            f = None if g is None else _arm_on_grid(p, arm, z, g, rmin, rmax)[0]
            if f is None:
                row[f"shift_{arm}_A"] = np.nan
                continue
            st = float(np.median(np.diff(g)))
            m = (g > windows[arm][0]) & (g < windows[arm][1])
            x = _xshift(tpl[f"ref_{arm}"][m], _highpass(f, max(int(highpass_A / st) | 1, 5))[m], st, max_shift,
                        _align_weight(g[m], masks.get(arm, ())))
            row[f"shift_{arm}_A"] = x if abs(x) < max_shift - st / 4 else np.nan   # at the search edge: no match
        rows.append(row)
    off = pd.DataFrame(rows)
    off.to_csv(off_f, index=False, float_format="%.4f")
    return off


def mean_rms(t: pd.DataFrame, z: float, red_max_observed: float = 9050.0, red_min_observed: float = 5300.0,
             offsets: pd.DataFrame | None = None, match_resolution: bool = True,
             resolution_percentile: float = 90.0) -> dict:
    """Mean and RMS spectra (rest frame) per arm from the series ``t`` of :func:`hbeta_series`.

    Each good spectrum is scaled by its [O III] factor (``oiii_scale``; 1 when the series is not calibrated),
    shifted by its arm offset (``offsets`` from :func:`arm_offsets`; else the blue arm by the fitted [O III]
    shift) and, with ``match_resolution``, smoothed to a common line width: the ``resolution_percentile`` of the
    fitted [O III] widths (σ) — in a 6\" slit the seeing sets the width, which otherwise leaves the narrow lines in
    the RMS; the red arm gets the same spatial width (scaled by its dispersion).  Spectra are resampled onto one
    grid per arm, averaged per night (DAY-OBS) and over the nights: mean, RMS = standard deviation (ddof 1;
    Peterson 2004), noise = typical nightly error.  Any number of nights: with one, ``rms`` is None."""
    from scipy.ndimage import gaussian_filter1d

    use = t[t["good"]] if "good" in t and t["good"].any() else t[t.get("ok", True)]
    out = {"calibrated": bool(use.get("oiii_calibrated", pd.Series([False])).any()), "n_spectra": len(use)}
    if use.empty:
        return out
    off = offsets.set_index("path") if offsets is not None and len(offsets) else None
    sig = pd.to_numeric(use.get("oiii_sigma_A", pd.Series(dtype=float)), errors="coerce")
    target_sig = float(np.nanpercentile(sig, resolution_percentile)) if match_resolution and sig.notna().any() else None
    out["resolution_sigma_A"] = target_sig
    blue_step = None
    for arm in ("blue", "red"):
        specs = []
        for r in use.itertuples():
            s = arms(r.path)[arm]
            if arm == "red":
                s = s[(s.w >= red_min_observed) & (s.w <= red_max_observed)]
            if len(s) < 50:
                continue
            w = s.w.to_numpy() / (1 + z)
            if off is not None and r.path in off.index:
                x = off.loc[r.path, f"shift_{arm}_A"]
                if not np.isfinite(x):
                    continue                                   # implausible offset: left out of this arm
                w = w - float(x)
            elif arm == "blue" and np.isfinite(getattr(r, "oiii_shift_A", np.nan)):
                w = w - float(r.oiii_shift_A)
            k = float(getattr(r, "oiii_scale", 1.0)) if out["calibrated"] else 1.0
            sg = float(getattr(r, "oiii_sigma_A", np.nan))
            specs.append((str(r.night), w, k * s.f.to_numpy(), k * s.e.to_numpy(), sg))
        if not specs:
            continue
        lo, hi = max(x[1].min() for x in specs), min(x[1].max() for x in specs)
        step = float(np.median([np.median(np.diff(x[1])) for x in specs]))
        if hi - lo < 20 * step:
            continue
        grid = np.arange(lo, hi, step)
        if arm == "blue":
            blue_step = step
        disp = (step / blue_step) if arm == "red" and blue_step else 1.0   # red arm: more Å per spatial pixel
        nights: dict[str, list] = {}
        for n, w, f, e, sg in specs:
            fi = np.interp(grid, w, f)
            if target_sig and np.isfinite(sg) and target_sig > sg:
                fi = gaussian_filter1d(fi, disp * np.sqrt(target_sig ** 2 - sg ** 2) / step)
            nights.setdefault(n, []).append((fi, np.interp(grid, w, e)))
        nf = np.array([np.mean([x[0] for x in v], axis=0) for v in nights.values()])
        ne = np.array([np.sqrt(np.sum([x[1] ** 2 for x in v], axis=0)) / len(v) for v in nights.values()])
        n = len(nf)
        out[arm] = {"w": grid, "mean": nf.mean(axis=0), "rms": nf.std(axis=0, ddof=1) if n > 1 else None,
                    "noise": np.sqrt(np.mean(ne ** 2, axis=0)), "n_nights": n,
                    "n_spectra": sum(len(v) for v in nights.values())}
    return out
