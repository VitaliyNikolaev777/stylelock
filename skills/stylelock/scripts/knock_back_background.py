#!/usr/bin/env python3
"""Push a scene plate back so composited sprites read against it.

Scenes and objects are drawn from the same spec, at the same saturation and value range,
so a sprite dropped on a scene competes with it instead of sitting on top. Prompt wording
does not fix this - measured across a rewrite, mean saturation moved 90.4% -> 90.6%.

This applies the separation as a deterministic post-process on the BACKGROUND ONLY:
pull saturation down a set amount and lift the whole plate slightly toward white, which
widens the gap between plate and sprite in both axes at once. Objects are never touched.

    python knock_back_background.py scene.png --strength 0.25
    python knock_back_background.py scene.png --strength 0.25 --out flat.png

Strength is the fraction of saturation removed. 0.15 is subtle, 0.25 is the usual answer,
0.40 starts to look washed out and starts to fight a guide that asks for saturated colour.
"""

from __future__ import annotations

import argparse
import colorsys
from pathlib import Path

from PIL import Image


def knock_back(im: Image.Image, strength: float, lift: float) -> Image.Image:
    """Desaturate by `strength` and raise value by `lift`, both as fractions of headroom.

    Done in HSV mode with per-channel LUTs. An earlier version quantised to a 256-colour
    palette first, which dithered the gradients and speckled every smooth surface - exactly
    the "noise, halftone, grain" the style guide forbids. Never reintroduce a quantise here.
    """
    hsv = im.convert("RGB").convert("HSV")
    h, s, v = hsv.split()
    s = s.point(lambda x: round(x * (1.0 - strength)))
    v = v.point(lambda x: round(x + (255 - x) * lift))
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def mean_sat_val(im: Image.Image) -> tuple[float, float]:
    q = im.convert("RGB").quantize(colors=64, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    total = sum(c for c, _ in q.getcolors(1 << 24))
    s_acc = v_acc = 0.0
    for count, idx in q.getcolors(1 << 24):
        r, g, b = pal[idx * 3: idx * 3 + 3]
        _, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        s_acc += s * count / total
        v_acc += v * count / total
    return s_acc * 100, v_acc * 100


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--strength", type=float, default=0.25, help="fraction of saturation removed")
    ap.add_argument("--lift", type=float, default=0.08, help="fraction of value headroom added")
    ap.add_argument("--out", type=Path, default=None, help="default: overwrite in place")
    a = ap.parse_args()

    src = Image.open(a.image)
    before = mean_sat_val(src)
    dst = knock_back(src, a.strength, a.lift)
    after = mean_sat_val(dst)

    dest = a.out or a.image
    dst.save(dest)
    print(f"{dest.name}  saturation {before[0]:.1f}% -> {after[0]:.1f}%   "
          f"value {before[1]:.1f}% -> {after[1]:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
