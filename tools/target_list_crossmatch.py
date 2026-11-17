#!/usr/bin/env python
"""Cross-match a supplied target list (name, ra, dec, type, z, approx. epochs) against the AVA catalogue.

For every list entry:

* **AVA match** — by name (normalised; AVA ``name``/``simbad_name``/``data_id``/``lco_id``, ``agn_lco.db_lco_names``
  and the LCO OBJECT spellings already linked in ``lco_targets``) and by position (nearest ``agn`` within
  ``--ava-radius`` arcsec). ``data/ava.db`` is opened read-only.
* **Coordinate check** (entries not in AVA) — the name is resolved with CDS Sesame (SIMBAD/NED) and the Gaia DR3
  nucleus is looked up near the resolved position and near the list position (``--gaia-radius``). The offsets
  list→Gaia and list→SIMBAD are reported.
* **Category** — in_ava, sdss_rm, non_agn (calibrator / SN / star / cluster), candidate (an AGN not in AVA).

Network results are cached in ``data/reference/external_catalogues/target_list_resolve.json`` (``--refresh``
re-queries). Nothing is written to the database.

    python tools/target_list_crossmatch.py tools/new_targets/lco_epoch_list_2026-11-16.tsv
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from ava.config import cfg  # noqa: E402

CACHE = ROOT / "data" / "reference" / "external_catalogues" / "target_list_resolve.json"
# SDSS-RM field (Shen et al. 2015): 7 deg^2 centred on RA 213.704, Dec +53.083
RM_CENTRE, RM_RADIUS_DEG = (213.704, 53.083), 1.6
AGN_OTYPES = {"AGN", "Sy1", "Sy2", "SyG", "QSO", "Q?", "BLL", "Bla", "BLLac", "Blazar", "LIN", "LINER", "LeQ",
              "LensedQ", "AG?", "SyG", "Seyfert", "Seyfert_1", "Seyfert_2", "QSO_Candidate", "AGN_Candidate",
              "BClG", "rG", "RadioG", "EmG", "GiG"}  # galaxy-ish types kept as "check" below
NON_AGN_NAME = re.compile(r"(?i)^(t_)?gd\d|^test$|^ngc ?2419|^xtej|^tcp_|^psn|^l74546|^ngc ?(2787|3968)$|^ic ?438$")
NON_AGN_TYPES = {"*", "*Cl", "GlC", "WD*", "SN", "XB", "LXB", "HXB", "PN", "HII", "Neb"}
STRICT_AGN = {"AGN", "Sy1", "Sy2", "SyG", "QSO", "Q?", "BLL", "Bla", "BLLac", "Blazar", "LIN", "LINER", "LeQ",
              "LensedQ", "AG?", "Seyfert", "Seyfert_1", "Seyfert_2", "QSO_Candidate", "AGN_Candidate"}


def norm(name: str) -> str:
    """Loose catalogue-name key: lower case, no separators, common prefix aliases folded."""
    s = str(name).lower().strip()
    s = re.sub(r"(_offs|offset|_\d)$", "", s)
    s = re.sub(r"[\s_\-\.+]", "", s)
    s = re.sub(r"^(markarian|mkn)", "mrk", s)
    s = re.sub(r"^akn", "ark", s)
    s = s.replace("izw1", "1zw1")
    s = re.sub(r"^t_", "", s)
    return s


def parse_list(path: Path) -> pd.DataFrame:
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        f = [x.strip() for x in line.split("\t")]
        f += [""] * (6 - len(f))
        if f[1] == "":  # alias line: "<name> <alias>"
            if rows and f[0].startswith(rows[-1]["list_name"]):
                alias = f[0][len(rows[-1]["list_name"]):].strip()
                if alias and alias.split()[0] != rows[-1]["list_name"]:
                    rows[-1]["aliases"].append(alias)
            continue
        z = None if f[4] in ("", "None") else float(f[4])
        rows.append({"list_name": f[0], "list_ra": float(f[1]), "list_dec": float(f[2]), "list_type": f[3],
                     "list_z": z, "list_epochs": int(f[5]) if f[5] else None, "aliases": []})
    return pd.DataFrame(rows)


def load_ava(db: Path):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    agn = pd.read_sql("select a.id, a.name, a.simbad_name, a.data_id, a.lco_id, a.ra_deg, a.dec_deg, a.redshift, "
                      "a.Vmag, a.agn_gaia_dr3_id, l.db_lco_names, l.db_lco_images, l.db_floyds_epochs "
                      "from agn a left join agn_lco l on l.db_ava_id = a.id", con)
    lt = pd.read_sql("select object, ava_id, n_phot, n_spec from lco_targets", con)
    con.close()
    keys: dict[str, int] = {}
    for _, r in agn.iterrows():
        names = [r["name"], r["simbad_name"], r["data_id"], r["lco_id"]]
        names += str(r["db_lco_names"] or "").replace(";", ",").split(",")
        for n in names:
            if n and str(n).strip() and str(n) != "None":
                keys.setdefault(norm(n), int(r["id"]))
    for _, r in lt.dropna(subset=["ava_id"]).iterrows():
        keys.setdefault(norm(r["object"]), int(r["ava_id"]))
    return agn, lt, keys


def _reachable(url: str, timeout: float = 8.0) -> bool:
    import requests

    try:
        requests.head(url, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False


def ned_lookup(name: str):
    """NED ObjectLookup, same dict shape as add_ava_targets.sesame (otype = NED ObjType, e.g. 'G', 'QSO')."""
    import requests

    d = requests.post("https://ned.ipac.caltech.edu/srs/ObjectLookup",
                      data={"json": json.dumps({"name": {"v": name}})}, timeout=30).json().get("Preferred") or {}
    if not d:
        return None
    z = (d.get("Redshift") or {}).get("Value")
    return {"by": "N", "oname": d.get("Name"), "otype": "NED:" + str((d.get("ObjType") or {}).get("Value")),
            "ra": d["Position"]["RA"], "dec": d["Position"]["Dec"], "z": z, "z_ref": None}


def gaia_nearest(servers, ra, dec, radius_arcsec):
    """Nearest Gaia DR3 source: ESA Gaia archive TAP first (authoritative), VizieR mirrors as fallback.

    The CfA VizieR mirror missed sources 0.2-1.6" from the cone centre during the CDS outage of 17 Nov 2026.
    """
    try:
        from astroquery.gaia import Gaia

        q = ("SELECT TOP 1 source_id, ra, dec, phot_g_mean_mag, "
             f"DISTANCE(POINT(ra, dec), POINT({ra:.8f}, {dec:.8f})) * 3600 AS sep FROM gaiadr3.gaia_source "
             f"WHERE 1 = CONTAINS(POINT(ra, dec), CIRCLE({ra:.8f}, {dec:.8f}, {radius_arcsec / 3600:.8f})) "
             "ORDER BY sep")
        t = Gaia.launch_job(q).get_results()
        if not len(t):
            return None
        t.rename_columns(t.colnames, [c.lower() for c in t.colnames])  # ESA returns SOURCE_ID
        r = t[0]
        g = r["phot_g_mean_mag"]
        return {"source_id": int(r["source_id"]), "ra": float(r["ra"]), "dec": float(r["dec"]),
                "g": None if np.ma.is_masked(g) else float(g), "src": "ESA",
                "sep": sep_arcsec(ra, dec, float(r["ra"]), float(r["dec"]))}  # (old astroquery drops the alias)
    except Exception as e:  # noqa: BLE001 — ESA archive down: use VizieR
        print(f"  ESA Gaia TAP failed ({type(e).__name__}); trying VizieR")
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    from ava.photometry.reference import vizier_query

    c = SkyCoord(ra, dec, unit="deg")
    try:
        t = vizier_query(servers, c, radius_arcsec * u.arcsec, "I/355/gaiadr3")[0].to_pandas()
    except RuntimeError:  # empty cone on every mirror
        return None
    sep = SkyCoord(t["RA_ICRS"].values, t["DE_ICRS"].values, unit="deg").separation(c).arcsec
    i = int(sep.argmin())
    return {"source_id": int(t["Source"].iloc[i]), "ra": float(t["RA_ICRS"].iloc[i]),
            "dec": float(t["DE_ICRS"].iloc[i]), "g": float(t["Gmag"].iloc[i]), "sep": float(sep[i]), "src": "VizieR"}


def resolve_all(names_aliases, positions, refresh, gaia_radius):
    from add_ava_targets import SESAME_MIRRORS, sesame  # reuse the vetted helper (tries CDS, then CfA)

    # CDS (Sesame + main VizieR) is sometimes down: fall back to NED and the other VizieR mirrors
    cds_up = any(_reachable(u.split("/cgi-bin")[0].split("/viz-bin")[0]) for u in SESAME_MIRRORS)
    resolver = sesame if cds_up else ned_lookup
    servers = [s for s in cfg.photometry.reference.vizier_servers if _reachable("https://" + s)]
    print(f"  resolver: {'Sesame' if cds_up else 'NED (CDS unreachable)'}; VizieR mirrors: {servers}")
    cache = {} if refresh or not CACHE.exists() else json.loads(CACHE.read_text())
    for (name, aliases), (ra, dec) in zip(names_aliases, positions):
        key = [round(float(ra), 6), round(float(dec), 6)]
        if name in cache and cache[name].get("pos", key) == key:
            continue
        s, used = None, None
        for n in dict.fromkeys([name, *aliases, re.sub(r"(_offs|offset)$", "", name)]):
            try:
                s = resolver(n)
            except Exception as e:  # noqa: BLE001
                print(f"  resolve {n}: {type(e).__name__}")
                s = None
            if s:
                used = n
                break
        g_list = gaia_nearest(servers, ra, dec, gaia_radius)
        g_sim = gaia_nearest(servers, s["ra"], s["dec"], gaia_radius) if s else None
        cache[name] = {"sesame": s, "resolved_as": used, "gaia_list": g_list, "gaia_simbad": g_sim, "pos": key}
        print(f"  {name:24s} {('-> ' + s['oname'] + ' [' + str(s['otype']) + ']') if s else 'unresolved'}")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True))
    return cache


def sep_arcsec(ra1, dec1, ra2, dec2):
    from astropy.coordinates import SkyCoord

    return float(SkyCoord(ra1, dec1, unit="deg").separation(SkyCoord(ra2, dec2, unit="deg")).arcsec)


def apply_fixes(lst: pd.DataFrame, path: Path | None) -> pd.DataFrame:
    """Apply a corrections YAML (see tools/new_targets/*_fixes.yaml) to the parsed list."""
    import yaml

    lst = lst.copy()
    lst["orig_ra"], lst["orig_dec"] = lst["list_ra"], lst["list_dec"]
    lst["duplicate_of"], lst["fix_note"], lst["keep_list_position"] = "", "", False
    if path is None:
        return lst
    fixes = (yaml.safe_load(path.read_text()) or {}).get("fixes", {})
    names = list(lst["list_name"])
    for name, f in fixes.items():
        if name not in names:
            raise SystemExit(f"{path.name}: {name!r} is not in the list")
        i = names.index(name)
        if f.get("duplicate_of"):
            j = names.index(f["duplicate_of"])
            lst.loc[i, ["list_ra", "list_dec"]] = lst.loc[j, ["list_ra", "list_dec"]].values
            lst.loc[i, "duplicate_of"] = f["duplicate_of"]
        if "ra" in f:
            lst.loc[i, ["list_ra", "list_dec"]] = [float(f["ra"]), float(f["dec"])]
        if f.get("resolve"):
            lst.at[i, "aliases"] = [f["resolve"], *lst.at[i, "aliases"]]
        lst.loc[i, "keep_list_position"] = bool(f.get("keep_list_position", False))
        lst.loc[i, "fix_note"] = f.get("note", "")
    print(f"  applied {len(fixes)} corrections from {path.name}")
    return lst


def count_frames(df: pd.DataFrame, object_radius: float, phot_radius: float, spec_radius: float) -> pd.DataFrame:
    """LCO frames of each entry from the local lcodb mirror (read-only; no archive requests).

    The LCO OBJECT names of a target are those whose ``target_link`` position lies within ``object_radius`` arcmin
    of the best position. Their science frames are counted when the frame's own footprint/pointing is within
    ``phot_radius`` (imaging exposures, rlevel 91 or else 90) or ``spec_radius`` (FLOYDS SPECTRUM, raw) arcmin, which drops frames of a
    re-used OBJECT name taken elsewhere. Nights = distinct DAY-OBS.
    """
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    from ava.lcodb.config import load_config

    lc = load_config(cfg.lcodb_config_path)
    con = {k: sqlite3.connect(f"file:{lc.db_path(k)}?mode=ro", uri=True) for k in ("photometry", "spectra")}
    tl = pd.read_sql("SELECT object, obj_ra, obj_dec FROM target_link WHERE obj_ra IS NOT NULL", con["photometry"])
    tl = pd.concat([tl, pd.read_sql("SELECT object, obj_ra, obj_dec FROM target_link WHERE obj_ra IS NOT NULL",
                                    con["spectra"])]).drop_duplicates("object")
    tlc = SkyCoord(tl["obj_ra"].values * u.deg, tl["obj_dec"].values * u.deg)
    # imaging: one row per exposure; 2014 - mid-2016 frames exist only at rlevel 90 (no 91 reprocessing)
    ph = pd.read_sql("SELECT object, exp_key, rlevel, day_obs, filter, ra, dec FROM frames "
                     "WHERE rlevel IN (90, 91) AND obstype = 'EXPOSE'", con["photometry"])
    ph = ph.sort_values("rlevel", ascending=False).drop_duplicates("exp_key")
    sp = pd.read_sql("SELECT object, day_obs, ra, dec FROM frames WHERE rlevel = 0 AND obstype = 'SPECTRUM'",
                     con["spectra"])
    rows = []
    for r in df.itertuples():
        c = SkyCoord(r.ra_best * u.deg, r.dec_best * u.deg)
        objs = sorted(set(tl["object"][tlc.separation(c).arcmin <= object_radius]))
        out = {"lco_objects": "; ".join(objs)}
        for kind, fr, rad in (("phot", ph, phot_radius), ("spec", sp, spec_radius)):
            f = fr[fr["object"].isin(objs) & fr["ra"].notna()]
            if len(f):
                f = f[SkyCoord(f["ra"].values * u.deg, f["dec"].values * u.deg).separation(c).arcmin <= rad]
            nights = sorted(f["day_obs"].dropna().unique())
            out[f"n_{kind}_frames"] = len(f)
            out[f"n_{kind}_nights"] = len(nights)
            out[f"{kind}_first"] = nights[0] if nights else None
            out[f"{kind}_last"] = nights[-1] if nights else None
            if kind == "phot":
                out["phot_filters"] = ",".join(sorted(f["filter"].dropna().unique()))
                d = np.diff(pd.to_datetime(pd.Series(nights)).values).astype("timedelta64[D]").astype(float)
                out["phot_median_cadence_d"] = float(np.median(d)) if len(d) else None
        rows.append(out)
    for c_ in con.values():
        c_.close()
    return pd.DataFrame(rows, index=df.index)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("list", type=Path)
    ap.add_argument("--out", type=Path, help="CSV output (default: <list>_xmatch.csv)")
    ap.add_argument("--ava-radius", type=float, default=60.0, help="arcsec, position match to AVA")
    ap.add_argument("--gaia-radius", type=float, default=5.0, help="arcsec, Gaia DR3 nucleus search")
    ap.add_argument("--resolve-max", type=float, default=30.0,
                    help="arcsec; a resolver position further than this from the list position is ignored")
    ap.add_argument("--dup-radius", type=float, default=30.0, help="arcsec; list entries this close are duplicates")
    ap.add_argument("--fixes", type=Path, help="corrections YAML (default: <list>_fixes.yaml if present)")
    ap.add_argument("--count-frames", action="store_true",
                    help="count LCO frames per entry from the local lcodb mirror (read-only, no archive requests)")
    ap.add_argument("--object-radius", type=float, default=3.0,
                    help="arcmin; LCO OBJECT names whose position lies this close count as the target")
    ap.add_argument("--phot-radius", type=float, default=12.0,
                    help="arcmin; a photometric frame counts if its footprint centre is this close")
    ap.add_argument("--spec-radius", type=float, default=6.0,
                    help="arcmin; a FLOYDS frame counts if its pointing is this close")
    ap.add_argument("--refresh", action="store_true", help="re-query Sesame/Gaia instead of using the cache")
    a = ap.parse_args()

    from astropy.coordinates import SkyCoord
    import astropy.units as u

    lst = parse_list(a.list)
    fixes_path = a.fixes or a.list.with_name(a.list.stem + "_fixes.yaml")
    lst = apply_fixes(lst, fixes_path if fixes_path.exists() else None)
    agn, lt, keys = load_ava(cfg.db_path)
    pos = agn[agn["ra_deg"].notna() & agn["dec_deg"].notna()].reset_index(drop=True)  # 2 SDSS-RM rows lack ra/dec
    cat = SkyCoord(pos["ra_deg"].values * u.deg, pos["dec_deg"].values * u.deg)
    idx, d2d, _ = SkyCoord(lst["list_ra"].values * u.deg, lst["list_dec"].values * u.deg).match_to_catalog_sky(cat)
    lst["pos_ava_id"] = np.where(d2d.arcsec <= a.ava_radius, pos["id"].values[idx], -1)
    lst["pos_sep"] = d2d.arcsec
    lst["name_ava_id"] = [next((keys[k] for k in [norm(n), *map(norm, al)] if k in keys), -1)
                          for n, al in zip(lst["list_name"], lst["aliases"])]
    ltn = {norm(o): (p, s) for o, p, s in lt[["object", "n_phot", "n_spec"]].itertuples(index=False)}
    lst["lco_n_phot"] = [ltn.get(norm(n), (None, None))[0] for n in lst["list_name"]]
    lst["lco_n_spec"] = [ltn.get(norm(n), (None, None))[1] for n in lst["list_name"]]

    def ava_status(r):
        if r.name_ava_id >= 0 and r.pos_ava_id == r.name_ava_id:
            return r.name_ava_id, "name+position"
        if r.name_ava_id >= 0:
            return r.name_ava_id, "name (list position off)"
        if r.pos_ava_id >= 0:
            return r.pos_ava_id, "position"
        return -1, ""

    st = [ava_status(r) for r in lst.itertuples()]
    lst["ava_id"] = [s[0] for s in st]
    lst["ava_match"] = [s[1] for s in st]
    byid = agn.set_index("id")
    lst["ava_name"] = [byid.loc[i, "name"] if i >= 0 else "" for i in lst["ava_id"]]
    lst["ava_sep_arcsec"] = [round(sep_arcsec(r.list_ra, r.list_dec, byid.loc[r.ava_id, "ra_deg"],
                                              byid.loc[r.ava_id, "dec_deg"]), 1)
                             if r.ava_id >= 0 and pd.notna(byid.loc[r.ava_id, "ra_deg"]) else None
                             for r in lst.itertuples()]

    todo = lst[lst["ava_id"] < 0]
    print(f"{len(lst)} list entries, {int((lst['ava_id'] >= 0).sum())} in AVA; resolving {len(todo)} others")
    cache = resolve_all(list(zip(todo["list_name"], todo["aliases"])), list(zip(todo["list_ra"], todo["list_dec"])),
                        a.refresh, a.gaia_radius)

    out = []
    for r in lst.itertuples():
        rec = {k: getattr(r, k) for k in ["list_name", "list_ra", "list_dec", "list_type", "list_z", "list_epochs",
                                          "lco_n_phot", "lco_n_spec", "ava_name", "ava_match", "ava_sep_arcsec"]}
        rec["aliases"] = "; ".join(r.aliases)
        rec.update(orig_ra=r.orig_ra, orig_dec=r.orig_dec, duplicate_of=r.duplicate_of, fix_note=r.fix_note)
        c = cache.get(r.list_name, {}) if r.ava_id < 0 else {}
        s, gl, gs = c.get("sesame"), c.get("gaia_list"), c.get("gaia_simbad")
        bad_resolve = s is not None and (r.keep_list_position or
                                         sep_arcsec(r.list_ra, r.list_dec, s["ra"], s["dec"]) > a.resolve_max)
        if bad_resolve:  # the resolver found a different object far from the list position: keep the list position
            rec["resolver_mismatch"] = f"{s['oname']} {sep_arcsec(r.list_ra, r.list_dec, s['ra'], s['dec']):.0f}\" away"
            s, gs = None, None
        g = gs or gl or {}
        rec.update(simbad_name=s["oname"] if s else "", otype=s["otype"] if s else "",
                   simbad_z=s["z"] if s else None,
                   sep_list_simbad=round(sep_arcsec(r.list_ra, r.list_dec, s["ra"], s["dec"]), 2) if s else None,
                   gaia_source_id=g.get("source_id"), gaia_G=g.get("g"), gaia_ra=g.get("ra"), gaia_dec=g.get("dec"),
                   sep_list_gaia=round(sep_arcsec(r.list_ra, r.list_dec, g["ra"], g["dec"]), 2) if g else None)
        rm = sep_arcsec(r.list_ra, r.list_dec, *RM_CENTRE) / 3600 < RM_RADIUS_DEG or \
            re.match(r"(?i)sdss[-_]?rm", r.list_name)
        otype = (s or {}).get("otype") or ""
        if r.ava_id >= 0:
            cat_ = "in_ava"
        elif r.duplicate_of:
            cat_ = "duplicate"
        elif rm:
            cat_ = "sdss_rm"
        elif NON_AGN_NAME.match(r.list_name) or otype.replace("NED:", "") in NON_AGN_TYPES:
            cat_ = "non_agn"
        elif s or g:
            cat_ = "candidate"
        else:
            cat_ = "no_counterpart"
        rec["category"] = cat_
        coord = []
        if r.ava_id < 0:
            if not g:
                coord.append("no Gaia within %.0f\"" % a.gaia_radius)
            elif rec["sep_list_gaia"] > 1.0:
                coord.append("list->Gaia %.1f\"" % rec["sep_list_gaia"])
            if rec["sep_list_simbad"] is not None and rec["sep_list_simbad"] > 3:
                coord.append("list->resolver %.0f\"" % rec["sep_list_simbad"])
            if bad_resolve:
                coord.append("resolver mismatch: " + rec["resolver_mismatch"])
        rec["coord_flag"] = "; ".join(coord) if coord else ("ok" if r.ava_id < 0 else "")
        out.append(rec)

    df = pd.DataFrame(out)
    # best position: Gaia DR3 nucleus, else resolver, else (corrected) list position
    df["pos_source"] = np.where(df["gaia_ra"].notna(), "gaia_dr3",
                                np.where(df["sep_list_simbad"].notna(), "resolver", "list"))
    df["ra_best"] = df["gaia_ra"].fillna(df["list_ra"])
    df["dec_best"] = df["gaia_dec"].fillna(df["list_dec"])
    if a.count_frames:
        df = pd.concat([df, count_frames(df, a.object_radius, a.phot_radius, a.spec_radius)], axis=1)
    # duplicates within the list (same object under two spellings / offset pointings): best position = Gaia if found
    bra = df["gaia_ra"].fillna(df["list_ra"]).values
    bde = df["gaia_dec"].fillna(df["list_dec"]).values
    cc = SkyCoord(bra * u.deg, bde * u.deg)
    dup = []
    for i in range(len(df)):
        d = cc[i].separation(cc).arcsec
        same = [j for j in np.where(d < a.dup_radius)[0] if j != i]
        dup.append("; ".join(f"{df['list_name'][j]} ({d[j]:.0f}\")" for j in same))
    df["list_duplicates"] = dup
    df = df.sort_values(["category", "list_epochs", "list_name"], ascending=[True, False, True])
    dest = a.out or a.list.with_name(a.list.stem + "_xmatch.csv")
    df.to_csv(dest, index=False, float_format="%.6g")
    print(f"wrote {dest}")
    print(df.groupby("category").size().to_string())


if __name__ == "__main__":
    main()
