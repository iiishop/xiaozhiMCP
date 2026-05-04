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
        self._remote_invoker: Any = None

    def supports_role(self, role: str) -> bool:
        return role == "server"

    def set_remote_invoker(self, invoker: Any) -> None:
        self._remote_invoker = invoker

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

    def _parse_platforms_from_readme(self, readme: str) -> dict[str, Any]:
        lines = [line.strip() for line in (readme or "").splitlines() if line.strip()]
        if not lines:
            return {"platforms": [], "valid": False, "raw": "", "warning": "README is empty"}
        last = lines[-1]
        m = re.match(r"^Platforms\s*:\s*(.+)$", last, re.IGNORECASE)
        if not m:
            return {
                "platforms": [],
                "valid": False,
                "raw": last,
                "warning": "Missing final line format: Platforms: Windows|Linux|MacOs",
            }

        raw = m.group(1).strip()
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        norm_map = {
            "windows": "Windows",
            "linux": "Linux",
            "macos": "MacOs",
        }
        out: list[str] = []
        unknown: list[str] = []
        for part in parts:
            key = part.lower()
            if key in norm_map:
                val = norm_map[key]
                if val not in out:
                    out.append(val)
            else:
                unknown.append(part)
        warning = ""
        if unknown:
            warning = f"Unknown platform tokens: {', '.join(unknown)}"
        return {"platforms": out, "valid": len(out) > 0 and not unknown, "raw": raw, "warning": warning}

    def _component_meta(self, target: dict[str, Any]) -> dict[str, Any]:
        readme_path = f"{target['path'].strip('/')}/{target['readme'].strip('/')}"
        readme_text = self._get_text(self._raw_url(readme_path))
        platform_info = self._parse_platforms_from_readme(readme_text)
        return {
            **target,
            "readme_path": readme_path,
            "readme": readme_text,
            "platforms": platform_info.get("platforms", []),
            "platform_valid": bool(platform_info.get("valid", False)),
            "platform_warning": str(platform_info.get("warning", "")),
        }

    def search_components(self, query: str = "", fuzzy: bool = True, readme: bool = False, platform: str = "") -> dict[str, Any]:
        q = (query or "").strip().lower()
        p = (platform or "").strip().lower()
        requested_platform = ""
        if p:
            requested_platform = {"windows": "Windows", "linux": "Linux", "macos": "MacOs"}.get(p, "")
        items = self.list_components()
        out: list[dict[str, Any]] = []
        for item in items:
            meta = self._component_meta(item)
            if requested_platform and requested_platform not in meta.get("platforms", []):
                continue
            matched = not q
            if q:
                name = str(meta.get("name", "")).lower()
                desc = str(meta.get("description", "")).lower()
                if fuzzy:
                    matched = q in name or q in desc
                else:
                    matched = q == name
                if readme and not matched:
                    matched = q in str(meta.get("readme", "")).lower()
            if matched:
                out.append(
                    {
                        "name": meta["name"],
                        "description": meta.get("description", ""),
                        "version": meta.get("version", ""),
                        "platforms": meta.get("platforms", []),
                        "platform_valid": meta.get("platform_valid", False),
                        "platform_warning": meta.get("platform_warning", ""),
                    }
                )
        out.sort(key=lambda x: x["name"])
        return {"success": True, "count": len(out), "components": out}

    def get_component_readme(self, component_name: str) -> dict[str, Any]:
        name = _safe_component_name(component_name)
        all_items = self.list_components()
        target = next((x for x in all_items if x["name"] == name), None)
        if not target:
            return {"success": False, "error": f"component not found: {name}"}
        readme_path = f"{target['path'].strip('/')}/{target['readme'].strip('/')}"
        text = self._get_text(self._raw_url(readme_path))
        platform_info = self._parse_platforms_from_readme(text)
        return {
            "success": True,
            "name": name,
            "readme_path": readme_path,
            "readme": text,
            "platforms": platform_info.get("platforms", []),
            "platform_valid": bool(platform_info.get("valid", False)),
            "platform_warning": str(platform_info.get("warning", "")),
        }

    def describe_component(self, component_name: str) -> dict[str, Any]:
        name = _safe_component_name(component_name)
        all_items = self.list_components()
        target = next((x for x in all_items if x["name"] == name), None)
        if not target:
            return {"success": False, "error": f"component not found: {name}"}
        meta = self._component_meta(target)
        lines = [line.strip() for line in str(meta.get("readme", "")).splitlines() if line.strip()]
        summary = lines[1] if len(lines) > 1 else (lines[0] if lines else "")
        return {
            "success": True,
            "name": meta["name"],
            "description": meta.get("description", ""),
            "version": meta.get("version", ""),
            "path": meta.get("path", ""),
            "entry": meta.get("entry", ""),
            "readme_path": meta.get("readme_path", ""),
            "summary": summary,
            "platforms": meta.get("platforms", []),
            "platform_valid": meta.get("platform_valid", False),
            "platform_warning": meta.get("platform_warning", ""),
        }

    def get_component_platforms(self, component_name: str) -> dict[str, Any]:
        name = _safe_component_name(component_name)
        all_items = self.list_components()
        target = next((x for x in all_items if x["name"] == name), None)
        if not target:
            return {"success": False, "error": f"component not found: {name}"}
        meta = self._component_meta(target)
        return {
            "success": True,
            "name": meta["name"],
            "platforms": meta.get("platforms", []),
            "platform_valid": meta.get("platform_valid", False),
            "platform_warning": meta.get("platform_warning", ""),
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

    async def install_component_to_client(self, component_name: str, node_id: str, mode: str = "client_pull") -> dict[str, Any]:
        if mode != "client_pull":
            return {
                "success": False,
                "error": "not_implemented",
                "mode": mode,
                "message": "server_push is not implemented in stage 1",
            }
        if self._remote_invoker is None:
            return {"success": False, "error": "remote invoker not configured"}

        req = {
            "type": "catalog_install_component",
            "component_name": str(component_name),
            "node_id": str(node_id),
            "repo_url": self.repo_url,
            "branch": self.branch,
        }
        tool_name = f"agent_install_component__{node_id}"
        result = await self._remote_invoker(tool_name, req)
        return {"success": True, "mode": mode, "node_id": node_id, "result": result}

    def export_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catalog_list_components",
                "description": "List available components in the remote MCP components repository.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "catalog_search_components",
                "description": "Search components by keyword, fuzzy match, README keyword and optional platform filter.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "fuzzy": {"type": "boolean"},
                        "readme": {"type": "boolean"},
                        "platform": {"type": "string"},
                    },
                },
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
                "name": "catalog_describe_component",
                "description": "Describe a component with summary and metadata.",
                "input_schema": {
                    "type": "object",
                    "properties": {"component_name": {"type": "string"}},
                    "required": ["component_name"],
                },
            },
            {
                "name": "catalog_get_component_platforms",
                "description": "Get required platforms parsed from README final Platforms line.",
                "input_schema": {
                    "type": "object",
                    "properties": {"component_name": {"type": "string"}},
                    "required": ["component_name"],
                },
            },
            {
                "name": "catalog_install_component_to_server",
                "description": "Install a component from remote repository into local server components folder.",
                "input_schema": {
                    "type": "object",
                    "properties": {"component_name": {"type": "string"}},
                    "required": ["component_name"],
                },
            },
            {
                "name": "catalog_install_component_to_client",
                "description": "Install a component to target client by node_id, supports client_pull and reserved server_push mode.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "component_name": {"type": "string"},
                        "node_id": {"type": "string"},
                        "mode": {"type": "string"},
                    },
                    "required": ["component_name", "node_id"],
                },
            },
        ]

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        if tool_name == "catalog_list_components":
            items = self.list_components()
            return {"success": True, "count": len(items), "components": items}
        if tool_name == "catalog_search_components":
            return self.search_components(
                query=str(arguments.get("query", "")),
                fuzzy=bool(arguments.get("fuzzy", True)),
                readme=bool(arguments.get("readme", False)),
                platform=str(arguments.get("platform", "")),
            )
        if tool_name == "catalog_get_component_readme":
            return self.get_component_readme(str(arguments.get("component_name", "")))
        if tool_name == "catalog_describe_component":
            return self.describe_component(str(arguments.get("component_name", "")))
        if tool_name == "catalog_get_component_platforms":
            return self.get_component_platforms(str(arguments.get("component_name", "")))
        if tool_name == "catalog_install_component_to_server":
            return self.install_component(str(arguments.get("component_name", "")))
        raise RuntimeError(f"unknown tool: {tool_name}")

    def register(self, mcp: Any) -> None:
        @mcp.tool()
        def catalog_list_components() -> dict:
            """List available remote components from configured GitHub components repository."""
            return self.invoke_tool("catalog_list_components", {})

        @mcp.tool()
        def catalog_search_components(query: str = "", fuzzy: bool = True, readme: bool = False, platform: str = "") -> dict:
            """Search remote components by query and optional platform filter (Windows/Linux/MacOs)."""
            return self.invoke_tool(
                "catalog_search_components",
                {"query": query, "fuzzy": bool(fuzzy), "readme": bool(readme), "platform": platform},
            )

        @mcp.tool()
        def catalog_get_component_readme(component_name: str) -> dict:
            """Read README.md of a remote component by name."""
            return self.invoke_tool("catalog_get_component_readme", {"component_name": component_name})

        @mcp.tool()
        def catalog_describe_component(component_name: str) -> dict:
            """Get metadata and summary of a remote component by name."""
            return self.invoke_tool("catalog_describe_component", {"component_name": component_name})

        @mcp.tool()
        def catalog_get_component_platforms(component_name: str) -> dict:
            """Get platform requirements parsed from README final line: Platforms: Windows|Linux|MacOs."""
            return self.invoke_tool("catalog_get_component_platforms", {"component_name": component_name})

        @mcp.tool()
        def catalog_install_component_to_server(component_name: str) -> dict:
            """Install a component by name into local configured components folder on server."""
            return self.invoke_tool("catalog_install_component_to_server", {"component_name": component_name})

        @mcp.tool()
        async def catalog_install_component_to_client(component_name: str, node_id: str, mode: str = "client_pull") -> dict:
            """Install component to specific client node_id. mode=client_pull|server_push (server_push placeholder)."""
            return await self.install_component_to_client(component_name=component_name, node_id=node_id, mode=mode)


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
