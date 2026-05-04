# Xiaozhi MCP Node

CLI-first MCP adapter for Xiaozhi with two runtime roles:

- `server`: connects to Xiaozhi endpoint and serves tools
- `client`: connects to a server over WebSocket and extends server capabilities

Both roles run from the same codebase.

## Install

```bash
uv sync
```

## Configuration

Create config file:

```bash
cp config.example.toml config.toml
```

Key sections:

- `[xiaozhi]`: Xiaozhi endpoint and server script for `mcp_router.py`
- `[cluster]`: server-side WebSocket listener for client nodes
- `[client]`: client-side connection settings
- `[components]`: folder path for user-provided components

Catalog install defaults to the folder configured by `[components].folder` unless `[catalog].install_folder` is explicitly set.

`user_components/` is ignored by git by design. Put custom components there.

## Run as Server

Use the existing Xiaozhi router (server role is default):

```bash
uv run start --config config.toml
```

Or directly:

```bash
uv run python app_server.py --role server --config config.toml
```

## Run as Client

On Windows/macOS/Linux client node:

```bash
uv run python app_server.py --role client --config config.toml
```

Client will register tools to server using WebSocket (`client.server_url`) and keep reconnecting.

## Built-in tools (server role)

- `exa_web_search(...)`
- `catalog_list_components()`
- `catalog_search_components(query="", fuzzy=true, readme=false, platform="")`
- `catalog_describe_component(component_name)`
- `catalog_get_component_readme(component_name)`
- `catalog_get_component_platforms(component_name)`
- `catalog_install_component_to_server(component_name)`
- `catalog_install_component_to_client(component_name, node_id, mode="client_pull")`
- `logmcp_get_errors(limit=50)`

## Components Repository README Rule

Each MCP folder README in `xiaozhiMCP-components` should end with this exact final line:

`Platforms: Windows|Linux|MacOs`

Examples:

- Cross-platform: `Platforms: Windows|Linux|MacOs`
- macOS only: `Platforms: MacOs`

## Cluster tools (server role, when `[cluster].enabled=true`)

- `cluster_list_clients()`
- `cluster_list_client_tools(node_id)`
- `cluster_list_remote_tools()`
- `cluster_call_remote_tool(tool_name, arguments_json="{}")`

## Notes

- Tool names must be globally unique across server + clients.
- `config.toml` is ignored and should hold secrets/tokens.
- Logs are plain text and intended for CLI deployment.
