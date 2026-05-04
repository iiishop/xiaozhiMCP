from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import requests


def parse_github_repo(repo_url: str) -> tuple[str, str]:
    text = (repo_url or "").strip().removesuffix(".git")
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+)$", text)
    if not m:
        raise ValueError("invalid github repo url")
    return m.group(1), m.group(2)


def safe_component_name(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]", "", (name or "").strip())
    if not value:
        raise ValueError("invalid component name")
    return value


class CatalogCore:
    def __init__(self, repo_url: str, branch: str, install_folder: str, timeout_seconds: int = 20) -> None:
        self.repo_url = repo_url
        self.owner, self.repo = parse_github_repo(repo_url)
        self.branch = branch or "main"
        self.install_folder = install_folder
        self.timeout_seconds = max(5, int(timeout_seconds))

    def _raw_url(self, path: str) -> str:
        p = path.lstrip("/")
        return f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{self.branch}/{p}"

    def _contents_api_url(self, path: str = "") -> str:
        p = path.strip("/")
        tail = f"/{p}" if p else ""
        return f"https://api.github.com/repos/{self.owner}/{self.repo}/contents{tail}?ref={self.branch}"

    def _get_json(self, url: str) -> Any:
        resp = requests.get(url, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def _get_text(self, url: str) -> str:
        resp = requests.get(url, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.text

    def parse_platforms_from_readme(self, readme: str) -> dict[str, Any]:
        lines = [line.strip() for line in (readme or "").splitlines() if line.strip()]
        if not lines:
            return {"platforms": [], "valid": False, "warning": "README is empty"}
        m = re.match(r"^Platforms\s*:\s*(.+)$", lines[-1], re.IGNORECASE)
        if not m:
            return {"platforms": [], "valid": False, "warning": "Missing final line format: Platforms: Windows|Linux|MacOs"}

        norm_map = {"windows": "Windows", "linux": "Linux", "macos": "MacOs"}
        parts = [p.strip() for p in m.group(1).split("|") if p.strip()]
        out: list[str] = []
        unknown: list[str] = []
        for part in parts:
            key = part.lower()
            if key in norm_map:
                value = norm_map[key]
                if value not in out:
                    out.append(value)
            else:
                unknown.append(part)
        warning = ""
        if unknown:
            warning = f"Unknown platform tokens: {', '.join(unknown)}"
        return {"platforms": out, "valid": len(out) > 0 and not unknown, "warning": warning}

    def list_components(self) -> list[dict[str, Any]]:
        try:
            data = self._get_json(self._raw_url("index.json"))
            if not isinstance(data, list):
                raise ValueError("index.json must be a JSON array")
            out: list[dict[str, Any]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = safe_component_name(str(item.get("name", "")))
                out.append(
                    {
                        "name": name,
                        "description": str(item.get("description", "")),
                        "version": str(item.get("version", "")),
                        "path": str(item.get("path", name)),
                        "entry": str(item.get("entry", "component.py")),
                        "readme": str(item.get("readme", "README.md")),
                        "platforms": item.get("platforms", []) if isinstance(item.get("platforms", []), list) else [],
                    }
                )
            out.sort(key=lambda x: x["name"])
            return out
        except Exception:
            items = self._get_json(self._contents_api_url())
            out: list[dict[str, Any]] = []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict) or item.get("type") != "dir":
                    continue
                name = str(item.get("name", "")).strip()
                if not name or name.startswith("."):
                    continue
                out.append({"name": name, "description": "", "version": "", "path": name, "entry": "component.py", "readme": "README.md", "platforms": []})
            out.sort(key=lambda x: x["name"])
            return out

    def get_component(self, component_name: str) -> dict[str, Any] | None:
        name = safe_component_name(component_name)
        items = self.list_components()
        return next((x for x in items if x["name"] == name), None)

    def get_component_readme(self, component_name: str) -> dict[str, Any]:
        target = self.get_component(component_name)
        if target is None:
            return {"success": False, "error": f"component not found: {component_name}"}
        readme_path = f"{target['path'].strip('/')}/{target['readme'].strip('/')}"
        text = self._get_text(self._raw_url(readme_path))
        parsed = self.parse_platforms_from_readme(text)
        return {"success": True, "name": target["name"], "readme": text, "readme_path": readme_path, "platforms": parsed["platforms"], "platform_valid": parsed["valid"], "platform_warning": parsed["warning"]}

    def describe_component(self, component_name: str) -> dict[str, Any]:
        target = self.get_component(component_name)
        if target is None:
            return {"success": False, "error": f"component not found: {component_name}"}
        readme_info = self.get_component_readme(target["name"])
        if not readme_info.get("success", False):
            return readme_info
        readme_text = str(readme_info.get("readme", ""))
        lines = [line.strip() for line in readme_text.splitlines() if line.strip()]
        summary = lines[1] if len(lines) > 1 else (lines[0] if lines else "")
        return {
            "success": True,
            "name": target["name"],
            "description": target.get("description", ""),
            "version": target.get("version", ""),
            "path": target.get("path", ""),
            "entry": target.get("entry", ""),
            "summary": summary,
            "platforms": readme_info.get("platforms", target.get("platforms", [])),
            "platform_valid": readme_info.get("platform_valid", False),
            "platform_warning": readme_info.get("platform_warning", ""),
        }

    def get_component_platforms(self, component_name: str) -> dict[str, Any]:
        target = self.get_component(component_name)
        if target is None:
            return {"success": False, "error": f"component not found: {component_name}"}
        if target.get("platforms"):
            return {"success": True, "name": target["name"], "platforms": target["platforms"], "platform_valid": True, "platform_warning": ""}
        readme_info = self.get_component_readme(target["name"])
        return {
            "success": bool(readme_info.get("success", False)),
            "name": target["name"],
            "platforms": readme_info.get("platforms", []),
            "platform_valid": readme_info.get("platform_valid", False),
            "platform_warning": readme_info.get("platform_warning", ""),
        }

    def search_components(self, query: str = "", fuzzy: bool = True, readme: bool = False, platform: str = "") -> dict[str, Any]:
        q = (query or "").strip().lower()
        requested = {"windows": "Windows", "linux": "Linux", "macos": "MacOs"}.get((platform or "").strip().lower(), "")
        out: list[dict[str, Any]] = []
        for item in self.list_components():
            platform_info = self.get_component_platforms(item["name"])
            platforms = platform_info.get("platforms", []) if isinstance(platform_info.get("platforms", []), list) else []
            if requested and requested not in platforms:
                continue
            matched = not q
            if q:
                text = (str(item.get("name", "")) + " " + str(item.get("description", ""))).lower()
                matched = (q in text) if fuzzy else (q == str(item.get("name", "")).lower())
                if readme and not matched:
                    readme_info = self.get_component_readme(item["name"])
                    matched = q in str(readme_info.get("readme", "")).lower()
            if matched:
                out.append(
                    {
                        "name": item["name"],
                        "description": item.get("description", ""),
                        "version": item.get("version", ""),
                        "platforms": platforms,
                        "platform_valid": bool(platform_info.get("platform_valid", False)),
                        "platform_warning": str(platform_info.get("platform_warning", "")),
                    }
                )
        out.sort(key=lambda x: x["name"])
        return {"success": True, "count": len(out), "components": out}

    def install_component(self, component_name: str, install_folder: str | None = None) -> dict[str, Any]:
        target = self.get_component(component_name)
        if target is None:
            return {"success": False, "error": f"component not found: {component_name}"}
        rel_path = target["path"].strip("/")
        entry = target["entry"].strip("/")
        readme = target["readme"].strip("/")
        entry_text = self._get_text(self._raw_url(f"{rel_path}/{entry}"))
        readme_text = self._get_text(self._raw_url(f"{rel_path}/{readme}"))
        root = Path(install_folder or self.install_folder)
        target_dir = root / target["name"]
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "component.py").write_text(entry_text, encoding="utf-8")
        (target_dir / "README.md").write_text(readme_text, encoding="utf-8")
        if not (target_dir / "__init__.py").exists():
            (target_dir / "__init__.py").write_text("", encoding="utf-8")
        return {"success": True, "name": target["name"], "installed_to": str(target_dir)}
