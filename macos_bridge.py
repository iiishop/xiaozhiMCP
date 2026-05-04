from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import threading
from pathlib import Path
from typing import Any


log = logging.getLogger("macos_bridge")


def _is_truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


def prepare_apple_music_bridge(config: dict[str, Any]) -> dict[str, Any] | None:
    if platform.system().lower() != "darwin":
        return None

    section = config.get("apple_music") if isinstance(config.get("apple_music"), dict) else {}
    if not _is_truthy(section.get("enabled"), default=True):
        log.info("apple_music bridge: disabled by config")
        return None

    repo_url = "https://github.com/epheterson/mcp-applemusic.git"
    branch = "main"
    install_dir = Path(str(section.get("install_dir") or "~/.xiaozhi/applemusic-mcp")).expanduser().resolve()
    venv_dir = install_dir / "venv"
    venv_python = venv_dir / "bin" / "python"

    install_dir.parent.mkdir(parents=True, exist_ok=True)
    log.info("apple_music bridge: install_dir=%s", str(install_dir))

    if not (install_dir / ".git").exists():
        log.info("apple_music bridge: cloning repository")
        _run(["git", "clone", "--branch", branch, repo_url, str(install_dir)], "clone repo")
    elif _is_truthy(section.get("update_on_startup"), default=True):
        log.info("apple_music bridge: updating repository")
        _run(["git", "-C", str(install_dir), "fetch", "origin", branch], "fetch updates")
        _run(["git", "-C", str(install_dir), "pull", "--ff-only", "origin", branch], "pull updates")

    if not venv_python.exists():
        log.info("apple_music bridge: creating venv")
        _run(["python3", "-m", "venv", str(venv_dir)], "create venv")

    log.info("apple_music bridge: installing package")
    _run([str(venv_python), "-m", "pip", "install", "-e", str(install_dir)], "install editable package")
    log.info("apple_music bridge: bootstrap complete")

    return {
        "command": "uv",
        "args": ["run", "--directory", str(install_dir), "python", "-m", "applemusic_mcp"],
        "tool_prefix": "apple_music_",
        "env": {},
    }


def _run(command: list[str], purpose: str) -> None:
    proc = subprocess.run(command, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        msg = stderr or stdout or f"exit={proc.returncode}"
        raise RuntimeError(f"{purpose} failed: {msg}")


class StdioMCPBridge:
    def __init__(self, bridge_config: dict[str, Any]) -> None:
        self.config = bridge_config
        self._proc: subprocess.Popen[bytes] | None = None
        self._id = 1
        self._lock = threading.Lock()
        self._cached_tools: list[dict[str, Any]] | None = None

    def _ensure_started(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        cmd = [str(self.config.get("command", "")).strip()]
        cmd.extend([str(x) for x in (self.config.get("args") or [])])
        if not cmd[0]:
            raise RuntimeError("bridge command is empty")

        env = os.environ.copy()
        for k, v in (self.config.get("env") or {}).items():
            env[str(k)] = str(v)

        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        log.info("apple_music bridge: spawned stdio mcp process")
        self._request(
            "initialize",
            {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "xiaozhi-apple-music-bridge", "version": "0.1.0"}},
        )
        self._notify("notifications/initialized", {})
        log.info("apple_music bridge: initialized mcp session")

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._write_message({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        req_id = self._id
        self._id += 1
        self._write_message({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        while True:
            msg = self._read_message()
            if msg.get("id") != req_id:
                continue
            if "error" in msg:
                err = msg.get("error") or {}
                raise RuntimeError(str(err.get("message", "unknown mcp error")))
            return msg

    def _write_message(self, payload: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("bridge process not started")
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
        self._proc.stdin.write(header + raw)
        self._proc.stdin.flush()

    def _read_message(self) -> dict[str, Any]:
        if not self._proc or not self._proc.stdout:
            raise RuntimeError("bridge process not started")

        headers = b""
        while b"\r\n\r\n" not in headers:
            b = self._proc.stdout.read(1)
            if not b:
                stderr = b""
                if self._proc.stderr:
                    stderr = self._proc.stderr.read() or b""
                detail = stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(detail or "bridge process closed stdout")
            headers += b

        content_length = 0
        for line in headers.decode("ascii", errors="replace").split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
                break
        if content_length <= 0:
            raise RuntimeError("invalid content length from bridged mcp")

        body = b""
        while len(body) < content_length:
            chunk = self._proc.stdout.read(content_length - len(body))
            if not chunk:
                raise RuntimeError("unexpected eof from bridged mcp")
            body += chunk
        return json.loads(body.decode("utf-8"))

    def export_tools(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._cached_tools is not None:
                return self._cached_tools
            self._ensure_started()
            msg = self._request("tools/list", {})
            tools = (msg.get("result") or {}).get("tools") or []
            prefix = str(self.config.get("tool_prefix") or "apple_music_")
            out: list[dict[str, Any]] = []
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                raw_name = str(tool.get("name", "")).strip()
                if not raw_name:
                    continue
                out.append(
                    {
                        "name": f"{prefix}{raw_name}",
                        "description": str(tool.get("description", "")),
                        "input_schema": tool.get("inputSchema") or tool.get("input_schema") or {"type": "object", "properties": {}},
                        "_raw_name": raw_name,
                    }
                )
            self._cached_tools = out
            log.info("apple_music bridge: discovered tools=%d", len(out))
            return out

    async def ainvoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        with self._lock:
            self._ensure_started()
            raw_name = ""
            for t in self.export_tools():
                if t.get("name") == tool_name:
                    raw_name = str(t.get("_raw_name", ""))
                    break
            if not raw_name:
                raise RuntimeError(f"unknown bridged tool: {tool_name}")
            msg = self._request("tools/call", {"name": raw_name, "arguments": arguments})
            return {"success": True, "result": msg.get("result")}

    def register(self, _mcp: Any) -> None:
        return None
