"""Usage: python tools/abscal_validation/anchor_sweep.py OUT.csv

Sweep: current absolute ZP (A) vs all-star anchors with a relative variability cut (D) for every field and band."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import anchor_stars as A
rows = []
for d in sorted(A.PH.iterdir()):
    pd_ = d / "pytics"
    if not pd_.is_dir() or not (d / "reference_stars.csv").exists():
        continue
    zpj = json.loads((pd_ / "absolute_zp.json").read_text()) if (pd_ / "absolute_zp.json").exists() else {}
    for f in ["up", "B", "gp", "V", "rp", "ip", "zs", "Y"]:
        if not (pd_ / f / "stars.parquet").exists():
            continue
        try:
            allst, ref, meta = A.star_means(d.name, f)
        except Exception as e:
            rows.append(dict(field=d.name, filter=f, error=str(e)[:80])); continue
        comp = pd.read_parquet(pd_ / f / "stars.parquet")
        cc = comp.merge(allst[["star_id", "m_star", "n"]], on="star_id", suffixes=("", "_o"))
        full = cc.n_o >= 0.9 * cc.n_o.max()
        gauge = float(np.median((cc.m_star_o - cc.m_star)[full])) if full.any() else np.nan
        c_agn = zpj.get(f, {}).get("agn_colour", meta.get("agn_colour", 0.5))
        Afit = A.fit(d.name, f, comp, ref)
        D_in = allst[(allst.n >= 0.9 * allst.n.max()) & (allst.rms_star <= 0.2)].sort_values("m_star").copy()
        trend = D_in.rms_star.rolling(15, center=True, min_periods=5).median()
        D_in["rms_raw"] = D_in.rms_star
        D_in["rms_star"] = np.sqrt(np.clip(D_in.rms_star ** 2 - trend ** 2, 0, None))
        D_in["m_star_err"] = D_in.rms_raw / np.sqrt(D_in.n)
        Dfit = A.fit(d.name, f, D_in, ref)
        za = lambda z: z["zp"] + z["C"] * (c_agn - z["c0"])
        rows.append(dict(field=d.name, filter=f, nA=Afit["n"], scA=Afit["scatter"], zpA=za(Afit), errA=Afit["zp_err"],
                         nD=Dfit["n"], scD=Dfit["scatter"], zpD=za(Dfit) + gauge, errD=Dfit["zp_err"], CA=Afit["C"], CD=Dfit["C"],
                         gauge_sd=float(np.std((cc.m_star_o - cc.m_star)[full])) if full.any() else np.nan))
r = pd.DataFrame(rows); r["dzp"] = r.zpD - r.zpA
r.to_csv(sys.argv[1], index=False)
pd.set_option("display.width", 220); pd.set_option("display.max_rows", 400)
s = r.copy()
for c in ["scA", "scD", "errA", "errD", "dzp", "gauge_sd"]:
    s[c] = (s[c] * 1e3).round(1)
print(s[["field", "filter", "nA", "nD", "scA", "scD", "errA", "errD", "dzp", "gauge_sd"]].to_string(index=False))
