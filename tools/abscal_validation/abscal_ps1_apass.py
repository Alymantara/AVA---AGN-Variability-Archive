"""Independent catalogues: PS1 DR2 g r i z (cached), APASS DR9 B V g r i (ESA Gaia archive external.apassdr9, cached in OUT),
SDSS DR16 (cached). Calibrated star means = GSPC - res (absolute_zp_stars). Offset at the AGN colour with a
free linear colour term (clipped), per filter and catalogue, plus GSPC - catalogue for the same stars."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from astropy.coordinates import SkyCoord
ROOT = Path(__file__).resolve().parents[2]; PH = ROOT / "data/test_archive/photometry/Mrk_817"; OUT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "tools"))
from check_absolute_calibration import offset_at, SDSS_AB, SDSS_BRIGHT   # noqa
ref = pd.read_csv(PH / "reference_stars.csv"); zpj = json.loads((PH / "pytics/absolute_zp.json").read_text())
tgt = __import__("yaml").safe_load((PH / "target.yaml").read_text())
cr = SkyCoord(ref["ra"], ref["dec"], unit="deg")
def match(ra, dec, tab, cols, r=1.0):
    i, d, _ = cr.match_to_catalog_sky(SkyCoord(ra, dec, unit="deg"))
    return {c: np.where(d.arcsec < r, np.asarray(tab[c], float)[i], np.nan) for c in cols}
# PS1
ps = pd.read_csv(PH / "external_ps1dr2.csv").replace(-999.0, np.nan)
ps = ps[ps["iMeanPSFMag"] - ps["iMeanKronMag"] < 0.05]
for b in "griz":
    bad = (ps[f"{b}MeanPSFMag"] < 14.5) | (ps[f"{b}MeanPSFMagErr"] > 0.03)
    ps.loc[bad, f"{b}MeanPSFMag"] = np.nan
m = match(ps["raMean"], ps["decMean"], ps, [f"{b}MeanPSFMag" for b in "griz"])
for b in "griz": ref[f"ps1_{b}"] = m[f"{b}MeanPSFMag"]
# SDSS
sd = pd.read_csv(PH / "external_sdss16.csv"); sd = sd[(sd["mode"] == 1) & (sd["class"] == 6) & (sd["clean"] == 1)]
for b, off in SDSS_AB.items():
    sd[f"{b}x"] = np.where((sd[f"{b}pmag"] > SDSS_BRIGHT[b]) & (sd[f"e_{b}pmag"] < 0.03), sd[f"{b}pmag"] + off, np.nan)
m = match(sd["RA_ICRS"], sd["DE_ICRS"], sd, [f"{b}x" for b in SDSS_AB])
for b in SDSS_AB: ref[f"sdss_{b}"] = m[f"{b}x"]
# APASS DR9
ap_f = OUT / "apass_dr9_esa_mrk817.csv"   # ESA Gaia archive external.apassdr9 (VizieR down)
if not ap_f.exists():
  try:   # ESA Gaia archive copy of APASS DR9 (VizieR mirrors were down on 18 Nov 2026)
    from astroquery.gaia import Gaia
    Gaia.ROW_LIMIT = -1
    t = Gaia.launch_job(
        "SELECT raj2000, dej2000, nobs, vmag, e_vmag, bmag, e_bmag, g_mag, e_g_mag, r_mag, e_r_mag, i_mag, e_i_mag "
        "FROM external.apassdr9 WHERE 1=CONTAINS(POINT('ICRS', raj2000, dej2000), "
        f"CIRCLE('ICRS', {tgt['ra_deg']}, {tgt['dec_deg']}, 0.35))").get_results()
    t.to_pandas().to_csv(ap_f, index=False)
  except Exception as e:
    print("APASS query failed:", str(e)[:120])
if ap_f.exists():
  ap = pd.read_csv(ap_f).rename(columns={"raj2000": "RAJ2000", "dej2000": "DEJ2000", "bmag": "Bmag", "e_bmag": "e_Bmag",
      "vmag": "Vmag", "e_vmag": "e_Vmag", "g_mag": "g'mag", "e_g_mag": "e_g'mag", "r_mag": "r'mag", "e_r_mag": "e_r'mag",
      "i_mag": "i'mag", "e_i_mag": "e_i'mag"})
  ren = {"g'mag": "g", "r'mag": "r", "i'mag": "i", "Bmag": "B", "Vmag": "V"}
  for k, b in ren.items():
      e = ap["e_" + k]
      ap[b + "x"] = np.where((e < 0.05) & (ap[k] > 10.5) & (ap["nobs"] >= 3), ap[k], np.nan)
  ap["Bx"] -= 0.09; ap["Vx"] += 0.02          # Vega -> AB (as GSPC JKC)
  m = match(ap["RAJ2000"], ap["DEJ2000"], ap, [b + "x" for b in ren.values()], r=2.0)
  for b in ren.values(): ref[f"apass_{b}"] = m[b + "x"]
zs = pd.read_parquet(PH / "pytics/absolute_zp_stars.parquet")
BAND = dict(up="u", B="B", gp="g", V="V", rp="r", ip="i", zs="z")
rows = []
for f, b in BAND.items():
    z = zpj[f]; s = zs[(zs["filter"] == f)].merge(ref, on="star_id", suffixes=("", "_r"))
    s = s[s["rms_star"] < 0.05]
    s["cal"] = s[f"lco_{b}"] - s["res"]          # calibrated ensemble mean (AVA)
    for cat in ["sdss", "ps1", "apass"]:
        col = f"{cat}_{b}"
        if col not in s: continue
        k = np.isfinite(s[col])
        for who, y in [("AVA", s["cal"] - s[col]), ("GSPC", s[f"lco_{b}"] - s[col])]:
            o, oe, sl, n = offset_at(s.loc[k, "c"], y[k], z["agn_colour"], np.random.default_rng(1))
            rows.append(dict(filter=f, cat=cat, who=who, offset_mmag=o * 1e3, err_mmag=oe * 1e3, slope=sl, n=n,
                             scatter_mmag=1.4826 * np.nanmedian(np.abs(y[k] - np.nanmedian(y[k]))) * 1e3))
r = pd.DataFrame(rows); r.to_csv(OUT / "ps1_apass_offsets.csv", index=False)
pd.set_option("display.width", 200)
print(r[r.who == "AVA"].pivot_table(index="filter", columns="cat", values=["offset_mmag", "err_mmag", "n", "scatter_mmag"]).round(1).to_string())
print(r[r.who == "GSPC"].pivot_table(index="filter", columns="cat", values="offset_mmag").round(1).to_string())
