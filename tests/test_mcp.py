"""The MCP server: in-process for the tool behaviour, once over real stdio like a host would."""

import asyncio
import json
import os
import sys

import pytest

pytest.importorskip("mcp")

from mcp import Client  # noqa: E402

from stylelock.mcp_server import build_server  # noqa: E402

EXPECTED_TOOLS = {
    "status", "style_info", "preview_prompt", "generate", "view_image", "list_pending",
    "accept", "reject", "review_reasons", "review_report", "list_references",
    "add_reference", "read_doc",
}


def call(server, name, args=None):
    async def go():
        async with Client(server) as c:
            return await c.call_tool(name, args or {})
    return asyncio.run(go())


def data(result):
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


def test_tools_and_instructions(project):
    server = build_server()

    async def go():
        async with Client(server) as c:
            return {t.name for t in (await c.list_tools()).tools}
    assert asyncio.run(go()) == EXPECTED_TOOLS
    assert "art director" in server.instructions


def test_status_reports_configuration_but_no_key(project, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-never-show-this")
    monkeypatch.setenv("STYLELOCK_PROVIDER", "openai")
    r = call(build_server(max_images=5), "status")
    d = data(r)
    assert d["generation"]["provider"] == "openai"
    assert d["generation"]["capabilities"]["key_set"] is True
    assert d["budget"] == {"max_images": 5, "generated_this_session": 0}
    assert "sk-never-show-this" not in r.content[0].text


def test_generate_returns_summary_and_previews(project):
    r = call(build_server(), "generate", {"subject": "a kite", "n": 2, "allow_draft": True})
    assert not r.is_error
    kinds = [type(b).__name__ for b in r.content]
    assert kinds == ["TextContent", "ImageContent", "ImageContent"]
    summary = json.loads(r.content[0].text)
    assert len(summary["images"]) == 2 and summary["generated_this_session"] == 2


def test_budget_is_enforced_per_session(project):
    server = build_server(max_images=2)

    async def go():
        async with Client(server) as c:
            a = await c.call_tool("generate", {"subject": "a", "n": 2, "allow_draft": True})
            b = await c.call_tool("generate", {"subject": "b", "allow_draft": True})
            return a, b
    a, b = asyncio.run(go())
    assert not a.is_error and b.is_error
    assert "budget" in b.content[0].text


def test_zero_budget_means_read_only(project, monkeypatch):
    r = call(build_server(max_images=0), "generate", {"subject": "a", "allow_draft": True})
    assert r.is_error and "budget" in r.content[0].text
    monkeypatch.setenv("STYLELOCK_MAX_IMAGES", "0")
    r = call(build_server(), "generate", {"subject": "a", "allow_draft": True})
    assert r.is_error and "budget" in r.content[0].text


def test_model_cannot_be_chosen_by_the_agent(project):
    r = call(build_server(), "generate",
             {"subject": "a", "allow_draft": True, "options": {"model": "something-else"}})
    assert r.is_error and "host" in r.content[0].text


def test_draft_guide_is_an_error_the_model_can_read(project):
    r = call(build_server(), "generate", {"subject": "a"})
    assert r.is_error and "draft" in r.content[0].text


def test_paths_outside_the_project_are_refused(project, tmp_path):
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"x")
    for tool, args in (
        ("view_image", {"path": str(outside)}),
        ("view_image", {"path": "../secret.png"}),
        ("add_reference", {"path": str(outside), "demonstrates": "x"}),
        ("accept", {"path": "/etc/hosts"}),
    ):
        r = call(build_server(), tool, args)
        assert r.is_error and "outside the project" in r.content[0].text, tool


def test_review_round_trip(project):
    server = build_server()

    async def go():
        async with Client(server) as c:
            g = await c.call_tool("generate", {"subject": "a kite", "allow_draft": True})
            img = json.loads(g.content[0].text)["images"][0]["image"]
            pend = await c.call_tool("list_pending")
            bad = await c.call_tool("reject", {"path": img, "reasons": ["looks-bad"]})
            ok = await c.call_tool("reject", {"path": img, "reasons": ["off-palette"], "note": "n"})
            view = await c.call_tool("view_image", {"path": "outputs"})
            return img, pend, bad, ok, view
    img, pend, bad, ok, view = asyncio.run(go())
    assert [p["image"] for p in data(pend)["pending"]] == [img]
    assert bad.is_error and "unknown reason" in bad.content[0].text
    assert data(ok)["reasons"] == ["off-palette"]
    assert view.is_error and "not an image file" in view.content[0].text


def test_add_reference_from_inside_the_project(project):
    from stylelock.providers.dryrun import _solid_png

    src = project / "references" / "_source" / "hero.png"
    src.write_bytes(_solid_png(8, 8))
    r = call(build_server(), "add_reference",
             {"path": "references/_source/hero.png", "demonstrates": "the look"})
    assert data(r)["file"] == "anchors/hero.png"
    refs = data(call(build_server(), "list_references"))["references"]
    assert [x["id"] for x in refs] == ["hero"]


def test_read_doc(project):
    r = call(build_server(), "read_doc", {"name": "briefing"})
    assert not r.is_error and "Briefing" in r.content[0].text
    assert call(build_server(), "read_doc", {"name": "nope"}).is_error


def test_real_stdio_session(project):
    """Launch the server the way an MCP host does and talk to it over stdin/stdout."""
    from mcp.client.stdio import StdioServerParameters

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "stylelock", "mcp", "--project", str(project), "--max-images", "3"],
        env={"PATH": os.environ.get("PATH", ""), "STYLELOCK_PROVIDER": "dryrun"},
    )

    async def go():
        async with Client(params, read_timeout_seconds=30) as c:
            tools = {t.name for t in (await c.list_tools()).tools}
            st = await c.call_tool("status")
            gen = await c.call_tool("generate", {"subject": "a kite", "allow_draft": True})
            return tools, st, gen
    tools, st, gen = asyncio.run(go())
    assert tools == EXPECTED_TOOLS
    assert data(st)["budget"]["max_images"] == 3
    assert not gen.is_error and (project / "outputs").glob("*.png")


def test_orchestrator_folder_matches_the_server():
    """integrations/orchestrator/ ships copies of the instructions and tool schemas."""
    import importlib.util
    from pathlib import Path

    here = Path(__file__).resolve().parents[1] / "integrations" / "orchestrator"
    spec = importlib.util.spec_from_file_location("regen", here / "regenerate.py")
    regen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regen)
    for name, text in regen.current().items():
        assert (here / name).read_text() == text, f"{name} is stale - run regenerate.py"


def test_connector_templates_are_valid_and_hold_no_key():
    from pathlib import Path

    from stylelock.providers import REGISTRY

    here = Path(__file__).resolve().parents[1] / "integrations" / "orchestrator"
    files = sorted(here.glob("connector*.json"))
    assert len(files) == 3
    for f in files:
        c = json.loads(f.read_text())
        assert c["command"] == "stylelock" and c["args"][0] == "mcp" and "--project" in c["args"]
        assert c["env"]["STYLELOCK_PROVIDER"] in REGISTRY
        for k, v in c["env"].items():
            if k.endswith(("_KEY", "_TOKEN")):
                assert v.startswith("<"), f"{f.name}: {k} looks like a real key"
