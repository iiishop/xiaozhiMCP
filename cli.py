from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from app_server import main as app_server_main
from config_loader import get_nested_str, load_config

logger = logging.getLogger("xiaozhimcp")

DEFAULT_CONFIG_PATHS = [
    "config.toml",
    str(Path.home() / ".xiaozhimcp" / "config.toml"),
]


def _find_config() -> str | None:
    for path in DEFAULT_CONFIG_PATHS:
        if Path(path).exists():
            return path
    return None


def _detect_role_from_config(config: dict[str, Any]) -> str:
    client_server_url = get_nested_str(config, "client", "server_url")
    client_node_id = get_nested_str(config, "client", "node_id")
    client_token = get_nested_str(config, "client", "client_token")
    if client_server_url and client_node_id and client_token:
        return "client"

    cluster_enabled = (get_nested_str(config, "cluster", "enabled") or "").lower() in {"1", "true", "yes", "on"}
    if cluster_enabled:
        return "server"

    return "server"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xiaozhimcp",
        description="Xiaozhi MCP node — single-command launch for server or client",
    )
    sub = parser.add_subparsers(dest="command", help="subcommand")

    server_parser = sub.add_parser("server", help="run as server (connect to xiaozhi endpoint)")
    server_parser.add_argument("--config", default=None, help="config file path (.toml)")

    client_parser = sub.add_parser("client", help="run as client (connect to cluster server)")
    client_parser.add_argument("--config", default=None, help="config file path (.toml)")

    sub.add_parser("init", help="interactive guided config setup")

    parser.add_argument(
        "--config",
        default=None,
        help="config file path (.toml), auto-detected if omitted",
    )
    return parser


def cmd_init() -> int:
    from config_guide import interactive_setup

    config_path = interactive_setup()
    if config_path:
        print(f"\nConfig saved to: {config_path}")
        print("You can now run: xiaozhimcp")
        return 0
    return 1


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "init":
        return cmd_init()

    config_path = args.config or _find_config()

    if not config_path:
        print("No config.toml found.")
        print("Run 'xiaozhimcp init' to create one interactively, or")
        print("copy config.example.toml to config.toml and edit it.")
        print(f"\nLooked in: {', '.join(DEFAULT_CONFIG_PATHS)}")
        return 2

    config = load_config(config_path)

    if args.command in ("server", "client"):
        role = args.command
    else:
        role = _detect_role_from_config(config)
        logger.info("auto-detected role: %s (use 'xiaozhimcp server' or 'xiaozhimcp client' to override)", role)

    sys.argv = ["xiaozhimcp", "--role", role, "--config", config_path]
    return app_server_main()


if __name__ == "__main__":
    raise SystemExit(main())
