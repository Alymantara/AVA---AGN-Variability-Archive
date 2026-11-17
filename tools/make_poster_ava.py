"""
AVA Poster — Deep Space brand identity
Colours, fonts, logos and banner all from the official AVA style guide.
Run with: python3 make_poster_ava.py [a0|a1]   (default: both)
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np
import math
import pandas as pd

# ── Canvas size ───────────────────────────────────────────────────────────────
# A0: 841×1189 mm   A1: 594×841 mm   both at 150 dpi
DPI   = 150
_SIZE = sys.argv[1].lower() if len(sys.argv) > 1 else "a0"
if _SIZE == "a1":
    W, H     = int(23.39 * DPI), int(33.11 * DPI)   # 3508 × 4966
    OUT_PATH = Path("/home/claude/AVA_poster_a1.png")
else:
    W, H     = int(33.11 * DPI), int(46.81 * DPI)   # 4966 × 7021
    OUT_PATH = Path("/home/claude/AVA_poster_ava.png")

# ── AVA Brand colours ─────────────────────────────────────────────────────────
ABYSS     = (10,  22,  40)   # #0A1628  dark background
INK_BLUE  = (26,  58,  92)   # #1A3A5C  primary / borders
SKY       = (45, 106, 159)   # #2D6A9F  accent
GOLD      = (212, 160,  23)  # #D4A017  AVA wordmark / accent
GOLD_L    = (232, 190,  80)  # lighter gold for numbers
AURORA    = (58, 158, 110)   # #3A9E6E  success green
WHITE     = (255, 255, 255)
GREY      = (160, 175, 195)  # subdued text

# ── Paths ─────────────────────────────────────────────────────────────────────
IMG_DIR   = Path("/home/claude/final2")
STA_LOGO  = Path("/mnt/user-data/uploads/AVA/docs/figures/University of St Andrews - Logos/01-foundation-horizontal/02-foundation-white.png")
LCO_LOGO  = Path("/mnt/user-data/uploads/AVA/docs/figures/lco_logo.png")
BANNER    = Path("/mnt/user-data/uploads/AVA/docs/figures/banner.png")
F9_CSV    = Path("/mnt/user-data/uploads/AVA/docs/figures/F9_all_aper_v1.csv")
FDICT     = Path("/mnt/user-data/uploads/AVA/data/reference/filter_dict.txt")
# OUT_PATH set above based on _SIZE argument

# ── Font loader — Inter (AVA brand) with fallbacks ────────────────────────────
def load_font(size, bold=False, extrabold=False):
    candidates = []
    if extrabold:
        candidates += [
            "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
            "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
        ]
    elif bold:
        candidates += [
            "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
            "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",
        ]
    else:
        candidates += [
            "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
            "/usr/share/fonts/opentype/inter/Inter-Medium.otf",
        ]
    # Fallbacks
    candidates += [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for fp in candidates:
        try: return ImageFont.truetype(fp, size)
        except: pass
    return ImageFont.load_default()

def tw(draw, text, font):
    bb = draw.textbbox((0,0), text, font=font); return bb[2]-bb[0]
def th(draw, text, font):
    bb = draw.textbbox((0,0), text, font=font); return bb[3]-bb[1]

def draw_centred(draw, text, cx, y, font, fill, max_w=None):
    if max_w:
        words = text.split(); lines, cur = [], []
        for w in words:
            test = " ".join(cur+[w])
            if tw(draw,test,font) > max_w and cur:
                lines.append(" ".join(cur)); cur = [w]
            else: cur.append(w)
        if cur: lines.append(" ".join(cur))
    else:
        lines = [text]
    for ln in lines:
        w_ = tw(draw,ln,font); h_ = th(draw,ln,font)
        draw.text((cx - w_//2, y), ln, fill=fill, font=font)
        y += h_ + max(2, int(h_*0.1))
    return y

# ── Grid layout ───────────────────────────────────────────────────────────────
# 7 × 10 grid, centre hole cols 2–4, rows 2–6 (5 rows)
COLS, ROWS        = 7, 10
HOLE_C1, HOLE_C2  = 2, 5
HOLE_R1, HOLE_R2  = 2, 7

MAR_H  = int(0.010 * W)
MAR_V  = int(0.008 * H)
GAP    = int(0.004 * W)

CELL_W = (W - 2*MAR_H - (COLS-1)*GAP) // COLS
CELL_H = (H - 2*MAR_V - (ROWS-1)*GAP) // ROWS
CELL   = min(CELL_W, CELL_H)

GRID_W = COLS*CELL + (COLS-1)*GAP
GRID_H = ROWS*CELL + (ROWS-1)*GAP
GRID_X = (W - GRID_W)//2
GRID_Y = (H - GRID_H)//2

PX0 = GRID_X + HOLE_C1*(CELL+GAP)
PY0 = GRID_Y + HOLE_R1*(CELL+GAP)
PX1 = GRID_X + HOLE_C2*(CELL+GAP) - GAP
PY1 = GRID_Y + HOLE_R2*(CELL+GAP) - GAP
PW, PH = PX1-PX0, PY1-PY0

print(f"Canvas {W}×{H}  Cell {CELL}  Panel {PW}×{PH}")

# ── Image ordering ────────────────────────────────────────────────────────────
PRIORITY = [
    "NGC_4151", "NGC_4051", "3C273", "Mrk_335", "Mrk_509",
    "NGC_7469", "NGC_1365", "Mrk_817", "Mrk_279", "Mrk_876",
    "NGC_4593", "NGC_6814", "NGC_3783", "Mrk_766", "Mrk_142",
]
all_imgs = sorted(IMG_DIR.glob("*_poster.png"),
                  key=lambda p: (PRIORITY.index(p.stem.replace("_poster",""))
                                 if p.stem.replace("_poster","") in PRIORITY else 100, str(p)))

slots = []
for r in range(ROWS):
    for c in range(COLS):
        if not (HOLE_C1 <= c < HOLE_C2 and HOLE_R1 <= r < HOLE_R2):
            slots.append((GRID_X + c*(CELL+GAP), GRID_Y + r*(CELL+GAP)))

# Perimeter-first ordering
def perimeter_first(slots):
    smap = {}
    idx = 0
    for r in range(ROWS):
        for c in range(COLS):
            if not (HOLE_C1 <= c < HOLE_C2 and HOLE_R1 <= r < HOLE_R2):
                smap[(r,c)] = idx; idx += 1
    top   = [(0,c) for c in range(COLS)]
    right = [(r,COLS-1) for r in range(1,ROWS)]
    bot   = [(ROWS-1,c) for c in range(COLS-2,-1,-1)]
    left  = [(r,0) for r in range(ROWS-2,0,-1)]
    order, seen = [], set()
    for rc in top+right+bot+left:
        if rc in smap and rc not in seen:
            order.append(smap[rc]); seen.add(rc)
    for rc,si in smap.items():
        if rc not in seen: order.append(si)
    return [slots[i] for i in order]

ordered_slots = perimeter_first(slots)
print(f"Slots: {len(ordered_slots)}")

# ── Build canvas ──────────────────────────────────────────────────────────────
canvas = Image.new("RGB", (W, H), ABYSS)
draw   = ImageDraw.Draw(canvas)

# ── Paste thumbnails with re-drawn labels (Inter, sized for A0 print) ─────────
# Label font: ~35pt at A0 = CELL * 0.075 px
F_NAME = load_font(max(24, int(CELL * 0.075)), bold=True)
n = len(all_imgs)
for i, (x, y) in enumerate(ordered_slots):
    img_path = all_imgs[i % n]
    name = img_path.stem.replace("_poster", "").replace("_", " ")
    img  = Image.open(img_path).convert("RGB")
    img  = img.resize((CELL, CELL), Image.LANCZOS)

    # Overdraw the existing small label with a fresh larger one
    idraw   = ImageDraw.Draw(img)
    # Black semi-transparent strip at bottom
    strip_h = int(CELL * 0.13)
    strip_y = CELL - strip_h
    idraw.rectangle([0, strip_y, CELL-1, CELL-1], fill=(0, 0, 0, 0))
    # Actually fill with solid dark colour (RGB mode)
    idraw.rectangle([0, strip_y, CELL-1, CELL-1], fill=(10, 15, 25))

    # Centre the name in the strip
    nb   = idraw.textbbox((0,0), name, font=F_NAME)
    nw, nh = nb[2]-nb[0], nb[3]-nb[1]
    nx = (CELL - nw) // 2
    ny = strip_y + (strip_h - nh) // 2
    # Drop shadow
    idraw.text((nx+1, ny+1), name, fill=(0, 0, 0), font=F_NAME)
    # White label
    idraw.text((nx, ny), name, fill=(255, 255, 255), font=F_NAME)

    canvas.paste(img, (x, y))

# ── Thin Ink Blue lines between cells (grid seams) ───────────────────────────
# Already have ABYSS gaps between cells — no need for explicit lines

# ── Centre panel — Abyss background with radial vignette ─────────────────────
panel_arr = np.zeros((PH, PW, 3), dtype=np.uint8)
cy_p, cx_p = PH//2, PW//2
for dy in range(0, PH, 2):   # step 2 for speed
    for dx in range(0, PW, 2):
        dist = math.sqrt(((dx-cx_p)/cx_p)**2 + ((dy-cy_p)/cy_p)**2)
        v = max(0, int(18*(1-dist*0.65)))
        panel_arr[dy,dx] = panel_arr[dy,min(dx+1,PW-1)] = [v//3, v//2, v]
        panel_arr[min(dy+1,PH-1),dx] = panel_arr[min(dy+1,PH-1),min(dx+1,PW-1)] = [v//3, v//2, v]
canvas.paste(Image.fromarray(panel_arr), (PX0, PY0))

# ── Panel border — Ink Blue with Gold corners ─────────────────────────────────
BW = max(3, int(0.003*W))
draw.rectangle([PX0, PY0, PX1-1, PY1-1], outline=INK_BLUE, width=BW)
# Gold corner accents
CS = int(PW * 0.06)  # corner size
for cx_, cy_, dx, dy in [(PX0,PY0,1,1),(PX1,PY0,-1,1),(PX0,PY1,1,-1),(PX1,PY1,-1,-1)]:
    draw.line([(cx_, cy_), (cx_+dx*CS, cy_)], fill=GOLD, width=BW)
    draw.line([(cx_, cy_), (cx_, cy_+dy*CS)], fill=GOLD, width=BW)

# ── Fonts (Inter — AVA brand) ─────────────────────────────────────────────────
# All sizes chosen for A0 print at 150dpi (1px ≈ 0.48pt)
# A0 readability: title ~140pt, body ~40pt, footnote ~24pt
CX = PX0 + PW//2
F_AVA   = load_font(int(PW * 0.148), extrabold=True)  # title ~145pt ✓
F_SUB   = load_font(int(PW * 0.052), bold=False)       # subtitle ~51pt ✓
F_TAG   = load_font(int(PW * 0.038), bold=False)       # tagline ~37pt ✓
F_NUM   = load_font(int(PW * 0.090), bold=True)        # stat numbers ~88pt
F_LBL   = load_font(int(PW * 0.040), bold=False)       # stat labels ~39pt ✓
F_FOOT  = load_font(int(PW * 0.030), bold=False)       # footer ~29pt ✓
F_CPY   = load_font(int(PW * 0.022), bold=False)       # copyright ~21pt — small but legible

SP  = int(PH * 0.014)
MED = int(PH * 0.025)
LRG = int(PH * 0.038)
RW  = int(PW * 0.72)

def rule(y, color=INK_BLUE, width=RW, lw=2):
    draw.line([(CX-width//2, y), (CX+width//2, y)], fill=color, width=lw)
    return y + lw

# ── Logo bar at top of panel (Abyss strip with real logos) ───────────────────
LOGO_BAR_H = int(PH * 0.095)
LBY0 = PY0 + BW + 1
LBY1 = LBY0 + LOGO_BAR_H

# Draw Abyss bar
draw.rectangle([PX0+BW, LBY0, PX1-BW, LBY1], fill=ABYSS)
# Thin rule under logo bar (ink blue, not gold)
draw.line([(PX0+BW, LBY1), (PX1-BW, LBY1)], fill=INK_BLUE, width=1)

def _scale_and_paste(img_rgba, max_w, max_h, bg=ABYSS):
    """Scale an RGBA image to fit max_w×max_h and composite onto bg."""
    ratio = img_rgba.width / img_rgba.height
    w = min(max_w, int(max_h * ratio))
    h = int(w / ratio)
    img_rgba = img_rgba.resize((w, h), Image.LANCZOS)
    patch = Image.new("RGBA", (w, h), bg + (255,))
    patch.paste(img_rgba, (0, 0), img_rgba)
    return patch.convert("RGB"), w, h

def logo_transparent(path, max_w, max_h, bg=ABYSS):
    """Logo already on transparent bg (e.g. St Andrews white PNG) — paste as-is."""
    img = Image.open(path).convert("RGBA")
    return _scale_and_paste(img, max_w, max_h, bg)

def logo_colour_on_white(path, max_w, max_h, bg=ABYSS):
    """Colour logo on white bg (e.g. LCO): remove white, turn dark text→white,
    keep all brand colours (reds, blues, greens) exactly."""
    raw = Image.open(path).convert("RGBA")
    arr = np.array(raw, dtype=np.float32)
    r, g, b, a = arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3]

    # 1. Remove white background
    white = (r > 240) & (g > 240) & (b > 240)
    arr[white, 3] = 0

    # 2. Near-black unsaturated text → pure white
    lum = 0.299*r + 0.587*g + 0.114*b
    sat = np.max(arr[:,:,:3], axis=2) - np.min(arr[:,:,:3], axis=2)
    dark_text = (~white) & (lum < 80) & (sat < 40)
    arr[dark_text, 0] = 255
    arr[dark_text, 1] = 255
    arr[dark_text, 2] = 255

    # 3. Anti-aliased edges around text → blend toward white
    aa = (~white) & (lum < 180) & (sat < 40) & ~dark_text
    scale = 1.0 - lum[aa] / 255.0
    for ch in range(3):
        arr[aa, ch] = np.clip(arr[aa, ch] + scale * (255 - arr[aa, ch]), 0, 255)

    # 4. All coloured pixels (brand reds, blues, greens) → unchanged

    img = Image.fromarray(arr.astype(np.uint8), 'RGBA')
    return _scale_and_paste(img, max_w, max_h, bg)

logo_max_h = int(LOGO_BAR_H * 0.82)
# Each logo fits within its half minus a small inner margin from panel edge and divider
PAD = int(PW * 0.04)   # equal padding from panel border and from centre divider
half_w = PW // 2       # width of each logo zone

logo_max_w = half_w - 2 * PAD

# Left half zone: PX0+BW  →  PX0+BW+half_w
# Right half zone: PX0+BW+half_w  →  PX1-BW
left_cx  = PX0 + BW + half_w // 2        # centre of left half
right_cx = PX0 + BW + half_w + half_w // 2  # centre of right half

# St Andrews — transparent-bg white logo, paste directly
sta_rgb, sta_w, sta_h = logo_transparent(STA_LOGO, logo_max_w, logo_max_h)
sta_x = left_cx - sta_w // 2
sta_y = LBY0 + (LOGO_BAR_H - sta_h) // 2
canvas.paste(sta_rgb, (sta_x, sta_y))

# LCO — colour-on-white logo: remove white bg, text→white, colours preserved
lco_rgb, lco_w, lco_h = logo_colour_on_white(LCO_LOGO, logo_max_w, logo_max_h)
lco_x = right_cx - lco_w // 2
lco_y = LBY0 + (LOGO_BAR_H - lco_h) // 2
canvas.paste(lco_rgb, (lco_x, lco_y))

# Thin vertical divider between logos
mid_x = PX0 + BW + half_w
draw.line([(mid_x, LBY0+int(LOGO_BAR_H*0.1)), (mid_x, LBY1-int(LOGO_BAR_H*0.1))],
          fill=INK_BLUE, width=1)

# ── Fairall 9 banner — daisy-chain light curve via make_ava_logo ──────────────
import sys; sys.path.insert(0, '/home/claude')
from make_ava_logo import make_logo as _make_logo

BAN_H  = int(PH * 0.070)   # taller so the curve has room to breathe
BAN_Y0 = LBY1 + 1
BAN_W  = PX1 - PX0 - 2*BW

ban_img = _make_logo(width=BAN_W, height=BAN_H, bg=ABYSS)
canvas.paste(ban_img, (PX0+BW, BAN_Y0))

# No bounding rule — banner flows directly into the content below

# ── Main text content ─────────────────────────────────────────────────────────
y = BAN_Y0 + BAN_H + MED

# "AVA" title in Gold — large display
y = draw_centred(draw, "AGN", CX, y, F_AVA, WHITE) + SP//2
y = draw_centred(draw, "Variability", CX, y, F_AVA, WHITE) + SP//2
y = draw_centred(draw, "Archive", CX, y, F_AVA, GOLD) + MED

# Gold gradient rule (approximate with solid gold — PIL has no gradient lines)
rule(y, color=GOLD, width=int(PW*0.56), lw=2); y += 2 + MED

# Tagline
y = draw_centred(draw, "Reverberation mapping of AGN", CX, y, F_TAG, GREY,
                 max_w=int(PW*0.88)) + SP//2
y = draw_centred(draw, "with the Las Cumbres Observatory", CX, y, F_TAG, WHITE,
                 max_w=int(PW*0.88)) + LRG * 2

# ── Stats — 2×2 ───────────────────────────────────────────────────────────────
CXL = PX0 + PW//4
CXR = PX0 + 3*PW//4

def stat_row(pairs, y_s):
    """Draw a row of (number, label, cx) pairs with numbers and labels
    both baseline-aligned across the row — number tops at y_s, label
    tops all at the same y regardless of number height differences."""
    # First pass: find the tallest number to set a common label baseline
    num_bottoms = []
    for num, lbl, cx_s in pairs:
        y_after_num = draw_centred(draw, num, cx_s, y_s, F_NUM, GOLD_L)
        num_bottoms.append(y_after_num)
    lbl_y = max(num_bottoms) + SP // 2
    # Second pass: draw numbers again (PIL doesn't have a dry-run), then labels
    for num, lbl, cx_s in pairs:
        draw_centred(draw, num, cx_s, y_s, F_NUM, GOLD_L)
        draw_centred(draw, lbl, cx_s, lbl_y, F_LBL, GREY)
    # Return y after the labels
    lbl_h = max(th(draw, lbl, F_LBL) for _, lbl, _ in pairs)
    return lbl_y + lbl_h

y = stat_row([("12",    "years of data",      CXL),
              ("65",    "AGN monitored",       CXR)], y) + MED

draw.line([(PX0+int(PW*0.08), y), (PX1-int(PW*0.08), y)],
          fill=(30,50,80), width=1)
y += MED

y = stat_row([("482k+",  "photometric images", CXL),
              ("5,139+", "spectra taken",       CXR)], y) + LRG

# Footer rule
rule(y, color=(50,80,120), width=int(PW*0.70), lw=1); y += 1 + MED

# Footer text
y = draw_centred(draw, "University of St Andrews  ·  School of Physics & Astronomy",
                 CX, y, F_FOOT, GREY, max_w=int(PW*0.88)) + SP//2
draw_centred(draw, "Las Cumbres Observatory Global Telescope Network",
             CX, y, F_FOOT, GREY, max_w=int(PW*0.88))

# ── Copyright — bottom-right of panel ────────────────────────────────────────
CPY_TEXT = "© J. Hernández Santisteban  2026"
cpy_w = tw(draw, CPY_TEXT, F_CPY)
cpy_h = th(draw, CPY_TEXT, F_CPY)
cpy_x = PX1 - BW - int(PW*0.03) - cpy_w
cpy_y = PY1 - BW - int(PH*0.012) - cpy_h
draw.text((cpy_x, cpy_y), CPY_TEXT, fill=GREY, font=F_CPY)

# ── Save ──────────────────────────────────────────────────────────────────────
canvas.save(str(OUT_PATH), "PNG")
print(f"Saved {OUT_PATH}  ({OUT_PATH.stat().st_size//1024} KB)")
