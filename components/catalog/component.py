from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import requests

from ..base import MCPComponent


def _parse_github_repo(repo_url: str) -> tuple[str, str]:
    text = (repo_url or "").strip()
    text = text.removesuffix(".git")
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+)$", text)
    if not m:
        raise ValueError("invalid github repo url")
    return m.group(1), m.group(2)


def _safe_component_name(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]", "", (name or "").strip())
    if not value:
        raise ValueError("invalid component name")
    return value


class CatalogComponent(MCPComponent):
    def __init__(
        self,
        repo_url: str,
        branch: str = "main",
        install_folder: str = "user_components",
        timeout_seconds: int = 20,
    ) -> None:
        self.repo_url = repo_url
        self.owner, self.repo = _parse_github_repo(repo_url)
        self.branch = branch or "main"
        self.install_folder = install_folder or "user_components"
        self.timeout_seconds = max(5, int(timeout_seconds))

    def _get_json(self, url: str) -> Any:
        resp = requests.get(url, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def _get_text(self, url: str) -> str:
        resp = requests.get(url, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.text

    def _raw_url(self, path: str) -> str:
        p = path.lstrip("/")
        return f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{self.branch}/{p}"

    def _contents_api_url(self, path: str = "") -> str:
        p = path.strip("/")
        tail = f"/{p}" if p else ""
        return f"https://api.github.com/repos/{self.owner}/{self.repo}/contents{tail}?ref={self.branch}"

    def _list_from_index(self) -> list[dict[str, Any]]:
        data = self._get_json(self._raw_url("index.json"))
        if not isinstance(data, list):
            raise ValueError("index.json must be a JSON array")
        out: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = _safe_component_name(str(item.get("name", "")))
            out.append(
                {
                    "name": name,
                    "description": str(item.get("description", "")),
                    "version": str(item.get("version", "")),
                    "path": str(item.get("path", name)),
                    "entry": str(item.get("entry", "component.py")),
                    "readme": str(item.get("readme", "README.md")),
                }
            )
        out.sort(key=lambda x: x["name"])
        return out

    def list_components(self) -> list[dict[str, Any]]:
        try:
            return self._list_from_index()
        except Exception:
            items = self._get_json(self._contents_api_url())
            out: list[dict[str, Any]] = []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "dir":
                    continue
                name = str(item.get("name", ""))
                if not name or name.startswith("."):
                    continue
                out.append(
                    {
                        "name": name,
                        "description": "",
                        "version": "",
                        "path": name,
                        "entry": "component.py",
                        "readme": "README.md",
                    }
                )
            out.sort(key=lambda x: x["name"])
            return out

    def get_component_readme(self, component_name: str) -> dict[str, Any]:
        name = _safe_component_name(component_name)
        all_items = self.list_components()
        target = next((x for x in all_items if x["name"] == name), None)
        if not target:
            return {"success": False, "error": f"component not found: {name}"}
        readme_path = f"{target['path'].strip('/')}/{target['readme'].strip('/')}"
        text = self._get_text(self._raw_url(readme_path))
        return {
            "success": True,
            "name": name,
            "readme_path": readme_path,
            "readme": text,
        }

    def install_component(self, component_name: str) -> dict[str, Any]:
        name = _safe_component_name(component_name)
        all_items = self.list_components()
        target = next((x for x in all_items if x["name"] == name), None)
        if not target:
            return {"success": False, "error": f"component not found: {name}"}

        rel_path = target["path"].strip("/")
        entry = target["entry"].strip("/")
        readme = target["readme"].strip("/")

        entry_text = self._get_text(self._raw_url(f"{rel_path}/{entry}"))
        readme_text = self._get_text(self._raw_url(f"{rel_path}/{readme}"))

        install_root = Path(self.install_folder)
        target_dir = install_root / name
        target_dir.mkdir(parents=True, exist_ok=True)

        (target_dir / "component.py").write_text(entry_text, encoding="utf-8")
        (target_dir / "README.md").write_text(readme_text, encoding="utf-8")
        if not (target_dir / "__init__.py").exists():
            (target_dir / "__init__.py").write_text("", encoding="utf-8")

        return {
            "success": True,
            "name": name,
            "installed_to": str(target_dir),
        }

    def export_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catalog_list_components",
                "description": "List available components in the remote MCP components repository.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "catalog_get_component_readme",
                "description": "Get README text for a component from remote repository.",
                "input_schema": {
                    "type": "object",
                    "properties": {"component_name": {"type": "string"}},
                    "required": ["component_name"],
                },
            },
            {
                "name": "catalog_install_component",
                "description": "Install a component from remote repository into local user_components folder.",
                "input_schema": {
                    "type": "object",
                    "properties": {"component_name": {"type": "string"}},
                    "required": ["component_name"],
                },
            },
        ]

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        if tool_name == "catalog_list_components":
            items = self.list_components()
            return {"success": True, "count": len(items), "components": items}
        if tool_name == "catalog_get_component_readme":
            return self.get_component_readme(str(arguments.get("component_name", "")))
        if tool_name == "catalog_install_component":
            return self.install_component(str(arguments.get("component_name", "")))
        raise RuntimeError(f"unknown tool: {tool_name}")

    def register(self, mcp: Any) -> None:
        @mcp.tool()
        def catalog_list_components() -> dict:
            """List available remote components from configured GitHub components repository."""
            return self.invoke_tool("catalog_list_components", {})

        @mcp.tool()
        def catalog_get_component_readme(component_name: str) -> dict:
            """Read README.md of a remote component by name."""
            return self.invoke_tool("catalog_get_component_readme", {"component_name": component_name})

        @mcp.tool()
        def catalog_install_component(component_name: str) -> dict:
            """Install a component by name into local user_components folder."""
            return self.invoke_tool("catalog_install_component", {"component_name": component_name})


def build_component(config: dict[str, Any] | None = None, full_config: dict[str, Any] | None = None) -> CatalogComponent:
    section = config or {}
    root = full_config or {}
    components_cfg = root.get("components", {}) if isinstance(root.get("components", {}), dict) else {}
    default_install_folder = str(components_cfg.get("folder", "user_components"))
    install_folder = str(section.get("install_folder", "")).strip() or default_install_folder
    return CatalogComponent(
        repo_url=str(section.get("repo_url", "https://github.com/iiishop/xiaozhiMCP-components.git")),
        branch=str(section.get("branch", "main")),
        install_folder=install_folder,
        timeout_seconds=int(section.get("timeout_seconds", 20)),
    )
