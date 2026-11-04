#!/usr/bin/env python3
"""Split a `--type character` model sheet into individual transparent sprites.

The sheet is generated in ONE call so the poses are identical to each other; this
script is the second half of that workflow - it cleans the low-alpha halo the image
API leaves behind and cuts the row into one PNG per pose.

    python split_character_sheet.py outputs/<sheet>.png --name hero

Nothing here talks to an image API. The sheet must already have been produced by
`stylelock generate --type character`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

# Alpha at or below this is halo, not artwork. Chosen from the measured histogram:
# real edge antialiasing lands well above it, the API's soft glow well below.
HALO_CUTOFF = 24

# A column is "empty" if no pixel in it survives the cutoff.
MIN_GAP_PX = 12       # narrower runs of empty columns are internal, not pose gaps
MIN_SPRITE_PX = 40    # discard slivers


def clean(im: Image.Image, cutoff: int = HALO_CUTOFF) -> Image.Image:
    """Zero out the sub-threshold halo, leaving genuine antialiased edges intact."""
    im = im.convert("RGBA")
    alpha = im.getchannel("A")
    alpha = alpha.point(lambda v: 0 if v <= cutoff else v)
    im.putalpha(alpha)
    return im


def column_occupancy(im: Image.Image) -> list[bool]:
    """True for each column that contains at least one non-transparent pixel."""
    alpha = im.getchannel("A")
    # collapse to a 1px-tall strip: cheaper than scanning every pixel in Python
    strip = alpha.resize((im.width, 1), Image.Resampling.BOX)
    return [v > 0 for v in strip.tobytes()]


def find_spans(occupied: list[bool]) -> list[tuple[int, int]]:
    """Contiguous occupied column ranges, merged across gaps narrower than MIN_GAP_PX."""
    spans: list[list[int]] = []
    start = None
    for x, on in enumerate(occupied):
        if on and start is None:
            start = x
        elif not on and start is not None:
            spans.append([start, x])
            start = None
    if start is not None:
        spans.append([start, len(occupied)])

    merged: list[list[int]] = []
    for span in spans:
        if merged and span[0] - merged[-1][1] < MIN_GAP_PX:
            merged[-1][1] = span[1]
        else:
            merged.append(span)

    return [(a, b) for a, b in merged if b - a >= MIN_SPRITE_PX]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sheet", type=Path)
    ap.add_argument("--name", required=True, help="character slug, e.g. hero")
    ap.add_argument("--out", type=Path, default=Path("outputs/sprites"))
    ap.add_argument("--cutoff", type=int, default=HALO_CUTOFF)
    ap.add_argument("--pad", type=int, default=8, help="transparent margin kept around each sprite")
    a = ap.parse_args()

    im = clean(Image.open(a.sheet), a.cutoff)
    spans = find_spans(column_occupancy(im))
    if not spans:
        print("no sprites found - is the background actually transparent?")
        return 1

    a.out.mkdir(parents=True, exist_ok=True)
    for i, (x0, x1) in enumerate(spans, 1):
        pose = im.crop((x0, 0, x1, im.height))
        bbox = pose.getbbox()          # trim vertically too
        if bbox:
            pose = pose.crop(bbox)
        if a.pad:
            padded = Image.new("RGBA", (pose.width + 2 * a.pad, pose.height + 2 * a.pad), (0, 0, 0, 0))
            padded.paste(pose, (a.pad, a.pad))
            pose = padded
        # a single-subject sheet (an `object` render) needs no pose suffix
        stem = a.name if len(spans) == 1 else f"{a.name}-pose-{i}"
        dest = a.out / f"{stem}.png"
        pose.save(dest)
        print(f"{dest}  {pose.width}x{pose.height}")

    print(f"\n{len(spans)} sprite(s) from {a.sheet.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
