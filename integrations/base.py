from abc import ABC, abstractmethod
from typing import Any


class RestaurantBookingProvider(ABC):
    """Common interface for all restaurant booking providers."""

    @abstractmethod
    async def search_restaurants(
        self,
        location: str,
        cuisine: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for restaurants."""
        raise NotImplementedError

    @abstractmethod
    async def check_availability(
        self,
        restaurant_id: str,
        date: str,
        time: str,
        party_size: int,
    ) -> dict[str, Any]:
        """Check restaurant availability."""
        raise NotImplementedError

    @abstractmethod
    async def get_alternative_times(
        self,
        restaurant_id: str,
        date: str,
        requested_time: str,
        party_size: int,
    ) -> Any:
        """Get alternative available times."""
        raise NotImplementedError

    @abstractmethod
    async def create_reservation(
        self,
        restaurant_id: str,
        date: str,
        time: str,
        party_size: int,
    ) -> dict[str, Any]:
        """Create a restaurant reservation."""
        raise NotImplementedError

    @abstractmethod
    async def get_reservation(
        self,
        reservation_id: str,
    ) -> dict[str, Any]:
        """Get an existing reservation."""
        raise NotImplementedError

    @abstractmethod
    async def modify_reservation(
        self,
        reservation_id: str,
        date: str | None = None,
        time: str | None = None,
        party_size: int | None = None,
    ) -> dict[str, Any]:
        """Modify an existing reservation."""
        raise NotImplementedError

    @abstractmethod
    async def cancel_reservation(
        self,
        reservation_id: str,
    ) -> dict[str, Any]:
        """Cancel an existing reservation."""
        raise NotImplementedError