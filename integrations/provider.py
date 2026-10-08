from .base import RestaurantBookingProvider
from .mock import MockRestaurantProvider


def get_restaurant_provider() -> RestaurantBookingProvider:
    """
    Return the restaurant booking provider used by Reseva.

    The mock provider is currently used for development and testing.
    A real provider can be plugged in later without changing the
    rest of the application.
    """

    return MockRestaurantProvider()

