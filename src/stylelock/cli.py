"""stylelock - style-locked image generation. Every image goes through `stylelock generate`."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .config import ProjectNotFound, is_project, load_dotenv, project
from .generate import DraftGuideError, run
from .manifest import KNOWN_ROLES, Library, ManifestError, Reference
from .prompt import assemble
from .providers import REGISTRY, ProviderError
from .review import REASONS, ReviewError, accept, pending, reject, report
from .style import StyleError, StyleGuide, list_versions


def _split(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


# -- generate ------------------------------------------------------------

def cmd_generate(a: argparse.Namespace) -> int:
    opts = {}
    for kv in a.option or []:
        key, _, val = kv.partition("=")
        opts[key.strip()] = _coerce(val.strip())

    if a.dry_run:
        guide = (
            StyleGuide.load(a.style_version)
            .with_variant(a.variant)
            .with_type(a.type)
            .with_character(a.character)
        )
        bundle = assemble(
            a.subject, guide, Library.load(),
            roles=_split(a.roles), tags=_split(a.tags), ref_ids=_split(a.ref_ids), extra=a.extra,
        )
        print(bundle.prompt)
        print("\n--- negative ---")
        print(", ".join(bundle.negative) or "(none)")
        print("\n--- references ---")
        for r in bundle.references:
            print(f"  {r.id} [{r.role}] {r.file}")
        print(f"\nstyle: {guide.label}  fingerprint: {bundle.fingerprint}")
        return 0

    try:
        paths = run(
            subject=a.subject,
            provider=a.provider,
            style_version=a.style_version,
            variant=a.variant,
            asset_type=a.type,
            character=a.character,
            roles=_split(a.roles),
            tags=_split(a.tags),
            ref_ids=_split(a.ref_ids),
            extra=a.extra,
            n=a.n,
            allow_draft=a.allow_draft,
            provider_options=opts,
        )
    except DraftGuideError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    for p in paths:
        print(p)
    return 0


def _coerce(v: str):
    if v.lower() in {"true", "false"}:
        return v.lower() == "true"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


# -- style ---------------------------------------------------------------

def cmd_style(a: argparse.Namespace) -> int:
    if a.style_action == "list":
        for num, path in list_versions():
            g = StyleGuide(path=path, data=json.loads(path.read_text()))
            print(f"v{num:<3} {g.version:<8} {g.status:<11} {path.name}")
        return 0

    guide = StyleGuide.load(a.style_version)

    if a.style_action == "cast":
        if not guide.cast:
            print("(this guide defines no cast)")
        for name, c in guide.cast.items():
            print(f"{name:<10} {c.get('description', '')}")
            print(f"{'':<10} {c.get('appearance', '')}")
        return 0

    if a.style_action in {"variants", "types"}:
        section = guide.variants if a.style_action == "variants" else guide.types
        if not section:
            print(f"(this guide defines no {a.style_action})")
        for name, v in section.items():
            tags = ", ".join(v.get("reference_tags", [])) or "inherits"
            print(f"{name:<10} {v.get('description', '')}")
            print(f"{'':<10} reference tags: {tags}")
        return 0

    if a.style_action in {"show", "render"}:
        # only the read-only views resolve overlays; lint and bump work on the base spec
        guide = guide.with_variant(a.variant).with_type(a.type).with_character(a.character)

    if a.style_action == "show":
        print(json.dumps(guide.data, indent=2))
        return 0

    if a.style_action == "render":
        print(guide.style_block())
        return 0

    if a.style_action == "lint":
        problems = guide.validate()
        for w in guide.warnings():
            print(f"  warning: {w}")
        if problems:
            print(f"{guide.label}: {len(problems)} problem(s)")
            for p in problems:
                print(f"  - {p}")
            return 1
        print(f"{guide.label}: ok" + (" (status=draft)" if guide.status == "draft" else ""))
        return 0

    if a.style_action == "bump":
        versions = list_versions()
        next_num = (versions[-1][0] if versions else 0) + 1
        dest = guide.path.parent / f"style-guide-v{next_num}.json"
        if dest.exists():
            print(f"error: {dest.name} already exists", file=sys.stderr)
            return 1
        data = dict(guide.data)
        major = guide.version.split(".")[0]
        data["version"] = f"{int(major) + 1}.0.0"
        data["status"] = "draft"
        data["updated"] = date.today().isoformat()
        dest.write_text(json.dumps(data, indent=2) + "\n")
        print(f"created {dest} from {guide.path.name} - edit it, then set status to active")
        print("Remember to mark the previous version deprecated and add a CHANGELOG entry.")
        return 0

    return 1


# -- refs ----------------------------------------------------------------

def cmd_refs(a: argparse.Namespace) -> int:
    lib = Library.load()

    if a.refs_action == "list":
        refs = lib.select(roles=_split(a.roles), tags=_split(a.tags), include_disabled=True)
        if not refs:
            print("(no references match)")
        for r in refs:
            flag = "on " if r.enabled else "off"
            print(f"[{flag}] {r.id:<28} {r.role:<12} {r.file}")
            if r.demonstrates:
                print(f"      {r.demonstrates}")
        return 0

    if a.refs_action == "validate":
        guide = StyleGuide.load()
        problems = lib.validate(
            anchor_limit=guide.anchor_limit, tag_groups=guide.reference_tag_groups()
        )
        if problems:
            print(f"{len(problems)} problem(s):")
            for p in problems:
                print(f"  - {p}")
            return 1
        print("reference library ok")
        return 0

    if a.refs_action == "add":
        src = Path(a.path).expanduser().resolve()
        if not src.exists():
            print(f"error: {src} not found", file=sys.stderr)
            return 1
        dest_dir = lib.root / (a.role + "s" if a.role == "anchor" else a.role)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists() and not a.force:
            print(f"error: {dest} exists (use --force)", file=sys.stderr)
            return 1
        shutil.copy2(src, dest)

        ref = Reference(
            id=a.id or dest.stem,
            file=dest.relative_to(lib.root).as_posix(),
            role=a.role,
            tags=_split(a.tags) or [],
            demonstrates=a.demonstrates,
            exclude=_split(a.exclude) or [],
            added=date.today().isoformat(),
        )
        lib.add(ref)
        lib.save()
        print(f"added {ref.id} -> {ref.file}")
        return 0

    return 1


# -- review --------------------------------------------------------------

def cmd_review(a: argparse.Namespace) -> int:
    if a.review_action == "pending":
        items = pending()
        for p in items:
            print(p)
        if not items:
            print("(nothing unreviewed)")
        return 0

    if a.review_action == "reasons":
        for k, v in sorted(REASONS.items()):
            print(f"{k:<16} {v}")
        return 0

    if a.review_action == "accept":
        accept(Path(a.image), note=a.note)
        print(f"accepted {a.image}")
        return 0

    if a.review_action == "reject":
        dest = reject(Path(a.image), reasons=_split(a.reasons) or [], note=a.note)
        print(f"rejected -> {dest}")
        return 0

    if a.review_action == "report":
        r = report(min_hits=a.min_hits)
        print(f"rejects logged: {r['total_rejects']}")
        if r["by_reason"]:
            print("\nby reason:")
            for k, v in r["by_reason"].items():
                print(f"  {v:>3}  {k}")
        if r["by_reference"]:
            print("\nreferences attached to rejects:")
            for k, v in r["by_reference"].items():
                print(f"  {v:>3}  {k}")
        if r["suggested_actions"]:
            print("\nsuggested actions:")
            for s in r["suggested_actions"]:
                print(f"  - {s}")
        elif r["total_rejects"]:
            print(f"\n(no reason has hit the {a.min_hits}x threshold yet)")
        return 0

    return 1


def cmd_doctor(_: argparse.Namespace) -> int:
    import os

    load_dotenv()
    ok = True

    print(f"project     : {project().root}")
    guide = StyleGuide.load()
    problems = guide.validate()
    print(f"style guide : {guide.label} status={guide.status} "
          f"{'ok' if not problems else f'{len(problems)} problem(s)'}")
    ok &= not problems

    if guide.variants:
        print(f"variants    : {', '.join(sorted(guide.variants))}")
    if guide.types:
        print(f"asset types : {', '.join(sorted(guide.types))}")

    lib = Library.load()
    ref_problems = lib.validate(
        anchor_limit=guide.anchor_limit, tag_groups=guide.reference_tag_groups()
    )
    anchors = len(lib.select(roles=["anchor"]))
    print(f"references  : {anchors} enabled anchor(s), "
          f"{'ok' if not ref_problems else f'{len(ref_problems)} problem(s)'}")
    ok &= not ref_problems

    keys = {
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "replicate": "REPLICATE_API_TOKEN",
    }
    print("providers   :")
    for name in sorted(REGISTRY):
        env = keys.get(name)
        if env is None:
            print(f"  {name:<10} ready (no key needed)")
        else:
            print(f"  {name:<10} {'key set' if os.getenv(env) else f'{env} missing'}")

    print(f"rejects     : {report()['total_rejects']} logged")
    for w in guide.warnings():
        print(f"warning     : {w}")
    if guide.status == "draft":
        print("\nnext: review the style guide, fix anything that reads wrong, "
              "then set status to active")
    if not anchors:
        print("next: add 2-5 approved on-style images with "
              "`stylelock refs add <file> --role anchor --demonstrates '...'`")
    return 0 if ok else 1


# -- init ----------------------------------------------------------------

# published path in the project -> file under stylelock/templates/
_TEMPLATE_FILES = {
    "style/style-guide-v1.json": "style-guide-v1.json",
    "style/style-guide.schema.json": "style-guide.schema.json",
    "style/CHANGELOG.md": "CHANGELOG.md",
    "references/manifest.json": "manifest.json",
    ".env.example": "env.example",
    ".gitignore": "gitignore",
    "CLAUDE.md": "CLAUDE.md",
}
_INIT_DIRS = (
    "style/experiments",
    "references/anchors", "references/palette", "references/texture",
    "references/composition", "references/subject", "references/_source",
    "outputs", "rejects",
)


def cmd_init(a: argparse.Namespace) -> int:
    from importlib.resources import files

    root = Path(a.dir).expanduser().resolve()
    if is_project(root):
        print(f"{root} is already a stylelock project - nothing changed")
        return 0

    templates = files("stylelock") / "templates"
    today = date.today().isoformat()
    created, kept = [], []
    for d in _INIT_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    for rel, name in _TEMPLATE_FILES.items():
        dest = root / rel
        if dest.exists():
            kept.append(rel)
            continue
        text = (templates / name).read_text()
        if name in {"style-guide-v1.json", "manifest.json"}:
            text = text.replace('"updated": ""', f'"updated": "{today}"', 1)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        created.append(rel)

    print(f"created a stylelock project at {root}")
    for rel in created:
        print(f"  + {rel}")
    for rel in kept:
        print(f"  = {rel} (already existed, left as is)")
    print(
        "\nnext:\n"
        "  1. put an API key in .env (see .env.example) or ~/.config/stylelock/.env\n"
        "  2. describe your style in style/style-guide-v1.json, then set status to active\n"
        "  3. add 2-5 approved images: stylelock refs add <file> --role anchor --demonstrates '...'\n"
        "  4. stylelock doctor"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stylelock", description=__doc__)
    p.add_argument("--version", action="version", version=f"stylelock {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    i = sub.add_parser("init", help="create a new project (style guide, reference library, folders)")
    i.add_argument("dir", nargs="?", default=".", help="where to create it (default: here)")
    i.set_defaults(func=cmd_init)

    g = sub.add_parser("generate", help="generate images through the style wrapper")
    g.add_argument("subject", help="what to depict - the subject only, never the style")
    g.add_argument("--provider", default="dryrun", choices=sorted(REGISTRY))
    g.add_argument("--style-version", default=None, help="e.g. 1 (default: latest)")
    g.add_argument("--variant", default=None, help="which world (see `stylelock style variants`)")
    g.add_argument("--type", default=None, help="what kind of asset (see `stylelock style types`)")
    g.add_argument(
        "--character",
        default=None,
        help="lock a named cast member into the prompt (see `stylelock style cast`)",
    )
    g.add_argument("--roles", default=None, help="reference roles, comma separated (default: anchor)")
    g.add_argument("--tags", default=None, help="require all these tags on references")
    g.add_argument("--ref-ids", default=None, help="use exactly these reference ids")
    g.add_argument("--extra", default="", help="extra per-image direction, appended after the style block")
    g.add_argument("-n", type=int, default=1)
    g.add_argument("--allow-draft", action="store_true", help="generate against a draft guide")
    g.add_argument("--dry-run", action="store_true", help="print the assembled prompt and exit")
    g.add_argument("--option", action="append", help="provider option, key=value (repeatable)")
    g.set_defaults(func=cmd_generate)

    s = sub.add_parser("style", help="inspect and version the style spec")
    s.add_argument(
        "style_action",
        choices=["show", "render", "lint", "list", "bump", "variants", "types", "cast"],
    )
    s.add_argument("--style-version", default=None)
    s.add_argument("--variant", default=None)
    s.add_argument("--type", default=None)
    s.add_argument("--character", default=None)
    s.set_defaults(func=cmd_style)

    r = sub.add_parser("refs", help="manage the reference library")
    r.add_argument("refs_action", choices=["list", "add", "validate"])
    r.add_argument("path", nargs="?", help="image to add")
    r.add_argument("--role", default="anchor", choices=KNOWN_ROLES)
    r.add_argument("--id", default=None)
    r.add_argument("--tags", default=None)
    r.add_argument("--demonstrates", default="")
    r.add_argument("--exclude", default=None, help="known impurities to ignore (non-anchors only)")
    r.add_argument("--roles", default=None, help="filter for list")
    r.add_argument("--force", action="store_true")
    r.set_defaults(func=cmd_refs)

    v = sub.add_parser("review", help="accept/reject outputs and mine the failures")
    v.add_argument("review_action", choices=["pending", "accept", "reject", "report", "reasons"])
    v.add_argument("image", nargs="?")
    v.add_argument("--reasons", default=None, help="comma separated, see `stylelock review reasons`")
    v.add_argument("--note", default="")
    v.add_argument("--min-hits", type=int, default=3)
    v.set_defaults(func=cmd_review)

    d = sub.add_parser("doctor", help="check the whole setup")
    d.set_defaults(func=cmd_doctor)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ProjectNotFound, StyleError, ManifestError, ProviderError, ReviewError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
