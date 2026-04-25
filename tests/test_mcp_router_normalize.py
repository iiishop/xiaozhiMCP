from __future__ import annotations

import json
import unittest

from mcp_router import normalize_incoming_ws_message


class NormalizeIncomingWsMessageTests(unittest.TestCase):
    def test_parses_tools_call_arguments_string_into_object(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "googlecalendar_call_tool",
                "arguments": '{"tool_name":"events_list","arguments_json":"{\\"calendarId\\":\\"primary\\"}"}',
            },
        }

        out = normalize_incoming_ws_message(json.dumps(payload))
        self.assertIsInstance(out["params"]["arguments"], dict)
        self.assertEqual(out["params"]["arguments"]["tool_name"], "events_list")

    def test_keeps_valid_arguments_object_unchanged(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "exa_web_search",
                "arguments": {"keywords": "llm news"},
            },
        }

        out = normalize_incoming_ws_message(json.dumps(payload))
        self.assertEqual(out["params"]["arguments"], {"keywords": "llm news"})


if __name__ == "__main__":
    unittest.main()
