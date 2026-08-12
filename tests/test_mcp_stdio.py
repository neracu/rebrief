from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_initialize_and_list_tools(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")

    async def _inner() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "rebrief", "mcp"],
            cwd=str(tmp_path),
        )
        async with Client(stdio_client(params)) as client:
            listed = await client.list_tools()
            names = {tool.name for tool in listed.tools}
            assert names >= {
                "get_repository_brief",
                "get_risk_map",
                "get_codebase_hotspots",
                "get_tech_stack",
            }
            result = await client.call_tool("get_tech_stack", {"path": str(tmp_path)})
            assert result.is_error is False

    asyncio.run(_inner())
