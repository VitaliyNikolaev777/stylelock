"""The reference library: a manifest of images decomposed by what each one demonstrates."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .config import IMAGE_SUFFIXES, project

KNOWN_ROLES = ("anchor", "palette", "texture", "composition", "subject")


class ManifestError(Exception):
    pass


@dataclass
class Reference:
    id: str
    file: str
    role: str
    tags: list[str] = field(default_factory=list)
    demonstrates: str = ""
    exclude: list[str] = field(default_factory=list)
    enabled: bool = True
    added: str = ""
    base: Path | None = field(default=None, repr=False, compare=False)

    @property
    def path(self) -> Path:
        return (self.base or project().references_dir) / self.file

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file": self.file,
            "role": self.role,
            "tags": self.tags,
            "demonstrates": self.demonstrates,
            "exclude": self.exclude,
            "enabled": self.enabled,
            "added": self.added,
        }


@dataclass
class Library:
    path: Path
    data: dict

    @staticmethod
    def load(path: Path | None = None) -> "Library":
        path = path or project().manifest_path
        if not path.exists():
            raise ManifestError(f"manifest not found: {path}")
        return Library(path=path, data=json.loads(path.read_text()))

    @property
    def root(self) -> Path:
        """The references folder - files in the manifest are relative to it."""
        return self.path.parent

    @property
    def references(self) -> list[Reference]:
        out = []
        for raw in self.data.get("images", []):
            out.append(
                Reference(
                    id=raw["id"],
                    file=raw["file"],
                    role=raw.get("role", "anchor"),
                    tags=list(raw.get("tags", [])),
                    demonstrates=raw.get("demonstrates", ""),
                    exclude=list(raw.get("exclude", [])),
                    enabled=bool(raw.get("enabled", True)),
                    added=raw.get("added", ""),
                    base=self.root,
                )
            )
        return out

    def select(
        self,
        roles: list[str] | None = None,
        tags: list[str] | None = None,
        ids: list[str] | None = None,
        limit: int | None = None,
        include_disabled: bool = False,
    ) -> list[Reference]:
        """Pick the references for one generation. `tags` is AND-matched."""
        refs = [r for r in self.references if r.enabled or include_disabled]
        if ids:
            wanted = set(ids)
            refs = [r for r in refs if r.id in wanted]
        if roles:
            refs = [r for r in refs if r.role in set(roles)]
        if tags:
            needed = set(tags)
            refs = [r for r in refs if needed.issubset(set(r.tags))]
        # anchors first, then declaration order - anchors carry the most signal
        refs.sort(key=lambda r: (r.role != "anchor",))
        return refs[:limit] if limit else refs

    def add(self, ref: Reference) -> None:
        if any(r.id == ref.id for r in self.references):
            raise ManifestError(f"reference id already exists: {ref.id}")
        self.data.setdefault("images", []).append(ref.to_dict())

    def save(self) -> None:
        self.data["updated"] = date.today().isoformat()
        self.path.write_text(json.dumps(self.data, indent=2) + "\n")

    def validate(self, anchor_limit: int = 5, tag_groups=None) -> list[str]:
        """Check the library. `tag_groups` is a list of (tags, roles) selectors taken from
        the guide's variants and types - the cap applies to what one call can send, so it is
        counted per selector, not library-wide. Plain lists of tags are accepted too and
        assumed to mean anchors."""
        tag_groups = [
            (g, ["anchor"]) if g and isinstance(g[0], str) else g for g in (tag_groups or [])
        ]
        problems: list[str] = []
        seen_ids: set[str] = set()
        anchors: list[Reference] = []

        for r in self.references:
            if r.id in seen_ids:
                problems.append(f"duplicate reference id: {r.id}")
            seen_ids.add(r.id)

            if r.role not in KNOWN_ROLES:
                problems.append(f"{r.id}: unknown role {r.role!r} (known: {', '.join(KNOWN_ROLES)})")

            if not r.enabled:
                continue

            if not r.path.exists():
                problems.append(f"{r.id}: file missing at {r.path}")
            elif r.path.suffix.lower() not in IMAGE_SUFFIXES:
                problems.append(f"{r.id}: unsupported image type {r.path.suffix}")

            if not r.demonstrates:
                problems.append(f"{r.id}: no `demonstrates` note - future you will not remember why it is here")

            if r.role == "anchor":
                anchors.append(r)
                if r.exclude:
                    problems.append(
                        f"{r.id}: anchors must be stylistically pure but declares exclude={r.exclude}. "
                        "Crop it and re-file as texture/composition, or drop it."
                    )

        if not anchors:
            problems.append("no enabled anchors - every generation will run on text alone")

        enabled = [r for r in self.references if r.enabled]
        for tags, roles in tag_groups:
            needed, wanted = set(tags), set(roles)
            in_group = [r for r in enabled if needed.issubset(set(r.tags)) and r.role in wanted]
            label = "+".join(tags) + f" [{'/'.join(roles)}]"
            if len(in_group) > anchor_limit:
                problems.append(
                    f"{len(in_group)} references matching {label} exceeds the per-call limit of "
                    f"{anchor_limit} - a big noisy reference set weakens style transfer"
                )
            if not in_group:
                problems.append(f"nothing matches {label} - that variant or type will run on text alone")

        ungrouped = [
            r for r in anchors
            if not any(set(t).issubset(set(r.tags)) for t, _ in tag_groups)
        ]
        if tag_groups and len(ungrouped) > anchor_limit:
            problems.append(
                f"{len(ungrouped)} untagged anchors exceeds the per-call limit of {anchor_limit}"
            )
        if not tag_groups and len(anchors) > anchor_limit:
            problems.append(
                f"{len(anchors)} enabled anchors exceeds the limit of {anchor_limit}. "
                "A big noisy anchor set weakens style transfer - cut to the best few."
            )

        # loose files nobody registered - `_`-prefixed dirs (e.g. _source/) are raw
        # material, deliberately outside the curated library
        registered = {r.file for r in self.references}
        for p in sorted(self.root.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            rel = p.relative_to(self.root)
            if any(part.startswith(("_", ".")) for part in rel.parts):
                continue
            if rel.as_posix() not in registered:
                problems.append(f"unregistered image on disk (invisible to the pipeline): {rel.as_posix()}")

        return problems
