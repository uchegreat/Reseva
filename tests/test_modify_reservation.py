import pytest

from agent.mcp_client import modify_reservation
from database.db import SessionLocal
from database.models import Reservation
from database.repository import save_reservation


TEST_RESERVATION_ID = "res-test-modify-001"


def create_test_reservation():
    db = SessionLocal()
    try:
        existing = (
            db.query(Reservation)
            .filter(Reservation.reservation_id == TEST_RESERVATION_ID)
            .first()
        )

        if existing:
            db.delete(existing)
            db.commit()

        return save_reservation(
            db,
            {
                "reservation_id": TEST_RESERVATION_ID,
                "restaurant_id": "rest-001",
                "date": "2026-09-25",
                "time": "19:00",
                "party_size": 2,
            },
        )
    finally:
        db.close()


def delete_test_reservation():
    db = SessionLocal()
    try:
        reservation = (
            db.query(Reservation)
            .filter(Reservation.reservation_id == TEST_RESERVATION_ID)
            .first()
        )

        if reservation:
            db.delete(reservation)
            db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_modify_reservation():
    create_test_reservation()

    try:
        result = await modify_reservation.ainvoke(
            {
                "reservation_id": TEST_RESERVATION_ID,
                "date": "2026-09-25",
                "time": "20:00",
                "party_size": 2,
            }
        )

        assert result["success"] is True

        reservation = result["reservation"]

        assert reservation["reservation_id"] == TEST_RESERVATION_ID
        assert reservation["restaurant_id"] == "rest-001"
        assert reservation["restaurant_name"] == "Bella Italia Mayfair"
        assert reservation["date"] == "2026-09-25"
        assert reservation["time"] == "20:00"
        assert reservation["party_size"] == 2

    finally:
        delete_test_reservation()


@pytest.mark.asyncio
async def test_modify_nonexistent_reservation():
    result = await modify_reservation.ainvoke(
        {
            "reservation_id": "res-does-not-exist",
            "time": "20:00",
        }
    )

    assert result["success"] is False
    assert result["reservation_id"] == "res-does-not-exist"