from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import requests

from ..base import MCPComponent


def _parse_github_repo(repo_url: str) -> tuple[str, str]:
    text = (repo_url or "").strip().removesuffix(".git")
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+)$", text)
    if not m:
        raise ValueError("invalid github repo url")
    return m.group(1), m.group(2)


class AgentInstallerComponent(MCPComponent):
    def __init__(self, node_id: str, install_folder: str, timeout_seconds: int = 20) -> None:
        self.node_id = node_id
        self.install_folder = install_folder
        self.timeout_seconds = max(5, int(timeout_seconds))
        self.tool_name = f"agent_install_component__{self.node_id}"

    def supports_role(self, role: str) -> bool:
        return role == "client"

    def _raw_url(self, owner: str, repo: str, branch: str, path: str) -> str:
        p = path.lstrip("/")
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{p}"

    def _get_json(self, url: str) -> Any:
        resp = requests.get(url, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def _get_text(self, url: str) -> str:
        resp = requests.get(url, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.text

    def _resolve_component_meta(self, repo_url: str, branch: str, component_name: str) -> dict[str, str]:
        owner, repo = _parse_github_repo(repo_url)
        index_url = self._raw_url(owner, repo, branch, "index.json")
        data = self._get_json(index_url)
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                if str(item.get("name", "")).strip() == component_name:
                    return {
                        "owner": owner,
                        "repo": repo,
                        "path": str(item.get("path", component_name)),
                        "entry": str(item.get("entry", "component.py")),
                        "readme": str(item.get("readme", "README.md")),
                    }
        return {
            "owner": owner,
            "repo": repo,
            "path": component_name,
            "entry": "component.py",
            "readme": "README.md",
        }

    def _install(self, component_name: str, repo_url: str, branch: str) -> dict[str, Any]:
        meta = self._resolve_component_meta(repo_url=repo_url, branch=branch, component_name=component_name)
        owner = meta["owner"]
        repo = meta["repo"]
        rel_path = meta["path"].strip("/")
        entry = meta["entry"].strip("/")
        readme = meta["readme"].strip("/")

        entry_text = self._get_text(self._raw_url(owner, repo, branch, f"{rel_path}/{entry}"))
        readme_text = self._get_text(self._raw_url(owner, repo, branch, f"{rel_path}/{readme}"))

        install_root = Path(self.install_folder)
        target_dir = install_root / component_name
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "component.py").write_text(entry_text, encoding="utf-8")
        (target_dir / "README.md").write_text(readme_text, encoding="utf-8")
        if not (target_dir / "__init__.py").exists():
            (target_dir / "__init__.py").write_text("", encoding="utf-8")

        return {"success": True, "component_name": component_name, "installed_to": str(target_dir), "node_id": self.node_id}

    def export_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": self.tool_name,
                "description": "Client-side installer tool used by server catalog client_pull mode.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "component_name": {"type": "string"},
                        "node_id": {"type": "string"},
                        "repo_url": {"type": "string"},
                        "branch": {"type": "string"},
                    },
                    "required": ["component_name", "node_id", "repo_url", "branch"],
                },
            }
        ]

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        if tool_name != self.tool_name:
            raise RuntimeError(f"unknown tool: {tool_name}")
        if str(arguments.get("node_id", "")) != self.node_id:
            return {"success": False, "error": "node_id mismatch"}
        return self._install(
            component_name=str(arguments.get("component_name", "")).strip(),
            repo_url=str(arguments.get("repo_url", "")).strip(),
            branch=str(arguments.get("branch", "main")).strip() or "main",
        )

    def register(self, mcp: Any) -> None:
        return None


def build_component(config: dict[str, Any] | None = None, full_config: dict[str, Any] | None = None) -> AgentInstallerComponent:
    section = config or {}
    root = full_config or {}
    client_cfg = root.get("client", {}) if isinstance(root.get("client", {}), dict) else {}
    components_cfg = root.get("components", {}) if isinstance(root.get("components", {}), dict) else {}
    node_id = str(client_cfg.get("node_id", "")).strip() or "unknown-node"
    install_folder = str(components_cfg.get("folder", "components")).strip() or "components"
    timeout_seconds = int(section.get("timeout_seconds", 20)) if isinstance(section, dict) else 20
    return AgentInstallerComponent(node_id=node_id, install_folder=install_folder, timeout_seconds=timeout_seconds)
