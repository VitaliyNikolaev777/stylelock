#!/usr/bin/env python3
"""Rasterize SVG source art to PNG.

If your source art is vector, but every image API takes raster references only - so
anything used as a reference has to be rasterized first. Chrome headless is the renderer
because these files lean on CSS class selectors, clip-paths, gradients and embedded
raster textures; lighter rasterizers (resvg, librsvg) drop some of that silently.

    python rasterize.py references/_source/scenes/*.svg --out /tmp/preview --width 960
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]

SIZE_RE = re.compile(r'\bwidth="(\d+(?:\.\d+)?)"[^>]*?\bheight="(\d+(?:\.\d+)?)"')
VIEWBOX_RE = re.compile(r'viewBox="[\d.\-]+ [\d.\-]+ ([\d.]+) ([\d.]+)"')


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("no Chrome/Chromium found - install one, or rasterize the SVGs by hand")


def svg_size(path: Path) -> tuple[float, float]:
    head = path.read_text(errors="ignore")[:4000]
    m = SIZE_RE.search(head) or VIEWBOX_RE.search(head)
    if not m:
        return (1920.0, 1080.0)
    return (float(m.group(1)), float(m.group(2)))


def rasterize(src: Path, dest: Path, width: int, chrome: str, transparent: bool) -> bool:
    w, h = svg_size(src)
    out_w = width
    out_h = max(1, round(width * h / w))
    cmd = [
        chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
        f"--screenshot={dest}", f"--window-size={out_w},{out_h}",
    ]
    if transparent:
        cmd.append("--default-background-color=00000000")
    cmd.append(src.resolve().as_uri())
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if not dest.exists():
        print(f"  FAILED {src.name}: {proc.stderr.strip()[:200]}", file=sys.stderr)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("svgs", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--width", type=int, default=1024, help="output width in px; height follows the aspect ratio")
    ap.add_argument("--transparent", action="store_true", help="keep the background transparent (for icons/badges)")
    a = ap.parse_args()

    chrome = find_chrome()
    a.out.mkdir(parents=True, exist_ok=True)

    ok = 0
    for src in a.svgs:
        if src.suffix.lower() != ".svg":
            continue
        dest = a.out / f"{src.stem}.png"
        if rasterize(src, dest, a.width, chrome, a.transparent):
            ok += 1
            print(f"  {dest}")
    print(f"rasterized {ok}/{len(a.svgs)} -> {a.out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
