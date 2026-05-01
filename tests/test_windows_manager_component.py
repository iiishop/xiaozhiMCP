from __future__ import annotations

import unittest
from unittest.mock import patch

from components.windows_manager import (
    filter_windows_by_keyword,
    focus_window,
    merge_windows_with_process_stats,
    normalize_windows,
    select_window_match,
)


class NormalizeWindowsTests(unittest.TestCase):
    def test_filters_empty_titles_and_deduplicates(self) -> None:
        rows = [
            {"title": "", "pid": 1, "hwnd": 10},
            {"title": "Settings", "pid": 2, "hwnd": 11},
            {"title": "Settings", "pid": 2, "hwnd": 12},
            {"title": "Terminal", "pid": 3, "hwnd": 13},
        ]

        out = normalize_windows(rows)
        self.assertEqual(
            out,
            [
                {"title": "Settings", "pid": 2},
                {"title": "Terminal", "pid": 3},
            ],
        )


class WindowSearchTests(unittest.TestCase):
    def test_filter_windows_by_keyword_case_insensitive(self) -> None:
        rows = [
            {"title": "Visual Studio Code", "pid": 11, "hwnd": 101},
            {"title": "Windows Terminal", "pid": 12, "hwnd": 102},
            {"title": "Chrome", "pid": 13, "hwnd": 103},
        ]

        out = filter_windows_by_keyword(rows, "code")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["title"], "Visual Studio Code")

    def test_select_window_match_uses_one_based_index(self) -> None:
        rows = [
            {"title": "Window A", "pid": 1, "hwnd": 11},
            {"title": "Window B", "pid": 2, "hwnd": 22},
        ]

        selected = select_window_match(rows, 2)
        self.assertEqual(selected["hwnd"], 22)

        self.assertIsNone(select_window_match(rows, 3))


class PerformanceMergeTests(unittest.TestCase):
    def test_merge_windows_with_process_stats(self) -> None:
        windows = [
            {"title": "Visual Studio Code", "pid": 100, "hwnd": 1},
            {"title": "Terminal", "pid": 200, "hwnd": 2},
        ]
        stats = {
            100: {"cpu_seconds": 12.5, "working_set_mb": 512.0},
            200: {"cpu_seconds": 2.0, "working_set_mb": 64.0},
        }

        out = merge_windows_with_process_stats(windows, stats)
        self.assertEqual(out[0]["title"], "Visual Studio Code")
        self.assertEqual(out[0]["cpu_seconds"], 12.5)
        self.assertEqual(out[1]["working_set_mb"], 64.0)


class FocusWindowTests(unittest.TestCase):
    @patch("components.windows_manager.win32gui.GetForegroundWindow")
    @patch("components.windows_manager.win32gui.SetForegroundWindow")
    @patch("components.windows_manager.win32gui.BringWindowToTop")
    @patch("components.windows_manager.win32gui.ShowWindow")
    def test_focus_window_direct_success(
        self,
        _show: object,
        _bring: object,
        _set_foreground: object,
        mock_get_foreground: object,
    ) -> None:
        mock_get_foreground.return_value = 123
        out = focus_window(123)
        self.assertTrue(out["activated"])
        self.assertEqual(out["strategy"], "direct")

    @patch("components.windows_manager.win32gui.GetForegroundWindow")
    @patch("components.windows_manager.win32gui.SetForegroundWindow")
    @patch("components.windows_manager.win32gui.BringWindowToTop")
    @patch("components.windows_manager.win32gui.ShowWindow")
    def test_focus_window_reports_failure(
        self,
        _show: object,
        _bring: object,
        _set_foreground: object,
        mock_get_foreground: object,
    ) -> None:
        mock_get_foreground.return_value = 999
        out = focus_window(123)
        self.assertFalse(out["activated"])


if __name__ == "__main__":
    unittest.main()
