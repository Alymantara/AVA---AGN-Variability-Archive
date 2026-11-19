"""Per field and band: frames (all / QC pass), usable GSPC anchors, absolute ZP fit (n, scatter, C), and the
reason a band has no light curve. Read-only."""
import json, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ava.config import cfg  # noqa: E402
PH = cfg.phot_root
F2B = dict(up="u", B="B", gp="g", V="V", rp="r", ip="i", zs="z", Y="Y")
qc = pd.read_sql("select data_id, filter, count(*) n, sum(qc_pass) npass, sum(n_zp is not null and zp is not null) nzp from frame_qc group by 1,2",
                 sqlite3.connect(f"file:{cfg.archive_root / 'frame_qc.sqlite'}?mode=ro", uri=True))
rows = []
for d in sorted(PH.iterdir()):
    if not (d / "reference_stars.csv").exists():
        continue
    ref = pd.read_csv(d / "reference_stars.csv")
    ok = ref["quality_ok"].astype(bool) & ~ref["is_agn"].astype(bool)
    meta = {}
    mp = d / "reference_stars_meta.yaml"
    if mp.exists():
        import yaml; meta = yaml.safe_load(mp.read_text()) or {}
    zpj = json.loads((d / "pytics/absolute_zp.json").read_text()) if (d / "pytics/absolute_zp.json").exists() else {}
    for f, b in F2B.items():
        q = qc[(qc.data_id == d.name) & (qc["filter"] == f)]
        col = f"lco_{b}"
        nref = int((ok & ref[col].notna()).sum()) if col in ref else 0
        src = ref.loc[ok & ref[col].notna(), "lco_u_src"].value_counts().to_dict() if (b == "u" and "lco_u_src" in ref) else {}
        z = zpj.get(f, {})
        rows.append(dict(field=d.name, filter=f, frames=int(q.n.sum()), qc_pass=int(q.npass.sum()), frames_zp=int(q.nzp.sum()),
                         ref_usable=nref, u_src=src or "", ref_method=meta.get("method", ""),
                         pytics=(d / "pytics" / f).is_dir(), zp_n=z.get("n"), zp_scatter=z.get("scatter"), zp_C=z.get("C"),
                         colour_terms=z.get("colour_terms")))
t = pd.DataFrame(rows)
t.to_csv(sys.argv[1], index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
s = t[t.frames > 0].copy()
s["zp_scatter"] = (s.zp_scatter * 1e3).round(0)
print(s.drop(columns=["ref_method", "zp_C", "colour_terms"]).to_string(index=False))
