"""Load a versioned style guide and render it into deterministic prompt text.

The rendered style block is the whole point of the file: it turns a structured spec
into the exact same sentence every time, so two runs a month apart differ only by
subject and provider - never by phrasing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .config import project

VERSION_RE = re.compile(r"^style-guide-v(\d+)\.json$")
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Keys of a cast entry that render into the prompt, in this order. `description` is the
# human-facing one-liner for `stylelock style cast`; `append` is handled like an overlay's.
_CAST_RENDERED = ("appearance", "silhouette", "notes")


class StyleError(Exception):
    pass


@dataclass(frozen=True)
class StyleGuide:
    path: Path
    data: dict
    variant: str = ""
    asset_type: str = ""
    character: str = ""

    # -- loading ---------------------------------------------------------

    @staticmethod
    def load(version: str | int | None = None, style_dir: Path | None = None) -> "StyleGuide":
        """Load a guide. `version` may be 1, "1", "v1", a filename, or None for latest."""
        style_dir = style_dir or project().style_dir
        if version is None:
            path = StyleGuide._latest_path(style_dir)
        else:
            token = str(version).lstrip("vV")
            path = Path(version) if str(version).endswith(".json") else style_dir / f"style-guide-v{token}.json"
        if not path.exists():
            raise StyleError(f"style guide not found: {path}")
        return StyleGuide(path=path, data=json.loads(path.read_text()))

    @staticmethod
    def _latest_path(style_dir: Path) -> Path:
        candidates = []
        for p in style_dir.glob("style-guide-v*.json"):
            m = VERSION_RE.match(p.name)
            if m:
                candidates.append((int(m.group(1)), p))
        if not candidates:
            raise StyleError(f"no style-guide-v*.json in {style_dir}")
        return max(candidates)[1]

    # -- accessors -------------------------------------------------------

    @property
    def version(self) -> str:
        return str(self.data.get("version", "0.0.0"))

    @property
    def status(self) -> str:
        return str(self.data.get("status", "draft"))

    @property
    def label(self) -> str:
        bits = "".join(
            f" {k}={v}"
            for k, v in (
                ("type", self.asset_type),
                ("variant", self.variant),
                ("character", self.character),
            )
            if v
        )
        return f"{self.data.get('id', 'style')}@{self.version} ({self.path.name}){bits}"

    # -- overlays: variants (which world) and types (which kind of asset) ---
    #
    # Two orthogonal dimensions. A variant answers "which world" - say forest, city, night.
    # A type answers "what am I making" - a scene, an object, an icon - and that changes
    # format, composition, and sometimes the rendering rules themselves (icons can
    # legitimately use outlines the scenes forbid).
    #
    # Application order is variant, then type: type wins on conflict, because the kind of
    # asset constrains the format more strongly than the world does.

    @property
    def variants(self) -> dict:
        return dict(self.data.get("variants", {}))

    @property
    def types(self) -> dict:
        return dict(self.data.get("types", {}))

    def with_variant(self, name: str | None) -> "StyleGuide":
        return self._overlay("variants", name, variant=name or self.variant)

    def with_type(self, name: str | None) -> "StyleGuide":
        return self._overlay("types", name, asset_type=name or self.asset_type)

    # -- cast: which named character (a third, independent dimension) -------
    #
    # Variant and type are overlays - they replace sections of the spec. A cast member is
    # not that: it adds one locked description of a recurring character, and only when the
    # brief actually calls for them. Selecting one character must not drag the rest of the
    # cast into a prompt for an empty room, which is exactly what would happen if the cast
    # lived in `characters` (that section renders every key it holds).
    #
    # Applied after variant and type, since a character is the most specific thing in a brief.

    @property
    def cast(self) -> dict:
        return dict(self.data.get("cast", {}))

    def with_character(self, name: str | None) -> "StyleGuide":
        """Lock one named cast member into the spec. `append` works as it does on overlays."""
        if not name:
            return self
        available = self.data.get("cast", {})
        if name not in available:
            raise StyleError(
                f"unknown character {name!r} (available: {', '.join(sorted(available)) or 'none'})"
            )
        merged = json.loads(json.dumps(self.data))
        entry = available[name]
        if entry.get("append"):
            merged.setdefault("prompt", {})
            suffix = merged["prompt"].get("suffix", "")
            merged["prompt"]["suffix"] = (suffix + "\n" + entry["append"]).strip()

        return StyleGuide(
            path=self.path,
            data=merged,
            variant=self.variant,
            asset_type=self.asset_type,
            character=name,
        )

    def _overlay(self, section: str, name: str | None, **stamp) -> "StyleGuide":
        """Apply one named overlay. Sections are replaced wholesale - a merged palette is
        not a palette - except provider_defaults, which merges per provider so an overlay
        can set a size without also having to restate the model name."""
        if not name:
            return self
        available = self.data.get(section, {})
        if name not in available:
            kind = section.rstrip("s")
            raise StyleError(
                f"unknown {kind} {name!r} (available: {', '.join(sorted(available)) or 'none'})"
            )
        merged = json.loads(json.dumps(self.data))
        overrides = available[name]

        for key, value in overrides.items():
            if key in {"description", "reference_tags", "append"}:
                continue
            if key == "negative":
                merged.setdefault("prompt", {})["negative"] = list(value)
                continue
            if key == "provider_defaults":
                for provider, opts in value.items():
                    merged.setdefault("provider_defaults", {}).setdefault(provider, {}).update(opts)
                continue
            merged[key] = value

        if overrides.get("append"):
            merged.setdefault("prompt", {})
            suffix = merged["prompt"].get("suffix", "")
            merged["prompt"]["suffix"] = (suffix + "\n" + overrides["append"]).strip()

        return StyleGuide(
            path=self.path,
            data=merged,
            variant=stamp.get("variant", self.variant) or "",
            asset_type=stamp.get("asset_type", self.asset_type) or "",
            character=self.character,
        )

    @property
    def variant_reference_tags(self) -> list[str]:
        """Tags used to scope the reference set. A type's tags win over a variant's - an
        icon reference set is not world-specific, so forest+icon would match nothing."""
        type_tags = list(self.types.get(self.asset_type, {}).get("reference_tags", []))
        if type_tags:
            return type_tags
        return list(self.variants.get(self.variant, {}).get("reference_tags", []))

    @property
    def reference_roles(self) -> list[str]:
        """Which roles an overlay pulls references from. A type can read `composition`
        instead of anchors - e.g. when its only reference carries baked-in text and so
        cannot be an anchor."""
        for spec in (self.types.get(self.asset_type, {}), self.variants.get(self.variant, {})):
            roles = spec.get("reference_roles")
            if roles:
                return list(roles)
        return list(self.data.get("references", {}).get("default_roles", ["anchor"]))

    @property
    def hard_rules(self) -> list[str]:
        """Rules that render on every prompt regardless of section order, and that no
        overlay may touch - `hard_rules` is not an allowed overlay key. This is where an
        absolute constraint lives, so a type cannot quietly relax it."""
        return list(self.data.get("hard_rules", []))

    @property
    def negative_terms(self) -> list[str]:
        return list(self.data.get("prompt", {}).get("negative", []))

    @property
    def anchor_limit(self) -> int:
        return int(self.data.get("references", {}).get("anchor_limit", 5))

    def provider_defaults(self, provider: str) -> dict:
        return dict(self.data.get("provider_defaults", {}).get(provider, {}))

    def reference_tag_groups(self) -> list[tuple[list[str], list[str]]]:
        """Every (tags, roles) selector some variant or type will ask the library for.
        Roles matter: a type that reads `composition` would report a phantom problem if it
        were checked for anchors."""
        default_roles = list(self.data.get("references", {}).get("default_roles", ["anchor"]))
        groups = []
        for section in ("variants", "types"):
            for spec in self.data.get(section, {}).values():
                tags = spec.get("reference_tags")
                if tags:
                    groups.append((list(tags), list(spec.get("reference_roles") or default_roles)))
        return groups

    # -- validation ------------------------------------------------------

    def validate(self) -> list[str]:
        """Return a list of problems. Empty list means the guide is well-formed."""
        problems: list[str] = []
        d = self.data

        for key in ("id", "version", "status", "palette", "rendering", "avoid", "prompt"):
            if key not in d:
                problems.append(f"missing required key: {key}")

        if not re.match(r"^\d+\.\d+\.\d+$", str(d.get("version", ""))):
            problems.append(f"version must be semver, got {d.get('version')!r}")

        if d.get("status") not in {"draft", "active", "deprecated"}:
            problems.append(f"status must be draft|active|deprecated, got {d.get('status')!r}")

        problems += _check_palette(d.get("palette", {}), "palette")

        allowed_overlay_keys = {
            "description", "reference_tags", "append", "palette", "lighting",
            "camera", "composition", "mood", "rendering", "avoid", "subject_domain",
            "provider_defaults", "negative", "reference_roles", "characters",
        }
        for section in ("variants", "types"):
            for name, overlay in d.get(section, {}).items():
                if "palette" in overlay:
                    problems += _check_palette(overlay["palette"], f"{section}.{name}.palette")
                unknown = set(overlay) - allowed_overlay_keys
                if unknown:
                    problems.append(f"{section}.{name}: unknown key(s) {sorted(unknown)}")
                if not overlay.get("description"):
                    problems.append(f"{section}.{name}: no description")

        if not d.get("avoid"):
            problems.append("avoid list is empty - it is the cheapest quality lever you have")

        template = d.get("prompt", {}).get("template", "")
        if "{subject}" not in template:
            problems.append("prompt.template must contain {subject}")
        if "{style_block}" not in template:
            problems.append("prompt.template must contain {style_block}")

        known_sections = {
            "medium", "rendering", "palette", "lighting",
            "camera", "composition", "characters", "cast", "mood", "avoid",
        }
        for section in d.get("prompt", {}).get("style_block_order", []):
            if section not in known_sections:
                problems.append(f"unknown section in style_block_order: {section!r}")

        if not d.get("hard_rules"):
            problems.append("hard_rules is empty - absolute constraints belong there, not in `avoid`")
        for section in ("variants", "types"):
            for name, overlay in d.get(section, {}).items():
                if "hard_rules" in overlay:
                    problems.append(
                        f"{section}.{name}: hard_rules cannot be overridden - that is the point of it"
                    )

        # A cast entry is a locked description, not an overlay: it may not restyle the world.
        allowed_cast_keys = {"description", "appearance", "silhouette", "notes", "append"}
        for name, entry in d.get("cast", {}).items():
            if not entry.get("description"):
                problems.append(f"cast.{name}: no description")
            if not entry.get("appearance"):
                problems.append(
                    f"cast.{name}: no appearance - a cast entry that pins nothing down is worse "
                    "than none, because it reads as if the character were specified"
                )
            unknown = set(entry) - allowed_cast_keys
            if unknown:
                problems.append(f"cast.{name}: unknown key(s) {sorted(unknown)}")

        if d.get("cast") and "cast" not in d.get("prompt", {}).get("style_block_order", []):
            problems.append(
                "cast is defined but 'cast' is missing from prompt.style_block_order - "
                "the descriptions would never render"
            )

        return problems

    def warnings(self) -> list[str]:
        """Advice, not errors: lint prints these but generation is not blocked by them."""
        out: list[str] = []
        if not any(re.search(r"text|letter", r, re.I) for r in self.data.get("hard_rules", [])):
            out.append(
                "no hard rule about text - image models garble lettering; unless this style "
                "really wants text in the picture, add a no-text rule to hard_rules so no "
                "overlay can weaken it"
            )
        if not self.data.get("references") and self.status == "active":
            out.append("no `references` section - anchors default to role=anchor, limit 5")
        return out

    # -- rendering -------------------------------------------------------

    def style_block(self) -> str:
        """Render the structured spec into the text injected into every prompt."""
        d = self.data
        order = d.get("prompt", {}).get("style_block_order") or [
            "medium", "rendering", "palette", "lighting",
            "camera", "composition", "mood", "avoid",
        ]
        parts = [p for p in (self._section(name) for name in order) if p]
        if self.hard_rules:
            parts.append(
                "Absolute rules, these override everything above: " + _sentences(self.hard_rules) + "."
            )
        return "\n".join(parts)

    def _section(self, name: str) -> str:
        d = self.data
        if name == "medium":
            medium = d.get("rendering", {}).get("medium")
            return f"Medium: {medium}." if medium else ""

        if name == "rendering":
            r = {k: v for k, v in d.get("rendering", {}).items() if k != "medium"}
            return "Rendering: " + _clauses(r) if r else ""

        if name == "palette":
            p = d.get("palette", {})
            swatches = ", ".join(
                f"{c['name']} {c['hex']}" + (f" ({c['role']})" if c.get("role") else "")
                for c in p.get("colors", [])
            )
            out = f"Palette ({p.get('description', 'fixed palette')}): {swatches}."
            if p.get("rules"):
                out += " Colour rules: " + _sentences(p["rules"]) + "."
            return out

        if name == "lighting":
            lig = d.get("lighting", {})
            if not lig:
                return ""
            body = _clauses({k: v for k, v in lig.items() if k != "avoid"})
            out = f"Lighting: {body}"
            if lig.get("avoid"):
                out += f" No {lig['avoid']}."
            return out

        if name == "camera":
            cam = d.get("camera", {})
            return "Camera: " + _clauses(cam) if cam else ""

        if name == "composition":
            comp = d.get("composition", {})
            return "Composition: " + _clauses(comp) if comp else ""

        if name == "characters":
            ch = d.get("characters", {})
            if not ch:
                return ""
            out = "Characters: " + _clauses({k: v for k, v in ch.items() if k != "animals"})
            if ch.get("animals"):
                out += f" Animals: {ch['animals'].rstrip('.')}."
            return out

        if name == "cast":
            # only the selected character renders - the rest of the cast is not in this brief
            entry = d.get("cast", {}).get(self.character)
            if not entry:
                return ""
            body = _clauses({k: entry[k] for k in _CAST_RENDERED if entry.get(k)})
            return f"{self.character.title()}: {body}" if body else ""

        if name == "mood":
            mood = d.get("mood", {})
            if not mood:
                return ""
            out = ""
            if mood.get("adjectives"):
                out += "Mood: " + ", ".join(mood["adjectives"]) + "."
            if mood.get("avoid_adjectives"):
                out += " Not " + ", ".join(mood["avoid_adjectives"]) + "."
            return out.strip()

        if name == "avoid":
            items = d.get("avoid", [])
            return "Do not include: " + _sentences(items) + "." if items else ""

        return ""


def _check_palette(palette: dict, where: str) -> list[str]:
    problems: list[str] = []
    colors = palette.get("colors", [])
    if len(colors) < 2:
        problems.append(f"{where}.colors needs at least 2 entries")
    seen: set[str] = set()
    for c in colors:
        hexv = str(c.get("hex", ""))
        if not HEX_RE.match(hexv):
            problems.append(f"{where}: colour {c.get('name')!r} has bad hex {hexv!r}")
        if hexv.upper() in seen:
            problems.append(f"{where}: duplicate hex {hexv}")
        seen.add(hexv.upper())
        if not c.get("name"):
            problems.append(f"{where}: colour {hexv} has no name")
    return problems


def _clauses(mapping: dict) -> str:
    """`{"a": "x", "b": "y"}` -> `"x; y."` - keys are structure for humans, not the model."""
    values = [str(v).rstrip(".") for v in mapping.values() if v]
    return "; ".join(values) + "." if values else ""


def _sentences(items: list) -> str:
    return "; ".join(str(i).rstrip(".") for i in items if i)


def list_versions(style_dir: Path | None = None) -> list[tuple[int, Path]]:
    style_dir = style_dir or project().style_dir
    found = []
    for p in sorted(style_dir.glob("style-guide-v*.json")):
        m = VERSION_RE.match(p.name)
        if m:
            found.append((int(m.group(1)), p))
    return sorted(found)
