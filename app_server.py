from __future__ import annotations

import argparse
import logging

from mcp.server.fastmcp import FastMCP

from components import ExaSearchComponent, LocalScheduleComponent
from config_loader import get_nested_str, load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local MCP server with pluggable components")
    parser.add_argument(
        "--config",
        default="config.toml",
        help="config file path (.toml), default: config.toml",
    )
    return parser.parse_args()


def build_server(config_path: str) -> FastMCP:
    config = load_config(config_path)

    mcp = FastMCP("XiaozhiExtensions")

    components = [
        ExaSearchComponent(
            api_key=get_nested_str(config, "exa", "api_key"),
            base_url=get_nested_str(config, "exa", "base_url"),
        ),
        LocalScheduleComponent(
            db_path=get_nested_str(config, "schedule", "db_path") or None,
        ),
    ]

    for component in components:
        component.register(mcp)

    return mcp


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    args = parse_args()
    build_server(args.config).run(transport="stdio")
