#!/usr/bin/env python3
"""Report the area-weighted dominant colours of an image.

Derive a guide's palette this way - measured off real art rather than picked by eye. Use it when adding a variant, or when the generator
keeps reaching for a colour the palette does not offer.

    python measure_palette.py references/anchors/<file>.png --top 12
    python measure_palette.py <file>.png --warm        # only warm hues

Transparent pixels are ignored, so it works on `object` sprites as well as scenes.
"""

from __future__ import annotations

import argparse
import colorsys
from pathlib import Path

from PIL import Image


def _pixels(im):
    """Pixel sequence on any Pillow: get_flattened_data is new, getdata goes in Pillow 14."""
    fn = getattr(im, "get_flattened_data", None)
    return fn() if fn else im.getdata()

# Quantising first stops near-identical gradient stops from each claiming their own row.
QUANTISE_COLORS = 64


def hue_deg(rgb: tuple[int, int, int]) -> float:
    r, g, b = (v / 255 for v in rgb)
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def sat_val(rgb: tuple[int, int, int]) -> tuple[float, float]:
    r, g, b = (v / 255 for v in rgb)
    _, s, v = colorsys.rgb_to_hsv(r, g, b)
    return s * 100, v * 100


def is_warm(rgb: tuple[int, int, int]) -> bool:
    """Reds through yellows - the half of the wheel a cold palette is missing."""
    h = hue_deg(rgb)
    return h <= 65 or h >= 330


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--warm", action="store_true", help="only report warm hues")
    ap.add_argument("--min-share", type=float, default=0.2, help="ignore colours below this %%")
    a = ap.parse_args()

    im = Image.open(a.image)
    if im.mode == "RGBA":
        # drop transparent pixels; compositing onto a colour would invent one
        opaque = [px[:3] for px in _pixels(im) if px[3] > 200]
        flat = Image.new("RGB", (len(opaque), 1))
        flat.putdata(opaque)
        im = flat
    else:
        im = im.convert("RGB")

    quantised = im.quantize(colors=QUANTISE_COLORS, method=Image.Quantize.MEDIANCUT)
    palette = quantised.getpalette()
    total = sum(c for c, _ in quantised.getcolors(1 << 24))

    rows = []
    for count, idx in quantised.getcolors(1 << 24):
        rgb = tuple(palette[idx * 3: idx * 3 + 3])
        share = count * 100 / total
        if share < a.min_share:
            continue
        if a.warm and not is_warm(rgb):
            continue
        rows.append((share, rgb))

    rows.sort(reverse=True)
    print(f"{a.image.name}  ({'warm only' if a.warm else 'all hues'})\n")
    print(f"{'share':>7}  {'hex':<9} {'hue':>5} {'sat':>5} {'val':>5}")
    for share, rgb in rows[: a.top]:
        s, v = sat_val(rgb)
        print(f"{share:6.2f}%  #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}  {hue_deg(rgb):5.0f} {s:5.0f} {v:5.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
