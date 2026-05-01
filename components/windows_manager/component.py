from __future__ import annotations

import json
import subprocess
import ctypes
from typing import Any

import win32con
import win32gui
import win32process

from ..base import MCPComponent


def normalize_windows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for row in rows:
        title = str(row.get("title", "")).strip()
        pid = int(row.get("pid", 0))
        if not title:
            continue
        key = (title, pid)
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "pid": pid})

    out.sort(key=lambda x: x["title"].lower())
    return out


def filter_windows_by_keyword(rows: list[dict[str, Any]], keyword: str) -> list[dict[str, Any]]:
    key = (keyword or "").strip().lower()
    if not key:
        return list(rows)

    return [row for row in rows if key in str(row.get("title", "")).lower()]


def select_window_match(rows: list[dict[str, Any]], match_index: int) -> dict[str, Any] | None:
    idx = int(match_index)
    if idx < 1 or idx > len(rows):
        return None
    return rows[idx - 1]


def merge_windows_with_process_stats(rows: list[dict[str, Any]], stats: dict[int, dict[str, float]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for row in rows:
        pid = int(row.get("pid", 0))
        item = {
            "title": str(row.get("title", "")),
            "pid": pid,
        }
        proc = stats.get(pid, {})
        item["cpu_seconds"] = float(proc.get("cpu_seconds", 0.0))
        item["working_set_mb"] = float(proc.get("working_set_mb", 0.0))
        merged.append(item)

    merged.sort(key=lambda x: (-x["working_set_mb"], x["title"].lower()))
    return merged


def list_open_windows() -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []

    def _enum(hwnd: int, _: int) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True

        if win32gui.GetWindow(hwnd, win32con.GW_OWNER) != 0:
            return True

        title = win32gui.GetWindowText(hwnd)
        if not title.strip():
            return True

        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:  # noqa: BLE001
            pid = 0

        windows.append(
            {
                "hwnd": int(hwnd),
                "title": title.strip(),
                "pid": int(pid),
            }
        )
        return True

    win32gui.EnumWindows(_enum, 0)
    return windows


def _fetch_process_stats(pids: list[int]) -> dict[int, dict[str, float]]:
    valid_pids = sorted({int(pid) for pid in pids if int(pid) > 0})
    if not valid_pids:
        return {}

    ids = ",".join(str(pid) for pid in valid_pids)
    cmd = (
        "$ids=@(" + ids + ");"
        "Get-Process -Id $ids -ErrorAction SilentlyContinue | "
        "Select-Object Id,CPU,WS | ConvertTo-Json -Compress"
    )

    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if completed.returncode != 0:
        return {}

    raw = (completed.stdout or "").strip()
    if not raw:
        return {}

    data = json.loads(raw)
    entries = data if isinstance(data, list) else [data]

    out: dict[int, dict[str, float]] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        pid = int(item.get("Id", 0))
        cpu = float(item.get("CPU", 0.0) or 0.0)
        ws_mb = float(item.get("WS", 0.0) or 0.0) / (1024 * 1024)
        out[pid] = {
            "cpu_seconds": round(cpu, 3),
            "working_set_mb": round(ws_mb, 3),
        }

    return out


def _is_foreground(hwnd: int) -> bool:
    try:
        return int(win32gui.GetForegroundWindow()) == int(hwnd)
    except Exception:  # noqa: BLE001
        return False


def focus_window(hwnd: int) -> dict[str, Any]:
    target = int(hwnd)
    try:
        win32gui.ShowWindow(target, win32con.SW_RESTORE)
        win32gui.BringWindowToTop(target)
        win32gui.SetForegroundWindow(target)
        if _is_foreground(target):
            return {"activated": True, "strategy": "direct"}
    except Exception:  # noqa: BLE001
        pass

    try:
        flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
        win32gui.SetWindowPos(target, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)
        win32gui.SetWindowPos(target, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        win32gui.SetForegroundWindow(target)
        if _is_foreground(target):
            return {"activated": True, "strategy": "topmost_toggle"}
    except Exception:  # noqa: BLE001
        pass

    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(win32con.VK_MENU, 0, 0, 0)
        user32.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32gui.SetForegroundWindow(target)
        if _is_foreground(target):
            return {"activated": True, "strategy": "alt_key"}
    except Exception:  # noqa: BLE001
        pass

    return {"activated": False, "strategy": "failed"}


def close_window(hwnd: int) -> None:
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)


class WindowsManagerComponent(MCPComponent):
    def export_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "windows_list_open_apps", "description": "List currently opened Windows desktop app windows.", "input_schema": {"type": "object", "properties": {}}},
            {"name": "windows_find_apps", "description": "Find opened app windows by title keyword.", "input_schema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}},
            {"name": "windows_focus_app", "description": "Focus app window by keyword and optional match index.", "input_schema": {"type": "object", "properties": {"keyword": {"type": "string"}, "match_index": {"type": "integer"}}, "required": ["keyword"]}},
            {"name": "windows_close_app", "description": "Close app window by keyword and optional match index.", "input_schema": {"type": "object", "properties": {"keyword": {"type": "string"}, "match_index": {"type": "integer"}}, "required": ["keyword"]}},
            {"name": "windows_list_app_performance", "description": "List opened windows with CPU/memory usage, optionally filtered by keyword.", "input_schema": {"type": "object", "properties": {"keyword": {"type": "string"}}}},
        ]

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        keyword = str(arguments.get("keyword", ""))
        match_index = int(arguments.get("match_index", 1))

        if tool_name == "windows_list_open_apps":
            rows = list_open_windows()
            return {"apps": normalize_windows(rows)}
        if tool_name == "windows_find_apps":
            rows = filter_windows_by_keyword(list_open_windows(), keyword)
            return {"keyword": keyword, "count": len(rows), "apps": normalize_windows(rows)}
        if tool_name == "windows_focus_app":
            rows = filter_windows_by_keyword(list_open_windows(), keyword)
            target = select_window_match(rows, match_index)
            if target is None:
                return {"ok": False, "error": "no matching window found", "count": len(rows)}
            out = focus_window(int(target["hwnd"]))
            return {"ok": bool(out.get("activated", False)), **out, "window": {"title": target["title"], "pid": int(target["pid"])}}
        if tool_name == "windows_close_app":
            rows = filter_windows_by_keyword(list_open_windows(), keyword)
            target = select_window_match(rows, match_index)
            if target is None:
                return {"ok": False, "error": "no matching window found", "count": len(rows)}
            close_window(int(target["hwnd"]))
            return {"ok": True, "window": {"title": target["title"], "pid": int(target["pid"])}}
        if tool_name == "windows_list_app_performance":
            rows = filter_windows_by_keyword(list_open_windows(), keyword)
            pids = [int(row.get("pid", 0)) for row in rows]
            stats = _fetch_process_stats(pids)
            return {"keyword": keyword, "count": len(rows), "apps": merge_windows_with_process_stats(rows, stats)}

        raise RuntimeError(f"unknown tool: {tool_name}")

    def register(self, mcp: Any) -> None:
        @mcp.tool()
        def windows_list_open_apps() -> dict:
            """List currently opened Windows desktop app windows."""
            rows = list_open_windows()
            apps = normalize_windows(rows)
            return {"success": True, "count": len(apps), "apps": apps}

        @mcp.tool()
        def windows_find_apps(keyword: str) -> dict:
            """Find opened app windows by title keyword (case-insensitive)."""
            rows = filter_windows_by_keyword(list_open_windows(), keyword)
            apps = normalize_windows(rows)
            return {"success": True, "keyword": keyword, "count": len(apps), "apps": apps}

        @mcp.tool()
        def windows_focus_app(keyword: str, match_index: int = 1) -> dict:
            """Focus an opened app window by title keyword. Use match_index when multiple matches exist."""
            rows = filter_windows_by_keyword(list_open_windows(), keyword)
            target = select_window_match(rows, match_index)
            if target is None:
                return {
                    "success": False,
                    "error": "no matching window found",
                    "keyword": keyword,
                    "count": len(rows),
                }

            try:
                focus_result = focus_window(int(target["hwnd"]))
                return {
                    "success": bool(focus_result.get("activated", False)),
                    "keyword": keyword,
                    "match_index": int(match_index),
                    "window": {"title": target["title"], "pid": int(target["pid"])},
                    **focus_result,
                }
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc), "keyword": keyword}

        @mcp.tool()
        def windows_close_app(keyword: str, match_index: int = 1) -> dict:
            """Request close for an opened app window by title keyword."""
            rows = filter_windows_by_keyword(list_open_windows(), keyword)
            target = select_window_match(rows, match_index)
            if target is None:
                return {
                    "success": False,
                    "error": "no matching window found",
                    "keyword": keyword,
                    "count": len(rows),
                }

            try:
                close_window(int(target["hwnd"]))
                return {
                    "success": True,
                    "keyword": keyword,
                    "match_index": int(match_index),
                    "window": {"title": target["title"], "pid": int(target["pid"])},
                }
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc), "keyword": keyword}

        @mcp.tool()
        def windows_list_app_performance(keyword: str = "") -> dict:
            """List opened windows with process CPU seconds and memory usage in MB, optionally filtered by keyword."""
            rows = filter_windows_by_keyword(list_open_windows(), keyword)
            pids = [int(row.get("pid", 0)) for row in rows]
            stats = _fetch_process_stats(pids)
            apps = merge_windows_with_process_stats(rows, stats)
            return {"success": True, "keyword": keyword, "count": len(apps), "apps": apps}
