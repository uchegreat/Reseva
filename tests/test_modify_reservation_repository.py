from database.db import SessionLocal
from database.models import Reservation
from database.repository import (
    get_reservation,
    modify_reservation,
    save_reservation,
)


TEST_RESERVATION_ID = "res-test-modify-001"


def create_test_reservation(db):
    reservation = save_reservation(
        db,
        {
            "reservation_id": TEST_RESERVATION_ID,
            "restaurant_id": "rest-001",
            "date": "2026-09-25",
            "time": "19:00",
            "party_size": 2,
        },
    )

    return reservation


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


def test_modify_existing_reservation():
    db = SessionLocal()

    try:
        delete_test_reservation(db)
        create_test_reservation(db)

        reservation = modify_reservation(
            db,
            TEST_RESERVATION_ID,
            date="2026-09-25",
            time="20:00",
            party_size=2,
        )

        assert reservation is not None
        assert reservation.reservation_id == TEST_RESERVATION_ID
        assert reservation.date == "2026-09-25"
        assert reservation.time == "20:00"
        assert reservation.party_size == 2

    finally:
        delete_test_reservation(db)
        db.close()


def test_modified_reservation_is_persisted():
    db = SessionLocal()

    try:
        delete_test_reservation(db)
        create_test_reservation(db)

        modify_reservation(
            db,
            TEST_RESERVATION_ID,
            time="20:00",
        )

        reservation = get_reservation(
            db,
            TEST_RESERVATION_ID,
        )

        assert reservation is not None
        assert reservation.time == "20:00"

    finally:
        delete_test_reservation(db)
        db.close()


def test_modify_nonexistent_reservation():
    db = SessionLocal()

    try:
        reservation = modify_reservation(
            db,
            "res-does-not-exist",
            time="20:00",
        )

        assert reservation is None

    finally:
        db.close()


def test_modify_reservation_creates_event():
    db = SessionLocal()

    try:
        delete_test_reservation(db)
        reservation = create_test_reservation(db)

        modify_reservation(
            db,
            TEST_RESERVATION_ID,
            time="20:30",
        )

        events = [
            event
            for event in reservation.events
            if event.event_type == "reservation_modified"
        ]

        assert events
        assert events[-1].event_type == "reservation_modified"
        assert (
            events[-1].description
            == "Reservation modified through Reseva."
        )

    finally:
        delete_test_reservation(db)
        db.close()
