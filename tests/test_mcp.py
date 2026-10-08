import anyio

from mcp import Client

from mcp_servers.restaurant_server import mcp


async def main():
    async with Client(mcp) as client:

        tools = await client.list_tools()

        print("\nAvailable MCP tools:")

        for tool in tools.tools:
            print("-", tool.name)

        result = await client.call_tool(
            "search_restaurants",
            {
                "location": "Mayfair",
                "cuisine": "Italian",
            },
        )

        print("\nSearch result:")
        print(result)


if __name__ == "__main__":
    anyio.run(main)