from database.db import SessionLocal
from database.models import Reservation, ReservationEvent
from database.repository import save_reservation


def test_successful_booking_is_persisted():
    db = SessionLocal()

    reservation = None

    try:
        booking_result = {
            "success": True,
            "reservation_id": "res-integration-001",
            "restaurant_id": "rest-001",
            "restaurant_name": "Bella Italia Mayfair",
            "date": "2026-10-10",
            "time": "19:00",
            "party_size": 2,
        }

        reservation = save_reservation(
            db,
            booking_result,
        )

        assert reservation.reservation_id == "res-integration-001"
        assert reservation.restaurant_id == "rest-001"
        assert reservation.date == "2026-10-10"
        assert reservation.time == "19:00"
        assert reservation.party_size == 2
        assert reservation.status == "confirmed"

        event = (
            db.query(ReservationEvent)
            .filter(
                ReservationEvent.reservation_id == reservation.id
            )
            .first()
        )

        assert event is not None
        assert event.event_type == "reservation_created"

    finally:
        if reservation is not None:
            db.query(ReservationEvent).filter(
                ReservationEvent.reservation_id == reservation.id
            ).delete(
                synchronize_session=False
            )

            db.query(Reservation).filter(
                Reservation.id == reservation.id
            ).delete(
                synchronize_session=False
            )

            db.commit()

        db.close()