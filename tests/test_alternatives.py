import pytest

from agent.mcp_client import get_alternative_times


@pytest.mark.anyio
async def test_get_alternative_times():

    result = await get_alternative_times.ainvoke({
        "restaurant_id": "rest-001",
        "date": "2026-09-18",
        "requested_time": "21:00",
        "party_size": 2,
    })

    print("\nAlternative times:")
    print(result)

    assert result["success"] is True

    assert result["alternative_times"] == [
        "18:00",
        "18:30",
        "19:00",
        "19:30",
        "20:00",
    ]