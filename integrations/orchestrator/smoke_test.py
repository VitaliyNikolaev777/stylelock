"""Check a stylelock connector end to end, the way an MCP host launches it.

    uv run --with "mcp>=2.3,<3" python smoke_test.py connector.json
    uv run --with "mcp>=2.3,<3" python smoke_test.py connector.json --generate   # spends 1 image

Reads a connector definition (command, args, env), starts the server over stdio, lists the
tools, calls `status` and `preview_prompt`, and with --generate makes one image.
Key values from the file are passed to the server, never printed. Placeholder values
("<...>") are dropped, so a key already exported in your shell is used instead.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

try:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters
except ImportError:
    sys.exit('needs the MCP SDK: uv run --with "mcp>=2.3,<3" python smoke_test.py ...')


def load(path: str) -> StdioServerParameters:
    spec = json.loads(open(path).read())
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    for key, value in (spec.get("env") or {}).items():
        if isinstance(value, str) and value.startswith("<"):
            if key in os.environ:  # placeholder in the file, real value in the shell
                env[key] = os.environ[key]
            continue
        env[key] = value
    if any("/ABSOLUTE/PATH" in a for a in spec["args"]):
        sys.exit("edit the --project path in the connector file first")
    return StdioServerParameters(command=spec["command"], args=spec["args"], env=env)


def text(result) -> str:
    return result.content[0].text if result.content else ""


async def run(params: StdioServerParameters, generate: bool) -> int:
    async with Client(params, read_timeout_seconds=180) as c:
        tools = sorted(t.name for t in (await c.list_tools()).tools)
        print(f"tools ({len(tools)}): {', '.join(tools)}")

        st = await c.call_tool("status")
        if st.is_error:
            print("status FAILED:", text(st))
            return 1
        s = json.loads(text(st))
        g, gen = s["guide"], s["generation"]
        caps = gen["capabilities"] or {}
        print(f"project : {s['project']}")
        print(f"guide   : {g['label']} status={g['status']} problems={len(g['problems'])}")
        print(f"painter : {gen['provider']} / {gen['model']} key_set={caps.get('key_set')} "
              f"transparency={caps.get('supports_transparency')} refs={caps.get('supports_reference_images')}")
        print(f"budget  : {s['budget']}")
        for step in s["next_steps"]:
            print(f"next    : {step}")

        subject = "a simple wooden chair"
        pv = await c.call_tool("preview_prompt", {"subject": subject})
        if pv.is_error:
            print("preview FAILED:", text(pv))
            return 1
        p = json.loads(text(pv))
        print(f"preview : {p['prompt_words']} words, {len(p['references'])} reference(s), "
              f"fingerprint {p['fingerprint']}")

        if generate:
            r = await c.call_tool("generate", {"subject": subject, "allow_draft": True})
            if r.is_error:
                print("generate FAILED:", text(r))
                return 1
            out = json.loads(text(r))
            print(f"generate: {out['images'][0]['image']} "
                  f"({len(r.content) - 1} preview image(s) returned)")
    print("ok")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("connector", help="connector .json (command, args, env)")
    ap.add_argument("--generate", action="store_true", help="also make one real image")
    a = ap.parse_args()
    return asyncio.run(run(load(a.connector), a.generate))


if __name__ == "__main__":
    sys.exit(main())
