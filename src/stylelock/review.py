"""The feedback loop.

A reject is only useful if it says *why*. `reject()` requires a reason tag drawn from a
fixed vocabulary, so `report()` can count them - and recurring tags tell you exactly what
to add to the guide's `avoid` list, or which anchor is sending mixed signals.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .config import project

# Fixed vocabulary: free-text reasons cannot be counted, and uncounted reasons
# never make it back into the spec.
REASONS = {
    "off-palette": "colours outside the palette, or accent over-used",
    "wrong-rendering": "shading, line weight, or texture is wrong",
    "too-detailed": "busier than the detail level allows",
    "too-simple": "under-rendered, reads as unfinished",
    "wrong-lighting": "glow, gradients, or dramatic lighting crept in",
    "bad-composition": "framing, negative space, or focal hierarchy is off",
    "off-mood": "tone is wrong even though the surface is right",
    "artifact": "anatomy, geometry, or text garbling",
    "prompt-miss": "on-style but not what was asked for",
    "content": "provider refusal, safety block, or unusable subject matter",
    "baked-ground": "a transparent-background asset came back standing on a ground slab or contact shadow",
}


class ReviewError(Exception):
    pass


def _sidecar_for(image: Path) -> Path:
    return image.with_suffix(".json")


def accept(image: Path, note: str = "") -> None:
    side = _sidecar_for(image)
    if not side.exists():
        raise ReviewError(f"no provenance sidecar for {image.name} - was it made outside the wrapper?")
    meta = json.loads(side.read_text())
    meta["status"] = "accepted"
    meta["reviewed"] = datetime.now(timezone.utc).isoformat()
    if note:
        meta["review_note"] = note
    side.write_text(json.dumps(meta, indent=2) + "\n")


def reject(image: Path, reasons: list[str], note: str = "") -> Path:
    """Move an image + sidecar into rejects/ and append an entry to the reject log."""
    proj = project()
    proj.ensure_dirs()
    unknown = [r for r in reasons if r not in REASONS]
    if unknown:
        raise ReviewError(
            f"unknown reason(s) {unknown}. Use one of: {', '.join(sorted(REASONS))}"
        )
    if not reasons:
        raise ReviewError("a reject needs at least one reason - that is the whole point of the log")

    side = _sidecar_for(image)
    meta = json.loads(side.read_text()) if side.exists() else {"image": image.name}
    meta["status"] = "rejected"
    meta["reviewed"] = datetime.now(timezone.utc).isoformat()
    meta["reject_reasons"] = reasons
    if note:
        meta["review_note"] = note

    dest = proj.rejects_dir / image.name
    shutil.move(str(image), dest)
    if side.exists():
        side.unlink()
    (proj.rejects_dir / f"{dest.stem}.json").write_text(json.dumps(meta, indent=2) + "\n")

    entry = {
        "logged": meta["reviewed"],
        "image": dest.name,
        "reasons": reasons,
        "note": note,
        "subject": meta.get("subject", ""),
        "style_version": meta.get("style_version", ""),
        "provider": meta.get("provider", ""),
        "references": [r.get("id") for r in meta.get("references", [])],
    }
    with proj.reject_log.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
    return dest


def load_log() -> list[dict]:
    log = project().reject_log
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def report(min_hits: int = 3) -> dict:
    """Aggregate the reject log into things you should actually change."""
    entries = load_log()
    reasons = Counter(r for e in entries for r in e.get("reasons", []))
    versions = Counter(e.get("style_version", "?") for e in entries)
    ref_hits = Counter(ref for e in entries for ref in e.get("references", []) if ref)

    actions = []
    for reason, count in reasons.most_common():
        if count >= min_hits:
            actions.append(
                f"{count}x {reason} ({REASONS[reason]}) - tighten the matching section of the "
                f"style guide and add an explicit line to `avoid`, then bump the version"
            )
    for ref, count in ref_hits.most_common(3):
        if count >= min_hits and count >= 0.5 * max(len(entries), 1):
            actions.append(
                f"{ref} was attached to {count}/{len(entries)} rejects - inspect it for "
                f"off-style content, or demote it out of `anchor`"
            )

    return {
        "total_rejects": len(entries),
        "by_reason": dict(reasons.most_common()),
        "by_style_version": dict(versions.most_common()),
        "by_reference": dict(ref_hits.most_common()),
        "suggested_actions": actions,
    }


def pending(out_dir: Path | None = None) -> list[Path]:
    """Generated images that have not been accepted or rejected yet."""
    out_dir = out_dir or project().outputs_dir
    result = []
    for side in sorted(out_dir.glob("*.json")):
        meta = json.loads(side.read_text())
        if meta.get("status") == "unreviewed":
            candidate = out_dir / meta.get("image", "")
            if candidate.exists():
                result.append(candidate)
    return result
