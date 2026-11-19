#!/usr/bin/env python
"""Star-based accuracy of the absolute zero point, field by field, against catalogues AVA never uses.

For each field (<photometry_root>/<target>/pytics/absolute_zp.json + absolute_zp_stars.parquet):
AVA's calibrated mean magnitude of each comparison star (m_GSPC − res) is compared with

  * SDSS DR13 PSF u g r i z   (ESA Gaia archive external.sdssdr13_photoprimary; SDSS footprint)
  * Pan-STARRS1 DR2 mean PSF g r i z y  (MAST; dec > −30°)
  * SkyMapper DR2 PSF g r i z (ESA Gaia archive external.skymapperdr2_master; dec < +2°)

Per field, band and catalogue: the offset AVA − catalogue at the AGN's g−i (clipped linear fit in colour, as
tools/check_absolute_calibration.py), and the same for GSPC − catalogue on the same stars. AVA − GSPC measures
how well the pipeline reproduces its anchor; AVA − catalogue measures the scale against an independent system.
Across fields, the spread of AVA − catalogue is the field-to-field (systematic) error of the zero point; its mean
is the system offset to that catalogue (PS1 and SkyMapper are different filter systems: only the spread is
expected to be small).

Catalogue queries (one cone per field and catalogue, not the LCO archive) are cached in <out>/cache/.
Read-only on the photometry folders; writes <out>/star_check_stars.csv (per star) and star_check_fields.csv.

    python tools/abscal_validation/star_check_fields.py --out <work> [--targets NGC_5548 Mrk_509 ...]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import click
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from ava.config import cfg  # noqa: E402
from check_absolute_calibration import offset_at  # noqa: E402

BAND = dict(up="u", B="B", gp="g", V="V", rp="r", ip="i", zs="z", Y="Y")
SDSS_AB = dict(u=-0.04, g=0.0, r=0.0, i=0.0, z=0.02)          # SDSS -> AB
SDSS_BRIGHT = dict(u=13.0, g=14.0, r=14.0, i=14.0, z=12.5)     # saturation, conservative
PS1_BRIGHT = 14.5
SM_BRIGHT = 10.5
MAX_ERR = 0.03
# AVA band -> catalogue band
CAT_BANDS = dict(sdss=dict(u="u", g="g", r="r", i="i", z="z"),
                 ps1=dict(g="g", r="r", i="i", z="z", Y="y"),
                 skymapper=dict(g="g", r="r", i="i", z="z"))


def _gaia_query(adql: str) -> pd.DataFrame:
    from astroquery.gaia import Gaia
    Gaia.ROW_LIMIT = -1
    return Gaia.launch_job_async(adql).get_results().to_pandas()   # sync jobs stop at 2000 rows


def fetch(cat: str, ra: float, dec: float, rad: float, cache: Path) -> pd.DataFrame | None:
    """Stars of one catalogue in a cone, cached; columns ra, dec, <cat>_<band> (AB, quality-cut)."""
    f = cache / f"{cat}_{ra:.4f}_{dec:+.4f}_{rad:.3f}.csv"
    if f.exists():
        t = pd.read_csv(f)
    else:
        if cat == "ps1":
            if dec < -30:
                return None
            cols = ["raMean", "decMean", "nDetections", "iMeanKronMag"] + \
                [f"{b}MeanPSFMag{e}" for b in "grizy" for e in ("", "Err")]
            q = urllib.parse.urlencode({"ra": ra, "dec": dec, "radius": rad, "nDetections.gte": 5,
                                        "columns": "[" + ",".join(cols) + "]", "pagesize": 50000})
            with urllib.request.urlopen("https://catalogs.mast.stsci.edu/api/v0.1/panstarrs/dr2/mean.csv?" + q,
                                        timeout=300) as r:
                t = pd.read_csv(r)
        elif cat == "sdss":
            t = _gaia_query("SELECT ra, dec, type, mode, clean, " + ", ".join(
                f"psfmag_{b}, psfmagerr_{b}" for b in "ugriz") + " FROM external.sdssdr13_photoprimary "
                f"WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {rad})) AND type=6 AND psfmag_r < 20")
        elif cat == "skymapper":
            if dec > 2:
                return None
            t = _gaia_query("SELECT raj2000, dej2000, flags, nimaflags, class_star, " + ", ".join(
                f"{b}_psf, e_{b}_psf, {b}_ngood" for b in "griz") + " FROM external.skymapperdr2_master "
                f"WHERE 1=CONTAINS(POINT('ICRS', raj2000, dej2000), CIRCLE('ICRS', {ra}, {dec}, {rad})) AND i_psf < 19")
        else:
            raise ValueError(cat)
        cache.mkdir(parents=True, exist_ok=True)
        t.to_csv(f, index=False)
        time.sleep(1.0)
    if t.empty:
        return t
    out = pd.DataFrame()
    if cat == "ps1":
        t = t.replace(-999.0, np.nan)
        t = t[(t["iMeanPSFMag"] - t["iMeanKronMag"]) < 0.05]          # point sources
        out["ra"], out["dec"] = t["raMean"], t["decMean"]
        for b in "grizy":
            m, e = t[f"{b}MeanPSFMag"], t[f"{b}MeanPSFMagErr"]
            out[f"ps1_{b}"] = np.where((m > PS1_BRIGHT) & (e < MAX_ERR), m, np.nan)
    elif cat == "sdss":
        t = t[(t["mode"] == 1) & (t["clean"] == 1) & (t["type"] == 6)]
        out["ra"], out["dec"] = t["ra"], t["dec"]
        for b, off in SDSS_AB.items():
            m, e = t[f"psfmag_{b}"], t[f"psfmagerr_{b}"]
            out[f"sdss_{b}"] = np.where((m > SDSS_BRIGHT[b]) & (e < MAX_ERR), m + off, np.nan)
    else:
        t = t[(t["flags"] == 0) & (t["nimaflags"] == 0) & (t["class_star"] > 0.9)]
        out["ra"], out["dec"] = t["raj2000"], t["dej2000"]
        for b in "griz":
            m, e = t[f"{b}_psf"], t[f"e_{b}_psf"]
            out[f"skymapper_{b}"] = np.where((m > SM_BRIGHT) & (e < MAX_ERR) & (t[f"{b}_ngood"] >= 1), m, np.nan)
    return out.reset_index(drop=True)


MATCH_ARCSEC = 2.0   # reference positions are Gaia (epoch 2016); SDSS/PS1/SkyMapper epochs differ by 5-15 yr


def field_stars(target: str, cache: Path, cats) -> pd.DataFrame:
    """One row per comparison star, band and catalogue: colour c (g-i), AVA − catalogue and GSPC − catalogue."""
    ph = cfg.phot_dir(target)
    zpj = json.loads((ph / "pytics/absolute_zp.json").read_text())
    zs = pd.read_parquet(ph / "pytics/absolute_zp_stars.parquet")
    ref = pd.read_csv(ph / "reference_stars.csv")
    ra0, dec0 = float(np.median(ref["ra"])), float(np.median(ref["dec"]))
    c0 = SkyCoord(ra0, dec0, unit="deg")
    cr = SkyCoord(ref["ra"], ref["dec"], unit="deg")
    rad = float(np.ceil((c0.separation(cr).deg.max() + 0.01) * 100) / 100)
    for cat in cats:
        t = fetch(cat, ra0, dec0, rad, cache)
        if t is None or t.empty:
            continue
        i, d, _ = cr.match_to_catalog_sky(SkyCoord(t["ra"], t["dec"], unit="deg"))
        for col in [c for c in t.columns if c.startswith(cat + "_")]:
            ref[col] = np.where(d.arcsec < MATCH_ARCSEC, t[col].to_numpy(float)[i], np.nan)
    out = []
    for f, b in BAND.items():
        if f not in zpj or f"lco_{b}" not in ref:
            continue
        s = zs[zs["filter"] == f][["star_id", "res", "c", "rms_star"]].merge(ref, on="star_id")
        s = s[s["rms_star"] < 0.05]
        cal = s[f"lco_{b}"] - s["res"]                     # AVA calibrated mean magnitude
        for cat in cats:
            col = f"{cat}_{CAT_BANDS[cat].get(b)}"
            if col not in s:
                continue
            k = np.isfinite(s[col]) & np.isfinite(cal)
            out.append(pd.DataFrame(dict(target=target, ra=ra0, dec=dec0, filter=f, band=b, cat=cat,
                                         agn_colour=zpj[f]["agn_colour"], star_id=s.loc[k, "star_id"],
                                         c=s.loc[k, "c"], mag=s.loc[k, col],
                                         ava=(cal - s[col])[k], gspc=(s[f"lco_{b}"] - s[col])[k])))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def system_transforms(S: pd.DataFrame, deg: int = 2) -> dict:
    """Per catalogue and band: GSPC − catalogue as a clipped polynomial in g−i, pooled over all fields.
    This is the filter-system difference (large for PS1 and SkyMapper g); removing it leaves field errors."""
    T = {}
    for (cat, b), g in S.groupby(["cat", "band"]):
        x, y = g["c"].to_numpy(float), g["gspc"].to_numpy(float)
        ok = np.isfinite(x) & np.isfinite(y) & (x > -0.5) & (x < 3.0)
        if ok.sum() < 20:
            continue
        keep = ok.copy()
        for _ in range(5):
            p = np.polyfit(x[keep], y[keep], deg)
            r = y - np.polyval(p, x)
            sd = 1.4826 * np.median(np.abs(r[keep]))
            keep = ok & (np.abs(r) < 3 * max(sd, 0.005))
        T[(cat, b)] = p
    return T


def field_offsets(S: pd.DataFrame, T: dict, min_stars: int = 6) -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(1)
    for (t, f, cat), g in S.groupby(["target", "filter", "cat"]):
        b = g["band"].iloc[0]
        a0 = float(g["agn_colour"].iloc[0])
        row = dict(target=t, ra=g["ra"].iloc[0], dec=g["dec"].iloc[0], filter=f, band=b, cat=cat, agn_colour=a0,
                   mag_min=g["mag"].min(), mag_max=g["mag"].max())
        p = T.get((cat, b))
        for who in ("ava", "gspc"):
            o, oe, sl, n = offset_at(g["c"], g[who], a0, rng)
            row.update({f"{who}_raw_mmag": 1e3 * o, f"{who}_err_mmag": 1e3 * oe, "n": n})
            if p is not None:     # after removing the pooled system transform, evaluated at the AGN colour
                o2, *_ = offset_at(g["c"], g[who] - np.polyval(p, g["c"]), a0, rng)
                row[f"{who}_mmag"] = 1e3 * o2
        if n >= min_stars:
            rows.append(row)
    R = pd.DataFrame(rows)
    if len(R):
        R["ava_minus_gspc_mmag"] = R["ava_raw_mmag"] - R["gspc_raw_mmag"]
    return R


@click.command()
@click.option("--out", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--targets", multiple=True, help="default: every field with pytics/absolute_zp.json")
@click.option("--cats", default="sdss,ps1,skymapper", show_default=True)
def main(out, targets, cats):
    cats = [c for c in cats.split(",") if c]
    names = targets or sorted(p.parent.parent.name for p in cfg.phot_root.glob("*/pytics/absolute_zp.json"))
    print(f"{len(names)} fields; up to {len(names) * len(cats)} catalogue cone queries (cached in {out / 'cache'})")
    parts = []
    for t in names:
        try:
            st = field_stars(t, out / "cache", cats)
        except Exception as e:                      # one bad field does not stop the sweep
            print(f"{t}: {type(e).__name__}: {str(e)[:120]}")
            continue
        parts.append(st)
        print(f"{t}: {len(st)} star-band-catalogue matches")
    S = pd.concat(parts, ignore_index=True)
    T = system_transforms(S)
    R = field_offsets(S, T)
    out.mkdir(parents=True, exist_ok=True)
    S.to_csv(out / "star_check_stars.csv", index=False)
    R.to_csv(out / "star_check_fields.csv", index=False)
    pd.set_option("display.width", 220)
    print("\nAVA − catalogue at the AGN colour, system transform removed (mmag):")
    print(R.pivot_table(index=["target", "cat"], columns="band", values="ava_mmag").round(1).to_string())
    print("\nAVA − catalogue, raw (mmag):")
    print(R.pivot_table(index=["target", "cat"], columns="band", values="ava_raw_mmag").round(1).to_string())
    print("\nAVA − GSPC (mmag):")
    print(R.pivot_table(index=["target", "cat"], columns="band", values="ava_minus_gspc_mmag").round(1).to_string())
    print("\nstars used:")
    print(R.pivot_table(index=["target", "cat"], columns="band", values="n").to_string())


if __name__ == "__main__":
    main()
