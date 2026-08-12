from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")

from mcp import Client

from rebrief.mcp.server import create_server
from rebrief.mcp.service import ScanService, format_rebrief_context


def _seed_repo(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("flask>=3.0\n", encoding="utf-8")


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _payload(result: object) -> object:
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
        return structured["result"]
    if structured is not None:
        return structured
    content = getattr(result, "content", None) or []
    if not content:
        return []
    text = getattr(content[0], "text", None)
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def test_lists_tools_resource_and_prompt() -> None:
    async def _inner() -> None:
        async with Client(create_server(), raise_exceptions=True) as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            assert tools >= {
                "get_repository_brief",
                "get_risk_map",
                "get_codebase_hotspots",
                "get_tech_stack",
            }
            resources = await client.list_resources()
            uris = [str(resource.uri) for resource in resources.resources]
            assert any(uri.startswith("rebrief://summary") for uri in uris)
            prompts = await client.list_prompts()
            names = [prompt.name for prompt in prompts.prompts]
            assert "rebrief_context" in names

    _run(_inner())


def test_call_tools(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    async def _inner() -> None:
        async with Client(create_server(ScanService()), raise_exceptions=True) as client:
            brief = await client.call_tool(
                "get_repository_brief", {"path": str(tmp_path)}
            )
            assert brief.is_error is False
            assert "REBRIEF" in brief.content[0].text

            stack = await client.call_tool("get_tech_stack", {"path": str(tmp_path)})
            assert stack.is_error is False
            payload = _payload(stack)
            assert isinstance(payload, dict)
            assert "Python" in payload["languages"] or "python" in str(payload).lower()

            risks = await client.call_tool(
                "get_risk_map", {"path": str(tmp_path), "min_confidence": "medium"}
            )
            assert risks.is_error is False
            risk_payload = _payload(risks)
            assert isinstance(risk_payload, dict)
            assert set(risk_payload) >= {"critical", "warning", "info"}

            hotspots = await client.call_tool(
                "get_codebase_hotspots", {"path": str(tmp_path), "top_n": 3}
            )
            assert hotspots.is_error is False
            hotspot_payload = _payload(hotspots)
            assert isinstance(hotspot_payload, list)

    _run(_inner())


def test_invalid_path_is_tool_error(tmp_path: Path) -> None:
    async def _inner() -> None:
        async with Client(create_server(), raise_exceptions=True) as client:
            result = await client.call_tool(
                "get_tech_stack", {"path": str(tmp_path / "missing")}
            )
            assert result.is_error is True
            assert "does not exist" in result.content[0].text

    _run(_inner())


def test_resource_and_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    async def _inner() -> None:
        async with Client(create_server(), raise_exceptions=True) as client:
            resource = await client.read_resource("rebrief://summary")
            texts = [block.text for block in resource.contents if hasattr(block, "text")]
            assert any("REBRIEF" in text for text in texts)

            prompted = await client.get_prompt("rebrief_context", {"summary": "HOTSPOTS"})
            message_text = prompted.messages[0].content.text
            assert message_text == format_rebrief_context("HOTSPOTS")

            auto = await client.get_prompt("rebrief_context", {})
            assert "REBRIEF" in auto.messages[0].content.text

    _run(_inner())
