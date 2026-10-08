import pytest

from integrations.provider import get_restaurant_provider


@pytest.mark.anyio
async def test_provider_search_restaurants():
    provider = get_restaurant_provider()

    restaurants = await provider.search_restaurants(
        location="Mayfair",
        cuisine="Italian",
    )

    assert isinstance(restaurants, list)
    assert len(restaurants) > 0
    assert restaurants[0]["id"]


@pytest.mark.anyio
async def test_provider_check_availability():
    provider = get_restaurant_provider()

    result = await provider.check_availability(
        restaurant_id="rest-001",
        date="2026-09-25",
        time="19:00",
        party_size=2,
    )

    assert isinstance(result, dict)
    assert result["restaurant_id"] == "rest-001"
    assert result["date"] == "2026-09-25"
    assert result["time"] == "19:00"
    assert result["party_size"] == 2
    assert result["available"] is True


@pytest.mark.anyio
async def test_provider_alternative_times():
    provider = get_restaurant_provider()

    result = await provider.get_alternative_times(
        restaurant_id="rest-002",
        date="2026-09-25",
        requested_time="19:00",
        party_size=2,
    )

    assert result is not None