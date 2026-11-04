#!/usr/bin/env python3
"""Make a full-bleed frame/overlay asset a clean surround with a crisp window.

The renderer will not reliably do two things at once: fill the canvas out to all four
borders AND leave the centre empty. Asked for both, it oscillates - sometimes it draws a
small frame floating in the middle with alpha around it, and sometimes it draws the frame
full-canvas but fades the outer band to a faint semi-transparent wash. Measured across six
generations: 0.2-0.3% faint pixels when it behaves, 3.3-8.4% when it does not, and edge
coverage swinging between 0% and 100% on the same prompt.

Rewording did not settle it (three rounds), so this settles it geometrically instead. The
picture is already correct - only its alpha is wrong. So:

  * find every opening the player sees through - the main window and any quarter lights -
    as the low-alpha regions the canvas border cannot reach;
  * make every pixel outside that opening fully opaque, which turns the faint outer wash
    back into solid structure running off all four borders;
  * make every pixel inside it fully transparent, keeping a short feathered rim so the
    window edge stays antialiased;
  * flatten the RGB under the transparent pixels, so a compositor that interpolates colour
    across the alpha edge cannot drag a dark halo into the scene behind.

The flood threshold steps down if the wash bridges the window to the canvas edge, so a leak
shrinks the opening rather than eating the whole frame.

    python solidify_frame.py outputs/frame.png
    python solidify_frame.py outputs/*.png --in-place
    python solidify_frame.py outputs/frame.png --report   # measure, change nothing
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter


def _pixels(im):
    """Pixel sequence on any Pillow: get_flattened_data is new, getdata goes in Pillow 14."""
    fn = getattr(im, "get_flattened_data", None)
    return fn() if fn else im.getdata()

THRESHOLDS = (128, 96, 64, 48, 32, 16, 8)
FEATHER = 1.2


def find_opening(alpha: Image.Image) -> tuple[set[int], int]:
    """Return every opening the player sees through, plus the cutoff that found them.

    An opening is a low-alpha region the canvas border cannot reach: the main window, and
    any quarter lights beside it. So this floods the EXTERIOR inward from the border and
    takes the low-alpha pixels it could not reach - which keeps a frame with three panes
    intact where flooding out from the centre would have found only the middle one and
    filled the other two solid.

    A wash can bridge an opening to the exterior. If the flood swallows the centre of the
    image the wash has joined them, so drop to a stricter cutoff and try again - better a
    slightly small opening than an asset with its window filled in.
    """
    w, h = alpha.size
    px = alpha.load()
    for cutoff in THRESHOLDS:
        exterior: set[int] = set()
        q = deque()
        for x in range(w):
            for y in (0, h - 1):
                if px[x, y] < cutoff and y * w + x not in exterior:
                    exterior.add(y * w + x)
                    q.append((x, y))
        for y in range(h):
            for x in (0, w - 1):
                if px[x, y] < cutoff and y * w + x not in exterior:
                    exterior.add(y * w + x)
                    q.append((x, y))
        while q:
            x, y = q.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                key = ny * w + nx
                if key in exterior or px[nx, ny] >= cutoff:
                    continue
                exterior.add(key)
                q.append((nx, ny))
        if (h // 2) * w + (w // 2) in exterior:
            continue  # the wash bridged window to border - tighten and retry
        opening = {
            y * w + x
            for y in range(h)
            for x in range(w)
            if px[x, y] < cutoff and y * w + x not in exterior
        }
        if opening:
            return opening, cutoff
    raise SystemExit("no window opening found - is the centre of this image opaque?")


def solidify(path: Path, in_place: bool, report: bool) -> None:
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    alpha = im.getchannel("A")
    hist = alpha.histogram()
    n = w * h
    faint_before = 100 * sum(hist[1:129]) / n

    opening, cutoff = find_opening(alpha)

    mask = Image.new("L", (w, h), 255)
    mp = mask.load()
    for key in opening:
        mp[key % w, key // w] = 0
    ox = [k % w for k in opening]
    oy = [k // w for k in opening]
    ow = 100 * (max(ox) - min(ox)) / w
    oh = 100 * (max(oy) - min(oy)) / h

    if report:
        edges = {
            "T": alpha.crop((0, 0, w, 3)),
            "B": alpha.crop((0, h - 3, w, h)),
            "L": alpha.crop((0, 0, 3, h)),
            "R": alpha.crop((w - 3, 0, w, h)),
        }
        cov = {
            k: 100 * sum(1 for v in _pixels(c) if v > 16) / (c.size[0] * c.size[1])
            for k, c in edges.items()
        }
        print(
            f"{path.name}: opening {ow:.0f}%x{oh:.0f}% (cutoff {cutoff}), "
            f"faint {faint_before:.1f}%, edges "
            + " ".join(f"{k}{v:.0f}%" for k, v in cov.items())
        )
        return

    new_alpha = mask.filter(ImageFilter.GaussianBlur(FEATHER))
    im.putalpha(new_alpha)

    # Kill the colour left under the hole so no compositor can bleed it inward. The rim
    # colour, not black: an interpolator that does reach past the edge then picks up the
    # frame's own tone instead of a dark fringe.
    rim = mask.filter(ImageFilter.MaxFilter(5))
    rp, mp2, px = rim.load(), mask.load(), im.load()
    samples = [
        px[x, y][:3]
        for y in range(0, h, 7)
        for x in range(0, w, 7)
        if rp[x, y] and not mp2[x, y]
    ]
    if samples:
        avg = tuple(sum(c[i] for c in samples) // len(samples) for i in range(3))
        for key in opening:
            x, y = key % w, key // w
            px[x, y] = (*avg, px[x, y][3])

    out = path if in_place else path.with_name(path.stem + "-solid.png")
    im.save(out)
    after = im.getchannel("A").histogram()
    print(
        f"{path.name} -> {out.name}  opening {ow:.0f}%x{oh:.0f}% (cutoff {cutoff})  "
        f"faint {faint_before:.1f}% -> {100 * sum(after[1:129]) / n:.1f}%"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--in-place", action="store_true")
    ap.add_argument("--report", action="store_true", help="measure only, write nothing")
    args = ap.parse_args()
    for p in args.paths:
        solidify(p, args.in_place, args.report)


if __name__ == "__main__":
    main()
