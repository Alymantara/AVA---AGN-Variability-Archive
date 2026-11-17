"""Merge the cached sources into data/literature/agn_properties.csv (+ references.csv, conflicts.csv).

Sources (all under data/literature/cache/):
  targets_matched.csv      AVA targets with their AGNmass match
  agnmass.json             AGN Black Hole Mass Database (Bentz & Katz 2015) — Hb lags, masses, L5100
  catalogs/catalogs.jsonl  NED (z), SIMBAD, Veron-Cetty & Veron 2010 (type) per target
  lit/batch_[ABCE].json    literature for targets not in AGNmass
  lit/batch_[DF].json      Hb campaigns newer than AGNmass for AGNmass targets
Rules: z from NED; type from VCV10, else literature, else SIMBAD; mass from AGNmass (Hb-only, f=4.3) unless
a newer well-sampled campaign is given; lag = the most recent well-sampled Hb campaign. Empty if not found.
"""
import json, math, re, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ads_refs import resolve, cite  # noqa: E402

L = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
C = L / "cache"
SKIP = {"SDSS_RM201": "SDSS-RM target: not searched (by request)", "SDSS_RM562": "SDSS-RM target: not searched (by request)",
        "IGR_J17062-6143": "X-ray binary (not an AGN): AGN properties not applicable"}
# Mass for AGNmass targets: "newest" uses the mass of the newest Hb campaign that reports one (batch D/F, its own f),
# with the AGNmass mean in notes; "agnmass" keeps the AGNmass mean of all Hb campaigns (<f>=4.3) and notes the newer mass.
MASS_POLICY = "newest"
# Newest campaign not usable for a mass -> the next newest one (log M, err, f, bibcode, reason).
MASS_CAMPAIGN = {
    "Mrk_1501": (7.85, 0.02, 4.47, "2022ApJS..262...14B",
                 "MAHA (Bao+2022, 2017-2021, all seasons, MICA lag, sigma_rms); Woo+2024 not used: Hb cadence 15 d vs lag 11.7 d"),
    "NGC_3516": (7.38, 0.085, 5.5, "2021ApJ...909...18F",
                 "Feng+2021 (Lijiang 2018-19, ICCF tau_cent x sigma_rms, asym +0.11/-0.06); Oknyansky+2021 gives only ~5e7 (FWHM, f=1.12) without an error"),
}
# Hb lags published only in the observed frame -> rest frame = obs / (1 + z_NED). (value, +err, -err, bibcode, note)
OBS_FRAME = {
    "IC_4329": (16.33, 2.59, 2.28, "2023ApJ...944...29B", "Bentz et al. 2023 Table 3, observed-frame tau_cent"),
    "Mrk_1239": (78.73, 7.20, 7.85, "2024ApJ...974...86L", "Li et al. 2024 Table 3, 2019 season (r_max 0.75), observed frame"),
    "PDS_456": (281.22, 49.29, 56.13, "2024ApJ...974...86L", "Li et al. 2024 Table 3, ICCF tau_cent, observed frame; authors caution Hb may not echo the continuum"),
}
# Types the catalogues get wrong for the current state of the source (value, bibcode, note).
TYPE_OVERRIDE = {
    "SDSS_J1430": ("Sy1.2", "2026arXiv260606802H", "changing-look AGN, turned on Sy1.9 -> Sy1.2 (SIMBAD still Sy2); arXiv only"),
}
# Known problems with the target position / identity in ava.db (copied into notes).
DB_ISSUES = {
    "IC_4329": "ava.db position is IC 4329 (the elliptical, ~3.6' away), not the AGN IC 4329A (13:49:19.3 -30:18:34); LCO frames/FLOYDS matched there",
}
BIB = re.compile(r"\d{4}[A-Za-z&.]{5}[\d.]{4}[A-Za-z.][\d.]{4}[A-Z.]")


def first_bib(v):
    m = BIB.search(str(v or ""))
    return m.group(0) if m else None


def norm_type(v):
    s = str(v or "").strip()
    m = re.match(r"(NLS1|Sy ?\d(?:\.\d)?|QSO|LINER|BL Lac|FSRQ|Blazar)", s)
    return m.group(1).replace("Sy ", "Sy") if m else None
t = pd.read_csv(C / "targets_matched.csv")
am = {o["name"]: o for o in json.load(open(C / "agnmass.json"))}
cat = {json.loads(l)["data_id"]: json.loads(l) for l in (C / "catalogs/catalogs.jsonl").read_text().splitlines()}
lit = {}
for b in "ABCE":
    p = C / f"lit/batch_{b}.json"
    if p.exists():
        for o in json.load(open(p)):
            lit[o["data_id"]] = o
newer = {o["data_id"]: o for b in "DF" if (C / f"lit/batch_{b}.json").exists() for o in json.load(open(C / f"lit/batch_{b}.json"))}

VCV = {"S1": "Sy1", "S1.0": "Sy1", "S1.2": "Sy1.2", "S1.5": "Sy1.5", "S1.8": "Sy1.8", "S1.9": "Sy1.9", "S1n": "NLS1",
       "S1h": "Sy1h", "S1i": "Sy1i", "S2": "Sy2", "S3": "LINER", "S3b": "LINER", "S": "Sy", "Q": "QSO", "BL": "BL Lac", "HP": "HPQ"}
NUM = r"(-?[\d.]+)"


def num(s):
    m = re.match(r"\s*" + NUM, str(s or ""))
    return float(m.group(1)) if m and m.group(1) not in (".", "...") else None


def pm(s):
    """'20.9 ( + 2.3 / - 2.3 )' -> (20.9, mean err); '43.73 (+/- 0.05)' -> (43.73, 0.05)."""
    s = str(s or "")
    v = num(s)
    if v is None:
        return None, None
    m = re.search(r"\+\s*([\d.]+)\s*/\s*-\s*([\d.]+)", s)
    if m:
        return v, round((float(m.group(1)) + float(m.group(2))) / 2, 3)
    m = re.search(r"\+/-\s*([\d.]+)", s)
    return v, (float(m.group(1)) if m else None)


def logmass(b):
    if not b:
        return None, None
    m = b["m"] * 10 ** b["exp"]; ep = b["ep"] * 10 ** b["exp"]; em = b["em"] * 10 ** b["exp"]
    return round(math.log10(m), 3), round(0.5 * (math.log10(m + ep) - math.log10(max(m - em, 1e-3))), 3)


def bib_of(text):
    """Bibcode from an AGNmass citation 'Author et al. YYYY Journal, vol, page' (ApJ/MNRAS/A&A/ApJS/AJ/PASP)."""
    m = re.search(r"(\d{4})\s+(ApJS|ApJL|ApJ|MNRAS|A&A|AJ|PASP|Nature)\s*,\s*(\d+)\s*,\s*L?(\d+)", text or "")
    if not m:
        return None
    y, j, v, p = m.groups(); jj = {"ApJL": "ApJ", "Nature": "Natur"}.get(j, j)
    letter = "L" if re.search(rf"{j}\s*,\s*{v}\s*,\s*L", text) or j == "ApJL" else "."
    return f"{y}{jj}{'.' * (5 - len(jj))}{v:>4}".replace(" ", ".") + f"{letter}{p:>4}".replace(" ", ".") + text.strip().split()[0][0]


def jd_end(r):
    m = re.findall(r"\d+", r["jd"]); return int(m[-1]) if m else 0


rows, refs, conflicts = [], {}, []
for r in t.itertuples():
    o = dict(data_id=r.data_id, name=r.name)
    c = cat.get(r.data_id, {})
    notes = []
    if r.data_id in SKIP:
        o["notes"] = SKIP[r.data_id]; rows.append(o); continue
    # --- redshift (NED) ---
    if c.get("ned_z") is not None and c.get("ned_sep", 99) < 10:
        o["z"] = round(float(c["ned_z"]), 6); o["z_ref"] = c.get("ned_zbib")   # NED stores float32: drop the noise
        if c.get("ned_name"):
            notes.append(f"NED: {c['ned_name']}")
    # --- type ---
    vt = VCV.get(str(c.get("vcv_sp") or "").strip())
    lt = norm_type((lit.get(r.data_id) or {}).get("agn_type"))
    if vt and lt and vt != lt:
        notes.append(f"type: VCV10 {vt}, literature {lt} ({first_bib(lit[r.data_id].get('type_ref')) or lit[r.data_id].get('type_ref')})")
    if vt and lt and vt in ("LINER", "Sy"):
        vt = None                                   # VCV gives no Seyfert subclass (e.g. Ark 564 'S3'): use the literature type
    if vt:
        o["agn_type"], o["type_ref"] = vt, "2010A&A...518A..10V"
    elif lt:
        o["agn_type"], o["type_ref"] = lt, (first_bib(lit[r.data_id].get("type_ref")) or "")
    elif c.get("sim_otype") in ("Sy1", "Sy2", "QSO", "BLL", "Bla"):
        o["agn_type"], o["type_ref"] = {"BLL": "BL Lac", "Bla": "Blazar"}.get(c["sim_otype"], c["sim_otype"]), "SIMBAD otype"
    if r.data_id in TYPE_OVERRIDE:
        tv, tb, tn = TYPE_OVERRIDE[r.data_id]
        notes.append(f"type: {tn}"); o["agn_type"], o["type_ref"] = tv, tb
    # --- AGNmass ---
    a = am.get(r.agnmass_name) if isinstance(r.agnmass_name, str) else None
    if a:
        lm, le = logmass(a["mbh_hb"]) if a["mbh_hb"] else logmass(a["mbh_all"])
        if lm is not None:
            o.update(log_MBH=lm, log_MBH_err=le, mbh_method=("RM Hb" if a["mbh_hb"] else "RM all lines") + ", <f>=4.3, AGNmass mean of campaigns; error statistical only (excl. ~0.3-0.4 dex f scatter)",
                     mbh_ref="2015PASP..127...67B")
        hb = [x for x in a["rows"] if x["line"].startswith("Hβ")]
        good = [x for x in hb if pm(x["tau_cent"])[0] is not None]
        span = lambda x: jd_end(x) - int((re.findall(r"\d+", x["jd"]) or [0])[0])
        campaigns = [x for x in good if span(x) <= 1000] or good   # skip multi-year sparse monitoring when a campaign exists
        if good:
            last = max(campaigns, key=jd_end)
            tau, te = pm(last["tau_cent"]); o.update(tau_hbeta_days=tau, tau_hbeta_err=te)
            o["tau_ref"] = resolve(last["rm_ref"]) or ""
            withL = [x for x in good if pm(x["logL"])[0] is not None]
            if withL:
                lx = last if last in withL else max(withL, key=jd_end)
                o["log_L5100"], o["l5100_ref"] = pm(lx["logL"])[0], resolve(lx["L_ref"]) or ""
                if lx is not last:
                    notes.append(f"L5100 from the campaign of JD {lx['jd']} (latest campaign has none)")
            o["key_reference"] = o["tau_ref"] or "2015PASP..127...67B"
            others = [f"{pm(x['tau_cent'])[0]} d (JD {x['jd']}; {x['rm_ref']})" for x in good if x is not last]
            if others:
                notes.append(f"AGNmass Hb lags (other campaigns): " + "; ".join(others[-6:]) + (f" (+{len(others) - 6} more)" if len(others) > 6 else ""))
            notes.append(f"lag = most recent AGNmass Hb campaign (JD {last['jd']}); centroid, rest frame")
        elif hb:
            notes.append("AGNmass lists Hb line width but no lag")
        if a.get("mbh_model"):
            mm, me = logmass(a["mbh_model"]); notes.append(f"dynamical-model mass logM={mm}±{me} ({a.get('model_ref')})")
    # --- newer campaign (batch D) ---
    n = newer.get(r.data_id) or {}
    only_lag = n.get("latest_tau_hbeta_days") is not None and o.get("tau_hbeta_days") is None
    if only_lag and n.get("is_well_sampled") not in (True, "true", "yes"):
        notes.append("lag: only published Hb lag, although the campaign does not meet the well-sampled rule (cadence <= tau/10)")
    if n.get("latest_tau_hbeta_days") is not None and (only_lag or n.get("is_well_sampled") in (True, "true", "yes")):
        if o.get("tau_hbeta_days") is not None:
            notes.append(f"AGNmass latest lag {o['tau_hbeta_days']}±{o.get('tau_hbeta_err')} d")
        o.update(tau_hbeta_days=n["latest_tau_hbeta_days"], tau_hbeta_err=n.get("latest_tau_err"), tau_ref=n.get("latest_ref"),
                 key_reference=n.get("latest_ref"))
        if n.get("latest_log_L5100") is not None:
            o.update(log_L5100=n["latest_log_L5100"], l5100_ref=n.get("latest_ref"))
    # --- mass from the newest campaign (MASS_POLICY) ---
    mc = MASS_CAMPAIGN.get(r.data_id)
    nm = (mc[0], mc[1], mc[2], mc[3]) if mc else (n.get("latest_log_MBH"), n.get("latest_log_MBH_err"), n.get("latest_f"), n.get("latest_ref"))
    if nm[0] is not None and MASS_POLICY == "agnmass" and o.get("log_MBH") is not None:
        notes.append(f"newest campaign mass logM={nm[0]}±{nm[1]} (f={nm[2]}, {nm[3]})")
    elif nm[0] is not None:
        if o.get("log_MBH") is not None:
            notes.append(f"AGNmass logM={o['log_MBH']}±{o.get('log_MBH_err')} (f=4.3, mean of campaigns)")
        if mc:
            notes.append(f"mass: {mc[4]}")
        o.update(log_MBH=nm[0], log_MBH_err=nm[1], mbh_method=f"RM Hb, newest campaign with a mass, f={nm[2]}", mbh_ref=nm[3])
    if n.get("other_new_campaigns"):
        notes.append("other recent campaigns: " + "; ".join(map(str, n["other_new_campaigns"])))
    if n.get("notes"):
        notes.append(str(n["notes"]))
    if n.get("mass_conflict"):
        conflicts.append(dict(data_id=r.data_id, source="literature (newer campaigns)",
                              detail="; ".join(map(str, n.get("other_new_campaigns") or []))[:600]
                              + (f"; latest {n.get('latest_ref')}: logM={n.get('latest_log_MBH')} f={n.get('latest_f')}" if n.get("latest_log_MBH") is not None else "")))
    # --- literature for non-AGNmass targets ---
    li = lit.get(r.data_id)
    if li:
        for k_out, k_in in [("log_MBH", "log_MBH"), ("log_MBH_err", "log_MBH_err"), ("mbh_method", "mbh_method"), ("mbh_ref", "mbh_ref"),
                            ("tau_hbeta_days", "tau_hbeta_days"), ("tau_hbeta_err", "tau_hbeta_err"), ("tau_ref", "tau_ref"),
                            ("log_L5100", "log_L5100"), ("l5100_ref", "l5100_ref"), ("key_reference", "key_reference")]:
            if o.get(k_out) in (None, "") and li.get(k_in) not in (None, ""):
                o[k_out] = first_bib(li[k_in]) or li[k_in] if k_out.endswith("ref") or k_out == "key_reference" else li[k_in]
        if li.get("notes"):
            notes.append(str(li["notes"]))
    if r.data_id in OBS_FRAME and o.get("tau_hbeta_days") in (None, "") and o.get("z") is not None:
        v, ep, em, bib, why = OBS_FRAME[r.data_id]; zz = 1 + o["z"]
        o.update(tau_hbeta_days=round(v / zz, 2), tau_hbeta_err=round((ep + em) / 2 / zz, 2), tau_ref=bib)
        o["key_reference"] = o.get("key_reference") or bib
        notes.insert(0, f"lag converted to rest frame here: {v} +{ep}/-{em} d observed / (1+z={o['z']}) ({why})")
    if r.data_id in DB_ISSUES:
        notes.insert(0, "DB ISSUE: " + DB_ISSUES[r.data_id])
    o["notes"] = " | ".join(notes)
    rows.append(o)

COLS = ["data_id", "name", "z", "log_MBH", "log_MBH_err", "tau_hbeta_days", "tau_hbeta_err", "log_L5100", "agn_type",
        "key_reference", "notes", "z_ref", "mbh_method", "mbh_ref", "tau_ref", "l5100_ref", "type_ref"]
df = pd.DataFrame(rows).reindex(columns=COLS)
df.to_csv(L / "agn_properties.csv", index=False)
bibs = sorted({str(v) for c in ["z_ref", "mbh_ref", "tau_ref", "l5100_ref", "type_ref", "key_reference"] for v in df[c].dropna() if re.match(r"^\d{4}\S{15}$", str(v))})
CATALOG_CITES = {  # catalogue bibcodes without an ADS paper record
    "1991RC3.9.C...0000d": "RC3 (1991)", "1992CORV..C...0000F": "ZCAT (1992)", "1992NED11.R......1N": "NED (1992)",
    "2000UZC...C......0F": "UZC (2000)", "20096dF...C...0000J": "6dFGS (2009)", "2016SDSSD.C...0000:": "SDSS DR13 (2016)",
}
pd.DataFrame([dict(bibcode=b, cite=CATALOG_CITES.get(b) or cite(b) or "") for b in bibs]).to_csv(L / "references.csv", index=False)
pd.DataFrame(conflicts).to_csv(C / "conflicts_batchD.csv", index=False)
print(f"wrote {L / 'agn_properties.csv'}: {len(df)} rows")
