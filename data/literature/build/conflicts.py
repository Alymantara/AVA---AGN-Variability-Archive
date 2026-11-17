"""Black-hole-mass conflicts between RM campaigns, and between the new CSV and the current ava.db values.

Per-campaign virial masses from AGNmass (tau_cent, sigma_line rms; M = f c tau sigma^2 / G, f = 4.3, as AGNmass).
A target is flagged when campaign masses span > 0.3 dex AND the extreme pair differs by > 3 sigma (combined).
"""
import json, math, re, sqlite3, sys
from pathlib import Path
import pandas as pd

L = Path(sys.argv[1]).resolve(); C = L / "cache"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_csv_helpers import pm  # noqa: E402

G, c, MSUN, F = 6.674e-8, 2.998e10, 1.989e33, 4.3
am = {o["name"]: o for o in json.load(open(C / "agnmass.json"))}
t = pd.read_csv(C / "targets_matched.csv")
out = []
for r in t.itertuples():
    a = am.get(r.agnmass_name) if isinstance(r.agnmass_name, str) else None
    if not a:
        continue
    ms = []
    for x in a["rows"]:
        if not x["line"].startswith("Hβ"):
            continue
        tau, te = pm(x["tau_cent"]); s, se = pm(x["sigma"])
        if not tau or not s or tau <= 0:
            continue
        lm = math.log10(F * c * tau * 86400 * (s * 1e5) ** 2 / G / MSUN)
        le = math.hypot((te or 0) / tau, 2 * (se or 0) / s) / math.log(10)
        ms.append((lm, le, x["jd"], (x["rm_ref"] or "").split(" et al")[0] + " " + (re.findall(r"\d{4}", x["rm_ref"]) or [""])[0]))
    if len(ms) < 2:
        continue
    lo, hi = min(ms), max(ms)
    nsig = (hi[0] - lo[0]) / math.hypot(lo[1], hi[1]) if (lo[1] or hi[1]) else float("inf")
    if hi[0] - lo[0] > 0.3 and nsig > 3:
        out.append(dict(data_id=r.data_id, kind="RM campaigns (Hb, f=4.3)", n=len(ms), range_dex=round(hi[0] - lo[0], 2), nsigma=round(nsig, 1),
                        low=f"{lo[0]:.2f}±{lo[1]:.2f} ({lo[3]}, JD {lo[2]})", high=f"{hi[0]:.2f}±{hi[1]:.2f} ({hi[3]}, JD {hi[2]})"))

# CSV vs current ava.db curated mass
p = pd.read_csv(L / "agn_properties.csv")
with sqlite3.connect(f"file:{L.parent / 'ava.db'}?mode=ro", uri=True) as con:
    db = pd.read_sql("SELECT data_id, logm, logm_url FROM agn", con)
m = p.merge(db, on="data_id")
for r in m.itertuples():
    if pd.notna(r.log_MBH) and pd.notna(r.logm) and r.logm > 3 and abs(r.log_MBH - r.logm) > 0.3:
        out.append(dict(data_id=r.data_id, kind="new CSV vs ava.db agn.logm", n=2, range_dex=round(abs(r.log_MBH - r.logm), 2), nsigma=None,
                        low=f"CSV {r.log_MBH:.2f} ({r.mbh_ref})", high=f"ava.db {r.logm:.2f} ({r.logm_url})"))
bd = C / "conflicts_batchD.csv"
if bd.exists() and bd.stat().st_size > 2:
    for r in pd.read_csv(bd).itertuples():
        out.append(dict(data_id=r.data_id, kind="literature (newer campaigns)", n=None, range_dex=None, nsigma=None, low=r.detail, high=""))
pd.DataFrame(out).to_csv(L / "mass_conflicts.csv", index=False)
print(pd.DataFrame(out).to_string(index=False))
