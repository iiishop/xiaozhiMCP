from __future__ import annotations

import asyncio
import platform
from typing import Any

from macos_bridge import StdioMCPBridge, prepare_apple_music_bridge


class Component:
    def __init__(self, _config: dict[str, Any] | None = None, full_config: dict[str, Any] | None = None) -> None:
        self.full_config = full_config or {}
        self.bridge: StdioMCPBridge | None = None
        self.bridge_error: str | None = None

    def supports_role(self, role: str) -> bool:
        return role == "client" and platform.system().lower() == "darwin"

    def _ensure_bridge(self) -> StdioMCPBridge | None:
        if self.bridge is not None:
            return self.bridge
        if self.bridge_error is not None:
            return None
        try:
            cfg = prepare_apple_music_bridge(self.full_config)
            if cfg is None:
                self.bridge_error = "apple_music disabled or non-macos"
                return None
            self.bridge = StdioMCPBridge(cfg)
            return self.bridge
        except Exception as exc:  # noqa: BLE001
            self.bridge_error = str(exc)
            return None

    def export_tools(self) -> list[dict[str, Any]]:
        bridge = self._ensure_bridge()
        if bridge is None:
            return []
        clean: list[dict[str, Any]] = []
        for t in bridge.export_tools():
            clean.append({"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]})
        return clean

    async def ainvoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        bridge = self._ensure_bridge()
        if bridge is None:
            return {"success": False, "error": self.bridge_error or "apple music bridge unavailable"}
        return await bridge.ainvoke_tool(tool_name, arguments)

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        bridge = self._ensure_bridge()
        if bridge is None:
            return {"success": False, "error": self.bridge_error or "apple music bridge unavailable"}
        return asyncio.run(bridge.ainvoke_tool(tool_name, arguments))

    def register(self, _mcp: Any) -> None:
        return None
