#!/usr/bin/env python3
"""Remove the contact shadow an image API bakes under a transparent-background object.

The `object` type forbids cast shadows and ground planes, but this renderer draws a soft
grey pool under roughly half of them anyway. Prompt wording does not fix it - measured on
one object, adding an explicit "no contact shadow, empty alpha everywhere the object
is not" direction moved the shadow from 15,612 stray pixels to 16,001.

It matters beyond looks. Sprites are placed by `compose_scene.py`, which anchors
bottom-centre on the alpha bounding box, so a shadow pool silently pushes the object up off
its mark and shrinks it. And on a plate the pool reads as a grey smudge.

`split_character_sheet.py` already strips the API's soft *glow* at alpha <= 24. A contact
shadow is denser than that - measured at alpha 32-63 - so raising that cutoff far enough to
catch it would also eat genuine antialiased edges. This separates them by GEOMETRY instead:
true edge antialiasing touches the solid body, a shadow pool does not.

    python strip_contact_shadow.py outputs/sprite.png
    python strip_contact_shadow.py outputs/*.png --in-place
    python strip_contact_shadow.py outputs/sprite.png --report   # measure, change nothing
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

SOLID = 200      # alpha at or above this is unambiguously the object's body
SHADOW_MAX = 96  # a shadow never gets denser than this; real translucency sits above it
REACH = 2        # px of genuine antialiasing allowed to trail off the solid body


def _solid_mask(alpha: Image.Image, reach: int = REACH) -> Image.Image:
    """The body, grown by `reach` px - the region where partial alpha is legitimate edge."""
    body = alpha.point(lambda v: 255 if v >= SOLID else 0)
    return body.filter(ImageFilter.MaxFilter(2 * reach + 1))


def strip(im: Image.Image, reach: int = REACH, shadow_max: int = SHADOW_MAX) -> Image.Image:
    """Zero every faint pixel that is not within `reach` px of the object's solid body."""
    im = im.convert("RGBA")
    alpha = im.getchannel("A")
    near = _solid_mask(alpha, reach)

    faint = alpha.point(lambda v: 255 if 0 < v <= shadow_max else 0)
    doomed = ImageChops.darker(ImageChops.invert(near), faint)  # faint AND away from the body

    cleaned = alpha.copy()
    cleaned.paste(0, (0, 0), doomed)
    im.putalpha(cleaned)
    return im


def measure(im: Image.Image) -> tuple[int, int]:
    """(faint pixels detached from the body, deepest px below the silhouette)."""
    im = im.convert("RGBA")
    alpha = im.getchannel("A")
    near = _solid_mask(alpha)
    px_a, px_n = alpha.load(), near.load()
    W, H = im.size

    detached = 0
    deepest = 0
    for x in range(W):
        low = -1
        for y in range(H - 1, -1, -1):
            if px_a[x, y] >= SOLID:
                low = y
                break
        if low < 0:
            continue
        for y in range(low + 1, H):
            v = px_a[x, y]
            if 0 < v <= SHADOW_MAX and not px_n[x, y]:
                detached += 1
                deepest = max(deepest, y - low)
    return detached, deepest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--in-place", action="store_true", help="overwrite instead of writing -noshadow.png")
    ap.add_argument("--report", action="store_true", help="measure only, write nothing")
    ap.add_argument("--reach", type=int, default=REACH, help=f"px of edge antialiasing to keep (default {REACH})")
    a = ap.parse_args()

    for path in a.images:
        im = Image.open(path)
        before, deep = measure(im)
        if a.report:
            print(f"{path.name[:58]:60} {before:6d} detached faint px, {deep:4d}px below base")
            continue

        cleaned = strip(im, reach=a.reach)
        after, _ = measure(cleaned)
        dest = path if a.in_place else path.with_name(path.stem + "-noshadow.png")
        cleaned.save(dest)
        print(f"{path.name[:52]:54} {before:6d} -> {after:5d} detached px  {dest.name[:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
