import pytest

from agent.mcp_client import get_reservation
from database.db import SessionLocal
from database.repository import save_reservation

def create_test_reservation():
    db = SessionLocal()

    try:
        reservation = save_reservation(
            db,
            {
                "reservation_id": "test-lookup-reservation",
                "restaurant_id": "rest-001",
                "date": "2026-09-25",
                "time": "19:00",
                "party_size": 2,
            },
        )

        return reservation.reservation_id
    finally:
        db.close()

@pytest.mark.asyncio
async def test_get_existing_reservation():

    reservation_id = create_test_reservation()

    result = await get_reservation.ainvoke(
        {"reservation_id": reservation_id}
    )

    assert result["success"] is True

    reservation = result["reservation"]

    assert reservation["reservation_id"] == reservation_id
    assert reservation["restaurant_id"] == "rest-001"
    assert reservation["restaurant_name"] == "Bella Italia Mayfair"
    assert reservation["date"] == "2026-09-25"
    assert reservation["time"] == "19:00"
    assert reservation["party_size"] == 2
    assert reservation["status"] == "confirmed"


@pytest.mark.asyncio
async def test_get_nonexistent_reservation():
    result = await get_reservation.ainvoke(
        {"reservation_id": "res-does-not-exist"}
    )

    assert result["success"] is False
    assert result["reservation_id"] == "res-does-not-exist"
    assert result["message"] == "Reservation not found."