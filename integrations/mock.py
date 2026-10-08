from typing import Any

from agent.mcp_client import (
    search_restaurants as mcp_search_restaurants,
    check_availability as mcp_check_availability,
    get_alternative_times as mcp_get_alternative_times,
    create_reservation as mcp_create_reservation,
    get_reservation as mcp_get_reservation,
    modify_reservation as mcp_modify_reservation,
    cancel_reservation as mcp_cancel_reservation,
)

from .base import RestaurantBookingProvider


class MockRestaurantProvider(RestaurantBookingProvider):
    """
    Development restaurant provider.

    This provider uses the existing Reseva MCP restaurant server.
    It allows us to develop and test the provider architecture
    without making real restaurant bookings.
    """

    async def search_restaurants(
        self,
        location: str,
        cuisine: str | None = None,
    ) -> list[dict[str, Any]]:
        result = await mcp_search_restaurants.ainvoke(
            {
                "location": location,
                "cuisine": cuisine,
            }
        )

        return result

    async def check_availability(
        self,
        restaurant_id: str,
        date: str,
        time: str,
        party_size: int,
    ) -> dict[str, Any]:
        result = await mcp_check_availability.ainvoke(
            {
                "restaurant_id": restaurant_id,
                "date": date,
                "time": time,
                "party_size": party_size,
            }
        )

        return result

    async def get_alternative_times(
        self,
        restaurant_id: str,
        date: str,
        requested_time: str,
        party_size: int,
    ) -> Any:
        result = await mcp_get_alternative_times.ainvoke(
            {
                "restaurant_id": restaurant_id,
                "date": date,
                "requested_time": requested_time,
                "party_size": party_size,
            }
        )

        return result

    async def create_reservation(
        self,
        restaurant_id: str,
        date: str,
        time: str,
        party_size: int,
    ) -> dict[str, Any]:
        result = await mcp_create_reservation.ainvoke(
            {
                "restaurant_id": restaurant_id,
                "date": date,
                "time": time,
                "party_size": party_size,
            }
        )

        return result

    async def get_reservation(
        self,
        reservation_id: str,
    ) -> dict[str, Any]:
        result = await mcp_get_reservation.ainvoke(
            {
                "reservation_id": reservation_id,
            }
        )

        return result

    async def modify_reservation(
        self,
        reservation_id: str,
        date: str | None = None,
        time: str | None = None,
        party_size: int | None = None,
    ) -> dict[str, Any]:
        result = await mcp_modify_reservation.ainvoke(
            {
                "reservation_id": reservation_id,
                "date": date,
                "time": time,
                "party_size": party_size,
            }
        )

        return result

    async def cancel_reservation(
        self,
        reservation_id: str,
    ) -> dict[str, Any]:
        result = await mcp_cancel_reservation.ainvoke(
            {
                "reservation_id": reservation_id,
            }
        )

        return result