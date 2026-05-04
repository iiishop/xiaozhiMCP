from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from error_store import ErrorStore


class ErrorStoreTests(unittest.TestCase):
    def test_add_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "errors.sqlite3"
            store = ErrorStore(str(db))
            store.add_known("cluster", "CLIENT_TOOL_CONFLICT", "tool name conflict: x", "rename tool")
            store.add_unknown("cluster", "boom", "trace")
            rows = store.list_recent(10)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["error_code"], "UNHANDLED")
            self.assertEqual(rows[1]["error_code"], "CLIENT_TOOL_CONFLICT")


if __name__ == "__main__":
    unittest.main()
