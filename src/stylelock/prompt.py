"""Assemble the final request: subject + style block + reference set.

Nothing else in the project builds a prompt. If you find yourself concatenating
strings somewhere else, that is the bug.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .manifest import Library, Reference
from .style import StyleGuide


@dataclass
class PromptBundle:
    prompt: str
    negative: list[str]
    references: list[Reference] = field(default_factory=list)
    style_version: str = ""
    style_file: str = ""
    variant: str = ""
    asset_type: str = ""
    character: str = ""

    @property
    def fingerprint(self) -> str:
        """Stable hash of everything that determines the output, minus provider randomness."""
        payload = "\n".join(
            [self.prompt, "|".join(self.negative), "|".join(r.id for r in self.references)]
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:12]

    def to_meta(self) -> dict:
        return {
            "prompt": self.prompt,
            "negative": self.negative,
            "references": [{"id": r.id, "file": r.file, "role": r.role} for r in self.references],
            "style_version": self.style_version,
            "style_file": self.style_file,
            "variant": self.variant,
            "asset_type": self.asset_type,
            "character": self.character,
            "fingerprint": self.fingerprint,
        }


def assemble(
    subject: str,
    guide: StyleGuide,
    library: Library | None = None,
    roles: list[str] | None = None,
    tags: list[str] | None = None,
    ref_ids: list[str] | None = None,
    extra: str = "",
    ref_limit: int | None = None,
) -> PromptBundle:
    """Build the one true prompt for `subject` under `guide`."""
    subject = subject.strip()
    if not subject:
        raise ValueError("subject is empty")

    p = guide.data.get("prompt", {})
    template = p.get("template", "{subject}\n\n{style_block}")
    body = template.format(subject=subject, style_block=guide.style_block())

    chunks = [p.get("prefix", "").strip(), body.strip(), extra.strip(), p.get("suffix", "").strip()]

    references: list[Reference] = []
    if library is not None:
        wanted_roles = roles if roles is not None else guide.reference_roles
        limit = ref_limit
        if limit is None and wanted_roles == ["anchor"]:
            limit = guide.anchor_limit
        # a variant scopes the reference set too - forest anchors for a forest scene
        wanted_tags = tags if tags is not None else guide.variant_reference_tags or None
        references = library.select(roles=wanted_roles, tags=wanted_tags, ids=ref_ids, limit=limit)
        note = _reference_note(references)
        if note:
            chunks.append(note)

    prompt = "\n\n".join(c for c in chunks if c)
    return PromptBundle(
        prompt=prompt,
        negative=guide.negative_terms,
        references=references,
        style_version=guide.version,
        style_file=guide.path.name,
        variant=guide.variant,
        asset_type=guide.asset_type,
        character=guide.character,
    )


def _reference_note(references: list[Reference]) -> str:
    """Tell the model what each attached image is for - and what to ignore in it."""
    if not references:
        return ""
    lines = ["Reference images attached:"]
    for i, r in enumerate(references, 1):
        what = r.demonstrates or f"{r.role} reference"
        line = f"{i}. {what}"
        if r.role != "anchor":
            line += f" - match its {r.role} only"
        if r.exclude:
            line += f"; ignore its {', '.join(r.exclude)}"
        lines.append(line)
    return "\n".join(lines)
