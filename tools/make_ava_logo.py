"""
AVA Logo Generator — Fairall 9 multi-wavelength daisy-chain light curve.

Design (matching the original AVA banner):
  - All filters observe the SAME ~30-day epoch so variability is correlated
  - Each filter is normalised independently to the same vertical range
    so amplitude looks consistent but the SHAPE is the real light curve
  - Filters plotted sequentially in wavelength order UV→NIR
  - Each filter used exactly once; blocks sized by n_pts for uniform density

Usage:
    from make_ava_logo import make_logo
    img = make_logo(width=2400, height=200, bg=(10,22,40))
"""

from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np
import pandas as pd

F9_CSV = Path("/mnt/user-data/uploads/AVA/docs/figures/F9_all_aper_v1.csv")
FDICT  = Path("/mnt/user-data/uploads/AVA/data/reference/filter_dict.txt")

CSV_TO_FD = {
    'W2': 'UVW2', 'M2': 'UVM2', 'W1': 'UVW1',
    'US': 'Us',   'BS': 'Bs',   'VS': 'Vs',
    'BL': 'B',    'VL': 'V',
    'uL': 'u',    'gL': 'g',    'rL': 'r',    'iL': 'i',    'zL': 'z',
}

FILTER_ORDER = ['W2', 'M2', 'W1', 'US', 'BS', 'BL', 'uL', 'VS', 'gL', 'VL', 'rL', 'iL', 'zL']

def _hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _named_to_rgb(name):
    named = {
        'k':      ( 50,  50,  50),
        'grey':   (160, 160, 160),
        'gray':   (160, 160, 160),
        'orange': (255, 140,   0),
        'brown':  (160, 100,  40),
        'red':    (200,  30,  30),
    }
    return named.get(name.lower(), (200, 200, 200))

def load_filter_colours():
    fd = pd.read_csv(FDICT)
    out = {}
    for _, row in fd.iterrows():
        c = str(row['color']).strip()
        out[row['Filter']] = _hex_to_rgb(c) if c.startswith('#') else _named_to_rgb(c)
    return out

def _find_best_epoch(f9, present, window=30, min_pts_per_filter=15):
    """Find the epoch where ALL filters have good coverage and variability."""
    mjd_min = f9['MJD'].min()
    mjd_max = f9['MJD'].max()
    best_score, best_start = -1, mjd_min
    for s in np.linspace(mjd_min, mjd_max - window, 100):
        score = 0
        all_ok = True
        for filt in present:
            sub = f9[f9['Filter'] == filt]
            win = sub[(sub['MJD'] >= s) & (sub['MJD'] < s + window)]
            if len(win) < min_pts_per_filter:
                all_ok = False
                break
            amp = win['Flux'].max() - win['Flux'].min()
            score += len(win) * amp / win['Flux'].mean()
        if all_ok and score > best_score:
            best_score = score
            best_start = s
    return best_start

def make_logo(
    width:         int   = 2400,
    height:        int   = 220,
    bg:            tuple = (10, 22, 40),
    margin_x_frac: float = 0.008,
    margin_y_frac: float = 0.10,
    epoch_start:   float = None,   # MJD start; None = auto-detect best epoch
    window_days:   float = 30.0,
    amp_frac:      float = 0.72,   # fraction of plot height for peak-to-trough
) -> Image.Image:
    """
    AVA daisy-chain logo using a single shared epoch for all filters.

    All filters show the same ~30-day window, normalised per-filter to
    the same vertical amplitude. The curve shape is the REAL correlated
    AGN variability, so it gently undulates rather than oscillating wildly.
    Filters are stitched end-to-end: each segment is shifted vertically
    so its first point continues from the last point of the previous filter.
    """
    f9      = pd.read_csv(F9_CSV)
    colours = load_filter_colours()

    def filt_col(csv_name):
        return colours.get(CSV_TO_FD.get(csv_name, csv_name), (200, 200, 200))

    present = [f for f in FILTER_ORDER if f in f9['Filter'].values]

    mx = int(width  * margin_x_frac)
    my = int(height * margin_y_frac)
    plot_w = width  - 2 * mx
    plot_h = height - 2 * my
    amp    = plot_h * amp_frac
    centre = my + plot_h // 2

    # --- Find shared epoch ---
    if epoch_start is None:
        epoch_start = None   # use full campaign

    # --- Extract each filter's data: full campaign or specified epoch ---
    excerpts = {}
    for filt in present:
        sub = f9[f9['Filter'] == filt].sort_values('MJD')
        if epoch_start is not None:
            win = sub[(sub['MJD'] >= epoch_start) & (sub['MJD'] < epoch_start + window_days)]
            if len(win) < 5:
                idx = (sub['MJD'] - epoch_start).abs().argsort()[:20]
                win = sub.iloc[sorted(idx)].copy()
        else:
            win = sub   # full campaign
        excerpts[filt] = win.reset_index(drop=True)

    # --- Normalise each filter to [-0.5, +0.5] using its own range ---
    # This makes all filters have the same visual amplitude while preserving
    # the real variability shape (correlated across bands since same epoch)
    normed = {}
    for filt in present:
        flux = excerpts[filt]['Flux'].values.astype(float)
        err  = excerpts[filt]['Error'].values.astype(float)
        lo   = np.percentile(flux, 5)
        hi   = np.percentile(flux, 95)
        rng  = hi - lo if hi > lo else flux.std() * 2 or 1.0
        mid  = (lo + hi) / 2.0
        normed[filt] = {
            'n':   (flux - mid) / rng,    # in [-0.5, 0.5]
            'e':    err / rng,
        }

    # --- Allocate x-pixels proportional to n_pts for uniform dot density ---
    n_pts   = {f: len(excerpts[f]) for f in present}
    total_n = sum(n_pts.values())
    block_w = {f: max(4, int(plot_w * n_pts[f] / total_n)) for f in present}
    used = sum(block_w.values())
    block_w[present[-1]] += (plot_w - used)

    # --- Build pixel coordinates, no stitching needed ---
    # All filters use the same epoch so shapes are correlated; each is
    # independently centred at plot midline. Gaps at joins are closed by
    # extending each block by one dot-radius into the next.
    filter_coords = {}
    x_cursor = mx

    for fi, filt in enumerate(present):
        norm  = normed[filt]['n']
        err_n = normed[filt]['e']
        n     = len(norm)
        bw    = block_w[filt]

        spacing = bw / max(1, n - 1)
        r_est   = max(2, min(int(spacing * 1.1), int(height * 0.13)))
        extend  = r_est if fi < len(present) - 1 else 0

        coords = []
        for i in range(n):
            px = int(x_cursor + i / max(1, n - 1) * (bw - 1 + extend))
            py = int(centre - norm[i] * amp)
            py = max(my + 2, min(my + plot_h - 2, py))
            ep = max(0, min(int(err_n[i] * amp), int(amp * 0.15)))
            coords.append((px, py, ep))

        filter_coords[filt] = coords
        x_cursor += bw

    # --- Render ---
    img  = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img, "RGBA")

    for fi, filt in enumerate(present):
        col    = filt_col(filt)
        coords = filter_coords[filt]
        n      = len(coords)
        bw     = block_w[filt]
        col_a  = col + (235,)

        spacing = bw / max(1, n - 1)
        r = max(2, min(int(spacing * 1.1), int(height * 0.13)))

        # Error bars
        for (px, py, ep) in coords:
            if ep > 1:
                lw  = max(1, r // 2)
                cap = max(1, r // 2)
                draw.line([(px, py-ep), (px, py+ep)], fill=col_a, width=lw)
                draw.line([(px-cap, py-ep), (px+cap, py-ep)], fill=col_a, width=1)
                draw.line([(px-cap, py+ep), (px+cap, py+ep)], fill=col_a, width=1)

        # Dots
        for (px, py, _) in coords:
            draw.ellipse([px-r, py-r, px+r, py+r], fill=col_a)

    return img


if __name__ == "__main__":
    out = Path("/home/claude/ava_logo_preview.png")
    img = make_logo(width=2400, height=220, bg=(10, 22, 40))
    img.save(out)
    print(f"Saved {out}  {img.size}  ({out.stat().st_size//1024} KB)")

    out_wide = Path("/home/claude/ava_logo_wide.png")
    img_w = make_logo(width=4000, height=300, bg=(10, 22, 40))
    img_w.save(out_wide)
    print(f"Saved {out_wide}  {img_w.size}  ({out_wide.stat().st_size//1024} KB)")
