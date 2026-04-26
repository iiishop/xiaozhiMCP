from __future__ import annotations

import unittest
from unittest.mock import patch

import components.clipboard as clipboard_module
from components.clipboard import build_cf_html_payload


class ClipboardHtmlPayloadTests(unittest.TestCase):
    def test_build_cf_html_payload_contains_required_markers(self) -> None:
        payload = build_cf_html_payload("<p><b>Hello</b> world</p>")
        text = payload.decode("utf-8")

        self.assertIn("Version:0.9", text)
        self.assertIn("StartHTML:", text)
        self.assertIn("EndHTML:", text)
        self.assertIn("StartFragment:", text)
        self.assertIn("EndFragment:", text)
        self.assertIn("<!--StartFragment-->", text)
        self.assertIn("<!--EndFragment-->", text)

    def test_offsets_are_valid(self) -> None:
        payload = build_cf_html_payload("<div>abc</div>")
        text = payload.decode("utf-8")

        start_html = int(text.split("StartHTML:", 1)[1].split("\r\n", 1)[0])
        end_html = int(text.split("EndHTML:", 1)[1].split("\r\n", 1)[0])
        start_fragment = int(text.split("StartFragment:", 1)[1].split("\r\n", 1)[0])
        end_fragment = int(text.split("EndFragment:", 1)[1].split("\r\n", 1)[0])

        self.assertGreaterEqual(start_html, 0)
        self.assertGreater(end_html, start_html)
        self.assertGreaterEqual(start_fragment, start_html)
        self.assertGreater(end_fragment, start_fragment)
        self.assertEqual(end_html, len(payload))


class ClipboardReadTests(unittest.TestCase):
    @patch("components.clipboard.get_windows_clipboard_text")
    def test_read_function_can_be_mocked(self, mock_get: object) -> None:
        mock_get.return_value = "line1\n    line2"
        value = clipboard_module.get_windows_clipboard_text()
        self.assertEqual(value, "line1\n    line2")


if __name__ == "__main__":
    unittest.main()
