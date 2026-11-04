"""Rewrite system-prompt.md and tools.json from what the package actually serves.

    .venv/bin/python integrations/orchestrator/regenerate.py           # write
    .venv/bin/python integrations/orchestrator/regenerate.py --check   # exit 1 if stale
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def current() -> dict[str, str]:
    from mcp import Client

    from stylelock import service
    from stylelock.cli import main
    from stylelock.mcp_server import build_server

    cwd, home = Path.cwd(), os.environ.get("STYLELOCK_HOME")
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "p"
        with contextlib.redirect_stdout(io.StringIO()):
            main(["init", str(proj)])
        try:
            server = build_server(proj)  # sets STYLELOCK_HOME and chdirs into the project

            async def tools():
                async with Client(server) as c:
                    return (await c.list_tools()).tools
            listed = asyncio.run(tools())
        finally:
            os.chdir(cwd)
            if home is None:
                os.environ.pop("STYLELOCK_HOME", None)
            else:
                os.environ["STYLELOCK_HOME"] = home

    spec = [{"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in listed]
    return {
        "system-prompt.md": service.read_doc("agent"),
        "tools.json": json.dumps(spec, indent=2) + "\n",
    }


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for name, text in current().items():
        path = HERE / name
        if path.exists() and path.read_text() == text:
            continue
        stale.append(name)
        if not check:
            path.write_text(text)
    if check and stale:
        print(f"stale: {', '.join(stale)} - run integrations/orchestrator/regenerate.py")
        return 1
    print("up to date" if not stale else f"rewrote {', '.join(stale)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
