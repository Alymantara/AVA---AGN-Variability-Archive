"""Build static image assets for the AVA website (web/assets).

Produces, from files already in the repo:
  - web/assets/agn/<stem>_600.webp and <stem>_1200.webp from poster/*_poster.png
  - web/assets/img/banner.webp (+ banner_1200.webp) from poster/ava_logo_dark.png
  - web/assets/img/lco_logo_white.png  (LCO logo, white bg removed, black text -> white)
  - web/assets/img/standrews_white.png (St Andrews foundation logo, white)

Only reads the source images; safe to re-run. Skips outputs newer than inputs.

Usage:
    python tools/build_web_assets.py [--force]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
POSTER = ROOT / "poster"
WEB = ROOT / "web" / "assets"
FIG = ROOT / "docs" / "figures"
STANDREWS = FIG / "University of St Andrews - Logos" / "01-foundation-horizontal" / "02-foundation-white.png"


def _stale(src: Path, dst: Path, force: bool) -> bool:
    return force or not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime


def build_agn_thumbs(force: bool) -> int:
    out = WEB / "agn"
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in sorted(POSTER.glob("*_poster.png")):
        stem = src.name[: -len("_poster.png")]
        if stem.upper().startswith("AVA"):
            continue  # full-size posters, not AGN images
        for size, q in ((600, 78), (1200, 82)):
            dst = out / f"{stem}_{size}.webp"
            if _stale(src, dst, force):
                im = Image.open(src).convert("RGB")
                im.thumbnail((size, size), Image.LANCZOS)
                im.save(dst, "WEBP", quality=q, method=6)
                n += 1
    return n


def build_banner(force: bool) -> None:
    src = POSTER / "ava_logo_dark.png"
    for width, name in ((2400, "banner.webp"), (1200, "banner_1200.webp")):
        dst = WEB / "img" / name
        if _stale(src, dst, force):
            im = Image.open(src).convert("RGB")
            if im.width != width:
                im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
            im.save(dst, "WEBP", quality=85, method=6)


def build_lco_logo(force: bool) -> None:
    """Remove white background, keep brand colours, turn dark text white."""
    src = FIG / "lco_logo.png"
    dst = WEB / "img" / "lco_logo_white.png"
    if not _stale(src, dst, force):
        return
    a = np.asarray(Image.open(src).convert("RGBA")).astype(np.float32)
    rgb, alpha = a[..., :3], a[..., 3]
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    # White background -> transparent (alpha from distance to white).
    whiteness = mn / 255.0
    low_sat = sat < 0.15
    alpha = np.where(low_sat & (whiteness > 0.5), alpha * (1 - whiteness) * 2, alpha)
    # Dark neutral text -> white, alpha from darkness for smooth edges.
    dark = low_sat & (whiteness <= 0.5)
    rgb[dark] = 255.0
    alpha = np.where(dark, alpha * np.clip((0.5 - whiteness) * 2 + 0.0, 0, 1) ** 0.5, alpha)
    out = np.dstack([rgb, np.clip(alpha, 0, 255)]).astype(np.uint8)
    im = Image.fromarray(out, "RGBA")
    im.thumbnail((640, 640), Image.LANCZOS)
    im.save(dst, optimize=True)


def build_standrews(force: bool) -> None:
    dst = WEB / "img" / "standrews_white.png"
    if _stale(STANDREWS, dst, force):
        im = Image.open(STANDREWS).convert("RGBA")
        im.thumbnail((500, 500), Image.LANCZOS)
        im.save(dst, optimize=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="rebuild everything")
    args = ap.parse_args()
    (WEB / "img").mkdir(parents=True, exist_ok=True)
    n = build_agn_thumbs(args.force)
    build_banner(args.force)
    build_lco_logo(args.force)
    build_standrews(args.force)
    print(f"AGN thumbnails written: {n}")


if __name__ == "__main__":
    main()
