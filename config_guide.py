from __future__ import annotations

import os
import sys
from pathlib import Path

_CATALOG_COMPONENTS = {
    "exa": {
        "description": "Exa web search (AI-powered neural search)",
        "platforms": ["Windows", "Linux", "MacOs"],
        "role": "server",
        "config_help": "An Exa API key is required. Get one at https://dashboard.exa.ai",
        "config_defaults": {
            "api_key": "",
            "base_url": "https://api.exa.ai",
        },
    },
    "clipboard": {
        "description": "Clipboard read/write (rich text support)",
        "platforms": ["Windows"],
        "role": "client",
        "config_help": "No configuration needed.",
        "config_defaults": {},
    },
    "windows_manager": {
        "description": "Window/application management (list, focus, close)",
        "platforms": ["Windows"],
        "role": "client",
        "config_help": "No configuration needed.",
        "config_defaults": {},
    },
    "apple_music_macos": {
        "description": "Apple Music control on macOS",
        "platforms": ["MacOs"],
        "role": "client",
        "config_help": "Auto-bootstraps the Apple Music MCP bridge.",
        "config_defaults": {
            "enabled": "true",
            "install_dir": "~/.xiaozhi/applemusic-mcp",
            "update_on_startup": "true",
        },
    },
    "local_schedule": {
        "description": "Local SQLite-backed schedule/calendar manager",
        "platforms": ["Windows", "Linux", "MacOs"],
        "role": "both",
        "config_help": "No configuration needed. DB is auto-created.",
        "config_defaults": {},
    },
}


def _platform_key() -> str:
    if os.name == "nt":
        return "Windows"
    if sys.platform == "darwin":
        return "MacOs"
    return "Linux"


def _input_str(prompt: str, default: str = "") -> str:
    if default:
        display = f"{prompt} [{default}]: "
    else:
        display = f"{prompt}: "
    value = input(display).strip()
    return value or default


def _input_bool(prompt: str, default: bool = True) -> bool:
    suffix = " (Y/n)" if default else " (y/N)"
    value = input(f"{prompt}{suffix}: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "1", "true"}


def _intro() -> None:
    print("=" * 56)
    print("  Xiaozhi MCP — Interactive Configuration Setup")
    print("=" * 56)
    print()
    print("This wizard will help you create a config.toml file.")
    print("Press Enter to accept defaults.")
    print()


def _ask_role() -> str:
    print("─" * 40)
    print("Step 1: Choose Runtime Role")
    print()
    print("  server — connects to Xiaozhi endpoint, serves tools to AI")
    print("  client — connects to a server, extends it with local tools")
    print("  auto   — detect from your config settings")
    print()
    while True:
        role = _input_str("Role", "server").lower()
        if role in ("server", "client", "auto"):
            return role
        print("  Please enter: server, client, or auto")


def _ask_server_config() -> dict[str, str]:
    print()
    print("─" * 40)
    print("Step 2a: Server Settings")
    print()
    print("The Xiaozhi endpoint URL with your token:")
    print('  Example: wss://api.xiaozhi.me/mcp/?token=YOUR_TOKEN')
    print()
    endpoint = _input_str("Endpoint URL")
    print()
    print("Optional: enable cluster mode to accept client connections?")
    cluster = _input_bool("Enable cluster", default=False)
    cluster_config = {}
    if cluster:
        print()
        cluster_config["listen_host"] = _input_str("Cluster listen host", "0.0.0.0")
        cluster_config["listen_port"] = _input_str("Cluster listen port", "18888")
        cluster_config["client_token"] = _input_str("Cluster shared token")
    return {
        "xiaozhi.endpoint": endpoint,
        "cluster.enabled": "true" if cluster else "false",
        **{f"cluster.{k}": v for k, v in cluster_config.items()},
    }


def _ask_client_config() -> dict[str, str]:
    print()
    print("─" * 40)
    print("Step 2b: Client Settings")
    print()
    server_url = _input_str("Server WebSocket URL", "ws://localhost:18888/agent")
    import socket

    node_id = _input_str("Node ID (unique name for this machine)", socket.gethostname())
    client_token = _input_str("Client shared token")
    return {
        "client.server_url": server_url,
        "client.node_id": node_id,
        "client.client_token": client_token,
    }


def _ask_components(role: str) -> list[str]:
    platform = _platform_key()
    print()
    print("─" * 40)
    print(f"Step 3: Components (detected platform: {platform})")
    print()

    available = []
    for name, info in _CATALOG_COMPONENTS.items():
        if platform not in info["platforms"]:
            continue
        role_ok = info["role"] == "both" or role == "auto" or info["role"] == role
        if not role_ok:
            continue
        available.append(name)

    if not available:
        print("  No components available for this platform+role combination.")
        return []

    print("  Available components for your setup:")
    for name in available:
        info = _CATALOG_COMPONENTS[name]
        print(f"    [{name}] {info['description']}")
        print(f"           {info['config_help']}")
        print()

    selected = []
    for name in available:
        if _input_bool(f"Enable {name}", default=True):
            selected.append(name)

    return selected


def _ask_component_config(selected: list[str]) -> dict[str, dict[str, str]]:
    configs: dict[str, dict[str, str]] = {}
    for name in selected:
        info = _CATALOG_COMPONENTS[name]
        defaults = info.get("config_defaults", {})
        if not defaults:
            configs[name] = {}
            continue
        print()
        print(f"  Configuring [{name}]:")
        comp_config: dict[str, str] = {}
        for key, default in defaults.items():
            value = _input_str(f"    {key}", str(default))
            comp_config[key] = value
        configs[name] = comp_config
    return configs


def _generate_toml(
    role: str,
    server_config: dict[str, str],
    client_config: dict[str, str],
    selected: list[str],
    comp_configs: dict[str, dict[str, str]],
) -> str:
    lines: list[str] = []
    lines.append("# xiaozhiMCP configuration")
    lines.append("# Generated by 'xiaozhimcp init'")
    lines.append("")

    lines.append("[xiaozhi]")
    if "xiaozhi.endpoint" in server_config:
        lines.append(f'endpoint = "{server_config["xiaozhi.endpoint"]}"')
    else:
        lines.append('endpoint = "wss://api.xiaozhi.me/mcp/?token=replace_with_your_token"')
    lines.append('server_script = "app_server.py"')
    lines.append("")

    if role in ("server", "auto"):
        lines.append("[cluster]")
        lines.append(f'enabled = {server_config.get("cluster.enabled", "false")}')
        if server_config.get("cluster.enabled") == "true":
            for k in ("listen_host", "listen_port", "client_token"):
                sub = f"cluster.{k}"
                if sub in server_config:
                    lines.append(f'{k} = "{server_config[sub]}"')
        lines.append("")

    if role in ("client", "auto"):
        lines.append("[client]")
        for k in ("server_url", "node_id", "client_token"):
            lines.append(f'{k} = "{client_config.get(f"client.{k}", "")}"')
        lines.append("")

    lines.append("[catalog]")
    lines.append('repo_url = "https://github.com/iiishop/xiaozhiMCP-components.git"')
    lines.append('branch = "main"')
    lines.append('timeout_seconds = 20')
    lines.append("")

    lines.append("[components]")
    lines.append('folder = "components"')
    lines.append("")

    for name in selected:
        cfg = comp_configs.get(name, {})
        lines.append(f"[{name}]")
        if cfg:
            for k, v in cfg.items():
                if v.lower() in ("true", "false"):
                    lines.append(f"{k} = {v.lower()}")
                elif v.isdigit():
                    lines.append(f"{k} = {v}")
                else:
                    lines.append(f'{k} = "{v}"')
        lines.append("")

    return "\n".join(lines)


def interactive_setup() -> str | None:
    _intro()
    role = _ask_role()

    server_config: dict[str, str] = {}
    client_config: dict[str, str] = {}

    if role == "server":
        server_config = _ask_server_config()
    elif role == "client":
        client_config = _ask_client_config()
    else:
        use_server = _input_bool("Use server role (has xiaozhi endpoint)?", default=True)
        if use_server:
            server_config = _ask_server_config()
        use_client = _input_bool("Also use client role (connect to cluster)?", default=False)
        if use_client:
            client_config = _ask_client_config()

    selected = _ask_components(role)
    comp_configs = _ask_component_config(selected)

    toml_content = _generate_toml(role, server_config, client_config, selected, comp_configs)

    print()
    print("─" * 40)
    print("Preview of generated config.toml:")
    print("─" * 40)
    print(toml_content)
    print("─" * 40)

    if not _input_bool("Save this config?", default=True):
        print("Cancelled.")
        return None

    config_dir = Path.home() / ".xiaozhimcp"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"

    config_path.write_text(toml_content, encoding="utf-8")
    return str(config_path)
