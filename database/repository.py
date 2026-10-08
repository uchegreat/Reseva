from sqlalchemy.orm import Session

from database.models import Reservation, ReservationEvent


def save_reservation(
    db: Session,
    reservation_data: dict,
    user_id: int | None = None,
) -> Reservation:

    reservation_id = reservation_data["reservation_id"]

    # ---------------------------------------------------------
    # Idempotency check
    # ---------------------------------------------------------
    existing_reservation = (
        db.query(Reservation)
        .filter(
            Reservation.reservation_id == reservation_id
        )
        .first()
    )

    if existing_reservation:
        return existing_reservation

    # ---------------------------------------------------------
    # Create new reservation
    # ---------------------------------------------------------
    reservation = Reservation(
        reservation_id=reservation_id,
        user_id=user_id,
        restaurant_id=reservation_data["restaurant_id"],
        date=reservation_data["date"],
        time=reservation_data["time"],
        party_size=reservation_data["party_size"],
        status="confirmed",
    )

    db.add(reservation)
    db.flush()

    # ---------------------------------------------------------
    # Record reservation event
    # ---------------------------------------------------------
    event = ReservationEvent(
        reservation_id=reservation.id,
        event_type="reservation_created",
        description="Reservation created through Reseva.",
    )

    db.add(event)
    db.commit()

    db.refresh(reservation)

    return reservation

def get_reservation(db, reservation_id):
    """Retrieve a reservation by its Reseva reservation ID."""

    reservation = (
        db.query(Reservation)
        .filter(Reservation.reservation_id == reservation_id)
        .first()
    )

    if not reservation:
        return None

    return reservation

def modify_reservation(
    db,
    reservation_id,
    date=None,
    time=None,
    party_size=None,
):
    """Modify an existing reservation."""

    reservation = (
        db.query(Reservation)
        .filter(Reservation.reservation_id == reservation_id)
        .first()
    )

    if not reservation:
        return None

    if date is not None:
        reservation.date = date

    if time is not None:
        reservation.time = time

    if party_size is not None:
        reservation.party_size = party_size

    event = ReservationEvent(
        reservation_id=reservation.id,
        event_type="reservation_modified",
        description="Reservation modified through Reseva.",
    )

    db.add(event)
    db.commit()
    db.refresh(reservation)

    return reservation

def cancel_reservation(db, reservation_id):
    """Cancel an existing reservation."""

    reservation = (
        db.query(Reservation)
        .filter(Reservation.reservation_id == reservation_id)
        .first()
    )

    if not reservation:
        return None

    reservation.status = "cancelled"

    event = ReservationEvent(
        reservation_id=reservation.id,
        event_type="reservation_cancelled",
        description="Reservation cancelled through Reseva.",
    )

    db.add(event)
    db.commit()
    db.refresh(reservation)

    return reservation