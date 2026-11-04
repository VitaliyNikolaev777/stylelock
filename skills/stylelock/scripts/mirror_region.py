#!/usr/bin/env python3
"""Mirror a rectangular region of an image horizontally, in place or to a copy.

For fixing a directional element in an otherwise-good plate without regenerating it. A signpost
whose arrows point the wrong way is a one-pixel-accurate problem, and re-rolling the whole scene
to fix it throws away everything that was already right - the same reasoning behind
knock_back_background.py and strip_contact_shadow.py doing deterministic post-processes.

Pass --centre to mirror about a specific x (rather than the region's own middle). Choosing the
centre of a vertical element - a signpost's post, a door's hinge line - maps that element onto
itself, so only the asymmetric parts either side of it swap over.

    python mirror_region.py plate.png --box 1205,391,1411,437 --centre 1308
    python mirror_region.py plate.png --box ... --centre ... --in-place

Check what will move before committing: --preview writes a side-by-side instead of editing.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def mirror(im: Image.Image, box: tuple[int, int, int, int], centre: int | None) -> Image.Image:
    x0, y0, x1, y1 = box
    if centre is not None:
        # widen the box to be symmetric about `centre`, so the axis element maps onto itself
        half = max(centre - x0, x1 - centre)
        x0, x1 = centre - half, centre + half
        if x0 < 0 or x1 > im.width:
            raise SystemExit(f"symmetric box {x0}..{x1} falls outside the image (width {im.width})")
    region = im.crop((x0, y0, x1, y1)).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    out = im.copy()
    out.paste(region, (x0, y0))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", type=Path)
    ap.add_argument("--box", required=True, help="x0,y0,x1,y1 of the region to mirror")
    ap.add_argument("--centre", type=int, default=None, help="x to mirror about (default: box middle)")
    ap.add_argument("--in-place", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--preview", type=Path, default=None, help="write a before/after crop, change nothing")
    a = ap.parse_args()

    box = tuple(int(v) for v in a.box.split(","))
    if len(box) != 4:
        raise SystemExit("--box needs exactly x0,y0,x1,y1")
    im = Image.open(a.image)
    out = mirror(im, box, a.centre)

    if a.preview:
        x0, y0, x1, y1 = box
        pad = 40
        crop = (max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad))
        before, after = im.crop(crop), out.crop(crop)
        sheet = Image.new("RGB", (before.width * 2 + 12, before.height), (255, 255, 255))
        sheet.paste(before.convert("RGB"), (0, 0))
        sheet.paste(after.convert("RGB"), (before.width + 12, 0))
        sheet.resize((sheet.width * 2, sheet.height * 2), Image.LANCZOS).save(a.preview)
        print(f"{a.preview}  (left = before, right = after)")
        return 0

    dest = a.image if a.in_place else (a.out or a.image.with_name(a.image.stem + "-mirrored.png"))
    out.save(dest)
    print(f"{dest}  mirrored {box} about x={a.centre if a.centre is not None else 'box middle'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
