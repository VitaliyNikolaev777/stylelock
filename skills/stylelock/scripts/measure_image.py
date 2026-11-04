#!/usr/bin/env python3
"""Measure an image before rerolling it. PIL only - no numpy needed.

Soft complaints ("too cartoonish", "messy", "looks pasted on", "is it bluer now?") usually
have a number behind them, and in practice the number has disproved the obvious fix more
often than it confirmed it. Measure first; compare against an image that was ACCEPTED, not
against the guide's prose.

Metrics, per image:
  grain     mean |img - GaussianBlur(img, 1.2)| on L. Real gradients survive the blur, grain
            does not. Typical: scene plates ~2.5-5.5, sprites ~2.3-3.0.
  flat      fraction of pixels whose 5x5 local range is <= 2 (unshaded fills).
  modelled  fraction whose 5x5 local range is >= 12 (strongly shaded/textured).
  sat, val  mean HSV saturation and value. On RGBA only pixels with alpha > 200 count,
            so a sprite is measured on the object, not its transparent canvas.
  hue_conc  circular concentration of hue over saturated pixels: 1.00 = monochrome.
  warm/cool share of saturated pixels in the warm band (hue 20-70) vs cool (180-260).
  edge      max alpha in the outer 6px on each side (RGBA only): >0 means something
            touches the frame edge.

    python measure_image.py a.png b.png accepted.png
    python measure_image.py outputs/*.png --csv > metrics.csv

Trust the number on tone and texture. Trust your eye (and a mock-up in context) on
geometry - perspective, shape and layout detectors fail confidently.
"""

from __future__ import annotations

import argparse
import colorsys
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter


def _pixels(im):
    """Pixel sequence on any Pillow: get_flattened_data is new, getdata goes in Pillow 14."""
    fn = getattr(im, "get_flattened_data", None)
    return fn() if fn else im.getdata()

SAT_MIN = 0.25  # pixels below this saturation do not vote on hue


def measure(path: Path) -> dict:
    im = Image.open(path)
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    rgba = im.convert("RGBA")
    alpha = rgba.getchannel("A")
    mask = alpha.point(lambda v: 255 if v > 200 else 0) if has_alpha else None

    lum = rgba.convert("L")
    diff = ImageChops.difference(lum, lum.filter(ImageFilter.GaussianBlur(1.2)))
    rng = ImageChops.subtract(lum.filter(ImageFilter.MaxFilter(5)), lum.filter(ImageFilter.MinFilter(5)))

    dpx, rpx = list(_pixels(diff)), list(_pixels(rng))
    mpx = list(_pixels(mask)) if mask else None
    idx = [i for i in range(len(dpx)) if mpx is None or mpx[i]]
    n = max(1, len(idx))
    grain = sum(dpx[i] for i in idx) / n
    flat = sum(1 for i in idx if rpx[i] <= 2) / n
    modelled = sum(1 for i in idx if rpx[i] >= 12) / n

    small = rgba.copy()
    small.thumbnail((256, 256))
    s_acc = v_acc = 0.0
    cnt = sat_cnt = warm = cool = 0
    cx = cy = 0.0
    for r, g, b, a in _pixels(small):
        if has_alpha and a <= 200:
            continue
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        s_acc += s
        v_acc += v
        cnt += 1
        if s >= SAT_MIN:
            sat_cnt += 1
            deg = h * 360
            cx += math.cos(h * 2 * math.pi)
            cy += math.sin(h * 2 * math.pi)
            if 20 <= deg <= 70:
                warm += 1
            elif 180 <= deg <= 260:
                cool += 1
    cnt = max(1, cnt)
    out = {
        "image": path.name,
        "grain": round(grain, 2),
        "flat": round(flat, 3),
        "modelled": round(modelled, 3),
        "sat": round(s_acc / cnt, 3),
        "val": round(v_acc / cnt, 3),
        "hue_conc": round(math.hypot(cx, cy) / sat_cnt, 2) if sat_cnt else 0.0,
        "warm": round(warm / sat_cnt, 3) if sat_cnt else 0.0,
        "cool": round(cool / sat_cnt, 3) if sat_cnt else 0.0,
    }
    if has_alpha:
        W, H = alpha.size
        edges = [alpha.crop(b).getextrema()[1] for b in
                 ((0, 0, 6, H), (W - 6, 0, W, H), (0, 0, W, 6), (0, H - 6, W, H))]
        out["edge"] = max(edges)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--csv", action="store_true")
    a = ap.parse_args()

    rows = [measure(p) for p in a.images]
    keys = ["image", "grain", "flat", "modelled", "sat", "val", "hue_conc", "warm", "cool", "edge"]
    if a.csv:
        print(",".join(keys))
        for r in rows:
            print(",".join(str(r.get(k, "")) for k in keys))
        return 0
    print(f"{'image':<40}" + "".join(f"{k:>9}" for k in keys[1:]))
    for r in rows:
        print(f"{r['image'][:39]:<40}" + "".join(f"{str(r.get(k, '-')):>9}" for k in keys[1:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
