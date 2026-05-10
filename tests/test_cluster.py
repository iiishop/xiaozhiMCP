from __future__ import annotations

import asyncio

from cluster import ClientRegistry


def run(coro):
    return asyncio.run(coro)


def test_register_rejects_tool_name_conflict_between_clients():
    registry = ClientRegistry()

    first_ok, first_msg = run(
        registry.register(
            node_id="node-a",
            websocket=object(),
            platform="Windows",
            tools=[{"name": "search", "description": "", "input_schema": {}}],
        )
    )
    second_ok, second_msg = run(
        registry.register(
            node_id="node-b",
            websocket=object(),
            platform="Linux",
            tools=[{"name": "search", "description": "", "input_schema": {}}],
        )
    )

    assert first_ok is True
    assert first_msg == "ok"
    assert second_ok is False
    assert second_msg == "tool name conflict: search"


def test_register_rejects_reserved_server_tool_name():
    registry = ClientRegistry()
    run(registry.set_reserved_tool_names({"local_search"}))

    ok, msg = run(
        registry.register(
            node_id="node-a",
            websocket=object(),
            platform="Windows",
            tools=[{"name": "local_search"}],
        )
    )

    assert ok is False
    assert msg == "tool name conflict with server local tool: local_search"


def test_reregistering_same_client_replaces_old_tool_mapping():
    registry = ClientRegistry()

    run(
        registry.register(
            node_id="node-a",
            websocket=object(),
            platform="Windows",
            tools=[{"name": "old_tool"}],
        )
    )
    ok, msg = run(
        registry.register(
            node_id="node-a",
            websocket=object(),
            platform="Windows",
            tools=[{"name": "new_tool"}],
        )
    )

    assert ok is True
    assert msg == "ok"
    assert run(registry.route_tool("old_tool")) is None
    assert run(registry.route_tool("new_tool")) is not None
