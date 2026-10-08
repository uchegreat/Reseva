from database.db import SessionLocal
from database.models import Reservation
from database.repository import (
    cancel_reservation,
    save_reservation,
)


TEST_RESERVATION_ID = "res-test-cancel-001"


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


def test_cancel_existing_reservation():
    db = SessionLocal()

    try:
        delete_test_reservation(db)
        reservation = create_test_reservation(db)

        result = cancel_reservation(
            db,
            TEST_RESERVATION_ID,
        )

        assert result is not None
        assert result.reservation_id == TEST_RESERVATION_ID
        assert result.status == "cancelled"

    finally:
        delete_test_reservation(db)
        db.close()


def test_cancel_reservation_is_persisted():
    db = SessionLocal()

    try:
        delete_test_reservation(db)
        create_test_reservation(db)

        cancel_reservation(
            db,
            TEST_RESERVATION_ID,
        )

        reservation = (
            db.query(Reservation)
            .filter(
                Reservation.reservation_id
                == TEST_RESERVATION_ID
            )
            .first()
        )

        assert reservation is not None
        assert reservation.status == "cancelled"

    finally:
        delete_test_reservation(db)
        db.close()


def test_cancel_nonexistent_reservation():
    db = SessionLocal()

    try:
        result = cancel_reservation(
            db,
            "res-does-not-exist",
        )

        assert result is None

    finally:
        db.close()


def test_cancel_reservation_creates_event():
    db = SessionLocal()

    try:
        delete_test_reservation(db)
        reservation = create_test_reservation(db)

        cancel_reservation(
            db,
            TEST_RESERVATION_ID,
        )

        events = [
            event
            for event in reservation.events
            if event.event_type
            == "reservation_cancelled"
        ]

        assert events
        assert (
            events[-1].description
            == "Reservation cancelled through Reseva."
        )

    finally:
        delete_test_reservation(db)
        db.close()