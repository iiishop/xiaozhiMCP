from __future__ import annotations

from typing import Any

from ..base import MCPComponent
from error_store import ErrorStore


class LogMCPComponent(MCPComponent):
    def __init__(self, db_path: str | None = None) -> None:
        self.store = ErrorStore(db_path=db_path)

    def supports_role(self, role: str) -> bool:
        return role == "server"

    def export_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "logmcp_get_errors",
                "description": "Get recent server-side error logs and predefined conclusions.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"},
                    },
                },
            }
        ]

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        if tool_name != "logmcp_get_errors":
            raise RuntimeError(f"unknown tool: {tool_name}")
        limit = int(arguments.get("limit", 50))
        rows = self.store.list_recent(limit)
        return {"success": True, "count": len(rows), "errors": rows}

    def register(self, mcp: Any) -> None:
        @mcp.tool()
        def logmcp_get_errors(limit: int = 50) -> dict:
            """Get recent server-side runtime errors with time and suggested conclusion."""
            return self.invoke_tool("logmcp_get_errors", {"limit": int(limit)})


def build_component(config: dict[str, Any] | None = None) -> LogMCPComponent:
    section = config or {}
    db_path = str(section.get("db_path", "")).strip() or None
    return LogMCPComponent(db_path=db_path)
