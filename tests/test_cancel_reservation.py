from database.db import SessionLocal
from database.models import Reservation
from database.repository import save_reservation
from agent.mcp_client import cancel_reservation


TEST_RESERVATION_ID = "res-test-cancel-002"


def create_test_reservation(db):
    return save_reservation(
        db,
        {
            "reservation_id": TEST_RESERVATION_ID,
            "restaurant_id": "rest-001",
            "date": "2026-09-26",
            "time": "19:00",
            "party_size": 2,
        },
    )


def delete_test_reservation(db):
    reservation = (
        db.query(Reservation)
        .filter(
            Reservation.reservation_id == TEST_RESERVATION_ID
        )
        .first()
    )

    if reservation:
        db.delete(reservation)
        db.commit()


def test_cancel_reservation_through_mcp():
    db = SessionLocal()

    try:
        delete_test_reservation(db)
        create_test_reservation(db)

        result = __import__("asyncio").run(
            cancel_reservation.ainvoke(
                {
                    "reservation_id": TEST_RESERVATION_ID
                }
            )
        )

        assert result["success"] is True
        assert (
            result["reservation"]["reservation_id"]
            == TEST_RESERVATION_ID
        )
        assert result["reservation"]["status"] == "cancelled"

    finally:
        delete_test_reservation(db)
        db.close()


def test_cancel_nonexistent_reservation_through_mcp():
    result = __import__("asyncio").run(
        cancel_reservation.ainvoke(
            {
                "reservation_id": "res-does-not-exist"
            }
        )
    )

    assert result["success"] is False
    assert result["reservation_id"] == "res-does-not-exist"