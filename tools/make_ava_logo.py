"""
AVA Logo Generator — replays the extracted datapoints from the original banner.

The file banner_datapoints.csv was produced by scanning the original
banner.png pixel-by-pixel and recording the centroid y-position and
mean colour of each foreground column.  This module replays those
coordinates at any target width × height, using the original colours
(or optionally overriding with filter_dict colours for a dark background).

Usage:
    from make_ava_logo import make_logo
    img = make_logo(width=2400, height=200, bg=(10,22,40))
    img.save("ava_logo.png")
"""

from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np
import pandas as pd

# Extracted datapoints from the original banner
DATAPOINTS = Path("/mnt/user-data/uploads/AVA/data/reference/banner_datapoints.csv")
FDICT      = Path("/mnt/user-data/uploads/AVA/data/reference/filter_dict.txt")

# Map extracted filter names → filter_dict names for colour override on dark bg
FILTER_TO_FD = {
    'W2':   'UVW2', 'M2':   'UVM2', 'UVM2': 'UVM2', 'UVW1': 'UVW1',
    'US':   'Us',   'BS':   'Bs',   'u':    'u',
    'B':    'B',    'V':    'V',    'g':    'g',
    'r':    'r',    'i':    'i',    'z':    'z',
}

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

def _load_filter_colours():
    fd = pd.read_csv(FDICT)
    out = {}
    for _, row in fd.iterrows():
        c = str(row['color']).strip()
        out[row['Filter']] = _hex_to_rgb(c) if c.startswith('#') else _named_to_rgb(c)
    return out

def make_logo(
    width:          int   = 2400,
    height:         int   = 220,
    bg:             tuple = (10, 22, 40),
    margin_x_frac:  float = 0.005,
    margin_y_frac:  float = 0.05,
    use_dict_colors: bool = True,   # True = use filter_dict colours (good on dark bg)
                                    # False = use original bitmap colours (good on white)
) -> Image.Image:
    """
    Replay the original AVA banner at any size.

    The extracted datapoints (x_norm, y_norm) are scaled to the target
    width × height.  Colours come from filter_dict.txt so they render
    correctly on a dark background (the original was white-background).

    Parameters
    ----------
    width, height : output dimensions in pixels
    bg            : RGB background colour
    use_dict_colors: if True, use filter_dict brand colours; if False,
                    use the original RGB values from the bitmap
    """
    df = pd.read_csv(DATAPOINTS)

    if use_dict_colors:
        fd_cols = _load_filter_colours()
        def get_col(row):
            fd_name = FILTER_TO_FD.get(row['filter'], row['filter'])
            return fd_cols.get(fd_name, (200, 200, 200))
    else:
        def get_col(row):
            return (int(row.r), int(row.g), int(row.b))

    mx = int(width  * margin_x_frac)
    my = int(height * margin_y_frac)
    plot_w = width  - 2 * mx
    plot_h = height - 2 * my

    img  = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img, "RGBA")

    # Dot radius: scale so it matches the original visual density
    # Original: ~1203 points across 1322px → ~1pt spacing → r≈2px
    # At target width: scale proportionally but keep minimum legible
    orig_density = 1203 / 1322   # pts per pixel in original
    target_spacing = 1.0 / orig_density * (plot_w / 1322) * (1322 / 1203)
    r = max(2, min(int(target_spacing * 0.9 * (width / 1322)), int(height * 0.09)))

    # Group by filter for colour consistency, draw in wavelength order
    filter_order = ['W2', 'M2', 'UVM2', 'UVW1', 'u', 'B', 'V', 'g', 'r', 'i', 'z']
    # Adjust r per filter: leftmost (W2) have sparser points → slightly larger dots
    for filt in filter_order:
        sub = df[df['filter'] == filt].copy()
        if len(sub) == 0:
            continue
        col   = get_col(sub.iloc[0])
        col_a = col + (230,)
        # Per-filter radius: inverse of local density
        # Radius scales with output height.
        # Original banner: 174px tall, dots ~4-5px radius → r ≈ height/38
        # Scale up slightly for dark-bg visibility.
        r_filt = max(3, int(height / 28))

        for _, row in sub.iterrows():
            px = int(mx + row.x_norm * plot_w)
            py = int(my + (1.0 - row.y_norm) * plot_h)
            px = max(mx, min(mx + plot_w - 1, px))
            py = max(my, min(my + plot_h - 1, py))
            draw.ellipse([px-r_filt, py-r_filt, px+r_filt, py+r_filt], fill=col_a)

    return img


if __name__ == "__main__":
    out = Path("/home/claude/ava_logo_preview.png")
    img = make_logo(width=2400, height=220, bg=(10, 22, 40))
    img.save(out)
    print(f"Saved {out}  {img.size}  ({out.stat().st_size//1024} KB)")

    # Also render on white to compare with original
    out_white = Path("/home/claude/ava_logo_white.png")
    img_w = make_logo(width=2400, height=220, bg=(255,255,255), use_dict_colors=False)
    img_w.save(out_white)
    print(f"Saved {out_white}  {img_w.size}  ({out_white.stat().st_size//1024} KB)")
