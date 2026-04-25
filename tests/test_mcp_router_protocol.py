from __future__ import annotations

import asyncio
import unittest

from mcp_router import read_stdio_message


class RouterProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_json_line_message(self) -> None:
        reader = asyncio.StreamReader()
        reader.feed_data(b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n')
        reader.feed_eof()

        payload = await read_stdio_message(reader)
        self.assertEqual(payload, b'{"jsonrpc":"2.0","id":1,"method":"ping"}')

    async def test_reads_content_length_message(self) -> None:
        reader = asyncio.StreamReader()
        body = b'{"jsonrpc":"2.0","id":2,"result":{}}'
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        reader.feed_data(header + body)
        reader.feed_eof()

        payload = await read_stdio_message(reader)
        self.assertEqual(payload, body)


if __name__ == "__main__":
    unittest.main()
