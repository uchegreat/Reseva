import json

from langchain_core.tools import tool
from mcp import Client

from mcp_servers.restaurant_server import mcp


@tool
async def search_restaurants(
    location: str,
    cuisine: str | None = None,
):
    """
    Search for restaurants through the Reseva MCP server.

    Use this tool when you need to find restaurants based on
    location and optionally cuisine.
    """

    async with Client(mcp) as client:

        result = await client.call_tool(
            "search_restaurants",
            {
                "location": location,
                "cuisine": cuisine,
            },
        )

        return result.structured_content["result"]


@tool
async def check_availability(
    restaurant_id: str,
    date: str,
    time: str,
    party_size: int,
):
    """
    Check restaurant availability through the Reseva MCP server.

    Use this tool when you need to determine whether a restaurant
    has a table for a specific date, time and party size.
    """

    async with Client(mcp) as client:

        result = await client.call_tool(
            "check_availability",
            {
                "restaurant_id": restaurant_id,
                "date": date,
                "time": time,
                "party_size": party_size,
            },
        )

        if result.structured_content:
            return result.structured_content["result"]

        if result.content:
            text = result.content[0].text
            return json.loads(text)

        return {
            "available": False,
            "message": "No availability data was returned.",
        }

@tool
async def get_alternative_times(
    restaurant_id: str,
    date: str,
    requested_time: str,
    party_size: int,
):
    """
    Find alternative available times for a restaurant
    when the requested time is unavailable.
    """

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_alternative_times",
            {
                "restaurant_id": restaurant_id,
                "date": date,
                "requested_time": requested_time,
                "party_size": party_size,
            },
        )

        if result.structured_content:
            return result.structured_content["result"]

        if result.content:
            text = result.content[0].text
            return json.loads(text)

        return {
            "success": False,
            "alternative_times": [],
            "message": "No alternative time data was returned.",
        }

@tool
async def create_reservation(
    restaurant_id: str,
    date: str,
    time: str,
    party_size: int,
):
    """
    Create a reservation through the Reseva MCP server.
    """

    async with Client(mcp) as client:
        result = await client.call_tool(
            "create_reservation",
            {
                "restaurant_id": restaurant_id,
                "date": date,
                "time": time,
                "party_size": party_size,
            },
        )

        if result.structured_content:
            return result.structured_content["result"]

        if result.content:
            text = result.content[0].text
            return json.loads(text)

        return {
            "success": False,
            "message": "No reservation result was returned.",
        }

@tool
async def get_reservation(reservation_id: str):
    """Retrieve an existing reservation by its reservation ID."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_reservation",
            {"reservation_id": reservation_id},
        )

        if result.structured_content:
            return result.structured_content["result"]

        if result.content:
            return json.loads(result.content[0].text)

        return {
            "success": False,
            "message": "No reservation data was returned.",
        }

@tool
async def modify_reservation(
    reservation_id: str,
    date: str | None = None,
    time: str | None = None,
    party_size: int | None = None,
):
    """Modify an existing reservation."""

    async with Client(mcp) as client:
        result = await client.call_tool(
            "modify_reservation",
            {
                "reservation_id": reservation_id,
                "date": date,
                "time": time,
                "party_size": party_size,
            },
        )

        if result.structured_content:
            return result.structured_content["result"]

        if result.content:
            return json.loads(result.content[0].text)

        return {
            "success": False,
            "message": "No reservation modification result was returned.",
        }
@tool
async def cancel_reservation(reservation_id: str):
    """Cancel an existing reservation through the Reseva MCP server."""

    async with Client(mcp) as client:

        result = await client.call_tool(
            "cancel_reservation",
            {
                "reservation_id": reservation_id,
            },
        )

        if result.structured_content:
            return result.structured_content["result"]

        if result.content:
            return json.loads(result.content[0].text)

        return {
            "success": False,
            "reservation_id": reservation_id,
            "message": "No reservation cancellation result was returned.",
        }