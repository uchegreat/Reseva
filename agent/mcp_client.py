import json
from contextlib import asynccontextmanager

from langchain_core.tools import tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ---------------------------------------------------------
# MCP SERVER CONFIGURATION
# ---------------------------------------------------------

server_params = StdioServerParameters(
    command="python",
    args=["-m", "mcp_servers.restaurant_server"],
)


# ---------------------------------------------------------
# MCP CONNECTION
# ---------------------------------------------------------

@asynccontextmanager
async def get_mcp_session():
    """
    Start the restaurant MCP server as a subprocess and
    create an MCP client session over stdio.
    """

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


# ---------------------------------------------------------
# RESULT HELPER
# ---------------------------------------------------------

def extract_result(result):
    """
    Extract structured MCP tool results.
    """

    if result.structured_content:
        return result.structured_content.get("result")

    if result.content:
        first_content = result.content[0]

        if hasattr(first_content, "text"):
            try:
                return json.loads(first_content.text)
            except json.JSONDecodeError:
                return first_content.text

    return None


# ---------------------------------------------------------
# SEARCH RESTAURANTS
# ---------------------------------------------------------

@tool
async def search_restaurants(
    location: str,
    cuisine: str | None = None,
):
    """
    Search for restaurants matching a location and
    optional cuisine.
    """

    async with get_mcp_session() as session:

        result = await session.call_tool(
            "search_restaurants",
            {
                "location": location,
                "cuisine": cuisine,
            },
        )

        return extract_result(result)


# ---------------------------------------------------------
# CHECK AVAILABILITY
# ---------------------------------------------------------

@tool
async def check_availability(
    restaurant_id: str,
    date: str,
    time: str,
    party_size: int,
):
    """
    Check whether a restaurant is available for the
    requested date, time and party size.
    """

    async with get_mcp_session() as session:

        result = await session.call_tool(
            "check_availability",
            {
                "restaurant_id": restaurant_id,
                "date": date,
                "time": time,
                "party_size": party_size,
            },
        )

        return extract_result(result)


# ---------------------------------------------------------
# GET ALTERNATIVE TIMES
# ---------------------------------------------------------

@tool
async def get_alternative_times(
    restaurant_id: str,
    date: str,
    requested_time: str,
    party_size: int,
):
    """
    Find alternative reservation times for a restaurant.
    """

    async with get_mcp_session() as session:

        result = await session.call_tool(
            "get_alternative_times",
            {
                "restaurant_id": restaurant_id,
                "date": date,
                "requested_time": requested_time,
                "party_size": party_size,
            },
        )

        return extract_result(result)


# ---------------------------------------------------------
# CREATE RESERVATION
# ---------------------------------------------------------

@tool
async def create_reservation(
    restaurant_id: str,
    date: str,
    time: str,
    party_size: int,
):
    """
    Create a reservation through the restaurant MCP server.

    IMPORTANT:
    The LangGraph workflow controls when this tool is called.
    Claude is not directly given this tool.
    """

    async with get_mcp_session() as session:

        result = await session.call_tool(
            "create_reservation",
            {
                "restaurant_id": restaurant_id,
                "date": date,
                "time": time,
                "party_size": party_size,
            },
        )

        return extract_result(result)


# ---------------------------------------------------------
# GET RESERVATION
# ---------------------------------------------------------

@tool
async def get_reservation(
    reservation_id: str,
):
    """
    Retrieve an existing reservation.
    """

    async with get_mcp_session() as session:

        result = await session.call_tool(
            "get_reservation",
            {
                "reservation_id": reservation_id,
            },
        )

        return extract_result(result)


# ---------------------------------------------------------
# MODIFY RESERVATION
# ---------------------------------------------------------

@tool
async def modify_reservation(
    reservation_id: str,
    date: str | None = None,
    time: str | None = None,
    party_size: int | None = None,
):
    """
    Modify an existing reservation.
    """

    async with get_mcp_session() as session:

        result = await session.call_tool(
            "modify_reservation",
            {
                "reservation_id": reservation_id,
                "date": date,
                "time": time,
                "party_size": party_size,
            },
        )

        return extract_result(result)


# ---------------------------------------------------------
# CANCEL RESERVATION
# ---------------------------------------------------------

@tool
async def cancel_reservation(
    reservation_id: str,
):
    """
    Cancel an existing reservation.
    """

    async with get_mcp_session() as session:

        result = await session.call_tool(
            "cancel_reservation",
            {
                "reservation_id": reservation_id,
            },
        )

        return extract_result(result)