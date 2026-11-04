"""stylelock as an MCP server (stdio).

    stylelock mcp --project /path/to/art [--max-images 40]

Meant to be launched by an MCP host - an orchestrator's connector, Claude Desktop, an IDE.
The host decides the painter; the connected model only gets tools:

  * provider, model and API key come from the server's environment at launch
    (STYLELOCK_PROVIDER, STYLELOCK_MODEL, OPENAI_API_KEY, ...). No tool can change them and
    no tool result contains a key.
  * one server = one project. Every path a tool accepts must resolve inside it.
  * `--max-images` (or STYLELOCK_MAX_IMAGES) caps how many images one session may generate;
    0 makes a read-only connector.
  * each tool call is logged to stderr, one line; the sidecars stay the durable record.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

from . import __version__, service
from .config import ProjectNotFound, project
from .generate import DraftGuideError
from .manifest import ManifestError
from .providers import ProviderError
from .review import ReviewError
from .style import StyleError

# per-call provider options the model may set; the rest are the host's decision
ALLOWED_OPTIONS = {"size", "quality", "background", "output_format", "output_compression",
                   "aspect_ratio", "seed", "guidance", "num_inference_steps"}
MAX_N = 4
_EXPECTED = (StyleError, ManifestError, ProviderError, ReviewError, ProjectNotFound, DraftGuideError,
             ValueError, FileNotFoundError, FileExistsError)


def build_server(root: str | Path | None = None, max_images: int | None = None):
    try:
        from mcp.server.mcpserver import Image, MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
    except ImportError as e:  # pragma: no cover - optional extra
        raise SystemExit("the MCP server needs the mcp extra: pip install 'stylelock[mcp]'") from e

    if root:
        os.environ["STYLELOCK_HOME"] = str(Path(root).expanduser().resolve())
    proj = project()  # fail at launch, not on the first tool call
    os.chdir(proj.root)  # relative paths in tool arguments mean project-relative
    env_cap = os.getenv("STYLELOCK_MAX_IMAGES")
    # 0 is a real limit (a read-only connector), so test for None rather than truthiness
    limit = max_images if max_images is not None else (int(env_cap) if env_cap else None)
    budget = {"limit": limit, "used": 0}

    server = MCPServer(
        name="stylelock",
        title="stylelock - style-locked image generation",
        instructions=service.read_doc("agent"),
        version=__version__,
    )

    def log(msg: str) -> None:
        print(f"[stylelock] {msg}", file=sys.stderr, flush=True)

    def inside(path: str) -> Path:
        p = Path(path).expanduser()
        p = (proj.root / p if not p.is_absolute() else p).resolve()
        if p != proj.root and proj.root not in p.parents:
            raise ToolError(f"{path} is outside the project {proj.root}")
        return p

    def guide_arg(style_version: str | None) -> str | None:
        if style_version and style_version.endswith(".json"):
            return str(inside(style_version))
        return style_version

    def safe(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except _EXPECTED as e:
            raise ToolError(str(e)) from e

    def picture(path: Path, max_side: int, checker: bool):
        """A downscaled preview the model can look at. Transparent images go over a
        checkerboard so baked shadows, halos and punched holes are visible."""
        try:
            from PIL import Image as PILImage
        except ImportError:
            return Image(path=str(path))
        im = PILImage.open(path)
        im.thumbnail((max_side, max_side))
        if checker and im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = PILImage.new("RGBA", im.size, (204, 204, 204, 255))
            tile = max(8, max_side // 32)
            dark = PILImage.new("RGBA", (tile, tile), (150, 150, 150, 255))
            for y in range(0, im.size[1], tile):
                for x in range((y // tile) % 2 * tile, im.size[0], 2 * tile):
                    bg.paste(dark, (x, y))
            bg.alpha_composite(im)
            im = bg
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="PNG")
        return Image(data=buf.getvalue(), format="png")

    # -- tools -----------------------------------------------------------

    @server.tool(description="Project, style guide, reference library and the configured "
                             "image provider/model with its capabilities. Call this first.")
    def status() -> dict:
        log("status")
        out = safe(service.status)
        out["budget"] = {"max_images": budget["limit"], "generated_this_session": budget["used"]}
        return out

    @server.tool(description="The types (what kind of asset), variants (which world) and cast "
                             "(recurring characters) the guide offers, with descriptions.")
    def style_info(style_version: str | None = None) -> dict:
        log(f"style_info {style_version or ''}")
        return safe(service.style_info, guide_arg(style_version))

    @server.tool(description="Assemble the exact prompt and reference set for a brief without "
                             "generating anything. Free. Use before any new kind of brief.")
    def preview_prompt(
        subject: str,
        type: str | None = None,
        variant: str | None = None,
        character: str | None = None,
        extra: str = "",
        style_version: str | None = None,
        roles: list[str] | None = None,
        tags: list[str] | None = None,
        ref_ids: list[str] | None = None,
    ) -> dict:
        log(f"preview_prompt {subject!r} type={type} variant={variant}")
        return safe(service.preview, subject, style_version=guide_arg(style_version),
                    variant=variant, asset_type=type, character=character,
                    roles=roles, tags=tags, ref_ids=ref_ids, extra=extra)

    @server.tool(description="Generate n images (max 4) through the style lock. `subject` is "
                             "what to depict, never how it looks; per-image direction goes in "
                             "`extra`. Provider and model are fixed by the host. Returns a "
                             "summary per image plus a preview of each.")
    def generate(
        subject: str,
        type: str | None = None,
        variant: str | None = None,
        character: str | None = None,
        extra: str = "",
        n: int = 1,
        style_version: str | None = None,
        roles: list[str] | None = None,
        tags: list[str] | None = None,
        ref_ids: list[str] | None = None,
        allow_draft: bool = False,
        options: dict | None = None,
        preview_size: int = 512,
    ):
        if not 1 <= n <= MAX_N:
            raise ToolError(f"n must be between 1 and {MAX_N}")
        bad = set(options or {}) - ALLOWED_OPTIONS
        if bad:
            raise ToolError(
                f"options {sorted(bad)} are not settable here (allowed: {sorted(ALLOWED_OPTIONS)}); "
                "provider and model are the host's setting"
            )
        if budget["limit"] is not None and budget["used"] + n > budget["limit"]:
            raise ToolError(
                f"image budget reached: {budget['used']}/{budget['limit']} used this session - "
                "ask the user before generating more"
            )
        log(f"generate {subject!r} type={type} variant={variant} n={n}")
        results = safe(
            service.generate, subject, style_version=guide_arg(style_version), variant=variant,
            asset_type=type, character=character, roles=roles, tags=tags, ref_ids=ref_ids,
            extra=extra, n=n, allow_draft=allow_draft, provider_options=options or {},
        )
        budget["used"] += len(results)
        log(f"  -> {len(results)} image(s), {budget['used']} this session")
        content: list = [{"images": results, "generated_this_session": budget["used"],
                          "max_images": budget["limit"]}]
        content += [picture(Path(r["image"]), preview_size, True) for r in results]
        return content

    @server.tool(description="Show an image from the project at up to max_side pixels. "
                             "Transparent images are drawn over a checkerboard unless checker=false.")
    def view_image(path: str, max_side: int = 1024, checker: bool = True):
        p = inside(path)
        if not p.is_file():
            raise ToolError(f"{path} is not an image file in the project")
        log(f"view_image {p.name}")
        summary = service.describe_output(p) if p.with_suffix(".json").exists() else {"image": str(p)}
        return [summary, picture(p, max(64, min(max_side, 2048)), checker)]

    @server.tool(description="Generated images not yet accepted or rejected.")
    def list_pending() -> dict:
        log("list_pending")
        return {"pending": safe(service.pending)}

    @server.tool(description="Mark an image accepted (on-style and on-brief).")
    def accept(path: str, note: str = "") -> dict:
        log(f"accept {Path(path).name}")
        return safe(service.accept, str(inside(path)), note)

    @server.tool(description="Reject an image with one or more reasons from review_reasons, "
                             "plus a precise note. Moves it to rejects/ and logs it.")
    def reject(path: str, reasons: list[str], note: str = "") -> dict:
        log(f"reject {Path(path).name} {reasons}")
        return safe(service.reject, str(inside(path)), reasons, note)

    @server.tool(description="The fixed vocabulary of reject reasons.")
    def review_reasons() -> dict:
        return service.reasons()

    @server.tool(description="Aggregate the reject log into suggested guide changes.")
    def review_report(min_hits: int = 3) -> dict:
        log("review_report")
        return safe(service.report, min_hits)

    @server.tool(description="The reference library (anchors and role references).")
    def list_references(roles: list[str] | None = None, tags: list[str] | None = None) -> dict:
        log("list_references")
        return {"references": safe(service.references, roles, tags)}

    @server.tool(description="Register an image from inside the project as a reference. "
                             "Anchors must be purely on-style; partly-right images go in as "
                             "texture/composition/palette/subject with `exclude`.")
    def add_reference(
        path: str,
        demonstrates: str,
        role: str = "anchor",
        tags: list[str] | None = None,
        exclude: list[str] | None = None,
        id: str | None = None,
    ) -> dict:
        log(f"add_reference {Path(path).name} role={role}")
        return safe(service.add_reference, str(inside(path)), role=role,
                    demonstrates=demonstrates, tags=tags, exclude=exclude, ref_id=id)

    @server.tool(description="Read guidance: agent, briefing, guides, post-processing, review, one-offs.")
    def read_doc(name: str) -> str:
        log(f"read_doc {name}")
        return safe(service.read_doc, name)

    return server


def serve(root: str | None = None, max_images: int | None = None) -> None:
    server = build_server(root, max_images)
    print(f"[stylelock] MCP server for {project().root}", file=sys.stderr, flush=True)
    server.run("stdio")
