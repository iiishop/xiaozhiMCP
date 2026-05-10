from __future__ import annotations

import json

import pytest

from mcp_router import normalize_incoming_ws_message, parse_ws_json_payload


def test_normalize_incoming_ws_message_deserializes_tool_call_arguments():
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "search", "arguments": '{"query":"xiaozhi"}'},
    }

    result = normalize_incoming_ws_message(json.dumps(payload))

    assert result["params"]["arguments"] == {"query": "xiaozhi"}


def test_normalize_incoming_ws_message_leaves_invalid_argument_strings_unchanged():
    payload = {
        "method": "tools/call",
        "params": {"arguments": "not-json"},
    }

    result = normalize_incoming_ws_message(json.dumps(payload))

    assert result["params"]["arguments"] == "not-json"


def test_parse_ws_json_payload_returns_compact_utf8_json_bytes():
    result = parse_ws_json_payload('{"method":"tools/call","params":{"arguments":"{\\"city\\":\\"北京\\"}"}}')

    assert result == b'{"method":"tools/call","params":{"arguments":{"city":"\xe5\x8c\x97\xe4\xba\xac"}}}'


def test_parse_ws_json_payload_rejects_empty_message():
    with pytest.raises(ValueError, match="empty websocket message"):
        parse_ws_json_payload("  ")
