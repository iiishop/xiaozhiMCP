from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys

import websockets

from config_loader import get_nested_str, load_config

logger = logging.getLogger("mcp_router")


def normalize_incoming_ws_message(message: str | bytes) -> dict | list | str | int | float | bool | None:
    if isinstance(message, bytes):
        text = message.decode("utf-8", errors="replace")
    else:
        text = message

    payload = json.loads(text)
    if not isinstance(payload, dict):
        return payload

    if payload.get("method") == "tools/call":
        params = payload.get("params")
        if isinstance(params, dict):
            arguments = params.get("arguments")
            if isinstance(arguments, str):
                try:
                    parsed = json.loads(arguments)
                    if isinstance(parsed, dict):
                        params["arguments"] = parsed
                except Exception:  # noqa: BLE001
                    pass

    return payload


async def read_stdio_message(reader: asyncio.StreamReader) -> bytes:
    line = await reader.readline()
    if not line:
        raise EOFError("stdio closed")

    stripped = line.strip()
    if not stripped:
        return await read_stdio_message(reader)

    if stripped.lower().startswith(b"content-length:"):
        content_length = int(stripped.split(b":", 1)[1].strip())

        while True:
            hline = await reader.readline()
            if not hline:
                raise EOFError("stdio closed while reading headers")
            if hline in (b"\r\n", b"\n"):
                break

        return await reader.readexactly(content_length)

    json.loads(stripped.decode("utf-8", errors="replace"))
    return stripped


def parse_ws_json_payload(msg: str | bytes) -> bytes:
    if isinstance(msg, bytes):
        raw_text = msg.decode("utf-8", errors="replace")
    else:
        raw_text = msg

    text = raw_text.strip()
    if not text:
        raise ValueError("empty websocket message")

    normalized = normalize_incoming_ws_message(text)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


async def websocket_to_stdio(ws: websockets.WebSocketClientProtocol, writer: asyncio.StreamWriter) -> None:
    async for message in ws:
        payload = parse_ws_json_payload(message)
        writer.write(payload + b"\n")
        await writer.drain()


async def stdio_to_websocket(reader: asyncio.StreamReader, ws: websockets.WebSocketClientProtocol) -> None:
    while True:
        payload = await read_stdio_message(reader)
        await ws.send(payload.decode("utf-8", errors="replace"))


async def run_router(endpoint: str, command: list[str]) -> None:
    logger.info("Starting local MCP process: %s", " ".join(command))

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert proc.stdin is not None
    assert proc.stdout is not None

    async def consume_stderr() -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            logger.info("local-mcp: %s", line.decode("utf-8", errors="replace").rstrip())

    stderr_task = asyncio.create_task(consume_stderr())

    logger.info("Connecting to xiaozhi endpoint...")
    try:
        async with websockets.connect(endpoint, max_size=2**20, ping_interval=20, ping_timeout=20) as ws:
            logger.info("Connected to xiaozhi endpoint")

            task_a = asyncio.create_task(websocket_to_stdio(ws, proc.stdin))
            task_b = asyncio.create_task(stdio_to_websocket(proc.stdout, ws))

            done, pending = await asyncio.wait({task_a, task_b}, return_when=asyncio.FIRST_EXCEPTION)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                err = task.exception()
                if err:
                    raise err
    finally:
        stderr_task.cancel()
        await asyncio.gather(stderr_task, return_exceptions=True)

        if proc.stdin and not proc.stdin.is_closing():
            proc.stdin.close()
        if proc.stdout and not proc.stdout.at_eof():
            proc.stdout.feed_eof()

        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route xiaozhi MCP endpoint <-> local stdio MCP server")
    parser.add_argument(
        "--endpoint",
        default="",
        help="xiaozhi MCP endpoint websocket url",
    )
    parser.add_argument(
        "--server",
        default="",
        help="local python MCP stdio server script path",
    )
    parser.add_argument(
        "--config",
        default="config.toml",
        help="config file path (.toml), default: config.toml",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    args = parse_args()

    config = load_config(args.config)
    endpoint = (
        args.endpoint
        or get_nested_str(config, "xiaozhi", "endpoint")
        or os.getenv("MCP_ENDPOINT", "")
    )
    server_script = (
        args.server
        or get_nested_str(config, "xiaozhi", "server_script")
        or "app_server.py"
    )

    if not endpoint:
        logger.error("MCP endpoint is missing. Set in --endpoint or config file or MCP_ENDPOINT")
        return 2

    command = [sys.executable, server_script, "--config", args.config]
    try:
        asyncio.run(run_router(endpoint, command))
        return 0
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        return 130
    except Exception as exc:  # noqa: BLE001
        logger.exception("Router crashed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
