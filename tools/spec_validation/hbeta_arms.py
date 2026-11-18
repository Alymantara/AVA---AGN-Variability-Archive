"""Hβ fit shown on one spectrum, and tested independently on each FLOYDS arm (blue = order 2, red = order 1).

    hbeta_arms.py [target] [spectrum-substring]     (AVA_CONFIG selects the archive; default fairall_9)

The red order covers Hβ only when its blue end (≈4500-4900 Å observed) is below the fit window (here
Fairall 9 at z = 0.046).  Figure → <spec>/<target>/plots/hbeta_fit_arms.png; table → hbeta_arms.csv."""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))   # repository root
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ava.config import cfg
from ava.plots import webplots as wp
from ava.spectroscopy import lines as L
from ava.spectroscopy import products as P

target = sys.argv[1] if len(sys.argv) > 1 else "fairall_9"
pick = sys.argv[2] if len(sys.argv) > 2 else None
z = float(cfg.target_by_data_id(target)["redshift"])
files = P.reduced_files(cfg.spec_dir(target))
out = cfg.spec_dir(target) / "plots"
wp._style(); plt.rcParams.update({"font.size": 9, "legend.frameon": False, "legend.fontsize": 7})
s = L.FitSettings()
ARMS = {"blue": 2, "red": 1}


def rob(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return 1.4826 * np.median(np.abs(x - np.median(x))) if len(x) else np.nan


# ---- every spectrum, each arm on its own
rows = []
for f in files:
    h = P._header(f)
    row = {"spectrum": Path(f).name.split("-e91")[0], "night": Path(f).name.split("-")[2], "MJD": h["MJD-OBS"],
           "qc": h["L1QFLAGS"]}
    for arm, order in ARMS.items():
        r = L.fit_hbeta(L.blue_arm(f, z, order=order), s)
        row.update({f"{arm}_{k}": r.get(k, np.nan) for k in ("ok", "hb_broad", "hb_broad_err", "oiii5007",
                                                             "oiii5007_err", "hb_fwhm_kms", "chi2nu", "oiii_shift_A",
                                                             "cont5100", "cont5100_err", "reason")})
    rows.append(row)
T = pd.DataFrame(rows)
for arm in ARMS:
    t = T.rename(columns=lambda c: c[len(arm) + 1:] if c.startswith(arm + "_") else c)
    t["ok"] = t["ok"].fillna(False).astype(bool)
    t, _ = L.oiii_calibrate(t, good=t.qc.eq("OK"))
    T[f"{arm}_hb_cal"] = t["hb_broad_cal"]
T.assign(MJD=T["MJD"].map("{:.6f}".format)).to_csv(out / "hbeta_arms.csv", index=False,
                                                float_format="%.6g")   # MJD to 1e-6 d (QC-0002)
ok = T.blue_ok.astype(bool) & T.red_ok.astype(bool)


def pair_scatter(col):
    d = []
    for _, g in T[ok].groupby("night"):
        if len(g) >= 2:
            v = g[col].to_numpy()
            d.append((v[1] - v[0]) / v[:2].mean())
    return 100 * rob(d) / np.sqrt(2), len(d)


summary = {"spectra": len(T), "fitted both arms": int(ok.sum())}
for q in ("hb_broad", "oiii5007", "hb_cal", "hb_fwhm_kms", "oiii_shift_A"):
    if q in ("hb_fwhm_kms", "oiii_shift_A"):
        summary[f"{q}: red − blue (median, robust σ)"] = (
            round(float(np.median(T[f"red_{q}"][ok] - T[f"blue_{q}"][ok])), 2),
            round(float(rob(T[f"red_{q}"][ok] - T[f"blue_{q}"][ok])), 2))
    else:
        rr = T[f"red_{q}"][ok] / T[f"blue_{q}"][ok]
        summary[f"{q}: red/blue (median, robust σ %)"] = (round(float(np.median(rr)), 4), round(100 * rob(rr), 2))
for arm in ARMS:
    summary[f"{arm}: Hβ [O III]-cal same-night pair σ (%, pairs)"] = tuple(round(x, 2) for x in pair_scatter(f"{arm}_hb_cal"))
    summary[f"{arm}: median Hβ S/N"] = round(float(np.median((T[f"{arm}_hb_broad"] / T[f"{arm}_hb_broad_err"])[ok])), 1)
for k, v in summary.items():
    print(f"{k}: {v}")

# ---- the example
ex = next((f for f in files if pick and pick in Path(f).name), None) or \
    max(files, key=lambda f: P._header(f)["L1QSN2"] or 0)
fig, ax = plt.subplots(2, 2, figsize=(13, 7), sharex=True, gridspec_kw=dict(height_ratios=[3, 1]))
lo, hi = 4740, 5110
g = np.linspace(s.fit_window[0], s.fit_window[1], 2000)
for j, (arm, order) in enumerate(ARMS.items()):
    sp = L.blue_arm(ex, z, order=order)
    r = L.fit_hbeta(sp, s)
    x = sp[(sp.w > lo) & (sp.w < hi)]
    a = ax[0, j]
    a.errorbar(x.w, x.f / 1e-15, x.e / 1e-15, fmt="none", ecolor="0.75", elinewidth=0.5)
    a.plot(x.w, x.f / 1e-15, color="k", lw=0.7, drawstyle="steps-mid", label="data")
    if r.get("params"):
        p = r["params"]
        c = L.model(p, g, s, "cont")
        a.plot(g, L.model(p, g, s) / 1e-15, color="#D55E00", lw=1.2, label="total model")
        a.plot(g, c / 1e-15, color="0.5", lw=0.8, ls="--", label="continuum")
        a.plot(g, (c + L.model(p, g, s, "hb_broad")) / 1e-15, color="#0072B2", lw=1.1, label="broad Hβ")
        a.plot(g, (c + L.model(p, g, s, "oiii") + L.model(p, g, s, "hb_narrow")) / 1e-15, color="#009E73", lw=0.9,
               label="[O III] + narrow Hβ")
        mod = np.interp(x.w, g, L.model(p, g, s))
        ax[1, j].plot(x.w, (x.f - mod) / x.e, color="k", lw=0.6, drawstyle="steps-mid")
        txt = (f"broad Hβ = {r['hb_broad'] / 1e-13:.3f} ± {r['hb_broad_err'] / 1e-13:.3f} ×10$^{{-13}}$\n"
               f"[O III] 5007 = {r['oiii5007'] / 1e-13:.3f} ± {r['oiii5007_err'] / 1e-13:.3f} ×10$^{{-13}}$\n"
               f"FWHM(Hβ) = {r['hb_fwhm_kms']:.0f} km/s,  χ²$_ν$ = {r['chi2nu']:.2f}")
        a.text(0.99, 0.97, txt, transform=a.transAxes, ha="right", va="top", fontsize=8,
               bbox=dict(facecolor="white", edgecolor="none", alpha=0.85))
    for lam in (L.HB, L.O3A, L.O3B):
        a.axvline(lam, color="0.85", lw=0.6, ls=":", zorder=0)
    for w0, w1 in s.continuum_windows:
        a.axvspan(w0, w1, color="0.93", zorder=-1, lw=0)
    a.set_title(f"{arm} arm (order {order})")
    a.set_ylabel(r"$F_\lambda$ ($10^{-15}$ cgs)")
    ax[1, j].axhline(0, color="0.6", lw=0.6)
    ax[1, j].set_ylim(-6, 6); ax[1, j].set_ylabel("residual / σ"); ax[1, j].set_xlabel("rest wavelength (Å)")
ax[0, 0].legend(loc="upper left")
fig.suptitle(f"{cfg.target_by_data_id(target)['name']} — {Path(ex).name.split('-e91')[0]}  (z = {z}); "
             "grey bands: continuum windows", fontsize=10)
fig.tight_layout()
fig.savefig(out / "hbeta_fit_arms.png", dpi=140, bbox_inches="tight")
print(out / "hbeta_fit_arms.png")
