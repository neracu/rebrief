from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from rebrief.mcp.service import ScanService, format_rebrief_context


def create_server(service: ScanService | None = None) -> MCPServer:
    """Build the rebrief MCP server."""
    scan = service or ScanService()
    mcp = MCPServer("rebrief")

    @mcp.tool()
    def get_repository_brief(path: str = ".", force_refresh: bool = False) -> str:
        """Run (or read cached) rebrief scan and return the full REBRIEF.md markdown.

        ``path`` may be a local directory, an HTTPS/SSH git URL, or GitHub
        ``owner/repo`` shorthand.
        """
        return scan.get_repository_brief(path, force_refresh=force_refresh)

    @mcp.tool(structured_output=True)
    def get_risk_map(path: str = ".", min_confidence: str = "medium") -> dict[str, Any]:
        """Return CRITICAL/WARNING/INFO risks filtered by minimum confidence."""
        return scan.get_risk_map(path, min_confidence=min_confidence)

    @mcp.tool(structured_output=True)
    def get_codebase_hotspots(path: str = ".", top_n: int = 10) -> list[dict[str, Any]]:
        """Return top N git-churn hotspot files with change counts."""
        return scan.get_codebase_hotspots(path, top_n=top_n)

    @mcp.tool(structured_output=True)
    def get_tech_stack(path: str = ".") -> dict[str, Any]:
        """Return detected languages, frameworks, manifests, and dependencies."""
        return scan.get_tech_stack(path)

    @mcp.resource("rebrief://summary")
    def rebrief_summary() -> str:
        """Latest Rebrief markdown summary for the current working directory."""
        return scan.get_repository_brief(".")

    @mcp.prompt()
    def rebrief_context(summary: str = "") -> str:
        """Steer an agent with the latest Rebrief architectural hotspots and risks."""
        text = summary.strip() if summary else scan.get_repository_brief(".")
        return format_rebrief_context(text)

    return mcp


def run_stdio() -> None:
    """Start the MCP server over stdin/stdout."""
    create_server().run()
