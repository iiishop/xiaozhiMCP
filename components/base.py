from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MCPComponent(ABC):
    def export_tools(self) -> list[dict[str, Any]]:
        return []

    async def ainvoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        return self.invoke_tool(tool_name, arguments)

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        raise RuntimeError(f"tool not supported by component: {tool_name}")

    @abstractmethod
    def register(self, mcp: Any) -> None:
        raise NotImplementedError
