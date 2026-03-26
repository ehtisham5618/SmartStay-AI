"""List and call SmartStay tools through the official MCP client."""

import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    async with streamable_http_client("http://localhost:8001/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            available = await session.list_tools()
            print([tool.name for tool in available.tools])
            result = await session.call_tool(
                "calculate_room_cost",
                {"room_type": "Deluxe", "check_in": "2026-05-01", "check_out": "2026-05-04", "guests": 2},
            )
            print(result.structuredContent or result.content)


if __name__ == "__main__":
    asyncio.run(main())

