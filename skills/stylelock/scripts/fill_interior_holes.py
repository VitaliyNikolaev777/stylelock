#!/usr/bin/env python3
"""Fill transparent holes that sit INSIDE a transparent-background asset.

Image APIs asked for a transparent background will happily knock out large flat interior
fills too - a map comes back with its blocks punched through, so the sheet renders as
a lattice over whatever UI sits behind it.

This finds the genuine exterior by flooding inward from the canvas edge; every transparent
pixel the flood cannot reach is an interior hole, and gets filled with the given colour.

    python fill_interior_holes.py outputs/map.png --color '#9CC8F0'

Run it after split_character_sheet.py, which strips the low-alpha halo first -
a halo bridges the hole to the exterior and this would then correctly leave it alone.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def parse_hex(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) != 6:
        raise argparse.ArgumentTypeError(f"expected #RRGGBB, got {value!r}")
    return tuple(int(v[i: i + 2], 16) for i in (0, 2, 4))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--color", type=parse_hex, required=True, help="fill colour, #RRGGBB")
    ap.add_argument("--out", type=Path, default=None, help="default: overwrite in place")
    ap.add_argument("--threshold", type=int, default=8, help="alpha at or below this counts as a hole")
    a = ap.parse_args()

    im = Image.open(a.image).convert("RGBA")
    alpha = im.getchannel("A")

    # 1 where the pixel is transparent, 0 where it is artwork
    holes = alpha.point(lambda v: 255 if v <= a.threshold else 0).convert("L")

    # Flood from every border pixel that is transparent; what it reaches is the true exterior.
    # 128 is a scratch value - it cannot collide with the 0/255 the mask already holds.
    marker = holes.copy()
    w, h = marker.size
    px = marker.load()
    seeds = [(x, y) for x in range(w) for y in (0, h - 1)]
    seeds += [(x, y) for y in range(h) for x in (0, w - 1)]
    for seed in seeds:
        if px[seed] == 255:
            ImageDraw.floodfill(marker, seed, 128)

    # still 255 -> transparent but unreachable from outside -> an interior hole
    interior = marker.point(lambda v: 255 if v == 255 else 0)
    filled = sum(interior.histogram()[255:])
    if not filled:
        print("no interior holes found")
        return 0

    patch = Image.new("RGBA", im.size, (*a.color, 255))
    im = Image.composite(patch, im, interior)

    dest = a.out or a.image
    im.save(dest)
    pct = filled * 100 / (w * h)
    print(f"{dest}  filled {filled} px ({pct:.1f}% of canvas) with #{'%02X%02X%02X' % a.color}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
