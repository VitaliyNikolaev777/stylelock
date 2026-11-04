#!/usr/bin/env python3
"""Key a flat pure-green (#00FF00) backdrop to alpha, with despill.

For models that cannot output transparency (e.g. gpt-image-2). Generate the asset on
"one flat pure green #00FF00 backdrop, no green spill, no shadow on the backdrop", or edit
an approved opaque image onto green (attach it as a `subject` reference, brief "change ONLY
the backdrop"), then key it here. Do not redraw approved art on a different model to get
alpha - the redraw drifts.

Keying uses a greenness ramp, k = g - max(r, b): at or below --lo the pixel is fully
opaque, at or above --hi fully clear, linear in between. Despill then pulls green down to
the other channels so edges do not carry a green fringe.

    python chroma_key.py in.png out.png
    python chroma_key.py in.png out.png --backdrop '#F4EFE6'   # also write an opaque copy
    python chroma_key.py outputs/*.png --suffix -keyed          # batch, writes <stem>-keyed.png

Only use this when nothing in the subject's own palette is green. Always check the result
over a checkerboard against the original: translucent effects (smoke, auras, glows) key to
olive fringes - brief them as solid opaque shapes instead.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def _pixels(im):
    """Pixel sequence on any Pillow: get_flattened_data is new, getdata goes in Pillow 14."""
    fn = getattr(im, "get_flattened_data", None)
    return fn() if fn else im.getdata()

LO, HI = 40, 120


def key(im: Image.Image, lo: int = LO, hi: int = HI) -> Image.Image:
    im = im.convert("RGB")
    out = []
    span = max(1, hi - lo)
    for r, g, b in _pixels(im):
        k = g - max(r, b)
        if k <= lo:
            a = 255
        elif k >= hi:
            a = 0
        else:
            a = round(255 * (hi - k) / span)
        if g > max(r, b):
            g = max(r, b)
        out.append((r, g, b, a))
    res = Image.new("RGBA", im.size)
    res.putdata(out)
    return res


def checker(size: tuple[int, int], cell: int = 16) -> Image.Image:
    w, h = size
    bg = Image.new("RGBA", size, (255, 255, 255, 255))
    px = bg.load()
    for y in range(h):
        for x in range(w):
            if (x // cell + y // cell) % 2:
                px[x, y] = (204, 204, 204, 255)
    return bg


def parse_hex(v: str) -> tuple[int, int, int]:
    v = v.lstrip("#")
    if len(v) != 6:
        raise argparse.ArgumentTypeError(f"expected #RRGGBB, got {v!r}")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def stats(im: Image.Image) -> str:
    h = im.getchannel("A").histogram()
    n = im.size[0] * im.size[1]
    return f"clear {100 * h[0] / n:.0f}%  opaque {100 * h[255] / n:.0f}%  partial {100 * (n - h[0] - h[255]) / n:.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path, help="in.png out.png, or many inputs with --suffix")
    ap.add_argument("--suffix", default=None, help="batch mode: write <stem><suffix>.png beside each input")
    ap.add_argument("--lo", type=int, default=LO, help=f"greenness at/below which a pixel stays opaque ({LO})")
    ap.add_argument("--hi", type=int, default=HI, help=f"greenness at/above which a pixel is clear ({HI})")
    ap.add_argument("--backdrop", type=parse_hex, default=None, help="also write <out>-opaque.png on this colour")
    ap.add_argument("--checker", action="store_true", help="also write <out>-checker.png for review")
    a = ap.parse_args()

    if a.suffix is not None:
        jobs = [(p, p.with_name(p.stem + a.suffix + ".png")) for p in a.paths]
    elif len(a.paths) == 2:
        jobs = [(a.paths[0], a.paths[1])]
    else:
        ap.error("give exactly in.png out.png, or use --suffix for several inputs")

    for src, dest in jobs:
        res = key(Image.open(src), a.lo, a.hi)
        res.save(dest)
        print(f"{dest.name}  {stats(res)}")
        if a.backdrop:
            flat = Image.new("RGBA", res.size, (*a.backdrop, 255))
            flat.alpha_composite(res)
            flat.convert("RGB").save(dest.with_name(dest.stem + "-opaque.png"))
        if a.checker:
            bg = checker(res.size)
            bg.alpha_composite(res)
            bg.convert("RGB").save(dest.with_name(dest.stem + "-checker.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
