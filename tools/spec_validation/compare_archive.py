"""Our FLOYDS reduction (improved banzai-floyds) vs the archive products, for a target's reduced nights.

    compare_archive.py [target] [redshift]      (AVA_CONFIG selects the archive; default Mrk_817)

Per science spectrum: flux ratio ours/archive (5500-6500 A), [O III] 5007 centroid offset from the
redshifted position, red-end small-scale scatter (fringing: robust rms of spectrum / 150-A running median,
7700-8500 A).  Figure → <spec_root>/<target>/plots/compare_archive.png, table → compare_archive.csv."""
import sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/Users/juan/astro/AVA")
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from astropy.io import fits
from scipy.ndimage import median_filter
from ava.config import cfg
from ava.plots import webplots as wp

target = sys.argv[1] if len(sys.argv) > 1 else "Mrk_817"
z = float(sys.argv[2]) if len(sys.argv) > 2 else float(cfg.target_by_data_id(target).get("redshift") or 0)
wp._style(); plt.rcParams.update({"font.size": 9, "legend.frameon": False, "legend.fontsize": 7})
red_dir, arc_dir = cfg.spec_dir(target) / "reduced", cfg.spec_dir(target) / "archive"
out_dir = cfg.spec_dir(target) / "plots"; out_dir.mkdir(parents=True, exist_ok=True)


def read_extracted(path, split=5300.0):
    """Our product from the per-order EXTRACTED table (fringe-corrected): blue order below ``split``, red above.
    The fork's merged SPECTRUM is re-extracted from the 2-d data, which the harmonic method leaves uncorrected."""
    d = fits.getdata(path, "EXTRACTED")
    o, w = np.asarray(d["order"]), np.asarray(d["wavelength"], float)
    sel = ((o == 2) & (w < split)) | ((o == 1) & (w >= split))
    sel &= np.isfinite(np.asarray(d["flux_optimal"], float)) & (np.asarray(d["mask"]) == 0)
    return pd.DataFrame({"w": w[sel], "f": np.asarray(d["flux_optimal"], float)[sel],
                         "e": np.asarray(d["fluxerror_optimal"], float)[sel]}).sort_values("w")


def read(path, ours):
    d = fits.getdata(path, "SPECTRUM")
    f = d["flux_optimal"] if ours else d["flux"]
    e = d["fluxerror_optimal"] if ours else d["fluxerror"]
    w = np.asarray(d["wavelength"], float); ok = np.isfinite(f) & (np.asarray(d["mask"]) == 0)
    return pd.DataFrame({"w": w[ok], "f": np.asarray(f, float)[ok], "e": np.asarray(e, float)[ok]}).sort_values("w")


def rob(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return 1.4826 * np.median(np.abs(x - np.median(x))) if len(x) else np.nan


def win(s, a, b):
    return s[(s.w > a) & (s.w < b)]


def centroid(s, lam, half=25):
    x = win(s, lam - half, lam + half)
    c = win(s, lam - 4 * half, lam - 2 * half).f.median() + win(s, lam + 2 * half, lam + 4 * half).f.median()
    y = np.clip(x.f - c / 2, 0, None)
    return float((x.w * y).sum() / y.sum()) - lam if y.sum() > 0 else np.nan


def fringe(s, a=7700, b=8500):
    x = win(s, a - 200, b + 200)
    step = np.median(np.diff(x.w)); k = max(int(150 / step) | 1, 3)
    r = x.f / median_filter(x.f.values, k, mode="nearest")
    return 100 * rob(r[(x.w > a) & (x.w < b)])


rows, pairs = [], []
for ours in sorted(red_dir.glob("*/*-e91-1d.fits*")):
    arch = arc_dir / ours.parent.name / ours.name
    if not arch.exists():
        continue
    a, o, om = read(arch, False), read_extracted(ours), read(ours, True)
    oiii = 5006.84 * (1 + z)
    ratio = np.median(np.interp(win(o, 5500, 6500).w, a.w, a.f) / win(o, 5500, 6500).f)
    rows.append(dict(spectrum=ours.name.split("-e91")[0], night=ours.parent.name,
                     archive_over_ours=ratio, oiii_offset_ours_A=centroid(o, oiii), oiii_offset_archive_A=centroid(a, oiii),
                     fringe_ours_pct=fringe(o), fringe_ours_merged_SPECTRUM_pct=fringe(om), fringe_archive_pct=fringe(a),
                     sn_ours=float(np.median(win(o, 6000, 6500).f / win(o, 6000, 6500).e)),
                     sn_archive=float(np.median(win(a, 6000, 6500).f / win(a, 6000, 6500).e))))
    pairs.append((ours.name.split("-e91")[0], o, a, ratio))
R = pd.DataFrame(rows)
R.round(3).to_csv(out_dir / "compare_archive.csv", index=False)
pd.set_option("display.width", 220); print(R.round(2).to_string())

n = len(pairs)
fig, ax = plt.subplots(n, 3, figsize=(15, 2.6 * n), gridspec_kw=dict(width_ratios=[2.2, 1, 1]), squeeze=False)
for i, (name, o, a, ratio) in enumerate(pairs):
    sc = 1e15
    ax[i, 0].plot(a.w, sc * a.f / ratio, color="0.6", lw=0.6, label=f"archive (1.0.1) ÷ {ratio:.2f}")
    ax[i, 0].plot(o.w, sc * o.f, color="#0072B2", lw=0.6, label="AVA: improved banzai-floyds (EXTRACTED)")
    ax[i, 0].set_xlim(3300, 9800); ax[i, 0].set_ylabel(r"$F_\lambda$ (10$^{-15}$ cgs)")
    ax[i, 0].text(0.01, 0.9, name, transform=ax[i, 0].transAxes, fontsize=8)
    for j, (lo, hi) in enumerate([(4700, 5300), (7400, 9200)]):
        aa, oo = win(a, lo, hi), win(o, lo, hi)
        if j == 1:   # normalised red end: fringing
            ax[i, 2].plot(aa.w, aa.f / median_filter(aa.f.values, 31, mode="nearest"), color="0.6", lw=0.6)
            ax[i, 2].plot(oo.w, oo.f / median_filter(oo.f.values, 31, mode="nearest"), color="#0072B2", lw=0.6)
            ax[i, 2].set_ylim(0.7, 1.3)
        else:
            ax[i, 1].plot(aa.w, sc * aa.f / ratio, color="0.6", lw=0.6)
            ax[i, 1].plot(oo.w, sc * oo.f, color="#0072B2", lw=0.6)
            for l in (4861.33, 4958.91, 5006.84):
                ax[i, 1].axvline(l * (1 + z), color="0.8", lw=0.5, ls=":")
    ax[i, 0].legend(loc="upper right")
ax[0, 1].set_title(r"H$\beta$ + [O III] (dotted: redshift)"); ax[0, 2].set_title("red end ÷ running median (fringing)")
for a_ in ax[-1]:
    a_.set_xlabel("wavelength (Å)")
fig.tight_layout(); fig.savefig(out_dir / "compare_archive.png", dpi=130, bbox_inches="tight")
print(out_dir / "compare_archive.png")
