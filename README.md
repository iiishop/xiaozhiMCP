# Xiaozhi MCP Node

Single-command MCP node for Xiaozhi. Two runtime roles from one CLI entrypoint:

- **server** — serves MCP tools over stdio (this is the default process started by `xiaozhimcp`)
- **client** — connects to a server over WebSocket, extends it with local tools

## Quick Start

```bash
# Install
uv sync

# Interactive setup (recommended for new users)
uv run xiaozhimcp init

# Run — auto-detects role and config
uv run xiaozhimcp
```

By default, `xiaozhimcp` launches `app_server.py` and auto-selects `server` or `client` role from config.

## Usage

```bash
# Auto-detect role from config
xiaozhimcp

# Explicit role
xiaozhimcp server
xiaozhimcp client

# Use a specific config file
xiaozhimcp --config /path/to/config.toml
xiaozhimcp server --config /path/to/config.toml
```

The CLI auto-finds `config.toml` by checking:
1. `config.toml` in the current directory
2. `~/.xiaozhimcp/config.toml`

If neither exists, it tells you to run `xiaozhimcp init`.

## Configuration

### Interactive setup (recommended)
```bash
xiaozhimcp init
```
Walks you through role, endpoint, component selection, and generates a validated `config.toml`.

### Manual setup
```bash
cp config.example.toml config.toml
# edit config.toml
```

`config.example.toml` is included in package builds, so this works both from source and after installation.

### Key sections

| Section | Role | Purpose |
|---------|------|---------|
| `[xiaozhi]` | server | Xiaozhi endpoint URL + token |
| `[cluster]` | server | Accept client node connections |
| `[client]` | client | Connect to a cluster server |
| `[components]` | both | Additional user component folder (with `components/` always loaded) |

### Components

`./components` is always scanned on startup and is the default install target for catalog-installed components. `[components].folder` can point to an additional user folder; when it differs from `components`, both locations are scanned. Each component needs a `[component_name]` section in `config.toml` only if it requires configuration:

| Component | Role | Platform | Needs Config? |
|-----------|------|----------|----------------|
| exa | server | all | Yes (API key) |
| logmcp | server | all | Optional (db_path) |
| apple_music_macos | client | macOS | Optional |
| clipboard | client | Windows | No |
| windows_manager | client | Windows | No |
| local_schedule | both | all | No |

Run `xiaozhimcp init` to configure each component interactively with explanations.

## Run as Server

```bash
xiaozhimcp server
# or just: xiaozhimcp (auto-detected)
```

Implementation detail: this path executes `app_server.py --role server`.

## Run as Client

```bash
xiaozhimcp client
```

Client registers its local tools to the server and auto-reconnects on disconnect.

Implementation detail: this path executes `app_server.py --role client`.

## Legacy Router Entry

`mcp_router.py` remains available as a legacy bridge command (`uv run start`) that connects Xiaozhi endpoint <-> local stdio server process. The recommended runtime entrypoint is `xiaozhimcp`.

## Built-in tools (server role)

Core tools registered directly in `app_server.py` — always available regardless of installed components:

### Catalog management
- `catalog_list_components()`
- `catalog_search_components(query, fuzzy, readme, platform)`
- `catalog_describe_component(component_name)`
- `catalog_get_component_readme(component_name)`
- `catalog_get_component_platforms(component_name)`
- `catalog_install_component_to_server(component_name)`
- `catalog_install_component_to_client(component_name, node_id, mode="client_pull")`

### Error logging
- `logmcp_get_errors(limit=50)`

### Component tools

Additional tools are provided by components installed from catalog into `components/` (auto-discovered on startup) or via `catalog_install_component_to_server()`. See the [xiaozhiMCP-components](https://github.com/iiishop/xiaozhiMCP-components) repository for available components and their READMEs.

## Components Convention

Components are defined in the `xiaozhiMCP-components` repository. See its [README](https://github.com/iiishop/xiaozhiMCP-components) for the full component specification.

Each component README must end with:

`Platforms: Windows|Linux|MacOs`

Examples:
- Cross-platform: `Platforms: Windows|Linux|MacOs`
- macOS only: `Platforms: MacOs`

## Cluster tools (server role, when `[cluster].enabled=true`)

- `cluster_list_clients()`
- `cluster_list_client_tools(node_id)`
- `cluster_list_remote_tools()`
- `cluster_call_remote_tool(tool_name, arguments_json)`

## Notes

- Tool names must be globally unique across server + all clients.
- `config.toml` contains secrets/tokens — do not commit it.
- Logs are plain text for CLI deployment.

## Apple Music (macOS only)

Add to `config.toml` on your macOS client:

```toml
[apple_music_macos]
enabled = true
install_dir = "~/.xiaozhi/applemusic-mcp"
update_on_startup = true
```

Before enabling `[apple_music_macos]`, install `apple_music_macos` from catalog (`xiaozhiMCP-components`) using catalog tools or `xiaozhimcp init`.
