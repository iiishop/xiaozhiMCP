from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from cluster import ClusterClient, ClusterServer
from config_loader import get_nested_str, load_config
from error_store import ErrorStore
from runtime import detect_platform, load_components_from_package_folder, load_user_components


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Xiaozhi MCP node (server/client)")
    parser.add_argument("--config", default="config.toml", help="config file path (.toml), default: config.toml")
    parser.add_argument("--role", choices=["server", "client"], default="server", help="node role")
    return parser.parse_args()


def collect_components(config: dict[str, Any]) -> list[Any]:
    components = load_components_from_package_folder("components", config)

    user_folder = get_nested_str(config, "components", "folder") or "user_components"
    base_folder = Path("components").resolve()
    configured_folder = Path(user_folder).resolve()
    if configured_folder != base_folder:
        user_components = load_user_components(user_folder, config)
        components.extend(user_components)
    return components


def register_components(mcp: FastMCP, config: dict[str, Any]) -> list[Any]:
    components = collect_components(config)
    for component in components:
        component.register(mcp)
    return components


def filter_components_by_role(components: list[Any], role: str) -> list[Any]:
    out: list[Any] = []
    for component in components:
        supports = getattr(component, "supports_role", None)
        if callable(supports):
            if bool(supports(role)):
                out.append(component)
            continue
        out.append(component)
    return out


def collect_exported_tools(components: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    invokers: dict[str, Any] = {}

    for component in components:
        for tool in component.export_tools():
            name = str(tool.get("name", "")).strip()
            if not name:
                continue
            if name in invokers:
                raise RuntimeError(f"duplicate local tool name: {name}")
            invokers[name] = component
            tools.append(tool)

    return tools, invokers


async def run_server(config_path: str) -> None:
    config = load_config(config_path)
    mcp = FastMCP("XiaozhiExtensions")
    components = filter_components_by_role(collect_components(config), "server")
    for component in components:
        component.register(mcp)
    local_tools, _ = collect_exported_tools(components)
    error_store = ErrorStore(get_nested_str(config, "logmcp", "db_path") or None)

    cluster_enabled = (get_nested_str(config, "cluster", "enabled") or "").lower() in {"1", "true", "yes", "on"}
    cluster_server = None
    if cluster_enabled:
        host = get_nested_str(config, "cluster", "listen_host") or "0.0.0.0"
        port = int(get_nested_str(config, "cluster", "listen_port") or "18888")
        token = get_nested_str(config, "cluster", "client_token")
        if token:
            cluster_server = ClusterServer(host=host, port=port, client_token=token, error_store=error_store)
            await cluster_server.set_reserved_tool_names(
                {str(t.get("name", "")).strip() for t in local_tools if str(t.get("name", "")).strip()}
            )
            await cluster_server.start()

            for component in components:
                setter = getattr(component, "set_remote_invoker", None)
                if callable(setter):
                    setter(cluster_server.invoke_remote_tool)

            @mcp.tool()
            async def cluster_list_remote_tools() -> dict:
                """List all tools registered by connected remote clients."""
                tools = await cluster_server.registry.list_remote_tools()
                return {"success": True, "count": len(tools), "tools": tools}

            @mcp.tool()
            async def cluster_list_clients() -> dict:
                """List connected clients with node_id, platform and tool count."""
                clients = await cluster_server.registry.list_clients()
                return {"success": True, "count": len(clients), "clients": clients}

            @mcp.tool()
            async def cluster_list_client_tools(node_id: str) -> dict:
                """List MCP tools installed on a specific client by node_id."""
                clients = await cluster_server.registry.list_clients()
                exists = any(str(item.get("node_id", "")) == str(node_id) for item in clients)
                if not exists:
                    return {"success": False, "error": f"client not found: {node_id}", "node_id": node_id}
                tools = await cluster_server.registry.list_tools_by_node(str(node_id))
                return {"success": True, "node_id": node_id, "count": len(tools), "tools": tools}

            @mcp.tool()
            async def cluster_call_remote_tool(tool_name: str, arguments_json: str = "{}") -> dict:
                """Call a remote client tool by exact unique tool_name."""
                import json

                try:
                    args = json.loads(arguments_json) if arguments_json.strip() else {}
                    if not isinstance(args, dict):
                        return {"success": False, "error": "arguments_json must decode to JSON object"}
                except Exception as exc:  # noqa: BLE001
                    return {"success": False, "error": f"invalid arguments_json: {exc}"}

                return await cluster_server.invoke_remote_tool(tool_name, args)

    await mcp.run_stdio_async()


async def run_client(config_path: str) -> None:
    config = load_config(config_path)
    components = filter_components_by_role(collect_components(config), "client")
    declared_tools, invokers = collect_exported_tools(components)

    async def invoker(tool_name: str, args: dict[str, Any]) -> dict:
        component = invokers.get(tool_name)
        if component is None:
            raise RuntimeError(f"tool not supported in client: {tool_name}")
        if hasattr(component, "ainvoke_tool"):
            return await component.ainvoke_tool(tool_name, args)
        return component.invoke_tool(tool_name, args)

    server_url = get_nested_str(config, "client", "server_url")
    node_id = get_nested_str(config, "client", "node_id")
    token = get_nested_str(config, "client", "client_token")
    if not server_url or not node_id or not token:
        raise RuntimeError("client mode requires client.server_url, client.node_id, client.client_token")

    client = ClusterClient(
        server_url=server_url,
        node_id=node_id,
        client_token=token,
        platform=detect_platform(),
        tools=declared_tools,
    )
    await client.run_forever(invoker)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    args = parse_args()
    try:
        if args.role == "server":
            asyncio.run(run_server(args.config))
        else:
            asyncio.run(run_client(args.config))
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("app_server").exception("Fatal error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
