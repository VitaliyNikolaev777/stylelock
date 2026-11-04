#!/usr/bin/env python3
"""Compose a scene from a background plate plus placed sprites.

Plates carry no people, animals or merchandise - everything that recurs is a sprite, so a
scene is assembled rather than generated. That keeps a character identical across five
scenes and lets a plate be re-rendered without disturbing anything placed on it.

    python compose_scene.py compositions/scene.json
    python compose_scene.py compositions/scene.json --out /tmp/preview.png
    python compose_scene.py compositions/scene.json --table   # Figma coordinates

Two ideas do the work:

1. SIZE COMES FROM THE CATALOGUE, NOT THE FILE. Each asset declares `height` as a fraction
   of the frame height at the near edge of the ground. A giraffe is 0.62, a tree frog 0.05.
   Sprites can then be regenerated at any resolution without touching a single placement.

2. DEPTH COMES FROM Y. The scene declares a ground ramp; anything standing further back is
   drawn smaller by the same rule, and painted in y order so nearer things overlap farther
   ones. That is what makes a flat plate read as having depth.

Anchor is bottom-centre throughout: a sprite's base sits on the point you give it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def ground_scale(scene: dict, y: float) -> float:
    """Scale multiplier for something standing at normalised depth `y`.

    `ground.far` and `ground.near` are the y values of the horizon-most and closest points
    where something can stand; `ground.far_scale` is how big it is back there.
    """
    g = scene.get("ground")
    if not g:
        return 1.0
    far, near = g["far"], g["near"]
    if near <= far:
        return 1.0
    t = (y - far) / (near - far)
    t = max(0.0, min(1.0, t))
    return g.get("far_scale", 0.55) + t * (1.0 - g.get("far_scale", 0.55))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("composition", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--table", action="store_true", help="print pixel coordinates instead of rendering")
    a = ap.parse_args()

    scene = load(a.composition)
    root = a.composition.parent
    catalogue = load(root / scene.get("catalogue", "catalogue.json"))

    plate_path = (root / scene["plate"]).resolve()
    plate = Image.open(plate_path).convert("RGBA")
    W, H = plate.size

    # painter's algorithm: things lower in frame are nearer, so they go on top
    placements = sorted(scene["place"], key=lambda p: p["y"])

    rows = []
    for p in placements:
        asset = catalogue["assets"].get(p["asset"])
        if asset is None:
            print(f"  ! unknown asset {p['asset']!r} - skipped")
            continue

        sprite = Image.open((root / asset["file"]).resolve()).convert("RGBA")
        # crop to the alpha bbox first: catalogue `height` describes the OBJECT, not the
        # file it sits in. Sprites that keep the API's 1024 canvas carry transparent
        # padding, which would otherwise both shrink the object and float it off its mark.
        bbox = sprite.getbbox()
        if bbox:
            sprite = sprite.crop(bbox)
        target_h = H * asset["height"] * ground_scale(scene, p["y"]) * p.get("scale", 1.0)
        w = max(1, round(sprite.width * target_h / sprite.height))
        h = max(1, round(target_h))
        sprite = sprite.resize((w, h), Image.Resampling.LANCZOS)
        if p.get("flip"):
            sprite = sprite.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

        x_px = round(W * p["x"] - w / 2)      # bottom-centre anchor
        y_px = round(H * p["y"] - h)
        plate.alpha_composite(sprite, (x_px, y_px))
        rows.append((p["asset"], x_px, y_px, w, h))

    if a.table:
        print(f"{'asset':<22}{'x':>7}{'y':>7}{'w':>7}{'h':>7}")
        for name, x, y, w, h in rows:
            print(f"{name:<22}{x:7d}{y:7d}{w:7d}{h:7d}")
        return 0

    dest = a.out or (root / scene.get("out", a.composition.stem + "-composed.png"))
    plate.convert("RGB").save(dest)
    print(f"{dest}  {W}x{H}  ({len(rows)} sprites placed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
