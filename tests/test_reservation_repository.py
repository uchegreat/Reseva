from database.db import SessionLocal
from database.repository import get_reservation, save_reservation


def test_get_existing_reservation():
    db = SessionLocal()

    try:
        test_reservation_id = "test-repository-lookup"

        # Create a known reservation for this test
        save_reservation(
            db,
            {
                "reservation_id": test_reservation_id,
                "restaurant_id": "rest-001",
                "date": "2026-09-25",
                "time": "19:00",
                "party_size": 2,
            },
        )

        reservation = get_reservation(
            db,
            test_reservation_id,
        )

        assert reservation is not None
        assert reservation.reservation_id == test_reservation_id

    finally:
        db.close()


def test_get_nonexistent_reservation():
    db = SessionLocal()

    try:
        reservation = get_reservation(
            db,
            "res-does-not-exist",
        )

        assert reservation is None

    finally:
        db.close()