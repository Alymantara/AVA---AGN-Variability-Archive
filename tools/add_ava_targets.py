"""Add AGN to the AVA database (``agn`` table of ``paths.database``), or correct existing rows, from a YAML list.

    python tools/add_ava_targets.py tools/new_targets/2026-11-16.yaml            # dry run: prints the rows
    python tools/add_ava_targets.py tools/new_targets/2026-11-16.yaml --write    # backup, then insert/update

For each target:
* position, redshift and object type from SIMBAD through the CDS Sesame resolver (NED's object lookup when SIMBAD
  has no redshift; both are printed when they disagree by > 0.001);
* the Gaia DR3 counterpart of the nucleus (nearest source within ``--gaia-radius`` arcsec of the SIMBAD position,
  VizieR I/355/gaiadr3, servers from ``photometry.reference.vizier_servers``): its position becomes ra/dec, its id
  ``agn_gaia_dr3_id``;
* E(B-V) along the line of sight (IRSA, Schlafly & Finkbeiner 2011) as ``ebv``;
* literature values (l_5100, logl, logm and their citations) from the YAML;
* ``ava`` = 2 (observing) if the target has LCO frames in the last 30 days, else 0; public = -1; lco_active = 1.
Vmag is left empty (to be filled from the merged g-band light curve).  After ``--write``, run
``python -m ava.lcodb link`` and ``python tools/ava_crossmatch.py`` to link the LCO frames.
"""
import argparse
import json
import shutil
import sqlite3
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ava.config import cfg  # noqa: E402

# Sesame mirrors, tried in order (CDS Strasbourg was unreachable on 17 Nov 2026; the CfA mirror served SIMBAD fine)
SESAME_MIRRORS = ["https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/SNV?",
                  "https://vizier.cfa.harvard.edu/viz-bin/nph-sesame/-oxp/SNV?"]
NED = "https://ned.ipac.caltech.edu/srs/ObjectLookup"

_SESAME_DOWN: set[str] = set()  # mirrors that failed to connect this run (one timeout each, not one per target)


def sesame(name):
    import requests

    r = None
    for url in SESAME_MIRRORS:
        if url in _SESAME_DOWN:
            continue
        try:
            r = requests.get(url + urllib.parse.quote(name), timeout=20)
            break
        except requests.RequestException as e:
            print(f"  Sesame mirror {url.split('/')[2]} unreachable ({type(e).__name__}); skipping it this run")
            _SESAME_DOWN.add(url)
    if r is None:  # every mirror down: build() falls back to NED
        return None
    res = ET.fromstring(r.content).find(".//Resolver")
    if res is None:
        return None
    t = lambda k: res.find(k).text if res.find(k) is not None else None  # noqa: E731
    z = res.find("z")
    return {"by": res.get("name", "")[:1], "oname": t("oname"), "otype": t("otype"), "ra": float(t("jradeg")),
            "dec": float(t("jdedeg")), "z": float(z.find("v").text) if z is not None else None,
            "z_ref": (z.find("r").text if z is not None and z.find("r") is not None else None)}


def ned(name):
    import requests

    d = requests.post(NED, data={"json": json.dumps({"name": {"v": name}})}, timeout=60).json().get("Preferred") or {}
    if not d:
        return None
    z = d.get("Redshift") or {}
    return {"name": d.get("Name"), "ra": d["Position"]["RA"], "dec": d["Position"]["Dec"], "z": z.get("Value"),
            "z_ref": z.get("RefCode")}


def gaia_counterpart(ra, dec, radius_arcsec):
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    from ava.photometry.reference import vizier_query

    try:  # ESA Gaia archive first: the CfA VizieR mirror missed close sources during the 17 Nov 2026 CDS outage
        from astroquery.gaia import Gaia

        t = Gaia.launch_job(
            "SELECT TOP 1 source_id, ra, dec, phot_g_mean_mag, "
            f"DISTANCE(POINT(ra, dec), POINT({ra:.8f}, {dec:.8f})) AS dist FROM gaiadr3.gaia_source WHERE 1 = "
            f"CONTAINS(POINT(ra, dec), CIRCLE({ra:.8f}, {dec:.8f}, {radius_arcsec / 3600:.8f})) "
            "ORDER BY dist").get_results()
        t.rename_columns(t.colnames, [x.lower() for x in t.colnames])
        if not len(t):
            return None
        r = t[0]
        sep = SkyCoord(float(r["ra"]), float(r["dec"]), unit="deg").separation(SkyCoord(ra, dec, unit="deg")).arcsec
        return {"source_id": int(r["source_id"]), "ra": float(r["ra"]), "dec": float(r["dec"]),
                "g": float(r["phot_g_mean_mag"]), "sep": float(sep)}
    except Exception as e:  # noqa: BLE001 — ESA archive down: VizieR mirrors
        print(f"  ESA Gaia query failed ({type(e).__name__}); trying VizieR")
    import requests

    def _up(server):
        try:
            requests.head(f"https://{server}", timeout=8)
            return True
        except requests.RequestException:
            return False

    c = SkyCoord(ra, dec, unit="deg")
    for server in [s_ for s_ in cfg.photometry.reference.vizier_servers if _up(s_)]:
        try:
            t = vizier_query(server, c, radius_arcsec * u.arcsec, "I/355/gaiadr3")[0].to_pandas()
        except Exception:  # noqa: BLE001 — empty cone or mirror problem: try the next mirror
            continue
        if len(t):
            sep = SkyCoord(t["RA_ICRS"].values, t["DE_ICRS"].values, unit="deg").separation(c).arcsec
            i = int(sep.argmin())
            return {"source_id": int(t["Source"].iloc[i]), "ra": float(t["RA_ICRS"].iloc[i]),
                    "dec": float(t["DE_ICRS"].iloc[i]), "g": float(t["Gmag"].iloc[i]), "sep": float(sep[i])}
    return None


def sexa(ra, dec):
    from astropy.coordinates import SkyCoord

    c = SkyCoord(ra, dec, unit="deg")
    return (c.ra.to_string(unit="hourangle", sep=":", precision=2, pad=True),
            c.dec.to_string(sep=":", precision=2, alwayssign=True, pad=True))


def last_lco_day(names):
    from ava.lcodb.config import load_config

    db = load_config(cfg.lcodb_config_path).db_path("photometry")
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        q = ",".join("?" * len(names))
        return con.execute(f"SELECT MAX(day_obs) FROM frames WHERE object IN ({q})", list(names)).fetchone()[0]


def lco_names_near(ra, dec, radius_arcmin=6.0):
    from ava.lcodb.config import load_config

    db = load_config(cfg.lcodb_config_path).db_path("photometry")
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        rows = con.execute("SELECT object, obj_ra, obj_dec FROM target_link WHERE obj_ra BETWEEN ? AND ? AND "
                           "obj_dec BETWEEN ? AND ?", (ra - 1, ra + 1, dec - 0.2, dec + 0.2)).fetchall()
    from astropy.coordinates import SkyCoord

    out = []
    for o, r_, d_ in rows:
        if r_ is not None and SkyCoord(r_, d_, unit="deg").separation(SkyCoord(ra, dec, unit="deg")).arcmin <= radius_arcmin:
            out.append(o)
    return out


def build(entry, gaia_radius, today):
    name = entry["name"]
    s = sesame(entry.get("resolve", name))
    n = ned(entry.get("resolve", name))
    if s is None and n is None:
        raise SystemExit(f"{name}: not resolved by SIMBAD or NED")
    pos = s or n
    z, zref = (s["z"], s["z_ref"]) if s and s.get("z") is not None else ((n or {}).get("z"), (n or {}).get("z_ref"))
    notes = []
    if s and n and s.get("z") is not None and n.get("z") is not None and abs(s["z"] - n["z"]) > 0.001:
        notes.append(f"z SIMBAD {s['z']:.5f} ({s['z_ref']}) vs NED {n['z']:.5f} ({n['z_ref']})")
    g = gaia_counterpart(pos["ra"], pos["dec"], gaia_radius)
    ra, dec = (g["ra"], g["dec"]) if g else (pos["ra"], pos["dec"])
    from ava.photometry.reference import field_ebv_sf11

    ebv = field_ebv_sf11(ra, dec)
    lco = lco_names_near(ra, dec)
    last = last_lco_day(lco) if lco else None
    recent = bool(last) and datetime.fromisoformat(str(last)) >= today - timedelta(days=30)
    ras, decs = sexa(ra, dec)
    row = {"name": name, "ra": ras, "dec": decs, "ra_deg": round(ra, 6), "dec_deg": round(dec, 6),
           "redshift": round(z, 6) if z is not None else None, "red_url": zref, "ebv": ebv,
           "simbad_name": entry.get("resolve", name), "agn_gaia_dr3_id": g["source_id"] if g else None}
    if "data_id" in entry:
        row.update(data_id=entry["data_id"], lco_id=urllib.parse.quote(entry.get("lco_id", name)),
                   ava=2 if recent else 0, public=-1, lco_active=1, lt_active=0,
                   last_update=today.date().isoformat())
    for k in ("l_5100", "l_5100_cite", "l_5100_url", "logl", "logl_cite", "logl_url", "logl_comment", "logm",
              "logm_cite", "logm_url", "AGN_type", "Comments"):
        if k in entry:
            row[k] = entry[k]
    info = {"simbad": s, "ned": n, "gaia": g, "lco_names": lco, "last_lco": last, "notes": notes}
    return row, info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--write", action="store_true", help="back up the database, then insert / update")
    ap.add_argument("--gaia-radius", type=float, default=2.0, help="arcsec, nucleus counterpart search")
    a = ap.parse_args()
    spec = yaml.safe_load(open(a.spec))
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    db = cfg.db_path
    plan = []
    for e in spec.get("targets", []):
        plan.append(("insert", e, *build(e, a.gaia_radius, today)))
    for e in spec.get("fix", []):
        plan.append(("update", e, *build(e, a.gaia_radius, today)))
    for kind, e, row, info in plan:
        g = info["gaia"]
        print(f"{kind:6s} {row['name']:18s} {row['ra']} {row['dec']}  z={row['redshift']}  E(B-V)={row['ebv']:.3f}  "
              f"Gaia {g['source_id'] if g else '-'} ({g['sep']:.2f}\", G={g['g']:.2f})" if g else
              f"{kind:6s} {row['name']:18s} {row['ra']} {row['dec']}  z={row['redshift']}  no Gaia counterpart")
        print(f"       SIMBAD {(info['simbad'] or {}).get('oname')} {(info['simbad'] or {}).get('otype')}; "
              f"LCO names {info['lco_names']} (last {info['last_lco']}); ava={row.get('ava', '(kept)')}"
              + ("; " + "; ".join(info["notes"]) if info["notes"] else ""))
    if not a.write:
        print("\n(dry run: nothing written; add --write)")
        return
    backup = Path(db).parent / "backups" / f"ava_{today:%Y%m%dT%H%M%S}_before_add_targets.db"
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)
    print(f"backup: {backup}")
    with sqlite3.connect(db) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(agn)")}
        for kind, e, row, _ in plan:
            row = {k: v for k, v in row.items() if k in cols}
            if kind == "insert":
                if con.execute("SELECT 1 FROM agn WHERE name=? OR data_id=?", (row["name"], row["data_id"])).fetchone():
                    print(f"skip {row['name']}: already in agn")
                    continue
                row["id"] = con.execute("SELECT MAX(id) + 1 FROM agn").fetchone()[0]
                con.execute(f"INSERT INTO agn ({','.join(chr(34) + k + chr(34) for k in row)}) VALUES "
                            f"({','.join('?' * len(row))})", list(row.values()))
                print(f"inserted id {row['id']}: {row['name']}")
            else:
                sets = ",".join(f'"{k}"=?' for k in row)
                con.execute(f"UPDATE agn SET {sets} WHERE id=?", [*row.values(), e["id"]])
                print(f"updated id {e['id']}: {row['name']}")
        con.commit()
    print("next: python -m ava.lcodb link && python tools/ava_crossmatch.py")


if __name__ == "__main__":
    main()
