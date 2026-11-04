"""stylelock - style-locked image generation. Every image goes through `stylelock generate`."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import date
from pathlib import Path

from . import __version__, service
from .config import (
    SETTABLE,
    USER_ENV_FILE,
    ProjectNotFound,
    env_sources,
    find_root,
    is_project,
    load_dotenv,
    write_env_value,
)
from .generate import DraftGuideError
from .manifest import KNOWN_ROLES, ManifestError
from .providers import REGISTRY, ProviderError
from .review import ReviewError
from .style import StyleError, StyleGuide, list_versions


def _split(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


def _emit(a: argparse.Namespace, data, text=None) -> None:
    """`--json` prints data; otherwise `text(data)` (or the data itself) for humans."""
    if getattr(a, "json", False):
        print(json.dumps(data, indent=2, default=str))
    elif text is not None:
        text(data)
    else:
        print(data if isinstance(data, str) else json.dumps(data, indent=2, default=str))


# -- generate ------------------------------------------------------------

def cmd_generate(a: argparse.Namespace) -> int:
    opts = {}
    for kv in a.option or []:
        key, _, val = kv.partition("=")
        opts[key.strip()] = _coerce(val.strip())
    if a.model:
        opts["model"] = a.model

    brief = dict(
        style_version=a.style_version, variant=a.variant, asset_type=a.type,
        character=a.character, roles=_split(a.roles), tags=_split(a.tags),
        ref_ids=_split(a.ref_ids), extra=a.extra,
    )

    if a.dry_run:
        def show(d):
            print(d["prompt"])
            print("\n--- negative ---")
            print(", ".join(d["negative"]) or "(none)")
            print("\n--- references ---")
            for r in d["references"]:
                print(f"  {r['id']} [{r['role']}] {r['file']}")
            print(f"\nstyle: {d['style']}  fingerprint: {d['fingerprint']}")
        _emit(a, service.preview(a.subject, **brief), show)
        return 0

    try:
        results = service.generate(
            a.subject, provider=a.provider, n=a.n, allow_draft=a.allow_draft,
            provider_options=opts, **brief,
        )
    except DraftGuideError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    _emit(a, results, lambda rs: [print(r["image"]) for r in rs])
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
        rows = []
        for num, path in list_versions():
            g = StyleGuide(path=path, data=json.loads(path.read_text()))
            rows.append({"n": num, "version": g.version, "status": g.status, "file": path.name})
        _emit(a, rows, lambda rs: [
            print(f"v{r['n']:<3} {r['version']:<8} {r['status']:<11} {r['file']}") for r in rs
        ])
        return 0

    if a.style_action in {"variants", "types", "cast"}:
        info = service.style_info(a.style_version)
        section = info[a.style_action]

        def show(sec):
            if not sec:
                print(f"(this guide defines no {a.style_action})")
            for name, desc in sec.items():
                print(f"{name:<14} {desc}")
        _emit(a, section, show)
        return 0

    guide = StyleGuide.load(a.style_version)
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
        problems, warnings = guide.validate(), guide.warnings()

        def show(d):
            for w in d["warnings"]:
                print(f"  warning: {w}")
            if d["problems"]:
                print(f"{d['guide']}: {len(d['problems'])} problem(s)")
                for p in d["problems"]:
                    print(f"  - {p}")
            else:
                print(f"{d['guide']}: ok" + (" (status=draft)" if d["status"] == "draft" else ""))
        _emit(a, {"guide": guide.label, "status": guide.status,
                  "problems": problems, "warnings": warnings}, show)
        return 1 if problems else 0

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
    if a.refs_action == "list":
        def show(rows):
            if not rows:
                print("(no references match)")
            for r in rows:
                flag = "on " if r["enabled"] else "off"
                print(f"[{flag}] {r['id']:<28} {r['role']:<12} {r['file']}")
                if r["demonstrates"]:
                    print(f"      {r['demonstrates']}")
        _emit(a, service.references(_split(a.roles), _split(a.tags)), show)
        return 0

    if a.refs_action == "validate":
        problems = service.validate_references()

        def show(ps):
            if not ps:
                print("reference library ok")
                return
            print(f"{len(ps)} problem(s):")
            for p in ps:
                print(f"  - {p}")
        _emit(a, problems, show)
        return 1 if problems else 0

    if a.refs_action == "add":
        if not a.path:
            print("error: refs add needs an image path", file=sys.stderr)
            return 2
        try:
            ref = service.add_reference(
                a.path, role=a.role, demonstrates=a.demonstrates, tags=_split(a.tags),
                exclude=_split(a.exclude), ref_id=a.id, force=a.force,
            )
        except (FileNotFoundError, FileExistsError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        _emit(a, ref, lambda r: print(f"added {r['id']} -> {r['file']}"))
        return 0

    return 1


# -- review --------------------------------------------------------------

def cmd_review(a: argparse.Namespace) -> int:
    if a.review_action == "pending":
        def show(rows):
            for r in rows:
                print(r["image"])
            if not rows:
                print("(nothing unreviewed)")
        _emit(a, service.pending(), show)
        return 0

    if a.review_action == "reasons":
        _emit(a, service.reasons(), lambda d: [print(f"{k:<16} {v}") for k, v in d.items()])
        return 0

    if a.review_action in {"accept", "reject"} and not a.image:
        print(f"error: review {a.review_action} needs an image path", file=sys.stderr)
        return 2

    if a.review_action == "accept":
        _emit(a, service.accept(a.image, a.note), lambda d: print(f"accepted {d['image']}"))
        return 0

    if a.review_action == "reject":
        d = service.reject(a.image, _split(a.reasons) or [], a.note)
        _emit(a, d, lambda d: print(f"rejected -> {d['moved_to']}"))
        return 0

    if a.review_action == "report":
        def show(r):
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
        _emit(a, service.report(a.min_hits), show)
        return 0

    return 1


# -- doctor / providers / config -----------------------------------------

def cmd_doctor(a: argparse.Namespace) -> int:
    s = service.status()

    def show(s):
        g = s["guide"]
        print(f"project     : {s['project']}")
        gp = "ok" if not g["problems"] else f"{len(g['problems'])} problem(s)"
        print(f"style guide : {g['label']} status={g['status']} {gp}")
        for p in g["problems"]:
            print(f"                - {p}")
        if g["variants"]:
            print(f"variants    : {', '.join(g['variants'])}")
        if g["types"]:
            print(f"asset types : {', '.join(g['types'])}")
        r = s["references"]
        rp = "ok" if not r["problems"] else f"{len(r['problems'])} problem(s)"
        print(f"references  : {r['enabled_anchors']} enabled anchor(s), {rp}")
        gen = s["generation"]
        caps = gen["capabilities"] or {}
        key = "no key needed" if not caps.get("key_env") else (
            "key set" if caps.get("key_set") else f"{caps['key_env']} missing")
        print(f"generation  : {gen['provider']} / {gen['model'] or '?'} "
              f"(provider from {gen['sources']['provider']}, model from {gen['sources']['model']}; {key})")
        print(f"review      : {s['unreviewed']} unreviewed, {s['rejects_logged']} rejects logged")
        for w in g["warnings"]:
            print(f"warning     : {w}")
        for step in s["next_steps"]:
            print(f"next        : {step}")

    _emit(a, s, show)
    return 0 if s["ok"] else 1


def cmd_providers(a: argparse.Namespace) -> int:
    def show(rows):
        for p in rows:
            key = "no key needed" if not p["key_env"] else (
                "key set" if p["key_set"] else f"{p['key_env']} missing")
            caps = ", ".join(
                label for flag, label in (
                    ("supports_reference_images", "references"),
                    ("supports_transparency", "transparency"),
                    ("supports_negative_prompt", "negative prompt"),
                ) if p[flag]
            ) or "text only"
            print(f"{p['name']:<18} {p['default_model'] or '-':<32} {key}")
            print(f"{'':<18} {caps}")
            if p["notes"]:
                print(f"{'':<18} {p['notes']}")
    _emit(a, service.providers(), show)
    return 0


def cmd_config(a: argparse.Namespace) -> int:
    target = (find_root() / ".env") if a.project and find_root() else USER_ENV_FILE
    if a.project and not find_root():
        raise ProjectNotFound("--project needs to run inside a stylelock project")

    if a.config_action == "show":
        names = sorted({*SETTABLE.values(), *(p.key_env for p in REGISTRY.values() if p.key_env)})
        sources = env_sources(names)
        load_dotenv()
        data = {
            "files": {"project": str(find_root() / ".env") if find_root() else None,
                      "user": str(USER_ENV_FILE)},
            "values": {
                n: {"source": sources[n],
                    "value": (_mask(os.environ.get(n, "")) if n.endswith(("_KEY", "_TOKEN"))
                              else os.environ.get(n, ""))}
                for n in names
            },
        }
        if find_root():
            data["generation"] = service.generation_config()

        def show(d):
            print(f"project .env : {d['files']['project'] or '(not in a project)'}")
            print(f"user .env    : {d['files']['user']}")
            for n, v in d["values"].items():
                shown = v["value"] or "-"
                print(f"  {n:<28} {shown:<34} {v['source']}")
            if "generation" in d:
                g = d["generation"]
                print(f"\ngenerate would use: {g['provider']} / {g['model'] or '?'}")
        _emit(a, data, show)
        return 0

    if a.config_action == "set":
        env = SETTABLE.get(a.name)
        if env is None:
            print(f"error: can set {', '.join(SETTABLE)} (keys go through `config set-key`)",
                  file=sys.stderr)
            return 2
        if a.name == "provider" and a.value not in REGISTRY:
            print(f"error: unknown provider {a.value!r} (available: {', '.join(sorted(REGISTRY))})",
                  file=sys.stderr)
            return 2
        write_env_value(target, env, a.value)
        print(f"{env}={a.value} -> {target}")
        return 0

    if a.config_action == "set-key":
        cls = REGISTRY.get(a.name)
        if cls is None or not cls.key_env:
            keyed = sorted(n for n, p in REGISTRY.items() if p.key_env)
            print(f"error: providers with keys: {', '.join(keyed)}", file=sys.stderr)
            return 2
        # never from argv - it would land in shell history and process listings
        value = getpass.getpass(f"{cls.key_env}: ") if sys.stdin.isatty() else sys.stdin.readline()
        value = value.strip()
        if not value:
            print("error: empty key, nothing written", file=sys.stderr)
            return 2
        write_env_value(target, cls.key_env, value)
        print(f"{cls.key_env} saved to {target} (mode 600)")
        return 0

    return 1


def _mask(v: str) -> str:
    return "" if not v else (v[:3] + "…" + v[-4:] if len(v) > 10 else "set")


# -- instructions / mcp --------------------------------------------------

def cmd_instructions(a: argparse.Namespace) -> int:
    print(service.read_doc(a.doc))
    return 0


def cmd_mcp(a: argparse.Namespace) -> int:
    from .mcp_server import serve

    serve(a.project, a.max_images)
    return 0


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
        "  1. stylelock config set provider openai && stylelock config set-key openai\n"
        "  2. describe your style in style/style-guide-v1.json, then set status to active\n"
        "  3. add 2-5 approved images: stylelock refs add <file> --role anchor --demonstrates '...'\n"
        "  4. stylelock doctor"
    )
    return 0


# -- parser --------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stylelock", description=__doc__)
    p.add_argument("--version", action="version", version=f"stylelock {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    js = argparse.ArgumentParser(add_help=False)
    js.add_argument("--json", action="store_true", help="machine-readable output")

    i = sub.add_parser("init", help="create a new project (style guide, reference library, folders)")
    i.add_argument("dir", nargs="?", default=".", help="where to create it (default: here)")
    i.set_defaults(func=cmd_init)

    g = sub.add_parser("generate", parents=[js], help="generate images through the style wrapper")
    g.add_argument("subject", help="what to depict - the subject only, never the style")
    g.add_argument("--provider", default=None, choices=sorted(REGISTRY),
                   help="default: STYLELOCK_PROVIDER, else dryrun")
    g.add_argument("--model", default=None, help="default: STYLELOCK_MODEL, else the guide's")
    g.add_argument("--style-version", default=None, help="e.g. 1, or a path to a guide .json")
    g.add_argument("--variant", default=None, help="which world (see `stylelock style variants`)")
    g.add_argument("--type", default=None, help="what kind of asset (see `stylelock style types`)")
    g.add_argument("--character", default=None, help="lock a cast member (see `stylelock style cast`)")
    g.add_argument("--roles", default=None, help="reference roles, comma separated (default: anchor)")
    g.add_argument("--tags", default=None, help="require all these tags on references")
    g.add_argument("--ref-ids", default=None, help="use exactly these reference ids")
    g.add_argument("--extra", default="", help="per-image direction, appended after the style block")
    g.add_argument("-n", type=int, default=1)
    g.add_argument("--allow-draft", action="store_true", help="generate against a draft guide")
    g.add_argument("--dry-run", action="store_true", help="print the assembled prompt and exit")
    g.add_argument("--option", action="append", help="provider option, key=value (repeatable)")
    g.set_defaults(func=cmd_generate)

    s = sub.add_parser("style", parents=[js], help="inspect and version the style spec")
    s.add_argument("style_action",
                   choices=["show", "render", "lint", "list", "bump", "variants", "types", "cast"])
    s.add_argument("--style-version", default=None)
    s.add_argument("--variant", default=None)
    s.add_argument("--type", default=None)
    s.add_argument("--character", default=None)
    s.set_defaults(func=cmd_style)

    r = sub.add_parser("refs", parents=[js], help="manage the reference library")
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

    v = sub.add_parser("review", parents=[js], help="accept/reject outputs and mine the failures")
    v.add_argument("review_action", choices=["pending", "accept", "reject", "report", "reasons"])
    v.add_argument("image", nargs="?")
    v.add_argument("--reasons", default=None, help="comma separated, see `stylelock review reasons`")
    v.add_argument("--note", default="")
    v.add_argument("--min-hits", type=int, default=3)
    v.set_defaults(func=cmd_review)

    d = sub.add_parser("doctor", parents=[js], help="check the whole setup")
    d.set_defaults(func=cmd_doctor)

    pr = sub.add_parser("providers", parents=[js], help="image providers, capabilities, key status")
    pr.set_defaults(func=cmd_providers)

    c = sub.add_parser("config", parents=[js], help="generation settings and API keys")
    c.add_argument("config_action", choices=["show", "set", "set-key"])
    c.add_argument("name", nargs="?", help=f"set: {', '.join(SETTABLE)}; set-key: a provider")
    c.add_argument("value", nargs="?")
    c.add_argument("--project", action="store_true",
                   help="write to this project's .env instead of ~/.config/stylelock/.env")
    c.set_defaults(func=cmd_config)

    ins = sub.add_parser("instructions", help="print the workflow for an orchestrating model")
    ins.add_argument("doc", nargs="?", default="agent", choices=service.DOCS)
    ins.set_defaults(func=cmd_instructions)

    m = sub.add_parser("mcp", help="run as an MCP server over stdio")
    m.add_argument("--project", default=None, help="project folder (default: discovery)")
    m.add_argument("--max-images", type=int, default=None, help="cap per session")
    m.set_defaults(func=cmd_mcp)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "config" and args.config_action in {"set", "set-key"} and not args.name:
        print(f"error: config {args.config_action} needs a name", file=sys.stderr)
        return 2
    if args.command == "config" and args.config_action == "set" and args.value is None:
        print("error: config set needs a value", file=sys.stderr)
        return 2
    try:
        return args.func(args)
    except (ProjectNotFound, StyleError, ManifestError, ProviderError, ReviewError,
            ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
