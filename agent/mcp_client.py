"""
Reseva MCP client (in-process).

The restaurant MCP server lives in the same codebase as the agent, so
the client talks to it through an in-memory transport instead of
spawning `python -m mcp_servers.restaurant_server` as a child process.

Why: a child process does not inherit the import path or working
directory that the LangGraph platform sets up for the agent, so on the
hosted deployment the server could exit before the MCP handshake and
raise `MCPError: Connection closed`. In-process there is nothing to
spawn, so that failure mode is gone.

All tool names and signatures are unchanged, so agent/graph.py,
agent/claude.py, integrations/mock.py and the tests need no edits.
"""

import json

from langchain_core.tools import tool
from mcp import Client

from mcp_servers.restaurant_server import mcp


# ---------------------------------------------------------
# RESULT HELPER
# ---------------------------------------------------------

def extract_result(result):
    """
    Extract a plain Python value from an MCP tool result.

    Handles both shapes the SDK can return:
    - wrapped:   {"result": <value>}   (e.g. tools returning a list)
    - unwrapped: {<fields>}            (e.g. tools returning a dict)
    """

    structured = getattr(result, "structured_content", None)

    if structured:
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]
        return structured

    content = getattr(result, "content", None)

    if content:
        first_content = content[0]

        if hasattr(first_content, "text"):
            try:
                return json.loads(first_content.text)
            except json.JSONDecodeError:
                return first_content.text

    return None


# ---------------------------------------------------------
# SHARED CALL HELPER
# ---------------------------------------------------------

async def _call_tool(name: str, arguments: dict):
    """Call a tool on the in-process Reseva MCP server."""

    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments)
        return extract_result(result)


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

    return await _call_tool(
        "search_restaurants",
        {
            "location": location,
            "cuisine": cuisine,
        },
    )


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

    return await _call_tool(
        "check_availability",
        {
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
        },
    )


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

    return await _call_tool(
        "get_alternative_times",
        {
            "restaurant_id": restaurant_id,
            "date": date,
            "requested_time": requested_time,
            "party_size": party_size,
        },
    )


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

    return await _call_tool(
        "create_reservation",
        {
            "restaurant_id": restaurant_id,
            "date": date,
            "time": time,
            "party_size": party_size,
        },
    )


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

    return await _call_tool(
        "get_reservation",
        {
            "reservation_id": reservation_id,
        },
    )


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

    return await _call_tool(
        "modify_reservation",
        {
            "reservation_id": reservation_id,
            "date": date,
            "time": time,
            "party_size": party_size,
        },
    )


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

    return await _call_tool(
        "cancel_reservation",
        {
            "reservation_id": reservation_id,
        },
    )