"""The wrapper. Every image in this project is created through `run()` - that is what
stops anyone from calling a model raw and shipping something off-style.

It does three things nothing else does:
  1. loads the versioned style guide and injects the rendered style block,
  2. attaches the curated anchor references,
  3. writes a provenance sidecar next to every image so a bad output can be traced
     back to the exact spec version, prompt, and reference set that produced it.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import load_dotenv, project, resolve_generation
from .manifest import Library
from .prompt import PromptBundle, assemble
from .providers import get_provider
from .style import StyleGuide


class DraftGuideError(Exception):
    pass


def run(
    subject: str,
    provider: str | None = None,
    style_version: str | None = None,
    variant: str | None = None,
    asset_type: str | None = None,
    character: str | None = None,
    roles: list[str] | None = None,
    tags: list[str] | None = None,
    ref_ids: list[str] | None = None,
    extra: str = "",
    n: int = 1,
    allow_draft: bool = False,
    out_dir: Path | None = None,
    provider_options: dict | None = None,
) -> list[Path]:
    """Generate `n` images for `subject` and return the paths written.

    `provider` defaults to STYLELOCK_PROVIDER, then `dryrun`; the model to STYLELOCK_MODEL
    (for that provider), then the guide's provider_defaults."""
    load_dotenv()
    provider, provider_options, _ = resolve_generation(provider, provider_options)
    proj = project()
    proj.ensure_dirs()

    guide = StyleGuide.load(style_version, style_dir=proj.style_dir)
    problems = guide.validate()
    if problems:
        raise ValueError(
            "style guide is invalid:\n  - " + "\n  - ".join(problems) + "\nRun `stylelock style lint`."
        )
    if guide.status == "draft" and not allow_draft:
        raise DraftGuideError(
            f"{guide.label} is still status=draft. Fill in the real values (or pass "
            "allow_draft / --allow-draft to generate against placeholders anyway)."
        )
    if guide.status == "deprecated":
        print(f"warning: {guide.label} is deprecated")

    # variant first, then type: the kind of asset constrains format more than the world does.
    # character last - it is the most specific thing a brief can name.
    guide = guide.with_variant(variant).with_type(asset_type).with_character(character)
    library = Library.load(proj.manifest_path)
    bundle = assemble(
        subject=subject,
        guide=guide,
        library=library,
        roles=roles,
        tags=tags,
        ref_ids=ref_ids,
        extra=extra,
    )

    options = guide.provider_defaults(provider)
    options.update(provider_options)
    impl = get_provider(provider, **options)

    if bundle.references and not impl.supports_reference_images:
        print(
            f"note: {provider} takes no reference images on this endpoint - "
            f"{len(bundle.references)} reference(s) described in text only"
        )

    images = impl.generate(bundle, n=n)
    return _write(images, bundle, subject, provider, out_dir or proj.outputs_dir)


def _write(images, bundle: PromptBundle, subject: str, provider: str, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    slug = _slug(subject)
    paths: list[Path] = []

    prefix = "".join(f"{p}-" for p in (bundle.asset_type, bundle.variant) if p)
    for i, img in enumerate(images):
        stem = f"{stamp}-{prefix}{slug}-{bundle.fingerprint}-{i}"
        image_path = out_dir / f"{stem}{img.suffix}"
        image_path.write_bytes(img.data)

        sidecar = {
            "created": datetime.now(timezone.utc).isoformat(),
            "image": image_path.name,
            "subject": subject,
            "provider": provider,
            "provider_meta": img.provider_meta,
            "status": "unreviewed",
            **bundle.to_meta(),
        }
        (out_dir / f"{stem}.json").write_text(json.dumps(sidecar, indent=2) + "\n")
        paths.append(image_path)

    return paths


def _slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:limit].rstrip("-") or "untitled"
