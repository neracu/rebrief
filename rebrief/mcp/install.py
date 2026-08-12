from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Callable

import click

MCP_SERVER_ENTRY = {
    "command": "rebrief",
    "args": ["mcp"],
}

CLAUDE_CODE_HINT = "claude mcp add rebrief -- rebrief mcp"

ClientName = str


def mcp_servers_snippet() -> dict[str, dict[str, dict[str, object]]]:
    return {"mcpServers": {"rebrief": dict(MCP_SERVER_ENTRY)}}


def claude_desktop_config_path() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def client_config_path(client: ClientName, *, cwd: Path | None = None) -> Path:
    root = cwd if cwd is not None else Path.cwd()
    mapping: dict[str, Callable[[], Path]] = {
        "cursor": lambda: root / ".cursor" / "mcp.json",
        "windsurf": lambda: root / ".windsurf" / "mcp.json",
        "claude": claude_desktop_config_path,
        "roo": lambda: root / ".roo" / "mcp.json",
    }
    try:
        return mapping[client]()
    except KeyError as exc:
        raise ValueError(f"Unknown MCP client: {client!r}") from exc


def merge_mcp_config(path: Path) -> None:
    existing: dict[str, object] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read existing MCP config at {path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"MCP config at {path} must be a JSON object.")
        existing = loaded

    servers = existing.get("mcpServers")
    if servers is None:
        servers = {}
        existing["mcpServers"] = servers
    if not isinstance(servers, dict):
        raise ValueError(f"mcpServers in {path} must be a JSON object.")
    servers["rebrief"] = dict(MCP_SERVER_ENTRY)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def install_mcp_config(
    client: str = "all",
    *,
    write: bool = False,
    cwd: Path | None = None,
    echo: Callable[[str], None] | None = None,
) -> list[Path]:
    """Print the MCP snippet and optionally merge it into client config files."""
    printer = echo or (lambda message: click.echo(message))
    snippet = json.dumps(mcp_servers_snippet(), indent=2, ensure_ascii=False)
    printer(snippet)
    printer("")
    printer(f"Claude Code: {CLAUDE_CODE_HINT}")

    targets = ["cursor", "windsurf", "claude", "roo"] if client == "all" else [client]
    written: list[Path] = []
    if not write:
        printer("")
        printer("Re-run with --write to merge this entry into client config files.")
        return written

    for name in targets:
        path = client_config_path(name, cwd=cwd)
        merge_mcp_config(path)
        written.append(path)
        printer(f"Wrote {name} config: {path}")
    return written
