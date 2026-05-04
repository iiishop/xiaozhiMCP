from __future__ import annotations

import json
import logging
import os
import platform
import select
import subprocess
import threading
import time
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
        self._lock = threading.RLock()
        self._cached_tools: list[dict[str, Any]] | None = None
        self._stderr_thread: threading.Thread | None = None
        self._protocol = "mcp_headers"
        self._header_rejected = threading.Event()

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
        self._start_stderr_drain()
        self._initialize_with_fallback()

    def _initialize_with_fallback(self) -> None:
        init_payload = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "xiaozhi-apple-music-bridge", "version": "0.1.0"},
        }
        try:
            self._request("initialize", init_payload, timeout_seconds=8.0)
            self._notify("notifications/initialized", {})
            log.info("apple_music bridge: initialized mcp session protocol=%s", self._protocol)
            return
        except Exception as exc:  # noqa: BLE001
            if not self._header_rejected.is_set():
                raise
            log.warning("apple_music bridge: header protocol rejected, retrying jsonl protocol: %s", exc)

        self._restart_process()
        self._protocol = "jsonl"
        self._header_rejected.clear()
        self._start_stderr_drain()
        self._request("initialize", init_payload, timeout_seconds=8.0)
        self._notify("notifications/initialized", {})
        log.info("apple_music bridge: initialized mcp session protocol=%s", self._protocol)

    def _restart_process(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:  # noqa: BLE001
                pass
        self._stderr_thread = None
        cmd = [str(self.config.get("command", "")).strip()]
        cmd.extend([str(x) for x in (self.config.get("args") or [])])
        env = os.environ.copy()
        for k, v in (self.config.get("env") or {}).items():
            env[str(k)] = str(v)
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        log.info("apple_music bridge: respawned stdio mcp process")

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._write_message({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict[str, Any], timeout_seconds: float | None = None) -> dict[str, Any]:
        req_id = self._id
        self._id += 1
        log.info("apple_music bridge: request start method=%s id=%s", method, req_id)
        self._write_message({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        deadline = (time.time() + timeout_seconds) if timeout_seconds and timeout_seconds > 0 else None
        while True:
            msg = self._read_message(deadline=deadline)
            if msg.get("id") != req_id:
                log.info("apple_music bridge: request id=%s skipped unrelated id=%s", req_id, msg.get("id"))
                continue
            if "error" in msg:
                err = msg.get("error") or {}
                raise RuntimeError(str(err.get("message", "unknown mcp error")))
            log.info("apple_music bridge: request success method=%s id=%s", method, req_id)
            return msg

    def _write_message(self, payload: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("bridge process not started")
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if self._protocol == "jsonl":
            self._proc.stdin.write(raw + b"\n")
        else:
            header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
            self._proc.stdin.write(header + raw)
        self._proc.stdin.flush()

    def _read_message(self, deadline: float | None = None) -> dict[str, Any]:
        if not self._proc or not self._proc.stdout:
            raise RuntimeError("bridge process not started")

        if self._protocol == "jsonl":
            line = b""
            while not line.endswith(b"\n"):
                line += self._read_with_wait(1, "jsonl_line", deadline)
            line = line.strip()
            if not line:
                raise RuntimeError("empty jsonl message from bridged mcp")
            log.info("apple_music bridge: received jsonl message bytes=%d", len(line))
            return json.loads(line.decode("utf-8"))

        headers = b""
        while b"\r\n\r\n" not in headers:
            headers += self._read_with_wait(1, "headers", deadline)

        content_length = 0
        for line in headers.decode("ascii", errors="replace").split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
                break
        if content_length <= 0:
            raise RuntimeError("invalid content length from bridged mcp")

        body = b""
        while len(body) < content_length:
            body += self._read_with_wait(content_length - len(body), "body", deadline)
        log.info("apple_music bridge: received message bytes=%d", len(body))
        return json.loads(body.decode("utf-8"))

    def _read_with_wait(self, max_bytes: int, phase: str, deadline: float | None) -> bytes:
        if not self._proc or not self._proc.stdout:
            raise RuntimeError("bridge process not started")

        fd = self._proc.stdout.fileno()
        started = time.time()
        while True:
            ready, _, _ = select.select([fd], [], [], 2.0)
            if ready:
                chunk = os.read(fd, max_bytes)
                if chunk:
                    return chunk
                raise RuntimeError("bridge process closed stdout")

            elapsed = int(time.time() - started)
            if elapsed > 0 and elapsed % 10 == 0:
                state = self._proc.poll()
                log.info(
                    "apple_music bridge: waiting for %s response... elapsed=%ss proc_exit=%s",
                    phase,
                    elapsed,
                    state,
                )
            if deadline is not None and time.time() > deadline:
                raise TimeoutError(f"timeout waiting for {phase} response from bridged mcp")

    def _start_stderr_drain(self) -> None:
        if not self._proc or not self._proc.stderr:
            return
        if self._stderr_thread is not None:
            return

        def _drain() -> None:
            assert self._proc is not None and self._proc.stderr is not None
            for raw in iter(self._proc.stderr.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    log.info("apple_music bridge stderr: %s", line)
                if "Invalid JSON" in line:
                    self._header_rejected.set()

        self._stderr_thread = threading.Thread(target=_drain, name="apple-music-bridge-stderr", daemon=True)
        self._stderr_thread.start()

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
            log.info("apple_music bridge: invoke start tool=%s", tool_name)
            self._ensure_started()
            raw_name = ""
            tools = self._cached_tools or []
            if not tools:
                tools = self.export_tools()
            for t in tools:
                if t.get("name") == tool_name:
                    raw_name = str(t.get("_raw_name", ""))
                    break
            if not raw_name:
                raise RuntimeError(f"unknown bridged tool: {tool_name}")
            msg = self._request("tools/call", {"name": raw_name, "arguments": arguments}, timeout_seconds=60.0)
            log.info("apple_music bridge: invoke success tool=%s", tool_name)
            return {"success": True, "result": msg.get("result")}

    def register(self, _mcp: Any) -> None:
        return None
