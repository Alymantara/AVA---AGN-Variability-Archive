#!/usr/bin/env python
"""
Check a target's reference catalogue against independent photometry.

Compares the synthetic LCO magnitudes in ``reference_stars.csv`` with:
  * SDSS DR16 PSF magnitudes (VizieR V/154; northern / equatorial fields only)
    — clean, primary stars, not saturated, error < 0.05 mag
  * Gaia DR3 GSPC (already stored in the catalogue)

and reports the median offset (ours - reference, AB) and robust scatter per
band, for the anchored ``lco_u`` and the raw ``lco_u_model``.

    python tools/check_reference.py Mrk_817 PG_0844+349
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ava.config import cfg  # noqa: E402

#: SDSS (and GSPC-SDSS) -> AB: u_AB = u - 0.04, z_AB = z + 0.02.
SDSS_TO_AB = {"u": -0.04, "g": 0.0, "r": 0.0, "i": 0.0, "z": 0.02}
#: SDSS saturation (PSF mag), conservative.
SDSS_BRIGHT = {"u": 13.0, "g": 14.0, "r": 14.0, "i": 14.0, "z": 12.5}
BANDS = ("u", "g", "r", "i", "z")


def fetch_sdss(ra: float, dec: float, radius_arcmin: float, servers) -> pd.DataFrame:
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    from ava.photometry.reference import vizier_query

    cols = (["RA_ICRS", "DE_ICRS", "mode", "class", "clean"]
            + [f"{b}pmag" for b in BANDS] + [f"e_{b}pmag" for b in BANDS])
    try:
        table, _ = vizier_query(servers, SkyCoord(ra, dec, unit="deg"), radius_arcmin * u.arcmin,
                                "V/154/sdss16", columns=cols)
    except RuntimeError:  # outside the SDSS footprint (or no mirror reachable)
        return pd.DataFrame()
    t = table.to_pandas()
    return t[(t["mode"] == 1) & (t["class"] == 6) & (t["clean"] == 1)].reset_index(drop=True)


def stats(d: np.ndarray) -> tuple[float, float, int]:
    d = d[np.isfinite(d)]
    if len(d) == 0:
        return np.nan, np.nan, 0
    med = float(np.median(d))
    return med, float(1.4826 * np.median(np.abs(d - med))), int(len(d))


def compare(target: str, match_arcsec: float = 1.5) -> list[dict]:
    from astropy.coordinates import SkyCoord

    cat = pd.read_csv(cfg.phot_dir(target) / "reference_stars.csv")
    good_col = "quality_ok" if "quality_ok" in cat else "fit_ok"
    cat = cat[cat[good_col] & ~cat["is_agn"]].reset_index(drop=True)
    method = cat["ref_method"].iat[0] if "ref_method" in cat and len(cat) else "apass_model"
    has_model_u = "lco_u_model" in cat
    entry = cfg.target_by_data_id(target)
    rc = cfg.photometry.reference
    rows = []

    sdss = fetch_sdss(entry["ra_deg"], entry["dec_deg"], float(rc.radius_arcmin) + 0.5, list(rc.vizier_servers))
    if len(sdss):
        idx, d2d, _ = SkyCoord(cat["ra"].values, cat["dec"].values, unit="deg").match_to_catalog_sky(
            SkyCoord(sdss["RA_ICRS"].values, sdss["DE_ICRS"].values, unit="deg"))
        ok = d2d.arcsec < match_arcsec
        m, s = cat[ok].reset_index(drop=True), sdss.iloc[idx[ok]].reset_index(drop=True)
        for b in BANDS:
            ref = s[f"{b}pmag"] + SDSS_TO_AB[b]
            good = (s[f"e_{b}pmag"] < 0.05) & (s[f"{b}pmag"] > SDSS_BRIGHT[b])
            cols = [f"lco_{b}"] + (["lco_u_model"] if b == "u" and has_model_u else [])
            for col in cols:
                med, sig, n = stats((m[col] - ref)[good].to_numpy())
                rows.append(dict(target=target, method=method, ref="SDSS DR16 PSF", band=b, ours=col,
                                 median=med, scatter=sig, n=n))

    gspc = {"u": "gspc_u_sdss", "g": "gspc_g_sdss", "r": "gspc_r_sdss",
            "i": "gspc_i_sdss", "z": "gspc_z_sdss", "Y": "gspc_y_ps1"}
    for b, col_ref in gspc.items():
        if col_ref not in cat:  # gspc method: lco_* already are GSPC
            continue
        good = cat[f"{col_ref}_flag"] == 1
        ref = cat[col_ref] + SDSS_TO_AB.get(b, 0.0)
        for col in [f"lco_{b}"] + (["lco_u_model"] if b == "u" and has_model_u else []):
            med, sig, n = stats((cat[col] - ref)[good].to_numpy())
            rows.append(dict(target=target, method=method, ref="Gaia GSPC", band=b, ours=col,
                             median=med, scatter=sig, n=n))
    return rows


@click.command()
@click.argument("targets", nargs=-1, required=True)
@click.option("--csv", "csv_out", type=click.Path(dir_okay=False, path_type=Path), default=None,
              help="Also write the comparison table to this CSV.")
def main(targets, csv_out):
    """Compare reference catalogues of TARGETS (data_ids) with SDSS and Gaia GSPC."""
    rows = [r for t in targets for r in compare(t)]
    df = pd.DataFrame(rows)
    with pd.option_context("display.width", 140, "display.max_rows", 500,
                           "display.float_format", "{:+.3f}".format):
        print(df.to_string(index=False))
    if csv_out:
        df.to_csv(csv_out, index=False)


if __name__ == "__main__":
    main()
