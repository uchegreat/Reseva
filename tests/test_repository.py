from database.db import SessionLocal
from database.models import Reservation, ReservationEvent
from database.repository import save_reservation


def test_save_reservation():
    db = SessionLocal()
    reservation = None

    try:
        reservation_data = {
            "reservation_id": "test-res-001",
            "restaurant_id": "rest-001",
            "date": "2026-10-01",
            "time": "19:00",
            "party_size": 2,
        }

        reservation = save_reservation(
            db,
            reservation_data,
        )

        assert reservation.reservation_id == "test-res-001"
        assert reservation.restaurant_id == "rest-001"
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