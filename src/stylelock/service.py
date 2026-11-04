"""Operations shared by the CLI's `--json` mode and the MCP server.

Every function returns plain data (dicts, lists, strings), so the two front ends cannot drift
apart: the CLI prints it, the MCP server hands it to the model.
"""

from __future__ import annotations

import json
import shutil
import struct
from datetime import date
from importlib.resources import files
from pathlib import Path

from .config import load_dotenv, project, resolve_generation
from .generate import run
from .manifest import Library, Reference
from .prompt import assemble
from .providers import REGISTRY, describe_all
from .review import REASONS
from .review import accept as _accept
from .review import pending as _pending
from .review import reject as _reject
from .review import report as _report
from .style import StyleGuide, list_versions

DOCS = ("agent", "briefing", "guides", "post-processing", "review", "one-offs")


def read_doc(name: str) -> str:
    if name not in DOCS:
        raise ValueError(f"unknown doc {name!r} (available: {', '.join(DOCS)})")
    return (files("stylelock") / "docs" / f"{name}.md").read_text()


# -- configuration and status --------------------------------------------

def generation_config(provider: str | None = None, options: dict | None = None) -> dict:
    """Which provider and model a generate call would use right now, and why."""
    load_dotenv()
    name, opts, sources = resolve_generation(provider, options)
    model = opts.get("model")
    if not model:
        try:
            model = StyleGuide.load().provider_defaults(name).get("model")
            sources["model"] = "guide" if model else "provider default"
        except Exception:
            model = None
    if not model and name in REGISTRY:
        model = REGISTRY[name].default_model
        sources["model"] = "provider default"
    return {
        "provider": name,
        "model": model or "",
        "sources": sources,
        "capabilities": REGISTRY[name].describe() if name in REGISTRY else None,
    }


def providers() -> list[dict]:
    load_dotenv()
    return describe_all()


def status() -> dict:
    load_dotenv()
    proj = project()
    guide = StyleGuide.load(style_dir=proj.style_dir)
    problems = guide.validate()
    lib = Library.load(proj.manifest_path)
    ref_problems = lib.validate(
        anchor_limit=guide.anchor_limit, tag_groups=guide.reference_tag_groups()
    )
    anchors = lib.select(roles=["anchor"])
    gen = generation_config()

    next_steps = []
    if problems:
        next_steps.append("fix the style guide problems (`stylelock style lint`)")
    if guide.status == "draft":
        next_steps.append(
            "the guide is a draft - describe the real approved art in it, then set status to active"
        )
    if not anchors:
        next_steps.append("register 2-5 approved on-style images as anchors")
    caps = gen["capabilities"] or {}
    if gen["provider"] == "dryrun" and gen["sources"]["provider"] == "default":
        next_steps.append("no provider configured - set STYLELOCK_PROVIDER (dryrun makes placeholders)")
    elif not caps.get("key_set", True):
        next_steps.append(f"{caps.get('key_env')} is not set for provider {gen['provider']}")

    return {
        "project": str(proj.root),
        "guide": {
            "label": guide.label,
            "status": guide.status,
            "problems": problems,
            "warnings": guide.warnings(),
            "variants": sorted(guide.variants),
            "types": sorted(guide.types),
            "cast": sorted(guide.cast),
        },
        "references": {"enabled_anchors": len(anchors), "problems": ref_problems},
        "generation": gen,
        "rejects_logged": _report()["total_rejects"],
        "unreviewed": len(_pending()),
        "ok": not problems and not ref_problems,
        "next_steps": next_steps,
    }


def style_info(style_version: str | None = None) -> dict:
    guide = StyleGuide.load(style_version)
    return {
        "guide": guide.label,
        "status": guide.status,
        "subject_domain": guide.data.get("subject_domain", ""),
        "types": {k: v.get("description", "") for k, v in guide.types.items()},
        "variants": {k: v.get("description", "") for k, v in guide.variants.items()},
        "cast": {k: v.get("description", "") for k, v in guide.cast.items()},
        "hard_rules": guide.hard_rules,
        "versions": [p.name for _, p in list_versions()],
        "experiments": sorted(
            p.relative_to(project().root).as_posix()
            for p in (project().style_dir / "experiments").glob("*.json")
        ),
    }


# -- prompts and generation ----------------------------------------------

def _guide(style_version, variant, asset_type, character) -> StyleGuide:
    return (
        StyleGuide.load(style_version)
        .with_variant(variant)
        .with_type(asset_type)
        .with_character(character)
    )


def preview(
    subject: str,
    style_version: str | None = None,
    variant: str | None = None,
    asset_type: str | None = None,
    character: str | None = None,
    roles: list[str] | None = None,
    tags: list[str] | None = None,
    ref_ids: list[str] | None = None,
    extra: str = "",
) -> dict:
    guide = _guide(style_version, variant, asset_type, character)
    bundle = assemble(
        subject, guide, Library.load(), roles=roles, tags=tags, ref_ids=ref_ids, extra=extra
    )
    return {
        "prompt": bundle.prompt,
        "negative": bundle.negative,
        "references": [{"id": r.id, "role": r.role, "file": r.file} for r in bundle.references],
        "style": guide.label,
        "fingerprint": bundle.fingerprint,
        "prompt_words": len(bundle.prompt.split()),
    }


def generate(subject: str, **kwargs) -> list[dict]:
    """Thin wrapper over `generate.run` that returns a summary per image."""
    return [describe_output(p) for p in run(subject, **kwargs)]


def describe_output(image: Path) -> dict:
    image = Path(image)
    side = image.with_suffix(".json")
    meta = json.loads(side.read_text()) if side.exists() else {}
    pm = meta.get("provider_meta", {})
    out = {
        "image": str(image),
        "sidecar": str(side) if side.exists() else None,
        "status": meta.get("status", "unknown"),
        "subject": meta.get("subject", ""),
        "provider": meta.get("provider", ""),
        "model": pm.get("model", ""),
        "style_version": meta.get("style_version", ""),
        "style_file": meta.get("style_file", ""),
        "type": meta.get("asset_type", ""),
        "variant": meta.get("variant", ""),
        "character": meta.get("character", ""),
        "fingerprint": meta.get("fingerprint", ""),
        "references": [r.get("id") for r in meta.get("references", [])],
    }
    size = png_size(image)
    if size:
        out["width"], out["height"] = size
    return out


def png_size(path: Path) -> tuple[int, int] | None:
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
    except OSError:
        return None
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


# -- review --------------------------------------------------------------

def pending() -> list[dict]:
    return [describe_output(p) for p in _pending()]


def accept(image: str, note: str = "") -> dict:
    _accept(Path(image), note=note)
    return describe_output(Path(image))


def reject(image: str, reasons: list[str], note: str = "") -> dict:
    dest = _reject(Path(image), reasons=reasons, note=note)
    return {"rejected": str(image), "moved_to": str(dest), "reasons": reasons}


def reasons() -> dict:
    return dict(sorted(REASONS.items()))


def report(min_hits: int = 3) -> dict:
    return _report(min_hits=min_hits)


# -- references ----------------------------------------------------------

def references(roles: list[str] | None = None, tags: list[str] | None = None) -> list[dict]:
    lib = Library.load()
    return [
        {
            "id": r.id, "role": r.role, "file": r.file, "tags": r.tags,
            "demonstrates": r.demonstrates, "exclude": r.exclude, "enabled": r.enabled,
            "path": str(r.path),
        }
        for r in lib.select(roles=roles, tags=tags, include_disabled=True)
    ]


def validate_references() -> list[str]:
    guide = StyleGuide.load()
    return Library.load().validate(
        anchor_limit=guide.anchor_limit, tag_groups=guide.reference_tag_groups()
    )


def add_reference(
    path: str,
    role: str = "anchor",
    demonstrates: str = "",
    tags: list[str] | None = None,
    exclude: list[str] | None = None,
    ref_id: str | None = None,
    force: bool = False,
) -> dict:
    src = Path(path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"{src} not found")
    if not demonstrates:
        raise ValueError("say what the image demonstrates - future readers will not remember")
    if role == "anchor" and exclude:
        raise ValueError(
            "anchors must be stylistically pure - file a partly-right image as "
            "texture/composition/palette/subject with exclude instead"
        )
    lib = Library.load()
    dest_dir = lib.root / (role + "s" if role == "anchor" else role)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists() and not force:
        raise FileExistsError(f"{dest} exists (use force)")
    shutil.copy2(src, dest)
    ref = Reference(
        id=ref_id or dest.stem,
        file=dest.relative_to(lib.root).as_posix(),
        role=role,
        tags=tags or [],
        demonstrates=demonstrates,
        exclude=exclude or [],
        added=date.today().isoformat(),
    )
    lib.add(ref)
    lib.save()
    return {"id": ref.id, "file": ref.file, "role": ref.role}
