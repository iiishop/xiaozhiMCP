from __future__ import annotations

from typing import Any

from ..base import MCPComponent


def build_cf_html_payload(fragment_html: str) -> bytes:
    fragment = fragment_html or ""
    html_body = f"<html><body><!--StartFragment-->{fragment}<!--EndFragment--></body></html>"

    header_template = (
        "Version:0.9\r\n"
        "StartHTML:{start_html:010d}\r\n"
        "EndHTML:{end_html:010d}\r\n"
        "StartFragment:{start_fragment:010d}\r\n"
        "EndFragment:{end_fragment:010d}\r\n"
    )

    provisional = header_template.format(
        start_html=0,
        end_html=0,
        start_fragment=0,
        end_fragment=0,
    ).encode("utf-8")
    html_bytes = html_body.encode("utf-8")

    start_html = len(provisional)
    end_html = start_html + len(html_bytes)
    marker_start = "<!--StartFragment-->".encode("utf-8")
    marker_end = "<!--EndFragment-->".encode("utf-8")
    start_fragment = start_html + html_bytes.index(marker_start) + len(marker_start)
    end_fragment = start_html + html_bytes.index(marker_end)

    header = header_template.format(
        start_html=start_html,
        end_html=end_html,
        start_fragment=start_fragment,
        end_fragment=end_fragment,
    ).encode("utf-8")

    return header + html_bytes


def set_windows_clipboard_text(text: str, html: str = "") -> None:
    import win32clipboard
    import win32con

    plain_text = text or ""

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, plain_text)
        if html.strip():
            html_format = win32clipboard.RegisterClipboardFormat("HTML Format")
            win32clipboard.SetClipboardData(html_format, build_cf_html_payload(html))
    finally:
        win32clipboard.CloseClipboard()


def get_windows_clipboard_text() -> str:
    import win32clipboard
    import win32con

    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            value = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return str(value or "")

        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_TEXT):
            value = win32clipboard.GetClipboardData(win32con.CF_TEXT)
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return str(value or "")

        return ""
    finally:
        win32clipboard.CloseClipboard()


class ClipboardComponent(MCPComponent):
    def export_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "clipboard_set",
                "description": "Copy content to Windows clipboard. Optional HTML keeps rich text style.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "content_html": {"type": "string"},
                    },
                    "required": ["content"],
                },
            },
            {
                "name": "clipboard_get",
                "description": "Read current Windows clipboard text content.",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        if tool_name == "clipboard_set":
            set_windows_clipboard_text(
                str(arguments.get("content", "")),
                str(arguments.get("content_html", "")),
            )
            return {"ok": True}
        if tool_name == "clipboard_get":
            content = get_windows_clipboard_text()
            return {"content": content, "length": len(content)}
        raise RuntimeError(f"unknown tool: {tool_name}")

    def register(self, mcp: Any) -> None:
        @mcp.tool()
        def clipboard_set(content: str, content_html: str = "") -> dict:
            """
            Copy content to Windows clipboard. Use content_html to preserve rich style when pasting.
            Plain text keeps spaces, indentation, and newlines.
            """
            try:
                set_windows_clipboard_text(content, content_html)
                return {
                    "success": True,
                    "length": len(content or ""),
                    "has_html": bool((content_html or "").strip()),
                }
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc)}

        @mcp.tool()
        def clipboard_get() -> dict:
            """Read current Windows clipboard text content."""
            try:
                content = get_windows_clipboard_text()
                return {
                    "success": True,
                    "content": content,
                    "length": len(content),
                }
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc)}
