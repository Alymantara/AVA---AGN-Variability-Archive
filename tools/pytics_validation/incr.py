"""Incremental-update tests: (A) hold out the last 60 days and add night by night;
(B) hold out from 61058 (a new scope, 1m006-fa11, appears). Compare with a full refit."""
import sys, time, warnings; warnings.filterwarnings("ignore"); sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))   # repository root
from pathlib import Path; import numpy as np, pandas as pd
from ava.config import cfg  # noqa: E402  (AVA_CONFIG selects the archive; AVA_TARGET the target)
from ava.pipeline.tasks.calibrate import frame_db_path  # noqa: E402
TARGET = __import__("os").environ.get("AVA_TARGET", "Mrk_817")
from ava.photometry import ensemble as E
PHOT = cfg.phot_dir(TARGET); DB = frame_db_path()
OUT = Path(sys.argv[1]); OUT.mkdir(exist_ok=True)
rows, nightly = [], []
for f in ["up", "B", "gp", "V", "rp", "ip", "zs"]:
    d = E.load_target(PHOT, DB, TARGET, f); agn = int(d.loc[d.is_agn, "star_id"].iloc[0])
    full = E.fit(d, agn_id=agn)
    lc_full = E.apply(full, d[d.is_agn])[["frame", "MJD", "scope", "mag", "mag_err"]]
    for test, cut in [("A_last60d", d.MJD.max() - 60), ("B_newscope", 61058.0)]:
        old = d[d.MJD < cut]
        t0 = time.time(); base = E.fit(old, agn_id=agn); t_base = time.time() - t0
        # night-by-night updates
        new = d[d.MJD >= cut]; nights = np.sort(np.unique(np.floor(new.MJD - 0.5)))
        sol = base; times = []; reasons = []
        for n in nights:
            upto = d[d.MJD < n + 1.5]
            t0 = time.time(); sol, info = E.update(sol, upto); times.append(time.time() - t0)
            reasons = info["needs_refit"] or reasons
            nightly.append(dict(filter=f, test=test, night=n, n_new=info["new_epochs"], ms=1e3 * times[-1]))
        lc_up = E.apply(sol, d[d.is_agn])[["frame", "MJD", "scope", "mag", "mag_err"]]
        lc_old = E.apply(base, old[old.is_agn])[["frame", "mag"]]
        m = lc_up.merge(lc_full, on=["frame", "MJD", "scope"], suffixes=("_up", "_full"))
        m["new"] = m.MJD >= cut
        dd = m.mag_up - m.mag_full
        hist = lc_old.merge(lc_full, on="frame", suffixes=("_old", "_full"))
        hd = hist.mag_old - hist.mag_full
        m.assign(filter=f, test=test).to_parquet(OUT / f"cmp_{f}_{test}.parquet")
        r = dict(filter=f, test=test, n_new=int(m.new.sum()), nights=len(nights),
                 base_fit_s=round(t_base, 2), update_ms_median=round(1e3 * np.median(times), 1),
                 update_ms_total=round(1e3 * np.sum(times), 0), full_fit_s=full.meta["seconds"],
                 new_off_mmag=round(1e3 * dd[m.new].median(), 2),
                 new_scatter_mmag=round(1e3 * (dd[m.new] - dd[m.new].median()).std(), 2),
                 new_max_mmag=round(1e3 * (dd[m.new] - dd[m.new].median()).abs().max(), 1),
                 hist_off_mmag=round(1e3 * hd.median(), 2), hist_scatter_mmag=round(1e3 * (hd - hd.median()).std(), 2),
                 med_err_mmag=round(1e3 * m.mag_err_full[m.new].median(), 1), refit=";".join(reasons))
        rows.append(r); print(r, flush=True)
pd.DataFrame(rows).to_csv(OUT / "incremental_summary.csv", index=False)
pd.DataFrame(nightly).to_csv(OUT / "incremental_nightly.csv", index=False)
