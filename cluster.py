from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

import websockets

from error_store import ErrorStore

logger = logging.getLogger("cluster")


@dataclass
class RemoteTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    node_id: str


@dataclass
class ClientSession:
    node_id: str
    websocket: Any
    platform: str
    tools: dict[str, RemoteTool] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)
    pending: dict[str, asyncio.Future] = field(default_factory=dict)


class ClientRegistry:
    def __init__(self) -> None:
        self._clients: dict[str, ClientSession] = {}
        self._tools: dict[str, str] = {}
        self._reserved_tool_names: set[str] = set()
        self._lock = asyncio.Lock()

    async def set_reserved_tool_names(self, names: set[str]) -> None:
        async with self._lock:
            self._reserved_tool_names = {name for name in names if name}

    async def register(
        self,
        *,
        node_id: str,
        websocket: Any,
        platform: str,
        tools: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        async with self._lock:
            new_tools: dict[str, RemoteTool] = {}
            for tool in tools:
                name = str(tool.get("name", "")).strip()
                if not name:
                    return False, "tool name missing"
                if name in self._reserved_tool_names:
                    return False, f"tool name conflict with server local tool: {name}"
                if name in self._tools and self._tools[name] != node_id:
                    return False, f"tool name conflict: {name}"
                new_tools[name] = RemoteTool(
                    name=name,
                    description=str(tool.get("description", "")),
                    input_schema=tool.get("input_schema", {}) if isinstance(tool.get("input_schema", {}), dict) else {},
                    node_id=node_id,
                )

            # cleanup old mappings for this node
            old = self._clients.get(node_id)
            if old:
                for tname in old.tools:
                    self._tools.pop(tname, None)

            for tname in new_tools:
                self._tools[tname] = node_id

            self._clients[node_id] = ClientSession(
                node_id=node_id,
                websocket=websocket,
                platform=platform,
                tools=new_tools,
                last_seen=time.time(),
            )

            return True, "ok"

    async def unregister(self, node_id: str) -> None:
        async with self._lock:
            item = self._clients.pop(node_id, None)
            if not item:
                return
            for fut in item.pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("client disconnected"))
            for tname in item.tools:
                self._tools.pop(tname, None)

    async def heartbeat(self, node_id: str) -> None:
        async with self._lock:
            if node_id in self._clients:
                self._clients[node_id].last_seen = time.time()

    async def route_tool(self, tool_name: str) -> ClientSession | None:
        async with self._lock:
            node_id = self._tools.get(tool_name)
            if not node_id:
                return None
            return self._clients.get(node_id)

    async def bind_pending(self, node_id: str, req_id: str, future: asyncio.Future) -> bool:
        async with self._lock:
            session = self._clients.get(node_id)
            if not session:
                return False
            session.pending[req_id] = future
            return True

    async def take_pending(self, node_id: str, req_id: str) -> asyncio.Future | None:
        async with self._lock:
            session = self._clients.get(node_id)
            if not session:
                return None
            return session.pending.pop(req_id, None)

    async def list_remote_tools(self) -> list[dict[str, Any]]:
        async with self._lock:
            out: list[dict[str, Any]] = []
            for node in self._clients.values():
                for tool in node.tools.values():
                    out.append(
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "node_id": tool.node_id,
                            "platform": node.platform,
                        }
                    )
            out.sort(key=lambda x: x["name"])
            return out

    async def list_clients(self) -> list[dict[str, Any]]:
        async with self._lock:
            out: list[dict[str, Any]] = []
            for node in self._clients.values():
                out.append(
                    {
                        "node_id": node.node_id,
                        "platform": node.platform,
                        "tool_count": len(node.tools),
                        "last_seen": int(node.last_seen),
                    }
                )
            out.sort(key=lambda x: x["node_id"])
            return out

    async def list_tools_by_node(self, node_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            node = self._clients.get(node_id)
            if node is None:
                return []
            out: list[dict[str, Any]] = []
            for tool in node.tools.values():
                out.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                        "node_id": tool.node_id,
                    }
                )
            out.sort(key=lambda x: x["name"])
            return out


class ClusterServer:
    def __init__(self, host: str, port: int, client_token: str, error_store: ErrorStore | None = None) -> None:
        self.host = host
        self.port = port
        self.client_token = client_token
        self.registry = ClientRegistry()
        self._server = None
        self.error_store = error_store

    def _log_known_error(self, error_code: str, message: str, conclusion: str) -> None:
        if self.error_store is not None:
            self.error_store.add_known("cluster", error_code, message, conclusion)

    def _log_unknown_error(self, message: str, detail: str) -> None:
        if self.error_store is not None:
            self.error_store.add_unknown("cluster", message, detail)

    async def set_reserved_tool_names(self, names: set[str]) -> None:
        await self.registry.set_reserved_tool_names(names)

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle_connection, self.host, self.port, max_size=2**20)
        logger.info("Cluster server listening on ws://%s:%d/agent", self.host, self.port)

    async def _handle_connection(self, websocket: Any) -> None:
        node_id = ""
        try:
            raw = await websocket.recv()
            hello = json.loads(raw)
            if not isinstance(hello, dict) or hello.get("type") != "register":
                self._log_known_error(
                    "INVALID_REGISTER_PACKET",
                    "first packet must be register",
                    "Client must send type=register as the first websocket message.",
                )
                await websocket.send(json.dumps({"type": "error", "message": "first packet must be register"}))
                return

            token = str(hello.get("client_token", ""))
            if token != self.client_token:
                self._log_known_error(
                    "UNAUTHORIZED_CLIENT",
                    "unauthorized",
                    "Client token mismatch. Ensure client.client_token equals server cluster.client_token.",
                )
                await websocket.send(json.dumps({"type": "error", "message": "unauthorized"}))
                return

            node_id = str(hello.get("node_id", "")).strip()
            if not node_id:
                self._log_known_error(
                    "MISSING_NODE_ID",
                    "node_id required",
                    "Client must provide a unique node_id in register message.",
                )
                await websocket.send(json.dumps({"type": "error", "message": "node_id required"}))
                return

            ok, msg = await self.registry.register(
                node_id=node_id,
                websocket=websocket,
                platform=str(hello.get("platform", "unknown")),
                tools=hello.get("tools", []) if isinstance(hello.get("tools", []), list) else [],
            )
            if not ok:
                if msg.startswith("tool name conflict with server local tool:"):
                    self._log_known_error(
                        "CLIENT_TOOL_CONFLICT_WITH_SERVER",
                        msg,
                        "Server local MCP/tool has higher priority. Rename client MCP/tool to a unique name.",
                    )
                elif msg.startswith("tool name conflict:"):
                    self._log_known_error(
                        "CLIENT_TOOL_CONFLICT",
                        msg,
                        "Multiple clients registered the same MCP/tool name. Keep client MCP/tool names globally unique.",
                    )
                else:
                    self._log_known_error("CLIENT_REGISTER_REJECTED", msg, "Fix registration payload and retry.")
                await websocket.send(json.dumps({"type": "error", "message": msg}))
                return

            await websocket.send(json.dumps({"type": "register_ack", "ok": True}))
            tool_names = sorted(list(self._clients_tools_preview(hello.get("tools", []))))
            logger.info(
                "Client registered: node_id=%s platform=%s tools=%d names=%s",
                node_id,
                str(hello.get("platform", "unknown")),
                len(tool_names),
                ",".join(tool_names),
            )

            async for message in websocket:
                payload = json.loads(message)
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") == "heartbeat":
                    await self.registry.heartbeat(node_id)
                    await websocket.send(json.dumps({"type": "heartbeat_ack", "ts": time.time()}))
                    continue
                if payload.get("type") == "invoke_result":
                    req_id = str(payload.get("id", ""))
                    future = await self.registry.take_pending(node_id, req_id)
                    if future and not future.done():
                        future.set_result(payload)
        except Exception as exc:  # noqa: BLE001
            logger.info("Client disconnected: %s (%s)", node_id or "unknown", exc)
            self._log_unknown_error(str(exc), traceback.format_exc())
        finally:
            if node_id:
                await self.registry.unregister(node_id)

    @staticmethod
    def _clients_tools_preview(tools: Any) -> set[str]:
        out: set[str] = set()
        if not isinstance(tools, list):
            return out
        for item in tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if name:
                out.add(name)
        return out

    async def invoke_remote_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        session = await self.registry.route_tool(tool_name)
        if not session:
            return {"success": False, "error": f"remote tool not found: {tool_name}"}

        req_id = f"req-{int(time.time() * 1000)}"
        req = {
            "type": "invoke",
            "id": req_id,
            "tool": tool_name,
            "arguments": arguments,
        }
        try:
            future: asyncio.Future = asyncio.get_running_loop().create_future()
            ok = await self.registry.bind_pending(session.node_id, req_id, future)
            if not ok:
                return {"success": False, "error": "target client offline"}
            await session.websocket.send(json.dumps(req))
            resp = await asyncio.wait_for(future, timeout=30)
            if isinstance(resp, dict) and resp.get("type") == "invoke_result" and resp.get("id") == req_id:
                return {
                    "success": bool(resp.get("success", False)),
                    "node_id": session.node_id,
                    "result": resp.get("result"),
                    "error": resp.get("error", ""),
                }
            return {"success": False, "error": "invalid invoke response"}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}
        finally:
            future = await self.registry.take_pending(session.node_id, req_id)
            if future and not future.done():
                future.cancel()


class ClusterClient:
    def __init__(self, server_url: str, node_id: str, client_token: str, platform: str, tools: list[dict[str, Any]]) -> None:
        self.server_url = server_url
        self.node_id = node_id
        self.client_token = client_token
        self.platform = platform
        self.tools = tools

    async def run_forever(self, invoker: Any) -> None:
        while True:
            try:
                async with websockets.connect(self.server_url, max_size=2**20, ping_interval=20, ping_timeout=20) as ws:
                    reg = {
                        "type": "register",
                        "node_id": self.node_id,
                        "client_token": self.client_token,
                        "platform": self.platform,
                        "tools": self.tools,
                    }
                    await ws.send(json.dumps(reg))
                    ack = json.loads(await ws.recv())
                    if not isinstance(ack, dict) or ack.get("type") != "register_ack":
                        raise RuntimeError(f"register failed: {ack}")

                    logger.info("Connected to cluster server: %s", self.server_url)
                    hb = asyncio.create_task(self._heartbeat_loop(ws))
                    try:
                        async for raw in ws:
                            msg = json.loads(raw)
                            if not isinstance(msg, dict):
                                continue
                            if msg.get("type") != "invoke":
                                continue
                            req_id = str(msg.get("id", ""))
                            tool_name = str(msg.get("tool", ""))
                            args = msg.get("arguments", {}) if isinstance(msg.get("arguments", {}), dict) else {}
                            try:
                                result = await invoker(tool_name, args)
                                payload = {"type": "invoke_result", "id": req_id, "success": True, "result": result}
                            except Exception as exc:  # noqa: BLE001
                                payload = {"type": "invoke_result", "id": req_id, "success": False, "error": str(exc)}
                            await ws.send(json.dumps(payload))
                    finally:
                        hb.cancel()
                        await asyncio.gather(hb, return_exceptions=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Cluster client reconnecting in 3s: %s", exc)
                await asyncio.sleep(3)

    async def _heartbeat_loop(self, ws: Any) -> None:
        while True:
            await asyncio.sleep(10)
            await ws.send(json.dumps({"type": "heartbeat", "node_id": self.node_id}))
